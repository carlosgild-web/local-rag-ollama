# Local RAG with Ollama — Implementation Plan

Companion file: `CLAUDE.md` (rules for Claude Code). Work one phase per session.

## 1. Goals

| Goal | Detail |
|---|---|
| Fully local | Ollama for chat and embeddings, no cloud calls at runtime |
| Sources | PDF, Word, txt, md (Spanish and English) |
| Web UI | Manage files, collections, versions, history, settings, evaluation |
| Version control | Per-document versions with diff and rollback; versioned settings profiles |
| Runs anywhere | Natively on Windows during development, in Docker for delivery |
| Portfolio-ready | Clone and run in 5 commands or fewer, CI, tests, eval numbers, demo video |

## 2. Stack

| Layer | Pick | Alternatives |
|---|---|---|
| LLM runtime | Ollama | none |
| Chat model | `qwen2.5:7b` or `llama3.1:8b` (14B with more RAM) | `gemma3`, `mistral-nemo` |
| Embeddings | `bge-m3` (multilingual) | `nomic-embed-text`, `mxbai-embed-large` |
| Backend | Python 3.11+, FastAPI | none |
| Vector DB | ChromaDB (embedded), behind a `VectorStore` interface | Qdrant, LanceDB |
| Keyword search | SQLite FTS5 + rank fusion (RRF) with vectors | none |
| Metadata DB | SQLite, SQLAlchemy, Alembic | Postgres later |
| Parsing | PyMuPDF, python-docx, optional Docling, Tesseract OCR | unstructured |
| Jobs | In-process worker backed by a SQLite `jobs` table | Redis + RQ/Celery later |
| Frontend | React, Vite, TypeScript, Tailwind, shadcn/ui, TanStack Query | none |
| Streaming | Server-sent events | none |
| File watching | `watchdog` (polling mode in containers) | none |

The built frontend is served by FastAPI, so the app starts with one command.

## 3. Architecture

```
React UI ──HTTP/SSE──► FastAPI ──► Ollama (chat + embeddings)
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
   SQLite (meta,      ChromaDB          DATA_DIR/files/
   FTS5, history,     (vectors)         (originals named
   jobs, audit)                          by SHA-256)
```

## 4. Data model

| Table | Purpose |
|---|---|
| `collections` | Separate knowledge bases; store embedding model and chunking config |
| `documents` | Logical file: name, tags, collection, `active_version_id`, trash state |
| `document_versions` | Version number, SHA-256, extracted text, date, note |
| `chunks` | Text, page or heading, position, `version_id`; same id in the vector payload |
| `ingest_jobs` | Status, progress, errors, retries |
| `rag_profiles` | Versioned settings snapshots (top-k, chunk size, prompt, models) |
| `chat_sessions`, `messages` | Conversation history |
| `message_sources` | Retrieved chunks, scores and profile version for each answer |
| `feedback` | Thumbs up/down with comment |
| `eval_sets`, `eval_cases`, `eval_runs` | Evaluation |
| `audit_log` | Every upload, delete, rollback, reindex, settings change |

## 5. Versioning and history rules

| Event | Behavior |
|---|---|
| Same file uploaded again (same hash) | Skipped as duplicate, with a notice |
| Same filename, changed content | New version; old chunks stay indexed with `active=false` |
| Rollback | Flip `active_version_id` only; no re-embedding |
| Delete | Soft delete, 30-day trash, then purge |
| Changing embedding model or chunking | Build a new collection in the background, swap in (blue/green), keep the old one until confirmed |
| Settings change | New `rag_profile` version; each answer records the version it used |
| Version diff | Text diff between extracted versions |

## 6. Retrieval defaults

| Setting | Start at |
|---|---|
| Chunk size | 600 tokens, 12% overlap, split on headings and paragraphs first |
| Candidates | 20 from vector search + 20 from FTS5, fused with RRF into the top 20 |
| Reranker | Off in MVP. Later, `bge-reranker-v2-m3` rescoring the top 20 |
| Sent to the LLM | Top 5 chunks |
| Temperature | 0 (was 0.2; decision 0016) |
| `num_ctx` | 8192 |
| Answer rule | Answer only from context, otherwise say "not found in the documents" |

## 7. Web UI pages

