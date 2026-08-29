"""Real Tesseract OCR smoke tests for the jpn+eng pipeline.

These exercise the actual OCR engine (no monkeypatching). They are skipped when
the Tesseract binary is not installed, so local runs without OCR stay green while
CI (which installs tesseract-ocr-jpn/eng) verifies the real environment.
"""
from __future__ import annotations

import os
import shutil

import cv2
import numpy as np
import pytest

pytesseract = pytest.importorskip("pytesseract")

from app.recognizer import OCR_LANGUAGE, _crop_ocr_region, _normalize_ocr_text

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract binary is not installed on PATH",
)

_CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
)

_LATIN_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    *_CJK_FONT_CANDIDATES,
)


def _white_canvas(width: int = 260, height: int = 130) -> np.ndarray:
    return np.full((height, width, 3), 255, np.uint8)


def test_language_data_bundles_japanese_and_english() -> None:
    languages = set(pytesseract.get_languages(config=""))
    assert {"jpn", "eng"} <= languages, f"missing OCR language data: {sorted(languages)}"
    # The production language string must only reference installed models.
    assert set(OCR_LANGUAGE.split("+")) <= languages


def test_real_ocr_reads_ascii_label_through_production_config() -> None:
    image = _white_canvas()
    cv2.putText(image, "READY", (16, 84), cv2.FONT_HERSHEY_SIMPLEX, 1.7, (0, 0, 0), 4)

    region = _crop_ocr_region(image, (0, 0, image.shape[1], image.shape[0]))

    assert region is not None
    assert "READY" in region.text.upper()
    assert region.confidence > 0.3


def test_real_ocr_reads_japanese_label() -> None:
    font_path = next((path for path in _CJK_FONT_CANDIDATES if os.path.exists(path)), None)
    if font_path is None:
        pytest.skip("No CJK font available to render Japanese text")
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.new("RGB", (280, 150), "white")
    ImageDraw.Draw(canvas).text((28, 34), "実行", font=ImageFont.truetype(font_path, 72), fill="black")
    image = cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)

    region = _crop_ocr_region(image, (0, 0, image.shape[1], image.shape[0]))

    assert region is not None
    recovered = _normalize_ocr_text(region.text)
    assert "実" in recovered and "行" in recovered, f"unexpected OCR text: {region.text!r}"


