from __future__ import annotations

import math
import re
import shutil
import time
from collections import defaultdict

import cv2
import numpy as np
import pytesseract

from .models import Geometry, RecognitionResult, RecognizedState, RecognizedTransition

_JAPANESE_CHAR = r"\u3040-\u30ff\u3400-\u9fff"


def _inside(point: tuple[int, int], box: tuple[int, int, int, int], margin: int = 8) -> bool:
    x, y = point
    bx, by, width, height = box
    return bx + margin < x < bx + width - margin and by + margin < y < by + height - margin


def _distance(point: tuple[int, int], box: tuple[int, int, int, int]) -> float:
    bx, by, width, height = box
    return math.hypot(point[0] - (bx + width / 2), point[1] - (by + height / 2))


def _states_along_line(
    p1: tuple[int, int],
    p2: tuple[int, int],
    boxes: list[tuple[int, int, int, int]],
) -> tuple[int, int] | None:
    vector = np.asarray(p2, dtype=float) - np.asarray(p1, dtype=float)
    length = float(np.linalg.norm(vector))
    if length == 0:
        return None
    unit = vector / length
    candidates: list[tuple[float, int]] = []
    for index, (x, y, width, height) in enumerate(boxes):
        offset = np.asarray((x + width / 2, y + height / 2)) - np.asarray(p1)
        projection = float(np.dot(offset, unit))
        perpendicular = float(abs(unit[0] * offset[1] - unit[1] * offset[0]))
        if perpendicular < max(width, height) / 2 + 28:
            candidates.append((projection, index))
    before = [item for item in candidates if item[0] <= length / 2]
    after = [item for item in candidates if item[0] > length / 2]
    if not before or not after:
        return None
    return (
        min(before, key=lambda item: abs(item[0]))[1],
        min(after, key=lambda item: abs(item[0] - length))[1],
    )


def _detect_states(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[int, int, int, int]] = []
    image_area = binary.shape[0] * binary.shape[1]
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, width, height = cv2.boundingRect(contour)
        if not 1_200 < area < image_area * 0.35 or width < 48 or height < 38:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        fill_ratio = area / (width * height)
        looks_like_state = (
            len(polygon) >= 4
            and 0.48 < fill_ratio < 0.995
            and width < binary.shape[1] * 0.4
        )
        if looks_like_state and not any(
            abs(x - bx) < 8 and abs(y - by) < 8 for bx, by, _, _ in candidates
        ):
            candidates.append((x, y, width, height))
    return sorted(candidates, key=lambda box: (box[0], box[1]))


def _line_angle(line: np.ndarray) -> float:
    return math.atan2(float(line[3] - line[1]), float(line[2] - line[0])) % math.pi


def _merge_collinear_segments(lines: np.ndarray) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    groups: list[list[np.ndarray]] = []
    for line in sorted(lines, key=lambda item: -math.hypot(item[2] - item[0], item[3] - item[1])):
        angle = _line_angle(line)
        midpoint = np.asarray(((line[0] + line[2]) / 2, (line[1] + line[3]) / 2))
        match = None
        for group in groups:
            reference = group[0]
            delta = abs(angle - _line_angle(reference))
            delta = min(delta, math.pi - delta)
            unit = np.asarray((math.cos(_line_angle(reference)), math.sin(_line_angle(reference))))
            normal = np.asarray((-unit[1], unit[0]))
            reference_mid = np.asarray(
                ((reference[0] + reference[2]) / 2, (reference[1] + reference[3]) / 2)
            )
            gap = min(
                math.dist(point, other)
                for point in ((line[0], line[1]), (line[2], line[3]))
                for item in group
                for other in ((item[0], item[1]), (item[2], item[3]))
            )
            if (
                delta < math.radians(10)
                and abs(float(np.dot(midpoint - reference_mid, normal))) < 12
                and gap < 45
            ):
                match = group
                break
        if match is None:
            groups.append([line])
        else:
            match.append(line)

    merged: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for group in groups:
        angle = _line_angle(group[0])
        unit = np.asarray((math.cos(angle), math.sin(angle)))
        points = np.asarray(
            [(item[0], item[1]) for item in group]
            + [(item[2], item[3]) for item in group]
        )
        projections = points @ unit
        a = points[int(np.argmin(projections))]
        b = points[int(np.argmax(projections))]
        merged.append(((int(a[0]), int(a[1])), (int(b[0]), int(b[1]))))
    return merged


