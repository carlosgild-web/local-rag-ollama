"""Watched folders (PLAN.md Phase 6, decision 0025). Adding, changing or
removing a folder tells the watcher thread to re-read the list; "Scan now"
queues the files whose content isn't in the library yet."""

from fastapi import APIRouter, Request, Response, status

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import (
    WatchedFolderIn,
    WatchedFolderOut,
    WatchedFolderPatch,
    WatchedFoldersOut,
    WatchScanOut,
)
from app.db.models import WatchedFolder
from app.versioning import watched

router = APIRouter(prefix="/watched-folders", tags=["watched folders"])


def _watcher(request: Request):
    return getattr(request.app.state, "watcher", None)


def _out(db, folder: WatchedFolder, request: Request) -> WatchedFolderOut:
    watcher = _watcher(request)
    status_ = watcher.status() if watcher is not None else None
    error = (status_.errors.get(folder.id) if status_ else None) or folder.last_error
    if not folder.enabled:
        state = "paused"
    elif status_ is None or not status_.running:
        state = "stopped"
    elif folder.id in status_.watching:
        state = "watching"
    elif folder.id in status_.errors:
        state = "error"
    else:  # just added or resumed: the watcher thread picks it up within a second
        state = "starting"
    shelf = watched.shelf_of(db, folder)
    return WatchedFolderOut(
        id=folder.id,
        path=folder.path,
        collection_id=shelf.id,
        collection_name=shelf.name,
        recursive=folder.recursive,
        enabled=folder.enabled,
        state=state,
        error=error,
        files_queued=folder.files_queued,
        last_scan_at=folder.last_scan_at,
        last_file_at=folder.last_file_at,
        created_at=folder.created_at,
    )


def _reload(request: Request, **kwargs) -> None:
    watcher = _watcher(request)
    if watcher is not None:
        watcher.reload(**kwargs)


@router.get("", response_model=WatchedFoldersOut)
def list_watched_folders(db: DbDep, runtime: RuntimeDep, request: Request):
    watcher = _watcher(request)
    return WatchedFoldersOut(
        mode="polling" if runtime.settings.watch_polling else "events",
        running=bool(watcher and watcher.status().running),
        poll_seconds=runtime.settings.watch_poll_seconds,
        folders=[_out(db, f, request) for f in watched.list_folders(db)],
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WatchedFolderOut)
def add_watched_folder(db: DbDep, runtime: RuntimeDep, request: Request, body: WatchedFolderIn):
    """Starts watching; the folder's current files are queued once (audited)."""
    folder = watched.add_folder(
        db,
        runtime.settings,
        path=body.path,
        collection_id=body.collection_id,
        recursive=body.recursive,
    )
    _reload(request, rescan=folder.id)
    return _out(db, folder, request)


@router.patch("/{folder_id}", response_model=WatchedFolderOut)
def update_watched_folder(db: DbDep, request: Request, folder_id: int, body: WatchedFolderPatch):
    before = watched.get_folder(db, folder_id).enabled
    folder = watched.update_folder(
        db,
        folder_id,
        enabled=body.enabled,
        recursive=body.recursive,
        collection_id=body.collection_id,
    )
    # Resuming catches up on what changed while paused.
    _reload(request, rescan=folder.id if folder.enabled and not before else None)
    return _out(db, folder, request)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_watched_folder(db: DbDep, request: Request, folder_id: int):
    """Stops watching. Documents already ingested from the folder stay."""
    watched.remove_folder(db, folder_id)
    _reload(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{folder_id}/scan", response_model=WatchScanOut)
def scan_watched_folder(db: DbDep, runtime: RuntimeDep, folder_id: int):
    """Queues every file whose content isn't in the library yet."""
    result = watched.scan_folder(db, runtime.settings, watched.get_folder(db, folder_id))
    return WatchScanOut(queued=result.queued, known=result.known, skipped=result.skipped)
