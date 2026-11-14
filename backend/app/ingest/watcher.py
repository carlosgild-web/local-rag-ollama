"""The watched-folder thread (PLAN.md Phase 6, decision 0025).

One thread, next to the job worker. It listens to file events from watchdog
(OS events, or polling with WATCH_POLLING=true for Docker bind mounts and
network drives) and, once a file has stopped changing for
WATCH_SETTLE_SECONDS, hands it to `watched.queue_file`, which queues an
ordinary ingest job. It never writes to the library itself (invariant 1).

On start, and when a folder is added or resumed, the folder is scanned once
to pick up changes made while nobody was watching. A file deleted from a
folder is only logged.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from app.core.runtime import Runtime
from app.versioning import watched

log = logging.getLogger(__name__)


@dataclass
class _Pending:
    seen_at: float  # monotonic time of the latest event
    stat: tuple[int, int] | None = None  # (size, mtime_ns) at the last look


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "FolderWatcher"):
        self.watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.watcher.file_changed(Path(str(event.src_path)))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.watcher.file_changed(Path(str(event.src_path)))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:  # a rename into the folder, or a save via a temp file
            self.watcher.file_changed(Path(str(event.dest_path)))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            # The user's choice (2026-11-14): the document stays in the library.
            log.info("file removed from a watched folder; its document is kept",
                     extra={"path": str(event.src_path)})  # fmt: skip


@dataclass
class WatcherStatus:
    running: bool
    mode: str  # "events" or "polling"
    watching: set[int] = field(default_factory=set)  # folder ids with a live observer
    errors: dict[int, str] = field(default_factory=dict)


class FolderWatcher:
    def __init__(self, runtime: Runtime, *, tick_seconds: float = 0.5):
        self.runtime = runtime
        self.settings = runtime.settings
        self.tick_seconds = tick_seconds
        self._pending: dict[Path, _Pending] = {}
        self._lock = threading.Lock()
        self._reload = threading.Event()
        self._rescan: set[int] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer = None
        self._watching: set[int] = set()
        self._errors: dict[int, str] = {}

    @property
    def mode(self) -> str:
        return "polling" if self.settings.watch_polling else "events"

    def status(self) -> WatcherStatus:
        with self._lock:
            return WatcherStatus(
                running=self._thread is not None and self._thread.is_alive(),
                mode=self.mode,
                watching=set(self._watching),
                errors=dict(self._errors),
            )

    # --- Lifecycle ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self.reload(rescan_all=True)
        self._thread = threading.Thread(target=self._run, name="folder-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        self._stop_observer()

    def reload(self, *, rescan: int | None = None, rescan_all: bool = False) -> None:
        """Re-reads the folders (after an add, change or removal). `rescan`
        scans that folder once; `rescan_all` scans every enabled folder."""
        with self._lock:
            if rescan is not None:
                self._rescan.add(rescan)
            if rescan_all:
                self._rescan.add(-1)
        self._reload.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self._reload.is_set():
                    self._reload.clear()
                    self._apply_config()
                self.process_pending()
            except Exception:  # never let one bad file stop the watcher
                log.exception("folder watcher error")
            self._stop.wait(self.tick_seconds)

    # --- Observers ---------------------------------------------------------------

    def _stop_observer(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=10)
            self._observer = None

    def _new_observer(self):
        if self.settings.watch_polling:
            return PollingObserver(timeout=self.settings.watch_poll_seconds)
        return Observer()

    def _apply_config(self) -> None:
        self._stop_observer()
        with self._lock:
            rescan, self._rescan = self._rescan, set()
        observer = self._new_observer()
        watching: set[int] = set()
        errors: dict[int, str] = {}
        handler = _Handler(self)
        with self.runtime.session_factory() as db:
            folders = [f for f in watched.list_folders(db) if f.enabled]
            for folder in folders:
                if watched.allowed_path(self.settings, folder.path) is None:
                    errors[folder.id] = f"{folder.path} is outside WATCH_ROOTS; it isn't watched"
                    continue
                try:
                    observer.schedule(handler, folder.path, recursive=folder.recursive)
                    watching.add(folder.id)
                except OSError as exc:  # the folder vanished or the drive is offline
                    errors[folder.id] = f"can't watch {folder.path}: {exc}"
            if watching:
                observer.start()
                self._observer = observer
            with self._lock:
                self._watching, self._errors = watching, errors
            for folder in folders:
                if folder.id in watching and (-1 in rescan or folder.id in rescan):
                    result = watched.scan_folder(db, self.settings, folder)
                    log.info("watched folder scanned",
                             extra={"path": folder.path, "queued": result.queued})  # fmt: skip

    # --- Files -------------------------------------------------------------------

    def file_changed(self, path: Path) -> None:
        if not watched.is_candidate(path):
            return
        with self._lock:
            entry = self._pending.get(path)
            if entry is None:
                self._pending[path] = _Pending(seen_at=time.monotonic())
            else:
                entry.seen_at = time.monotonic()

    def process_pending(self, now: float | None = None) -> list[Path]:
        """Queues the files that stopped changing; returns them (for tests)."""
        now = time.monotonic() if now is None else now
        settle = self.settings.watch_settle_seconds
        ready: list[Path] = []
        with self._lock:
            for path, entry in list(self._pending.items()):
                if now - entry.seen_at < settle:
                    continue
                try:
                    st = path.stat()
                except OSError:  # gone again (a temp file, or deleted)
                    del self._pending[path]
                    continue
                stat = (st.st_size, st.st_mtime_ns)
                if entry.stat == stat:
                    ready.append(path)
                    del self._pending[path]
                else:  # still being written: look again after another quiet spell
                    entry.stat, entry.seen_at = stat, now
        if not ready:
            return []
        with self.runtime.session_factory() as db:
            for path in ready:
                folder = watched.folder_for(db, self.settings, path)
                if folder is None:
                    continue
                try:
                    watched.queue_file(db, self.settings, folder, path)
                except OSError as exc:  # locked by another program: try on the next change
                    log.warning("watched file unreadable",
                                extra={"path": str(path), "error": str(exc)})  # fmt: skip
        return ready
