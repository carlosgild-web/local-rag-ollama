"""Simulated L2 support tickets (POST /api/support/tickets).

The troubleshooter can "send the details to L2 support". This app never
calls a third-party service at runtime (CLAUDE.md), so the ticket is a
report saved under DATA_DIR/support/ with a ticket number: what a real
integration would send. Nothing leaves the machine. The report holds check
results, versions, settings and recent job errors, never document text.
"""

import json
import platform
import secrets
import sys

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import SupportTicketIn, SupportTicketOut
from app.core.diagnostics import run_diagnostics
from app.db.models import IngestJob, utcnow
from app.versioning.service import audit_event

router = APIRouter(tags=["support"])

RECENT_FAILED_JOBS = 10


@router.post(
    "/support/tickets", status_code=status.HTTP_201_CREATED, response_model=SupportTicketOut
)
def create_ticket(request: Request, db: DbDep, runtime: RuntimeDep, body: SupportTicketIn):
    settings = runtime.settings
    worker = getattr(request.app.state, "worker", None)
    diagnostics = run_diagnostics(runtime, db, worker_running=bool(worker and worker.is_running))
    db.rollback()  # diagnostics only read; start clean before writing the audit entry

    now = utcnow()
    ticket_id = f"L2-{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"
    failed_jobs = db.execute(
        select(IngestJob)
        .where(IngestJob.status == "failed")
        .order_by(IngestJob.id.desc())
        .limit(RECENT_FAILED_JOBS)
    ).scalars()
    report = {
        "ticket_id": ticket_id,
        "simulated": True,
        "created_at": now.isoformat(),
        "user_note": (body.note or "").strip() or None,
        "app": {
            "version": request.app.version,
            "python": sys.version.split()[0],
            "os": platform.platform(),
        },
        "settings": {
            "ollama_base_url": settings.ollama_base_url,
            "chat_model": settings.chat_model,
            "embedding_model": settings.embedding_model,
            "data_dir": str(settings.data_dir),
            "simulate_faults": settings.simulate_faults or None,
        },
        "troubleshooter": diagnostics.to_dict(),
        "recent_failed_jobs": [
            {
                "id": job.id,
                "type": job.job_type,
                "error": job.error,
                "updated_at": job.updated_at.isoformat(),
            }
            for job in failed_jobs
        ],
    }
    problems = sum(c.status in ("fail", "warn") for c in diagnostics.checks)

    settings.support_dir.mkdir(parents=True, exist_ok=True)
    path = settings.support_dir / f"{ticket_id}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    audit_event(
        db, "support_ticket", "support", None, f"{ticket_id} (simulated), {problems} problem(s)"
    )

    return SupportTicketOut(
        ticket_id=ticket_id,
        created_at=now,
        simulated=True,
        saved_to=str(path),
        status=diagnostics.status,
        problems=problems,
        report=json.loads(json.dumps(report, default=str)),
    )
