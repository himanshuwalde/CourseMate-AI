import json
from typing import List, Optional

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..deps import resolve_doc_ids
from ..services import llm, prompts, retriever
from ..services.formats import detect_format

router = APIRouter(prefix="/api", tags=["chat"])


class Msg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: List[Msg] = []
    doc_ids: List[str] = []
    model: Optional[str] = None


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest):
    doc_ids = resolve_doc_ids(req.doc_ids)
    history = [m.model_dump() for m in req.history]

    async def events():
        try:
            query = req.question
            if history:  # turn follow-ups ("explain that more") into standalone search queries
                try:
                    rewritten = (await llm.chat(prompts.rewrite_messages(req.question, history), req.model, 0.0)).strip()
                    if rewritten:
                        query = rewritten.splitlines()[0]
                except llm.LLMError:
                    pass

            result = await run_in_threadpool(retriever.retrieve, query, doc_ids)
            hits = result.hits
            yield sse("sources", [
                {"index": i, "filename": h.filename, "page": h.page, "snippet": h.text[:320]}
                for i, h in enumerate(hits, start=1)
            ])

            if not hits:
                yield sse("token", {"text": prompts.NOT_FOUND_MESSAGE})
            else:
                head, decided = "", False
                async for token in llm.stream_chat(prompts.rag_messages(req.question, hits, history), req.model):
                    if decided:
                        yield sse("token", {"text": token})
                        continue
                    head += token
                    if len(head) >= 12:  # enough text to tell whether the model said NOT_FOUND
                        decided = True
                        if prompts.is_not_found(head):
                            yield sse("token", {"text": prompts.NOT_FOUND_MESSAGE})
                            break
                        yield sse("token", {"text": head})
                if not decided and head:
                    yield sse("token", {"text": prompts.NOT_FOUND_MESSAGE if prompts.is_not_found(head) else head})

            fmt = detect_format(req.question)
            if fmt:
                yield sse("export_hint", {"format": fmt})
            yield sse("done", {})
        except llm.LLMError as exc:
            yield sse("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            yield sse("error", {"message": f"Unexpected error: {exc}"})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
