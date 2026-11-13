"""Ingestion queue (PLAN.md section 8)."""

import json
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbDep
from app.api.schemas import JobOut
from app.db.models import Collection, Document, IngestJob
from app.jobs import queue

router = APIRouter(tags=["jobs"])

# Internal paths stay server-side.
_HIDDEN_PAYLOAD_KEYS = {"staged_path"}


class _Names:
    """Document and collection names for a page of jobs, loaded in two queries."""

    def __init__(self, db: Session, jobs: list[IngestJob]):
        results = [json.loads(j.result) if j.result else {} for j in jobs]
        payloads = [json.loads(j.payload or "{}") for j in jobs]
        doc_ids = {j.document_id for j in jobs if j.document_id} | {
            r["document_id"] for r in results if r.get("document_id")
        }
        self.documents = {
            d.id: d for d in db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars()
        }
        col_ids = {p["collection_id"] for p in payloads if p.get("collection_id")} | {
            d.collection_id for d in self.documents.values()
        }
        self.collections = {
            c.id: c.name
            for c in db.execute(select(Collection).where(Collection.id.in_(col_ids))).scalars()
        }


def _subject(job: IngestJob, payload: dict, names: _Names) -> str | None:
    """What the job is about, in words: a file name or a shelf name."""
    if payload.get("filename"):
        return payload["filename"]
    if job.job_type == "backup":
        return "automatic daily backup" if payload.get("reason") == "auto" else "backup"
    if job.job_type == "purge_trash":
        return "documents in the trash for over 30 days"
    if job.job_type == "seed_demo":
        return "the demo company (Hilda & Luna Beadworks)"
    if job.job_type == "analyze_intake":
        count = payload.get("files", 0)
        return f"{count} file{'s' if count != 1 else ''} to suggest shelves and tags for"
    document = names.documents.get(job.document_id or payload.get("document_id"))
    if document is not None:
        return document.filename
    if payload.get("collection_id") in names.collections:
        return f"shelf {names.collections[payload['collection_id']]}"
    return None


def _note(result: dict | None, names: _Names) -> str | None:
    if not result or result.get("status") != "skipped_duplicate":
        return None
    document = names.documents.get(result.get("document_id"))
    if document is None:
        return "Skipped: the same content is already in the library."
    shelf = names.collections.get(document.collection_id, f"#{document.collection_id}")
    where = " (in the trash)" if document.trashed_at else ""
    return f"Skipped: already in the library as '{document.filename}' on shelf '{shelf}'{where}."


def job_out(job: IngestJob, names: _Names) -> JobOut:
    payload = json.loads(job.payload or "{}")
    result = json.loads(job.result) if job.result else None
    return JobOut(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        error=job.error,
        result=result,
        retries=job.retries,
        cancel_requested=job.cancel_requested,
        document_id=job.document_id,
        payload={k: v for k, v in payload.items() if k not in _HIDDEN_PAYLOAD_KEYS},
        subject=_subject(job, payload, names),
        note=_note(result, names),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _out(db: Session, jobs: list[IngestJob]) -> list[JobOut]:
    names = _Names(db, jobs)
    return [job_out(j, names) for j in jobs]


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    db: DbDep,
    status: Annotated[
        str | None, Query(pattern="^(pending|running|completed|failed|cancelled)$")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return _out(db, queue.list_jobs(db, status=status, limit=limit, offset=offset))


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(db: DbDep, job_id: int):
    return _out(db, [queue.retry(db, job_id)])[0]


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(db: DbDep, job_id: int):
    """Pending jobs cancel at once; running jobs stop at their next progress step."""
    return _out(db, [queue.cancel(db, job_id)])[0]
