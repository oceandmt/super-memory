from logging.config import fileConfig
from pathlib import Path
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def get_sqlite_url() -> str:
    """Derive the SQLite URL, preferring the programmatic config option."""
    url = config.get_main_option("sqlalchemy.url", "")
    if url and url != "sqlite:///data/sm.sqlite3":
        return url
    try:
        from super_memory.config import load_config
        from super_memory.migrations import sqlite_path as _sqlite_path
        cfg = load_config(None)
        db_path = _sqlite_path(cfg)
        return f"sqlite:///{db_path}"
    except Exception:
        return "sqlite:///data/sm.sqlite3"


def run_migrations_offline() -> None:
    url = get_sqlite_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_sqlite_url()
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