| Page | What the user can do | Priority |
|---|---|---|
| Dashboard | Counts of documents, chunks, disk; Ollama status; active jobs; recent activity | MVP |
| Library | Drag-and-drop upload, folder import, status badges, tags, search and filter, preview, delete, re-index | MVP |
| Collections | Create, rename, choose model and chunking | MVP |
| Ingestion queue | Progress bars, errors, retry, cancel | MVP |
| Chat | Streaming answers, clickable citations to source page or chunk, collection and tag filters, model picker, session list, regenerate, thumbs up/down | MVP |
| Document history | Version timeline, text diff, rollback, notes per version | v1 |
| Watched folders | Auto-ingest on file add or change | v1 |
| Retrieval inspector | Top-k chunks with scores, final prompt, sliders for k, threshold, hybrid weight, reranker | v1 |
| Models manager | List Ollama models, pull with progress, delete, set defaults | v1 |
| Profiles | Edit system prompt, chunk size, top-k, with version history and compare | v1 |
| History and audit | Timeline of changes and queries, search, CSV or JSON export | v1 |
| Evaluation | Golden Q&A set, run it, compare profiles or versions | v2 |
| Backup and restore | One-click zip of DB, vectors and files; restore | v2 |
| System | Logs, RAM and GPU use, health checks | v2 |
| Auth | Optional password; bound to localhost by default | v2 |

## 8. API endpoints

| Area | Endpoints |
|---|---|
| Documents | `POST /documents`, `GET /documents`, `DELETE /documents/{id}`, `POST /documents/{id}/reindex` |
| Versions | `GET /documents/{id}/versions`, `GET /documents/{id}/diff?a=&b=`, `POST /documents/{id}/rollback` |
| Collections | `GET/POST /collections`, `POST /collections/{id}/reindex` |
| Chat | `POST /chat` (SSE), `GET /sessions`, `GET /sessions/{id}`, `POST /messages/{id}/feedback` |
| Retrieval | `POST /retrieve` (chunks and scores without generating) |
| Jobs | `GET /jobs`, `POST /jobs/{id}/retry`, `POST /jobs/{id}/cancel` |
| Models | `GET /models`, `POST /models/pull` (SSE progress), `DELETE /models/{name}` |
| Profiles | `GET/POST /profiles`, `GET /profiles/{id}/versions` |
| Ops | `GET /audit`, `POST /backup`, `POST /restore`, `GET /health`, `GET /metrics` |

## 9. Phases

Estimates are working days of your attention and review with Claude Code doing most of the typing.
Total is about 30 working days; the MVP (through phase 4) is about 15.

### Phase 0 — Setup (0.75 d)

- [x] Install Ollama; pull `bge-m3` and `qwen2.5:7b` (or `llama3.1:8b`). On the 8 GB laptop: `qwen2.5:3b` (decision 0004)
- [x] Create repo, layout from `CLAUDE.md`, dependencies, `ruff`, `pytest`, pre-commit
- [x] `core/config.py` with pydantic-settings; `.env.example`
- [x] Add `CLAUDE.md` and this `PLAN.md` to the repo root
- [x] Open-license test corpus of 20 to 30 mixed files (Spanish and English) in `backend/tests/corpus/`

**Done when:** `ollama run` answers, `pytest` runs, config loads from environment variables.

### Phase 1 — Ingestion core, CLI (2–3 d)

- [x] Interfaces `LLMClient`, `EmbeddingClient`, `VectorStore` with Ollama/Chroma implementations and fakes
- [x] Parsers for txt, md, docx, pdf; detect pages with low text yield and queue OCR
- [x] Structure-aware chunker (600 tokens, 12% overlap)
- [x] Content-addressed file store under `DATA_DIR/files`
- [x] Write chunks to SQLite, FTS5 and Chroma
- [x] CLI `ingest <path>`; skip unchanged files

**Done when:** the test corpus ingests, a second run skips everything, unit tests pass with fakes.

### Phase 2 — Retrieval and answers, CLI (2 d)

- [x] Vector search + FTS5 search + RRF fusion
- [x] Optional reranker behind a flag
- [x] Prompt template with citations and the "not found" rule
- [x] Streaming generation; CLI `ask`

**Done when:** answers cite file and page, and an unanswerable question returns "not found in the documents".

### Phase 3 — Backend API (3–4 d) — plan first, then code

- [x] SQLAlchemy models and Alembic migrations for all tables
- [x] Versioning service (single service layer) and audit log
- [x] SQLite-backed job worker (1 worker) with retry and cancel
- [x] All routes from section 8 (except metrics and backup)
- [x] SSE chat endpoint; `/health` with Ollama, SQLite and vector store status
- [x] Structured JSON logging with request ids

**Done when:** Swagger lists all routes and versioning tests pass (duplicate skip, new version, rollback, soft delete, blue/green swap).

### Phase 4 — UI MVP and Docker (about 6 d)

- [x] Vite + React + TypeScript + Tailwind + shadcn/ui; TanStack Query
- [x] Dashboard, Library, Collections, Queue, Chat with citations
- [x] FastAPI serves the built frontend
- [x] `Dockerfile` and `compose.yaml` (appendix A), healthchecks, named volumes
- [x] GitHub Actions: ruff, pytest, frontend build, `docker build` on every push

**Done when:** uploading a PDF in the browser indexes it and you can ask about it, and `docker compose up` gives the same result.

