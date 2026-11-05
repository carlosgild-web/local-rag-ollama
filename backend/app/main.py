"""FastAPI app factory.

Run with exactly one uvicorn worker (embedded Chroma and SQLite are
single-writer): `uvicorn app.main:app --port 8000`.
"""

from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import chat, collections, documents, jobs, models, ops, profiles, retrieval
from app.core.config import get_settings
from app.core.runtime import Runtime, build_runtime
from app.ingest.uploads import UnsupportedUploadError, UploadTooLargeError
from app.jobs.worker import JobWorker
from app.versioning.profiles import InvalidProfileError
from app.versioning.service import ConflictError, NotFoundError

API_PREFIX = "/api"

_ERROR_STATUS = {
    NotFoundError: 404,
    ConflictError: 409,
    InvalidProfileError: 422,
    UploadTooLargeError: 413,
    UnsupportedUploadError: 415,
}


def create_app(runtime: Runtime | None = None, *, start_worker: bool = True) -> FastAPI:
    """`runtime` defaults to the real one built from env settings; tests pass
    a fake one and `start_worker=False`, then drain jobs with
    `app.state.worker.run_until_idle()`."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime or build_runtime(get_settings())
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
        version="0.3.0",
        description="Fully local retrieval-augmented generation: documents, versions, chat.",
        lifespan=lifespan,
    )

    api = APIRouter(prefix=API_PREFIX)
    for module in (documents, collections, chat, retrieval, jobs, models, profiles, ops):
        api.include_router(module.router)
    app.include_router(api)
    # Unprefixed alias for container health checks.
    app.add_api_route("/health", ops.health, methods=["GET"], include_in_schema=False)

    for exc_type, status_code in _ERROR_STATUS.items():
        app.add_exception_handler(exc_type, _error_handler(status_code))
    app.add_exception_handler(httpx.HTTPError, _ollama_error)
    return app


def _error_handler(status_code: int):
    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


async def _ollama_error(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=502, content={"detail": f"Ollama request failed: {type(exc).__name__}: {exc}"}
    )


app = create_app()
