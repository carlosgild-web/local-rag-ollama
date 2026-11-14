# 0028: An active-version pointer, not re-indexing, for rollback

**Status:** accepted (Phase 1, written down 2026-11-14)

## Context

Documents change: a handbook gets a new edition, a price list is corrected. The app must answer from the current text, show what changed, and go back to an earlier version when an edit was wrong (invariant 3). On a laptop CPU, embedding a 100-page document takes minutes, so going back must not mean embedding it again.

## Decision

- **Every version is indexed once and kept.** A new file is stored under its SHA-256 (`DATA_DIR/files/<sha256>.<ext>`). If that hash is already in the library, it's a duplicate and is skipped. A known filename with a new hash becomes a new `document_version`, chunked and embedded like any other. The old version's chunks and vectors stay where they are.
- **`documents.active_version_id` says which version answers.** Rollback (`versioning/service.py: rollback_document`) sets that pointer, writes an `audit_log` row and commits. It touches no chunk, vector or file. In the API it's `POST /documents/{id}/rollback`.
- **Retrieval filters on the pointer.** Chroma can't express "chunk of the document's active version", which changes without touching the vectors. So vector search fetches 3× the candidates, and SQLite keeps only the chunks of active versions of documents that aren't in the trash, in the shelf searched (`retrieval/retrieve.py`). Keyword search (FTS5) joins on the same condition.
- **The pointer is a plain column**, not a foreign key, to avoid a circular reference between `documents` and `document_versions`. The service layer is the only writer and checks that the version belongs to the document. `test_rollback_rejects_version_from_another_document` covers that.

## Consequences

- Rollback is instant and can't fail halfway. `test_rollback_flips_pointer_without_reembedding` checks that the embedding client isn't called.
- Old answers stay reproducible. `message_sources` points at chunks of the version that answered, and those chunks never go away while the document exists (invariant 5).
- Storage grows with every version: each one keeps its file, chunks and vectors. For text documents that's small. Deleting goes through the 30-day trash, and only purging removes vectors ([0018](0018-trash-purge.md)).
- Retrieval over-fetches. With many versions per document, the 3× margin could run short. The inspector shows the vector candidates if that ever happens.

## Alternatives considered

- **Re-embed on rollback:** simple data, but minutes of CPU for every undo.
- **Delete old vectors and keep only the files:** smaller, but rollback becomes re-embedding, and old answers lose their sources.
- **An `active` flag on each chunk:** rollback would update every chunk of two versions, in SQLite and in Chroma's metadata, and the two could drift apart. One pointer can't drift.
