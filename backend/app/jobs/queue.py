"""SQLite-backed job queue (no Redis): the service layer for `ingest_jobs`.

Status flow: pending -> running -> completed | failed | cancelled.
A failure is retried automatically up to `max_retries` times; after that
the job stays `failed` until someone calls `retry`. Cancelling a pending
job is immediate. Cancelling a running job sets `cancel_requested`, which
the worker checks at each progress report.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IngestJob, utcnow
from app.versioning.service import ConflictError, NotFoundError, record_audit

JOB_TYPES = {"ingest", "reindex_document", "reindex_collection", "rebuild_collection"}
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


def claim_next(db: Session) -> IngestJob | None:
    """Marks the oldest pending job running. Safe with exactly one worker."""
    job = db.execute(
        select(IngestJob).where(IngestJob.status == "pending").order_by(IngestJob.id).limit(1)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    job.progress = 0.0
    job.updated_at = utcnow()
    db.commit()
    return job


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
    job = get_job(db, job_id)
    if job.status in TERMINAL:
        raise ConflictError(f"job {job_id} is already {job.status}")
    if job.status == "pending":
        job.status = "cancelled"
    else:
        job.cancel_requested = True
    job.updated_at = utcnow()
    record_audit(db, "job_cancel", "job", job.id, job.job_type)
    db.commit()
    return job


def retry(db: Session, job_id: int) -> IngestJob:
    job = get_job(db, job_id)
    if job.status not in {"failed", "cancelled"}:
        raise ConflictError(f"job {job_id} is {job.status}; only failed or cancelled jobs retry")
    job.status = "pending"
    job.progress = 0.0
    job.error = None
    job.cancel_requested = False
    job.retries += 1
    job.updated_at = utcnow()
    record_audit(db, "job_retry", "job", job.id, job.job_type)
    db.commit()
    return job


def recover_stale(db: Session) -> int:
    """On startup, jobs left `running` by a crash go back to pending."""
    jobs = db.execute(select(IngestJob).where(IngestJob.status == "running")).scalars().all()
    for job in jobs:
        job.status = "cancelled" if job.cancel_requested else "pending"
        job.updated_at = utcnow()
    db.commit()
    return len(jobs)
