"""The single in-process job worker (CLAUDE.md: exactly 1 job worker,
because embedded Chroma and SQLite are single-writer).

A daemon thread polls `ingest_jobs` for pending work. Tests skip the
thread and call `run_once()` directly.
"""

import json
import logging
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.core.runtime import Runtime
from app.db.models import IngestJob
from app.ingest.uploads import discard_staged
from app.jobs import queue
from app.jobs.handlers import HANDLERS
from app.jobs.queue import JobCancelled
from app.versioning.service import NoTextError

logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(self, runtime: Runtime):
        self._runtime = runtime
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._runtime.session_factory() as db:
            recovered = queue.recover_stale(db)
        if recovered:
            logger.info("recovered stale jobs", extra={"count": recovered})
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="job-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        interval = self._runtime.settings.job_poll_interval_seconds
        while not self._stop.is_set():
            try:
                processed = self.run_once()
            except Exception:  # never let the worker thread die
                logger.exception("job worker loop error")
                processed = False
            if not processed:
                self._stop.wait(interval)

    def run_once(self) -> bool:
        """Runs the oldest pending job, if any. Returns whether one ran."""
        with self._runtime.session_factory() as db:
            job = queue.claim_next(db)
            if job is None:
                return False

            token = request_id_var.set(f"job-{job.id}")
            try:
                return self._run(db, job)
            finally:
                request_id_var.reset(token)

    def _run(self, db: Session, job: IngestJob) -> bool:
        log_extra = {"job_id": job.id, "job_type": job.job_type}
        logger.info("job started", extra=log_extra)
        payload = json.loads(job.payload)
        handler = HANDLERS.get(job.job_type)

        def progress(fraction: float) -> None:
            queue.report_progress(db, job, fraction)

        try:
            if handler is None:
                raise ValueError(f"no handler for job type {job.job_type!r}")
            result = handler(db, payload, self._runtime, progress)
        except JobCancelled:
            db.rollback()
            queue.mark_cancelled(db, job)
            self._cleanup(job.job_type, payload)
            logger.info("job cancelled", extra=log_extra)
        except Exception as exc:
            db.rollback()
            # Retrying cannot give an empty file text, so fail it at once.
            permanent = isinstance(exc, NoTextError)
            queue.fail(
                db,
                job,
                f"{type(exc).__name__}: {exc}",
                max_retries=0 if permanent else self._runtime.settings.job_max_retries,
            )
            logger.exception("job failed", extra={**log_extra, "status": job.status})
        else:
            if job.job_type == "ingest" and result.get("document_id"):
                job.document_id = result["document_id"]
            queue.complete(db, job, result)
            logger.info("job completed", extra=log_extra)
        return True

    def run_until_idle(self, max_jobs: int = 100) -> int:
        """Test helper: drains the queue synchronously."""
        count = 0
        while count < max_jobs and self.run_once():
            count += 1
        return count

    def _cleanup(self, job_type: str, payload: dict) -> None:
        if job_type == "ingest" and "staged_path" in payload:
            discard_staged(Path(payload["staged_path"]), self._runtime.settings.uploads_dir)
