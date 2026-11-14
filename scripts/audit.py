"""Ledger audit CLI: every user's balance must equal the sum of their ledger rows."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from bot.config import get_settings
from bot.db.models import Ledger, User
from bot.db.session import create_engine, create_session_factory


async def audit() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        sums = dict(
            (
                await session.execute(
                    select(Ledger.user_id, func.sum(Ledger.amount)).group_by(Ledger.user_id)
                )
            ).all()
        )
    await engine.dispose()
    mismatches = [
        (user.telegram_id, user.balance, int(sums.get(user.telegram_id, 0)))
        for user in users
        if user.balance != int(sums.get(user.telegram_id, 0))
    ]
    print(f"checked {len(users)} users")
    if not mismatches:
        print("OK: every balance equals its ledger sum")
        return 0
    for telegram_id, balance, ledger in mismatches:
        print(f"MISMATCH {telegram_id}: balance={balance} ledger={ledger} diff={balance - ledger}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(audit()))
