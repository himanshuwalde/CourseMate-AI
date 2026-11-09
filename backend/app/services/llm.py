"""Thin async client for Ollama's /api/chat. The model is configurable per request, per session
(UI dropdown, remembered on disk) or globally (LLM_MODEL in .env)."""
import json
from typing import AsyncIterator, Dict, List, Optional

import httpx

from ..config import settings
from ..storage import get_active_model


class LLMError(Exception):
    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal  # fatal = retrying other questions is pointless (Ollama down, model missing)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout, connect=5.0))


def _payload(messages: List[Dict], model: Optional[str], stream: bool, temperature: Optional[float]) -> Dict:
    return {
        "model": model or get_active_model(),
        "messages": messages,
        "stream": stream,
        "options": {
            "temperature": settings.llm_temperature if temperature is None else temperature,
            "num_ctx": settings.llm_num_ctx,
        },
    }


def _raise_for(status: int, body: str, model: str) -> None:
    if status == 404 or "not found" in body.lower():
        raise LLMError(f"Model '{model}' is not installed. Run:  ollama pull {model}", fatal=True)
    raise LLMError(f"Ollama returned HTTP {status}: {body[:200]}")


def _connect_error() -> LLMError:
    return LLMError(f"Cannot reach Ollama at {settings.ollama_base_url}. Start it with `ollama serve`.", fatal=True)


async def chat(messages: List[Dict], model: Optional[str] = None, temperature: Optional[float] = None) -> str:
    payload = _payload(messages, model, False, temperature)
    try:
        async with _client() as client:
            r = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
    except httpx.ConnectError as exc:
        raise _connect_error() from exc
    except httpx.TimeoutException as exc:
        raise LLMError("The model took too long to respond. Try a smaller model or raise LLM_TIMEOUT.") from exc
    if r.status_code != 200:
        _raise_for(r.status_code, r.text, payload["model"])
    return r.json().get("message", {}).get("content", "")


async def stream_chat(messages: List[Dict], model: Optional[str] = None) -> AsyncIterator[str]:
    payload = _payload(messages, model, True, None)
    try:
        async with _client() as client:
            async with client.stream("POST", f"{settings.ollama_base_url}/api/chat", json=payload) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode("utf-8", "replace")
                    _raise_for(r.status_code, body, payload["model"])
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break
    except httpx.ConnectError as exc:
        raise _connect_error() from exc
    except httpx.TimeoutException as exc:
        raise LLMError("The model took too long to respond. Try a smaller model or raise LLM_TIMEOUT.") from exc


async def list_models() -> List[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []))
    except Exception:  # noqa: BLE001
        return []
