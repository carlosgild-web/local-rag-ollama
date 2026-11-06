"""Reindexing and purging documents that saved answers cite (invariant 5).

A reindex used to delete every old chunk, which SQLite refused (FOREIGN KEY)
once a chat answer pointed at one of them in message_sources.
"""

import datetime as dt
from pathlib import Path

from sqlalchemy import select, text

from app.core.config import Settings
from app.db import fts
from app.db.models import Chunk, Document, MessageSource
from app.llm.fake_client import FakeEmbeddingClient
from app.retrieval.fake_store import FakeVectorStore
from app.versioning import history, service
from app.versioning.history import SourceRef

CORPUS = Path(__file__).parent / "corpus"


def _setup(db, tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    vector_store = FakeVectorStore()
    embedding_client = FakeEmbeddingClient(dimensions=8)
    collection = service.create_collection(
        db, vector_store, name="default", embedding_model="fake", chunk_size_tokens=60
    )
    result = service.ingest_document(
        db,
        collection=collection,
        source_path=CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    return settings, vector_store, embedding_client, collection, result


def _cite_first_chunk(db, document_id: int) -> tuple[int, int]:
    """Saves a chat answer citing the document's first chunk."""
    chunk = (
        db.execute(
            select(Chunk)
            .join(Document, Document.active_version_id == Chunk.version_id)
            .where(Document.id == document_id)
            .order_by(Chunk.chunk_index)
        )
        .scalars()
        .first()
    )
    session = history.create_session(db, "how do I brew coffee?")
    message = history.add_message(
        db,
        session.id,
        "assistant",
        "Use a pour-over [1].",
        sources=[SourceRef(chunk_id=chunk.id, rank=1, score=0.5)],
    )
    return message.id, chunk.id


def _live_chunks(db, collection_id: int) -> list[Chunk]:
    return list(
        db.execute(
            select(Chunk).where(Chunk.collection_id == collection_id, Chunk.retired_at.is_(None))
        ).scalars()
    )


def test_reindex_document_retires_cited_chunks_and_deletes_the_rest(db_session, tmp_path):
    settings, vector_store, embedding_client, collection, result = _setup(db_session, tmp_path)
    assert result.chunk_count > 1, "test needs a document with several chunks"
    message_id, cited_id = _cite_first_chunk(db_session, result.document_id)

    reindexed = service.reindex_document(
        db_session,
        result.document_id,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    # The cited chunk stays for the answer's history, marked retired...
    cited = db_session.get(Chunk, cited_id)
    assert cited is not None and cited.retired_at is not None
    [source] = db_session.execute(
        select(MessageSource).where(MessageSource.message_id == message_id)
    ).scalars()
    assert source.chunk_id == cited_id
    # ...the uncited old chunks are gone (SQLite may reuse their ids, which
    # is safe: nothing cites them), so only the retired one is left over...
    all_chunks = db_session.execute(select(Chunk)).scalars().all()
    assert [c.id for c in all_chunks if c.retired_at is not None] == [cited_id]
    assert len(all_chunks) == reindexed.chunk_count + 1
    # ...and search only sees the fresh chunks.
    live = _live_chunks(db_session, collection.id)
    assert len(live) == reindexed.chunk_count and cited_id not in {c.id for c in live}
    assert vector_store.count(collection.chroma_collection) == reindexed.chunk_count
    assert cited_id not in fts.search(db_session, "coffee", top_k=50)


def test_reindexing_twice_and_whole_collection_after_chat(db_session, tmp_path):
    settings, vector_store, embedding_client, collection, result = _setup(db_session, tmp_path)
    _cite_first_chunk(db_session, result.document_id)
    kwargs = dict(settings=settings, embedding_client=embedding_client, vector_store=vector_store)

    service.reindex_document(db_session, result.document_id, **kwargs)
    # Retired chunks are skipped the second time (no double FTS delete).
    [again] = service.reindex_collection(db_session, collection.id, **kwargs)

    assert again.chunk_count == len(_live_chunks(db_session, collection.id))
    assert vector_store.count(collection.chroma_collection) == again.chunk_count
    integrity = db_session.execute(
        text("INSERT INTO chunks_fts (chunks_fts) VALUES ('integrity-check')")
    )
    assert integrity is not None  # raises if the FTS index were corrupt


def test_purge_removes_cited_and_retired_chunks_and_unlinks_sources(db_session, tmp_path):
    settings, vector_store, embedding_client, collection, result = _setup(db_session, tmp_path)
    message_id, _ = _cite_first_chunk(db_session, result.document_id)
    service.reindex_document(
        db_session,
        result.document_id,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    service.soft_delete_document(db_session, result.document_id)
    document = db_session.get(Document, result.document_id)
    document.trashed_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=31)
    db_session.commit()

    assert service.purge_expired_trash(db_session, vector_store) == [result.document_id]

    assert db_session.execute(select(Chunk)).scalars().all() == []
    assert vector_store.count(collection.chroma_collection) == 0
    sources = db_session.execute(
        select(MessageSource).where(MessageSource.message_id == message_id)
    ).scalars()
    assert list(sources) == []
    db_session.execute(text("INSERT INTO chunks_fts (chunks_fts) VALUES ('integrity-check')"))