def _draw_printed_diagram(font_path: str) -> bytes:
    """A hand-drawing-like diagram: ellipse states, modest text near the curved
    outline, thin strokes, a few degrees of rotation."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 760, 380
    image = np.full((height, width, 3), 255, np.uint8)
    cv2.ellipse(image, (150, 190), (110, 66), 0, 0, 360, (0, 0, 0), 3)
    cv2.ellipse(image, (610, 190), (110, 66), 0, 0, 360, (0, 0, 0), 3)
    cv2.arrowedLine(image, (262, 190), (498, 190), (0, 0, 0), 3, tipLength=0.12)

    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    label_font = ImageFont.truetype(font_path, 24)
    event_font = ImageFont.truetype(font_path, 20)
    draw.text((92, 178), "WAITING", font=label_font, fill=(0, 0, 0))
    draw.text((548, 178), "DISPENSE", font=label_font, fill=(0, 0, 0))
    draw.text((352, 160), "coin", font=event_font, fill=(0, 0, 0))
    rendered = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    rotation = cv2.getRotationMatrix2D((width / 2, height / 2), 3.0, 1.0)
    rotated = cv2.warpAffine(rendered, rotation, (width, height), borderValue=(255, 255, 255))
    ok, buffer = cv2.imencode(".png", rotated)
    assert ok
    return buffer.tobytes()


def test_printed_state_and_event_labels_are_read() -> None:
    """A legible 2-state diagram (WAITING -> DISPENSE, event `coin`) should be
    auto-named rather than left as `State N` / `event_N`."""
    font_path = next((path for path in _LATIN_FONT_CANDIDATES if os.path.exists(path)), None)
    if font_path is None:
        pytest.skip("No usable TrueType font to render printed labels")
    from app.recognizer import recognize_image

    result = recognize_image(_draw_printed_diagram(font_path))

    names = [state.name for state in result.states]
    events = [edge.event for edge in result.transitions]
    print("recognized states:", names, "events:", events)

    assert len(result.states) == 2, names
    joined = " ".join(name.upper() for name in names)
    assert "WAIT" in joined, f"WAITING not read: {names}"
    assert "DISP" in joined, f"DISPENSE not read: {names}"
    assert not any(name.startswith("State ") for name in names), names
    if events:
        assert any("coin" in event.lower() for event in events), events


def _diagram(font_path, centres, names, arrows, events, size, rot):
    from PIL import Image, ImageDraw, ImageFont
    w, h = size
    img = np.full((h, w, 3), 255, np.uint8)
    for cx, cy in centres:
        cv2.ellipse(img, (cx, cy), (96, 56), 0, 0, 360, (0, 0, 0), 3)
    for a, b in arrows:
        (x1, y1), (x2, y2) = centres[a], centres[b]
        cv2.arrowedLine(img, (x1 + 96, y1), (x2 - 96, y2), (0, 0, 0), 3, tipLength=0.1)
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    lf = ImageFont.truetype(font_path, 22)
    ef = ImageFont.truetype(font_path, 18)
    for (cx, cy), nm in zip(centres, names):
        d.text((cx - 46, cy - 12), nm, font=lf, fill=(0, 0, 0))
    for (a, b), nm in zip(arrows, events):
        (x1, y1), (x2, y2) = centres[a], centres[b]
        d.text(((x1 + x2) // 2 - 22, (y1 + y2) // 2 - 26), nm, font=ef, fill=(0, 0, 0))
    out = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), rot, 1.0)
    out = cv2.warpAffine(out, m, (w, h), borderValue=(255, 255, 255))
    ok, buf = cv2.imencode(".png", out)
    assert ok
    return buf.tobytes()


def _score(result, exp_states, exp_events):
    def norm(t): return "".join(c for c in t.lower() if c.isalnum())
    exp_s = [norm(x) for x in exp_states]
    exp_e = [norm(x) for x in exp_events]
    got_s = [norm(x.name) for x in result.states]
    got_e = [norm(x.event) for x in result.transitions]
    correct = sum(1 for g in got_s if any(g and (g in e or e in g) for e in exp_s))
    correct += sum(1 for g in got_e if any(g and (g in e or e in g) for e in exp_e))
    placeholder = sum(1 for x in result.states if x.name.startswith("State ")) +                   sum(1 for x in result.transitions if x.event.startswith("event_"))
    auto = sum(1 for x in result.states if x.confidence >= 0.8) +            sum(1 for x in result.transitions if x.direction_confirmed and x.confidence >= 0.8)
    total = len(result.states) + len(result.transitions)
    return dict(correct=correct, placeholder=placeholder, auto_confirmed=auto,
               review=total - auto, states=len(result.states), transitions=len(result.transitions))


def test_measure_pipeline() -> None:
    font_path = next((p for p in _LATIN_FONT_CANDIDATES if os.path.exists(p)), None)
    if font_path is None:
        pytest.skip("no font")
    from app.recognizer import recognize_image

    normal = _diagram(font_path, [(150, 190), (610, 190)], ["WAITING", "DISPENSE"],
                      [(0, 1)], ["coin"], (760, 380), 3.0)
    busy = _diagram(font_path,
                    [(120, 130), (430, 130), (740, 130), (1050, 130), (585, 380)],
                    ["WAITING", "PENDING", "PAID", "DISPENSE", "REFUND"],
                    [(0, 1), (1, 2), (2, 3), (3, 4)],
                    ["coin", "confirm", "select", "cancel"], (1180, 520), 2.0)

    report = {}
    for tag, png, es, ee in (("normal", normal, ["WAITING", "DISPENSE"], ["coin"]),
                             ("busy", busy, ["WAITING", "PENDING", "PAID", "DISPENSE", "REFUND"],
                              ["coin", "confirm", "select", "cancel"])):
        dbg = {}
        r = recognize_image(png, _debug=dbg)
        report[tag] = dict(processing_ms=r.processing_ms, timings=dbg.get("timings"),
                           **_score(r, es, ee),
                           names=[s.name for s in r.states], events=[t.event for t in r.transitions])

    assert False, "[MEASURE-PIPELINE] " + repr(report)
