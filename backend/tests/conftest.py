import shutil
from pathlib import Path

import pytest

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