✅ **Done 2026-11-06.** Browser upload and chat were verified locally and in Docker (host-Ollama mode). A full end-to-end test (`e2e/`) followed, with 52/52 must-pass checks on the re-test; see `docs/test-reports/2026-11-06-e2e.md` and `CHANGELOG.md` (0.4.0).

### Phase 5 — Versions and history (3 d) — plan first, then code

- [x] Version timeline per document, text diff, rollback, notes, and a quick editor with who and what changed (decision 0014)
- [x] Trash view with restore and purge: the 30-day purge runs at app start, and *Delete permanently* empties one document (decision 0018)
- [x] Chat history list and search (decision 0014)
- [x] Audit view

**Done when:** you can edit a file, re-upload, roll back, and see answers change accordingly.

✅ **Done 2026-11-13.** Released as 0.8.0 on 2026-11-12. The trash purge and the audit view were finished afterwards (they had been left unticked).

### Phase 6 — Control panel (about 3 d)

- [x] Retrieval inspector (chunks, scores, final prompt, parameter sliders): `/inspector`, [decision 0024](docs/decisions/0024-retrieval-inspector.md)
- [x] Profiles with version history and compare: `/profiles`, with restore as a new version
- [x] Models manager with pull progress: `/models`, delete refused while a model is in use
- [x] Watched folders with `WATCH_POLLING` option: `/watched`, [decision 0025](docs/decisions/0025-watched-folders.md)

**Done when:** changing a slider changes retrieval results live in the inspector.

✅ **Done when is met (2026-11-14).** The user checked it by hand on the demo library. Moving a slider re-queries in about 15 ms once the question's embedding is cached. PRs #33 (inspector), #34 (profiles), #36 (models) and the watched-folders PR. Along the way, #35 fixed demo libraries loaded before v0.9.0, which had no glossary words.

### Phase 7 — Evaluation (3 d)

Taken before Phase 6 ([decision 0019](docs/decisions/0019-evaluation.md)).

- [x] Golden set editor (question, expected source, expected answer notes): the Evaluation page, 53-case demo set
- [x] Runner with hit rate@5, MRR and LLM-judged faithfulness, plus facts, "not found" and citations to the right file
- [x] Compare two profiles or two index versions side by side

**Done when:** vector only, hybrid and hybrid + reranker can be compared on the same question set.

✅ **Done when is met (2026-11-14).** Retrieval: vector 0.865 MRR, hybrid 0.934, hybrid + reranker 0.956 (decision 0023). Answers went from 70% to 91% of questions passed after three measured fixes: citation repair (0020), glossary (0021) and a partial-answers prompt rule (0022). Closed with v0.9.0: the final run with the judge confirmed 91% (faithfulness 0.74; the 3B judge is unreliable), and the README has the eval tables.

Open quality items from the 2026-11-06 end-to-end test, to measure here (`docs/test-reports/2026-11-06-e2e.md`):
- FAQ questions answered "not found" although the right passages were retrieved (sc-06, sc-07). Check the chunking of `08-customer-faq.txt`.
- A price-table mix-up: a wholesale price given as the retail price (sc-01).
- About 1 in 5 citations are valid numbers that point to the wrong document. `citation_status` can't detect this (decision 0007).
- Try a 7B/8B chat model on better hardware against `qwen2.5:3b` (decision 0004).

Found in manual tests on 2026-11-12/13 (temperature 0), to add to the golden set:
- **Different words:** "How many vacation days do I have?" answers "not found" in both the console (hr shelf) and the portal, although the PTO section is in the top 3 sources. Asking for "PTO days" answers correctly. The model doesn't connect "vacation" with "PTO".
- **Missing detail:** "Can I get a custom bead color made?" on the customer-support shelf cites the right FAQ entry but leaves out the contact email. The portal's answer includes it.
- **Answers from unrelated text:** the same question on the operations shelf (no FAQ) builds an answer from the supplier agreement instead of saying "not found", and reads the agreement's "Buyer" (Hilda & Luna) as the customer.

### Phase 8 — Hardening (2 d)

- [x] Backup and restore (zip of DB, vectors, files; decision 0015)
- [ ] Optional password auth (localhost-only by default)
- [x] Launcher scripts for Windows (`start.ps1`) and Linux/macOS: `start.cmd` / `start.sh` (decision 0013; macOS not tried on a real Mac yet)
- [ ] Test coverage on versioning and jobs; fix flaky tests

**Done when:** a fresh machine goes from clone to working app in under 15 minutes (excluding model downloads).

### Phase 9 — Portfolio polish (3–4 d)

