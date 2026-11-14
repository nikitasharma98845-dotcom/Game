from __future__ import annotations

import asyncio

import pytest

from bot.core import wallet
from bot.core.errors import InsufficientFunds
from bot.db import repo
from tests.conftest import USER_ID


async def test_balance_always_equals_ledger_sum(ctx):
    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        ledger_total = await wallet.ledger_sum(session, USER_ID)
    assert user.balance == ledger_total


async def test_thousand_concurrent_changes_stay_consistent(ctx):
    async def credit(i: int) -> None:
        await wallet.change(ctx.session_factory, USER_ID, 7, wallet.CREDIT, note=f"c{i}")

    async def debit(i: int) -> None:
        await wallet.change(ctx.session_factory, USER_ID, -3, wallet.DEBIT, note=f"d{i}")

    tasks = []
    for i in range(500):
        tasks.append(asyncio.create_task(credit(i)))
        tasks.append(asyncio.create_task(debit(i)))
    await asyncio.gather(*tasks)

    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        ledger_total = await wallet.ledger_sum(session, USER_ID)
    assert user.balance == ledger_total
    assert user.balance == 10_000_000 + 500 * 7 - 500 * 3
    assert user.balance >= 0


async def test_debit_cannot_make_balance_negative(ctx):
    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        current = user.balance
    with pytest.raises(InsufficientFunds):
        await wallet.change(ctx.session_factory, USER_ID, -(current + 1), wallet.DEBIT)
    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        ledger_total = await wallet.ledger_sum(session, USER_ID)
    assert user.balance == current
    assert user.balance == ledger_total


async def test_every_change_writes_a_ledger_row(ctx):
    async with ctx.session_factory() as session:
        before = await repo.user_ledger(session, USER_ID, 1000)
    await wallet.change(ctx.session_factory, USER_ID, 500, wallet.CREDIT, note="audit")
    async with ctx.session_factory() as session:
        after = await repo.user_ledger(session, USER_ID, 1000)
    assert len(after) == len(before) + 1
    assert after[0].type == wallet.CREDIT
    assert after[0].amount == 500
