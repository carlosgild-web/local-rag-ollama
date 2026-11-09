"""ChromaDB-backed VectorStore (persistent, embedded)."""

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import chromadb
from chromadb.errors import InternalError

from app.retrieval.vector_store import VectorMatch, VectorStore

log = logging.getLogger(__name__)
T = TypeVar("T")

# Right after a large write, Chroma (1.5.x, Rust core) can briefly fail reads of
# that collection with "Error creating hnsw segment reader: Nothing found on disk"
# until its index is flushed. Reads wait and retry for about 15 s on that error only.
_INDEX_NOT_READY = "Nothing found on disk"
_RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0, 8.0)


def _read_with_retry(read: Callable[[], T], *, sleep: Callable[[float], None] = time.sleep) -> T:
    for delay in _RETRY_DELAYS:
        try:
            return read()
        except InternalError as error:
            if _INDEX_NOT_READY not in str(error):
                raise
            log.warning("chroma index not on disk yet; retrying read", extra={"wait_s": delay})
            sleep(delay)
    return read()


class EmbeddingModelMismatchError(Exception):
    """Raised when a collection already exists with a different embedding model."""


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_dir: Path):
        # Embedded only: Chroma's HTTP server is never started. Telemetry is off
        # explicitly so no future Chroma version can send anything (no cloud calls).
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )

    def get_or_create_collection(self, name: str, metadata: dict) -> None:
        full_metadata = {**metadata, "hnsw:space": "cosine"}
        collection = self._client.get_or_create_collection(name=name, metadata=full_metadata)

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
        self._client.get_collection(collection).upsert(
            ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents
        )

    def query(self, collection: str, embedding: list[float], top_k: int) -> list[VectorMatch]:
        result = _read_with_retry(
            lambda: self._client.get_collection(collection).query(
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
        self._client.get_collection(collection).delete(ids=ids)

    def count(self, collection: str) -> int:
        return self._client.get_collection(collection).count()

    def ping(self) -> None:
        self._client.heartbeat()

    def get_vectors(self, collection: str, where: dict) -> list[tuple[dict, list[float]]]:
        result = _read_with_retry(
            lambda: self._client.get_collection(collection).get(
                where=where, include=["embeddings", "metadatas"]
            )
        )
        return [
            (metadata, list(embedding))
            for metadata, embedding in zip(result["metadatas"], result["embeddings"], strict=True)
        ]
