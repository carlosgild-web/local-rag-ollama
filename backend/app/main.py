"""FastAPI app factory.

Run with exactly one uvicorn worker (embedded Chroma and SQLite are
single-writer): `uvicorn app.main:app --port 8000`.
"""

from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import (
    chat,
    collections,
    demo,
    documents,
    jobs,
    models,
    ops,
    profiles,
    retrieval,
    support,
)
from app.api.routes import (
    intake as intake_routes,
)
from app.api.static import find_static_dir, mount_frontend
from app.core.config import get_settings
from app.core.logging import RequestIdMiddleware, configure_logging
from app.core.runtime import Runtime, build_runtime
from app.ingest import intake
from app.ingest.uploads import EmptyUploadError, UnsupportedUploadError, UploadTooLargeError
from app.jobs.worker import JobWorker
from app.versioning.profiles import InvalidProfileError
from app.versioning.service import ConflictError, NotFoundError

API_PREFIX = "/api"

_ERROR_STATUS = {
    NotFoundError: 404,
    ConflictError: 409,
    InvalidProfileError: 422,
    UploadTooLargeError: 413,
    EmptyUploadError: 422,
    UnsupportedUploadError: 415,
}


def _schedule_daily_backup(runtime: Runtime) -> None:
    """Queues an automatic backup when the newest one is a day old or missing, and the
    library has something in it (decision 0015). BACKUP_KEEP=0 turns it off."""
    from sqlalchemy import func, select

    from app.db import backup
    from app.db.models import Document, IngestJob
    from app.jobs import queue

    settings = runtime.settings
    if settings.backup_keep <= 0:
        return
    age = backup.latest_automatic_age_hours(settings)
    if age is not None and age < 24:
        return
    with runtime.session_factory() as db:
        if not db.execute(select(func.count(Document.id))).scalar_one():
            return
        waiting = db.execute(
            select(func.count(IngestJob.id)).where(
                IngestJob.job_type == "backup", IngestJob.status.in_(("pending", "running"))
            )
        ).scalar_one()
        if not waiting:
            queue.enqueue(db, "backup", {"reason": "auto"})


def create_app(runtime: Runtime | None = None, *, start_worker: bool = True) -> FastAPI:
    """`runtime` defaults to the real one built from env settings; tests pass
    a fake one and `start_worker=False`, then drain jobs with
    `app.state.worker.run_until_idle()`."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if runtime is None:
            # Real server: JSON logs (tests keep pytest's log capture).
            settings = get_settings()
            configure_logging(settings.log_level)
            app.state.runtime = build_runtime(settings)
        else:
            app.state.runtime = runtime
        # Staged intake batches nobody confirmed or cancelled expire after a day.
        intake.purge_stale_batches(app.state.runtime.settings)
        _schedule_daily_backup(app.state.runtime)
        app.state.worker = JobWorker(app.state.runtime)
        if start_worker:
            app.state.worker.start()
        try:
            yield
        finally:
            app.state.worker.stop()
            app.state.runtime.engine.dispose()

    app = FastAPI(
        title="Local RAG with Ollama",
        version=__version__,
        description="Fully local retrieval-augmented generation: documents, versions, chat.",
        lifespan=lifespan,
    )

    api = APIRouter(prefix=API_PREFIX)
    for module in (
        documents,
        intake_routes,
        collections,
        chat,
        retrieval,
        jobs,
        models,
        profiles,
        ops,
        support,
        demo,
    ):
        api.include_router(module.router)
    app.include_router(api)
    # Unprefixed alias for container health checks.
    app.add_api_route("/health", ops.health, methods=["GET"], include_in_schema=False)

    for exc_type, status_code in _ERROR_STATUS.items():
        app.add_exception_handler(exc_type, _error_handler(status_code))
    app.add_exception_handler(httpx.HTTPError, _ollama_error)
    app.add_middleware(RequestIdMiddleware)
    _patch_openapi_file_fields(app)

    # Last, so the catch-all never shadows the API, /docs or /health.
    settings = runtime.settings if runtime is not None else get_settings()
    static_dir = find_static_dir(settings.static_dir)
    if static_dir is not None:
        mount_frontend(app, static_dir, api_prefix=API_PREFIX)
    return app


def _patch_openapi_file_fields(app: FastAPI) -> None:
    """FastAPI describes uploads the OpenAPI 3.1 way (`contentMediaType`),
    which Swagger UI renders as a text box instead of a file picker. Adding
    `format: binary` keeps the schema valid and brings the picker back."""
    generate = app.openapi

    def openapi():
        if app.openapi_schema is None:
            schema = generate()
            _add_binary_format(schema)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi


def _add_binary_format(node) -> None:
    if isinstance(node, dict):
        if (
            node.get("type") == "string"
            and node.get("contentMediaType") == "application/octet-stream"
        ):
            node.setdefault("format", "binary")
        for value in node.values():
            _add_binary_format(value)
    elif isinstance(node, list):
        for value in node:
            _add_binary_format(value)


def _error_handler(status_code: int):
    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


async def _ollama_error(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=502, content={"detail": f"Ollama request failed: {type(exc).__name__}: {exc}"}
    )


app = create_app()
