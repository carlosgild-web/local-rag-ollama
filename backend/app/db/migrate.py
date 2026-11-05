"""Runs Alembic migrations programmatically, so the API and CLI bring the
database to the current schema on startup ("clone and run")."""

from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]


def upgrade_to_head(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["db_path"] = str(db_path)
    config.attributes["configure_logging"] = False
    command.upgrade(config, "head")
