# RAG Studio

Chat with your own documents, and turn a whole **question bank** into a finished **PDF / Word** answer file.
Runs fully locally and for free: **Ollama** for the language model, **HuggingFace** embeddings, **Chroma** vector DB,
**FastAPI** backend, **React** frontend.

## What it does

- **Documents:** upload PDF, DOCX, TXT or MD. Indexing runs in the background and shows progress. Tick which documents each question may use.
- **Chat with citations:** streamed answers with `[1]`-style references that point to file and page. Follow-up questions ("explain that more") are rewritten into standalone search queries first.
- **Question-bank mode:** upload documents, then upload a question bank. The app detects the questions (you can edit, add, delete, and set marks), answers each from your documents, and exports everything as **PDF, DOCX or Markdown**.
- **Choose the output format** from the buttons, or just say it: ask "...as a PDF" or "...in a Word file" and the matching export button is highlighted.
- **Safe by default:** if the documents don't contain the answer you get "Not in documents". An opt-in toggle falls back to general knowledge and labels those answers clearly.
- **Better retrieval than plain vector search:** hybrid search (vectors + BM25 keywords, merged with Reciprocal Rank Fusion), optional cross-encoder reranking.
- **Configurable model:** default `llama3.2:3b`; switch to `llama3.1:8b` (or anything else Ollama serves) without touching code.

## Setup

**Prerequisites:** Python 3.10+, Node 18+, [Ollama](https://ollama.com/download).

```bash
# 1) Models
ollama pull llama3.2:3b          # ~2 GB, works on most laptops
ollama pull llama3.1:8b          # optional, ~5 GB download, wants ~8 GB+ free RAM

# 2) Backend  (first run downloads torch + the embedding model, so give it a few minutes)
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
uvicorn app.main:app --reload --port 8000

# 3) Frontend (new terminal)
cd frontend
npm install
npm run dev                      # open http://localhost:5173
```

## Switching between the 3B and 8B model

Any of these works:

1. **UI:** use the *Language model* dropdown in the sidebar. The choice is remembered.
2. **`.env`:** set `LLM_MODEL=llama3.1:8b` and restart the backend.
3. **API:** `POST /api/models/active` with `{"model": "llama3.1:8b"}`.

The dropdown lists whatever `ollama list` shows. If the 3B answers feel thin on long exam questions, the 8B is the single biggest quality upgrade.
You can also raise `LLM_NUM_CTX` (default 4096) for longer contexts.

## Using it

**Chat:** tick documents, ask. Open "passages used" to see the exact source text. Use the PDF / Word / Markdown buttons under an answer, or the "Whole conversation" row.

**Question bank:**
1. Upload and tick your study documents.
2. *Question bank* tab, then *Upload question bank*. Detected questions appear in an editable list. Marks written like `(5 marks)` or `[10M]` are picked up and used to size each answer.
3. Pick a style (exam / detailed / short), optionally add instructions such as "keep each answer under 150 words", then *Generate answers*.
4. Watch progress, regenerate any weak answer individually, then download PDF, Word or Markdown.

Question detection is regex-first (numbered lists, `Q1.`, `1)`, tables, ignores "Unit/Module" headings) with an LLM fallback for messy layouts.

## Project layout

```
backend/
  app/
    main.py                 FastAPI app
    config.py  storage.py   settings (.env) and small JSON stores
    routes/                 documents, chat (SSE), question_bank (+jobs/export), models
    services/
      loaders.py            PDF / DOCX / TXT readers
      chunking.py           overlap-aware splitter
      embeddings.py         HuggingFace sentence-transformers
      vectorstore.py        Chroma wrapper
      retriever.py          hybrid search + optional reranker
      llm.py  prompts.py    Ollama client and all prompt text
      question_parser.py    question detection
      qb_jobs.py            background answering jobs
      exporters.py          DOCX / PDF / Markdown rendering
  tests/                    pytest suite (fake embedder + fake LLM, no downloads needed)
frontend/                   React + Vite (plain CSS)
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET / POST / DELETE | `/api/documents`, `/api/documents/{id}` | list, upload, remove |
| POST | `/api/chat` | streamed answer (SSE: `sources`, `token`, `export_hint`, `done`, `error`) |
| POST | `/api/question-bank/parse` | upload a question bank, get its questions |
| POST | `/api/question-bank/answer` | start an answering job |
| GET | `/api/jobs/{id}` | progress and results |
| POST | `/api/jobs/{id}/questions/{qid}/regenerate` | redo one answer |
| GET | `/api/jobs/{id}/download?format=docx\|pdf\|md` | download the finished file |
| POST | `/api/export` | export any list of Q&A as a file |
| GET / POST | `/api/models`, `/api/models/active` | list / switch model |

Interactive docs: http://localhost:8000/docs

## Configuration (`backend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `LLM_MODEL` | `llama3.2:3b` | any Ollama model name |
| `LLM_NUM_CTX` | `4096` | context window sent to Ollama |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | changing it requires re-uploading documents |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200` | characters |
| `TOP_K` | `5` | passages sent to the model |
| `RERANK_ENABLED` | `false` | cross-encoder reranking |
| `MIN_RELEVANCE` | `0.0` | raise (e.g. `0.35`) to answer "not found" more eagerly |
| `MAX_UPLOAD_MB` | `50` | per file |
| `DATA_DIR` | `./data` | uploads, Chroma DB, jobs |

## Tests

```bash
cd backend && pytest -q
```

## Troubleshooting

- **"Cannot reach Ollama":** run `ollama serve` (the desktop app does this automatically).
- **"Model ... is not installed":** `ollama pull <name>`.
- **Upload stuck on "Reading and indexing":** the first upload downloads the embedding model. Wait, or check the backend terminal.
- **Scanned PDF fails with "No extractable text":** OCR isn't built in yet (see roadmap).
- **Weak or cut-off answers:** switch to the 8B model, raise `TOP_K` or `LLM_NUM_CTX`, or turn on `RERANK_ENABLED`.
- **Non-Latin characters missing in PDF export:** the PDF exporter uses DejaVu / Arial if found on the machine. DOCX export always works.

## Roadmap ideas

OCR for scanned PDFs (Tesseract), retrieval evaluation set (RAGAS), user accounts with per-user documents, Postgres + pgvector, Docker Compose, Celery queue for ingestion, agentic retrieval, feedback buttons.
