# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow the phases in [PLAN.md](PLAN.md).

## [Unreleased]

### Added

- **Load the demo company from the console.** On an empty library the dashboard offers *Load the demo company*, with a progress bar and links to the website and the intranet when it's done. It runs as a `seed_demo` job (`POST /api/demo/seed`, `GET /api/demo`), through the same service as `app.cli seed-demo`, and is audited. `compose.yaml` takes `APP_PORT` for when port 8000 is taken.
- **[Getting started](GETTING_STARTED.md):** a step-by-step guide covering three ways to start, the demo, a tour with screenshots, the tests and troubleshooting. It's also a web page for GitHub Pages (`docs/getting-started.html`), next to a landing page (`docs/index.html`).
- **Ready-made Docker image:** `.github/workflows/release-image.yml` publishes `ghcr.io/carlosgild-web/local-rag-ollama` on version tags. `compose.yaml` pulls it, and builds from source with `--build` or when no image is published yet. Checked by hand on 2026-11-09:
  - the fallback build, the health check and the non-root user
  - `seed-demo` in the container
  - data kept across a restart
  - `CHAT_MODEL`
  - all pages
  - Luna answering in English and Spanish with citations
- **Reviewer walkthrough** ([docs/walkthrough.md](docs/walkthrough.md)): a 10-minute tour from the company's website through the intranet and Luna to the admin console, with screenshots.
- New showcase screenshots of the public site, staff sign-in, demo guide, Luna's sources, the dashboard and the portal switch, plus a contact sheet of the product renders and a GitHub social preview image (`docs/showcase/social-preview.png`).

### Tested

- **End-to-end run on v0.6.0** ([report](docs/test-reports/2026-11-09-e2e.md)):
  - 53/53 must-pass checks, 53/57 answer checks, 31/38 citations correct and 7/7 refusals
  - the restart check passed
  - a new Luna check through the employee portal passed 6/6, in English and Spanish, including a not-found
  - it found the Chroma read bug fixed below

### Security

- `SECURITY.md`: the project's scope (a local demo with no authentication by design), how the code protects itself, and private vulnerability reporting.
- CI runs with read-only permissions (`permissions: contents: read`), and `.github/dependabot.yml` proposes weekly grouped updates for pip, npm and GitHub Actions.
- Chroma's anonymized telemetry is turned off explicitly, with a test, so no future Chroma version can make a network call. It was already a no-op in chromadb 1.5.9.
- `pip-audit` flags chromadb 1.5.9 for four advisories, all in Chroma's HTTP server, which this app never starts. See `SECURITY.md`.

### Changed

- **The website's photos are now made with Google Gemini** ([decision 0012](docs/decisions/0012-site-images-with-gemini.md), [how](docs/site-images.md)). All 19 site photos (the hero necklace, 15 products, two collection banners and the workshop). Each product photo starts from its Blender render, now kept as a reference in `art/blender/`, so colors and shapes match the catalog. The prompts are in `scripts/gemini_jobs.json`, and `scripts/gemini_images.py` can print them, make a prompt sheet for the Gemini app, or call the API when a key has image quota.
- README: CI and license badges, a stack line, and the slide deck linked on GitHub Pages.
- Slide deck: v0.6.0, two new slides (the demo company, and Luna), and 179 tests.

### Fixed

- **`docker compose up` failed when Ollama was already installed on the computer**, with "ports are not available: … 11434". The Ollama container no longer publishes port 11434 on the host; the app reaches it on Compose's own network. Found by testing from a fresh clone.
- **Reads right after a large write could fail.** Chroma 1.5.x sometimes failed reads of a collection with "Error creating hnsw segment reader: Nothing found on disk" until its index was flushed. The end-to-end run on 2026-11-09 hit it while analysing a dropped folder right after an upload. The Chroma store now retries vector reads (search and `get_vectors`) on that error only, for up to about 15 seconds, with tests.
- Luna showed the question twice while answering. The admin chat's check now lives in `useChatStream` and both use it.
- The demo guide promised a version-rollback screen that the console doesn't have yet. Rollback is in the API; the guide now suggests uploading a new version instead.
- The demo guide's strip on the site fits on one line.

## [0.6.0] - 2026-11-09

The employee portal, from the `feature/employee-portal` branch ([decision 0010](docs/decisions/0010-employee-portal.md)).

### Added

- **Employee portal** at `/intranet`: the intranet of *Hilda & Luna Beadworks*, a fictional company, with its own bead-moon logo, self-hosted fonts and an ES/EN switch.
  - Home page with a dated season timeline, handbook highlights, department hours, a company snapshot and news, written from the demo documents. Every card can ask Luna about it.
  - **Luna**, the assistant, as a floating chat bubble on every portal page and full screen at `/intranet/luna`, sharing one conversation and one stream. It has suggested questions, citations with the exact passage, 👍/👎 feedback, a friendly "not found" message, and recent conversations kept in the browser.
- **Multi-shelf retrieval:** `retrieve_many` searches several shelves. Shelves that share an embedding model are ranked together by similarity, keyword search runs once over all of them, and RRF fuses the lists. Models are never mixed. The single-shelf `retrieve` now calls it with one shelf, with the same results as before.
- **Portal visibility per shelf:** `collections.portal_visible` (default on), a switch on each shelf in Collections, and `PATCH /api/collections/{id}`. Audited as `collection_portal_visibility`; a blue/green swap keeps the setting.
- **Chat channels:** `chat_sessions.channel` (`admin` or `intranet`). `POST /api/chat` takes `channel` and `answer_language` (`en` or `es`, which adds one prompt rule). `GET /api/sessions?channel=` defaults to `admin`.
- **Dashboard:** an *Employee portal* button, an *Employee questions* card, and a sidebar link.
- **`python -m app.cli seed-demo`** loads the 11 fictional documents in `backend/demo/hilda-luna/`, one shelf per folder. Running it again skips every file.
- Migration `0005_portal`.
- **Public company website** at `/site` ([decision 0011](docs/decisions/0011-public-site.md)): the outside face of Hilda & Luna Beadworks, in warm Amber Hollow colors with the same logo, fonts and ES/EN switch.
  - Home: collection banners (Amber Hollow, Coastal Garden), shop-by tiles, customer favorites, the workshop's story, a wholesale band and a newsletter.
  - Catalog (glass beads, charms, findings, with retail prices and nickel notes), Wholesale (tiers, how to apply, custom colors, starter sets) and Help (shipping, returns, damaged items, FAQ, contact).
  - Written only from the customer-facing demo documents. Beads, charms and findings are drawn in SVG, and the forms are demos that send and store nothing.
  - **Product photos rendered in Blender** by `scripts/render_site_art.py` (beads, charms, findings, starter set, hero necklace), and slots for three AI-generated scene photos prepared by `scripts/prepare_site_photos.py` ([docs/site-images.md](docs/site-images.md)). Any missing image falls back to its SVG drawing.
  - **Employee login** opens `/site/staff`, a simulated staff sign-in with one *Enter as demo employee* button into `/intranet`.
  - Links between the site, the intranet and the console: a *Company site* button on the dashboard and a sidebar link.
- **Reviewer's demo guide**, marked as not part of the company design: a strip on the public site, a banner on the intranet with *How this demo works* (a side panel with the path and things to try) and *Open the RAG admin console*. It can collapse to a *Demo guide* pill.

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
