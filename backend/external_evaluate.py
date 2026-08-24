"""Evaluate StateInk on a temporary local copy of the FA Database.

Raw InkML and rendered PNG files remain outside Git. The script writes only an
aggregate JSON report when --output is provided.
"""
from __future__ import annotations

import argparse
import json
import inspect
import math
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from app.recognizer import recognize_image


def annotations(element: ET.Element) -> dict[str, str]:
    return {item.get("type", ""): (item.text or "").strip() for item in element.findall("annotation")}


def trace_points(element: ET.Element) -> list[tuple[float, float]]:
    points = []
    for raw in (element.text or "").replace("\n", " ").split(","):
        values = raw.strip().split()
        if len(values) >= 2:
            points.append((float(values[0]), float(values[1])))
    return points


def parse_inkml(path: Path) -> dict:
    root = ET.parse(path).getroot()
    traces = {item.get("id", ""): trace_points(item) for item in root.findall("trace")}
    symbols = {}
    for group in root.findall("./symbols/traceGroup"):
        refs = [view.get("traceDataRef", "") for view in group.findall("traceView")]
        shaft = group.find("shaft")
        shaft_refs = [view.get("traceDataRef", "") for view in shaft.findall("traceView")] if shaft is not None else []
        symbols[group.get("id", "")] = {"truth": annotations(group).get("truth", ""), "refs": refs, "shaft_refs": shaft_refs}
    state_ids = [key for key, value in symbols.items() if value["truth"] in {"state", "final state"}]
    relations = []
    initial_arrows = set()
    for group in root.findall("./relations/symbolGroup"):
        truth = annotations(group).get("truth")
        refs = [view.get("symbolDataRef", "") for view in group.findall("symbolView")]
        if truth == "arrow_connection" and len(refs) == 3:
            relations.append((refs[0], refs[1], refs[2]))
        elif truth == "arrow_in" and refs:
            initial_arrows.add(refs[0])
    all_points = [point for points in traces.values() for point in points]
    minimum = np.min(np.asarray(all_points), axis=0); maximum = np.max(np.asarray(all_points), axis=0)
    scale = min(740 / max(maximum[0] - minimum[0], 1), 440 / max(maximum[1] - minimum[1], 1))
    def transform(point): return (int((point[0] - minimum[0]) * scale + 30), int((point[1] - minimum[1]) * scale + 30))
    image = np.full((500, 800, 3), 255, np.uint8)
    for points in traces.values():
        converted = np.asarray([transform(point) for point in points], np.int32)
        if len(converted) > 1: cv2.polylines(image, [converted], False, (0, 0, 0), 2, cv2.LINE_AA)
    state_centers = {}
    for state_id in state_ids:
        points = [transform(point) for ref in symbols[state_id]["refs"] for point in traces.get(ref, [])]
        state_centers[state_id] = tuple(np.mean(np.asarray(points), axis=0))
    unsupported_relation_ids = set()
    for arrow, source, target in relations:
        shaft_traces = [traces.get(ref, []) for ref in symbols.get(arrow, {}).get("shaft_refs", [])]
        curved = any(len(points) > 2 and sum(math.dist(a, b) for a, b in zip(points, points[1:])) / max(math.dist(points[0], points[-1]), 1) > 1.35 for points in shaft_traces)
        if source == target or curved: unsupported_relation_ids.add(arrow)
    supported_relations = [item for item in relations if item[0] not in unsupported_relation_ids]
    # Dense layouts and diagrams with many straight-line crossings are reported overall only.
    segments = [(state_centers[source], state_centers[target], source, target) for _, source, target in supported_relations]
    def crosses(a, b, c, d):
        def orientation(p, q, r): return np.sign((q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]))
        return orientation(a,b,c) != orientation(a,b,d) and orientation(c,d,a) != orientation(c,d,b)
    crossing_count = sum(not {s1,t1} & {s2,t2} and crosses(a,b,c,d) for index,(a,b,s1,t1) in enumerate(segments) for c,d,s2,t2 in segments[index+1:])
    unsupported = bool(len(state_ids) > 6 or crossing_count > 3)
    return {"image": image, "states": state_centers, "relations": relations, "supported_relations": supported_relations, "unsupported": unsupported, "unsupported_relations": len(unsupported_relation_ids), "initial_arrows": initial_arrows}


