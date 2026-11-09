"""The real Chroma store: no cloud calls, and reads that survive a just-written index."""

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
    assert waits == [0.5, 1.0, 2.0, 4.0, 8.0]
