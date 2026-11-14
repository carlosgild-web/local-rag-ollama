"""Watched folders (PLAN.md Phase 6, decision 0025): the service layer.

A watched folder feeds one shelf. A new or changed supported file in it is
copied to the upload staging area and queued as an ordinary ingest job, so
the usual rules apply (invariant 3): the same content is skipped as a
duplicate, the same name with new content becomes a new version. A file
deleted from the folder is only logged; the document stays (the user's
choice, 2026-11-14).

The watcher thread (app/ingest/watcher.py) only calls `queue_file` and
`scan_folder`; every write goes through here (invariant 1).
"""

import hashlib
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Collection, DocumentVersion, IngestJob, WatchedFolder, utcnow
from app.ingest.parsers import SUPPORTED_EXTENSIONS
from app.jobs import queue
from app.versioning.service import ConflictError, NotFoundError, get_collection, record_audit

log = logging.getLogger(__name__)

# Editors and browsers write these while a file is being saved or downloaded.
_TEMP_SUFFIXES = {".tmp", ".part", ".crdownload", ".partial", ".swp", ".download"}


class InvalidWatchedFolderError(ValueError):
    pass


def _norm(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def is_candidate(path: Path) -> bool:
    """A supported document, not a hidden, lock or partial file."""
    name = path.name
    if name.startswith((".", "~$", "~")) or path.suffix.lower() in _TEMP_SUFFIXES:
        return False
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


# --- Configuration ---------------------------------------------------------------


def list_folders(db: Session) -> list[WatchedFolder]:
    return list(db.execute(select(WatchedFolder).order_by(WatchedFolder.path)).scalars())


def get_folder(db: Session, folder_id: int) -> WatchedFolder:
    folder = db.get(WatchedFolder, folder_id)
    if folder is None:
        raise NotFoundError(f"watched folder {folder_id} not found")
    return folder


def shelf_of(db: Session, folder: WatchedFolder) -> Collection:
    """The live generation of the folder's shelf (blue/green swaps change ids)."""
    collection = folder.collection
    if collection.is_active:
        return collection
    live = db.execute(
        select(Collection).where(Collection.name == collection.name, Collection.is_active.is_(True))
    ).scalar_one_or_none()
    return live or collection


def allowed_path(settings: Settings, raw: str) -> str | None:
    """The normalized absolute path when it lies inside WATCH_ROOTS, else None.
    Checked before the folder is touched at all: the path comes from an API
    caller, and without the check anyone who can reach the API could make the
    app read (and then answer from) any folder on the machine."""
    # realpath resolves ".." and links, and on Windows returns the case the
    # folder really has on disk, so a plain prefix check is enough.
    real = os.path.realpath(os.path.expanduser(raw))
    for root in settings.watch_root_paths:
        base = str(root).rstrip(os.sep)
        if real == base or real.startswith(base + os.sep):
            return real
    return None


def _validate_path(
    db: Session, settings: Settings, raw: str, *, ignore_id: int | None = None
) -> Path:
    if not raw.strip():
        raise InvalidWatchedFolderError("give the folder's full path")
    if not os.path.isabs(os.path.expanduser(raw.strip())):
        raise InvalidWatchedFolderError(f"{raw!r} isn't a full path (e.g. C:\\Docs or /watch)")
    allowed = allowed_path(settings, raw.strip())
    if allowed is None:
        roots = ", ".join(str(r) for r in settings.watch_root_paths)
        raise InvalidWatchedFolderError(
            f"only folders inside {roots} can be watched; set WATCH_ROOTS to allow others"
        )
    path = Path(allowed)
    if not path.is_dir():
        raise InvalidWatchedFolderError(f"{path} doesn't exist or isn't a folder on this machine")
    data_dir = _norm(settings.data_dir)
    if _inside(path, data_dir) or _inside(data_dir, path):
        raise InvalidWatchedFolderError(
            "the folder can't be inside the app's data folder, or contain it"
        )
    for other in list_folders(db):
        if other.id == ignore_id:
            continue
        other_path = Path(other.path)
        if _inside(path, other_path) or _inside(other_path, path):
            raise ConflictError(f"{path} overlaps the watched folder {other.path}")
    return path


def add_folder(
    db: Session, settings: Settings, *, path: str, collection_id: int, recursive: bool = True
) -> WatchedFolder:
    collection = get_collection(db, collection_id)
    folder = WatchedFolder(
        path=str(_validate_path(db, settings, path)),
        collection_id=collection.id,
        recursive=recursive,
    )
    db.add(folder)
    db.flush()
    record_audit(db, "watch_add", "watched_folder", folder.id, f"{folder.path} → {collection.name}")
    db.commit()
    return folder


def update_folder(
    db: Session,
    folder_id: int,
    *,
    enabled: bool | None = None,
    recursive: bool | None = None,
    collection_id: int | None = None,
) -> WatchedFolder:
    folder = get_folder(db, folder_id)
    changes = []
    if enabled is not None and enabled != folder.enabled:
        folder.enabled = enabled
        changes.append("resumed" if enabled else "paused")
    if recursive is not None and recursive != folder.recursive:
        folder.recursive = recursive
        changes.append("subfolders " + ("included" if recursive else "left out"))
    if collection_id is not None and collection_id != folder.collection_id:
        folder.collection_id = get_collection(db, collection_id).id
        db.flush()
        db.refresh(folder)
        changes.append(f"now feeds {folder.collection.name}")
    if changes:
        record_audit(
            db, "watch_update", "watched_folder", folder.id, f"{folder.path}: {', '.join(changes)}"
        )
    db.commit()
    return folder


def remove_folder(db: Session, folder_id: int) -> None:
    """Stops watching. Documents already ingested from it stay in the library."""
    folder = get_folder(db, folder_id)
    record_audit(db, "watch_remove", "watched_folder", folder.id, folder.path)
    db.delete(folder)
    db.commit()


# --- Queuing files ---------------------------------------------------------------


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _known(db: Session, sha256: str) -> bool:
    """Already a version somewhere, or waiting in the queue from a watched folder."""
    if db.execute(select(DocumentVersion.id).where(DocumentVersion.sha256 == sha256)).first():
        return True
    waiting = db.execute(
        select(IngestJob.payload).where(
            IngestJob.job_type == "ingest", IngestJob.status.in_(["pending", "running"])
        )
    ).scalars()
    return any(json.loads(payload or "{}").get("sha256") == sha256 for payload in waiting)


def document_name(folder: WatchedFolder, path: Path) -> str:
    """The document's name: the file name, with its subfolder in front for files
    below the top level, so two files with the same name stay two documents."""
    relative = _norm(path).relative_to(Path(folder.path))
    return relative.as_posix()


@dataclass
class QueueResult:
    status: str  # "queued", "known" (already ingested or waiting), "ignored", "too_large", "empty"
    job_id: int | None = None


def queue_file(db: Session, settings: Settings, folder: WatchedFolder, path: Path) -> QueueResult:
    """Copies one file to staging and queues its ingest, unless its content is
    already in the library (a duplicate would only be skipped by the job)."""
    path = _norm(path)
    if not is_candidate(path) or not path.is_file():
        return QueueResult("ignored")
    size = path.stat().st_size
    if size == 0:
        return QueueResult("empty")
    if size > settings.max_upload_mb * 1024 * 1024:
        folder.last_error = f"{path.name} is over {settings.max_upload_mb} MB and was skipped"
        db.commit()
        return QueueResult("too_large")

    sha256 = _hash(path)
    if _known(db, sha256):
        return QueueResult("known")

    staging_dir = settings.uploads_dir / uuid.uuid4().hex
    staging_dir.mkdir(parents=True)
    staged = staging_dir / path.name
    shutil.copy2(path, staged)
    if _hash(staged) != sha256:  # the file changed while it was copied; the next event retries
        shutil.rmtree(staging_dir, ignore_errors=True)
        return QueueResult("ignored")

    shelf = shelf_of(db, folder)
    job = queue.enqueue(
        db,
        "ingest",
        {
            "staged_path": str(staged),
            "filename": document_name(folder, path),
            "collection_id": shelf.id,
            "note": f"From watched folder {folder.path}",
            "watched_folder_id": folder.id,
            "sha256": sha256,
        },
    )
    folder.files_queued += 1
    folder.last_file_at = utcnow()
    folder.last_error = None
    db.commit()
    log.info("watched folder queued a file", extra={"path": str(path), "job_id": job.id})
    return QueueResult("queued", job.id)


@dataclass
class ScanResult:
    queued: int = 0
    known: int = 0
    skipped: int = 0  # ignored, empty or too large


def folder_files(folder: WatchedFolder) -> list[Path]:
    root = Path(folder.path)
    pattern = root.rglob("*") if folder.recursive else root.glob("*")
    return sorted(p for p in pattern if p.is_file() and is_candidate(p))


def scan_folder(db: Session, settings: Settings, folder: WatchedFolder) -> ScanResult:
    """Queues every supported file whose content isn't in the library yet: at
    startup (changes made while the app was off) and from "Scan now"."""
    result = ScanResult()
    if allowed_path(settings, folder.path) is None:
        folder.last_error = f"{folder.path} is outside WATCH_ROOTS; it isn't read"
        folder.last_scan_at = utcnow()
        db.commit()
        return result
    root = Path(folder.path)
    if not root.is_dir():
        folder.last_error = f"{folder.path} isn't reachable"
        folder.last_scan_at = utcnow()
        db.commit()
        return result
    for path in folder_files(folder):
        try:
            outcome = queue_file(db, settings, folder, path)
        except OSError as exc:  # locked or vanished mid-scan; the next event or scan retries
            log.warning("watched file unreadable", extra={"path": str(path), "error": str(exc)})
            result.skipped += 1
            continue
        if outcome.status == "queued":
            result.queued += 1
        elif outcome.status == "known":
            result.known += 1
        else:
            result.skipped += 1
    folder.last_scan_at = utcnow()
    if result.skipped == 0 and folder.last_error and "isn't reachable" in folder.last_error:
        folder.last_error = None
    db.commit()
    return result


def folder_for(db: Session, settings: Settings, path: Path) -> WatchedFolder | None:
    """The enabled watched folder a path belongs to, if any (inside WATCH_ROOTS)."""
    path = _norm(path)
    for folder in list_folders(db):
        root = Path(folder.path)
        if not folder.enabled or not _inside(path, root):
            continue
        if allowed_path(settings, folder.path) is None:
            continue
        if folder.recursive or path.parent == root:
            return folder
    return None