- [ ] Prometheus `/metrics` (query latency, retrieval count, job durations) and request-id logging
- [ ] `demo` compose profile with small models (`llama3.2:3b` plus `bge-m3`)
- [x] Public open-license demo corpus (Spanish and English): the Hilda & Luna demo company in `backend/demo/`
- [ ] README: architecture diagram, 3–5 screenshots, 2–3 minute demo video, "how it works", hardware notes. Done except the video, which is on hold
- [ ] Eval results table in the README (hit rate@5 and MRR per profile)
- [ ] `docs/decisions/`: why Chroma behind an interface, why active-version pointer, why blue/green reindex
- [ ] License (MIT or Apache-2.0), changelog, tag `v0.1`
- [ ] Audit repo for personal data and secrets, including git history

**Done when:** a reviewer who only has Docker can run the demo in 5 commands or fewer and understand the project from the README in a few minutes.

## 10. Hardware sizing

| Model | Approx. memory (Q4) | Notes |
|---|---|---|
| `bge-m3` | ~1.2 GB | Always loaded |
| 3B chat model (demo) | ~2 GB | Fine on 8 GB RAM |
| 7–8B chat model | ~5–6 GB | Comfortable on 16 GB RAM |
| 14B chat model | ~9–10 GB | 8+ GB VRAM or 32 GB RAM |

CPU-only indexing is the slow part: budget a few minutes per 100 pages.

## 11. Docker

| Mode | Description |
|---|---|
| A. Ollama container | `docker compose up` starts app and Ollama; GPU needs NVIDIA Container Toolkit with Docker Desktop on WSL2 |
| B. Ollama on host | Remove the `ollama` service and set `OLLAMA_BASE_URL=http://host.docker.internal:11434`; if unreachable, set `OLLAMA_HOST=0.0.0.0` on the host |

Windows and Docker Desktop notes:

| Issue | Fix |
|---|---|
| WSL2 memory cap (default about 50% of RAM) | Set `memory=16GB` in `%UserProfile%\.wslconfig` for an 8B model in a container |
| SQLite and Chroma on bind-mounted Windows folders | Use named volumes for `/data`; bind mount only the read-only inbox |
| File-change events on bind mounts | Use polling every 5 to 10 s |
| Image size | About 1 GB without Docling; 3 to 5 GB with Docling or the reranker, so keep them optional extras with CPU-only torch |
| Exposed ports | Bind to `127.0.0.1`; if opened to a LAN, enable auth first |

When to change the stack:

| Situation | Change |
|---|---|
| Single user, one machine | Keep current design |
| More than 1 concurrent user or heavy indexing | Add a Qdrant container behind `VectorStore` |
| Several users with accounts | Postgres and a real queue (Redis with RQ or Celery) |
| Remote server | Reverse proxy (Caddy) with HTTPS and auth |

## 12. Risks

| Risk | Mitigation |
|---|---|
| Scanned PDFs produce empty text | Detect low text yield per page; OCR with Tesseract |
| Tables get mangled | Docling for PDFs with tables |
| Hallucinated answers | Strict prompt, mandatory citations, eval set to catch regressions |
| Index and DB go out of sync | Single service layer plus a "verify index" command |
| Changing embedding model silently breaks search | Model name stored per collection; refuse mixed vectors |
| Reviewer has no GPU | Demo profile with small models and a demo video |

## 13. Interview talking points

| Topic | Be ready to explain |
|---|---|
| Retrieval | Why hybrid (vector + keyword with rank fusion) and what the eval numbers showed |
| Versioning | Content hashing, soft-active versions, rollback without re-embedding |
| Reindexing | Why a new embedding model needs a new collection; blue/green swap |
| Reproducibility | Each answer records the profile version it used |
| Trade-offs | Single-user SQLite and Chroma now; the exact path to Qdrant and Postgres |
| Failure handling | OCR for scans, the "not found" rule, job retries |
| Operability | Health checks, metrics, structured logs, backup and restore |

## Appendix A — `compose.yaml` (mode A)

```yaml
services:
  ollama:
    image: ollama/ollama:latest        # pin a version later
    volumes:
      - ollama_models:/root/.ollama
    ports:
      - "127.0.0.1:11434:11434"
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 15s
      timeout: 5s
      retries: 10
    # GPU (NVIDIA): uncomment
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]

  app:
    build: .
    environment:
      OLLAMA_BASE_URL: http://ollama:11434   # mode B: http://host.docker.internal:11434
      DATA_DIR: /data
      WATCH_POLLING: "true"
      WEB_CONCURRENCY: "1"
    volumes:
      - app_data:/data
      - ./inbox:/watch:ro                    # optional watched folder
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      ollama:
        condition: service_healthy

volumes:
  ollama_models:
  app_data:
```

## Appendix B — `Dockerfile`

```dockerfile
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist ./static
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
ENV DATA_DIR=/data HF_HOME=/data/hf
EXPOSE 8000
HEALTHCHECK --interval=30s CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
