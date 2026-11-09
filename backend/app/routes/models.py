from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..services import llm
from ..storage import get_active_model, set_active_model

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
async def models():
    available = await llm.list_models()
    return {
        "active": get_active_model(),
        "default": settings.llm_model,
        "available": available,
        "ollama_ok": bool(available) or await _ollama_up(),
        "embedding_model": settings.embedding_model,
        "rerank_enabled": settings.rerank_enabled,
    }


async def _ollama_up() -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            return (await c.get(f"{settings.ollama_base_url}/api/tags")).status_code == 200
    except Exception:  # noqa: BLE001
        return False


class ActiveModel(BaseModel):
    model: str


@router.post("/models/active")
async def choose_model(body: ActiveModel):
    name = body.model.strip()
    if not name:
        raise HTTPException(400, "Model name is empty.")
    available = await llm.list_models()
    if available and name not in available:
        raise HTTPException(400, f"'{name}' is not installed in Ollama. Run: ollama pull {name}")
    set_active_model(name)
    return {"active": name}
