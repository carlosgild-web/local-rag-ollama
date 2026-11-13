# 0018: Emptying the 30-day trash

**Status:** accepted (2026-11-13)

## Context

Invariant 3 says deletes are soft, with a 30-day trash, and the Library says "Deleted documents stay here for 30 days". `service.purge_expired_trash()` existed and was tested, but nothing called it, so documents stayed in the trash forever. There was no way to delete one permanently, either.

## Decision

- **The 30-day purge runs at app start**, as the daily backup does (decision 0015). When a document has been in the trash for over 30 days and no purge is waiting, the start queues a `purge_trash` job. The backup is queued first, so the newest automatic backup still holds what the purge removes.
- **Delete permanently**: `POST /api/documents/{id}/purge` queues a `purge_document` job. It returns 409 for a document that isn't in the trash, so nothing skips the trash. The Trash view has the button, behind a confirmation that says it cannot be undone.
- Both run in the job worker, because purging deletes vectors and the worker is the only writer to the vector store.
- Both share one helper. It removes the document, its versions, chunks, FTS rows and vectors, and the answer-source links to them (the answers keep their text). Each document purged writes a `purge` audit entry with its filename, since the document row is gone.
- The original files in `DATA_DIR/files/` stay. They're content-addressed, so another document or version can share the same file.

## Consequences

- An app left running for weeks purges at its next start, not exactly on day 30. The Trash view says "removed after ‹date›".
- Purged documents can only come back from a backup.
