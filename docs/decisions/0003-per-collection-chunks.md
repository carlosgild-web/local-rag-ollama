# 0003 — Per-collection chunks and a real blue/green rebuild

## Context

PLAN.md section 5 says a change of embedding model or chunking builds a new
collection in the background, swaps it in, and keeps the old one until
confirmed. The first Phase 3 cut didn't do that:

- `create_collection` on an existing name turned off the old collection
  immediately, but documents and chunks still pointed at it, so the newly
  active collection served nothing.
- `chunks` had no collection link, so one version couldn't have chunks in
  two generations at once, and rebuilding meant deleting the live chunks.

Phase 2 retrieval and the CLI also still used the Phase 1 raw-sqlite3 store,
which declares its own `documents`/`chunks` tables and clashes with the ORM
schema in the same `app.db`.

## Decision

- Migration 0002 adds `chunks.collection_id` (backfilled from the owning
  document) and `ingest_jobs.result`.
- Blue/green is three service calls, run by one background job:
  `start_collection_rebuild` (new inactive generation), `build_collection`
  (re-chunk and re-embed **every** version of every document, so rollback
  still never re-embeds), `swap_collection` (activate, repoint documents,
  keep the old generation and its vectors).
- `create_collection` now refuses a name that already has an active
  collection; changing model or chunking goes through
  `POST /collections/{id}/reindex` with the new settings.
- Retrieval and the CLI use the ORM and versioning service. Only chunks of
  the active version, of non-trashed documents, in the requested collection
  are served. `ingest/sqlite_store.py` and `ingest/pipeline.py` are removed.

## Consequences

A Phase 1/2 `data/app.db` has the old raw schema and won't migrate. Delete
`data/app.db` and `data/chroma/` and re-ingest. Purging old generations
after a swap is left for a later phase (Phase 6, control panel).
