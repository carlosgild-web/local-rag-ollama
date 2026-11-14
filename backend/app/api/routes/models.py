"""Ollama model manager (PLAN.md section 8). Pull progress streams as SSE:
`progress` events carry Ollama's own {status, total, completed} objects,
then `done` or `error`. A model a profile or shelf uses can't be deleted
(app/versioning/model_usage.py)."""

from collections.abc import Iterator

from fastapi import APIRouter, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import ModelOut, ModelPullIn
from app.api.sse import SSE_HEADERS, drive_sync_stream, sse
from app.core.runtime import Runtime
from app.versioning import model_usage, service

router = APIRouter(tags=["models"])


@router.get("/models", response_model=list[ModelOut])
def list_models(db: DbDep, runtime: RuntimeDep):
    """The models Ollama has, with what uses each one and whether it's loaded."""
    models = runtime.ollama.list_models()
    uses = model_usage.model_uses(db, runtime.settings)
    try:
        loaded = {model_usage.same_model(n) for n in runtime.ollama.loaded_models()}
    except Exception:  # /api/ps is only a hint; the list still works without it
        loaded = set()
    for model in models:
        key = model_usage.same_model(model["name"])
        model["used_by"] = uses.get(key, [])
        model["loaded"] = key in loaded
    return models


@router.post(
    "/models/pull",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream"}},
)
def pull_model(runtime: RuntimeDep, body: ModelPullIn):
    return StreamingResponse(
        drive_sync_stream(_pull_stream(runtime, body.name)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _pull_stream(runtime: Runtime, name: str) -> Iterator[str]:
    try:
        last = {}
        for last in runtime.ollama.pull(name):
            if "error" in last:
                yield sse("error", {"detail": last["error"]})
                return
            yield sse("progress", last)
    except Exception as exc:
        yield sse("error", {"detail": f"pull failed: {type(exc).__name__}: {exc}"})
        return

    with runtime.session_factory() as db:
        service.audit_event(db, "model_pull", "model", None, name)
    yield sse("done", {"name": name, "status": last.get("status", "success")})


@router.delete("/models/{name:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(db: DbDep, runtime: RuntimeDep, name: str):
    """Refused (409) while a profile or shelf uses the model."""
    uses = model_usage.uses_of(db, runtime.settings, name)
    if uses:
        raise service.ConflictError(f"{name} is in use: {'; '.join(uses)}")
    if not runtime.ollama.delete(name):
        raise service.NotFoundError(f"model {name!r} not found")
    service.audit_event(db, "model_delete", "model", None, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
