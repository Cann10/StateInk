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
