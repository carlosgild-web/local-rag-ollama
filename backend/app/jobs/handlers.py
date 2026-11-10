"""One handler per job type. Each takes the worker's session, the payload,
the runtime, and a progress callback, and returns a JSON-able result. All
writes go through the versioning service (invariant 1)."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.runtime import Runtime
from app.ingest import intake
from app.ingest.uploads import discard_staged
from app.versioning import demo, service
from app.versioning.service import ProgressCallback

Handler = Callable[[Session, dict, Runtime, ProgressCallback], dict]


def handle_ingest(db: Session, payload: dict, runtime: Runtime, progress: ProgressCallback) -> dict:
    staged = Path(payload["staged_path"])
    if not staged.exists():
        raise FileNotFoundError(f"staged upload {staged.name!r} is gone; upload it again")

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


HANDLERS: dict[str, Handler] = {
    "ingest": handle_ingest,
    "analyze_intake": handle_analyze_intake,
    "reindex_document": handle_reindex_document,
    "reindex_collection": handle_reindex_collection,
    "rebuild_collection": handle_rebuild_collection,
    "seed_demo": handle_seed_demo,
}
