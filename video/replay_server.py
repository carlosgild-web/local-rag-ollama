"""Pass 2 of the README video (decision 0043): the real app, with the chat model's answers
from pass 1 replayed instead of a live model call.

The app is the one `start.cmd video` runs: the same settings, data-video/, Chroma and
SQLite FTS5, bge-m3 embeddings on Ollama, the glossary, the prompt, citation repair and
the stored answers. Only the chat model's call is replaced: for each prompt it streams
what qwen2.5:3b streamed in pass 1 for the same prompt (matched by SHA-256, so the
passages must be the same), piece by piece, after waiting as long as pass 1 did
(VIDEO_REPLAY_SPEED scales the waits, for tests). qwen2.5:3b itself is not loaded, so
the browser and the recorder have the laptop's memory and CPU.

A prompt pass 1 never saw stops the answer with an error: the take fails instead of
showing a made-up answer. cues.mjs checks every answer of the take against pass 1.

--dry (the dry takes): no pass 1; each question gets the storyboard's `dry_answer`.

    set DATA_DIR=...\\data-video  (and the other settings start.cmd video uses)
    backend/.venv/Scripts/python video/replay_server.py --pass1 video/out/pass1 --port 8010
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

import uvicorn  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.runtime import build_runtime  # noqa: E402
from app.llm.base import LLMClient  # noqa: E402
from app.main import create_app  # noqa: E402

SPEED = float(os.environ.get("VIDEO_REPLAY_SPEED", "1"))
DRY_WAIT_S = 4.0
DRY_WORD_S = 0.08


def prompt_sha(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class Replay(LLMClient):
    """Pass 1's answers by prompt, streamed at pass 1's pace."""

    def __init__(self, runs: dict[str, dict[str, Any]], log: Path) -> None:
        self.runs = runs
        self.log = log

    def _note(self, entry: dict) -> None:
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def generate(self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192) -> str:
        raise RuntimeError("the replay only answers the chat's questions")

    def stream_generate(
        self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192
    ) -> Iterator[str]:
        sha = prompt_sha(prompt)
        run = self.runs.get(sha)
        question = re.search(r"\n\nQuestion: (.*?)\n\n", prompt, re.S)
        self._note(
            {
                "sha256": sha,
                "question": question.group(1) if question else None,
                "matched": bool(run),
            }
        )
        if run is None:
            raise RuntimeError("pass 1 has no answer for this prompt (the passages differ)")
        time.sleep(run["first_token_ms"] / 1000 * SPEED)
        for piece in run["pieces"]:
            time.sleep(piece["after_ms"] / 1000 * SPEED)
            yield piece["text"]


class Dry(LLMClient):
    """The dry takes: the storyboard's scripted answer for each question."""

    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers

    def generate(self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192) -> str:
        raise RuntimeError("the dry run only answers the chat's questions")

    def stream_generate(
        self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192
    ) -> Iterator[str]:
        match = re.search(r"\n\nQuestion: (.*?)\n\n", prompt, re.S)
        asked = match.group(1) if match else ""
        # The glossary may add words in brackets; the asked question starts the same way.
        text = next(
            (a for q, a in self.answers.items() if asked.startswith(q.rstrip("?"))),
            "Dry run: no scripted answer for this question.",
        )
        time.sleep(DRY_WAIT_S)
        words = text.split(" ")
        for i, word in enumerate(words):
            time.sleep(DRY_WORD_S)
            yield word + (" " if i < len(words) - 1 else "")


def load_runs(pass1: Path) -> dict[str, dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for path in sorted(pass1.glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        if run["end"] is None or run["end"]["event"] != "done":
            raise SystemExit(f"{path.name}: pass 1 did not answer")
        if run["model_called"]:
            runs[run["prompt_sha256"]] = run
    if not runs:
        raise SystemExit(f"no pass 1 answers in {pass1}")
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pass1", default=str(HERE / "out" / "pass1"))
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    runtime = build_runtime(get_settings())
    if args.dry:
        board = json.loads((HERE / "storyboard-ollama.json").read_text(encoding="utf-8"))
        client: LLMClient = Dry({t["question"]: t["dry_answer"] for t in board["turns"].values()})
        print("dry run: the storyboard's scripted answers", flush=True)
    else:
        runs = load_runs(Path(args.pass1))
        log = Path(args.pass1) / "replay.log.jsonl"
        log.unlink(missing_ok=True)
        client = Replay(runs, log)
        print(f"replaying {len(runs)} answers from {args.pass1} (speed {SPEED})", flush=True)
    runtime.llm_client_for = lambda _model: client
    uvicorn.run(create_app(runtime), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
