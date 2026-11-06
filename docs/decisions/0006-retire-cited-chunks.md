# 0006: Retire cited chunks instead of deleting them

**Status:** accepted (2026-11-06)

## Context

An in-place reindex (of one document or a whole collection) deleted every
old chunk of the active version and wrote new ones. Saved answers point at
their chunks in `message_sources` (invariant 5), so once a document had been
cited in a chat, SQLite refused the delete (`FOREIGN KEY constraint failed`)
and the reindex job failed. Purging trash after 30 days had the same flaw.

## Decision

- `chunks.retired_at` (migration 0003). On reindex, chunks no answer cites
  are deleted as before. Cited chunks are removed from Chroma and FTS and
  stamped `retired_at`. They are never retrieved again, but old answers keep
  showing their exact sources.
- Retrieval and the per-version chunk counts ignore retired chunks.
- Purge is the deliberate permanent delete. It removes the document's
  chunks, retired ones included, and the `message_sources` rows pointing at
  them. The answer text stays, and the audit entry records how many source
  links were removed.

## Consequences

- Retired chunks accumulate as documents that have been chatted about get
  reindexed. They are small text rows. A future cleanup could drop the ones
  whose answers were deleted.
- SQLite may reuse ids of deleted (never cited) chunks. This is safe,
  because nothing referenced them.
