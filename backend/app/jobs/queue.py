"""SQLite-backed job queue (no Redis): the service layer for `ingest_jobs`.

Status flow: pending -> running -> completed | failed | cancelled.

Status changes that can race (the worker claiming a job while a request
cancels or retries it) are conditional UPDATEs: they only apply if the row
is still in the expected status, so neither side overwrites the other.
A failure is retried automatically up to `max_retries` times; after that
the job stays `failed` until someone calls `retry`. Cancelling a pending
job is immediate. Cancelling a running job sets `cancel_requested`, which
the worker checks at each progress report.
"""

import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import IngestJob, utcnow
from app.versioning.service import ConflictError, NotFoundError, record_audit

JOB_TYPES = {
    "ingest",
    "reindex_document",
    "reindex_collection",
    "rebuild_collection",
    "analyze_intake",
    "seed_demo",
}
TERMINAL = {"completed", "failed", "cancelled"}


class JobCancelled(Exception):
    """Raised inside a running job when cancellation was requested."""


def enqueue(
    db: Session, job_type: str, payload: dict, *, document_id: int | None = None
) -> IngestJob:
    if job_type not in JOB_TYPES:
        raise ValueError(f"unknown job type {job_type!r}")
    job = IngestJob(job_type=job_type, payload=json.dumps(payload), document_id=document_id)
    db.add(job)
    db.commit()
    return job


def get_job(db: Session, job_id: int) -> IngestJob:
    # populate_existing: the worker updates jobs from another session.
    job = db.get(IngestJob, job_id, populate_existing=True)
    if job is None:
        raise NotFoundError(f"job {job_id} not found")
    return job


def list_jobs(
    db: Session, *, status: str | None = None, limit: int = 100, offset: int = 0
) -> list[IngestJob]:
    query = select(IngestJob).order_by(IngestJob.id.desc()).limit(limit).offset(offset)
    if status:
        query = query.where(IngestJob.status == status)
    return list(db.execute(query).scalars().all())


def _transition(db: Session, job_id: int, from_statuses: set[str], **values) -> bool:
    """Applies `values` only if the job is still in one of `from_statuses`.
    Does not commit. Returns whether the row changed."""
    result = db.execute(
        update(IngestJob)
        .where(IngestJob.id == job_id, IngestJob.status.in_(from_statuses))
        .values(updated_at=utcnow(), **values)
    )
    return result.rowcount == 1


def claim_next(db: Session) -> IngestJob | None:
    """Marks the oldest pending job running. A job cancelled between the
    read and the update is skipped, not resurrected."""
    while True:
        job_id = db.execute(
            select(IngestJob.id)
            .where(IngestJob.status == "pending")
            .order_by(IngestJob.id)
            .limit(1)
        ).scalar_one_or_none()
        if job_id is None:
            db.rollback()
            return None
        claimed = _transition(db, job_id, {"pending"}, status="running", progress=0.0)
        db.commit()
        if claimed:
            return get_job(db, job_id)


def report_progress(db: Session, job: IngestJob, fraction: float) -> None:
    """Commits progress, then raises JobCancelled if a cancel came in. Call
    only between units of work (no uncommitted changes pending)."""
    job.progress = max(0.0, min(1.0, fraction))
    job.updated_at = utcnow()
    db.commit()
    db.refresh(job)
    if job.cancel_requested:
        raise JobCancelled()


def complete(db: Session, job: IngestJob, result: dict) -> None:
    job.status = "completed"
    job.progress = 1.0
    job.result = json.dumps(result)
    job.error = None
    job.updated_at = utcnow()
    db.commit()


def mark_cancelled(db: Session, job: IngestJob) -> None:
    job.status = "cancelled"
    job.updated_at = utcnow()
    db.commit()


def fail(db: Session, job: IngestJob, error: str, *, max_retries: int) -> None:
    job.error = error
    job.updated_at = utcnow()
    if job.retries < max_retries:
        job.retries += 1
        job.status = "pending"
    else:
        job.status = "failed"
    db.commit()


def cancel(db: Session, job_id: int) -> IngestJob:
    """Pending: cancelled at once. Running: asks the worker to stop at its
    next progress report. Conditional, so a job the worker claims at the
    same moment is asked to stop instead of silently running on."""
    job = get_job(db, job_id)
    if not (
        _transition(db, job_id, {"pending"}, status="cancelled")
        or _transition(db, job_id, {"running"}, cancel_requested=True)
    ):
        db.rollback()
        job = get_job(db, job_id)
        raise ConflictError(f"job {job_id} is already {job.status}")
    record_audit(db, "job_cancel", "job", job_id, job.job_type)
    db.commit()
    return get_job(db, job_id)


def retry(db: Session, job_id: int) -> IngestJob:
    job = get_job(db, job_id)
    retried = _transition(
        db,
        job_id,
        {"failed", "cancelled"},
        status="pending",
        progress=0.0,
        error=None,
        cancel_requested=False,
        retries=IngestJob.retries + 1,
    )
    if not retried:
        db.rollback()
        job = get_job(db, job_id)
        raise ConflictError(f"job {job_id} is {job.status}; only failed or cancelled jobs retry")
    record_audit(db, "job_retry", "job", job_id, job.job_type)
    db.commit()
    return get_job(db, job_id)


def recover_stale(db: Session) -> int:
    """On startup, jobs left `running` by a crash go back to pending."""
    jobs = db.execute(select(IngestJob).where(IngestJob.status == "running")).scalars().all()
    for job in jobs:
        job.status = "cancelled" if job.cancel_requested else "pending"
        job.updated_at = utcnow()
    db.commit()
    return len(jobs)
