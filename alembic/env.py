"""Alembic migration environment.

Uses a synchronous psycopg2 connection (for offline + online migration runs).
The database URL is sourced from the app .env so there is a single source of
truth for the connection string.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from mediaforge.db.tables import Base  # noqa: E402

target_metadata = Base.metadata


def _get_url() -> str:
    url = os.environ.get("ALEMBIC_DATABASE_URL")
    if url:
        # Accept either asyncpg or plain postgresql URL.
        return url.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")

    from mediaforge.config import get_settings
    url = get_settings().database_url
    # Strip asyncpg dialect; use psycopg2 for synchronous migration runner.
    return url.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg2://")


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
