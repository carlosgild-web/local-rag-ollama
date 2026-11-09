"""ChromaDB-backed VectorStore (persistent, embedded)."""

from pathlib import Path

import chromadb

from app.retrieval.vector_store import VectorMatch, VectorStore


class EmbeddingModelMismatchError(Exception):
    """Raised when a collection already exists with a different embedding model."""


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_dir: Path):
        self._client = chromadb.PersistentClient(path=str(persist_dir))

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
        result = self._client.get_collection(collection).query(
            query_embeddings=[embedding], n_results=top_k
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
        result = self._client.get_collection(collection).get(
            where=where, include=["embeddings", "metadatas"]
        )
        return [
            (metadata, list(embedding))
            for metadata, embedding in zip(result["metadatas"], result["embeddings"], strict=True)
        ]
