from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re
import shutil
import time
import unicodedata

import cv2
import numpy as np
import pytesseract

from .models import Geometry, RecognitionResult, RecognizedState, RecognizedTransition

OCR_LANGUAGE = "jpn+eng"
OCR_AUTO_LABEL_CONFIDENCE = 0.55


@lru_cache(maxsize=1)
def _available_ocr_language() -> str | None:
    """Return the best installed Tesseract language string.

    Prefers ``jpn+eng`` when both packs are present and degrades to whichever
    single pack exists, so a box that is missing one language still runs OCR
    instead of raising. ``None`` means OCR should be skipped entirely. Cached
    because it shells out to ``tesseract --list-langs``.
    """
    if not shutil.which("tesseract"):
        return None
    try:
        languages = set(pytesseract.get_languages(config=""))
    except (pytesseract.TesseractError, OSError):
        return None
    if {"jpn", "eng"}.issubset(languages):
        return "jpn+eng"
    if "jpn" in languages:
        return "jpn"
    if "eng" in languages:
        return "eng"
    return None


@dataclass(frozen=True)
class _OcrRegion:
    text: str
    box: tuple[int, int, int, int]
    confidence: float


@dataclass(frozen=True)
class _PreprocessedImage:
    gray: np.ndarray
    binary: np.ndarray
    state_binary: np.ndarray
    inverse_transform: np.ndarray
    quality: float
    corrections: tuple[str, ...]
    # Perspective/skew-corrected grayscale with illumination flattened but no
    # CLAHE sharpening; the cleanest source for cropped, upscaled label OCR.
    ocr_gray: np.ndarray


def _normalize_ocr_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"[\u0000-\u001f\u007f\u200b-\u200d\ufeff]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized.replace("\u3000", " ")).strip()
    # Tesseract sometimes inserts spaces between individual Japanese glyphs.
    return re.sub(r"(?<=[\u3040-\u30ff\u3400-\u9fff]) (?=[\u3040-\u30ff\u3400-\u9fff])", "", normalized)


def _is_japanese(character: str) -> bool:
    return any(
        start <= ord(character) <= end
        for start, end in ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xFF66, 0xFF9F))
    )


def _join_ocr_tokens(tokens: list[str]) -> str:
    joined = ""
    closing_punctuation = "、。,.!?！？:：;；)]}）］】」』"
    opening_punctuation = "([{（［【「『"
    for token in (_normalize_ocr_text(item) for item in tokens):
        if not token:
            continue
        needs_space = bool(joined)
        if joined and (_is_japanese(joined[-1]) and _is_japanese(token[0])):
            needs_space = False
        if joined and (token[0] in closing_punctuation or joined[-1] in opening_punctuation):
            needs_space = False
        joined += (" " if needs_space else "") + token
    return _normalize_ocr_text(joined)


def _order_quad(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0], ordered[2] = points[np.argmin(sums)], points[np.argmax(sums)]
    ordered[1], ordered[3] = points[np.argmin(differences)], points[np.argmax(differences)]
    return ordered


def _detect_page_quad(gray: np.ndarray) -> np.ndarray | None:
    height, width = gray.shape
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 45, 140)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = height * width
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        if cv2.contourArea(contour) < image_area * 0.42:
            break
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        quad = _order_quad(polygon[:, 0, :])
        frame = np.asarray(((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)), dtype=np.float32)
        # A detected image border does not need a perspective warp.
        if float(np.mean(np.linalg.norm(quad - frame, axis=1))) < min(width, height) * 0.025:
            return None
        return quad
    return None


def _warp_page(gray: np.ndarray, quad: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    top_left, top_right, bottom_right, bottom_left = quad
    width = int(round(max(np.linalg.norm(top_right - top_left), np.linalg.norm(bottom_right - bottom_left))))
    height = int(round(max(np.linalg.norm(bottom_left - top_left), np.linalg.norm(bottom_right - top_right))))
    if width < gray.shape[1] * 0.45 or height < gray.shape[0] * 0.45:
        return None
    destination = np.asarray(((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)), dtype=np.float32)
    transform = cv2.getPerspectiveTransform(quad, destination)
    return cv2.warpPerspective(gray, transform, (width, height), borderValue=255), transform


def _estimate_skew(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 50, 150)
    minimum_length = max(55, int(min(gray.shape) * 0.16))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=45, minLineLength=minimum_length, maxLineGap=18)
    if lines is None:
        return 0.0
    samples: list[tuple[float, float]] = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        residual = ((angle + 45) % 90) - 45
        length = math.hypot(x2 - x1, y2 - y1)
        if abs(residual) <= 15:
            samples.append((residual, length))
    if not samples:
        return 0.0
    samples.sort(key=lambda item: item[0])
    total_weight = sum(weight for _, weight in samples)
    accumulated = 0.0
    median = 0.0
    for angle, weight in samples:
        accumulated += weight
        if accumulated >= total_weight / 2:
            median = angle
            break
    consensus = sum(weight for angle, weight in samples if abs(angle - median) <= 2.5) / total_weight
    return median if 1.0 <= abs(median) <= 12 and consensus >= 0.42 else 0.0


