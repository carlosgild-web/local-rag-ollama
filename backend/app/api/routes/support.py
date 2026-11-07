"""Simulated L2 service-desk incidents (ServiceNow-style).

GET  /api/support/draft    a prefilled incident: caller, computer, versions,
                           suggested impact/urgency/priority, problems found
POST /api/support/tickets  submits it: assigns an INC number, priority from
                           the impact/urgency matrix and a response target

This app never calls a third-party service at runtime (CLAUDE.md), so
"submitting" saves the incident a real integration would send under
DATA_DIR/support/<number>.json and records it in the audit log. Nothing
leaves the machine. Incidents never contain document or chat text.
"""

import datetime as dt
import getpass
import json
import platform
import socket
import sys

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import SupportDraftOut, SupportTicketIn, SupportTicketOut
from app.core.diagnostics import Report, run_diagnostics
from app.core.runtime import Runtime
from app.db.models import IngestJob, utcnow
from app.versioning.service import audit_event

router = APIRouter(tags=["support"])

RECENT_FAILED_JOBS = 10
ASSIGNMENT_GROUP = "L2 Application Support"
CATEGORY = "Software"
SUBCATEGORY = "Local RAG application"

# ServiceNow's default priority matrix: (impact, urgency) -> priority.
PRIORITY = {
    (1, 1): 1, (1, 2): 2, (1, 3): 3,
    (2, 1): 2, (2, 2): 3, (2, 3): 4,
    (3, 1): 3, (3, 2): 4, (3, 3): 5,
}  # fmt: skip
PRIORITY_LABEL = {
    1: "1 - Critical",
    2: "2 - High",
    3: "3 - Moderate",
    4: "4 - Low",
    5: "5 - Planning",
}
RESPONSE_TARGET = {1: dt.timedelta(minutes=30), 2: dt.timedelta(hours=1), 3: dt.timedelta(hours=4),
                   4: dt.timedelta(hours=8), 5: dt.timedelta(days=2)}  # fmt: skip
NUMBER_START = 10001


def _environment(request: Request, runtime: Runtime) -> dict:
    settings = runtime.settings
    computer = settings.support_computer_name or socket.gethostname()
    return {
        "computer_name": computer,
        "user_name": settings.support_user_name or _user_name(),
        "os": platform.platform(),
        "app_version": request.app.version,
        "python": sys.version.split()[0],
        "configuration_item": f"Local RAG on {computer}",
        "ollama_base_url": settings.ollama_base_url,
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "data_dir": str(settings.data_dir),
    }


def _user_name() -> str:
    try:
        return getpass.getuser()
    except Exception:  # no user name in some containers
        return "unknown"


def _diagnose(request: Request, runtime: Runtime, db) -> Report:
    worker = getattr(request.app.state, "worker", None)
    report = run_diagnostics(runtime, db, worker_running=bool(worker and worker.is_running))
    db.rollback()  # diagnostics only read; start clean before any write
    return report


def _problems(report: Report) -> list[dict]:
    return [
        {"title": c.title, "status": c.status, "detail": c.detail, "cause": c.cause, "fix": c.fix}
        for c in report.checks
        if c.status in ("fail", "warn")
    ]


def _suggest(report: Report) -> tuple[int, int, str]:
    """Impact and urgency from what the checks found, plus a short description."""
    failed = [c for c in report.checks if c.status == "fail"]
    warned = [c for c in report.checks if c.status == "warn"]
    core_down = any(c.component in ("sqlite", "vector_store") for c in failed)
    if core_down:
        impact, urgency = 2, 1  # the app can't be used at all
    elif failed:
        impact, urgency = 2, 2  # part of the app is down (e.g. no answers)
    elif warned:
        impact, urgency = 3, 3
    else:
        impact, urgency = 3, 3
    first = (failed or warned or [None])[0]
    if first is None:
        summary = "Local RAG: question for support"
    else:
        state = "failing" if first.status == "fail" else "warning"
        more = len(failed) + len(warned) - 1
        summary = f"Local RAG: check '{first.title}' is {state}" + (
            f" (+{more} more)" if more else ""
        )
    return impact, urgency, summary[:160]


