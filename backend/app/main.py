from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import chat, documents, models, question_bank
from .storage import registry


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_dirs()
    registry.fail_interrupted()
    yield


app = FastAPI(title="RAG Studio", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])

for module in (documents, chat, question_bank, models):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
