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

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "llama3.1"
    embedding_model: str = "bge-m3"

    # Retrieval defaults (see PLAN.md section 6)
    chunk_size_tokens: int = 600
    chunk_overlap_pct: float = 0.12
    retrieval_candidates: int = 20  # from each of vector search and FTS5, before RRF fusion
    retrieval_top_k: int = 5  # sent to the LLM, after fusion
    rerank_enabled: bool = False  # off in MVP; hook point for bge-reranker-v2-m3 later
    llm_temperature: float = 0.2
    ollama_num_ctx: int = 8192

    # OCR fallback for low-text-yield PDF pages
    ocr_lang: str = "eng+spa"
    ocr_min_text_chars: int = 20
    tesseract_cmd: str | None = None
    tessdata_prefix: str | None = None

    # File watching
    watch_polling: bool = False

    # Logging
    log_level: str = "INFO"

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
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def hf_home(self) -> Path:
        return self.data_dir / "hf"

    def ensure_data_dirs(self) -> None:
        """Create DATA_DIR and its subdirectories if they don't exist."""
        dirs = (self.data_dir, self.files_dir, self.chroma_dir, self.backups_dir, self.hf_home)
        for path in dirs:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
