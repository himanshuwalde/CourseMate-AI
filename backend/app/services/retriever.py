"""Hybrid retrieval: vector search + BM25 keyword search, fused with Reciprocal Rank Fusion,
with an optional cross-encoder reranker."""
import re
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..config import settings
from . import vectorstore
from .vectorstore import Hit

_bm25_cache: Dict[tuple, tuple] = {}
_cache_lock = threading.Lock()
_reranker = None
_rerank_lock = threading.Lock()


@dataclass
class RetrievalResult:
    hits: List[Hit] = field(default_factory=list)
    best_similarity: float = 0.0


def invalidate_cache() -> None:
    with _cache_lock:
        _bm25_cache.clear()


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


def _bm25_for(doc_ids: List[str]):
    key = tuple(sorted(doc_ids))
    with _cache_lock:
        if key in _bm25_cache:
            return _bm25_cache[key]
    rows = vectorstore.get_all_chunks(list(key))
    if not rows:
        entry = (None, [])
    else:
        from rank_bm25 import BM25Okapi

        entry = (BM25Okapi([_tokenize(r.text) for r in rows]), rows)
    with _cache_lock:
        _bm25_cache[key] = entry
    return entry


def _rerank(query: str, hits: List[Hit]) -> List[Hit]:
    global _reranker
    if _reranker is None:
        with _rerank_lock:
            if _reranker is None:
                from sentence_transformers import CrossEncoder

                _reranker = CrossEncoder(settings.rerank_model)
    scores = _reranker.predict([(query, h.text) for h in hits])
    return [h for h, _ in sorted(zip(hits, scores), key=lambda p: -p[1])]


def retrieve(query: str, doc_ids: Optional[List[str]], k: Optional[int] = None) -> RetrievalResult:
    k = k or settings.top_k
    pool = max(k * 4, 20)

    vec_hits = vectorstore.vector_search(query, doc_ids, pool)
    best = vec_hits[0].similarity if vec_hits and vec_hits[0].similarity is not None else 0.0

    bm25, rows = _bm25_for(doc_ids or [])  # empty list -> all documents
    bm_hits: List[Hit] = []
    if bm25 is not None:
        scores = bm25.get_scores(_tokenize(query))
        order = sorted(range(len(rows)), key=lambda i: -scores[i])[:pool]
        bm_hits = [rows[i] for i in order if scores[i] > 0]

    fused: Dict[str, list] = {}
    for rank, h in enumerate(vec_hits):
        fused[h.chunk_id] = [h, 1.0 / (60 + rank + 1)]
    for rank, h in enumerate(bm_hits):
        if h.chunk_id in fused:
            fused[h.chunk_id][1] += 1.0 / (60 + rank + 1)
        else:
            fused[h.chunk_id] = [h, 1.0 / (60 + rank + 1)]

    ordered = [h for h, _ in sorted(fused.values(), key=lambda p: -p[1])]
    if settings.rerank_enabled and ordered:
        ordered = _rerank(query, ordered[: k * 3])
    hits = ordered[:k]

    if settings.min_relevance and best < settings.min_relevance:
        hits = []
    return RetrievalResult(hits=hits, best_similarity=best)
