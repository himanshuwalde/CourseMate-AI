"""Test setup: an isolated data dir, a fake embedder (no model download) and a fake LLM (no Ollama)."""
import hashlib
import math
import os
import re
import tempfile

import pytest

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="rag-test-")

from fastapi.testclient import TestClient  # noqa: E402

from app.services import embeddings, llm  # noqa: E402


def _vec(text: str, dim: int = 128):
    v = [0.0] * dim
    for w in re.findall(r"\w+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts: [_vec(t) for t in texts])
    monkeypatch.setattr(embeddings, "embed_query", lambda q: _vec(q))

    async def fake_chat(messages, model=None, temperature=None):
        user = messages[-1]["content"]
        if messages[0]["content"].startswith("Extract every"):
            return '["What is overfitting?", "Define dropout."]'
        if "Context:" in user and "zzzunknown" in user:
            return "NOT_FOUND"
        if "Context:" in user:
            return "Dropout randomly disables neurons during training [1].\n- Reduces overfitting [1]\n- **Cheap** to apply"
        return "General answer from the model."

    async def fake_stream(messages, model=None):
        for tok in ["Dropout ", "randomly ", "disables ", "neurons ", "while training [1]."]:
            yield tok

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "stream_chat", fake_stream)

    async def fake_models():
        return ["llama3.2:3b", "llama3.1:8b"]

    monkeypatch.setattr(llm, "list_models", fake_models)


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