def _head_score(
    endpoint: tuple[int, int],
    other: tuple[int, int],
    lines: np.ndarray,
) -> tuple[int, list[tuple[int, int]]]:
    shaft = np.asarray(other, dtype=float) - endpoint
    shaft /= max(float(np.linalg.norm(shaft)), 1)
    sides: set[int] = set()
    wings: list[tuple[int, int]] = []
    for line in lines:
        a, b = np.asarray(line[:2], dtype=float), np.asarray(line[2:], dtype=float)
        near, far = (a, b) if np.linalg.norm(a - endpoint) < np.linalg.norm(b - endpoint) else (b, a)
        length = float(np.linalg.norm(far - near))
        if np.linalg.norm(near - endpoint) > 24 or not 8 < length < 65:
            continue
        wing = (far - near) / length
        angle = math.degrees(math.acos(min(1, abs(float(np.dot(shaft, wing))))))
        if 20 < angle < 70:
            cross = shaft[0] * wing[1] - shaft[1] * wing[0]
            sides.add(1 if cross >= 0 else -1)
            wings.append((int(far[0]), int(far[1])))
    return len(sides), wings


def _detect_transitions(
    binary: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    debug: list[dict] | None = None,
) -> list[tuple[int, int, tuple[int, int], tuple[int, int], float]]:
    lines = cv2.HoughLinesP(
        binary, 1, np.pi / 180, threshold=28, minLineLength=35, maxLineGap=18
    )
    detected: dict[
        tuple[int, int], tuple[int, int, tuple[int, int], tuple[int, int], float]
    ] = {}
    if lines is None:
        return []

    raw_lines = lines.reshape(-1, 4)
    raw_lines = np.asarray(
        sorted(
            raw_lines,
            key=lambda line: -math.hypot(line[2] - line[0], line[3] - line[1]),
        )[:400]
    )
    head_lines = cv2.HoughLinesP(
        binary, 1, np.pi / 180, threshold=10, minLineLength=8, maxLineGap=5
    )
    head_lines = head_lines.reshape(-1, 4) if head_lines is not None else raw_lines
    head_lines = np.asarray(
        sorted(
            head_lines,
            key=lambda line: math.hypot(line[2] - line[0], line[3] - line[1]),
        )[:400]
    )
    candidates = _merge_collinear_segments(raw_lines) + [
        ((int(line[0]), int(line[1])), (int(line[2]), int(line[3])))
        for line in raw_lines
    ]

    for p1, p2 in candidates:
        if any(_inside(p1, box) or _inside(p2, box) for box in boxes):
            continue
        first = min(range(len(boxes)), key=lambda index: _distance(p1, boxes[index]))
        second = min(range(len(boxes)), key=lambda index: _distance(p2, boxes[index]))
        if first == second:
            midpoint = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
            if _inside(midpoint, boxes[first], margin=-12):
                continue
            aligned = _states_along_line(p1, p2, boxes)
            if aligned is None:
                continue
            first, second = aligned

        score1, wings1 = _head_score(p1, p2, head_lines)
        score2, wings2 = _head_score(p2, p1, head_lines)
        if score1 == 2 and score1 > score2:
            source, target, confidence, head = second, first, 0.68, p1
        elif score2 == 2 and score2 > score1:
            source, target, confidence, head = first, second, 0.68, p2
        else:
            source, target, confidence, head = first, second, 0.42, None

        length = math.dist(p1, p2)
        key = tuple(sorted((source, target)))
        if key not in detected or length > math.dist(detected[key][2], detected[key][3]):
            detected[key] = (source, target, p1, p2, confidence)
            if debug is not None:
                debug.append(
                    {
                        "shaft": [p1, p2],
                        "source": source,
                        "target": target,
                        "arrowhead": head,
                        "wings": wings1 if head == p1 else wings2 if head == p2 else [],
                    }
                )
    return list(detected.values())


def _available_ocr_language() -> str | None:
    """Prefer Japanese + English when both language packs are installed."""
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


def _normalize_ocr_text(text: str) -> str:
    text = " ".join(text.replace("\u3000", " ").split())
    text = re.sub(fr"(?<=[{_JAPANESE_CHAR}])\s+(?=[{_JAPANESE_CHAR}])", "", text)
    text = re.sub(r"\s+([、。,.!?！？:：;；])", r"\1", text)
    return text.strip()


