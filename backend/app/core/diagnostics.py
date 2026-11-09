# ruff: noqa: E501  (user-facing help text reads better unwrapped)
"""Troubleshooter: checks each part of the app and explains, in plain words,
what is wrong, the likely cause, and what to do (GET /api/diagnostics).

Every check returns ok / warn / fail / skip. A failed prerequisite (Ollama
unreachable, database closed) turns the checks that depend on it into
"skip", so the user sees the root cause first instead of a cascade. Faults
can be simulated with SIMULATE_FAULTS (app/core/faults.py).
"""

import datetime as dt
import shutil
from dataclasses import asdict, dataclass, field
from typing import Literal

from sqlalchemy import func, select, text

from app.core.faults import SimulatedFault, active_faults, simulate
from app.core.runtime import Runtime
from app.core.sysinfo import free_memory_bytes
from app.db.migrate import head_revision
from app.db.models import Chunk, Collection, IngestJob, RagProfile, utcnow

Status = Literal["ok", "warn", "fail", "skip"]

# /api/embed arrived in 0.3.x; model capabilities in /api/show in 0.6.
MIN_OLLAMA_VERSION = (0, 6, 0)
LOW_DISK_BYTES = 1024**3
STUCK_JOB_MINUTES = 30
GB = 1024**3


@dataclass
class Action:
    """Something the UI can offer as a button next to a check."""

    kind: Literal["pull_model", "reindex_collection", "open_queue", "open_collections"]
    label: str
    target: str | None = None


@dataclass
class Check:
    id: str
    component: Literal["ollama", "sqlite", "vector_store", "jobs"]
    title: str
    status: Status
    detail: str
    cause: str | None = None
    fix: str | None = None
    commands: list[str] = field(default_factory=list)
    action: Action | None = None


@dataclass
class Report:
    status: Literal["ok", "warn", "fail"]
    checks: list[Check]
    simulated: list[str]
    ran_at: dt.datetime

    def to_dict(self) -> dict:
        return asdict(self)


def _base(name: str) -> str:
    return name.removesuffix(":latest")


def _version_tuple(version: str) -> tuple[int, ...] | None:
    parts = version.split("-")[0].split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError:
        return None


def _error(exc: Exception) -> str:
    return str(exc) if isinstance(exc, SimulatedFault) else f"{type(exc).__name__}: {exc}"


# --- Ollama ---------------------------------------------------------------


