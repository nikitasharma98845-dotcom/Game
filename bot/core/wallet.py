from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.errors import InsufficientFunds
from bot.db.models import Ledger, User, utcnow

# Ledger is the single source of truth. Every balance change writes one row and
# users.balance must always equal SUM(ledger.amount) for that user.
CREDIT = "ADMIN_CREDIT"
DEBIT = "ADMIN_DEBIT"
BET = "BET"
WIN = "WIN"
REFUND = "REFUND"
RESET = "RESET"

_locks: dict[int, asyncio.Lock] = {}
_bet_locks: dict[int, asyncio.Lock] = {}


def user_lock(user_id: int) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


def bet_lock(bet_id: int) -> asyncio.Lock:
    lock = _bet_locks.get(bet_id)
    if lock is None:
        lock = asyncio.Lock()
        _bet_locks[bet_id] = lock
    return lock


def credit_in_session(
    session: AsyncSession,
    user: User,
    amount: int,
    kind: str,
    *,
    game: str | None = None,
    bet_id: int | None = None,
    admin_id: int | None = None,
    note: str | None = None,
) -> Ledger:
    """Low-level mutation. Caller must hold the user lock and an open transaction."""
    new_balance = user.balance + amount
    if new_balance < 0:
        raise InsufficientFunds("Not enough Chips.")
    user.balance = new_balance
    ledger = Ledger(
        user_id=user.telegram_id,
        type=kind,
        amount=amount,
        balance_after=new_balance,
        game=game,
        bet_id=bet_id,
        admin_id=admin_id,
        note=note,
    )
    session.add(ledger)
    return ledger


async def change(
    session_factory,
    user_id: int,
    amount: int,
    kind: str,
    *,
    game: str | None = None,
    bet_id: int | None = None,
    admin_id: int | None = None,
    note: str | None = None,
) -> tuple[Ledger, int]:
    """Atomically apply a balance delta, returning the ledger row and new balance."""
    async with user_lock(user_id):
        async with session_factory() as session:
            async with session.begin():
                user = await session.get(User, user_id, with_for_update=True)
                if user is None:
                    raise InsufficientFunds("Unknown user.")
                ledger = credit_in_session(
                    session,
                    user,
                    amount,
                    kind,
                    game=game,
                    bet_id=bet_id,
                    admin_id=admin_id,
                    note=note,
                )
                balance = user.balance
                user.last_active = utcnow()
    return ledger, balance


async def balance(session: AsyncSession, user_id: int) -> int:
    user = await session.get(User, user_id)
    return user.balance if user else 0


async def ledger_sum(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(Ledger.amount).where(Ledger.user_id == user_id)
    )
    return sum(result.scalars().all())


@asynccontextmanager
async def locked_user(session_factory, user_id: int) -> AsyncIterator[AsyncSession]:
    """Session + user row lock for multi-step settlements."""
    async with user_lock(user_id):
        async with session_factory() as session:
            async with session.begin():
                yield session
