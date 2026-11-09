"""Loads the fictional Hilda & Luna Beadworks corpus (decision 0010).

Each subfolder of `demo/hilda-luna/` becomes a shelf of the same name and
each file is ingested through the normal service, tagged with its folder.
Running it again is a no-op: files already stored are duplicates by hash.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.base import EmbeddingClient
from app.retrieval.vector_store import VectorStore
from app.versioning import service

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo" / "hilda-luna"


@dataclass
class SeededFile:
    shelf: str
    path: Path
    status: str  # "ingested" or "skipped_duplicate"
    chunk_count: int = 0


def seed_demo(
    db: Session,
    *,
    settings: Settings,
    embedding_client_for: Callable[[str], EmbeddingClient],
    vector_store: VectorStore,
    root: Path = DEMO_DIR,
) -> list[SeededFile]:
    if not root.is_dir():
        raise service.NotFoundError(f"demo folder not found: {root}")

    results: list[SeededFile] = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        shelf = folder.name
        collection = service.get_active_collection(db, shelf) or service.create_collection(
            db,
            vector_store,
            name=shelf,
            embedding_model=settings.embedding_model,
            chunk_size_tokens=settings.chunk_size_tokens,
            chunk_overlap_pct=settings.chunk_overlap_pct,
        )
        embedding_client = embedding_client_for(collection.embedding_model)
        for path in service.discover_files(folder):
            result = service.ingest_document(
                db,
                collection=collection,
                source_path=path,
                settings=settings,
                embedding_client=embedding_client,
                vector_store=vector_store,
                tags=f"demo,{shelf}",
            )
            results.append(SeededFile(shelf, path, result.status, result.chunk_count))
    return results
