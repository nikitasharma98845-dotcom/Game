from __future__ import annotations

import asyncio
import os
import pathlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from bot.db.models import Base
from bot.db.url import normalize_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", normalize_database_url(database_url))

# Alembic connects before the application's create_engine() helper runs, so make
# sure a SQLite file's parent directory exists (e.g. ./data/ on first boot).
configured_url = normalize_database_url(config.get_main_option("sqlalchemy.url") or "")
if configured_url.startswith("sqlite"):
    sqlite_path = configured_url.split(":///", 1)[-1].split("?", 1)[0]
    if sqlite_path and sqlite_path != ":memory:":
        pathlib.Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
