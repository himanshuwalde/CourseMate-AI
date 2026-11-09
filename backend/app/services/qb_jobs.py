"""Question-bank jobs: answer many questions in the background and keep progress + results."""
import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from fastapi.concurrency import run_in_threadpool

from ..config import settings
from . import llm, prompts, retriever
from .exporters import ExportItem

GENERAL_NOTE = "Not found in the uploaded documents. Answered from the model's general knowledge: verify before using."
NOT_FOUND_ANSWER = "Not found in the uploaded documents."


@dataclass
class QResult:
    id: int
    number: str
    question: str
    marks: Optional[int] = None
    answer: str = ""
    status: str = "pending"  # pending | running | done | not_found | general | error
    sources: List[str] = field(default_factory=list)
    note: Optional[str] = None


@dataclass
class Job:
    id: str
    title: str
    doc_ids: List[str]
    style: str
    instructions: str
    allow_general: bool
    model: Optional[str]
    status: str = "queued"  # queued | running | done | failed
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    results: List[QResult] = field(default_factory=list)

    @property
    def done_count(self) -> int:
        return sum(1 for r in self.results if r.status not in {"pending", "running"})

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["done_count"] = self.done_count
        d["total"] = len(self.results)
        return d

    def to_export_items(self) -> List[ExportItem]:
        return [
            ExportItem(r.question, r.answer or "(no answer)", r.sources, r.marks, r.note)
            for r in self.results
        ]


JOBS: Dict[str, Job] = {}
_sem: Optional[asyncio.Semaphore] = None  # one job at a time: a local model can't parallelise well


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(1)
    return _sem


def create_job(questions: List[Dict], doc_ids: List[str], style: str, instructions: str,
               allow_general: bool, model: Optional[str], title: str) -> Job:
    job = Job(uuid.uuid4().hex[:12], title or "Answers", doc_ids, style, instructions, allow_general, model)
    for i, q in enumerate(questions, start=1):
        job.results.append(QResult(i, str(q.get("number") or i), q["text"].strip(), q.get("marks")))
    JOBS[job.id] = job
    save_job(job)
    return job


def save_job(job: Job) -> None:
    settings.ensure_dirs()
    (settings.jobs_dir / f"{job.id}.json").write_text(json.dumps(job.to_dict()), encoding="utf-8")


def get_job(job_id: str) -> Optional[Job]:
    if job_id in JOBS:
        return JOBS[job_id]
    path = settings.jobs_dir / f"{job_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    results = [QResult(**r) for r in data.pop("results")]
    data.pop("done_count", None)
    data.pop("total", None)
    job = Job(**data, results=results)
    if job.status in {"queued", "running"}:  # interrupted by a restart
        job.status = "failed"
        job.error = "Interrupted by a server restart."
    JOBS[job.id] = job
    return job


async def _answer(job: Job, r: QResult, extra_instructions: Optional[str] = None) -> None:
    r.status = "running"
    k = 6 if job.style in {"detailed", "exam"} else 4
    result = await run_in_threadpool(retriever.retrieve, r.question, job.doc_ids, k)

    extra = " ".join(x for x in [
        prompts.STYLE_GUIDE.get(job.style, ""),
        prompts.marks_guidance(r.marks),
        job.instructions,
        extra_instructions or "",
    ] if x)

    answer = ""
    if result.hits:
        answer = await llm.chat(prompts.rag_messages(r.question, result.hits, extra=extra), job.model)

    if result.hits and not prompts.is_not_found(answer):
        idx = prompts.cited_indexes(answer, len(result.hits)) or list(range(1, len(result.hits) + 1))
        seen, sources = set(), []
        for i in idx:
            h = result.hits[i - 1]
            label = f"{h.filename}, p.{h.page}" if h.page else h.filename
            if label not in seen:
                seen.add(label)
                sources.append(label)
        r.answer, r.sources, r.status, r.note = prompts.strip_citations(answer), sources, "done", None
    elif job.allow_general:
        general = await llm.chat(prompts.general_messages(r.question, extra), job.model)
        r.answer, r.sources, r.status, r.note = general.strip(), [], "general", GENERAL_NOTE
    else:
        r.answer, r.sources, r.status, r.note = NOT_FOUND_ANSWER, [], "not_found", None


async def run_job(job: Job) -> None:
    async with _semaphore():
        job.status = "running"
        try:
            for r in job.results:
                if r.status in {"done", "general", "not_found"}:
                    continue
                try:
                    await _answer(job, r)
                except llm.LLMError as exc:
                    r.status, r.answer, r.note = "error", "", str(exc)
                    if exc.fatal:
                        raise
                except Exception as exc:  # noqa: BLE001
                    r.status, r.answer, r.note = "error", "", f"Unexpected error: {exc}"
                save_job(job)
            job.status = "done"
        except llm.LLMError as exc:
            job.status, job.error = "failed", str(exc)
        finally:
            save_job(job)


async def regenerate(job: Job, qid: int, extra: Optional[str] = None) -> QResult:
    r = next((x for x in job.results if x.id == qid), None)
    if r is None:
        raise KeyError(qid)
    async with _semaphore():
        try:
            await _answer(job, r, extra)
        except llm.LLMError as exc:
            r.status, r.note = "error", str(exc)
        save_job(job)
    return r
