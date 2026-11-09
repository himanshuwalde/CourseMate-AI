from typing import List

from fastapi import HTTPException

from .storage import registry


def resolve_doc_ids(requested: List[str]) -> List[str]:
    """Empty request = search every ready document. Unknown / not-ready ids are ignored."""
    ready = registry.ready_ids()
    ids = [d for d in requested if d in ready] if requested else ready
    if not ids:
        raise HTTPException(400, "No ready documents. Upload a document and wait until it shows as ready.")
    return ids