def _group_ocr_lines(
    tokens: list[tuple[int, int, str, float]],
    *,
    tolerance: int = 14,
) -> list[list[tuple[int, int, str, float]]]:
    lines: list[list[tuple[int, int, str, float]]] = []
    for token in sorted(tokens, key=lambda item: (item[1], item[0])):
        for line in lines:
            baseline = sum(item[1] for item in line) / len(line)
            if abs(token[1] - baseline) <= tolerance:
                line.append(token)
                break
        else:
            lines.append([token])
    split_lines: list[list[tuple[int, int, str, float]]] = []
    for line in lines:
        ordered = sorted(line, key=lambda item: item[0])
        current: list[tuple[int, int, str, float]] = []
        previous_x: int | None = None
        for token in ordered:
            if previous_x is not None and token[0] - previous_x > 80 and current:
                split_lines.append(current)
                current = []
            current.append(token)
            previous_x = token[0]
        if current:
            split_lines.append(current)
    return split_lines


def _join_ocr_tokens(tokens: list[tuple[int, int, str, float]]) -> tuple[str, float]:
    """Join OCR tokens in visual reading order and return text + average confidence."""
    if not tokens:
        return "", 0.0
    lines = _group_ocr_lines(tokens)
    line_texts = [
        _normalize_ocr_text(" ".join(item[2] for item in line))
        for line in lines
    ]
    text = _normalize_ocr_text(" ".join(item for item in line_texts if item))
    confidence = sum(item[3] for item in tokens) / len(tokens)
    return text, confidence


def _best_ocr_line(
    tokens: list[tuple[int, int, str, float]],
) -> tuple[str, float]:
    best_text = ""
    best_confidence = 0.0
    best_score = -1.0
    for line in _group_ocr_lines(tokens):
        text, confidence = _join_ocr_tokens(line)
        meaningful = sum(
            char.isalnum() or re.match(fr"[{_JAPANESE_CHAR}]", char) is not None
            for char in text
        )
        score = confidence + min(meaningful, 20) * 0.015
        if text and score > best_score:
            best_text, best_confidence, best_score = text, confidence, score
    return best_text, best_confidence


def _meaningful_ocr_text(text: str) -> bool:
    return bool(re.search(fr"[A-Za-z0-9{_JAPANESE_CHAR}]", text))


def _ocr_tokens_from_crop(
    crop: np.ndarray,
    language: str,
    *,
    psm: int,
) -> list[tuple[int, int, str, float]]:
    try:
        words = pytesseract.image_to_data(
            crop,
            lang=language,
            config=f"--psm {psm}",
            output_type=pytesseract.Output.DICT,
        )
    except (pytesseract.TesseractError, OSError):
        return []

    tokens: list[tuple[int, int, str, float]] = []
    for index, raw_text in enumerate(words.get("text", [])):
        text = _normalize_ocr_text(str(raw_text))
        try:
            confidence = float(words["conf"][index]) / 100
        except (ValueError, TypeError, IndexError, KeyError):
            continue
        if not text or confidence < 0.25 or not _meaningful_ocr_text(text):
            continue
        left = int(words["left"][index])
        top = int(words["top"][index])
        tokens.append((left, top, text, confidence))
    return tokens


def _best_ocr_crop(crop: np.ndarray, language: str) -> tuple[str, float]:
    best_text = ""
    best_confidence = 0.0
    best_score = -1.0
    for psm in (7, 6, 11):
        tokens = _ocr_tokens_from_crop(crop, language, psm=psm)
        text, confidence = _join_ocr_tokens(tokens)
        if not text:
            continue
        meaningful = sum(
            char.isalnum() or re.match(fr"[{_JAPANESE_CHAR}]", char) is not None
            for char in text
        )
        score = confidence + min(meaningful, 16) * 0.01
        if score > best_score:
            best_text, best_confidence, best_score = text, confidence, score
    return best_text, best_confidence