def _ollama_checks(runtime: Runtime, chat_model: str, embedding_models: dict[str, list[str]]):
    settings = runtime.settings
    url = settings.ollama_base_url
    checks: list[Check] = []

    try:
        simulate(settings.simulate_faults, "ollama_down")
        version = runtime.ollama.ping()
    except Exception as exc:
        checks.append(
            Check(
                id="ollama.reachable",
                component="ollama",
                title="Ollama is reachable",
                status="fail",
                detail=f"No answer from Ollama at {url}: {_error(exc)}",
                cause="Ollama isn't running, or OLLAMA_BASE_URL points to the wrong address.",
                fix=(
                    "Start Ollama: on Windows or macOS open the Ollama app, on Linux run "
                    "`ollama serve`. In Docker, check that the ollama container is up, or "
                    "use compose.host-ollama.yaml to reach the Ollama on your machine. "
                    f"If Ollama runs elsewhere, set OLLAMA_BASE_URL (now {url})."
                ),
                commands=["ollama serve", "ollama list"],
            )
        )
        for check_id, title in [
            ("ollama.version", "Ollama version is supported"),
            ("ollama.models", "Required models are installed"),
            ("ollama.memory", "Enough free memory for the chat model"),
        ]:
            checks.append(
                Check(check_id, "ollama", title, "skip", "Not checked: Ollama is unreachable.")
            )
        return checks

    checks.append(
        Check(
            "ollama.reachable", "ollama", "Ollama is reachable", "ok", f"Version {version} at {url}"
        )
    )

    simulated_version = "ollama_version" in active_faults(settings.simulate_faults)
    if simulated_version:
        version = "0.1.32"
    parsed = _version_tuple(version)
    if simulated_version:
        version += " (simulated)"
    minimum = ".".join(map(str, MIN_OLLAMA_VERSION))
    if parsed is None or parsed < MIN_OLLAMA_VERSION:
        checks.append(
            Check(
                id="ollama.version",
                component="ollama",
                title="Ollama version is supported",
                status="fail" if parsed is not None else "warn",
                detail=f"Ollama reports version {version}; this app needs {minimum} or newer.",
                cause=(
                    "An older Ollama lacks the endpoints the app uses for embeddings and "
                    "for telling embedding models from chat models."
                ),
                fix="Update Ollama from https://ollama.com/download, then restart it.",
                commands=["ollama --version"],
            )
        )
    else:
        checks.append(
            Check(
                "ollama.version",
                "ollama",
                "Ollama version is supported",
                "ok",
                f"{version} (needs {minimum}+)",
            )
        )

    try:
        models = runtime.ollama.list_models()
    except Exception as exc:
        checks.append(
            Check("ollama.models", "ollama", "Required models are installed", "fail", _error(exc))
        )
        return checks
    installed = {_base(m["name"]): m for m in models}
    simulated_missing = "model_missing" in active_faults(settings.simulate_faults)
    if simulated_missing:
        installed.pop(_base(chat_model), None)

    needed: list[tuple[str, str, str]] = [
        (chat_model, "completion", "chat model (answers questions)")
    ]
    needed += [
        (model, "embedding", f"embedding model of shelf {', '.join(shelves)}")
        for model, shelves in embedding_models.items()
    ]
    problems = 0
    for model, role, purpose in needed:
        found = installed.get(_base(model))
        if found is None:
            problems += 1
            checks.append(
                Check(
                    id=f"ollama.model.{_base(model)}",
                    component="ollama",
                    title=f"{model} is installed",
                    status="fail",
                    detail=f"{model} is the {purpose}, but Ollama doesn't have it."
                    + (" (simulated)" if simulated_missing and model == chat_model else ""),
                    cause="The model was never downloaded, or it was removed.",
                    fix=f"Download it (a few GB, once). Until then {'answers' if role == 'completion' else 'uploads and search on that shelf'} will fail.",
                    commands=[f"ollama pull {model}"],
                    action=Action("pull_model", f"Download {model}", model),
                )
            )
            continue
        capabilities = found.get("capabilities") or []
        if capabilities and role not in capabilities:
            problems += 1
            wrong = "a chat model" if role == "embedding" else "an embedding model"
            checks.append(
                Check(
                    id=f"ollama.model.{_base(model)}",
                    component="ollama",
                    title=f"{model} can do its job",
                    status="fail",
                    detail=f"{model} is used as the {purpose}, but it is {wrong} ({', '.join(capabilities)}).",
                    cause="The wrong kind of model was chosen in the settings.",
                    fix=(
                        "Rebuild the shelf with an embedding model such as bge-m3 (Collections → Change)."
                        if role == "embedding"
                        else "Choose a chat model (e.g. qwen2.5:3b or llama3.1) for the RAG profile."
                    ),
                    action=Action("open_collections", "Open Collections")
                    if role == "embedding"
                    else None,
                )
            )
    if problems == 0:
        checks.append(
            Check(
                "ollama.models",
                "ollama",
                "Required models are installed",
                "ok",
                ", ".join(sorted({m for m, _, _ in needed})),
            )
        )

    checks.append(_memory_check(runtime, chat_model, installed))
    return checks


