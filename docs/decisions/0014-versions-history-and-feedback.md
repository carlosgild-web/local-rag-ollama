# 0014: Versions, history and feedback in the console (Phase 5, part A)

**Status:** accepted (2026-11-12)

## Context

Testing from a fresh clone raised questions the console couldn't answer:
- What text is the app actually searching?
- What changed between two versions?
- How do I go back to the previous one?
- Why didn't the date change after I uploaded a new version?

The backend already had version listing, a text diff and rollback (Phase 3), but no screen used them. The 👍/👎 ratings were stored but shown nowhere, and the chat history couldn't be searched.

## Decision

- **A document details panel.** Clicking a file name in the Library opens a side panel:
  - **Content**: the extracted text of any version (`GET /documents/{id}/versions/{vid}/text`), next to *Original*
  - **Versions**: a timeline (active marked, date, type, passages, note) with *View text*, *Compare with the previous version* and *Restore this version*
  - **Compare**: any two versions, shown as a colored line diff (from the existing `diff_versions()`)
- **Restore stays a rollback**, as PLAN.md section 5 says: it only switches the active version. Nothing is re-embedded or deleted, and it's audited.
- **`documents.updated_at`** (migration 0006) records the last change to a document's content: a new version or a restore. Existing rows get their newest version's date. The Library shows *Updated* next to *Added* and can sort by it. `created_at` keeps meaning "first added".
- **Ratings become useful:**
  - after 👎, an optional *What was wrong?* note (the existing `comment` field), in Chat and in Luna
  - the dashboard's **Answer feedback** card shows the helpful % and the latest "not helpful" answers, with the question, the note, the cited files and a link to the conversation (`GET /feedback/summary`)
- **Chat history search:** `GET /sessions?q=` matches the title or any message text (SQL `LIKE`), with a search box above the Chat list.

## Consequences

- Phase 5 items done: version timeline, text diff and rollback in the UI, and chat history search.
- Still to come, in separate PRs:
  - a near-duplicate warning when adding files ("almost the same as …")
  - a quick text editor that saves a new version with who, when and a note
  - backup and restore
- `updated_at` doesn't change on tag edits or moves to the trash: it tracks content, which is what "last edited" means for a document.
- Search is a plain substring match. It's enough for a local, single-user history; full-text search over chats can reuse FTS5 later if needed.

## Addendum (2026-11-12): near-duplicates under another name (part B)

**Problem:** a file with almost the same text as a document already in the library, but another name, was indexed as a second document. For example, "customer support_2.txt" with one email changed. Exact-hash duplicates and same-name versions were caught; this wasn't. Both copies were then searchable, so an answer could quote the old email.

**Decision:**
- **Detection.** While adding files, the intake compares each new file's text with the active text of every document, **word by word** (`difflib.SequenceMatcher` on word lists). A length check and `quick_ratio()` rule out most pairs cheaply first. At **90% or more** the same, the file is flagged "Almost the same as 'X' (97% the same text)" and suggested for X's shelf. A same-name file keeps the existing rule (a new version), so it's never flagged.
- **Choice.** The review offers *Make it a new version of X* (default), *Keep both*, or *Skip*, and *See the differences* (`GET /intake/{batch}/files/{key}/diff`, the same colored view as Compare).
- **Merging.** The ingest job gets the target document (`document_id`). `ingest_document(into_document_id=…)` adds the version to that document, keeps its name, and notes *"Uploaded as 'customer support_2.txt'"*. The note shows in the version timeline, and the upload is audited. Invariants 1 and 3 hold: it goes through the service, and the old version stays.

**Consequences:**
- The comparison is in-process and uncached. On a laptop that's fine for hundreds of documents. With thousands, it would need the embeddings (already computed) to pick a few candidates first.
- 90% is a starting threshold. A file that only shares a long boilerplate section with another (for example, two contracts from one template) can be flagged. The user then chooses *Keep both*.

