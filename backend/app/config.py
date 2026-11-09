"""Central configuration, read from environment variables / backend/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    llm_model = os.getenv("LLM_MODEL", "llama3.2:3b")
    llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_num_ctx = int(os.getenv("LLM_NUM_CTX", "4096"))
    llm_timeout = float(os.getenv("LLM_TIMEOUT", "300"))

    embedding_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    rerank_enabled = _bool("RERANK_ENABLED", False)
    rerank_model = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
    chunk_overlap = min(int(os.getenv("CHUNK_OVERLAP", "200")), int(os.getenv("CHUNK_SIZE", "1000")) // 2)
    top_k = int(os.getenv("TOP_K", "5"))
    min_relevance = float(os.getenv("MIN_RELEVANCE", "0.0"))

    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "50"))
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.jobs_dir, self.chroma_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
