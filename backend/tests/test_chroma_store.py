"""The real Chroma store: no cloud calls, and calls that survive an unreadable index."""

import pytest
from chromadb.errors import InternalError

from app.retrieval.chroma_store import ChromaVectorStore, _read_with_retry

NOT_READY = (
    "Error executing plan: Internal error: "
    "Error creating hnsw segment reader: Nothing found on disk"
)


def test_chroma_telemetry_is_off(tmp_path):
    store = ChromaVectorStore(tmp_path / "chroma")
    assert store._client.get_settings().anonymized_telemetry is False


def test_read_retries_until_the_index_is_on_disk():
    calls, waits = [], []

    def read():
        calls.append(1)
        if len(calls) < 3:
            raise InternalError(NOT_READY)
        return "vectors"

    assert _read_with_retry(read, sleep=waits.append) == "vectors"
    assert len(calls) == 3
    assert waits == [0.5, 1.0]


def test_other_chroma_errors_are_not_retried():
    waits = []

    def read():
        raise InternalError("something else broke")

    with pytest.raises(InternalError, match="something else"):
        _read_with_retry(read, sleep=waits.append)
    assert waits == []


def test_gives_up_after_the_last_attempt():
    waits = []

    def read():
        raise InternalError(NOT_READY)

    with pytest.raises(InternalError, match="Nothing found on disk"):
        _read_with_retry(read, sleep=waits.append)
    assert waits == [0.5, 1.0]


def unreadable_on(first_client):
    """An operation that fails like Chroma 1.5.9 for as long as it gets the given client."""

    def op(client):
        if client is first_client:
            raise InternalError(NOT_READY)
        return "vectors"

    return op


def test_store_reopens_the_client_when_the_index_stays_unreadable(tmp_path):
    waits = []
    store = ChromaVectorStore(tmp_path / "chroma", sleep=waits.append)
    first = store._client

    assert store._call(unreadable_on(first)) == "vectors"
    assert store._client is not first
    assert waits == [0.5, 1.0]  # the short retries come first


def test_other_errors_do_not_reopen_the_client(tmp_path):
    store = ChromaVectorStore(tmp_path / "chroma", sleep=lambda _: None)
    first = store._client

    def op(client):
        raise InternalError("something else broke")

    with pytest.raises(InternalError, match="something else"):
        store._call(op)
    assert store._client is first


def test_vectors_survive_reopening(tmp_path):
    store = ChromaVectorStore(tmp_path / "chroma")
    store.get_or_create_collection("shelf_g1", {"embedding_model": "fake"})
    store.upsert(
        "shelf_g1",
        ids=["a", "b"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[{"chunk_index": 0}, {"chunk_index": 1}],
        documents=["first", "second"],
    )

    store._reopen()

    assert store.count("shelf_g1") == 2
    assert store.query("shelf_g1", [1.0, 0.0], top_k=1)[0].id == "a"
