from __future__ import annotations

from dataclasses import dataclass

import pytest_asyncio

from bot.config import Settings
from bot.core import wallet
from bot.core.bet_engine import BetEngine
from bot.core.rate_limit import MemoryRateLimiter
from bot.db import repo
from bot.db.session import create_engine, create_session_factory, init_models
from bot.games import all_games

USER_ID = 7001


@dataclass
class Ctx:
    settings: Settings
    session_factory: object
    engine: BetEngine
    db_engine: object


async def _build(tmp_path, **overrides) -> Ctx:
    settings = Settings(
        BOT_TOKEN="test-token",
        OWNER_TELEGRAM_ID=999,
        DATABASE_URL=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        **overrides,
    )
    db_engine = create_engine(settings.database_url)
    await init_models(db_engine)
    session_factory = create_session_factory(db_engine)
    async with session_factory() as session:
        await repo.ensure_settings(
            session,
            [game.key for game in all_games()],
            min_bet=settings.min_bet,
            max_bet=settings.max_bet,
            edge=settings.default_house_edge,
        )
        await repo.get_or_create_user(session, USER_ID, username="tester", first_name="Tester")
        await session.commit()
    await wallet.change(session_factory, USER_ID, 10_000_000, wallet.CREDIT, note="fixture")
    engine = BetEngine(settings, session_factory, MemoryRateLimiter(10_000))
    return Ctx(settings, session_factory, engine, db_engine)


@pytest_asyncio.fixture
async def ctx(tmp_path):
    built = await _build(tmp_path)
    yield built
    await built.db_engine.dispose()


@pytest_asyncio.fixture
async def tight_profit_ctx(tmp_path):
    built = await _build(tmp_path, MAX_PROFIT_PER_BET=1)
    yield built
    await built.db_engine.dispose()