def _enhance_and_binarize(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    background_size = max(15, (min(gray.shape) // 18) | 1)
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((background_size, background_size), np.uint8))
    shadow_removed = cv2.divide(gray, np.maximum(background, 1), scale=255)
    denoised = cv2.bilateralFilter(shadow_removed, 7, 35, 35)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
    adaptive = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 11)
    otsu_threshold, otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    def binary_score(candidate: np.ndarray) -> float:
        ink_ratio = float(np.count_nonzero(candidate)) / candidate.size
        state_count = len(_detect_states(candidate))
        ink_score = max(0.0, 1.0 - abs(ink_ratio - 0.075) / 0.16)
        return min(state_count, 8) * 0.3 + ink_score

    binary = adaptive if binary_score(adaptive) >= binary_score(otsu) else otsu
    dark_pixels = enhanced[enhanced < otsu_threshold]
    light_pixels = enhanced[enhanced >= otsu_threshold]
    contrast_delta = float(np.median(light_pixels) - np.median(dark_pixels)) if dark_pixels.size and light_pixels.size else 0.0
    contrast = min(1.0, max(0.0, contrast_delta / 175))
    sharpness = min(1.0, float(cv2.Laplacian(enhanced, cv2.CV_64F).var()) / 180)
    quality = round(max(0.35, min(0.98, 0.58 * contrast + 0.42 * sharpness)), 2)
    return enhanced, binary, quality, shadow_removed


def _preprocess_image(image: np.ndarray) -> _PreprocessedImage:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    transform = np.eye(3, dtype=np.float64)
    corrections: list[str] = []
    quad = _detect_page_quad(gray)
    if quad is not None:
        warped = _warp_page(gray, quad)
        if warped is not None:
            gray, perspective_transform = warped
            transform = perspective_transform @ transform
            corrections.append("perspective")
    skew = _estimate_skew(gray)
    if skew:
        height, width = gray.shape
        rotation = cv2.getRotationMatrix2D((width / 2, height / 2), -skew, 1.0)
        gray = cv2.warpAffine(gray, rotation, (width, height), flags=cv2.INTER_CUBIC, borderValue=255)
        rotation3 = np.vstack((rotation, (0.0, 0.0, 1.0)))
        transform = rotation3 @ transform
        corrections.append("deskew")
    state_gray = cv2.GaussianBlur(gray, (3, 3), 0)
    state_binary = cv2.adaptiveThreshold(
        state_gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        9,
    )
    enhanced, binary, quality, ocr_gray = _enhance_and_binarize(gray)
    return _PreprocessedImage(
        gray=enhanced,
        binary=binary,
        state_binary=state_binary,
        inverse_transform=np.linalg.inv(transform),
        quality=quality,
        corrections=tuple(corrections),
        ocr_gray=ocr_gray,
    )


def _map_points(points: list[tuple[int, int]], inverse_transform: np.ndarray) -> list[tuple[int, int]]:
    array = np.asarray(points, dtype=np.float32).reshape(1, -1, 2)
    mapped = cv2.perspectiveTransform(array, inverse_transform.astype(np.float64))[0]
    return [(int(round(point[0])), int(round(point[1]))) for point in mapped]


def _map_box(box: tuple[int, int, int, int], inverse_transform: np.ndarray, image_shape: tuple[int, int]) -> tuple[int, int, int, int]:
    x, y, width, height = box
    corners = _map_points([(x, y), (x + width, y), (x + width, y + height), (x, y + height)], inverse_transform)
    left = max(0, min(point[0] for point in corners))
    top = max(0, min(point[1] for point in corners))
    right = min(image_shape[1] - 1, max(point[0] for point in corners))
    bottom = min(image_shape[0] - 1, max(point[1] for point in corners))
    return left, top, max(1, right - left), max(1, bottom - top)


def _extract_ocr_regions(image: np.ndarray) -> list[_OcrRegion]:
    words = pytesseract.image_to_data(
        image,
        lang=_available_ocr_language() or OCR_LANGUAGE,
        config="--oem 1 --psm 11",
        output_type=pytesseract.Output.DICT,
        timeout=12,
    )
    text_items = words.get("text", [])
    groups: dict[tuple[int, int, int, int], list[tuple[int, str, float, tuple[int, int, int, int]]]] = {}
    for index, raw_text in enumerate(text_items):
        text = _normalize_ocr_text(str(raw_text))
        try:
            confidence = float(words["conf"][index]) / 100
            left = int(words["left"][index])
            top = int(words["top"][index])
            width = int(words["width"][index])
            height = int(words["height"][index])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if confidence < 0 or not text or not any(character.isalnum() for character in text):
            continue
        key = tuple(
            int(words.get(field, [0] * len(text_items))[index])
            for field in ("page_num", "block_num", "par_num", "line_num")
        )
        word_number = int(words.get("word_num", [index] * len(text_items))[index])
        groups.setdefault(key, []).append((word_number, text, confidence, (left, top, width, height)))

    regions: list[_OcrRegion] = []
    for tokens in groups.values():
        tokens.sort(key=lambda item: (item[0], item[3][0]))
        text = _join_ocr_tokens([item[1] for item in tokens])
        if not text:
            continue
        left = min(item[3][0] for item in tokens)
        top = min(item[3][1] for item in tokens)
        right = max(item[3][0] + item[3][2] for item in tokens)
        bottom = max(item[3][1] + item[3][3] for item in tokens)
        weights = [max(1, len(item[1].replace(" ", ""))) for item in tokens]
        confidence = sum(item[2] * weight for item, weight in zip(tokens, weights)) / sum(weights)
        regions.append(_OcrRegion(text=text, box=(left, top, right - left, bottom - top), confidence=confidence))
    return sorted(regions, key=lambda region: (region.box[1], region.box[0]))


def _inside(point: tuple[int, int], box: tuple[int, int, int, int], margin: int = 8) -> bool:
    x, y = point
    bx, by, width, height = box
    return bx + margin < x < bx + width - margin and by + margin < y < by + height - margin


def _distance(point: tuple[int, int], box: tuple[int, int, int, int]) -> float:
    bx, by, width, height = box
    return math.hypot(point[0] - (bx + width / 2), point[1] - (by + height / 2))


def _boundary_distance(point: tuple[int, int], box: tuple[int, int, int, int]) -> float:
    """Distance to the state outline, including endpoints slightly inside it."""
    x, y = point
    bx, by, width, height = box
    right, bottom = bx + width, by + height
    outside_x = max(bx - x, x - right, 0)
    outside_y = max(by - y, y - bottom, 0)
    if outside_x or outside_y:
        return math.hypot(outside_x, outside_y)
    return min(x - bx, right - x, y - by, bottom - y)


def _axis_alignment(p1: tuple[int, int], p2: tuple[int, int], first_box: tuple[int, int, int, int], second_box: tuple[int, int, int, int]) -> float:
    shaft = np.asarray(p2, dtype=float) - np.asarray(p1, dtype=float)
    centers = np.asarray(_box_center(second_box)) - np.asarray(_box_center(first_box))
    denominator = float(np.linalg.norm(shaft) * np.linalg.norm(centers))
    return abs(float(np.dot(shaft, centers))) / denominator if denominator else 0.0


def _ray_box_intersection(
    box: tuple[int, int, int, int],
    direction: np.ndarray,
) -> np.ndarray | None:
    center = np.asarray(_box_center(box), dtype=float)
    norm = float(np.linalg.norm(direction))
    if norm == 0:
        return None
    unit = direction / norm
    x, y, width, height = box
    limits = ((x, 0), (x + width, 0), (y, 1), (y + height, 1))
    intersections: list[tuple[float, np.ndarray]] = []
    for boundary, axis in limits:
        if abs(unit[axis]) < 1e-6:
            continue
        distance = (boundary - center[axis]) / unit[axis]
        if distance <= 0:
            continue
        point = center + unit * distance
        if x - 1 <= point[0] <= x + width + 1 and y - 1 <= point[1] <= y + height + 1:
            intersections.append((distance, point))
    return min(intersections, key=lambda item: item[0])[1] if intersections else None


def _projected_box_radius(box: tuple[int, int, int, int], direction: np.ndarray) -> float:
    norm = float(np.linalg.norm(direction))
    if norm == 0:
        return 0.0
    unit = direction / norm
    half_width, half_height = max(1.0, box[2] / 2), max(1.0, box[3] / 2)
    return 1.0 / math.sqrt((unit[0] / half_width) ** 2 + (unit[1] / half_height) ** 2)


def _endpoint_attachment_score(endpoint: tuple[int, int], other: tuple[int, int], box: tuple[int, int, int, int]) -> float:
    gap = _boundary_distance(endpoint, box)
    distance_limit = max(24.0, min(box[2], box[3]) * 0.42)
    proximity = max(0.0, 1.0 - gap / distance_limit)
    outward = np.asarray(endpoint, dtype=float) - np.asarray(_box_center(box), dtype=float)
    tangent = np.asarray(other, dtype=float) - np.asarray(endpoint, dtype=float)
    denominator = float(np.linalg.norm(outward) * np.linalg.norm(tangent))
    alignment = max(0.0, float(np.dot(outward, tangent)) / denominator) if denominator else 0.0
    intersection = _ray_box_intersection(box, tangent)
    intersection_gap = float(np.linalg.norm(np.asarray(endpoint, dtype=float) - intersection)) if intersection is not None else distance_limit
    intersection_score = max(0.0, 1.0 - intersection_gap / distance_limit)
    near_outline = 1.0 if gap <= max(10.0, min(box[2], box[3]) * 0.12) else 0.0
    return 0.4 * proximity + 0.3 * intersection_score + 0.2 * alignment + 0.1 * near_outline


def _infer_connected_states(
    p1: tuple[int, int],
    p2: tuple[int, int],
    boxes: list[tuple[int, int, int, int]],
    *,
    minimum_attachment: float = 0.52,
    minimum_score: float = 0.56,
    arrowhead_endpoint: int | None = None,
) -> tuple[int, int, float, float] | None:
    """Rank endpoint/state pairs using tangent/outline intersections and geometry."""
    ranked: list[tuple[float, int, int]] = []
    shaft = np.asarray(p2, dtype=float) - np.asarray(p1, dtype=float)
    shaft_length = float(np.linalg.norm(shaft))
    if shaft_length == 0:
        return None
    for first_index, first_box in enumerate(boxes):
        first_score = _endpoint_attachment_score(p1, p2, first_box)
        for second_index, second_box in enumerate(boxes):
            if first_index == second_index:
                continue
            second_score = _endpoint_attachment_score(p2, p1, second_box)
            if min(first_score, second_score) < minimum_attachment:
                continue
            alignment = _axis_alignment(p1, p2, first_box, second_box)
            centers_distance = math.dist(_box_center(first_box), _box_center(second_box))
            natural_length = max(
                12.0,
                centers_distance - _projected_box_radius(first_box, shaft) - _projected_box_radius(second_box, shaft),
            )
            length_consistency = min(shaft_length, natural_length) / max(shaft_length, natural_length)
            if length_consistency < 0.28:
                continue
            crossing_penalty = 0.0
            for index, box in enumerate(boxes):
                if index in (first_index, second_index):
                    continue
                projection = _line_projection(_box_center(box), p1, p2)
                if 0.06 < projection < 0.94 and _point_segment_distance(_box_center(box), p1, p2) < min(box[2], box[3]) * 0.45:
                    crossing_penalty += 0.32
            arrowhead_bonus = 0.0
            if arrowhead_endpoint == 1:
                arrowhead_bonus = max(0.0, first_score - 0.7) * 0.08
            elif arrowhead_endpoint == 2:
                arrowhead_bonus = max(0.0, second_score - 0.7) * 0.08
            score = max(
                0.0,
                0.34 * first_score
                + 0.34 * second_score
                + 0.14 * alignment
                + 0.18 * length_consistency
                + arrowhead_bonus
                - crossing_penalty,
            )
            ranked.append((score, first_index, second_index))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    best_score, first, second = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score < minimum_score:
        return None
    return first, second, best_score, best_score - runner_up


def _state_overlap_ratio(p1: tuple[int, int], p2: tuple[int, int], boxes: list[tuple[int, int, int, int]]) -> float:
    samples = 25
    overlap = 0
    for index in range(samples):
        ratio = index / (samples - 1)
        point = (round(p1[0] + (p2[0] - p1[0]) * ratio), round(p1[1] + (p2[1] - p1[1]) * ratio))
        if any(_inside(point, box, margin=-4) for box in boxes):
            overlap += 1
    return overlap / samples


def _box_center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def _box_gap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    first_right, first_bottom = first[0] + first[2], first[1] + first[3]
    second_right, second_bottom = second[0] + second[2], second[1] + second[3]
    horizontal = max(first[0] - second_right, second[0] - first_right, 0)
    vertical = max(first[1] - second_bottom, second[1] - first_bottom, 0)
    return math.hypot(horizontal, vertical)


def _intersection_ratio(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    return intersection / max(1, first[2] * first[3])


def _line_projection(point: tuple[float, float], start: tuple[int, int], end: tuple[int, int]) -> float:
    start_vector = np.asarray(start, dtype=float)
    segment = np.asarray(end, dtype=float) - start_vector
    length_squared = float(np.dot(segment, segment))
    return float(np.dot(np.asarray(point, dtype=float) - start_vector, segment) / length_squared) if length_squared else 0.0


def _point_segment_distance(point: tuple[float, float], start: tuple[int, int], end: tuple[int, int]) -> float:
    point_vector = np.asarray(point, dtype=float)
    start_vector = np.asarray(start, dtype=float)
    segment = np.asarray(end, dtype=float) - start_vector
    length_squared = float(np.dot(segment, segment))
    if length_squared == 0:
        return float(np.linalg.norm(point_vector - start_vector))
    projection = min(1.0, max(0.0, _line_projection(point, start, end)))
    return float(np.linalg.norm(point_vector - (start_vector + projection * segment)))


def _state_ocr_owner(region: _OcrRegion, boxes: list[tuple[int, int, int, int]]) -> int | None:
    center = _box_center(region.box)
    candidates: list[tuple[int, float, float, int]] = []
    for index, box in enumerate(boxes):
        inside_or_overlapping = _inside((int(center[0]), int(center[1])), box, margin=-8) or _intersection_ratio(region.box, box) >= 0.25
        gap = _box_gap(region.box, box)
        near_limit = max(8.0, min(box[2], box[3]) * 0.06)
        if inside_or_overlapping or gap <= near_limit:
            candidates.append((0 if inside_or_overlapping else 1, gap, _distance((int(center[0]), int(center[1])), box), index))
    return min(candidates)[3] if candidates else None


def _transition_ocr_owner(
    region: _OcrRegion,
    paths: list[tuple[tuple[int, int], tuple[int, int]]],
) -> int | None:
    center = _box_center(region.box)
    candidates: list[tuple[float, int]] = []
    for index, (start, end) in enumerate(paths):
        length = math.dist(start, end)
        distance = _point_segment_distance(center, start, end)
        limit = max(45.0, min(90.0, length * 0.28))
        segment = np.asarray(end, dtype=float) - np.asarray(start, dtype=float)
        projection = float(np.dot(np.asarray(center) - np.asarray(start), segment) / max(1.0, np.dot(segment, segment)))
        if distance <= limit and -0.08 <= projection <= 1.08:
            # Prefer labels beside the central shaft over text near arrowheads/states.
            centrality_penalty = abs(projection - 0.5) * min(30.0, length * 0.1)
            candidates.append((distance + centrality_penalty, index))
    return min(candidates)[1] if candidates else None


def _associate_ocr_regions(
    regions: list[_OcrRegion],
    boxes: list[tuple[int, int, int, int]],
    transition_paths: list[tuple[tuple[int, int], tuple[int, int]]],
) -> tuple[list[list[_OcrRegion]], list[list[_OcrRegion]]]:
    state_regions: list[list[_OcrRegion]] = [[] for _ in boxes]
    transition_regions: list[list[_OcrRegion]] = [[] for _ in transition_paths]
    for region in regions:
        state_owner = _state_ocr_owner(region, boxes)
        if state_owner is not None:
            state_regions[state_owner].append(region)
            continue
        transition_owner = _transition_ocr_owner(region, transition_paths)
        if transition_owner is not None:
            transition_regions[transition_owner].append(region)
    return state_regions, transition_regions


def _crop_ocr_region(image: np.ndarray, box: tuple[int, int, int, int], *, psm: int = 7) -> _OcrRegion | None:
    height, width = image.shape[:2]
    x, y, box_width, box_height = box
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(width, x + box_width), min(height, y + box_height)
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    crop = image[y1:y2, x1:x2]
    data = pytesseract.image_to_data(
        crop,
        lang=_available_ocr_language() or OCR_LANGUAGE,
        config=f"--oem 1 --psm {psm}",
        output_type=pytesseract.Output.DICT,
        timeout=5,
    )
    tokens: list[str] = []
    confidences: list[tuple[float, int]] = []
    for raw_text, raw_confidence in zip(data.get("text", []), data.get("conf", [])):
        text = _normalize_ocr_text(str(raw_text))
        try:
            confidence = float(raw_confidence) / 100
        except (TypeError, ValueError):
            continue
        if confidence < 0 or not text or not any(character.isalnum() for character in text):
            continue
        tokens.append(text)
        confidences.append((confidence, max(1, len(text.replace(" ", "")))))
    combined = _join_ocr_tokens(tokens)
    if not combined or not confidences:
        return None
    confidence = sum(value * weight for value, weight in confidences) / sum(weight for _, weight in confidences)
    return _OcrRegion(text=combined, box=(x1, y1, x2 - x1, y2 - y1), confidence=confidence)


# --- Local label OCR: crop weak ROIs -> upscale -> one batched (montage) pass ---

_ROI_TARGET_HEIGHT = 150
_ROI_MAX_SCALE = 4.0
_OCR_PHASE_BUDGET_S = 12.0      # wall-clock cap for global + local OCR combined


def _norm_ocr_key(text: str) -> str:
    """Loose key for comparing two OCR readings of the same label."""
    return "".join(ch for ch in _normalize_ocr_text(text).lower() if ch.isalnum())


def _ocr_words_to_text(data: dict) -> tuple[str, float]:
    tokens: list[tuple[int, int, str, float, int]] = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = _normalize_ocr_text(str(raw_text))
        try:
            confidence = float(data["conf"][index]) / 100
            top = int(data["top"][index])
            left = int(data["left"][index])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if confidence < 0 or not text or not any(character.isalnum() for character in text):
            continue
        tokens.append((top, left, text, confidence, max(1, len(text.replace(" ", "")))))
    if not tokens:
        return "", 0.0
    tokens.sort(key=lambda item: (item[0] // 12, item[1]))
    combined = _join_ocr_tokens([item[2] for item in tokens])
    weight = sum(item[4] for item in tokens)
    confidence = sum(item[3] * item[4] for item in tokens) / weight if weight else 0.0
    return combined, confidence


def _prepare_label_roi(
    gray: np.ndarray,
    box: tuple[int, int, int, int],
    *,
    margin_x_ratio: float,
    margin_y_ratio: float,
) -> np.ndarray | None:
    height, width = gray.shape[:2]
    x, y, box_width, box_height = box
    margin_x = int(round(box_width * margin_x_ratio))
    margin_y = int(round(box_height * margin_y_ratio))
    x1 = max(0, x + margin_x)
    y1 = max(0, y + margin_y)
    x2 = min(width, x + box_width - margin_x)
    y2 = min(height, y + box_height - margin_y)
    if x2 - x1 < 10 or y2 - y1 < 8:
        return None
    crop = gray[y1:y2, x1:x2]
    if float(crop.std()) < 6.0:  # essentially blank -- nothing to read
        return None
    scale = min(_ROI_MAX_SCALE, max(1.0, _ROI_TARGET_HEIGHT / max(1, crop.shape[0])))
    if scale > 1.01:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(crop, 14, 14, 14, 14, cv2.BORDER_CONSTANT, value=255)


def _binarize_label_roi(roi: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(roi, (3, 3), 0)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Tesseract wants dark glyphs on a light field.
    if float(np.count_nonzero(otsu == 0)) > otsu.size * 0.5:
        otsu = cv2.bitwise_not(otsu)
    return otsu


def _transition_label_roi(p1: tuple[int, int], p2: tuple[int, int], perp: float = 0.0) -> tuple[int, int, int, int]:
    length = max(1.0, math.dist(p1, p2))
    unit_x, unit_y = (p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length
    perp_x, perp_y = -unit_y, unit_x  # 90 deg to the shaft
    centre_x = (p1[0] + p2[0]) / 2 + perp_x * perp * length
    centre_y = (p1[1] + p2[1]) / 2 + perp_y * perp * length - length * 0.05
    # The event label sits near the midpoint but *where* varies: above a roughly
    # horizontal arrow, or off to one side of a diagonal one. The caller probes
    # perp = 0 / +0.42 / -0.42, so each window can be a little tighter.
    side = int(max(120, min(320, length * (0.5 if perp else 0.62))))
    return (int(centre_x - side / 2), int(centre_y - side / 2), side, side)


_BATCH_GAP = 46


def _read_labels_batched(
    gray: np.ndarray,
    rois: list[tuple[object, tuple[int, int, int, int], float, float]],
    *,
    binarized: bool = False,
) -> dict:
    """OCR every weak ROI in ONE Tesseract call.

    Each ROI's upscaled crop keeps its own resolution, is padded to a common
    width and stacked into one tall montage; a `--psm 6` pass reads it as a block
    of lines and words map back to their source ROI by vertical position. This
    trades N subprocess spawns for one without distorting the glyphs.
    """
    prepared: list[tuple[object, tuple[int, int, int, int], np.ndarray]] = []
    for key, box, margin_x, margin_y in rois:
        roi = _prepare_label_roi(gray, box, margin_x_ratio=margin_x, margin_y_ratio=margin_y)
        if roi is not None:
            prepared.append((key, box, _binarize_label_roi(roi) if binarized else roi))
    if not prepared:
        return {}

    width = max(roi.shape[1] for _, _, roi in prepared)
    rows: list[np.ndarray] = []
    spans: list[tuple[object, tuple[int, int, int, int], int, int]] = []
    cursor = 0
    for key, box, roi in prepared:
        pad_right = width - roi.shape[1]
        cell = cv2.copyMakeBorder(roi, 0, 0, 0, pad_right, cv2.BORDER_CONSTANT, value=255) if pad_right else roi
        rows.append(cell)
        rows.append(np.full((_BATCH_GAP, width), 255, np.uint8))
        spans.append((key, box, cursor, cursor + cell.shape[0]))
        cursor += cell.shape[0] + _BATCH_GAP
    montage = cv2.copyMakeBorder(np.vstack(rows), 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)

    try:
        data = pytesseract.image_to_data(
            montage,
            lang=_available_ocr_language() or OCR_LANGUAGE,
            config="--oem 1 --psm 6",
            output_type=pytesseract.Output.DICT,
            timeout=15,
        )
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, RuntimeError):
        return {}

    buckets: dict[int, list[tuple[int, str, float, int]]] = {index: [] for index in range(len(spans))}
    for i, raw_text in enumerate(data.get("text", [])):
        text = _normalize_ocr_text(str(raw_text))
        try:
            confidence = float(data["conf"][i]) / 100
            top = int(data["top"][i]) - 16
            left = int(data["left"][i])
            height = int(data["height"][i])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if confidence < 0 or not text or not any(ch.isalnum() for ch in text):
            continue
        middle = top + height / 2
        for index, (_, _, y0, y1) in enumerate(spans):
            if y0 - _BATCH_GAP / 2 <= middle <= y1 + _BATCH_GAP / 2:
                buckets[index].append((left, text, confidence, max(1, len(text.replace(" ", "")))))
                break

    results: dict = {}
    for index, (key, box, _, _) in enumerate(spans):
        tokens = sorted(buckets[index], key=lambda item: item[0])
        if not tokens:
            results[key] = None
            continue
        combined = _join_ocr_tokens([token[1] for token in tokens])
        weight = sum(token[3] for token in tokens)
        confidence = sum(token[2] * token[3] for token in tokens) / weight if weight else 0.0
        results[key] = _OcrRegion(text=combined, box=box, confidence=round(confidence, 4)) if combined else None
    return results


def _resolve_label(global_text: str, global_confidence: float, local: _OcrRegion | None) -> tuple[str, float]:
    """Cross-check the whole-image reading against the upscaled local crop."""
    local_text = local.text if local else ""
    local_confidence = local.confidence if local else 0.0
    if global_text and local_text and _norm_ocr_key(global_text) == _norm_ocr_key(local_text):
        return local_text, min(0.98, max(global_confidence, local_confidence) + 0.08)
    if local_confidence >= max(global_confidence, 0.001):
        return local_text, local_confidence
    return global_text, global_confidence


def _combine_ocr_regions(regions: list[_OcrRegion]) -> tuple[str, float]:
    lines: list[list[_OcrRegion]] = []
    for region in sorted(regions, key=lambda item: (_box_center(item.box)[1], item.box[0])):
        center_y = _box_center(region.box)[1]
        matching_line = next(
            (
                line
                for line in lines
                if abs(center_y - sum(_box_center(item.box)[1] for item in line) / len(line))
                <= max(region.box[3], max(item.box[3] for item in line)) * 0.6
            ),
            None,
        )
        if matching_line is None:
            lines.append([region])
        else:
            matching_line.append(region)
    line_texts = [
        _join_ocr_tokens([region.text for region in sorted(line, key=lambda item: item.box[0])])
        for line in lines
    ]
    text = _normalize_ocr_text(" ".join(line_texts))
    weights = [max(1, len(region.text.replace(" ", ""))) for region in regions]
    confidence = sum(region.confidence * weight for region, weight in zip(regions, weights)) / sum(weights)
    return text, confidence


def _label_confidence(structure_confidence: float, ocr_confidence: float) -> float:
    return round(structure_confidence * 0.45 + ocr_confidence * 0.55, 2)


def _states_along_line(p1: tuple[int, int], p2: tuple[int, int], boxes: list[tuple[int, int, int, int]]) -> tuple[int, int] | None:
    vector = np.asarray(p2, dtype=float) - np.asarray(p1, dtype=float); length = float(np.linalg.norm(vector))
    if length == 0: return None
    unit = vector / length; candidates = []
    for index, (x, y, width, height) in enumerate(boxes):
        offset = np.asarray((x + width / 2, y + height / 2)) - np.asarray(p1)
        projection = float(np.dot(offset, unit)); perpendicular = float(abs(unit[0] * offset[1] - unit[1] * offset[0]))
        if perpendicular < max(width, height) / 2 + 28: candidates.append((projection, index))
    before = [item for item in candidates if item[0] <= length / 2]; after = [item for item in candidates if item[0] > length / 2]
    if not before or not after: return None
    return min(before, key=lambda item: abs(item[0]))[1], min(after, key=lambda item: abs(item[0] - length))[1]


def _detect_states(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    candidates: list[tuple[float, tuple[int, int, int, int]]] = []
    image_area = binary.shape[0] * binary.shape[1]
    for index, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        x, y, width, height = cv2.boundingRect(contour)
        if not 800 < area < image_area * 0.12 or width < 36 or height < 30:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        fill_ratio = area / (width * height)
        circularity = 4 * math.pi * area / max(1.0, perimeter * perimeter)
        has_interior = hierarchy[0][index][2] >= 0
        looks_like_state = (
            len(polygon) >= 4
            and 0.42 < fill_ratio < 0.995
            and circularity >= 0.58
            and width < binary.shape[1] * 0.32
            and has_interior
        )
        if looks_like_state:
            shape_score = circularity + min(0.12, area / image_area * 2)
            candidates.append((shape_score, (x, y, width, height)))

    def _center_inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
        cx, cy = _box_center(inner)
        ox, oy, ow, oh = outer
        return ox < cx < ox + ow and oy < cy < oy + oh

    # A letter counter (D/O/P/A ...) sits fully inside its state outline; drop any
    # candidate that a >=2x larger candidate contains. The outer outline is kept.
    candidates = [
        candidate for candidate in candidates
        if not any(
            other is not candidate
            and other[1][2] * other[1][3] >= 2.0 * (candidate[1][2] * candidate[1][3])
            and _center_inside(candidate[1], other[1])
            for other in candidates
        )
    ]

    selected: list[tuple[int, int, int, int]] = []
    for _, box in sorted(candidates, key=lambda item: (item[0], item[1][2] * item[1][3]), reverse=True):
        x, y, width, height = box
        duplicate = False
        for existing in selected:
            ex, ey, existing_width, existing_height = existing
            intersection = max(0, min(x + width, ex + existing_width) - max(x, ex)) * max(0, min(y + height, ey + existing_height) - max(y, ey))
            union = width * height + existing_width * existing_height - intersection
            center_gap = math.dist(_box_center(box), _box_center(existing))
            if intersection / max(1, union) > 0.35 or center_gap < min(max(width, height), max(existing_width, existing_height)) * 0.38:
                duplicate = True
                break
        if not duplicate:
            selected.append(box)
    return sorted(selected, key=lambda box: (box[0], box[1]))


def _line_angle(line: np.ndarray) -> float:
    return math.atan2(float(line[3] - line[1]), float(line[2] - line[0])) % math.pi


def _merge_collinear_segments(lines: np.ndarray) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    groups: list[list[np.ndarray]] = []
    for line in sorted(lines, key=lambda item: -math.hypot(item[2]-item[0], item[3]-item[1])):
        angle = _line_angle(line); midpoint = np.asarray(((line[0]+line[2])/2, (line[1]+line[3])/2))
        match = None
        for group in groups:
            reference=group[0]; delta=abs(angle-_line_angle(reference)); delta=min(delta,math.pi-delta)
            unit=np.asarray((math.cos(_line_angle(reference)),math.sin(_line_angle(reference)))); normal=np.asarray((-unit[1],unit[0]))
            reference_mid=np.asarray(((reference[0]+reference[2])/2,(reference[1]+reference[3])/2))
            gap=min(math.dist(point,other) for point in ((line[0],line[1]),(line[2],line[3])) for item in group for other in ((item[0],item[1]),(item[2],item[3])))
            if delta < math.radians(10) and abs(float(np.dot(midpoint-reference_mid,normal))) < 12 and gap < 45: match=group; break
        if match is None: groups.append([line])
        else: match.append(line)
    merged=[]
    for group in groups:
        angle=_line_angle(group[0]); unit=np.asarray((math.cos(angle),math.sin(angle))); points=np.asarray([(x[0],x[1]) for x in group]+[(x[2],x[3]) for x in group]); projections=points@unit
        a,b=points[int(np.argmin(projections))],points[int(np.argmax(projections))]; merged.append(((int(a[0]),int(a[1])),(int(b[0]),int(b[1]))))
    return merged


def _deduplicate_segments(
    segments: list[tuple[tuple[int, int], tuple[int, int]]],
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    selected: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for candidate in sorted(segments, key=lambda item: -math.dist(*item)):
        start, end = candidate
        vector = np.asarray(end, dtype=float) - np.asarray(start, dtype=float)
        length = float(np.linalg.norm(vector))
        if length == 0:
            continue
        angle = math.atan2(vector[1], vector[0]) % math.pi
        duplicate = False
        for existing_start, existing_end in selected:
            existing_vector = np.asarray(existing_end, dtype=float) - np.asarray(existing_start, dtype=float)
            existing_length = float(np.linalg.norm(existing_vector))
            existing_angle = math.atan2(existing_vector[1], existing_vector[0]) % math.pi
            angle_gap = abs(angle - existing_angle)
            angle_gap = min(angle_gap, math.pi - angle_gap)
            if angle_gap > math.radians(7):
                continue
            perpendicular_gap = max(
                _point_segment_distance(start, existing_start, existing_end),
                _point_segment_distance(end, existing_start, existing_end),
            )
            projections = sorted((_line_projection(start, existing_start, existing_end), _line_projection(end, existing_start, existing_end)))
            contained_ratio = max(0.0, min(1.0, projections[1]) - max(0.0, projections[0])) * existing_length / length
            if perpendicular_gap <= 11 and contained_ratio >= 0.72:
                duplicate = True
                break
        if not duplicate:
            selected.append(candidate)
    return selected


def _head_score(endpoint: tuple[int,int], other: tuple[int,int], lines: np.ndarray) -> tuple[int,list[tuple[int,int]]]:
    shaft=np.asarray(other,dtype=float)-endpoint; shaft/=max(float(np.linalg.norm(shaft)),1)
    candidates: list[tuple[int, tuple[int, int], float, float]] = []
    for line in lines:
        a,b=np.asarray(line[:2],dtype=float),np.asarray(line[2:],dtype=float); near,far=(a,b) if np.linalg.norm(a-endpoint)<np.linalg.norm(b-endpoint) else (b,a)
        length=float(np.linalg.norm(far-near))
        if np.linalg.norm(near-endpoint)>14 or not 8<length<65: continue
        wing=(far-near)/length; forward=float(np.dot(shaft,wing)); angle=math.degrees(math.acos(min(1,max(-1,forward))))
        if 20<angle<70 and forward > 0:
            cross=shaft[0]*wing[1]-shaft[1]*wing[0]
            candidates.append((1 if cross>=0 else -1, (int(far[0]),int(far[1])), angle, length))
    pairs = [
        (abs(first[2] - second[2]) + abs(first[3] - second[3]) * .35, first, second)
        for first in candidates
        for second in candidates
        if first[0] < second[0] and abs(first[2] - second[2]) <= 22 and min(first[3], second[3]) / max(first[3], second[3]) >= .5
    ]
    if pairs:
        _, first, second = min(pairs, key=lambda item: item[0])
        return 2, [first[1], second[1]]
    return (1, [candidates[0][1]]) if candidates else (0, [])


def _detect_curved_connections(
    binary: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    existing_pairs: set[tuple[int, int]],
) -> list[tuple[int, int, tuple[int, int], tuple[int, int], float, bool]]:
    """Find ink components bridging state outlines when no straight shaft survived."""
    remaining = binary.copy()
    for x, y, width, height in boxes:
        cv2.rectangle(remaining, (max(0, x - 3), max(0, y - 3)), (x + width + 3, y + height + 3), 0, -1)
    remaining = cv2.morphologyEx(remaining, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(remaining, 8)
    results = []
    for component in range(1, component_count):
        x, y, width, height, area = stats[component]
        if area < 45 or max(width, height) < 45 or area > binary.size * 0.08:
            continue
        if area / max(1, width * height) > 0.32:
            continue
        ys, xs = np.where(labels == component)
        points = np.column_stack((xs, ys))[:: max(1, len(xs) // 500)]
        attachments: list[tuple[float, int]] = []
        for index, (bx, by, box_width, box_height) in enumerate(boxes):
            dx = np.maximum.reduce((bx - points[:, 0], points[:, 0] - (bx + box_width), np.zeros(len(points))))
            dy = np.maximum.reduce((by - points[:, 1], points[:, 1] - (by + box_height), np.zeros(len(points))))
            attachments.append((float(np.min(np.hypot(dx, dy))), index))
        nearby = sorted(item for item in attachments if item[0] <= 26)
        if len(nearby) < 2:
            continue
        # A component touching three states in a dense diagram is ambiguous at
        # an intersection. Do not invent a longest connection through it.
        if len(nearby) > 2 and nearby[2][0] - nearby[1][0] < 14:
            continue
        first, second = nearby[0][1], nearby[1][1]
        if tuple(sorted((first, second))) in existing_pairs:
            continue
        first_center, second_center = np.asarray(_box_center(boxes[first])), np.asarray(_box_center(boxes[second]))
        p1 = tuple(map(int, points[int(np.argmin(np.linalg.norm(points - first_center, axis=1)))]))
        p2 = tuple(map(int, points[int(np.argmin(np.linalg.norm(points - second_center, axis=1)))]))
        natural_gap = max(1.0, math.dist(first_center, second_center) - max(boxes[first][2:]) / 2 - max(boxes[second][2:]) / 2)
        if math.dist(p1, p2) < max(40.0, natural_gap * 0.42):
            continue
        source, target = sorted((first, second), key=lambda index: (_box_center(boxes[index])[0], _box_center(boxes[index])[1]))
        results.append((source, target, p1, p2, 0.34, False))
        existing_pairs.add(tuple(sorted((source, target))))
    return results


def _detect_transitions(binary: np.ndarray, boxes: list[tuple[int, int, int, int]], debug: list[dict] | None = None) -> list[tuple[int, int, tuple[int, int], tuple[int, int], float, bool]]:
    minimum_line_length = max(35, int(min(binary.shape) * 0.07))
    lines = cv2.HoughLinesP(binary, 1, np.pi / 180, threshold=28, minLineLength=minimum_line_length, maxLineGap=18)
    detected: dict[tuple[int, int], tuple[int, int, tuple[int, int], tuple[int, int], float, bool]] = {}
    detected_scores: dict[tuple[int, int], float] = {}
    if lines is None or len(boxes) < 2:
        return []
    raw_lines = lines.reshape(-1, 4)
    raw_lines = np.asarray(sorted(raw_lines, key=lambda line: -math.hypot(line[2]-line[0], line[3]-line[1]))[:400])
    head_lines = cv2.HoughLinesP(binary,1,np.pi/180,threshold=10,minLineLength=8,maxLineGap=5)
    head_lines = head_lines.reshape(-1,4) if head_lines is not None else raw_lines
    head_lines = np.asarray(sorted(head_lines, key=lambda line: math.hypot(line[2]-line[0], line[3]-line[1]))[:400])
    candidates = _deduplicate_segments(
        _merge_collinear_segments(raw_lines)
        + [((int(line[0]), int(line[1])), (int(line[2]), int(line[3]))) for line in raw_lines]
    )
    review_candidates: list[tuple[float, int, int, tuple[int, int], tuple[int, int]]] = []
    for p1,p2 in candidates:
        length = math.dist(p1, p2)
        if length < minimum_line_length:
            continue
        overlap = _state_overlap_ratio(p1, p2, boxes)
        if overlap > .46:
            continue
        midpoint = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
        if any(_inside(midpoint, box, margin=10) for box in boxes):
            continue
        score1,wings1=_head_score(p1,p2,head_lines); score2,wings2=_head_score(p2,p1,head_lines)
        arrowhead_endpoint = 1 if score1 == 2 and score1 > score2 else 2 if score2 == 2 and score2 > score1 else None
        connection = _infer_connected_states(p1, p2, boxes, arrowhead_endpoint=arrowhead_endpoint)
        if connection is None:
            # Curved, interrupted, or shadowed shafts often only yield a partial
            # Hough segment. Keep a conservative candidate for human review.
            relaxed = _infer_connected_states(
                p1,
                p2,
                boxes,
                minimum_attachment=0.4,
                minimum_score=0.48,
                arrowhead_endpoint=arrowhead_endpoint,
            )
            if relaxed is not None and overlap <= .38:
                first, second, connection_score, connection_margin = relaxed
                review_score = connection_score + min(0.08, max(0.0, connection_margin)) + min(0.06, length / max(binary.shape) * .08)
                review_candidates.append((review_score, first, second, p1, p2))
            continue
        first, second, connection_score, connection_margin = connection
        if score1==2 and score1>score2:
            source,target,head,head_score=second,first,p1,.9
        elif score2==2 and score2>score1:
            source,target,head,head_score=first,second,p2,.9
        else:
            # Hough segment endpoint order is arbitrary. With no complete V-shaped
            # arrowhead, offer a stable reading-order suggestion but require review.
            source, target = sorted((first, second), key=lambda index: (_box_center(boxes[index])[0], _box_center(boxes[index])[1]))
            head, head_score = None, .45 if score1 != score2 else .25
        confidence = round(min(.96, .62 * head_score + .3 * connection_score + .08 * min(1.0, connection_margin * 4)), 2)
        if connection_margin < 0.1:
            confidence = min(confidence, 0.49)
        # In dense diagrams, unrelated short strokes frequently imitate a V.
        # Preserve the candidate but require review instead of auto-confirming.
        direction_confirmed = confidence >= .68 and head_score >= .9 and connection_margin >= .1 and len(boxes) <= 4
        key = tuple(sorted((source, target)))
        candidate_score = confidence + min(length / max(binary.shape), 1.0) * .05
        if key not in detected or candidate_score > detected_scores[key]:
            detected[key] = (source, target, p1, p2, confidence, direction_confirmed)
            detected_scores[key] = candidate_score
            if debug is not None: debug.append({"shaft":[p1,p2],"source":source,"target":target,"arrowhead":head,"wings":wings1 if head==p1 else wings2 if head==p2 else []})

    for review_score, first, second, p1, p2 in sorted(review_candidates, reverse=True):
        source, target = sorted((first, second), key=lambda index: (_box_center(boxes[index])[0], _box_center(boxes[index])[1]))
        key = tuple(sorted((source, target)))
        if key in detected:
            continue
        confidence = round(min(0.49, max(0.28, review_score * 0.72)), 2)
        detected[key] = (source, target, p1, p2, confidence, False)
        detected_scores[key] = confidence
        if debug is not None:
            debug.append({"shaft": [p1, p2], "source": source, "target": target, "arrowhead": None, "wings": [], "review_only": True})
    for source, target, p1, p2, confidence, confirmed in _detect_curved_connections(binary, boxes, set(detected)):
        key = tuple(sorted((source, target)))
        detected[key] = (source, target, p1, p2, confidence, confirmed)
        if debug is not None:
            debug.append({"shaft": [p1, p2], "source": source, "target": target, "arrowhead": None, "wings": [], "review_only": True, "curved": True})
    return list(detected.values())


def recognize_image(data: bytes, *, _debug: dict | None = None) -> RecognitionResult:
    started = time.perf_counter()
    timings: dict[str, float] = {}

    def _mark(name: str, since: float) -> None:
        timings[name] = round((time.perf_counter() - since) * 1000, 1)

    # Hard wall-clock deadline for the whole OCR phase so recognition always
    # returns well under the frontend's 25s timeout, even on a slow/cold host.
    ocr_deadline = started + _OCR_PHASE_BUDGET_S

    stage = time.perf_counter()
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("画像を読み取れませんでした")
    _mark("decode", stage)

    stage = time.perf_counter()
    processed = _preprocess_image(image)
    _mark("preprocess", stage)
    gray, binary = processed.gray, processed.binary

    stage = time.perf_counter()
    boxes = _detect_states(processed.state_binary)
    _mark("detect_states", stage)
    mapped_boxes = [_map_box(box, processed.inverse_transform, image.shape[:2]) for box in boxes]
    structure_confidence = min(0.82, max(0.5, 0.62 + processed.quality * 0.2))
    states = [
        RecognizedState(
            id=f"state-{index + 1}",
            name=f"State {index + 1}",
            geometry=Geometry(x=x, y=y, width=width, height=height),
            confidence=round(structure_confidence, 2),
            initial=index == 0,
        )
        for index, (x, y, width, height) in enumerate(mapped_boxes)
    ]
    transitions: list[RecognizedTransition] = []
    transition_debug=[]
    stage = time.perf_counter()
    detected_transitions = _detect_transitions(binary, boxes, transition_debug)
    _mark("detect_transitions", stage)
    for index, detected in enumerate(detected_transitions):
        source, target, p1, p2, confidence = detected[:5]
        direction_confirmed = detected[5] if len(detected) > 5 else confidence >= .7
        mapped_p1, mapped_p2 = _map_points([p1, p2], processed.inverse_transform)
        # Poor focus/contrast is an explicit review signal even when an arrowhead
        # happened to match geometrically.
        direction_confirmed = direction_confirmed and processed.quality >= 0.58
        confidence = min(confidence, round(0.45 + processed.quality * 0.5, 2))
        transitions.append(RecognizedTransition(id=f"transition-{index + 1}", **{"from": states[source].id}, to=states[target].id, event=f"event_{index + 1}", geometry=Geometry(x=min(mapped_p1[0], mapped_p2[0]), y=min(mapped_p1[1], mapped_p2[1]), width=abs(mapped_p1[0] - mapped_p2[0]), height=abs(mapped_p1[1] - mapped_p2[1])), confidence=confidence, direction_confirmed=direction_confirmed))
    if _debug is not None:
        mapped_transition_debug = []
        for item in transition_debug:
            mapped_item = dict(item)
            mapped_item["shaft"] = _map_points(item["shaft"], processed.inverse_transform)
            if item.get("arrowhead") is not None:
                mapped_item["arrowhead"] = _map_points([item["arrowhead"]], processed.inverse_transform)[0]
            mapped_item["wings"] = _map_points(item.get("wings", []), processed.inverse_transform) if item.get("wings") else []
            mapped_transition_debug.append(mapped_item)
        _debug.update({"boxes": mapped_boxes, "processed_boxes": boxes, "transitions": mapped_transition_debug, "quality": processed.quality, "corrections": processed.corrections})

    warnings = []
    ocr_regions: list[_OcrRegion] = []
    ocr_failed = False
    ocr_truncated = False
    if not shutil.which("tesseract"):
        ocr_failed = True
    elif not boxes and not detected_transitions:
        pass  # nothing to label
    else:
        stage = time.perf_counter()
        _available_ocr_language()  # first call spawns `tesseract --list-langs`; cached after
        _mark("tesseract_startup", stage)
        if time.perf_counter() >= ocr_deadline:
            ocr_truncated = True
        else:
            try:
                stage = time.perf_counter()
                ocr_regions = _extract_ocr_regions(gray)
                _mark("global_ocr", stage)
            except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, RuntimeError):
                ocr_failed = True
    local_ocr_started = time.perf_counter()

    state_ocr, transition_ocr = _associate_ocr_regions(
        ocr_regions,
        boxes,
        [(item[2], item[3]) for item in detected_transitions],
    )
    low_ocr_labels: list[str] = []
    unread_labels: list[str] = []
    # A confident whole-image reading is kept as-is; the rest are read together in
    # one batched (montage) Tesseract call instead of one call per ROI.
    global_trust = 0.78
    state_global = [_combine_ocr_regions(regions) if regions else ("", 0.0) for regions in state_ocr]
    transition_global = [_combine_ocr_regions(regions) if regions else ("", 0.0) for regions in transition_ocr]

    batched: dict = {}
    if not ocr_failed and time.perf_counter() < ocr_deadline:
        weak_rois: list[tuple[object, tuple[int, int, int, int], float, float]] = []
        for index, (box, (_, confidence)) in enumerate(zip(boxes, state_global)):
            if confidence < global_trust:
                # Centre band of the ellipse/box: wide, but clear of the top/bottom arcs.
                weak_rois.append((("s", index), box, 0.09, 0.27))
        for index, (detected, (_, confidence)) in enumerate(zip(detected_transitions, transition_global)):
            if confidence < global_trust:
                # Probe the midpoint and both perpendicular sides -- diagonal
                # arrows carry their label off to one flank, not just above.
                weak_rois.append((("t", index), _transition_label_roi(detected[2], detected[3], 0.0), 0.0, 0.06))
                weak_rois.append((("tp", index), _transition_label_roi(detected[2], detected[3], 0.42), 0.0, 0.06))
                weak_rois.append((("tn", index), _transition_label_roi(detected[2], detected[3], -0.42), 0.0, 0.06))
        if weak_rois:
            stage = time.perf_counter()
            batched = _read_labels_batched(processed.ocr_gray, weak_rois)
            retry = [
                (key, box, mx, my) for key, box, mx, my in weak_rois
                if (batched.get(key) is None or batched[key].confidence < 0.6)
            ]
            if retry and time.perf_counter() < ocr_deadline:
                for key, region in _read_labels_batched(processed.ocr_gray, retry, binarized=True).items():
                    if region is not None and (batched.get(key) is None or region.confidence > batched[key].confidence):
                        batched[key] = region
            _mark("local_ocr_batch", stage)

    for index, (state, regions) in enumerate(zip(states, state_ocr)):
        global_text, global_confidence = state_global[index]
        if ocr_failed or global_confidence >= global_trust:
            text, confidence = global_text, global_confidence
        elif not batched and time.perf_counter() >= ocr_deadline:
            ocr_truncated = True
            text, confidence = global_text, global_confidence
        else:
            text, confidence = _resolve_label(global_text, global_confidence, batched.get(("s", index)))
        if not text:
            state.confidence = min(state.confidence, 0.58)
            unread_labels.append(state.name)
            continue
        if confidence >= OCR_AUTO_LABEL_CONFIDENCE:
            state.name = text
            state.confidence = _label_confidence(state.confidence, confidence)
        else:
            state.confidence = min(state.confidence, round(confidence, 2))
            low_ocr_labels.append(f"{state.name} ({confidence:.0%})")
    for index, transition in enumerate(transitions):
        global_text, global_confidence = transition_global[index]
        if ocr_failed or global_confidence >= global_trust:
            text, confidence = global_text, global_confidence
        elif not batched and time.perf_counter() >= ocr_deadline:
            ocr_truncated = True
            text, confidence = global_text, global_confidence
        else:
            local = None
            for probe_key in (("t", index), ("tp", index), ("tn", index)):
                candidate = batched.get(probe_key)
                if candidate is None or _state_ocr_owner(candidate, boxes) is not None:
                    continue  # missing, or the crop drifted into a state box
                if local is None or candidate.confidence > local.confidence:
                    local = candidate
            text, confidence = _resolve_label(global_text, global_confidence, local)
        if not text:
            transition.confidence = min(transition.confidence, 0.58)
            unread_labels.append(transition.event)
            continue
        if confidence >= OCR_AUTO_LABEL_CONFIDENCE:
            transition.event = text
            transition.confidence = _label_confidence(transition.confidence, confidence)
        else:
            transition.confidence = min(transition.confidence, round(confidence, 2))
            low_ocr_labels.append(f"{transition.event} ({confidence:.0%})")

    timings["local_ocr"] = round((time.perf_counter() - local_ocr_started) * 1000, 1)

    if ocr_truncated and (states or transitions):
        warnings.append("処理時間の都合で一部の名前は仮名のままです。Reviewで確認してください。")
    if ocr_failed and (states or transitions):
        warnings.append("OCRを利用できなかったため、名前は仮名です。Reviewで修正してください。")
    elif low_ocr_labels:
        warnings.append(f"OCRの確信度が低いため、{', '.join(low_ocr_labels)} は自動命名しませんでした。Reviewで修正してください。")
    if not ocr_failed and unread_labels:
        warnings.append(f"文字を読み取れなかった {', '.join(unread_labels)} は仮名です。Reviewで修正してください。")
    if not states:
        warnings.append("状態の形を検出できませんでした。白紙に黒い線で、円・楕円・長方形をはっきり描いてください。")
    if states and not transitions:
        warnings.append("矢印の接続を確認できませんでした。Review画面で遷移を追加してください。")
    if processed.corrections:
        correction_names = {"perspective": "遠近歪み", "deskew": "傾き"}
        warnings.append(f"{ '・'.join(correction_names[item] for item in processed.corrections) }を補正して認識しました。オーバーレイで位置を確認してください。")
    if processed.quality < 0.58 and (states or transitions):
        warnings.append("画像のコントラストまたは鮮明度が低いため、自動確定を抑制しました。Reviewで確認してください。")
    unconfirmed_directions = sum(not item.direction_confirmed for item in transitions)
    if unconfirmed_directions:
        warnings.append(f"方向の確信度が低い遷移が{unconfirmed_directions}件あります。Reviewでsource / targetを確認してください。")
    if any(item.confidence < 0.7 for item in [*states, *transitions]):
        warnings.append("読み取りを確認してください。薄い線や矢印方向は誤認識することがあります。")
    timings["total"] = round((time.perf_counter() - started) * 1000, 1)
    if _debug is not None:
        _debug["timings"] = timings
    return RecognitionResult(states=states, transitions=transitions, warnings=warnings, processing_ms=round((time.perf_counter() - started) * 1000, 2))
