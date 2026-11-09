# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow the phases in [PLAN.md](PLAN.md).

## [Unreleased]

## [0.5.0] - 2026-11-09

UI improvements for non-technical users, from the `feature/ui-improvements` branch. Some items came forward from later phases ([decision 0008](docs/decisions/0008-ui-improvements-scope.md)).

### Added

- **Suggested shelves and tags** ([decision 0009](docs/decisions/0009-suggested-shelves-and-tags.md)):
  - Drop files or a folder and the app analyses each document. For each file it suggests an existing shelf, or a new one with a name, plus tags: department, kind, quarter and year, folder.
  - You review, rename, move, retag or leave files out, then confirm.
  - Nothing is indexed before you confirm.
  - New endpoints: `POST /api/intake`, `GET`, `POST …/confirm` and `DELETE /api/intake/{id}`; new job type `analyze_intake`.
- **Review before processing:** `POST /api/documents/check` and `GET /api/documents/upload-rules`. Each file shows whether it is new, a new version (v1 → v2), already in the library, in the trash, or unreadable.
- **Troubleshooter:**
  - `GET /api/diagnostics` runs checks on Ollama (reachable, version, models installed and in the right role, free memory), SQLite (integrity, migrations, FTS, disk), the vector store (in step with the database) and the job worker. Each check gives a cause, a fix and action buttons.
  - `SIMULATE_FAULTS` reproduces each failure, for developers.
- **A broken system is impossible to miss:**
  - a status bar and status pill on every page, plus a warning bar for problems such as low memory
  - controls that can't work are paused, with the reason
  - toasts when the status changes, the state in the tab title, and opt-in desktop notifications
- **Simulated L2 support ticket:** a ServiceNow-style incident draft with environment details, failed checks, priority and the user's notes. Submitting saves a numbered INC record under `DATA_DIR/support/`; nothing is sent. `SUPPORT_COMPUTER_NAME` and `SUPPORT_USER_NAME` show a demo identity instead of the real one.
- **Restore from trash:** `POST /api/documents/{id}/restore`. It is refused if the name was reused on that shelf.
- **Citation passage viewer:** `GET /api/chunks/{id}`. Clicking a source or a `[n]` chip shows the exact passage.
- **Queue:** jobs show what they are about (file or shelf), and why a file was skipped.
- **Collections in plain language:** tooltips, presets (Short facts / Balanced / Long text), a guide for unusual values, and a confirmation before Create, Rebuild and Reindex.
- **Showcase:** a README with screenshots and an architecture diagram, plus a slide deck in `docs/showcase/`.
- **End-to-end kit:** a `ui_endpoints` phase, and a restore check.

### Changed

- The Library no longer asks for a shelf and tags before upload; the suggestions replace them.
- Error boundaries keep one broken panel from blanking the whole page.

## [0.4.0] - 2026-11-06

Phase 4: the web UI and Docker. The app was also tested end to end, and every finding was fixed ([test report](docs/test-reports/2026-11-06-e2e.md)).

### Added

- **Web UI** (React, Vite, TypeScript, Tailwind, shadcn/ui-style components, TanStack Query):
  - Dashboard: health, counts, active model, recent jobs
  - Library: drag-and-drop upload with shelf and tags, search, tag filter, trash view, reindex
  - Collections: create, reindex, change settings with a blue/green rebuild, plain-language help
  - Queue: live progress, cancel and retry
  - Chat: streamed answers, citation chips linked to the sources, session history, feedback
- **FastAPI serves the built UI**, and page URLs survive a browser refresh.
- **Docker:**
  - one app image, plus `compose.yaml` with Ollama in its own container
  - `compose.host-ollama.yaml` to use the Ollama already on your machine
  - healthchecks, named volumes, one worker
- **GitHub Actions:** ruff, pytest, the frontend build and `docker build` on every push.
- **End-to-end test kit** (`e2e/`):
  - 11 fictional sample documents and a scenario of about 60 questions
  - checks for versions, rollback, trash, jobs, reindex and rebuild, prompt injection and restart recovery
  - Markdown reports with server-log excerpts
- **Citations:**
  - a one-line citation hint in the prompt
  - a `citation_status` on every answer (`ok` / `missing` / `invalid`)
  - a UI warning when citations can't be checked ([decision 0007](docs/decisions/0007-citation-reminder-and-check.md))
- **Model capabilities:** `GET /api/models` reports each model's capabilities (`embedding`, `completion`, …).
- **Chat sessions remember their shelf** (migration 0004).
- **This README and changelog.**

### Fixed

- **Word files:** paragraphs without a style no longer crash ingestion, and tables are now read.
- **Reindexing a document that a chat answer cites** no longer fails: cited chunks are retired instead of deleted, and purge unlinks them ([decision 0006](docs/decisions/0006-retire-cited-chunks.md), migration 0003).
- **Cancelling a job:**
  - a Cancel can no longer be lost to the job worker
  - Cancel answers in about 0.3 s instead of 9–12 s, because indexing no longer holds the SQLite write lock while embedding
  - a cancelled upload leaves nothing behind
- **Chat:**
  - the shelf picker no longer resets after a refresh
  - questions never create an empty "default" shelf
  - retired shelf copies are refused
  - a stopped answer stays on screen
- **Ollama errors** show their reason (for example "not enough free memory") instead of a bare HTTP 500.
- **Empty files** are refused: a 0-byte upload gets a 422, and a file with no text fails its job with a reason.
- **PDF chunks** never span a page break, so citations name the right page.
- **The "Change" form** offers only embedding models, each listed once.
- **API timestamps** are marked as UTC.
- **Swagger "Try it out"** works for upload and chat.

### Changed

- **The chat model on low-RAM machines** is `qwen2.5:3b`; the repo default stays `llama3.1` ([decision 0004](docs/decisions/0004-small-chat-model-on-low-ram.md)).
- **Docker build:** Node 22 instead of 20, among other Phase 4 details ([decision 0005](docs/decisions/0005-phase4-docker-and-ui-details.md)).
- **The branch** was renamed from `master` to `main`.

### Known issues

- **Model quality with the 3B model** (see the test report):
  - two FAQ questions are wrongly answered "not found"
  - one answer mixed up two price tables
  - about 1 in 5 citations still point to the wrong document
- **Follow-up questions** are answered on their own; earlier turns are not used.
- **Restore from trash** isn't in the API yet (Phase 5).

## [0.3.0] - 2026-11-05

Phases 0–3: setup, the ingestion core, retrieval with cited answers, and the backend API:
- the job worker
- SSE chat
- `/health`
- JSON logs with request ids
- per-collection chunks with blue/green rebuilds ([decision 0003](docs/decisions/0003-per-collection-chunks.md))
