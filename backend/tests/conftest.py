import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.core.runtime import Runtime
from app.db.fts import create_fts_table
from app.db.migrate import upgrade_to_head
from app.db.models import Base
from app.db.session import make_engine, make_session_factory
from app.llm.fake_client import FakeEmbeddingClient, FakeLLMClient
from app.llm.ollama_admin import OllamaAdmin
from app.retrieval.fake_store import FakeVectorStore

CORPUS_DIR = Path(__file__).parent / "corpus"

_FALLBACK_TESSERACT = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
_FALLBACK_TESSDATA = Path.home() / ".tessdata"


@pytest.fixture
def tesseract_config():
    """Resolves a usable (tesseract_cmd, tessdata_prefix) pair, or skips the test.

    Prefers whatever is already on PATH; falls back to the per-user install
    documented in docs/decisions/0002-tesseract-user-tessdata.md.
    """
    on_path = shutil.which("tesseract")
    if on_path and (_FALLBACK_TESSDATA / "spa.traineddata").exists():
        return {"tesseract_cmd": None, "tessdata_prefix": str(_FALLBACK_TESSDATA)}
    if on_path and {"eng", "spa"} <= _installed_languages(on_path):
        # System install with language packs (CI, Docker): default tessdata.
        return {"tesseract_cmd": None, "tessdata_prefix": None}

    if _FALLBACK_TESSERACT.exists() and (_FALLBACK_TESSDATA / "spa.traineddata").exists():
        return {
            "tesseract_cmd": str(_FALLBACK_TESSERACT),
            "tessdata_prefix": str(_FALLBACK_TESSDATA),
        }

    pytest.skip("Tesseract with eng+spa language data not found")


def _installed_languages(tesseract: str) -> set[str]:
    try:
        out = subprocess.run(
            [tesseract, "--list-langs"], capture_output=True, text=True, timeout=10, check=False
        )
    except OSError:
        return set()
    return {line.strip() for line in out.stdout.splitlines()[1:] if line.strip()}


@pytest.fixture
def db_session(tmp_path):
    """A fresh SQLAlchemy session against a throwaway SQLite file with the
    full schema, including the chunks_fts virtual table."""
    engine = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    create_fts_table(engine)
    session_factory = make_session_factory(engine)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _fake_ollama_handler(request: httpx.Request) -> httpx.Response:
    """A tiny stand-in for the Ollama HTTP API used by OllamaAdmin."""
    path = request.url.path
    if path == "/api/version":
        return httpx.Response(200, json={"version": "0.0.0-fake"})
    if path == "/api/tags":
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "llama3.1:latest", "size": 1, "details": {"family": "llama"}},
                    {"name": "bge-m3:latest", "size": 2, "details": {"family": "bert"}},
                ]
            },
        )
    if path == "/api/pull":
        lines = [{"status": "pulling manifest"}, {"status": "success"}]
        body = "\n".join(json.dumps(line) for line in lines)
        return httpx.Response(200, text=body)
    if path == "/api/delete":
        name = json.loads(request.content)["model"]
        return httpx.Response(200 if name.startswith("llama3.1") else 404)
    return httpx.Response(404)


@pytest.fixture
def runtime(tmp_path):
    """A Runtime wired to fakes: migrated SQLite under tmp_path, in-memory
    vectors, fake embeddings/LLM, and a mocked Ollama API."""
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    settings.ensure_data_dirs()
    upgrade_to_head(settings.db_path)
    engine = make_engine(settings.db_path)

    embedders: dict[str, FakeEmbeddingClient] = {}
    llm = FakeLLMClient()

    def embedding_client_for(model: str) -> FakeEmbeddingClient:
        return embedders.setdefault(model, FakeEmbeddingClient(dimensions=8))

    rt = Runtime(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        vector_store=FakeVectorStore(),
        embedding_client_for=embedding_client_for,
        llm_client_for=lambda _model: llm,
        ollama=OllamaAdmin(
            "http://ollama.test", transport=httpx.MockTransport(_fake_ollama_handler)
        ),
    )
    rt.fake_llm = llm  # tests queue canned answers here
    yield rt
    engine.dispose()
