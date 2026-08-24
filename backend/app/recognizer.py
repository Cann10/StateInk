from __future__ import annotations

import math
import shutil
import time

import cv2
import numpy as np
import pytesseract

from .models import Geometry, RecognitionResult, RecognizedState, RecognizedTransition


def _inside(point: tuple[int, int], box: tuple[int, int, int, int], margin: int = 8) -> bool:
    x, y = point
    bx, by, width, height = box
    return bx + margin < x < bx + width - margin and by + margin < y < by + height - margin


def _distance(point: tuple[int, int], box: tuple[int, int, int, int]) -> float:
    bx, by, width, height = box
    return math.hypot(point[0] - (bx + width / 2), point[1] - (by + height / 2))


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
        looks_like_state = len(polygon) >= 4 and 0.48 < fill_ratio < 0.995 and width < binary.shape[1] * 0.4
        if looks_like_state and not any(abs(x - bx) < 8 and abs(y - by) < 8 for bx, by, _, _ in candidates):
            candidates.append((x, y, width, height))
    return sorted(candidates, key=lambda box: (box[0], box[1]))


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


def _head_score(endpoint: tuple[int,int], other: tuple[int,int], lines: np.ndarray) -> tuple[int,list[tuple[int,int]]]:
    shaft=np.asarray(other,dtype=float)-endpoint; shaft/=max(float(np.linalg.norm(shaft)),1); sides=set(); wings=[]
    for line in lines:
        a,b=np.asarray(line[:2],dtype=float),np.asarray(line[2:],dtype=float); near,far=(a,b) if np.linalg.norm(a-endpoint)<np.linalg.norm(b-endpoint) else (b,a)
        length=float(np.linalg.norm(far-near))
        if np.linalg.norm(near-endpoint)>24 or not 8<length<65: continue
        wing=(far-near)/length; angle=math.degrees(math.acos(min(1,abs(float(np.dot(shaft,wing))))))
        if 20<angle<70:
            cross=shaft[0]*wing[1]-shaft[1]*wing[0]; sides.add(1 if cross>=0 else -1); wings.append((int(far[0]),int(far[1])))
    return len(sides),wings


def _detect_transitions(binary: np.ndarray, boxes: list[tuple[int, int, int, int]], debug: list[dict] | None = None) -> list[tuple[int, int, tuple[int, int], tuple[int, int], float]]:
    lines = cv2.HoughLinesP(binary, 1, np.pi / 180, threshold=28, minLineLength=35, maxLineGap=18)
    detected: dict[tuple[int, int], tuple[int, int, tuple[int, int], tuple[int, int], float]] = {}
    if lines is None:
        return []
    raw_lines = lines.reshape(-1, 4)
    raw_lines = np.asarray(sorted(raw_lines, key=lambda line: -math.hypot(line[2]-line[0], line[3]-line[1]))[:400])
    head_lines = cv2.HoughLinesP(binary,1,np.pi/180,threshold=10,minLineLength=8,maxLineGap=5)
    head_lines = head_lines.reshape(-1,4) if head_lines is not None else raw_lines
    head_lines = np.asarray(sorted(head_lines, key=lambda line: math.hypot(line[2]-line[0], line[3]-line[1]))[:400])
    candidates = _merge_collinear_segments(raw_lines) + [((int(line[0]),int(line[1])),(int(line[2]),int(line[3]))) for line in raw_lines]
    for p1,p2 in candidates:
        if any(_inside(p1, box) or _inside(p2, box) for box in boxes):
            continue
        first = min(range(len(boxes)), key=lambda index: _distance(p1, boxes[index]))
        second = min(range(len(boxes)), key=lambda index: _distance(p2, boxes[index]))
        if first == second:
            midpoint = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
            if _inside(midpoint, boxes[first], margin=-12): continue
            aligned = _states_along_line(p1, p2, boxes)
            if aligned is None: continue
            first, second = aligned
        score1,wings1=_head_score(p1,p2,head_lines); score2,wings2=_head_score(p2,p1,head_lines)
        if score1==2 and score1>score2:
            source,target,confidence,head=second,first,.68,p1
        elif score2==2 and score2>score1:
            source,target,confidence,head=first,second,.68,p2
        else:
            source,target,confidence,head=first,second,.42,None
        length = math.dist(p1, p2)
        key = tuple(sorted((source, target)))
        if key not in detected or length > math.dist(detected[key][2], detected[key][3]):
            detected[key] = (source, target, p1, p2, confidence)
            if debug is not None: debug.append({"shaft":[p1,p2],"source":source,"target":target,"arrowhead":head,"wings":wings1 if head==p1 else wings2 if head==p2 else []})
    return list(detected.values())


def recognize_image(data: bytes, *, _debug: dict | None = None) -> RecognitionResult:
    started = time.perf_counter()
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("画像を読み取れませんでした")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9)
    boxes = _detect_states(binary)
    states = [RecognizedState(id=f"state-{index + 1}", name=f"State {index + 1}", geometry=Geometry(x=x, y=y, width=width, height=height), confidence=0.78 if len(boxes) > 0 else 0.3, initial=index == 0) for index, (x, y, width, height) in enumerate(boxes)]
    transitions: list[RecognizedTransition] = []
    transition_debug=[]
    for index, (source, target, p1, p2, confidence) in enumerate(_detect_transitions(binary, boxes, transition_debug)):
        transitions.append(RecognizedTransition(id=f"transition-{index + 1}", **{"from": states[source].id}, to=states[target].id, event=f"event_{index + 1}", geometry=Geometry(x=min(p1[0], p2[0]), y=min(p1[1], p2[1]), width=abs(p1[0] - p2[0]), height=abs(p1[1] - p2[1])), confidence=confidence))
    if _debug is not None: _debug.update({"boxes":boxes,"transitions":transition_debug})
    if shutil.which("tesseract"):
        words = pytesseract.image_to_data(gray, config="--psm 11", output_type=pytesseract.Output.DICT)
        for index, text in enumerate(words["text"]):
            text = text.strip()
            confidence = float(words["conf"][index]) / 100
            if not text or confidence < 0.25:
                continue
            center = (int(words["left"][index] + words["width"][index] / 2), int(words["top"][index] + words["height"][index] / 2))
            owner = next((state_index for state_index, box in enumerate(boxes) if _inside(center, box, margin=0)), None)
            if owner is not None:
                states[owner].name = text
                states[owner].confidence = round((states[owner].confidence + confidence) / 2, 2)
                continue
            if transitions:
                nearest = min(transitions, key=lambda edge: math.hypot(center[0] - (edge.geometry.x + edge.geometry.width / 2), center[1] - (edge.geometry.y + edge.geometry.height / 2)))
                distance = math.hypot(center[0] - (nearest.geometry.x + nearest.geometry.width / 2), center[1] - (nearest.geometry.y + nearest.geometry.height / 2))
                if distance < 70:
                    nearest.event = text
                    nearest.confidence = round((nearest.confidence + confidence) / 2, 2)
    warnings = []
    if not states:
        warnings.append("状態の形を検出できませんでした。白紙に黒い線で、円・楕円・長方形をはっきり描いてください。")
    if states and not transitions:
        warnings.append("矢印の接続を確認できませんでした。Review画面で遷移を追加してください。")
    if any(item.confidence < 0.7 for item in [*states, *transitions]):
        warnings.append("読み取りを確認してください。薄い線や矢印方向は誤認識することがあります。")
    return RecognitionResult(states=states, transitions=transitions, warnings=warnings, processing_ms=round((time.perf_counter() - started) * 1000, 2))