def _memory_check(runtime: Runtime, chat_model: str, installed: dict) -> Check:
    title = "Enough free memory for the chat model"
    try:
        loaded = {_base(m) for m in runtime.ollama.loaded_models()}
    except Exception:
        loaded = set()
    if _base(chat_model) in loaded:
        return Check(
            "ollama.memory", "ollama", title, "ok", f"{chat_model} is already loaded in memory."
        )
    if _base(chat_model) not in installed:
        return Check(
            "ollama.memory", "ollama", title, "skip", f"Not checked: {chat_model} isn't installed."
        )
    size = (installed.get(_base(chat_model)) or {}).get("size")
    free = free_memory_bytes()
    if "low_memory" in active_faults(runtime.settings.simulate_faults):
        free = int(0.4 * GB)
    if free is None or not size:
        return Check(
            "ollama.memory",
            "ollama",
            title,
            "skip",
            "Free memory or model size unknown on this system.",
        )
    needed = int(size * 1.3)  # weights plus context buffers
    detail = f"{free / GB:.1f} GB free; {chat_model} needs about {needed / GB:.1f} GB to load."
    if "low_memory" in active_faults(runtime.settings.simulate_faults):
        detail += " (simulated)"
    if free >= needed:
        return Check("ollama.memory", "ollama", title, "ok", detail)
    return Check(
        id="ollama.memory",
        component="ollama",
        title=title,
        status="warn",
        detail=detail,
        cause="Other programs (browsers, Docker Desktop, IDEs) are using the memory the model needs.",
        fix=(
            "Close programs you don't need (browser tabs first) and ask again. If it keeps "
            f"failing, use a smaller chat model than {chat_model}, e.g. "
            f"{'qwen2.5:3b' if size > 3 * GB else 'qwen2.5:1.5b'} "
            "(set CHAT_MODEL in backend/.env and restart the app)."
        ),
    )


# --- SQLite ------------------------------------------------------------------


def _sqlite_checks(runtime: Runtime, db) -> tuple[list[Check], bool]:
    settings = runtime.settings
    checks: list[Check] = []
    try:
        simulate(settings.simulate_faults, "sqlite")
        db.execute(text("SELECT 1")).scalar_one()
    except Exception as exc:
        checks.append(
            Check(
                id="sqlite.open",
                component="sqlite",
                title="Database opens",
                status="fail",
                detail=f"{settings.db_path}: {_error(exc)}",
                cause=(
                    "The database file is missing, locked by another program, on a full or "
                    "read-only disk, or the app has no permission to open it."
                ),
                fix=(
                    "Close other programs using the file (a second copy of the app, a database "
                    "viewer), check free disk space and permissions on DATA_DIR, then restart "
                    "the app. If the file is damaged, restore it from a backup."
                ),
            )
        )
        for check_id, title in [
            ("sqlite.integrity", "Database is not damaged"),
            ("sqlite.schema", "Database schema is up to date"),
            ("sqlite.fts", "Keyword search index is healthy"),
        ]:
            checks.append(
                Check(
                    check_id, "sqlite", title, "skip", "Not checked: the database can't be opened."
                )
            )
        checks.append(_disk_check(settings))
        return checks, False

    checks.append(Check("sqlite.open", "sqlite", "Database opens", "ok", str(settings.db_path)))

    result = db.execute(text("PRAGMA quick_check")).scalar_one()
    if result == "ok":
        checks.append(
            Check("sqlite.integrity", "sqlite", "Database is not damaged", "ok", "quick_check: ok")
        )
    else:
        checks.append(
            Check(
                id="sqlite.integrity",
                component="sqlite",
                title="Database is not damaged",
                status="fail",
                detail=f"quick_check: {result}",
                cause="The file was damaged, e.g. by a crash or power loss during a write, or a disk error.",
                fix="Stop the app and restore app.db from a backup. Keep a copy of the damaged file.",
            )
        )

    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    head = head_revision()
    if current == head:
        checks.append(
            Check(
                "sqlite.schema", "sqlite", "Database schema is up to date", "ok", f"revision {head}"
            )
        )
    else:
        checks.append(
            Check(
                id="sqlite.schema",
                component="sqlite",
                title="Database schema is up to date",
                status="fail",
                detail=f"The database is at revision {current}; this version of the app expects {head}.",
                cause="The app was updated but the database migration hasn't run, or it failed.",
                fix="Restart the app: migrations run on startup. If that fails, check the server log.",
                commands=["cd backend && .venv/Scripts/python -m alembic upgrade head"],
            )
        )

    try:
        db.execute(text("INSERT INTO chunks_fts (chunks_fts) VALUES ('integrity-check')"))
        checks.append(
            Check(
                "sqlite.fts",
                "sqlite",
                "Keyword search index is healthy",
                "ok",
                "integrity-check passed",
            )
        )
    except Exception as exc:
        checks.append(
            Check(
                id="sqlite.fts",
                component="sqlite",
                title="Keyword search index is healthy",
                status="fail",
                detail=_error(exc),
                cause="The keyword index is out of step with the stored passages.",
                fix="Reindex the affected shelf (Collections → Reindex) to rebuild it.",
                action=Action("open_collections", "Open Collections"),
            )
        )
    finally:
        db.rollback()

    checks.append(_disk_check(settings))
    return checks, True


