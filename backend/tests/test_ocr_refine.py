"""Tests for the on-demand high-accuracy re-read (`/api/recognize/refine`).

The endpoint-contract tests run everywhere (Tesseract is mocked). The
accuracy/timing comparison tests need the real engine and skip without it.
"""
from __future__ import annotations

import io
import os
import shutil
import time

import cv2
import numpy as np
import pytest

pytesseract = pytest.importorskip("pytesseract")

from fastapi.testclient import TestClient

from app.main import app
from app.refine import RefineItem, RefineRegion, RefineResult, refine_regions

_HAS_TESSERACT = shutil.which("tesseract") is not None

_LATIN_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
)


def _tiny_png() -> bytes:
    ok, buffer = cv2.imencode(".png", np.full((40, 40, 3), 255, np.uint8))
    assert ok
    return buffer.tobytes()


# --------------------------------------------------------------------------- #
# Endpoint contract (Tesseract mocked -- runs everywhere)
# --------------------------------------------------------------------------- #

def test_refine_endpoint_returns_items_for_requested_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main

    captured: dict[str, object] = {}

    def fake_refine(data: bytes, regions: list[RefineRegion]) -> RefineResult:
        captured["regions"] = regions
        return RefineResult(
            items=[RefineItem(id="state-2", text="入金済み", confidence=0.82)],
            processing_ms=1234.5,
            timed_out=False,
            attempted=len(regions),
        )

    monkeypatch.setattr(main, "refine_regions", fake_refine)
    response = TestClient(app).post(
        "/api/recognize/refine",
        files={"file": ("d.png", _tiny_png(), "image/png")},
        data={"regions": '{"regions": [{"id": "state-2", "kind": "state", "x": 10, "y": 20, "width": 120, "height": 70}]}'},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == [{"id": "state-2", "text": "入金済み", "confidence": 0.82}]
    assert body["attempted"] == 1
    assert body["timed_out"] is False
    assert isinstance(body["processing_ms"], (int, float))
    # The endpoint forwards exactly the requested boxes -- no structure work.
    regions = captured["regions"]
    assert [r.id for r in regions] == ["state-2"]
    assert regions[0].kind == "state"
    assert regions[0].box == (10, 20, 120, 70)


def test_refine_endpoint_rejects_malformed_regions() -> None:
    response = TestClient(app).post(
        "/api/recognize/refine",
        files={"file": ("d.png", _tiny_png(), "image/png")},
        data={"regions": "not json"},
    )
    assert response.status_code == 422
    assert "対象指定" in response.json()["detail"]


def test_refine_endpoint_accepts_empty_target_list() -> None:
    response = TestClient(app).post(
        "/api/recognize/refine",
        files={"file": ("d.png", _tiny_png(), "image/png")},
        data={"regions": '{"regions": []}'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["attempted"] == 0


def test_refine_endpoint_rejects_non_image() -> None:
    response = TestClient(app).post(
        "/api/recognize/refine",
        files={"file": ("notes.txt", b"nope", "text/plain")},
        data={"regions": '{"regions": []}'},
    )
    assert response.status_code == 415


def test_refine_never_runs_structure_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """`refine_regions` must not run structure / transition / connection /
    direction detection, and must not fall back to the full recognition
    preprocessor (which counts blobs to tune its binariser)."""
    import app.recognizer as recognizer

    forbidden = (
        "_detect_states",
        "_detect_transitions",
        "_infer_connected_states",
        "_detect_curved_connections",
        "_preprocess_image",
        "recognize_image",
    )
    for name in forbidden:
        def _blocked(*_args, _name=name, **_kwargs):  # pragma: no cover - only if regressed
            raise AssertionError(f"refine must not call {_name}")

        monkeypatch.setattr(recognizer, name, _blocked)

    ok, buffer = cv2.imencode(".png", np.full((120, 200, 3), 255, np.uint8))
    assert ok
    result = refine_regions(buffer.tobytes(), [RefineRegion(id="s1", kind="state", box=(10, 10, 80, 40))])
    assert isinstance(result, RefineResult)
    # It carries text readings only -- no structure / connection / direction fields.
    assert not hasattr(result, "transitions")
    assert not hasattr(result, "states")


# --------------------------------------------------------------------------- #
# Real-OCR accuracy / timing comparison
# --------------------------------------------------------------------------- #

def _draw_faint_diagram(font_path: str) -> bytes:
    """Two rectangular states, event `submit`. The right-hand state name is
    small and light grey -- the kind of label the fast pass tends to leave as
    a placeholder or read with low confidence."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 820, 360
    image = np.full((height, width, 3), 255, np.uint8)
    cv2.rectangle(image, (70, 130), (330, 250), (0, 0, 0), 3)
    cv2.rectangle(image, (500, 130), (760, 250), (0, 0, 0), 3)
    cv2.arrowedLine(image, (332, 190), (498, 190), (0, 0, 0), 3, tipLength=0.12)

    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    strong = ImageFont.truetype(font_path, 30)
    faint = ImageFont.truetype(font_path, 15)
    tiny = ImageFont.truetype(font_path, 14)
    draw.text((120, 175), "READY", font=strong, fill=(0, 0, 0))
    draw.text((560, 182), "REVIEWING", font=faint, fill=(150, 150, 150))
    draw.text((372, 168), "submit", font=tiny, fill=(140, 140, 140))
    rendered = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    rotation = cv2.getRotationMatrix2D((width / 2, height / 2), 2.0, 1.0)
    rotated = cv2.warpAffine(rendered, rotation, (width, height), borderValue=(255, 255, 255))
    ok, buffer = cv2.imencode(".png", rotated)
    assert ok
    return buffer.tobytes()


@pytest.mark.skipif(not _HAS_TESSERACT, reason="Tesseract binary is not installed on PATH")
def test_refine_recovers_labels_the_fast_pass_left_weak() -> None:
    font_path = next((path for path in _LATIN_FONT_CANDIDATES if os.path.exists(path)), None)
    if font_path is None:
        pytest.skip("No usable TrueType font")
    from app.recognizer import recognize_image

    data = _draw_faint_diagram(font_path)

    normal_start = time.perf_counter()
    normal = recognize_image(data)
    normal_ms = (time.perf_counter() - normal_start) * 1000

    weak = [s for s in normal.states if s.confidence < 0.8 or s.name.strip().lower().startswith("state ")]
    weak += [
        s for s in normal.states
        if s not in weak and s.name.strip().upper() not in {"READY"}  # REVIEWING may be read but poorly
    ]
    weak_events = [t for t in normal.transitions if t.confidence < 0.8 or t.event.strip().lower().startswith("event_")]

    targets = [RefineRegion(id=s.id, kind="state", box=(int(s.geometry.x), int(s.geometry.y), int(s.geometry.width), int(s.geometry.height))) for s in weak]
    targets += [RefineRegion(id=t.id, kind="transition", box=(int(t.geometry.x), int(t.geometry.y), int(t.geometry.width), int(t.geometry.height))) for t in weak_events]
    if not targets:
        pytest.skip("fast pass already read every label with high confidence -- nothing to refine")

    refine_start = time.perf_counter()
    refined = refine_regions(data, targets)
    refine_ms = (time.perf_counter() - refine_start) * 1000

    readings = {item.id: item for item in refined.items}
    print(
        "\n[REFINE COMPARISON]"
        f"\n  normal : {normal_ms:7.0f} ms  states={[(s.name, round(s.confidence, 2)) for s in normal.states]}"
        f"  events={[(t.event, round(t.confidence, 2)) for t in normal.transitions]}"
        f"\n  refine : {refined.processing_ms:7.0f} ms  targets={len(targets)}  applied={len(readings)}"
        f"  items={[(i.id, i.text, round(i.confidence, 2)) for i in refined.items]}"
        f"  timed_out={refined.timed_out}"
        f"\n  wallclock refine={refine_ms:.0f} ms"
    )

    # Structure is untouched: refine returns text only, never states/transitions.
    assert not hasattr(refined, "states")
    # It must not have invented readings for ids it was not asked about.
    assert set(readings) <= {t.id for t in targets}
    # Stays inside the advertised budget.
    assert refined.processing_ms < 70_000
    # At least one weak label should now be readable, and better than before.
    improved = False
    for state in normal.states:
        hit = readings.get(state.id)
        if hit and hit.confidence >= state.confidence and any(c.isalnum() for c in hit.text):
            improved = True
    for edge in normal.transitions:
        hit = readings.get(edge.id)
        if hit and hit.confidence >= edge.confidence and any(c.isalnum() for c in hit.text):
            improved = True
    assert improved, f"refine produced nothing usable: {refined.items}"


@pytest.mark.skipif(not _HAS_TESSERACT, reason="Tesseract binary is not installed on PATH")
def test_refine_omits_blank_regions_instead_of_guessing() -> None:
    """A box over empty paper must come back with no reading -- no forced misread."""
    canvas = np.full((300, 400, 3), 255, np.uint8)
    ok, buffer = cv2.imencode(".png", canvas)
    assert ok
    result = refine_regions(
        buffer.tobytes(),
        [RefineRegion(id="blank", kind="state", box=(120, 120, 160, 60))],
    )
    assert result.items == []
    assert result.attempted == 1
