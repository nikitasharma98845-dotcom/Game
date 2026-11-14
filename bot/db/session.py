from __future__ import annotations

import pathlib

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bot.db.models import Base
from bot.db.url import normalize_database_url


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite") and ":///" in url:
        path = url.split(":///", 1)[1]
        if path and path != ":memory:":
            pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    database_url = normalize_database_url(database_url)
    _ensure_sqlite_dir(database_url)
    kwargs: dict = {"echo": echo, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 30}
    return create_async_engine(database_url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def init_models(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
