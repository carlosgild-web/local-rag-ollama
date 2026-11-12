# 0015: Backup and restore

**Status:** accepted (2026-11-12)

## Context

There was no way to back up or restore the app's data (PLAN.md Phase 8). The only option was to stop the app and copy the data folder by hand, which isn't easy with Docker volumes. A tester asked for both.

## Decision

- **One zip per backup** in `DATA_DIR/backups/`:
  - `manifest.json`: app version, schema revision, embedding models, counts, and the reason (`manual`, `auto` or `before-restore`)
  - `app.db`: from SQLite's online backup API, so the snapshot is consistent while the app runs
  - `chroma/`: the vector store
  - `files/`: the original uploads
- **Made by the job worker** (job type `backup`). It's the only writer to the vector store, so no indexing changes it while it's copied. *Back up now* on the console's **Backups** page and `POST /api/backups` queue it. In the copy, backup jobs are marked done, so a restored app doesn't rerun the backup that made it.
- **Automatic daily backup**: on start, when the newest automatic backup is a day old or missing and the library isn't empty. The newest `BACKUP_KEEP` (default 7, `0` turns it off) are kept. Manual backups are kept until deleted.
- **Restore is offline**, because embedded SQLite and Chroma are single-writer:
  - `.\start.cmd restore <name|file>` / `./start.sh restore …` stops the app, runs `python -m app.cli restore`, and starts the app again (in Docker, through a one-off app container on the data volume)
  - the restore checks the zip (manifest, no unexpected entries, schema not newer than the app) and **backs up the current data first** (`before-restore`)
  - it swaps the data in, putting the old data back if a step fails, then upgrades an older schema; it's audited
- **"Is the app running?"** The job worker writes a heartbeat file (`DATA_DIR/app.alive`) every 10 s and removes it on shutdown. A restore refuses while it's fresher than 30 s (`--force` overrides). A process check isn't used: on Windows, `os.kill(pid, 0)` terminates the process.
- **The console** lists backups (date, kind, contents, size) with download and delete, and shows the restore command for each. It doesn't restore from the browser, since the server would have to stop itself mid-request.

## Consequences

- Backups live on the same disk as the data, so they protect against mistakes, not disk failure. The page says so and offers a download.
- A snapshot taken while an upload is being indexed can contain that ingest job as running. After a restore it re-runs and fails cleanly if its staged file is gone. Backups made while the app is idle don't have this.
- `__version__` in `app/__init__.py` is now the single app version, used by the API and the manifest (it had been left at 0.6.0).
