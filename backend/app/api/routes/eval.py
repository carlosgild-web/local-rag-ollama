"""Evaluation (PLAN.md Phase 7, decision 0019): golden sets, runs, comparison.

A run is queued as a `run_eval` job; poll `GET /eval/runs/{id}` for its
status and progress, and cancel it through `POST /jobs/{job_id}/cancel`.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import (
    EvalCaseIn,
    EvalCaseOut,
    EvalCasePatch,
    EvalCompareOut,
    EvalDemoStatus,
    EvalImportIn,
    EvalResultOut,
    EvalRunDetail,
    EvalRunIn,
    EvalRunOut,
    EvalSetDetail,
    EvalSetIn,
    EvalSetOut,
    EvalSetPatch,
)
from app.db.models import EvalRun, EvalSet, IngestJob, RagProfile
from app.eval import service as eval_service

router = APIRouter(prefix="/eval", tags=["evaluation"])


def _set_out(db: Session, eval_set: EvalSet, *, detail: bool = False):
    runs = db.execute(
        select(func.count()).select_from(EvalRun).where(EvalRun.eval_set_id == eval_set.id)
    ).scalar_one()
    fields = {
        "id": eval_set.id,
        "name": eval_set.name,
        "description": eval_set.description,
        "case_count": len(eval_set.cases),
        "run_count": runs,
        "created_at": eval_set.created_at,
    }
    if detail:
        return EvalSetDetail(
            **fields, cases=[EvalCaseOut.model_validate(c) for c in eval_set.cases]
        )
    return EvalSetOut(**fields)


def run_out(db: Session, run: EvalRun) -> EvalRunOut:
    profile = db.get(RagProfile, run.rag_profile_id) if run.rag_profile_id else None
    job = db.get(IngestJob, run.job_id) if run.job_id else None
    eval_set = db.get(EvalSet, run.eval_set_id)
    run_status = eval_service.run_status(db, run)
    return EvalRunOut(
        id=run.id,
        eval_set_id=run.eval_set_id,
        eval_set_name=eval_set.name if eval_set else "",
        rag_profile_id=run.rag_profile_id,
        profile=f"{profile.name} v{profile.version}" if profile else None,
        chat_model=profile.chat_model if profile else None,
        label=run.label,
        config=run.config,
        index_snapshot=run.index_snapshot,
        metrics=run.metrics,
        status=run_status,
        progress=1.0 if run_status == "completed" else (job.progress if job else 0.0),
        error=job.error if job and run_status != "completed" else None,
        job_id=run.job_id,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


# --- Golden sets --------------------------------------------------------------


@router.get("/sets", response_model=list[EvalSetOut])
def list_sets(db: DbDep):
    return [_set_out(db, s) for s in eval_service.list_sets(db)]


@router.post("/sets", status_code=status.HTTP_201_CREATED, response_model=EvalSetDetail)
def create_set(db: DbDep, body: EvalSetIn):
    return _set_out(db, eval_service.create_set(db, body.name, body.description), detail=True)


@router.post("/sets/import", status_code=status.HTTP_201_CREATED, response_model=EvalSetDetail)
def import_set(db: DbDep, body: EvalImportIn):
    """Creates a set from the JSON file format (see `GET /eval/sets/{id}/export`)."""
    return _set_out(db, eval_service.import_set(db, body.model_dump()), detail=True)


@router.get("/demo", response_model=EvalDemoStatus)
def demo_status(db: DbDep):
    """Whether the demo golden set ships with this install, and if it's loaded."""
    name = None
    if eval_service.demo_set_available():
        name = json.loads(eval_service.DEMO_SET_PATH.read_text(encoding="utf-8")).get("name")
    loaded = db.execute(select(EvalSet.id).where(EvalSet.name == name)).scalar_one_or_none()
    return EvalDemoStatus(available=name is not None, loaded_set_id=loaded)


@router.post("/demo", status_code=status.HTTP_201_CREATED, response_model=EvalSetDetail)
def load_demo_set(db: DbDep):
    """Loads the golden set for the demo company; a 409 if it's already there."""
    return _set_out(db, eval_service.load_demo_set(db), detail=True)


@router.get("/sets/{set_id}", response_model=EvalSetDetail)
def get_set(db: DbDep, set_id: int):
    return _set_out(db, eval_service.get_set(db, set_id), detail=True)


@router.patch("/sets/{set_id}", response_model=EvalSetDetail)
def update_set(db: DbDep, set_id: int, body: EvalSetPatch):
    eval_set = eval_service.update_set(db, set_id, name=body.name, description=body.description)
    return _set_out(db, eval_set, detail=True)


@router.delete("/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_set(db: DbDep, set_id: int):
    """Deletes the set with its cases and runs (there's no trash for golden sets)."""
    eval_service.delete_set(db, set_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sets/{set_id}/export")
def export_set(db: DbDep, set_id: int):
    data = eval_service.export_set(db, set_id)
    filename = "".join(c if c.isalnum() else "-" for c in data["name"].lower()).strip("-")
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename or "golden-set"}.json"'},
    )


@router.post(
    "/sets/{set_id}/cases", status_code=status.HTTP_201_CREATED, response_model=EvalCaseOut
)
def add_case(db: DbDep, set_id: int, body: EvalCaseIn):
    return eval_service.add_case(db, set_id, **body.model_dump())


@router.patch("/cases/{case_id}", response_model=EvalCaseOut)
def update_case(db: DbDep, case_id: int, body: EvalCasePatch):
    return eval_service.update_case(db, case_id, **body.model_dump(exclude_unset=True))


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(db: DbDep, case_id: int):
    eval_service.delete_case(db, case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Runs -----------------------------------------------------------------------


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED, response_model=EvalRunOut)
def start_run(db: DbDep, runtime: RuntimeDep, body: EvalRunIn):
    run = eval_service.start_run(
        db,
        runtime.settings,
        body.eval_set_id,
        profile_id=body.profile_id,
        mode=body.mode,
        top_k=body.top_k,
        answers=body.answers,
        judge=body.judge,
        judge_model=body.judge_model,
        label=body.label,
    )
    return run_out(db, run)


@router.get("/runs", response_model=list[EvalRunOut])
def list_runs(db: DbDep, eval_set_id: Annotated[int | None, Query()] = None):
    return [run_out(db, r) for r in eval_service.list_runs(db, eval_set_id)]


@router.get("/runs/{run_id}", response_model=EvalRunDetail)
def get_run(db: DbDep, run_id: int):
    run = eval_service.get_run(db, run_id)
    return EvalRunDetail(
        **run_out(db, run).model_dump(),
        results=[EvalResultOut.model_validate(r) for r in run.results],
    )


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(db: DbDep, run_id: int):
    eval_service.delete_run(db, run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/compare", response_model=EvalCompareOut)
def compare_runs(db: DbDep, a: Annotated[int, Query()], b: Annotated[int, Query()]):
    """Two runs case by case; `same_index` says whether they searched the same index."""
    comparison = eval_service.compare_runs(db, a, b)
    return EvalCompareOut(
        a=run_out(db, comparison["a"]),
        b=run_out(db, comparison["b"]),
        same_index=comparison["same_index"],
        cases=comparison["cases"],
    )
