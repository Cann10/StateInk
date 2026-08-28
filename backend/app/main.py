import logging
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .models import RecognitionResult
from .recognizer import recognize_image

logger = logging.getLogger("stateink.recognition")

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def cors_origins(value: str) -> list[str]:
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


app = FastAPI(title="StateInk Recognition", version="0.2.0")
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
    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=415, detail="PNG、JPEG、WebP画像を選択してください")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
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
