import logging
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .models import RecognitionResult, RefineItemOut, RefineRequest, RefineResultOut
from .recognizer import recognize_image
from .refine import RefineRegion, refine_regions

logger = logging.getLogger("stateink.recognition")

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ACCEPTED_TYPES = {"image/png", "image/jpeg", "image/webp"}


def cors_origins(value: str) -> list[str]:
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


app = FastAPI(title="StateInk Recognition", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(os.getenv("STATEINK_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/recognize", response_model=RecognitionResult, response_model_by_alias=True)
async def recognize(file: UploadFile = File(...)) -> RecognitionResult:
    if file.content_type not in ACCEPTED_TYPES:
        raise HTTPException(status_code=415, detail="PNG、JPEG、WebP画像を選択してください")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="画像は10MB以下にしてください")
    try:
        return recognize_image(data)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001 - last-resort guard for a stable demo
        logger.exception("recognition failed")
        raise HTTPException(
            status_code=500,
            detail="画像の解析中に問題が発生しました。別の画像で試してください。",
        ) from error


@app.post("/api/recognize/refine", response_model=RefineResultOut)
async def recognize_refine(
    file: UploadFile = File(...),
    regions: str = Form(...),
) -> RefineResultOut:
    """High-accuracy re-read of a few weak State/Event boxes only.

    Slow on purpose (30-60s). Never touches structure, connection or direction:
    it returns text for the given ids and nothing else.
    """
    if file.content_type not in ACCEPTED_TYPES:
        raise HTTPException(status_code=415, detail="PNG、JPEG、WebP画像を選択してください")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="画像は10MB以下にしてください")
    try:
        parsed = RefineRequest.model_validate_json(regions)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail="再読取の対象指定が不正です") from error
    if not parsed.regions:
        return RefineResultOut(items=[], processing_ms=0.0, timed_out=False, attempted=0)
    targets = [
        RefineRegion(
            id=region.id,
            kind="transition" if region.kind == "transition" else "state",
            box=(int(region.x), int(region.y), int(region.width), int(region.height)),
        )
        for region in parsed.regions
    ]
    try:
        result = refine_regions(data, targets)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001 - last-resort guard for a stable demo
        logger.exception("refine failed")
        raise HTTPException(
            status_code=500,
            detail="高精度の再読取中に問題が発生しました。時間をおいて再試行してください。",
        ) from error
    return RefineResultOut(
        items=[RefineItemOut(id=item.id, text=item.text, confidence=item.confidence) for item in result.items],
        processing_ms=result.processing_ms,
        timed_out=result.timed_out,
        attempted=result.attempted,
    )
