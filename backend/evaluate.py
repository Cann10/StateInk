"""Print deterministic fixture metrics for the documented recognition scope."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.recognizer import recognize_image
from tests.fixtures.generate_fixtures import generate_fixtures


def evaluate(root: Path) -> None:
    totals = {key: 0 for key in ("states", "transitions", "connections", "directions", "state_labels", "event_labels")}
    expected_totals = totals.copy()
    confirmed_directions = 0
    correct_confirmed_directions = 0
    review_directions = 0
    category_totals: dict[str, dict[str, int]] = {}
    times = []
    for image_path in sorted(root.glob("*.png")):
        expected = json.loads(image_path.with_suffix(".expected.json").read_text(encoding="utf-8"))
        result = recognize_image(image_path.read_bytes())
        times.append(result.processing_ms)
        expected_edges = {tuple(edge) for edge in expected["connections"]}
        actual_edges = {(edge.from_state, edge.to) for edge in result.transitions}
        confirmed_edges = {(edge.from_state, edge.to) for edge in result.transitions if edge.direction_confirmed}
        review_directions += sum(not edge.direction_confirmed for edge in result.transitions)
        category = expected.get("category", "synthetic")
        category_totals.setdefault(category, {"images": 0, "states": 0, "expected_states": 0, "connections": 0, "expected_connections": 0})
        category_totals[category]["images"] += 1
        category_totals[category]["states"] += min(len(result.states), expected["states"])
        category_totals[category]["expected_states"] += expected["states"]
        category_totals[category]["connections"] += len({frozenset(edge) for edge in expected_edges} & {frozenset(edge) for edge in actual_edges})
        category_totals[category]["expected_connections"] += len(expected_edges)
        totals["states"] += min(len(result.states), expected["states"]); expected_totals["states"] += expected["states"]
        totals["transitions"] += min(len(result.transitions), expected["transitions"]); expected_totals["transitions"] += expected["transitions"]
        totals["connections"] += len({frozenset(edge) for edge in expected_edges} & {frozenset(edge) for edge in actual_edges}); expected_totals["connections"] += len(expected_edges)
        totals["directions"] += len(expected_edges & actual_edges); expected_totals["directions"] += len(expected_edges)
        totals["state_labels"] += sum(state.name in expected["state_labels"] for state in result.states); expected_totals["state_labels"] += len(expected["state_labels"])
        totals["event_labels"] += sum(edge.event in expected["event_labels"] for edge in result.transitions); expected_totals["event_labels"] += len(expected["event_labels"])
        confirmed_directions += len(confirmed_edges)
        correct_confirmed_directions += len(expected_edges & confirmed_edges)
        print(f"{image_path.stem}: states={len(result.states)}/{expected['states']} transitions={len(result.transitions)}/{expected['transitions']} {result.processing_ms:.2f}ms")
    for key, value in totals.items():
        expected = expected_totals[key]
        print(f"{key}: {value}/{expected} ({value / expected * 100:.1f}%)")
    precision = correct_confirmed_directions / confirmed_directions * 100 if confirmed_directions else 0
    print(f"confirmed direction precision: {correct_confirmed_directions}/{confirmed_directions} ({precision:.1f}%)")
    direction_candidates = confirmed_directions + review_directions
    review_rate = review_directions / direction_candidates * 100 if direction_candidates else 0
    print(f"direction review rate: {review_directions}/{direction_candidates} ({review_rate:.1f}%)")
    for category, values in sorted(category_totals.items()):
        print(
            f"category {category}: images={values['images']} "
            f"states={values['states']}/{values['expected_states']} "
            f"connections={values['connections']}/{values['expected_connections']}"
        )
    print(f"processing: avg={sum(times)/len(times):.2f}ms max={max(times):.2f}ms")


if __name__ == "__main__":
    with TemporaryDirectory(prefix="stateink-evaluation-") as temporary_directory:
        fixture_root = Path(temporary_directory)
        generate_fixtures(fixture_root)
        evaluate(fixture_root)
