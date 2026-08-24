"""Print deterministic fixture metrics for the documented recognition scope."""
import json
from pathlib import Path

from app.recognizer import recognize_image

root = Path(__file__).parent / "tests" / "fixtures"
totals = {key: 0 for key in ("states", "transitions", "connections", "directions", "state_labels", "event_labels")}
expected_totals = totals.copy()
times = []
for image_path in sorted(root.glob("*.png")):
    expected = json.loads(image_path.with_suffix(".expected.json").read_text(encoding="utf-8"))
    result = recognize_image(image_path.read_bytes()); times.append(result.processing_ms)
    expected_edges = {tuple(edge) for edge in expected["connections"]}
    actual_edges = {(edge.from_state, edge.to) for edge in result.transitions}
    totals["states"] += min(len(result.states), expected["states"]); expected_totals["states"] += expected["states"]
    totals["transitions"] += min(len(result.transitions), expected["transitions"]); expected_totals["transitions"] += expected["transitions"]
    totals["connections"] += len({frozenset(edge) for edge in expected_edges} & {frozenset(edge) for edge in actual_edges}); expected_totals["connections"] += len(expected_edges)
    totals["directions"] += len(expected_edges & actual_edges); expected_totals["directions"] += len(expected_edges)
    totals["state_labels"] += sum(state.name in expected["state_labels"] for state in result.states); expected_totals["state_labels"] += len(expected["state_labels"])
    totals["event_labels"] += sum(edge.event in expected["event_labels"] for edge in result.transitions); expected_totals["event_labels"] += len(expected["event_labels"])
    print(f"{image_path.stem}: states={len(result.states)}/{expected['states']} transitions={len(result.transitions)}/{expected['transitions']} {result.processing_ms:.2f}ms")
for key, value in totals.items(): print(f"{key}: {value}/{expected_totals[key]} ({value / expected_totals[key] * 100:.1f}%)")
print(f"processing: avg={sum(times)/len(times):.2f}ms max={max(times):.2f}ms")