def evaluate_file(path: Path, debug_dir: Path | None = None) -> dict:
    truth = parse_inkml(path)
    ok, encoded = cv2.imencode(".png", truth["image"]); assert ok
    debug = {}; result = recognize_image(encoded.tobytes(), _debug=debug) if "_debug" in inspect.signature(recognize_image).parameters else recognize_image(encoded.tobytes())
    predicted_centers = {state.id: (state.geometry.x + state.geometry.width / 2, state.geometry.y + state.geometry.height / 2) for state in result.states}
    mapping = {}
    available = set(truth["states"])
    for predicted_id, center in predicted_centers.items():
        if not available: break
        nearest = min(available, key=lambda key: math.dist(center, truth["states"][key]))
        if math.dist(center, truth["states"][nearest]) < 90:
            mapping[predicted_id] = nearest; available.remove(nearest)
    predicted = {(mapping.get(edge.from_state, "?"), mapping.get(edge.to, "?")) for edge in result.transitions}
    predicted_undirected = {frozenset(edge) for edge in predicted}
    def score(relations):
        expected = {(source, target) for _, source, target in relations}; expected_undirected = {frozenset(edge) for edge in expected}
        return {"expected_transitions": len(relations), "transition_tp": min(len(result.transitions), len(relations)), "expected_connections": len(expected_undirected), "connection_tp": len(expected_undirected & predicted_undirected), "expected_directions": len(expected), "direction_tp": len(expected & predicted)}, expected, expected_undirected
    overall, _, _ = score(truth["relations"])
    supported, expected, expected_undirected = score(truth["supported_relations"])
    failures = Counter()
    if len(mapping) < len(truth["states"]): failures["state contour"] += len(truth["states"]) - len(mapping)
    missing_connections = expected_undirected - predicted_undirected
    if missing_connections: failures["line detection"] += len(missing_connections)
    wrong_connections = predicted_undirected - expected_undirected
    if wrong_connections: failures["source/target association"] += len(wrong_connections)
    connected_pairs = expected_undirected & predicted_undirected
    failures["arrowhead"] += sum(frozenset(edge) in connected_pairs and edge not in predicted for edge in expected)
    if truth["unsupported_relations"]: failures["unsupported geometry"] += truth["unsupported_relations"]
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True); overlay = truth["image"].copy()
        for center in truth["states"].values(): cv2.circle(overlay, tuple(map(int, center)), 8, (0, 180, 0), 2)
        for _, source, target in truth["relations"]: cv2.arrowedLine(overlay, tuple(map(int, truth["states"][source])), tuple(map(int, truth["states"][target])), (180, 0, 180), 2, tipLength=.08)
        for x,y,width,height in debug["boxes"]: cv2.rectangle(overlay, (x,y), (x+width,y+height), (255,80,0), 2)
        for item in debug["transitions"]:
            p1,p2 = map(tuple,item["shaft"]); cv2.line(overlay,p1,p2,(0,180,255),3)
            if item["arrowhead"]: cv2.circle(overlay,tuple(item["arrowhead"]),7,(0,0,255),-1)
            source_box,target_box=debug["boxes"][item["source"]],debug["boxes"][item["target"]]
            center=lambda box:(int(box[0]+box[2]/2),int(box[1]+box[3]/2))
            cv2.arrowedLine(overlay,center(source_box),center(target_box),(255,0,0),2,tipLength=.1)
        cv2.imwrite(str(debug_dir / f"{path.stem}.png"), overlay)
    return {"name": path.stem, "unsupported": truth["unsupported"], "unsupported_transitions": truth["unsupported_relations"], "expected_states": len(truth["states"]), "state_tp": len(mapping), "overall": overall, "supported": supported, "failures": dict(failures), "processing_ms": result.processing_ms}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("dataset", type=Path); parser.add_argument("--limit", type=int, default=24); parser.add_argument("--output", type=Path); parser.add_argument("--debug-dir", type=Path)
    args = parser.parse_args(); files = sorted(args.dataset.glob("*.inkml"))[:args.limit]
    results = [evaluate_file(path, args.debug_dir) for path in files]; subset = [item for item in results if not item["unsupported"]]
    metric_keys = ("expected_transitions", "transition_tp", "expected_connections", "connection_tp", "expected_directions", "direction_tp")
    def aggregate(items, scope):
        totals = {"expected_states": sum(item["expected_states"] for item in items), "state_tp": sum(item["state_tp"] for item in items)}
        totals.update({key: sum(item[scope][key] for item in items) for key in metric_keys}); return totals
    overall_totals = aggregate(results, "overall"); supported_totals = aggregate(subset, "supported")
    failures = sum((Counter(item["failures"]) for item in subset), Counter())
    failure_categories = ("state contour", "line detection", "arrowhead", "source/target association", "direction", "unsupported geometry", "OCR")
    failures = {category: failures.get(category, 0) for category in failure_categories}
    report = {"source": "FA Database 1.1", "sample_count": len(results), "supported_count": len(subset), "unsupported_count": len(results) - len(subset), "overall_metrics": overall_totals, "supported_metrics": supported_totals, "failures": dict(failures), "per_image": results}
    for item in results:
        metric=item["supported"]
        print(f"{item['name']}: {'unsupported' if item['unsupported'] else 'supported'} state={item['state_tp']}/{item['expected_states']} transition={metric['transition_tp']}/{metric['expected_transitions']} connection={metric['connection_tp']}/{metric['expected_connections']} direction={metric['direction_tp']}/{metric['expected_directions']} failures={item['failures']}")
    print(json.dumps({key: value for key, value in report.items() if key != "per_image"}, ensure_ascii=False, indent=2))
    if args.output: args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__": main()
