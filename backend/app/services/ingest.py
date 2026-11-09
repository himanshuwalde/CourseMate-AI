"""Background ingestion: load -> chunk -> embed -> store."""
from ..config import settings
from ..storage import registry
from . import retriever, vectorstore
from .chunking import split_text
from .loaders import load_pages


def ingest_document(doc_id: str) -> None:
    rec = registry.get(doc_id)
    if not rec:
        return
    path = settings.uploads_dir / f"{doc_id}{rec['ext']}"
    try:
        pages = load_pages(path)
        chunks = []
        for page_no, text in pages:
            for piece in split_text(text, settings.chunk_size, settings.chunk_overlap):
                chunks.append({"text": piece, "page": page_no or 0})
        if not chunks:
            raise ValueError("No extractable text found. Scanned PDFs need OCR, which is not supported yet.")
        vectorstore.add_chunks(doc_id, rec["filename"], chunks)
        registry.update(doc_id, status="ready", pages=len(pages), chunks=len(chunks), error=None)
    except Exception as exc:  # noqa: BLE001
        registry.update(doc_id, status="failed", error=str(exc)[:300])
        try:
            vectorstore.delete_document(doc_id)
        except Exception:  # noqa: BLE001
            pass
    finally:
        retriever.invalidate_cache()
