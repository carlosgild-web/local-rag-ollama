"""Runs Alembic migrations programmatically, so the API and CLI bring the
database to the current schema on startup ("clone and run")."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def known_revisions() -> set[str]:
    """Every schema revision this version of the app knows (a backup from a newer app
    has one it doesn't)."""
    return {r.revision for r in ScriptDirectory.from_config(_config()).walk_revisions()}


def head_revision() -> str:
    """The schema revision this version of the app expects."""
    return ScriptDirectory.from_config(_config()).get_current_head()


def upgrade_to_head(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = _config()
    config.attributes["db_path"] = str(db_path)
    config.attributes["configure_logging"] = False
    command.upgrade(config, "head")
