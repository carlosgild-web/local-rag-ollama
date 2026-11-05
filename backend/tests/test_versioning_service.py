"""The Phase 3 done-when criteria: duplicate skip, new version, rollback,
soft delete, blue/green swap -- plus diff and purge."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.models import Document, DocumentVersion
from app.llm.fake_client import FakeEmbeddingClient
from app.retrieval.fake_store import FakeVectorStore
from app.versioning import service

CORPUS = Path(__file__).parent / "corpus"


def _settings(tmp_path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")


def _collection(db, settings):
    return service.create_collection(
        db,
        FakeVectorStore(),
        name="default",
        embedding_model=settings.embedding_model,
        chunk_size_tokens=settings.chunk_size_tokens,
        chunk_overlap_pct=settings.chunk_overlap_pct,
    )


def test_duplicate_file_is_skipped(db_session, tmp_path):
    settings = _settings(tmp_path)
    vector_store = FakeVectorStore()
    collection = service.create_collection(
        db_session, vector_store, name="default", embedding_model="fake"
    )
    embedding_client = FakeEmbeddingClient(dimensions=8)

    first = service.ingest_document(
        db_session,
        collection=collection,
        source_path=CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    second = service.ingest_document(
        db_session,
        collection=collection,
        source_path=CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    assert first.status == "ingested"
    assert second.status == "skipped_duplicate"
    assert second.document_id == first.document_id
    # only one document_version row exists for this content
    versions = db_session.query(DocumentVersion).all()
    assert len(versions) == 1


def test_changed_content_creates_new_version_and_old_chunks_remain(db_session, tmp_path):
    settings = _settings(tmp_path)
    vector_store = FakeVectorStore()
    collection = service.create_collection(
        db_session, vector_store, name="default", embedding_model="fake"
    )
    embedding_client = FakeEmbeddingClient(dimensions=8)

    original = tmp_path / "doc.txt"
    original.write_text("Version one content about espresso.")
    v1 = service.ingest_document(
        db_session,
        collection=collection,
        source_path=original,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    original.write_text("Version two content, now about pour-over coffee instead.")
    v2 = service.ingest_document(
        db_session,
        collection=collection,
        source_path=original,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    assert v1.status == "ingested"
    assert v2.status == "ingested"
    assert v1.document_id == v2.document_id, "same filename in the same collection is one document"
    assert v1.version_id != v2.version_id

    document = db_session.get(Document, v1.document_id)
    assert document.active_version_id == v2.version_id, "new version becomes active"

    versions = (
        db_session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number)
        .all()
    )
    assert [v.version_number for v in versions] == [1, 2]
    # the old version's chunks are untouched, just no longer active
    assert versions[0].chunks, "old version's chunks still exist (invariant 3)"


def test_rollback_flips_pointer_without_reembedding(db_session, tmp_path):
    settings = _settings(tmp_path)
    vector_store = FakeVectorStore()
    collection = service.create_collection(
        db_session, vector_store, name="default", embedding_model="fake"
    )
    embedding_client = FakeEmbeddingClient(dimensions=8)

    doc_path = tmp_path / "doc.txt"
    doc_path.write_text("Version one content about espresso.")
    v1 = service.ingest_document(
        db_session,
        collection=collection,
        source_path=doc_path,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    doc_path.write_text("Version two content, now about pour-over coffee instead.")
    v2 = service.ingest_document(
        db_session,
        collection=collection,
        source_path=doc_path,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    embed_calls_before = embedding_client.call_count
    service.rollback_document(db_session, v1.document_id, v1.version_id)
    embed_calls_after = embedding_client.call_count

    document = db_session.get(Document, v1.document_id)
    assert document.active_version_id == v1.version_id
    assert embed_calls_after == embed_calls_before, "rollback must not re-embed"
    # v2's chunks still exist too -- rollback doesn't delete anything
    assert db_session.get(DocumentVersion, v2.version_id).chunks


def test_soft_delete_sets_trashed_at_and_restore_clears_it(db_session, tmp_path):
    settings = _settings(tmp_path)
    vector_store = FakeVectorStore()
    collection = service.create_collection(
        db_session, vector_store, name="default", embedding_model="fake"
    )
    result = service.ingest_document(
        db_session,
        collection=collection,
        source_path=CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=FakeEmbeddingClient(dimensions=8),
        vector_store=vector_store,
    )

    service.soft_delete_document(db_session, result.document_id)
    document = db_session.get(Document, result.document_id)
    assert document.trashed_at is not None

    service.restore_document(db_session, result.document_id)
    document = db_session.get(Document, result.document_id)
    assert document.trashed_at is None


def test_blue_green_swap_deactivates_old_collection_and_keeps_it(db_session):
    vector_store = FakeVectorStore()
    first = service.create_collection(
        db_session, vector_store, name="docs", embedding_model="model-a"
    )
    second = service.create_collection(
        db_session, vector_store, name="docs", embedding_model="model-b"
    )

    assert first.is_active is False
    assert second.is_active is True
    assert first.chroma_collection != second.chroma_collection
    assert service.get_active_collection(db_session, "docs").id == second.id
    # old collection row (and its vectors) still exist, just inactive
    assert vector_store.count(first.chroma_collection) == 0  # nothing ingested into it, but present
    assert first.chroma_collection in vector_store._collections


def test_diff_versions_shows_text_changes(db_session, tmp_path):
    settings = _settings(tmp_path)
    vector_store = FakeVectorStore()
    collection = service.create_collection(
        db_session, vector_store, name="default", embedding_model="fake"
    )
    embedding_client = FakeEmbeddingClient(dimensions=8)

    doc_path = tmp_path / "doc.txt"
    doc_path.write_text("Original line about espresso.")
    v1 = service.ingest_document(
        db_session,
        collection=collection,
        source_path=doc_path,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    doc_path.write_text("Changed line about pour-over.")
    v2 = service.ingest_document(
        db_session,
        collection=collection,
        source_path=doc_path,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    diff = service.diff_versions(db_session, v1.version_id, v2.version_id)
    diff_text = "\n".join(diff)
    assert "espresso" in diff_text
    assert "pour-over" in diff_text


def test_purge_expired_trash_hard_deletes_and_removes_vectors(db_session, tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    vector_store = FakeVectorStore()
    collection = service.create_collection(
        db_session, vector_store, name="default", embedding_model="fake"
    )
    result = service.ingest_document(
        db_session,
        collection=collection,
        source_path=CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=FakeEmbeddingClient(dimensions=8),
        vector_store=vector_store,
    )
    assert vector_store.count(collection.chroma_collection) == result.chunk_count

    service.soft_delete_document(db_session, result.document_id)

    import datetime as dt

    document = db_session.get(Document, result.document_id)
    document.trashed_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=31)
    db_session.commit()

    purged_ids = service.purge_expired_trash(db_session, vector_store, older_than_days=30)

    assert purged_ids == [result.document_id]
    assert db_session.get(Document, result.document_id) is None
    assert vector_store.count(collection.chroma_collection) == 0


def test_rollback_rejects_version_from_another_document(db_session, tmp_path):
    settings = _settings(tmp_path)
    vector_store = FakeVectorStore()
    collection = service.create_collection(
        db_session, vector_store, name="default", embedding_model="fake"
    )
    embedding_client = FakeEmbeddingClient(dimensions=8)

    a = service.ingest_document(
        db_session,
        collection=collection,
        source_path=CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    b = service.ingest_document(
        db_session,
        collection=collection,
        source_path=CORPUS / "intro-to-astronomy-telescopes.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    with pytest.raises(ValueError):
        service.rollback_document(db_session, a.document_id, b.version_id)