def _disk_check(settings) -> Check:
    title = "Enough free disk space"
    try:
        free = shutil.disk_usage(settings.data_dir).free
    except OSError as exc:
        return Check("sqlite.disk", "sqlite", title, "skip", f"Couldn't read disk usage: {exc}")
    detail = f"{free / GB:.1f} GB free in {settings.data_dir}"
    if free >= LOW_DISK_BYTES:
        return Check("sqlite.disk", "sqlite", title, "ok", detail)
    return Check(
        id="sqlite.disk",
        component="sqlite",
        title=title,
        status="fail" if free < LOW_DISK_BYTES / 5 else "warn",
        detail=detail,
        cause="Uploads, the database and the search index need room to grow.",
        fix="Free up disk space, or move DATA_DIR to a larger disk.",
    )


# --- Vector store -------------------------------------------------------------


def _vector_checks(runtime: Runtime, db, collections: list[Collection], db_ok: bool) -> list[Check]:
    settings = runtime.settings
    checks: list[Check] = []
    try:
        simulate(settings.simulate_faults, "vector_store")
        runtime.vector_store.ping()
    except Exception as exc:
        checks.append(
            Check(
                id="vector.open",
                component="vector_store",
                title="Vector store answers",
                status="fail",
                detail=f"{settings.chroma_dir}: {_error(exc)}",
                cause=(
                    "The Chroma files under DATA_DIR/chroma are missing, locked by another copy "
                    "of the app, or damaged."
                ),
                fix=(
                    "Make sure only one copy of the app is running, then restart it. If the files "
                    "are damaged, restore DATA_DIR/chroma from a backup, or reindex every shelf "
                    "to rebuild them from the stored documents."
                ),
            )
        )
        return checks
    checks.append(
        Check("vector.open", "vector_store", "Vector store answers", "ok", str(settings.chroma_dir))
    )
    if not db_ok:
        checks.append(
            Check(
                "vector.shelves",
                "vector_store",
                "Search index matches each shelf",
                "skip",
                "Not checked: the database can't be opened.",
            )
        )
        return checks

    for collection in collections:
        title = f"Search index of shelf '{collection.name}' is complete"
        expected = db.execute(
            select(func.count(Chunk.id)).where(
                Chunk.collection_id == collection.id, Chunk.retired_at.is_(None)
            )
        ).scalar_one()
        action = Action("reindex_collection", f"Reindex '{collection.name}'", str(collection.id))
        try:
            actual = runtime.vector_store.count(collection.chroma_collection)
        except Exception as exc:
            checks.append(
                Check(
                    id=f"vector.shelf.{collection.id}",
                    component="vector_store",
                    title=title,
                    status="fail",
                    detail=f"The index '{collection.chroma_collection}' is missing: {_error(exc)}",
                    cause="The vector files were deleted or replaced, e.g. by restoring only part of a backup.",
                    fix="Reindex the shelf to rebuild its search index from the stored documents.",
                    action=action,
                )
            )
            continue
        if actual == expected:
            checks.append(
                Check(
                    f"vector.shelf.{collection.id}",
                    "vector_store",
                    title,
                    "ok",
                    f"{actual} passages",
                )
            )
        else:
            checks.append(
                Check(
                    id=f"vector.shelf.{collection.id}",
                    component="vector_store",
                    title=title,
                    status="warn",
                    detail=f"{actual} passages in the search index, {expected} in the database.",
                    cause="An indexing job was interrupted, or the index files are from another time than the database.",
                    fix="Reindex the shelf; answers may miss documents until then.",
                    action=action,
                )
            )
    return checks


