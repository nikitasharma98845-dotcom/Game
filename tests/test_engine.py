from __future__ import annotations

import datetime as dt

import pytest

from bot.core import fairness, wallet
from bot.core.errors import BettingClosed, GameError, InsufficientFunds, StaleBet
from bot.db import repo
from bot.db.models import Bet, utcnow
from tests.conftest import USER_ID


async def test_place_and_settle_moves_money_once(ctx):
    play = await ctx.engine.place(USER_ID, "dice", 1_000, {"direction": "under", "target": "50"})
    assert play.bet.status in ("WON", "LOST")
    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        total = await wallet.ledger_sum(session, USER_ID)
        bet = await session.get(Bet, play.bet.id)
    assert user.balance == total
    assert bet.status == play.bet.status
    assert bet.payout == play.bet.payout


async def test_stale_callback_is_rejected(ctx):
    play = await ctx.engine.place(USER_ID, "mines", 1_000, {"mines": "3"})
    state = play.bet.result["state"]
    safe = next(i for i in range(25) if i not in state["mines"])
    stepped = await ctx.engine.step(USER_ID, play.bet.id, play.bet.step, "pick", str(safe))
    assert stepped.bet.step == 1
    with pytest.raises(StaleBet):
        await ctx.engine.step(USER_ID, play.bet.id, 0, "pick", str(safe))


async def test_other_player_cannot_step(ctx):
    play = await ctx.engine.place(USER_ID, "mines", 1_000, {"mines": "3"})
    with pytest.raises(GameError) as exc:
        await ctx.engine.step(USER_ID + 1, play.bet.id, 0, "cashout", "")
    assert str(exc.value) == "not_yours"


async def test_profit_cap_applies(tight_profit_ctx):
    ctx = tight_profit_ctx
    # Play dice repeatedly until a win; the win payout must be capped at stake + cap.
    for _ in range(60):
        play = await ctx.engine.place(USER_ID, "dice", 1_000, {"direction": "under", "target": "50"})
        if play.bet.status == "WON":
            assert play.bet.payout <= 1_100
            assert play.bet.profit <= 100
            return
    pytest.fail("expected at least one win")


async def test_timeout_auto_cashes_out(ctx):
    play = await ctx.engine.place(USER_ID, "mines", 1_000, {"mines": "3"})
    async with ctx.session_factory() as session:
        bet = await session.get(Bet, play.bet.id)
        bet.created_at = utcnow() - dt.timedelta(hours=2)
        await session.commit()
    settled = await ctx.engine.timeout_active(older_than_seconds=60)
    assert settled >= 1
    async with ctx.session_factory() as session:
        bet = await session.get(Bet, play.bet.id)
        user = await repo.get_user(session, USER_ID)
        total = await wallet.ledger_sum(session, USER_ID)
    assert bet.status == "CASHED_OUT"
    assert bet.payout == 1_000
    assert user.balance == total


async def test_refund_restores_stake(ctx):
    async with ctx.session_factory() as session:
        before = (await repo.get_user(session, USER_ID)).balance
    play = await ctx.engine.place(USER_ID, "mines", 1_000, {"mines": "5"})
    refunded = await ctx.engine.refund(play.bet.id, "test")
    assert refunded == 1_000
    assert await ctx.engine.refund(play.bet.id, "test") is None  # idempotent
    async with ctx.session_factory() as session:
        after = (await repo.get_user(session, USER_ID)).balance
        bet = await session.get(Bet, play.bet.id)
    assert after == before
    assert bet.status == "REFUNDED"


async def test_daily_limit_blocks_bets(ctx):
    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        user.daily_limit = 1_500
        user.daily_wagered = 0
        await session.commit()
    await ctx.engine.place(USER_ID, "dice", 1_000, {"direction": "under", "target": "10"})
    with pytest.raises(BettingClosed):
        await ctx.engine.place(USER_ID, "dice", 1_000, {"direction": "under", "target": "10"})


async def test_insufficient_balance_is_rejected(ctx):
    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        user.balance = 50
        await session.commit()
    with pytest.raises(InsufficientFunds):
        await ctx.engine.place(USER_ID, "dice", 1_000, {"direction": "under", "target": "50"})


async def test_verify_after_seed_rotation(ctx):
    play = await ctx.engine.place(USER_ID, "dice", 1_000, {"direction": "under", "target": "50"})
    async with ctx.session_factory() as session:
        await fairness.rotate_seed(session, USER_ID)
        await session.commit()
    info = await ctx.engine.verify(play.bet.id)
    assert info["ok"] is True
    assert info["revealed"] is True
    assert info["matches"] is True


async def test_one_active_round_per_game(ctx):
    first = await ctx.engine.place(USER_ID, "mines", 1_000, {"mines": "3"})
    assert first.bet.status == "ACTIVE"
    with pytest.raises(GameError):
        await ctx.engine.place(USER_ID, "mines", 1_000, {"mines": "3"})
    await ctx.engine.auto_settle(first.bet.id, "test")
    second = await ctx.engine.place(USER_ID, "mines", 1_000, {"mines": "3"})
    assert second.bet.status == "ACTIVE"


async def test_owner_edge_change_rescales_payout(ctx):
    from bot.db.models import GameSetting

    async with ctx.session_factory() as session:
        setting = await session.get(GameSetting, "dice")
        setting.house_edge = 0.05
        await session.commit()
    play = None
    for _ in range(80):
        play = await ctx.engine.place(USER_ID, "dice", 1_000, {"direction": "under", "target": "50"})
        if play.bet.status == "WON":
            break
    assert play is not None and play.bet.status == "WON"
    expected = 1.98 * (0.95 / 0.99)
    assert play.bet.multiplier == pytest.approx(expected, rel=0.01)


async def test_verify_before_reveal_shows_commitment(ctx):
    play = await ctx.engine.place(USER_ID, "dice", 1_000, {"direction": "under", "target": "50"})
    info = await ctx.engine.verify(play.bet.id)
    assert info["ok"] is True
    assert info["revealed"] is False
    assert info["proof_len"] >= 1
