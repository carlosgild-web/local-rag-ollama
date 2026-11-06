# Local RAG with Ollama

> **Draft README.** The full version, with screenshots, architecture and a demo, comes in Phase 9 (see [PLAN.md](PLAN.md)).

A fully local retrieval-augmented generation (RAG) app. Upload your PDF, Word, Markdown and text files, ask questions in a chat, and get answers taken **only from your documents**, with numbered citations. Nothing leaves your machine: models run in [Ollama](https://ollama.com), and storage is SQLite plus Chroma.

- **Grounded answers.** The model answers only from the retrieved passages. If the documents don't hold the answer, it says *"not found in the documents"*.
- **Citations.** Every answer shows its sources (file, page or section, retrieval score), and the UI warns when citations are missing or don't match a source.
- **Hybrid search.** Vector search (`bge-m3`) and keyword search (SQLite FTS5) are combined with reciprocal rank fusion.
- **Versioning.** A file with the same content is skipped. The same filename with new content becomes a new version, and rollback is instant. Deletes go to a 30-day trash, and every change is in the audit log.
- **Collections ("shelves").** Separate document sets, each with its own embedding model and chunking. Changing those settings rebuilds a shelf in the background and swaps it in when it's ready.
- **Web UI.** Dashboard, Library, Collections, Queue, and a streaming Chat with citations.

## Status

Phases 0–4 of [PLAN.md](PLAN.md) are done: ingestion, retrieval, API, web UI and Docker. The app was tested end to end on 2026-11-06 ([report](docs/test-reports/2026-11-06-e2e.md)). Phases 5–9 are planned: versions UI, control panel, evaluation, hardening and polish. See [CHANGELOG.md](CHANGELOG.md).

## Quick start

You need [Ollama](https://ollama.com) with a chat model and the embedding model:

```bash
ollama pull bge-m3
ollama pull llama3.1        # or qwen2.5:3b on a machine with ~8 GB RAM (see below)
```

### Local (Windows / macOS / Linux)

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env                                                      # optional settings
.venv/Scripts/python -m uvicorn app.main:app --port 8000                  # migrations run on start

# frontend (once, or after UI changes; FastAPI serves the build)
cd ../frontend && npm ci && npm run build
```

Open http://localhost:8000. For UI work, run `npm run dev` in `frontend/`: Vite serves the app on http://localhost:5173 and forwards `/api` to port 8000.

### Docker

```bash
# Ollama in its own container (pull models into it once):
docker compose up --build
docker compose exec ollama ollama pull bge-m3
docker compose exec ollama ollama pull llama3.1

# or use the Ollama already running on your machine:
docker compose -f compose.yaml -f compose.host-ollama.yaml up --build
```

**Low on RAM?** With about 8 GB, use a 3B chat model: set `CHAT_MODEL=qwen2.5:3b` in `backend/.env`, or pass it to `docker compose`. See [decision 0004](docs/decisions/0004-small-chat-model-on-low-ram.md).

## Testing

```bash
cd backend
.venv/Scripts/python -m pytest -q          # unit and API tests with fakes, no Ollama needed (CI runs these)
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
cd ../frontend && npm run build            # type check + build
```

**End-to-end test** against a running server and a real Ollama: the sample corpus, about 60 questions, versions, trash, jobs, a restart check and a prompt-injection check. See [e2e/README.md](e2e/README.md). The results of the 2026-11-06 runs are in [docs/test-reports/](docs/test-reports/).

## Repository layout

```
backend/app/        FastAPI app: api/, core/, ingest/, retrieval/, llm/, versioning/, jobs/, db/
backend/migrations/ Alembic migrations          backend/tests/  pytest suite (fakes only)
frontend/src/       React + Vite + TypeScript + Tailwind (pages/, components/, api/, hooks/)
e2e/                End-to-end test kit and sample corpus (fictional data)
docs/decisions/     Short records of design decisions and deviations from the plan
docs/test-reports/  End-to-end test reports
```

`backend/data/` holds your documents, the database, vectors and backups. It is never committed.

## Further reading

- [PLAN.md](PLAN.md): the roadmap, phase by phase
- [CLAUDE.md](CLAUDE.md): the project rules and invariants
- [docs/decisions/](docs/decisions/): why things are the way they are
- [CHANGELOG.md](CHANGELOG.md): what changed
