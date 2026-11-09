import asyncio
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..config import settings
from ..deps import resolve_doc_ids
from ..services import exporters, qb_jobs
from ..services.loaders import ALLOWED_EXTENSIONS, load_text
from ..services.question_parser import parse_questions

router = APIRouter(prefix="/api", tags=["question-bank"])
_tasks: set = set()  # keep references so background tasks are not garbage collected


@router.post("/question-bank/parse")
async def parse_question_bank(file: UploadFile = File(...), model: Optional[str] = None):
    name = Path(file.filename or "questions").name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File too large.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"qb{ext}"
        path.write_bytes(data)
        try:
            text = load_text(path)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Could not read the file: {exc}") from exc
    if not text.strip():
        raise HTTPException(400, "No text found in this file (scanned PDF?).")
    questions = await parse_questions(text, model)
    if not questions:
        raise HTTPException(422, "No questions detected. Add them manually in the list.")
    return {"filename": name, "questions": questions}


class QuestionIn(BaseModel):
    number: Optional[str] = None
    text: str = Field(min_length=2, max_length=2000)
    marks: Optional[int] = Field(default=None, ge=1, le=100)


class AnswerRequest(BaseModel):
    questions: List[QuestionIn] = Field(min_length=1, max_length=150)
    doc_ids: List[str] = []
    style: str = "detailed"  # short | detailed | exam
    instructions: str = Field(default="", max_length=500)  # e.g. "keep each answer under 150 words"
    allow_general_knowledge: bool = False
    model: Optional[str] = None
    title: str = "Question bank answers"


@router.post("/question-bank/answer", status_code=202)
async def start_answering(req: AnswerRequest):
    if req.style not in {"short", "detailed", "exam"}:
        raise HTTPException(400, "style must be short, detailed or exam.")
    doc_ids = resolve_doc_ids(req.doc_ids)
    job = qb_jobs.create_job([q.model_dump() for q in req.questions], doc_ids, req.style, req.instructions,
                             req.allow_general_knowledge, req.model, req.title)
    task = asyncio.create_task(qb_jobs.run_job(job))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job.to_dict()


def _job_or_404(job_id: str) -> qb_jobs.Job:
    job = qb_jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return job


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    return _job_or_404(job_id).to_dict()


class RegenerateRequest(BaseModel):
    instructions: Optional[str] = Field(default=None, max_length=500)


@router.post("/jobs/{job_id}/questions/{qid}/regenerate")
async def regenerate_answer(job_id: str, qid: int, req: RegenerateRequest = RegenerateRequest()):
    job = _job_or_404(job_id)
    try:
        result = await qb_jobs.regenerate(job, qid, req.instructions)
    except KeyError:
        raise HTTPException(404, "Question not found.")
    return result.__dict__


@router.get("/jobs/{job_id}/download")
def download_job(job_id: str, format: str = Query("docx")):
    job = _job_or_404(job_id)
    try:
        body, mime, filename = exporters.export(job.title, job.to_export_items(), format)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class ExportItemIn(BaseModel):
    question: str
    answer: str
    sources: List[str] = []


class ExportRequest(BaseModel):
    title: str = "Answers"
    format: str = "docx"
    items: List[ExportItemIn] = Field(min_length=1, max_length=200)


@router.post("/export")
def export_items(req: ExportRequest):
    items = [exporters.ExportItem(i.question, i.answer, i.sources) for i in req.items]
    try:
        body, mime, filename = exporters.export(req.title, items, req.format)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
