"""The demo company (decision 0010), loadable from the console on first run."""

from pathlib import Path

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.api.deps import DbDep
from app.api.originals import opens_in_browser, original_response
from app.api.routes.jobs import _out as jobs_out
from app.api.schemas import DemoFileOut, DemoStatusOut, JobOut
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


def _demo_files() -> dict[tuple[str, str], Path]:
    """Every demo file by (shelf, name). Serving only what's listed here means a
    request can never reach a path outside the demo folder."""
    root = demo.DEMO_DIR
    if not root.is_dir():
        return {}
    return {
        (folder.name, path.name): path
        for folder in sorted(p for p in root.iterdir() if p.is_dir())
        for path in service.discover_files(folder)
    }


@router.get("/demo/files", response_model=list[DemoFileOut])
def demo_files():
    """The demo company's original documents, so people can read them before loading."""
    return [
        DemoFileOut(
            shelf=shelf,
            name=name,
            type=path.suffix.lstrip(".").lower(),
            size=path.stat().st_size,
            opens_in_browser=opens_in_browser(path.suffix),
        )
        for (shelf, name), path in _demo_files().items()
    ]


@router.get("/demo/files/{shelf}/{name}", include_in_schema=True)
def demo_file(shelf: str, name: str):
    """One original demo document: PDFs and text open in the browser, Word files download."""
    path = _demo_files().get((shelf, name))
    if path is None:
        raise service.NotFoundError(f"no demo document {shelf}/{name}")
    return original_response(path, name)
