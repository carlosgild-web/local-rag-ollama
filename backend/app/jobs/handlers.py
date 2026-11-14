"""One handler per job type. Each takes the worker's session, the payload,
the runtime, and a progress callback, and returns a JSON-able result. All
writes go through the versioning service (invariant 1)."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.runtime import Runtime
from app.db import backup
from app.eval import service as eval_service
from app.ingest import intake
from app.ingest.uploads import discard_staged
from app.versioning import demo, service
from app.versioning.service import ProgressCallback

Handler = Callable[[Session, dict, Runtime, ProgressCallback], dict]


def handle_ingest(db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback) -> dict:
    staged = Path(payload["staged_path"])
    if not staged.exists():
        raise FileNotFoundError(f"staged upload {staged.name!r} is gone; upload it again")

    into = payload.get("document_id")  # a near-duplicate merged into this document
    if into is not None:
        payload = {**payload, "collection_id": service.get_document(db, into).collection_id}
    collection = service.get_collection(db, payload["collection_id"])
    if not collection.is_active:
        # A blue/green swap happened while this job waited: use the live generation.
        collection = service.get_active_collection(db, collection.name) or collection

    progress(0.0)
    result = service.ingest_document(
        db,
        collection=collection,
        source_path=staged,
        filename=payload["filename"],
        tags=payload.get("tags"),
        settings=runtime.settings,
        embedding_client=runtime.embedding_client_for(collection.embedding_model),
        vector_store=runtime.vector_store,
        progress=progress,
        into_document_id=into,
        edited_by=payload.get("edited_by"),
        note=payload.get("note"),
    )
    discard_staged(staged, runtime.settings.uploads_dir)
    return {
        "status": result.status,
        "document_id": result.document_id,
        "version_id": result.version_id,
        "chunk_count": result.chunk_count,
    }


def handle_reindex_document(
    db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback
) -> dict:
    document = service.get_document(db, payload["document_id"])
    collection = service.get_collection(db, document.collection_id)
    progress(0.0)
    result = service.reindex_document(
        db,
        document.id,
        settings=runtime.settings,
        embedding_client=runtime.embedding_client_for(collection.embedding_model),
        vector_store=runtime.vector_store,
    )
    return {"document_id": result.document_id, "chunk_count": result.chunk_count}


def handle_reindex_collection(
    db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback
) -> dict:
    collection = service.get_collection(db, payload["collection_id"])
    results = service.reindex_collection(
        db,
        collection.id,
        settings=runtime.settings,
        embedding_client=runtime.embedding_client_for(collection.embedding_model),
        vector_store=runtime.vector_store,
        progress=progress,
    )
    return {"documents": len(results), "chunk_count": sum(r.chunk_count for r in results)}


def handle_rebuild_collection(
    db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback
) -> dict:
    """Blue/green: build the new generation, then swap it in."""
    source_id = payload["source_collection_id"]
    target = service.get_collection(db, payload["target_collection_id"])
    chunk_count = service.build_collection(
        db,
        source_id,
        target.id,
        settings=runtime.settings,
        embedding_client=runtime.embedding_client_for(target.embedding_model),
        vector_store=runtime.vector_store,
        progress=progress,
    )
    service.swap_collection(db, source_id, target.id)
    return {"active_collection_id": target.id, "chunk_count": chunk_count}


def handle_analyze_intake(
    db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback
) -> dict:
    """Suggest a shelf and tags for each staged file (nothing is indexed)."""
    return intake.analyze_batch(db, runtime, payload["batch_id"], progress)


def handle_seed_demo(
    db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback
) -> dict:
    """Loads the demo company (the same as `app.cli seed-demo`)."""
    progress(0.0)
    results = demo.seed_demo(
        db,
        settings=runtime.settings,
        embedding_client_for=runtime.embedding_client_for,
        vector_store=runtime.vector_store,
        root=demo.DEMO_DIR,
        progress=progress,
    )
    ingested = sum(item.status == "ingested" for item in results)
    return {"ingested": ingested, "skipped": len(results) - ingested}


def handle_backup(db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback) -> dict:
    """A backup zip (decision 0015). Running in the worker means no indexing writes
    to the vector store while it's copied."""
    progress(0.0)
    reason = payload.get("reason", "manual")
    path = backup.create_backup(runtime.settings, reason=reason)
    removed = []
    if reason == "auto":
        removed = backup.prune_automatic(runtime.settings, runtime.settings.backup_keep)
    service.audit_event(db, "backup", "backup", None, f"{path.name} ({reason})")
    return {"name": path.name, "size": path.stat().st_size, "removed": removed}


def handle_purge_trash(
    db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback
) -> dict:
    """Empties the 30-day trash (decision 0018). In the worker: it deletes vectors."""
    purged = service.purge_expired_trash(db, runtime.vector_store)
    return {"purged": len(purged), "document_ids": purged}


def handle_purge_document(
    db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback
) -> dict:
    """'Delete permanently' for one document in the trash."""
    filename = service.purge_document(db, runtime.vector_store, payload["document_id"])
    return {"purged": 1, "filename": filename}


def handle_run_eval(
    db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback
) -> dict:
    """One evaluation run (decision 0019). In the worker so it never competes with
    indexing for the CPU and Ollama, and so it can be cancelled between cases."""
    return eval_service.execute_run(
        db,
        payload["run_id"],
        settings=runtime.settings,
        embedding_client_for=runtime.embedding_client_for,
        vector_store=runtime.vector_store,
        llm_client_for=runtime.llm_client_for,
        progress=progress,
        reranker=runtime.reranker,
    )


HANDLERS: dict[str, Handler] = {
    "ingest": handle_ingest,
    "analyze_intake": handle_analyze_intake,
    "reindex_document": handle_reindex_document,
    "reindex_collection": handle_reindex_collection,
    "rebuild_collection": handle_rebuild_collection,
    "seed_demo": handle_seed_demo,
    "backup": handle_backup,
    "purge_trash": handle_purge_trash,
    "purge_document": handle_purge_document,
    "run_eval": handle_run_eval,
}