@router.get("/support/draft", response_model=SupportDraftOut)
def ticket_draft(request: Request, db: DbDep, runtime: RuntimeDep):
    """A prefilled incident for the user to review and complete."""
    report = _diagnose(request, runtime, db)
    impact, urgency, summary = _suggest(report)
    priority = PRIORITY[(impact, urgency)]
    return SupportDraftOut(
        environment=_environment(request, runtime),
        category=CATEGORY,
        subcategory=SUBCATEGORY,
        assignment_group=ASSIGNMENT_GROUP,
        impact=impact,
        urgency=urgency,
        priority=PRIORITY_LABEL[priority],
        short_description=summary,
        system_status=report.status,
        problems=_problems(report),
        simulated_faults=report.simulated,
    )


def _next_number(runtime: Runtime) -> str:
    folder = runtime.settings.support_dir
    existing = (
        [int(p.stem[3:]) for p in folder.glob("INC*.json") if p.stem[3:].isdigit()]
        if folder.exists()
        else []
    )
    return f"INC{max(existing, default=NUMBER_START - 1) + 1:07d}"


@router.post(
    "/support/tickets", status_code=status.HTTP_201_CREATED, response_model=SupportTicketOut
)
def submit_ticket(request: Request, db: DbDep, runtime: RuntimeDep, body: SupportTicketIn):
    """Files the incident (simulated: saved locally, never sent)."""
    report = _diagnose(request, runtime, db)
    environment = _environment(request, runtime)
    priority = PRIORITY[(body.impact, body.urgency)]
    opened = utcnow()
    number = _next_number(runtime)
    failed_jobs = db.execute(
        select(IngestJob)
        .where(IngestJob.status == "failed")
        .order_by(IngestJob.id.desc())
        .limit(RECENT_FAILED_JOBS)
    ).scalars()

    incident = {
        "number": number,
        "simulated": True,
        "state": "New",
        "opened_at": opened.isoformat(),
        "response_due": (opened + RESPONSE_TARGET[priority]).isoformat(),
        "caller": {
            "name": body.caller_name.strip(),
            "contact": (body.contact or "").strip() or None,
            "best_time_to_contact": (body.best_time_to_contact or "").strip() or None,
        },
        "category": CATEGORY,
        "subcategory": SUBCATEGORY,
        "configuration_item": environment["configuration_item"],
        "assignment_group": ASSIGNMENT_GROUP,
        "impact": body.impact,
        "urgency": body.urgency,
        "priority": PRIORITY_LABEL[priority],
        "short_description": body.short_description.strip(),
        "description": body.description.strip(),
        "user_details": {
            "started_at": (body.started_at or "").strip() or None,
            "recent_changes": (body.recent_changes or "").strip() or None,
            "users_affected": (body.users_affected or "").strip() or None,
            "steps_to_reproduce": (body.steps_to_reproduce or "").strip() or None,
        },
        "environment": environment,
        "work_notes": {
            "system_status": report.status,
            "problems": _problems(report),
            "simulated_faults": report.simulated,
            "recent_failed_jobs": [
                {
                    "id": j.id,
                    "type": j.job_type,
                    "error": j.error,
                    "updated_at": j.updated_at.isoformat(),
                }
                for j in failed_jobs
            ],
        },
        "attachments": {"diagnostics.json": report.to_dict()},
    }
    incident = json.loads(json.dumps(incident, default=str))

    runtime.settings.support_dir.mkdir(parents=True, exist_ok=True)
    path = runtime.settings.support_dir / f"{number}.json"
    path.write_text(json.dumps(incident, indent=2, ensure_ascii=False), encoding="utf-8")
    audit_event(
        db, "support_ticket", "support", None, f"{number} {PRIORITY_LABEL[priority]} (simulated)"
    )

    return SupportTicketOut(number=number, saved_to=str(path), incident=incident)
