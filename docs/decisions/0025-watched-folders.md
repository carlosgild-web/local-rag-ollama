# 0025: Watched folders through the job queue, with watchdog

**Status:** accepted (2026-11-14)

## Context

Phase 6 asks for "watched folders with a `WATCH_POLLING` option": new and changed files in a folder are ingested by themselves. `PLAN.md` names `watchdog`, with polling in containers. The user approved adding the dependency, and chose (2026-11-14) that a file deleted from a folder is **only logged**: the document stays in the library.

## Decision

- **`watchdog>=6.0`** is the one new runtime dependency (pure Python, Apache-2.0).
  - By default it uses the operating system's file events.
  - With `WATCH_POLLING=true` it uses its `PollingObserver` (`WATCH_POLL_SECONDS`, default 5). Events don't cross Docker bind mounts or network drives, so `compose.yaml` turns polling on.
- **A file goes through the job queue like an upload.** The watcher thread never writes to the library (invariant 1). For each file, `watched.queue_file`:
  - ignores hidden, lock and partial files (`~$x.docx`, `.part`, `.crdownload`…) and unsupported types
  - skips empty files, and files over `MAX_UPLOAD_MB` (with a note on the folder)
  - hashes the file and skips it when that content is already a version, or already waiting in the queue
  - otherwise copies it to the staging area, checks the copy's hash, and queues an ordinary `ingest` job

  The usual rules then apply (invariant 3): the same content is skipped, the same name with new content becomes a new version, and every version is audited as an upload with the note "From watched folder …".
- **A file is queued once it stops changing.** After the last event, its size and time must stay the same across `WATCH_SETTLE_SECONDS` (default 2). A copy in progress therefore waits, and a file appears 2–4 s after it lands.
- **Document names:** files at the top level keep their file name. Files in subfolders keep the folder in the name (`policies/hr.pdf`), so two files with the same name stay two documents.
- **Catching up:** each folder is scanned once when the app starts (changes made while it was off), when the folder is added and when it is resumed, plus "Scan now" on the page.
- **Shelf:** the folder stores a collection id, and the live generation is found by name, so a blue/green swap keeps feeding the right shelf (invariant 4).
- **Folder rules:**
  - full paths only
  - **inside `WATCH_ROOTS` only.** It defaults to the user's home folder, and `compose.yaml` sets `/watch`. The path comes from whoever calls the API. Without a limit, anyone who can reach the API could make the app read any folder on the machine and then answer questions from its documents. The app only listens on localhost, but it has no login yet (Phase 8). CodeQL flagged this as `py/path-injection` on the first version of the PR. The check runs on the resolved real path (so `..` and links can't escape) before the folder is touched, and again when a folder is scanned or watched, in case `WATCH_ROOTS` changed since.
  - never inside `DATA_DIR`, and never containing it (that would feed the app its own files)
  - folders can't overlap, so no file is queued twice
- **Deleted files** are logged (`file removed from a watched folder; its document is kept`) and nothing else happens.
- **One thread**, started with the job worker. It isn't started by the CLI or in tests, where the page shows "Watcher off" and only "Scan now" works.
- **Audit:** `watch_add`, `watch_update` (pause, resume, subfolders, shelf) and `watch_remove`.
- **Storage:** migration 0010, `watched_folders`.
- **Docker:** `compose.yaml` mounts `./inbox` read-only at `/watch`, and `inbox/` is gitignored.

## Consequences

- A big folder is hashed in full at every start. That's fine for documents, the target here, and the price of not tracking each file in the database.
- Mirroring deletions isn't supported. If it's ever wanted, it would be a per-folder option that moves documents to the trash (soft delete, audited), so it can be undone.
