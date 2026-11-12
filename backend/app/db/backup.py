"""Backups of everything the app keeps, and restoring one (decision 0015).

A backup is one zip in DATA_DIR/backups:
  manifest.json   app version, schema revision, embedding models, counts, reason
  app.db          the SQLite database, from SQLite's online backup API
  chroma/         the vector store
  files/          the original uploaded files

Backups are made by the job worker (job type "backup"), so no indexing runs while the
vector store is copied. Restoring is offline: the app must be stopped, because the
embedded SQLite and Chroma have a single writer. `restore_backup` refuses while the
app's heartbeat is fresh, backs up the current state first, then swaps the data in.
"""

import datetime as dt
import json
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from app import __version__
from app.core.config import Settings

NAME = re.compile(r"^backup-\d{8}-\d{6}(-[a-z][a-z-]*)?\.zip$")
HEARTBEAT = "app.alive"  # written by the running app's job worker
HEARTBEAT_FRESH_SECONDS = 30
FOLDERS = ("chroma", "files")


class BackupError(Exception):
    """A backup can't be made or restored; the message says why."""


# --- the running app's heartbeat ---------------------------------------------


def write_heartbeat(settings: Settings) -> None:
    (settings.data_dir / HEARTBEAT).write_text(str(time.time()), encoding="ascii")


def clear_heartbeat(settings: Settings) -> None:
    (settings.data_dir / HEARTBEAT).unlink(missing_ok=True)


def app_is_running(settings: Settings) -> bool:
    try:
        beat = float((settings.data_dir / HEARTBEAT).read_text(encoding="ascii"))
    except (OSError, ValueError):
        return False
    return time.time() - beat < HEARTBEAT_FRESH_SECONDS


# --- making and listing backups --------------------------------------------------


def backup_path(settings: Settings, name: str) -> Path:
    if not NAME.match(name):
        raise BackupError(f"{name!r} isn't a backup name")
    path = settings.backups_dir / name
    if not path.is_file():
        raise BackupError(f"backup {name!r} not found")
    return path


def _manifest(db_copy: Path, reason: str) -> dict:
    con = sqlite3.connect(db_copy)
    try:

        def one(sql: str):
            try:
                return con.execute(sql).fetchone()[0]
            except sqlite3.Error:
                return None

        models = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT embedding_model FROM collections WHERE is_active = 1"
            )
        ]
        return {
            "app_version": __version__,
            "schema_revision": one("SELECT version_num FROM alembic_version"),
            "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "reason": reason,
            "embedding_models": models,
            "counts": {
                "documents": one("SELECT COUNT(*) FROM documents WHERE trashed_at IS NULL"),
                "versions": one("SELECT COUNT(*) FROM document_versions"),
                "shelves": one("SELECT COUNT(*) FROM collections WHERE is_active = 1"),
                "chats": one("SELECT COUNT(*) FROM chat_sessions"),
            },
        }
    finally:
        con.close()


def create_backup(settings: Settings, *, reason: str = "manual") -> Path:
    """Writes a backup zip and returns its path. Call it from the job worker (or with
    the app stopped) so nothing writes to the vector store meanwhile."""
    if not settings.db_path.is_file():
        raise BackupError("there is no database to back up yet")
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    name = f"backup-{stamp}{'' if reason == 'manual' else '-' + reason}.zip"
    target = settings.backups_dir / name
    part = target.with_suffix(".zip.part")
    with tempfile.TemporaryDirectory(dir=settings.backups_dir) as tmp:
        db_copy = Path(tmp) / "app.db"
        source = sqlite3.connect(settings.db_path)
        copy = sqlite3.connect(db_copy)
        try:
            source.backup(copy)  # a consistent snapshot, even while the app runs
            # The snapshot is taken while this backup's own job is running. Mark backup
            # jobs done in the copy, or a restored app would rerun them as interrupted.
            copy.execute(
                "UPDATE ingest_jobs SET status = 'completed', progress = 1.0 "
                "WHERE job_type = 'backup' AND status IN ('pending', 'running')"
            )
            copy.commit()
        finally:
            copy.close()
            source.close()
        manifest = _manifest(db_copy, reason)
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.write(db_copy, "app.db")
            for folder in FOLDERS:
                root = settings.data_dir / folder
                if not root.is_dir():
                    continue
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        zf.write(path, f"{folder}/{path.relative_to(root).as_posix()}")
    part.replace(target)
    return target


