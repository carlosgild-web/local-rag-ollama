"""Ingestion queue (PLAN.md section 8)."""

import json
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.api.schemas import JobOut
from app.db.models import IngestJob
from app.jobs import queue

router = APIRouter(tags=["jobs"])

# Internal paths stay server-side.
_HIDDEN_PAYLOAD_KEYS = {"staged_path"}


def job_out(job: IngestJob) -> JobOut:
    payload = json.loads(job.payload or "{}")
    return JobOut(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        error=job.error,
        result=json.loads(job.result) if job.result else None,
        retries=job.retries,
        cancel_requested=job.cancel_requested,
        document_id=job.document_id,
        payload={k: v for k, v in payload.items() if k not in _HIDDEN_PAYLOAD_KEYS},
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    db: DbDep,
    status: Annotated[
        str | None, Query(pattern="^(pending|running|completed|failed|cancelled)$")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return [job_out(j) for j in queue.list_jobs(db, status=status, limit=limit, offset=offset)]


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(db: DbDep, job_id: int):
    return job_out(queue.retry(db, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(db: DbDep, job_id: int):
    """Pending jobs cancel at once; running jobs stop at their next progress step."""
    return job_out(queue.cancel(db, job_id))
