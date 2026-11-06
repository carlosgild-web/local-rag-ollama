"""Ops (PLAN.md section 8): audit log and health. Backup, restore and
metrics come in later phases."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select, text

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import AuditOut, ComponentHealth, DiagnosticsOut, HealthOut
from app.core.diagnostics import run_diagnostics
from app.core.faults import SimulatedFault, active_faults, simulate
from app.db.models import AuditLog

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
