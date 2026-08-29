"""High-accuracy OCR re-read (on demand).

``refine_regions`` runs an exhaustive per-ROI OCR sweep on a handful of
State/Event boxes the caller flags as weak. It is intentionally slow
(30-60s budget) and is NOT part of the normal ``recognize_image`` fast path,
so that pipeline is untouched. It re-uses the perspective/skew correction
but never re-runs structure, connection or direction detection: it returns
text only for the exact ids it was asked about, and omits any ROI that did
not produce a usable reading so the caller never accepts a forced misread.
"""

from __future__ import annotations

from dataclasses import dataclass
import time

import cv2
import numpy as np
import pytesseract

from .recognizer import (
    OCR_LANGUAGE,
    _available_ocr_language,
    _detect_page_quad,
    _estimate_skew,
    _normalize_ocr_text,
    _ocr_words_to_text,
    _warp_page,
)

_REFINE_BUDGET_S = 55.0
_REFINE_MIN_CONFIDENCE = 0.50
_REFINE_SCALES = (3.0, 4.0)
_REFINE_PSMS = (7, 6, 11)
_REFINE_MAX_REGIONS = 40


@dataclass(frozen=True)
class RefineRegion:
    id: str
    kind: str  # "state" | "transition"
    box: tuple[int, int, int, int]  # original-image space (x, y, width, height)


@dataclass(frozen=True)
class RefineItem:
    id: str
    text: str
    confidence: float


@dataclass(frozen=True)
class RefineResult:
    items: list[RefineItem]
    processing_ms: float
    timed_out: bool
    attempted: int


def _cleanliness(text: str) -> float:
    """0..1 heuristic: how much a reading looks like a real label vs OCR noise."""
    stripped = text.replace(" ", "")
    if not stripped:
        return 0.0
    alnum = sum(1 for character in stripped if character.isalnum())
    ratio = alnum / len(stripped)
    length_ok = 1.0 if 1 <= len(stripped) <= 24 else 0.55
    return ratio * length_ok


