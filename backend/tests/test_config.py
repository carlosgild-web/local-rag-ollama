from pathlib import Path

from app.core.config import Settings


def test_defaults():
    settings = Settings(_env_file=None)
    assert settings.data_dir == Path("./data")
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.embedding_model == "bge-m3"
    assert settings.retrieval_top_k == 5


def test_reads_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("CHAT_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("WATCH_POLLING", "true")

    settings = Settings(_env_file=None)

    assert settings.data_dir == tmp_path
    assert settings.ollama_base_url == "http://ollama:11434"
    assert settings.chat_model == "qwen2.5:7b"
    assert settings.watch_polling is True


def test_derived_paths_and_dir_creation(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")

    assert settings.files_dir == tmp_path / "data" / "files"
    assert settings.chroma_dir == tmp_path / "data" / "chroma"
    assert not settings.files_dir.exists()

    settings.ensure_data_dirs()

    assert settings.files_dir.is_dir()
    assert settings.chroma_dir.is_dir()
    assert settings.backups_dir.is_dir()
    assert settings.hf_home.is_dir()
