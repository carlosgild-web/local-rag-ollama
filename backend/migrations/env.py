from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.models import Base

config = context.config

# Programmatic callers (app/db/migrate.py) keep the app's own logging config.
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Skip the FTS5 virtual table and its shadow tables: they are created with
    raw DDL (app/db/fts.py), so autogenerate must not try to drop them."""
    return not (type_ == "table" and name.startswith("chunks_fts"))


def _get_url() -> str:
    if "db_path" in config.attributes:
        return f"sqlite:///{config.attributes['db_path']}"
    x_args = context.get_x_argument(as_dictionary=True)
    if "db_path" in x_args:
        return f"sqlite:///{x_args['db_path']}"
    return f"sqlite:///{get_settings().db_path}"


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        include_object=_include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
