"""Ops (PLAN.md section 8): audit log, health, diagnostics and backups. Restoring a
backup is offline (the start script or app.cli), see decision 0015."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import (
    AuditOut,
    BackupOut,
    ComponentHealth,
    DiagnosticsOut,
    HealthOut,
    JobQueued,
)
from app.core.diagnostics import run_diagnostics
from app.core.faults import SimulatedFault, active_faults, simulate
from app.db import backup
from app.db.models import AuditLog
from app.jobs import queue
from app.versioning.service import NotFoundError, audit_event

router = APIRouter(tags=["ops"])


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    db: DbDep,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    if action:
        query = query.where(AuditLog.action == action)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    return db.execute(query).scalars().all()


def _check(fn) -> ComponentHealth:
    try:
        detail = fn()
        return ComponentHealth(ok=True, detail=detail)
    except SimulatedFault as exc:
        return ComponentHealth(ok=False, detail=str(exc))
    except Exception as exc:
        return ComponentHealth(ok=False, detail=f"{type(exc).__name__}: {exc}")


@router.get("/diagnostics", response_model=DiagnosticsOut)
def diagnostics(request: Request, db: DbDep, runtime: RuntimeDep):
    """The troubleshooter: every check with a plain-language cause and fix."""
    worker = getattr(request.app.state, "worker", None)
    report = run_diagnostics(runtime, db, worker_running=bool(worker and worker.is_running))
    return report.to_dict()


@router.get("/health", response_model=HealthOut)
def health(request: Request, response: Response, db: DbDep, runtime: RuntimeDep):
    """`down` (HTTP 503) if SQLite or the vector store fails, since the app
    can't work without them. `degraded` (HTTP 200) if only Ollama or the job
    worker is unavailable."""

    faults = runtime.settings.simulate_faults

    def sqlite() -> str:
        simulate(faults, "sqlite")
        db.execute(text("SELECT 1")).scalar_one()
        return "ok"

    def vector_store() -> str:
        simulate(faults, "vector_store")
        runtime.vector_store.ping()
        return "ok"

    def ollama() -> str:
        simulate(faults, "ollama_down")
        return f"version {runtime.ollama.ping()}"

    def job_worker() -> str:
        simulate(faults, "worker")
        worker = getattr(request.app.state, "worker", None)
        if worker is None or not worker.is_running:
            raise RuntimeError("not running")
        return "running"

    result = HealthOut(
        status="ok",
        simulated=sorted(active_faults(faults)),
        ollama=_check(ollama),
        sqlite=_check(sqlite),
        vector_store=_check(vector_store),
        job_worker=_check(job_worker),
    )
    if not (result.sqlite.ok and result.vector_store.ok):
        result.status = "down"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif not (result.ollama.ok and result.job_worker.ok):
        result.status = "degraded"
    return result


# --- Backups (decision 0015) --------------------------------------------------


@router.get("/backups", response_model=list[BackupOut])
def list_backups(runtime: RuntimeDep):
    """Backups in DATA_DIR/backups, newest first."""
    return backup.list_backups(runtime.settings)


@router.post("/backups", status_code=status.HTTP_202_ACCEPTED, response_model=JobQueued)
def create_backup(db: DbDep):
    """Queues a backup; the job worker makes it, so no indexing runs meanwhile."""
    job = queue.enqueue(db, "backup", {"reason": "manual"})
    return JobQueued(job_id=job.id)


@router.get("/backups/{name}")
def download_backup(runtime: RuntimeDep, name: str):
    try:
        path = backup.backup_path(runtime.settings, name)
    except backup.BackupError as exc:
        raise NotFoundError(str(exc)) from exc
    return FileResponse(path, media_type="application/zip", filename=name)


@router.delete("/backups/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(db: DbDep, runtime: RuntimeDep, name: str):
    try:
        backup.delete_backup(runtime.settings, name)
    except backup.BackupError as exc:
        raise NotFoundError(str(exc)) from exc
    audit_event(db, "backup_delete", "backup", None, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
