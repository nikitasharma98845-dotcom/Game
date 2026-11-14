from __future__ import annotations

import pytest

from bot.core import wallet
from bot.db import repo
from bot.db.models import Bet
from bot.games import all_games, get_game
from tests.conftest import USER_ID

TERMINAL = {"WON", "LOST", "CASHED_OUT", "REFUNDED"}


def _keys():
    return [g.key for g in all_games() if g.key not in ("roulette", "duel")]


@pytest.mark.parametrize("key", _keys())
async def test_each_game_round_through_engine(ctx, key):
    game = get_game(key)
    starter = game.quick_starts()[0]
    params = game.validate(dict(starter.params))
    play = await ctx.engine.place(USER_ID, key, 1_000, params)
    assert play.bet.game == key
    if play.bet.status == "ACTIVE":
        settled = await ctx.engine.auto_settle(play.bet.id, "test")
        assert settled is not None
        assert settled.bet.status in TERMINAL
        assert settled.bet.status != "ACTIVE"
    else:
        assert play.bet.status in TERMINAL
    async with ctx.session_factory() as session:
        bet = await session.get(Bet, play.bet.id)
        user = await repo.get_user(session, USER_ID)
        ledger_total = await wallet.ledger_sum(session, USER_ID)
    assert bet.status in TERMINAL
    assert user.balance >= 0
    assert user.balance == ledger_total


async def test_roulette_with_bet_slip(ctx):
    params = {
        "bets": [
            {"type": "color", "sel": "red", "amount": 600},
            {"type": "straight", "sel": [17], "amount": 400},
        ]
    }
    play = await ctx.engine.place(USER_ID, "roulette", 1_000, params)
    assert play.bet.status in ("WON", "LOST")
    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        ledger_total = await wallet.ledger_sum(session, USER_ID)
    assert user.balance == ledger_total


async def test_open_bet_and_manual_settlement(ctx):
    async with ctx.session_factory() as session:
        before = (await repo.get_user(session, USER_ID)).balance
    bet = await ctx.engine.open_bet(USER_ID, "crash", 1_000, {"target": "2"}, chat_id=-100)
    assert bet.status == "ACTIVE"
    settled = await ctx.engine.settle_manual(bet.id, 2.0, "CASHED_OUT", text="group crash")
    assert settled is not None and settled.status == "CASHED_OUT"
    assert settled.payout == 2_000
    # idempotent: a second settlement must not pay again
    again = await ctx.engine.settle_manual(bet.id, 2.0, "CASHED_OUT")
    assert again is not None and again.payout == 2_000
    async with ctx.session_factory() as session:
        after = (await repo.get_user(session, USER_ID)).balance
        ledger_total = await wallet.ledger_sum(session, USER_ID)
    assert after == before + 1_000
    assert after == ledger_total


async def test_double_tap_is_idempotent(ctx):
    play = await ctx.engine.place(USER_ID, "mines", 1_000, {"mines": "3"})
    state = play.bet.result["state"]
    safe = next(i for i in range(25) if i not in state["mines"])
    results = []
    for _ in range(3):
        try:
            results.append(await ctx.engine.step(USER_ID, play.bet.id, play.bet.step, "pick", str(safe)))
        except Exception:
            results.append(None)
    assert sum(1 for r in results if r is not None) == 1
    async with ctx.session_factory() as session:
        user = await repo.get_user(session, USER_ID)
        ledger_total = await wallet.ledger_sum(session, USER_ID)
    assert user.balance == ledger_total


def test_game_count_and_categories():
    games = all_games()
    assert len(games) >= 28
    categories = {g.category for g in games}
    assert {"instant", "cards", "risk", "wheel", "slots", "group"} <= categories
    for game in games:
        assert 0 < game.theoretical_rtp() <= 1
        assert game.rules_text
