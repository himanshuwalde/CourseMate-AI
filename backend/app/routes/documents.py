from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from ..config import settings
from ..services import retriever, vectorstore
from ..services.ingest import ingest_document
from ..services.loaders import ALLOWED_EXTENSIONS
from ..storage import registry

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents():
    return registry.list()


@router.post("", status_code=202)
async def upload_documents(background: BackgroundTasks, files: List[UploadFile] = File(...)):
    settings.ensure_dirs()
    limit = settings.max_upload_mb * 1024 * 1024
    created = []
    for f in files:
        name = Path(f.filename or "upload").name
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"'{name}': unsupported type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        rec = registry.add(name, ext, 0)
        dest = settings.uploads_dir / f"{rec['id']}{ext}"
        size = 0
        with dest.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    out.close()
                    dest.unlink(missing_ok=True)
                    registry.remove(rec["id"])
                    raise HTTPException(413, f"'{name}' is larger than {settings.max_upload_mb} MB.")
                out.write(chunk)
        registry.update(rec["id"], size=size)
        background.add_task(ingest_document, rec["id"])  # runs in a worker thread
        created.append(registry.get(rec["id"]))
    return created


@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    rec = registry.get(doc_id)
    if not rec:
        raise HTTPException(404, "Document not found.")
    try:
        vectorstore.delete_document(doc_id)
    except Exception:  # noqa: BLE001
        pass
    (settings.uploads_dir / f"{doc_id}{rec['ext']}").unlink(missing_ok=True)
    registry.remove(doc_id)
    retriever.invalidate_cache()
    return {"deleted": doc_id}
