"""ChromaDB-backed VectorStore (persistent, embedded)."""

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.client import SharedSystemClient
from chromadb.errors import InternalError

from app.retrieval.vector_store import VectorMatch, VectorStore

log = logging.getLogger(__name__)
T = TypeVar("T")

# Chroma 1.5.x (Rust core) sometimes fails every use of a collection with "Error
# creating hnsw segment reader: Nothing found on disk". Right after a write it can
# clear in a second or two, so calls first wait and retry briefly. But it can also
# stay broken for the whole process, on a collection nobody wrote to, while the
# files on disk are fine: only a new client loads it again (the store reopens).
_INDEX_NOT_READY = "Nothing found on disk"
_RETRY_DELAYS = (0.5, 1.0)


def _is_index_not_ready(error: Exception) -> bool:
    return isinstance(error, InternalError) and _INDEX_NOT_READY in str(error)


def _read_with_retry(read: Callable[[], T], *, sleep: Callable[[float], None] = time.sleep) -> T:
    for delay in _RETRY_DELAYS:
        try:
            return read()
        except InternalError as error:
            if not _is_index_not_ready(error):
                raise
            log.warning("chroma index not on disk yet; retrying read", extra={"wait_s": delay})
            sleep(delay)
    return read()


class EmbeddingModelMismatchError(Exception):
    """Raised when a collection already exists with a different embedding model."""


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_dir: Path, *, sleep: Callable[[float], None] = time.sleep):
        self._persist_dir = persist_dir
        self._sleep = sleep
        # Every Chroma call holds this lock, so reopening the client never pulls it
        # out from under a call in another thread (requests and the job worker).
        self._lock = threading.RLock()
        self._client = self._open()

    def _open(self) -> ClientAPI:
        # Embedded only: Chroma's HTTP server is never started. Telemetry is off
        # explicitly so no future Chroma version can send anything (no cloud calls).
        return chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )

    def _reopen(self) -> None:
        log.warning("chroma index still unreadable; reopening the vector store")
        # PersistentClient reuses one cached system per path; drop it so the new
        # client loads every index from disk again.
        SharedSystemClient.clear_system_cache()
        self._client = self._open()

    def _call(self, op: Callable[[ClientAPI], T]) -> T:
        """Runs one Chroma operation: retries briefly, then once more on a new client."""
        with self._lock:
            try:
                return _read_with_retry(lambda: op(self._client), sleep=self._sleep)
            except InternalError as error:
                if not _is_index_not_ready(error):
                    raise
                self._reopen()
                return op(self._client)

    def get_or_create_collection(self, name: str, metadata: dict) -> None:
        full_metadata = {**metadata, "hnsw:space": "cosine"}
        collection = self._call(
            lambda client: client.get_or_create_collection(name=name, metadata=full_metadata)
        )

        existing_model = collection.metadata.get("embedding_model")
        requested_model = metadata.get("embedding_model")
        if existing_model and requested_model and existing_model != requested_model:
            raise EmbeddingModelMismatchError(
                f"Collection '{name}' was built with embedding model '{existing_model}', "
                f"cannot mix in vectors from '{requested_model}'. Create a new collection instead."
            )

    def upsert(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        documents: list[str],
    ) -> None:
        self._call(
            lambda client: client.get_collection(collection).upsert(
                ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents
            )
        )

    def query(self, collection: str, embedding: list[float], top_k: int) -> list[VectorMatch]:
        result = self._call(
            lambda client: client.get_collection(collection).query(
                query_embeddings=[embedding], n_results=top_k
            )
        )
        matches = []
        ids = result["ids"][0]
        distances = result["distances"][0]
        metadatas = result["metadatas"][0]
        documents = result["documents"][0]
        for i, chunk_id in enumerate(ids):
            matches.append(
                VectorMatch(
                    id=chunk_id,
                    score=1.0 - distances[i],
                    metadata=metadatas[i],
                    document=documents[i],
                )
            )
        return matches

    def delete(self, collection: str, ids: list[str]) -> None:
        self._call(lambda client: client.get_collection(collection).delete(ids=ids))

    def count(self, collection: str) -> int:
        return self._call(lambda client: client.get_collection(collection).count())

    def ping(self) -> None:
        with self._lock:
            self._client.heartbeat()

    def get_vectors(self, collection: str, where: dict) -> list[tuple[dict, list[float]]]:
        result = self._call(
            lambda client: client.get_collection(collection).get(
                where=where, include=["embeddings", "metadatas"]
            )
        )
        return [
            (metadata, list(embedding))
            for metadata, embedding in zip(result["metadatas"], result["embeddings"], strict=True)
        ]
