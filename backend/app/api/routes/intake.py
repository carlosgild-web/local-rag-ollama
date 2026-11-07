"""Intake (decision 0009): the app suggests a shelf and tags for every
file before anything is indexed; the user reviews, changes and confirms.

POST   /api/intake                  stage files, start the analysis job
GET    /api/intake/{batch_id}       the suggestions (state "ready" when done)
POST   /api/intake/{batch_id}/confirm   create shelves, queue ingest jobs
DELETE /api/intake/{batch_id}       cancel: remove the staged files
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import IntakeConfirmed, IntakeConfirmIn, IntakeOut, IntakeStarted
from app.ingest import intake
from app.jobs import queue

router = APIRouter(tags=["intake"])


@router.post("/intake", status_code=status.HTTP_202_ACCEPTED, response_model=IntakeStarted)
def start_intake(
    db: DbDep,
    runtime: RuntimeDep,
    files: Annotated[list[UploadFile], File(description="The files to analyze")],
    paths: Annotated[
        list[str] | None, Form(description="Relative path of each file, same order (folders)")
    ] = None,
):
    """Stages the files and queues the analysis. Nothing is indexed yet."""
    rel_paths = paths or []
    uploads = [
        (f.filename or "", rel_paths[i] if i < len(rel_paths) else (f.filename or ""), f.file)
        for i, f in enumerate(files)
    ]
    batch_id, count = intake.stage_batch(runtime.settings, uploads)
    job = queue.enqueue(db, "analyze_intake", {"batch_id": batch_id, "files": count})
    return IntakeStarted(batch_id=batch_id, job_id=job.id, files=count)


@router.get("/intake/{batch_id}", response_model=IntakeOut)
def get_intake(runtime: RuntimeDep, batch_id: str):
    manifest = intake.load_batch(runtime.settings, batch_id)
    return IntakeOut(
        batch_id=batch_id,
        state=manifest["state"],
        files=[
            {k: v for k, v in f.items() if k not in ("stored", "sha256")} for f in manifest["files"]
        ],
        shelves=manifest["shelves"],
    )


@router.post("/intake/{batch_id}/confirm", response_model=IntakeConfirmed)
def confirm_intake(db: DbDep, runtime: RuntimeDep, batch_id: str, body: IntakeConfirmIn):
    """Creates the approved new shelves and queues one ingest job per file."""
    job_ids, created = intake.confirm_batch(
        db,
        runtime,
        batch_id,
        body.new_shelves,
        [intake.ConfirmedFile(f.key, f.include, f.shelf, f.tags) for f in body.files],
        enqueue=lambda job_type, payload: queue.enqueue(db, job_type, payload),
    )
    return IntakeConfirmed(job_ids=job_ids, created_shelves=created)


@router.delete("/intake/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_intake(runtime: RuntimeDep, batch_id: str):
    intake.load_batch(runtime.settings, batch_id)  # 404 if unknown
    intake.cancel_batch(runtime.settings, batch_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
