import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, cors_origins
import numpy as np

from app.recognizer import _head_score, _merge_collinear_segments, _states_along_line, recognize_image
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
    assert result.processing_ms < 1_000


def test_api_returns_reviewable_result(generated_fixtures: Path) -> None:
    image = generated_fixtures / "simple_two_state.png"
    response = TestClient(app).post("/api/recognize", files={"file": (image.name, image.read_bytes(), "image/png")})
    assert response.status_code == 200
    body = response.json()
    assert body["states"][0]["name"] == "State 1"
    assert body["transitions"][0]["from"] == "state-1"
    assert body["warnings"] == ["読み取りを確認してください。薄い線や矢印方向は誤認識することがあります。"]


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