def read_manifest(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as zf:
            return json.loads(zf.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise BackupError(f"{path.name} isn't a backup made by this app ({exc})") from exc


def list_backups(settings: Settings) -> list[dict]:
    """Newest first. A damaged file is listed with its error instead of a manifest."""
    if not settings.backups_dir.is_dir():
        return []
    out = []
    for path in settings.backups_dir.iterdir():
        if not NAME.match(path.name):
            continue
        item = {"name": path.name, "size": path.stat().st_size, "manifest": None, "error": None}
        try:
            item["manifest"] = read_manifest(path)
        except BackupError as exc:
            item["error"] = str(exc)
        out.append(item)
    return sorted(out, key=lambda b: b["name"][7:22], reverse=True)


def delete_backup(settings: Settings, name: str) -> None:
    backup_path(settings, name).unlink()


def prune_automatic(settings: Settings, keep: int) -> list[str]:
    """Keeps the newest `keep` automatic backups; returns the names removed."""
    autos = [b["name"] for b in list_backups(settings) if b["name"].endswith("-auto.zip")]
    removed = autos[keep:]
    for name in removed:
        (settings.backups_dir / name).unlink(missing_ok=True)
    return removed


def latest_automatic_age_hours(settings: Settings) -> float | None:
    autos = [b for b in list_backups(settings) if b["name"].endswith("-auto.zip")]
    if not autos:
        return None
    newest = dt.datetime.strptime(autos[0]["name"][7:22], "%Y%m%d-%H%M%S").replace(tzinfo=dt.UTC)
    return (dt.datetime.now(dt.UTC) - newest).total_seconds() / 3600


# --- restoring ------------------------------------------------------------------------------


def _check_zip(path: Path, known_revisions: set[str]) -> dict:
    manifest = read_manifest(path)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        bad = zf.testzip()
    if bad is not None:
        raise BackupError(f"{path.name} is damaged (first bad file: {bad})")
    if "app.db" not in names:
        raise BackupError(f"{path.name} has no database in it")
    for name in names:
        top = name.split("/", 1)[0]
        if (
            name.startswith("/")
            or ".." in name.split("/")
            or top not in (*FOLDERS, "app.db", "manifest.json")
        ):
            raise BackupError(f"{path.name} contains an unexpected entry: {name!r}")
    revision = manifest.get("schema_revision")
    if revision and known_revisions and revision not in known_revisions:
        raise BackupError(
            f"{path.name} was made by a newer version of the app (schema {revision}); "
            "update the app first, then restore it"
        )
    return manifest


def restore_backup(
    settings: Settings, path: Path, *, known_revisions: set[str], force: bool = False
) -> dict:
    """Replaces the database, vectors and files with the backup's. The current state is
    backed up first (reason "before-restore"). Returns the restored backup's manifest
    and the name of that safety backup."""
    if app_is_running(settings) and not force:
        raise BackupError(
            "the app is running: stop it first (.\\start.cmd stop or ./start.sh stop), then restore"
        )
    manifest = _check_zip(path, known_revisions)
    safety = None
    if settings.db_path.is_file():
        safety = create_backup(settings, reason="before-restore").name

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    staging = settings.data_dir / f".restore-{stamp}"
    replaced = settings.data_dir / f".replaced-{stamp}"
    with zipfile.ZipFile(path) as zf:
        zf.extractall(staging)
    replaced.mkdir()
    moved: list[str] = []
    targets = ["app.db", *FOLDERS]
    try:
        for name in targets:
            current = settings.data_dir / name
            if current.exists():
                shutil.move(str(current), replaced / name)
                moved.append(name)
        for extra in ("app.db-wal", "app.db-shm"):  # belong to the old database
            (settings.data_dir / extra).unlink(missing_ok=True)
        for name in targets:
            source = staging / name
            if source.exists():
                shutil.move(str(source), settings.data_dir / name)
            elif name in FOLDERS:
                (settings.data_dir / name).mkdir()
    except Exception:
        for name in targets:  # put the previous data back as it was
            if (settings.data_dir / name).exists() and name in moved:
                target = settings.data_dir / name
                shutil.rmtree(target) if target.is_dir() else target.unlink()
        for name in moved:
            shutil.move(str(replaced / name), settings.data_dir / name)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(replaced, ignore_errors=True)
    return {"restored": manifest, "safety_backup": safety}