def _correct_for_ocr(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Perspective + skew correction and shadow flattening for cleaner label
    OCR. Deliberately NOT ``recognizer._preprocess_image`` -- that one counts
    blobs with ``_detect_states`` to tune its binariser. This path never runs
    any structure / connection / direction detection.

    Returns ``(ocr_gray, forward_transform)`` where ``forward_transform`` maps
    original-image coordinates into the corrected image.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    transform = np.eye(3, dtype=np.float64)
    quad = _detect_page_quad(gray)
    if quad is not None:
        warped = _warp_page(gray, quad)
        if warped is not None:
            gray, perspective = warped  # perspective is a 3x3 homography
            transform = perspective @ transform
    skew = _estimate_skew(gray)
    if skew:
        height, width = gray.shape
        rotation = cv2.getRotationMatrix2D((width / 2, height / 2), -skew, 1.0)
        gray = cv2.warpAffine(gray, rotation, (width, height), flags=cv2.INTER_CUBIC, borderValue=255)
        transform = np.vstack((rotation, (0.0, 0.0, 1.0))) @ transform
    background_size = max(15, (min(gray.shape) // 18) | 1)
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((background_size, background_size), np.uint8))
    ocr_gray = cv2.divide(gray, np.maximum(background, 1), scale=255)
    return ocr_gray, transform


def _clip_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x, y, box_width, box_height = (int(round(value)) for value in box)
    x = max(0, min(x, max(0, width - 1)))
    y = max(0, min(y, max(0, height - 1)))
    box_width = max(1, min(box_width, width - x))
    box_height = max(1, min(box_height, height - y))
    return x, y, box_width, box_height


def _candidate_crops(
    gray_orig: np.ndarray,
    ocr_gray: np.ndarray,
    forward: np.ndarray,
    region: RefineRegion,
) -> list[np.ndarray]:
    """Grayscale crops to try for one region: the original AND the
    perspective-corrected image space, a few margins, plus a taller/wider
    neighbourhood sweep for transition labels (event text usually sits above
    or beside the arrow)."""
    x, y, box_width, box_height = region.box
    if region.kind == "transition":
        pads = ((0.0, 0.0), (-0.30, -0.85), (-0.55, -0.35))
    else:
        pads = ((0.10, 0.24), (0.03, 0.12), (-0.06, -0.06))
    crops: list[np.ndarray] = []

    def _take(source: np.ndarray, raw_box: tuple[int, int, int, int]) -> None:
        cx, cy, cw, ch = _clip_box(raw_box, source.shape[1], source.shape[0])
        if cw < 8 or ch < 6:
            return
        crop = source[cy:cy + ch, cx:cx + cw]
        if float(crop.std()) >= 5.0:
            crops.append(crop)

    for margin_x, margin_y in pads:
        delta_x = int(round(box_width * margin_x))
        delta_y = int(round(box_height * margin_y))
        box_o = (x + delta_x, y + delta_y, box_width - 2 * delta_x, box_height - 2 * delta_y)
        _take(gray_orig, box_o)
        corners = np.float32([
            [box_o[0], box_o[1]],
            [box_o[0] + box_o[2], box_o[1] + box_o[3]],
        ]).reshape(1, -1, 2)
        mapped = cv2.perspectiveTransform(corners, forward.astype(np.float64))[0]
        box_c = (
            min(mapped[0][0], mapped[1][0]),
            min(mapped[0][1], mapped[1][1]),
            abs(mapped[1][0] - mapped[0][0]),
            abs(mapped[1][1] - mapped[0][1]),
        )
        _take(ocr_gray, box_c)
    return crops


def _preprocessors(crop: np.ndarray) -> tuple[np.ndarray, ...]:
    """A small spread of binarisations / contrast treatments for one crop."""
    blurred = cv2.GaussianBlur(crop, (3, 3), 0)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if float(np.count_nonzero(otsu == 0)) > otsu.size * 0.5:
        otsu = cv2.bitwise_not(otsu)
    adaptive = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(crop)
    return (crop, otsu, adaptive, clahe)


def _read_region(
    gray_orig: np.ndarray,
    ocr_gray: np.ndarray,
    forward: np.ndarray,
    region: RefineRegion,
    deadline: float,
) -> tuple[str, float]:
    language = _available_ocr_language() or OCR_LANGUAGE
    best_text, best_conf, best_score = "", 0.0, 0.0
    for crop in _candidate_crops(gray_orig, ocr_gray, forward, region):
        if time.perf_counter() >= deadline:
            break
        for scale in _REFINE_SCALES:
            if time.perf_counter() >= deadline:
                break
            scaled = (
                cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                if scale > 1.01
                else crop
            )
            for prepared in _preprocessors(scaled):
                if time.perf_counter() >= deadline:
                    break
                bordered = cv2.copyMakeBorder(prepared, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
                for psm in _REFINE_PSMS:
                    if time.perf_counter() >= deadline:
                        break
                    try:
                        data = pytesseract.image_to_data(
                            bordered,
                            lang=language,
                            config=f"--oem 1 --psm {psm}",
                            output_type=pytesseract.Output.DICT,
                            timeout=20,
                        )
                    except (pytesseract.TesseractError, RuntimeError, OSError):
                        continue
                    text, confidence = _ocr_words_to_text(data)
                    text = _normalize_ocr_text(text)
                    if not text:
                        continue
                    score = confidence * _cleanliness(text)
                    if score > best_score:
                        best_text, best_conf, best_score = text, confidence, score
                    if confidence >= 0.88 and _cleanliness(text) >= 0.95:
                        return best_text, best_conf
    return best_text, best_conf


def refine_regions(data: bytes, regions: list[RefineRegion]) -> RefineResult:
    started = time.perf_counter()
    regions = list(regions)[:_REFINE_MAX_REGIONS]
    if not regions:
        return RefineResult(items=[], processing_ms=0.0, timed_out=False, attempted=0)
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("画像を読み込めませんでした。PNG / JPEG / WebP を選択してください。")
    if _available_ocr_language() is None:
        return RefineResult(
            items=[],
            processing_ms=round((time.perf_counter() - started) * 1000, 2),
            timed_out=False,
            attempted=0,
        )
    gray_orig = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ocr_gray, forward = _correct_for_ocr(image)
    deadline = started + _REFINE_BUDGET_S
    items: list[RefineItem] = []
    attempted = 0
    for index, region in enumerate(regions):
        now = time.perf_counter()
        if now >= deadline:
            break
        attempted += 1
        regions_left = len(regions) - index
        region_deadline = min(deadline, now + max(6.0, (deadline - now) / regions_left))
        text, confidence = _read_region(
            gray_orig, ocr_gray, forward, region, region_deadline
        )
        if text and confidence >= _REFINE_MIN_CONFIDENCE and _cleanliness(text) >= 0.5:
            items.append(RefineItem(id=region.id, text=text, confidence=round(min(0.97, confidence), 2)))
    return RefineResult(
        items=items,
        processing_ms=round((time.perf_counter() - started) * 1000, 2),
        timed_out=time.perf_counter() >= deadline,
        attempted=attempted,
    )