# --- Jobs ---------------------------------------------------------------------


def _job_checks(runtime: Runtime, db, worker_running: bool, db_ok: bool) -> list[Check]:
    checks: list[Check] = []
    try:
        simulate(runtime.settings.simulate_faults, "worker")
        if not worker_running:
            raise RuntimeError("the worker thread has stopped")
        checks.append(
            Check(
                "jobs.worker",
                "jobs",
                "Job worker is running",
                "ok",
                "Uploads and reindexing are processed.",
            )
        )
    except Exception as exc:
        checks.append(
            Check(
                id="jobs.worker",
                component="jobs",
                title="Job worker is running",
                status="fail",
                detail=_error(exc),
                cause="The background worker stopped, so uploads and reindexing wait in the queue forever.",
                fix="Restart the app. If it stops again, check the server log for the error.",
            )
        )
    if not db_ok:
        return checks

    failed = db.execute(
        select(func.count(IngestJob.id)).where(IngestJob.status == "failed")
    ).scalar_one()
    if failed:
        checks.append(
            Check(
                id="jobs.failed",
                component="jobs",
                title="No failed jobs",
                status="warn",
                detail=f"{failed} job{'s' if failed != 1 else ''} failed.",
                cause="Usually a file that can't be read, or Ollama being unavailable at the time.",
                fix="Open the Queue to see each error; retry once the cause is fixed.",
                action=Action("open_queue", "Open the Queue"),
            )
        )
    else:
        checks.append(Check("jobs.failed", "jobs", "No failed jobs", "ok", "None failed."))

    cutoff = utcnow() - dt.timedelta(minutes=STUCK_JOB_MINUTES)
    stuck = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.status == "running", IngestJob.updated_at < cutoff
        )
    ).scalar_one()
    if stuck:
        checks.append(
            Check(
                id="jobs.stuck",
                component="jobs",
                title="No job is stuck",
                status="warn",
                detail=f"{stuck} job{'s' if stuck != 1 else ''} running for over {STUCK_JOB_MINUTES} minutes without progress.",
                cause="A very large document, or Ollama stopped answering in the middle of a job.",
                fix="Check that Ollama is running. Restarting the app puts interrupted jobs back in the queue.",
                action=Action("open_queue", "Open the Queue"),
            )
        )
    return checks


# --- Report -------------------------------------------------------------------


def run_diagnostics(runtime: Runtime, db, *, worker_running: bool) -> Report:
    sqlite_checks, db_ok = _sqlite_checks(runtime, db)

    collections: list[Collection] = []
    chat_model = runtime.settings.chat_model
    if db_ok:
        collections = list(db.execute(select(Collection).where(Collection.is_active)).scalars())
        profile = (
            db.execute(
                select(RagProfile)
                .where(RagProfile.is_active, RagProfile.name == "default")
                .order_by(RagProfile.version.desc())
            )
            .scalars()
            .first()
        )
        if profile is not None:
            chat_model = profile.chat_model
    embedding_models: dict[str, list[str]] = {}
    for c in collections:
        embedding_models.setdefault(c.embedding_model, []).append(c.name)
    if not embedding_models:
        embedding_models[runtime.settings.embedding_model] = ["(new shelves)"]

    checks = [
        *_ollama_checks(runtime, chat_model, embedding_models),
        *sqlite_checks,
        *_vector_checks(runtime, db, collections, db_ok),
        *_job_checks(runtime, db, worker_running, db_ok),
    ]
    worst = (
        "fail"
        if any(c.status == "fail" for c in checks)
        else ("warn" if any(c.status == "warn" for c in checks) else "ok")
    )
    return Report(
        status=worst,
        checks=checks,
        simulated=sorted(active_faults(runtime.settings.simulate_faults)),
        ran_at=utcnow(),
    )
