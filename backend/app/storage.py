"""Tiny JSON-file stores: the document registry and runtime settings (e.g. the chosen LLM)."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .config import settings


class _JsonFile:
    def __init__(self, filename: str):
        self.filename = filename
        self.lock = threading.RLock()

    @property
    def path(self) -> Path:
        return settings.data_dir / self.filename

    def read(self, default):
        with self.lock:
            if not self.path.exists():
                return default
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return default

    def write(self, data) -> None:
        with self.lock:
            settings.ensure_dirs()
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self.path)


class DocumentRegistry:
    """Keeps one record per uploaded document: status, pages, chunks, etc."""

    def __init__(self):
        self._file = _JsonFile("documents.json")

    def list(self) -> list[dict]:
        docs = self._file.read({})
        return sorted(docs.values(), key=lambda d: d["created_at"], reverse=True)

    def get(self, doc_id: str) -> Optional[dict]:
        return self._file.read({}).get(doc_id)

    def add(self, filename: str, ext: str, size: int) -> dict:
        with self._file.lock:
            docs = self._file.read({})
            doc_id = uuid.uuid4().hex[:12]
            rec = {
                "id": doc_id, "filename": filename, "ext": ext, "size": size,
                "status": "processing", "error": None, "pages": 0, "chunks": 0,
                "created_at": time.time(),
            }
            docs[doc_id] = rec
            self._file.write(docs)
            return rec

    def update(self, doc_id: str, **fields: Any) -> None:
        with self._file.lock:
            docs = self._file.read({})
            if doc_id in docs:
                docs[doc_id].update(fields)
                self._file.write(docs)

    def remove(self, doc_id: str) -> None:
        with self._file.lock:
            docs = self._file.read({})
            docs.pop(doc_id, None)
            self._file.write(docs)

    def ready_ids(self) -> list[str]:
        return [d["id"] for d in self.list() if d["status"] == "ready"]

    def fail_interrupted(self) -> None:
        """Anything still 'processing' at startup was interrupted by a restart."""
        for d in self.list():
            if d["status"] == "processing":
                self.update(d["id"], status="failed", error="Interrupted by a server restart. Delete and upload again.")


registry = DocumentRegistry()
_runtime = _JsonFile("runtime_settings.json")


def get_active_model() -> str:
    return _runtime.read({}).get("llm_model") or settings.llm_model


def set_active_model(model: str) -> None:
    data = _runtime.read({})
    data["llm_model"] = model
    _runtime.write(data)
