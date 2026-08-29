"""Tests for the on-demand high-accuracy re-read (`/api/recognize/refine`).

The endpoint-contract tests run everywhere (Tesseract is mocked). The
accuracy/timing comparison test needs the real engine and skips without it.
"""
from __future__ import annotations

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
# Real-OCR: fast pass vs high-accuracy re-read
# --------------------------------------------------------------------------- #

def _draw_hard_diagram(font_path: str) -> bytes:
    """Two rectangular states + one event, drawn small, low-contrast, noisy and
    rotated -- the kind of photo the fast montage pass reads poorly. The event
    text sits well above the arrow so a tight label crop misses it."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 900, 420
    image = np.full((height, width, 3), 255, np.uint8)
    cv2.rectangle(image, (80, 150), (330, 270), (40, 40, 40), 2)
    cv2.rectangle(image, (560, 150), (810, 270), (40, 40, 40), 2)
    cv2.arrowedLine(image, (332, 210), (558, 210), (40, 40, 40), 2, tipLength=0.10)

    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    small = ImageFont.truetype(font_path, 16)
    tiny = ImageFont.truetype(font_path, 13)
    draw.text((150, 200), "IDLE", font=small, fill=(120, 120, 120))
    draw.text((588, 200), "CHARGING", font=small, fill=(150, 150, 150))
    draw.text((402, 150), "plug", font=tiny, fill=(150, 150, 150))  # ~55px above the arrow

    rendered = np.array(pil)
    noise = np.random.default_rng(7).normal(0, 9, rendered.shape).astype(np.int16)
    rendered = np.clip(rendered.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    rendered = cv2.cvtColor(rendered, cv2.COLOR_RGB2BGR)
    rotation = cv2.getRotationMatrix2D((width / 2, height / 2), 3.5, 1.0)
    rotated = cv2.warpAffine(rendered, rotation, (width, height), borderValue=(255, 255, 255))
    ok, buffer = cv2.imencode(".png", rotated)
    assert ok
    return buffer.tobytes()


@pytest.mark.skipif(not _HAS_TESSERACT, reason="Tesseract binary is not installed on PATH")
def test_refine_compared_with_the_fast_pass() -> None:
    """Run the fast pass and the high-accuracy re-read on the same hard image
    and print a comparison (visible in CI via `pytest -rsp`). The re-read must
    return usable, id-scoped text within budget and never touch structure."""
    font_path = next((path for path in _LATIN_FONT_CANDIDATES if os.path.exists(path)), None)
    if font_path is None:
        pytest.skip("No usable TrueType font")
    from app.recognizer import recognize_image

    data = _draw_hard_diagram(font_path)

    normal_start = time.perf_counter()
    normal = recognize_image(data)
    normal_ms = (time.perf_counter() - normal_start) * 1000

    targets = [
        RefineRegion(id=s.id, kind="state", box=(int(s.geometry.x), int(s.geometry.y), int(s.geometry.width), int(s.geometry.height)))
        for s in normal.states
    ] + [
        RefineRegion(id=t.id, kind="transition", box=(int(t.geometry.x), int(t.geometry.y), int(t.geometry.width), int(t.geometry.height)))
        for t in normal.transitions
    ]
    if not targets:
        pytest.skip("fast pass detected no boxes to re-read")

    refine_start = time.perf_counter()
    refined = refine_regions(data, targets)
    refine_wall_ms = (time.perf_counter() - refine_start) * 1000
    readings = {item.id: item for item in refined.items}

    weak_before = [
        (s.id, s.name, round(s.confidence, 2))
        for s in normal.states
        if s.confidence < 0.8 or s.name.strip().lower().startswith("state ")
    ] + [
        (t.id, t.event, round(t.confidence, 2))
        for t in normal.transitions
        if t.confidence < 0.8 or t.event.strip().lower().startswith("event_")
    ]
    report_lines = [
        "",
        "[REFINE COMPARISON]",
        "  fast pass    : {:8.0f} ms  states={}  events={}".format(
            normal_ms,
            [(s.name, round(s.confidence, 2)) for s in normal.states],
            [(t.event, round(t.confidence, 2)) for t in normal.transitions],
        ),
        "  weak after fast pass: {}".format(weak_before),
        "  high-accuracy: {:8.0f} ms (wallclock {:.0f} ms)  targets={}  applied={}  timed_out={}".format(
            refined.processing_ms, refine_wall_ms, len(targets), len(readings), refined.timed_out
        ),
        "  re-read items: {}".format([(i.id, i.text, round(i.confidence, 2)) for i in refined.items]),
    ]
    print("\n".join(report_lines))

    assert not hasattr(refined, "states") and not hasattr(refined, "transitions")
    assert set(readings) <= {t.id for t in targets}, "re-read invented an id it was not asked about"
    assert refined.processing_ms < 70_000, "re-read blew the time budget"
    for item in refined.items:
        assert item.text.strip() and any(character.isalnum() for character in item.text)
        assert 0.5 <= item.confidence <= 0.97
    assert readings, "re-read produced nothing usable: {}".format(refined.items)


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
