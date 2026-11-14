"""Application configuration.

All config comes from environment variables (optionally via a `.env` file).
No hardcoded paths — everything persistent lives under `DATA_DIR`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    data_dir: Path = Path("./data")
    # Built frontend; empty = backend/static, then ../frontend/dist (none = API only)
    static_dir: Path | None = None

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "llama3.1"
    embedding_model: str = "bge-m3"

    # Retrieval defaults (see PLAN.md section 6)
    chunk_size_tokens: int = 600
    chunk_overlap_pct: float = 0.12
    retrieval_candidates: int = 20  # from each of vector search and FTS5, before RRF fusion
    retrieval_top_k: int = 5  # sent to the LLM, after fusion
    # bge-reranker-v2-m3 rescoring the fused candidates in the chat (decision 0023).
    # Off by default: it adds seconds per question on a CPU. Evaluation runs
    # can turn it on per run either way.
    rerank_enabled: bool = False
    rerank_model_dir: Path | None = None  # default DATA_DIR/hf/bge-reranker-v2-m3-onnx
    llm_temperature: float = 0.0  # repeatable answers (decision 0016)
    ollama_num_ctx: int = 8192

    # OCR fallback for low-text-yield PDF pages
    ocr_lang: str = "eng+spa"
    ocr_min_text_chars: int = 20
    tesseract_cmd: str | None = None
    tessdata_prefix: str | None = None

    # Jobs (one in-process worker)
    job_poll_interval_seconds: float = 1.0
    job_max_retries: int = 2  # automatic retries before a job stays failed
    max_upload_mb: int = 100
    # Automatic daily backups kept in DATA_DIR/backups (0 turns them off)
    backup_keep: int = 7

    # Watched folders (decision 0025). Polling instead of OS file events: needed
    # for Docker bind mounts and network drives, where events don't arrive.
    watch_polling: bool = False
    watch_poll_seconds: float = 5.0  # how often polling looks, when it's on
    # A file is queued once its size and time stop changing for this long, so a
    # copy in progress isn't ingested half-written.
    watch_settle_seconds: float = 2.0
    # Only folders inside these may be watched (separated by ";" on Windows and
    # ":" elsewhere, like PATH). Empty = the user's home folder. Anyone who can
    # reach the API could otherwise make the app read any folder on the machine.
    watch_roots: str = ""

    # Logging
    log_level: str = "INFO"

    # Developer only: simulate failures for the troubleshooter, e.g.
    # "sqlite,ollama_down" (see app/core/faults.py). Empty = off.
    simulate_faults: str = ""
    # Shown on the simulated L2 ticket instead of this machine's real name
    # and user (e.g. for screenshots). Empty = the real values.
    support_computer_name: str = ""
    support_user_name: str = ""

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def watch_root_paths(self) -> list[Path]:
        """WATCH_ROOTS as absolute paths; the home folder when it's empty."""
        import os

        parts = [p.strip() for p in self.watch_roots.split(os.pathsep) if p.strip()]
        return [Path(os.path.realpath(os.path.expanduser(p))) for p in parts] or [
            Path(os.path.realpath(Path.home()))
        ]

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def support_dir(self) -> Path:
        """Simulated L2 support tickets (nothing is sent anywhere)."""
        return self.data_dir / "support"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def hf_home(self) -> Path:
        return self.data_dir / "hf"

    @property
    def reranker_dir(self) -> Path:
        return self.rerank_model_dir or self.hf_home / "bge-reranker-v2-m3-onnx"

    def ensure_data_dirs(self) -> None:
        """Create DATA_DIR and its subdirectories if they don't exist."""
        dirs = (
            self.data_dir,
            self.files_dir,
            self.uploads_dir,
            self.chroma_dir,
            self.backups_dir,
            self.hf_home,
        )
        for path in dirs:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
