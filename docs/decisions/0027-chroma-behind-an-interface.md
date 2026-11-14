# 0027: Chroma behind a `VectorStore` interface

**Status:** accepted (Phase 1, written down 2026-11-14)

## Context

The app needs a vector index that runs on one laptop, offline, with nothing to install beyond `pip`. It also needs tests that run in CI without Ollama or a vector database, and a way to move to a server-grade store (PLAN.md section 11: "more than 1 concurrent user or heavy indexing → Qdrant") without rewriting the app.

## Decision

- **Chroma, embedded** (`chromadb.PersistentClient` under `DATA_DIR/chroma`). There's no server to run, it persists to disk, and it does cosine HNSW search. Telemetry is turned off explicitly, so no Chroma version can call out (CLAUDE.md: no cloud calls).
- **Behind a small abstract class**, `retrieval/vector_store.py`. It has seven methods: `get_or_create_collection`, `upsert`, `query`, `delete`, `count`, `ping` and `get_vectors`. Nothing outside `retrieval/chroma_store.py` imports `chromadb`.
- **Two implementations:**
  - `ChromaVectorStore`: the real one. Reads retry for about 15 s on the one error Chroma raises while its index isn't flushed to disk yet.
  - `FakeVectorStore`: in memory, exact cosine. Every unit and API test, and CI, uses it, together with the fake LLM and embedding clients. CI never needs Ollama or Chroma's files.
- **The interface guards invariant 4.** Each collection's metadata carries its `embedding_model`. Both implementations refuse to add vectors from another model (`EmbeddingModelMismatchError`, tested in `test_fakes.py`).
- **SQLite stays the source of truth.** Chroma holds the vectors and their passages, with the document, version and position in their metadata. Which version is active, the trash and the shelves all live in SQLite. Retrieval over-fetches 3× from Chroma and filters there ([0028](0028-active-version-pointer.md)), so the vector store needs no filtering features of its own.

## Consequences

- Moving to Qdrant (or pgvector) is one new class and the line in `core/runtime.py` that builds the store. The service layer, retrieval and tests don't change.
- Chroma is single-writer when embedded. That's one reason for the one-worker rule (CLAUDE.md). A second process writing to the same folder could corrupt it.
- The interface is the lowest common denominator: no hybrid search inside the store, no metadata filters in `query`. Keyword search is SQLite FTS5, fused by RRF in Python.

## Alternatives considered

- **FAISS:** fast, but it's a library with no persistence or metadata of its own, so all of that would be extra code.
- **Qdrant or Weaviate in a container:** better for many users, but a reviewer would need a second container and a running server just to try the app.
- **`sqlite-vec` in the same SQLite file:** one file and one transaction for chunks and vectors. PLAN.md chose Chroma at the start; with the interface, `sqlite-vec` stays an option as one more implementation.