def _apply_state_ocr(
    gray: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    states: list[RecognizedState],
    language: str,
) -> None:
    height, width = gray.shape
    for state_index, (x, y, box_width, box_height) in enumerate(boxes):
        inset = max(8, int(min(box_width, box_height) * 0.18))
        x1, y1 = max(0, x + inset), max(0, y + inset)
        x2, y2 = min(width, x + box_width - inset), min(height, y + box_height - inset)
        if x2 <= x1 or y2 <= y1:
            continue
        text, confidence = _best_ocr_crop(gray[y1:y2, x1:x2], language)
        if text:
            states[state_index].name = text
            states[state_index].confidence = round(
                (states[state_index].confidence + confidence) / 2, 2
            )


def _apply_transition_ocr(
    gray: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    transitions: list[RecognizedTransition],
    shafts: list[tuple[tuple[int, int], tuple[int, int]]],
    language: str,
) -> None:
    image_height, image_width = gray.shape
    for transition_index, transition in enumerate(transitions):
        if transition_index >= len(shafts):
            break
        p1, p2 = shafts[transition_index]
        work = gray.copy()
        for x, y, box_width, box_height in boxes:
            cv2.rectangle(work, (x, y), (x + box_width, y + box_height), 255, -1)
        cv2.line(work, p1, p2, 255, 10)

        x1 = max(0, min(p1[0], p2[0]) - 55)
        x2 = min(image_width, max(p1[0], p2[0]) + 55)
        y1 = max(0, min(p1[1], p2[1]) - 75)
        y2 = min(image_height, max(p1[1], p2[1]) + 55)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = work[y1:y2, x1:x2]
        tokens = _ocr_tokens_from_crop(crop, language, psm=11)
        if not tokens:
            continue

        center_x = crop.shape[1] / 2
        center_y = crop.shape[0] / 2
        nearby = [
            token
            for token in tokens
            if math.hypot(token[0] - center_x, token[1] - center_y) <= 150
        ]
        text, confidence = _best_ocr_line(nearby)
        if text:
            transition.event = text
            transition.confidence = round(
                (transition.confidence + confidence) / 2, 2
            )


def _apply_ocr_labels(
    gray: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    states: list[RecognizedState],
    transitions: list[RecognizedTransition],
    shafts: list[tuple[tuple[int, int], tuple[int, int]]],
) -> None:
    language = _available_ocr_language()
    if language is None:
        return
    _apply_state_ocr(gray, boxes, states, language)
    _apply_transition_ocr(gray, boxes, transitions, shafts, language)


def recognize_image(data: bytes, *, _debug: dict | None = None) -> RecognitionResult:
    started = time.perf_counter()
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("画像を読み取れませんでした")

    ocr_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(ocr_gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        9,
    )
    boxes = _detect_states(binary)
    states = [
        RecognizedState(
            id=f"state-{index + 1}",
            name=f"State {index + 1}",
            geometry=Geometry(x=x, y=y, width=width, height=height),
            confidence=0.78 if boxes else 0.3,
            initial=index == 0,
        )
        for index, (x, y, width, height) in enumerate(boxes)
    ]

    transitions: list[RecognizedTransition] = []
    transition_debug: list[dict] = []
    transition_shafts: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for index, (source, target, p1, p2, confidence) in enumerate(
        _detect_transitions(binary, boxes, transition_debug)
    ):
        transition_shafts.append((p1, p2))
        transitions.append(
            RecognizedTransition(
                id=f"transition-{index + 1}",
                **{"from": states[source].id},
                to=states[target].id,
                event=f"event_{index + 1}",
                geometry=Geometry(
                    x=min(p1[0], p2[0]),
                    y=min(p1[1], p2[1]),
                    width=abs(p1[0] - p2[0]),
                    height=abs(p1[1] - p2[1]),
                ),
                confidence=confidence,
            )
        )

    if _debug is not None:
        _debug.update({"boxes": boxes, "transitions": transition_debug})

    _apply_ocr_labels(ocr_gray, boxes, states, transitions, transition_shafts)

    warnings: list[str] = []
    if not states:
        warnings.append(
            "状態の形を検出できませんでした。白紙に黒い線で、円・楕円・長方形をはっきり描いてください。"
        )
    if states and not transitions:
        warnings.append("矢印の接続を確認できませんでした。Review画面で遷移を追加してください。")
    if any(item.confidence < 0.7 for item in [*states, *transitions]):
        warnings.append("読み取りを確認してください。薄い線や矢印方向は誤認識することがあります。")

    return RecognitionResult(
        states=states,
        transitions=transitions,
        warnings=warnings,
        processing_ms=round((time.perf_counter() - started) * 1000, 2),
    )
