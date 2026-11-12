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
