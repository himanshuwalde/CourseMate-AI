"""Local HuggingFace embeddings (sentence-transformers). The model downloads on first use."""
import threading
from typing import List

from ..config import settings

_model = None
_load_lock = threading.Lock()
_encode_lock = threading.Lock()

# BGE models work best when queries get this instruction prefix (documents do not).
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _get_model():
    global _model
    if _model is None:
        with _load_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_documents(texts: List[str]) -> List[List[float]]:
    with _encode_lock:
        vecs = _get_model().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    return vecs.tolist()


def embed_query(query: str) -> List[float]:
    prefix = _QUERY_PREFIX if "bge" in settings.embedding_model.lower() else ""
    with _encode_lock:
        vec = _get_model().encode([prefix + query], normalize_embeddings=True, show_progress_bar=False)
    return vec[0].tolist()
