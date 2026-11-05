"""Ingestion pipeline: the single service layer for writing documents.

Routes and the CLI call into this module; nothing else writes to the file
store, SQLite, or the vector store directly (CLAUDE.md invariant 1).
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.ingest import file_store, sqlite_store
from app.ingest.chunker import chunk_blocks
from app.ingest.parsers import SUPPORTED_EXTENSIONS, parse_file
from app.llm.base import EmbeddingClient
from app.retrieval.vector_store import VectorStore

DEFAULT_COLLECTION = "default"


@dataclass
class IngestResult:
    path: Path
    status: str  # "ingested" | "skipped_duplicate"
    chunk_count: int = 0


def ingest_path(
    path: Path,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    collection: str = DEFAULT_COLLECTION,
) -> list[IngestResult]:
    """Ingest a single file or every supported file under a directory."""
    files = _discover_files(path)

    vector_store.get_or_create_collection(
        collection,
        metadata={
            "embedding_model": settings.embedding_model,
            "chunk_size_tokens": settings.chunk_size_tokens,
            "chunk_overlap_pct": settings.chunk_overlap_pct,
        },
    )

    conn = sqlite_store.connect(settings.db_path)
    try:
        return [
            _ingest_file(
                f,
                settings=settings,
                embedding_client=embedding_client,
                vector_store=vector_store,
                collection=collection,
                conn=conn,
            )
            for f in files
        ]
    finally:
        conn.close()


def _discover_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(
        p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _ingest_file(
    path: Path,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    collection: str,
    conn,
) -> IngestResult:
    sha256 = file_store.hash_file(path)
    if sqlite_store.find_document_by_hash(conn, sha256) is not None:
        return IngestResult(path=path, status="skipped_duplicate")

    file_store.store_file(path, settings.files_dir)

    parsed = parse_file(
        path,
        ocr_lang=settings.ocr_lang,
        ocr_min_text_chars=settings.ocr_min_text_chars,
        tesseract_cmd=settings.tesseract_cmd,
        tessdata_prefix=settings.tessdata_prefix,
    )
    chunks = chunk_blocks(
        parsed.blocks,
        chunk_size_tokens=settings.chunk_size_tokens,
        overlap_pct=settings.chunk_overlap_pct,
    )

    document_id = sqlite_store.insert_document(
        conn,
        path=str(path),
        filename=path.name,
        sha256=sha256,
        ext=path.suffix.lower(),
        ingested_at=dt.datetime.now(dt.UTC).isoformat(),
    )

    chunk_rows = [
        {
            "chunk_index": i,
            "text": c.text,
            "page": c.page,
            "heading": c.heading,
            "token_estimate": c.token_estimate,
        }
        for i, c in enumerate(chunks)
    ]
    chunk_ids = sqlite_store.insert_chunks(conn, document_id, chunk_rows)
    conn.commit()

    if chunks:
        embeddings = embedding_client.embed([c.text for c in chunks])
        vector_store.upsert(
            collection,
            ids=[f"{document_id}:{chunk_id}" for chunk_id in chunk_ids],
            embeddings=embeddings,
            metadatas=[
                {
                    "document_id": document_id,
                    "filename": path.name,
                    "chunk_index": i,
                    "page": c.page or 0,
                    "heading": c.heading or "",
                }
                for i, c in enumerate(chunks)
            ],
            documents=[c.text for c in chunks],
        )

    return IngestResult(path=path, status="ingested", chunk_count=len(chunks))
