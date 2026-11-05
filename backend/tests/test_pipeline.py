from pathlib import Path

from app.core.config import Settings
from app.ingest import sqlite_store
from app.ingest.pipeline import ingest_path
from app.llm.fake_client import FakeEmbeddingClient
from app.retrieval.fake_store import FakeVectorStore

CORPUS = Path(__file__).parent / "corpus"


def _settings(tmp_path, tesseract_config=None) -> Settings:
    kwargs = dict(tesseract_config) if tesseract_config else {}
    return Settings(_env_file=None, data_dir=tmp_path / "data", **kwargs)


def test_ingest_corpus_then_second_run_skips_everything(tmp_path, tesseract_config):
    settings = _settings(tmp_path, tesseract_config)
    embedding_client = FakeEmbeddingClient(dimensions=8)
    vector_store = FakeVectorStore()

    first = ingest_path(
        CORPUS, settings=settings, embedding_client=embedding_client, vector_store=vector_store
    )
    assert first, "expected at least one supported file in the corpus"
    assert all(r.status == "ingested" for r in first)
    assert all(r.chunk_count > 0 for r in first)

    second = ingest_path(
        CORPUS, settings=settings, embedding_client=embedding_client, vector_store=vector_store
    )
    assert len(second) == len(first)
    assert all(r.status == "skipped_duplicate" for r in second)


def test_ingest_single_file_writes_chunks_to_vector_store(tmp_path):
    settings = _settings(tmp_path)
    embedding_client = FakeEmbeddingClient(dimensions=8)
    vector_store = FakeVectorStore()

    results = ingest_path(
        CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    assert len(results) == 1
    assert results[0].status == "ingested"
    assert vector_store.count("default") == results[0].chunk_count


def test_ingest_writes_chunks_to_sqlite_fts(tmp_path):
    settings = _settings(tmp_path)
    ingest_path(
        CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=FakeEmbeddingClient(dimensions=8),
        vector_store=FakeVectorStore(),
    )

    conn = sqlite_store.connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT text FROM chunks_fts WHERE chunks_fts MATCH 'espresso'"
        ).fetchall()
        assert rows
    finally:
        conn.close()


def test_duplicate_file_with_different_name_is_skipped(tmp_path):
    settings = _settings(tmp_path)
    embedding_client = FakeEmbeddingClient(dimensions=8)
    vector_store = FakeVectorStore()

    source = CORPUS / "coffee-brewing-methods.txt"
    copy_path = tmp_path / "renamed-copy.txt"
    copy_path.write_bytes(source.read_bytes())

    first = ingest_path(
        source, settings=settings, embedding_client=embedding_client, vector_store=vector_store
    )
    second = ingest_path(
        copy_path, settings=settings, embedding_client=embedding_client, vector_store=vector_store
    )

    assert first[0].status == "ingested"
    assert second[0].status == "skipped_duplicate"
