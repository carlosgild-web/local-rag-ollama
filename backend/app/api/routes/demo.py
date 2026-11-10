"""The demo company (decision 0010), loadable from the console on first run."""

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.api.deps import DbDep
from app.api.routes.jobs import _out as jobs_out
from app.api.schemas import DemoStatusOut, JobOut
from app.db.models import Document, IngestJob
from app.jobs import queue
from app.versioning import demo, service

router = APIRouter(tags=["demo"])


def _latest_seed_job(db) -> IngestJob | None:
    return db.execute(
        select(IngestJob)
        .where(IngestJob.job_type == "seed_demo")
        .order_by(IngestJob.id.desc())
        .limit(1)
    ).scalar_one_or_none()


@router.get("/demo", response_model=DemoStatusOut)
def demo_status(db: DbDep):
    """Whether the demo corpus ships with this install, how many documents the
    library has, and the latest demo load, so the dashboard can offer it."""
    documents = db.execute(
        select(func.count()).select_from(Document).where(Document.trashed_at.is_(None))
    ).scalar_one()
    job = _latest_seed_job(db)
    return DemoStatusOut(
        available=demo.demo_available(),
        documents=documents,
        job=jobs_out(db, [job])[0] if job else None,
    )


@router.post("/demo/seed", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
def seed_demo(db: DbDep):
    """Queues loading the demo company. Files already stored are skipped, so
    running it again is harmless; a second request while one runs is a 409."""
    if not demo.demo_available():
        raise service.NotFoundError("the demo documents aren't part of this install")
    job = _latest_seed_job(db)
    if job is not None and job.status in {"pending", "running"}:
        raise service.ConflictError("the demo company is already loading")
    job = queue.enqueue(db, "seed_demo", {})
    service.audit_event(db, "demo_seed", "job", job.id, "load the demo company")
    return jobs_out(db, [job])[0]
