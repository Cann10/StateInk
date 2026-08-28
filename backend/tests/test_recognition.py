import json
from pathlib import Path

import cv2
import pytest
from fastapi.testclient import TestClient

from app.main import app, cors_origins
import numpy as np

import app.recognizer as recognizer
from app.recognizer import (
    _OcrRegion,
    _boundary_distance,
    _detect_transitions,
    _extract_ocr_regions,
    _head_score,
    _infer_connected_states,
    _join_ocr_tokens,
    _merge_collinear_segments,
    _normalize_ocr_text,
    _states_along_line,
    _transition_ocr_owner,
    recognize_image,
)
from tests.fixtures.generate_fixtures import generate_fixtures

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def generated_fixtures(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("recognition-fixtures")
    generate_fixtures(output)
    return output


@pytest.mark.parametrize("expected_path", sorted(FIXTURES.glob("*.expected.json")), ids=lambda path: path.stem.removesuffix(".expected"))
def test_fixture_structure(expected_path: Path, generated_fixtures: Path) -> None:
    image_path = generated_fixtures / f"{expected_path.stem.removesuffix('.expected')}.png"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    result = recognize_image(image_path.read_bytes())
    assert len(result.states) == expected["states"]
    assert len(result.transitions) == expected["transitions"]
    assert all(edge.from_state != edge.to for edge in result.transitions)
    assert result.processing_ms < 3_000


def test_api_returns_reviewable_result(generated_fixtures: Path) -> None:
    image = generated_fixtures / "simple_two_state.png"
    response = TestClient(app).post("/api/recognize", files={"file": (image.name, image.read_bytes(), "image/png")})
    assert response.status_code == 200
    body = response.json()
    assert body["states"][0]["name"] in {"State 1", "IDLE"}
    assert body["transitions"][0]["from"] == "state-1"
    assert isinstance(body["warnings"], list)


def test_api_rejects_non_image() -> None:
    response = TestClient(app).post("/api/recognize", files={"file": ("notes.txt", b"not an image", "text/plain")})
    assert response.status_code == 415


def test_cors_origins_are_trimmed_for_deployment() -> None:
    assert cors_origins(" https://stateink.example/ ,https://api.example ,, ") == [
        "https://stateink.example",
        "https://api.example",
    ]


def test_local_frontend_origin_is_allowed_by_default() -> None:
    response = TestClient(app).options(
        "/api/recognize",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_fragmented_line_associates_nearest_states_on_each_side() -> None:
    boxes = [(0, 40, 80, 60), (200, 40, 80, 60), (400, 40, 80, 60)]
    assert _states_along_line((95, 70), (175, 70), boxes) == (0, 1)


def test_collinear_shaft_fragments_are_merged() -> None:
    merged = _merge_collinear_segments(np.asarray([[10, 50, 60, 50], [68, 51, 120, 51]]))
    assert len(merged) == 1
    assert merged[0][0][0] <= 10 and merged[0][1][0] >= 120


def test_v_shaped_wings_identify_arrowhead_endpoint() -> None:
    lines = np.asarray([[100, 50, 82, 38], [100, 50, 82, 62], [10, 50, 100, 50]])
    score, _ = _head_score((100, 50), (10, 50), lines)
    assert score == 2


def test_connection_ranking_uses_outline_distance_and_line_angle() -> None:
    boxes = [(0, 20, 100, 60), (300, 20, 100, 60), (170, 170, 100, 60)]
    connection = _infer_connected_states((102, 50), (298, 50), boxes)
    assert connection is not None
    assert connection[:2] == (0, 1)
    assert connection[2] >= 0.75
    assert _boundary_distance((102, 50), boxes[0]) == 2


def test_arrowhead_and_attachment_confirm_direction(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = iter([
        np.asarray([[[100, 50, 300, 50]]], dtype=np.int32),
        np.asarray([[[300, 50, 282, 38]], [[300, 50, 282, 62]], [[100, 50, 300, 50]]], dtype=np.int32),
    ])
    monkeypatch.setattr(recognizer.cv2, "HoughLinesP", lambda *_args, **_kwargs: next(calls))
    detected = _detect_transitions(np.zeros((140, 420), np.uint8), [(0, 20, 100, 60), (300, 20, 100, 60)])
    assert detected
    source, target, _p1, _p2, confidence, direction_confirmed = detected[0]
    assert (source, target) == (0, 1)
    assert confidence >= 0.68
    assert direction_confirmed is True


def test_ambiguous_line_keeps_direction_unconfirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    shaft = np.asarray([[[100, 50, 300, 50]]], dtype=np.int32)
    monkeypatch.setattr(recognizer.cv2, "HoughLinesP", lambda *_args, **_kwargs: shaft)
    detected = _detect_transitions(np.zeros((140, 420), np.uint8), [(0, 20, 100, 60), (300, 20, 100, 60)])
    assert detected[0][4] < 0.68
    assert detected[0][5] is False


def test_single_arrowhead_wing_is_only_a_review_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = iter([
        np.asarray([[[100, 50, 300, 50]]], dtype=np.int32),
        np.asarray([[[300, 50, 282, 38]], [[100, 50, 300, 50]]], dtype=np.int32),
    ])
    monkeypatch.setattr(recognizer.cv2, "HoughLinesP", lambda *_args, **_kwargs: next(calls))
    detected = _detect_transitions(np.zeros((140, 420), np.uint8), [(0, 20, 100, 60), (300, 20, 100, 60)])
    assert detected[0][5] is False


def test_ocr_uses_japanese_and_english_and_preserves_phrases(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_image_to_data(_image: np.ndarray, **kwargs: object) -> dict[str, list[object]]:
        captured["lang"] = str(kwargs["lang"])
        captured["config"] = str(kwargs["config"])
        return {
            "text": ["商品", "選択", "payment", "confirmed", "待機", "idle"],
            "conf": ["92", "90", "88", "86", "91", "89"],
            "left": [10, 48, 10, 82, 10, 52],
            "top": [10, 10, 40, 40, 70, 70],
            "width": [34, 34, 66, 78, 36, 38],
            "height": [20, 20, 20, 20, 20, 20],
            "page_num": [1, 1, 1, 1, 1, 1],
            "block_num": [1, 1, 2, 2, 3, 3],
            "par_num": [1, 1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 1, 1, 1],
            "word_num": [1, 2, 1, 2, 1, 2],
        }

    monkeypatch.setattr(recognizer.pytesseract, "image_to_data", fake_image_to_data)
    regions = _extract_ocr_regions(np.full((120, 220), 255, np.uint8))

    assert captured == {"lang": "jpn+eng", "config": "--oem 1 --psm 11"}
    assert [region.text for region in regions] == ["商品選択", "payment confirmed", "待機 idle"]


def test_ocr_whitespace_is_normalized_without_losing_words() -> None:
    assert _normalize_ocr_text("  入金済み\n\t payment   confirmed  ") == "入金済み payment confirmed"
    assert _join_ocr_tokens(["商品", "選択", "select", "item"]) == "商品選択 select item"
    assert _normalize_ocr_text("Ｓｔａｒｔ　待 機\u200b中") == "Start 待機中"


def test_transition_ocr_assignment_uses_segment_position() -> None:
    paths = [((100, 100), (300, 100)), ((100, 220), (300, 220))]
    assert _transition_ocr_owner(_OcrRegion("go", (185, 116, 30, 18), .9), paths) == 0
    assert _transition_ocr_owner(_OcrRegion("outside", (345, 88, 50, 18), .9), paths) is None


def test_photo_fixture_is_unwarped_back_to_original_coordinates(generated_fixtures: Path) -> None:
    debug: dict[str, object] = {}
    result = recognize_image((generated_fixtures / "photo_perspective_shadow.png").read_bytes(), _debug=debug)
    assert len(result.states) == 2
    assert len(result.transitions) == 1
    assert "perspective" in debug["corrections"]
    assert all(state.geometry.x >= 0 and state.geometry.y >= 0 for state in result.states)


def test_curved_connection_is_review_only(generated_fixtures: Path) -> None:
    result = recognize_image((generated_fixtures / "curved_shadow.png").read_bytes())
    assert len(result.transitions) == 1
    assert result.transitions[0].direction_confirmed is False
    assert result.transitions[0].confidence < .5


def test_ocr_labels_states_then_nearby_transitions(monkeypatch: pytest.MonkeyPatch) -> None:
    boxes = [(40, 40, 160, 90), (320, 40, 160, 90), (600, 40, 160, 90)]
    detected = [
        (0, 1, (200, 85), (320, 85), 0.68),
        (1, 2, (480, 85), (600, 85), 0.68),
        (2, 0, (680, 210), (120, 210), 0.68),
    ]
    regions = [
        _OcrRegion("待機", (80, 70, 70, 22), 0.94),
        _OcrRegion("入金済み", (345, 70, 105, 22), 0.91),
        _OcrRegion("商品選択", (620, 70, 120, 22), 0.90),
        _OcrRegion("coin", (235, 48, 50, 20), 0.93),
        _OcrRegion("select", (515, 48, 54, 20), 0.92),
        _OcrRegion("refund", (350, 170, 72, 20), 0.89),
    ]
    monkeypatch.setattr(recognizer, "_detect_states", lambda _binary: boxes)
    monkeypatch.setattr(recognizer, "_detect_transitions", lambda _binary, _boxes, _debug=None: detected)
    monkeypatch.setattr(recognizer, "_extract_ocr_regions", lambda _gray: regions)
    monkeypatch.setattr(recognizer.shutil, "which", lambda _name: "/usr/bin/tesseract")
    image = np.full((280, 820, 3), 255, np.uint8)
    encoded, buffer = cv2.imencode(".png", image)
    assert encoded

    result = recognize_image(buffer.tobytes())

    assert [state.name for state in result.states] == ["待機", "入金済み", "商品選択"]
    assert [edge.event for edge in result.transitions] == ["coin", "select", "refund"]
    assert all(item.confidence >= 0.7 for item in [*result.states, *result.transitions])


def test_japanese_english_mixed_label_is_kept_editable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recognizer, "_detect_states", lambda _binary: [(40, 40, 210, 90)])
    monkeypatch.setattr(recognizer, "_detect_transitions", lambda _binary, _boxes, _debug=None: [])
    monkeypatch.setattr(
        recognizer,
        "_extract_ocr_regions",
        lambda _gray: [
            _OcrRegion("商品", (60, 65, 38, 20), 0.92),
            _OcrRegion("選択", (102, 65, 38, 20), 0.91),
            _OcrRegion("select", (146, 65, 50, 20), 0.90),
            _OcrRegion("item", (202, 65, 36, 20), 0.89),
        ],
    )
    monkeypatch.setattr(recognizer.shutil, "which", lambda _name: "/usr/bin/tesseract")
    encoded, buffer = cv2.imencode(".png", np.full((180, 280, 3), 255, np.uint8))
    assert encoded

    result = recognize_image(buffer.tobytes())

    assert result.states[0].name == "商品選択 select item"


def test_low_confidence_ocr_keeps_fallback_and_warns_review(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recognizer, "_detect_states", lambda _binary: [(40, 40, 180, 90)])
    monkeypatch.setattr(recognizer, "_detect_transitions", lambda _binary, _boxes, _debug=None: [])
    monkeypatch.setattr(recognizer, "_extract_ocr_regions", lambda _gray: [_OcrRegion("待機", (75, 65, 70, 20), 0.41)])
    monkeypatch.setattr(recognizer.shutil, "which", lambda _name: "/usr/bin/tesseract")
    encoded, buffer = cv2.imencode(".png", np.full((180, 280, 3), 255, np.uint8))
    assert encoded

    result = recognize_image(buffer.tobytes())

    assert result.states[0].name == "State 1"
    assert result.states[0].confidence == 0.41
    assert any("41%" in warning and "自動命名しませんでした" in warning for warning in result.warnings)


def test_low_confidence_event_keeps_event_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recognizer, "_detect_states", lambda _binary: [(40, 40, 160, 90), (320, 40, 160, 90)])
    monkeypatch.setattr(
        recognizer,
        "_detect_transitions",
        lambda _binary, _boxes, _debug=None: [(0, 1, (200, 85), (320, 85), 0.68)],
    )
    monkeypatch.setattr(
        recognizer,
        "_extract_ocr_regions",
        lambda _gray: [
            _OcrRegion("待機", (80, 70, 70, 22), 0.94),
            _OcrRegion("入金済み", (345, 70, 105, 22), 0.91),
            _OcrRegion("refund", (230, 48, 62, 20), 0.38),
        ],
    )
    monkeypatch.setattr(recognizer.shutil, "which", lambda _name: "/usr/bin/tesseract")
    encoded, buffer = cv2.imencode(".png", np.full((180, 520, 3), 255, np.uint8))
    assert encoded

    result = recognize_image(buffer.tobytes())

    assert result.transitions[0].event == "event_1"
    assert result.transitions[0].confidence == 0.38
    assert any("event_1 (38%)" in warning for warning in result.warnings)
