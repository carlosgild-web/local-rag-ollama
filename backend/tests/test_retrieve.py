from pathlib import Path

from app.core.config import Settings
from app.llm.fake_client import FakeEmbeddingClient
from app.retrieval.fake_store import FakeVectorStore
from app.retrieval.retrieve import retrieve
from app.versioning import service

CORPUS = Path(__file__).parent / "corpus"


class _Env:
    def __init__(self, db, tmp_path):
        self.db = db
        self.settings = Settings(
            _env_file=None, data_dir=tmp_path / "data", retrieval_candidates=20, retrieval_top_k=5
        )
        self.embedder = FakeEmbeddingClient(dimensions=8)
        self.vector_store = FakeVectorStore()
        self.collection = service.create_collection(
            db, self.vector_store, name="default", embedding_model="fake"
        )

    def ingest(self, path, collection=None):
        return service.ingest_document(
            self.db,
            collection=collection or self.collection,
            source_path=path,
            settings=self.settings,
            embedding_client=self.embedder,
            vector_store=self.vector_store,
        )

    def retrieve(self, question, collection=None, top_k=None):
        return retrieve(
            self.db,
            question,
            collection=collection or self.collection,
            settings=self.settings,
            embedding_client=self.embedder,
            vector_store=self.vector_store,
            top_k=top_k,
        )


def test_retrieve_against_empty_knowledge_base_returns_nothing(db_session, tmp_path):
    assert _Env(db_session, tmp_path).retrieve("anything") == []


def test_retrieve_finds_keyword_match_via_fts_with_scores(db_session, tmp_path):
    env = _Env(db_session, tmp_path)
    env.ingest(CORPUS / "coffee-brewing-methods.txt")
    env.ingest(CORPUS / "intro-to-astronomy-telescopes.txt")

    chunks = env.retrieve("espresso")

    assert chunks, "expected at least one match for a keyword from the coffee document"
    assert any("espresso" in c.text.lower() for c in chunks)
    assert all(c.filename and c.version_id for c in chunks)
    assert all(c.score > 0 for c in chunks)
    assert [c.score for c in chunks] == sorted((c.score for c in chunks), reverse=True)


def test_retrieve_respects_top_k(db_session, tmp_path):
    env = _Env(db_session, tmp_path)
    env.ingest(CORPUS / "basics-of-machine-learning.md")
    assert len(env.retrieve("machine learning", top_k=1)) <= 1


def test_retrieve_only_serves_the_active_version(db_session, tmp_path):
    env = _Env(db_session, tmp_path)
    doc = tmp_path / "doc.txt"
    doc.write_text("The espresso machine is red.")
    v1 = env.ingest(doc)
    doc.write_text("The espresso machine is blue.")
    v2 = env.ingest(doc)

    assert {c.version_id for c in env.retrieve("espresso machine")} == {v2.version_id}

    service.rollback_document(db_session, v1.document_id, v1.version_id)
    assert {c.version_id for c in env.retrieve("espresso machine")} == {v1.version_id}


def test_retrieve_skips_trashed_documents(db_session, tmp_path):
    env = _Env(db_session, tmp_path)
    result = env.ingest(CORPUS / "coffee-brewing-methods.txt")
    service.soft_delete_document(db_session, result.document_id)
    assert env.retrieve("espresso") == []


def test_retrieve_is_scoped_to_the_collection(db_session, tmp_path):
    env = _Env(db_session, tmp_path)
    other = service.create_collection(
        db_session, env.vector_store, name="other", embedding_model="fake"
    )
    env.ingest(CORPUS / "coffee-brewing-methods.txt", collection=other)

    assert env.retrieve("espresso") == []
    assert env.retrieve("espresso", collection=other)


def test_discover_files_finds_supported_corpus_files():
    files = service.discover_files(CORPUS)
    assert files
    assert all(f.suffix.lower() in {".txt", ".md", ".docx", ".pdf"} for f in files)
    single = CORPUS / "coffee-brewing-methods.txt"
    assert service.discover_files(single) == [single]
