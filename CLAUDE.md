# CLAUDE.md — Local RAG with Ollama

Read this file first in every session. The full roadmap is in `PLAN.md`.

## What this project is

A fully local RAG (retrieval-augmented generation) app: Ollama for chat and embeddings,
a FastAPI backend, a React web UI to manage documents, versions, history and settings.
No cloud calls at runtime. It will be published as a GitHub portfolio project, so
code quality, tests, README and "clone and run" experience matter.

## Stack (do not change without asking)

| Layer | Choice |
|---|---|
| LLM runtime | Ollama (chat: `qwen2.5:7b` or `llama3.1:8b`; embeddings: `bge-m3`) |
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Alembic, pydantic-settings |
| Vector store | ChromaDB (persistent) behind a `VectorStore` interface |
| Keyword search | SQLite FTS5, fused with vectors via RRF |
| Parsing | PyMuPDF (PDF), python-docx (Word), txt/md direct; optional Docling; Tesseract OCR fallback |
| Jobs | In-process worker backed by a SQLite `jobs` table (no Redis) |
| Frontend | React, Vite, TypeScript, Tailwind, shadcn/ui, TanStack Query |
| Streaming | Server-sent events (SSE) |
| Packaging | Docker (one app image + Ollama container) |

## Repo layout

```
backend/app/{api,core,ingest,retrieval,llm,versioning,jobs,db,eval}/
backend/migrations/   backend/tests/
frontend/src/{pages,components,api,hooks}/
data/                 # gitignored: files/, chroma/, app.db, backups/, hf/
scripts/              # start.ps1, backup.ps1
docs/decisions/       # short decision records
```

## Commands

```bash
# backend
cd backend && pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
pytest -q
ruff check . && ruff format --check .

# CLI (phases 1-2)
python -m app.cli ingest ./docs
python -m app.cli ask "your question"

# frontend
cd frontend && npm ci && npm run dev      # Vite dev server, proxies /api to :8000
npm run build

# containers
docker compose up --build
```

## Invariants (never break these)

1. **One service layer.** All writes to SQLite, Chroma and the file store go through the
   service layer in `versioning/` and `ingest/`. Routes and CLI never write directly.
2. **Content-addressed files.** Originals are stored as `DATA_DIR/files/<sha256>.<ext>`.
3. **Versioning.** Same hash = duplicate (skip). Same filename with new hash = new
   `document_version`; old chunks stay indexed with `active=false`. Rollback only flips
   `active_version_id` and never re-embeds. Deletes are soft (30-day trash).
4. **Embedding model per collection.** Store model name and chunking config on the
   collection. Never mix vectors from different models. A change means a new collection,
   built in the background and swapped in (blue/green).
5. **Reproducible answers.** Every assistant message stores the `rag_profile` version,
   retrieved chunks and scores in `message_sources`.
6. **Grounded answers only.** The prompt must instruct the model to answer only from
   context and otherwise say the answer is not in the documents. Citations are mandatory.
7. **Audit everything.** Uploads, deletes, rollbacks, reindexes and settings changes
   write to `audit_log`.

## Container-ready rules (follow from day one)

- All config comes from environment variables via `core/config.py`; keep `.env.example` updated.
- Everything persistent lives under `DATA_DIR`. No hardcoded paths; use `pathlib`.
- `OLLAMA_BASE_URL` is configurable (container `http://ollama:11434`, host `http://host.docker.internal:11434`).
- `/health` reports Ollama, SQLite and vector store status.
- Logs go to stdout, structured JSON with a request id.
- Run exactly 1 uvicorn worker and 1 job worker (embedded Chroma and SQLite are single-writer).
- File watcher supports polling mode (`WATCH_POLLING=true`).
- Never bake models into images. Cache downloads under `DATA_DIR/hf`.

## Testing rules

- `LLMClient`, `EmbeddingClient` and `VectorStore` are interfaces with real and fake
  implementations. Unit tests and CI use the fakes and never need Ollama.
- Every versioning invariant above has a test (duplicate skip, new version, rollback,
  soft delete, blue/green swap).
- Keep a small open-license test corpus in `backend/tests/corpus/` (Spanish and English).
  Never add personal documents to the repo.
- A phase is not done until its "Done when" criteria in `PLAN.md` pass and `ruff` and
  `pytest` are green.

## How to work in this repo

- One phase per session. Start by reading `PLAN.md` for that phase.
- For phases 3 and 5 (API and versioning), propose a short plan and wait for approval before coding.
- Make small commits with clear messages (conventional commits: `feat:`, `fix:`, `test:`, `docs:`).
- If a decision deviates from `PLAN.md`, add a short note in `docs/decisions/` and tell me.
- Ask before adding a new dependency, and prefer the standard library or what is already installed.

## Do not

- Call any cloud or third-party API at runtime.
- Commit `data/`, `.env`, model weights, or personal documents.
- Run more than one uvicorn worker.
- Bypass the service layer, or hard-delete versions without going through the trash.
- Add features outside the current phase.
