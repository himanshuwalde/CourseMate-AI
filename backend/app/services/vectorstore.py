"""Chroma wrapper. All documents live in one collection and are isolated by `doc_id` metadata."""
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..config import settings
from . import embeddings

_collection = None
_lock = threading.Lock()


@dataclass
class Hit:
    chunk_id: str
    text: str
    filename: str
    page: int  # 0 = no page information (docx / txt)
    doc_id: str
    similarity: Optional[float] = None  # cosine similarity from the vector search, if any


def get_collection():
    global _collection
    if _collection is None:
        with _lock:
            if _collection is None:
                import chromadb

                settings.ensure_dirs()
                client = chromadb.PersistentClient(path=str(settings.chroma_dir))
                _collection = client.get_or_create_collection("documents", metadata={"hnsw:space": "cosine"})
    return _collection


def _where(doc_ids: Optional[List[str]]) -> Optional[Dict]:
    if not doc_ids:
        return None
    if len(doc_ids) == 1:
        return {"doc_id": doc_ids[0]}
    return {"doc_id": {"$in": list(doc_ids)}}


def add_chunks(doc_id: str, filename: str, chunks: List[Dict]) -> None:
    col = get_collection()
    batch = 128
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        col.add(
            ids=[f"{doc_id}:{i + j}" for j in range(len(part))],
            documents=[c["text"] for c in part],
            embeddings=embeddings.embed_documents([c["text"] for c in part]),
            metadatas=[{"doc_id": doc_id, "filename": filename, "page": int(c["page"])} for c in part],
        )


def delete_document(doc_id: str) -> None:
    get_collection().delete(where={"doc_id": doc_id})


def _to_hit(cid: str, text: str, meta: Dict, similarity: Optional[float] = None) -> Hit:
    return Hit(cid, text, meta.get("filename", "?"), int(meta.get("page", 0)), meta.get("doc_id", ""), similarity)


def vector_search(query: str, doc_ids: Optional[List[str]], n: int) -> List[Hit]:
    col = get_collection()
    res = col.query(
        query_embeddings=[embeddings.embed_query(query)],
        n_results=n,
        where=_where(doc_ids),
        include=["documents", "metadatas", "distances"],
    )
    ids, docs, metas, dists = res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
    return [_to_hit(i, d, m, 1.0 - dist) for i, d, m, dist in zip(ids, docs, metas, dists)]


def get_all_chunks(doc_ids: Optional[List[str]]) -> List[Hit]:
    res = get_collection().get(where=_where(doc_ids), include=["documents", "metadatas"])
    return [_to_hit(i, d, m) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])]
