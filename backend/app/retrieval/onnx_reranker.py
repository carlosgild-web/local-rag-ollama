"""bge-reranker-v2-m3 as a cross-encoder through ONNX Runtime (decision 0023).

A cross-encoder reads the question and one passage together and scores how
well the passage answers it, which is slower but sharper than comparing two
separate embeddings. It rescores the fused candidates (20 by default) before
the top-k are sent to the model (PLAN.md section 6).

The model is an 8-bit ONNX export kept in DATA_DIR/hf, fetched once with
`python -m app.cli reranker-download` and never baked into an image.
`onnxruntime` and `tokenizers` come with ChromaDB already; they're also listed
in requirements-rerank.txt so the reranker doesn't rely on that.
"""

import hashlib
import math
import threading
from dataclasses import replace
from pathlib import Path

from app.retrieval.reranker import Reranker
from app.retrieval.retrieve import RetrievedChunk

REPO = "onnx-community/bge-reranker-v2-m3-ONNX"
REVISION = "6f5ff65298512715a1e669753bc754d2bc8f367b"  # pinned
MODEL_FILE = "onnx/model_int8.onnx"
# File -> SHA-256 from the Hub's LFS metadata; small JSON files aren't LFS.
FILES = {
    "config.json": None,
    "tokenizer_config.json": None,
    "special_tokens_map.json": None,
    "tokenizer.json": "8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3",
    MODEL_FILE: "912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d",
}
MAX_LENGTH = 512  # tokens per question + passage pair
BATCH = 4  # pairs per forward pass: keeps peak memory low on a 7 GB machine


class RerankerUnavailableError(RuntimeError):
    pass


def model_ready(model_dir: Path) -> bool:
    return (model_dir / MODEL_FILE).is_file() and (model_dir / "tokenizer.json").is_file()


def download(model_dir: Path, progress=print) -> None:
    """Fetches the pinned files and checks their hashes. An explicit command,
    like `ollama pull`: the app itself never downloads at runtime."""
    import httpx

    model_dir.mkdir(parents=True, exist_ok=True)
    for name, sha in FILES.items():
        target = model_dir / name
        if target.is_file() and (sha is None or _sha256(target) == sha):
            progress(f"have      {name}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}"
        with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            with partial.open("wb") as out:
                for block in response.iter_bytes(1 << 20):
                    out.write(block)
        if sha is not None and _sha256(partial) != sha:
            partial.unlink()
            raise RerankerUnavailableError(f"{name}: SHA-256 doesn't match the pinned file")
        partial.replace(target)
        progress(f"got       {name} ({target.stat().st_size / 1e6:.1f} MB)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class OnnxReranker(Reranker):
    """Loaded on first use, then kept: loading takes a few seconds and about
    0.6 GB of RAM. Thread-safe for the API and the job worker."""

    def __init__(self, model_dir: Path):
        self._model_dir = model_dir
        self._lock = threading.Lock()
        self._session = None
        self._tokenizer = None

    def _load(self) -> None:
        if self._session is not None:
            return
        if not model_ready(self._model_dir):
            raise RerankerUnavailableError(
                f"the reranker model isn't in {self._model_dir}; "
                "run `python -m app.cli reranker-download` first"
            )
        try:
            import onnxruntime
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover - both come with chromadb
            raise RerankerUnavailableError(
                "onnxruntime and tokenizers are needed: pip install -r requirements-rerank.txt"
            ) from exc
        tokenizer = Tokenizer.from_file(str(self._model_dir / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=MAX_LENGTH)
        tokenizer.enable_padding()
        self._tokenizer = tokenizer
        self._session = onnxruntime.InferenceSession(
            str(self._model_dir / MODEL_FILE), providers=["CPUExecutionProvider"]
        )

    def scores(self, question: str, passages: list[str]) -> list[float]:
        """Relevance in 0..1 (the sigmoid of the model's logit), one per passage."""
        import numpy as np

        with self._lock:
            self._load()
            results: list[float] = []
            for start in range(0, len(passages), BATCH):
                batch = passages[start : start + BATCH]
                encoded = self._tokenizer.encode_batch([(question, p) for p in batch])
                feed = {
                    "input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
                    "attention_mask": np.array([e.attention_mask for e in encoded], dtype=np.int64),
                }
                logits = self._session.run(None, feed)[0].reshape(-1)
                results += [1 / (1 + math.exp(-float(x))) for x in logits]
            return results

    def rerank(self, question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return chunks
        scored = zip(chunks, self.scores(question, [c.text for c in chunks]), strict=True)
        ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)
        return [replace(chunk, score=score) for chunk, score in ranked]
