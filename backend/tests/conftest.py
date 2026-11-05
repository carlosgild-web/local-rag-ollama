import shutil
from pathlib import Path

import pytest

from app.db.fts import create_fts_table
from app.db.models import Base
from app.db.session import make_engine, make_session_factory

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

    if _FALLBACK_TESSERACT.exists() and (_FALLBACK_TESSDATA / "spa.traineddata").exists():
        return {
            "tesseract_cmd": str(_FALLBACK_TESSERACT),
            "tessdata_prefix": str(_FALLBACK_TESSDATA),
        }

    pytest.skip("Tesseract with eng+spa language data not found")


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
