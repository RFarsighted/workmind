import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

router = APIRouter()


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL is not ready") from exc

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.chroma_url.rstrip('/')}/api/v2/heartbeat")
            response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Chroma is not ready") from exc

    return {"status": "ready", "postgres": "ok", "chroma": "ok"}
