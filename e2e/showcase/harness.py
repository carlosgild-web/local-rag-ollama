"""The backend for the README GIFs and screenshots (decision 0042): the real app on
Ollama's `bge-m3`, with the chat model's outputs replayed from a recorded run.

- Embeddings, Chroma, SQLite FTS5, retrieval, the glossary, the prompt, citation repair
  and the intake's tags and shelves are real: they need Ollama with `bge-m3`.
- The chat model is replayed: `replay.json` holds what `qwen2.5:3b` answered to each
  prompt in a recorded run (`E2E_RECORD=1`). Replays are keyed by the question in the
  prompt, or "shelf-naming" for the intake's naming call, and streamed word by word.
  A prompt with no recording gets a short "not recorded" answer.

Each run starts from an empty data folder and loads the demo company (the dashboard's
own seeding service) before the app starts.

Run: python harness.py   (env: E2E_DATA_DIR, E2E_PORT (default 8020), E2E_RECORD=1)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from collections.abc import Iterator
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DATA_DIR = Path(os.environ.get("E2E_DATA_DIR", HERE / ".tmp" / "data"))
PORT = int(os.environ.get("E2E_PORT", "8020"))
RECORD = os.environ.get("E2E_RECORD") == "1"
REPLAY_FILE = HERE / "replay.json"
CHAT_MODEL = "qwen2.5:3b"
# Paced like the recorded model: its first word came after the prompt was read.
FIRST_TOKEN_S = float(os.environ.get("E2E_FIRST_TOKEN_MS", "1200")) / 1000
WORD_S = float(os.environ.get("E2E_WORD_MS", "70")) / 1000
NOT_RECORDED = "This demo replays recorded answers only (no recording for this question)."

# Everything the app reads from the environment is set before it is imported.
shutil.rmtree(DATA_DIR, ignore_errors=True)
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["CHAT_MODEL"] = CHAT_MODEL
os.environ.setdefault("EMBEDDING_MODEL", "bge-m3")
os.environ["APP_PORT"] = str(PORT)

import uvicorn  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.runtime import build_runtime  # noqa: E402
from app.llm.base import LLMClient  # noqa: E402
from app.main import create_app  # noqa: E402
from app.versioning import demo  # noqa: E402


def replay_key(prompt: str) -> str:
    """The question of an answer prompt (after the glossary's rewrite), or the call's kind."""
    if prompt.startswith("You organise one company's documents into shelves"):
        return "shelf-naming"
    match = re.search(r"\n\nQuestion: (.*?)\n\n", prompt, re.S)
    return match.group(1).strip() if match else "other"


class Recording(LLMClient):
    """The real model; every answer is saved to replay.json under its key."""

    def __init__(self, real: LLMClient) -> None:
        self._real = real
        self._saved = json.loads(REPLAY_FILE.read_text("utf-8")) if REPLAY_FILE.exists() else {}

    def _save(self, prompt: str, answer: str) -> None:
        self._saved[replay_key(prompt)] = answer
        text = json.dumps(self._saved, indent=2, ensure_ascii=False) + "\n"
        REPLAY_FILE.write_text(text, "utf-8")

    def generate(self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192) -> str:
        answer = self._real.generate(prompt, temperature=temperature, num_ctx=num_ctx)
        self._save(prompt, answer)
        return answer

    def stream_generate(
        self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192
    ) -> Iterator[str]:
        parts = []
        for piece in self._real.stream_generate(prompt, temperature=temperature, num_ctx=num_ctx):
            parts.append(piece)
            yield piece
        self._save(prompt, "".join(parts))


class Replay(LLMClient):
    """The recorded answers, streamed at a steady pace."""

    def __init__(self) -> None:
        self._saved = json.loads(REPLAY_FILE.read_text("utf-8"))

    def generate(self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192) -> str:
        return self._saved.get(replay_key(prompt), NOT_RECORDED)

    def stream_generate(
        self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192
    ) -> Iterator[str]:
        time.sleep(FIRST_TOKEN_S)
        words = self.generate(prompt).split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            time.sleep(WORD_S)


def main() -> None:
    runtime = build_runtime(get_settings())
    real_for = runtime.llm_client_for
    if RECORD:
        recorders: dict[str, LLMClient] = {}

        def recording_for(model: str) -> LLMClient:
            if model not in recorders:
                recorders[model] = Recording(real_for(model))
            return recorders[model]

        runtime.llm_client_for = recording_for
    else:
        replay = Replay()
        runtime.llm_client_for = lambda _model: replay
    with runtime.session_factory() as db:
        demo.seed_demo(
            db,
            settings=runtime.settings,
            embedding_client_for=runtime.embedding_client_for,
            vector_store=runtime.vector_store,
        )
        db.commit()
    uvicorn.run(create_app(runtime), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
