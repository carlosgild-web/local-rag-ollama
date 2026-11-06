# 0005: Phase 4 Docker and UI details

**Status:** accepted (2026-11-06)

Small departures from PLAN.md appendices A and B, and two dependencies.

## Docker

- **Node 22, not Node 20, for the web build stage.** Vite 8 needs Node
  20.19+ or 22.12+, and Node 20 reached end of life in April 2026.
- **`compose.host-ollama.yaml` added for mode B.** Use it with
  `docker compose -f compose.yaml -f compose.host-ollama.yaml up`. It points
  the app at `host.docker.internal:11434`, leaves the Ollama container out,
  and drops the `depends_on`. Appendix A only mentioned mode B in a comment.
- **The `./inbox:/watch:ro` mount is commented out until Phase 6.** Nothing
  reads it yet, and Docker would create an empty `inbox/` folder in the repo.
- **`CHAT_MODEL` and `EMBEDDING_MODEL` pass through from the host**
  (`CHAT_MODEL=qwen2.5:3b docker compose up`), with defaults `llama3.1` and
  `bge-m3`. See [0004](0004-small-chat-model-on-low-ram.md).
- **The healthcheck has a timeout and a start period** of 5s and 30s. This
  covers migrations and Chroma opening on the first start.

## Frontend

- **`react-router-dom` (page URLs) and `react-markdown` (formatted answers)**
  were added with approval. They are not in the CLAUDE.md stack.
- **shadcn/ui components are written in `src/components/ui/` by hand**
  (button, card, badge, input, progress), following shadcn's
  copy-the-source model. Only `@radix-ui/react-slot` comes from Radix. The
  shadcn CLI is not needed to build.
- **Chat streams with `fetch` and a small SSE parser** (`src/api/sse.ts`),
  because `EventSource` only does GET and `POST /api/chat` takes a body.
- **Citations open nothing yet.** Clicking `[n]` highlights the matching
  source (file, page, score). Showing the chunk text is the Phase 6
  retrieval inspector.
