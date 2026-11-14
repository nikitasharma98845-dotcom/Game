from __future__ import annotations

import pytest

from bot.config import Settings
from bot.core.bet_engine import Play
from bot.db.models import Bet
from bot.games import get_game
from bot.games.base import Round
from bot.handlers.play import _parse_roulette_text
from bot.handlers.ui import (
    finished_keyboard,
    games_keyboard,
    menu_keyboard,
    parse_amount,
    play_keyboard,
    play_text,
    starters_keyboard,
)

SETTINGS = Settings(BOT_TOKEN="x", OWNER_TELEGRAM_ID=1, MIN_BET=1, MAX_BET=100_000)


def test_parse_amount_shortcuts():
    assert parse_amount("100", 10_000_00, SETTINGS) == 10_000
    assert parse_amount("2.5k", 10_000_00, SETTINGS) == 250_000
    assert parse_amount("1,000", 10_000_00, SETTINGS) == 100_000
    assert parse_amount("max", 500_00, SETTINGS) == 500_00
    assert parse_amount("half", 500_00, SETTINGS) == 250_00
    assert parse_amount("min", 500_00, SETTINGS) == 100
    with pytest.raises(ValueError):
        parse_amount("abc", 500_00, SETTINGS)
    with pytest.raises(ValueError):
        parse_amount("0", 500_00, SETTINGS)


def test_starters_keyboard_callbacks_are_valid():
    game = get_game("dice")
    keyboard = starters_keyboard("dice", game.quick_starts(), 1_000)
    assert keyboard.inline_keyboard
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert all(c and len(c.encode()) <= 64 for c in callbacks)
    assert any(c.startswith("go:dice:1000:") for c in callbacks)
    back = keyboard.inline_keyboard[-1][0]
    assert back.callback_data == "games"


def test_play_text_and_finished_keyboard():
    bet = Bet(
        id=5,
        user_id=1,
        game="dice",
        amount=1_000,
        multiplier=1.98,
        payout=1_980,
        profit=980,
        status="WON",
        step=1,
        result={},
        server_seed_hash="x",
        client_seed="c",
        nonce=1,
    )
    play = Play(
        bet=bet,
        round=Round(finished=True, text="Rolled 12.34", multiplier=1.98, status="WON"),
        game=get_game("dice"),
        balance=10_000,
    )
    text = play_text(play)
    assert "Dice" in text
    assert "1.98x" in text
    assert "Play again" in str(finished_keyboard(play).inline_keyboard)
    assert play_keyboard(play).inline_keyboard


def test_active_play_has_step_callbacks_and_rules():
    bet = Bet(
        id=9,
        user_id=1,
        game="mines",
        amount=1_000,
        multiplier=1.0,
        payout=0,
        profit=0,
        status="ACTIVE",
        step=2,
        result={},
        server_seed_hash="x",
        client_seed="c",
        nonce=1,
    )
    from tests.sim import FastRNG

    game = get_game("mines")
    rnd = game.start(FastRNG(3), {"mines": "3"}, 1_000)
    bet.step = 0
    play = Play(bet=bet, round=rnd, game=game, balance=10_000)
    keyboard = play_keyboard(play)
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert any(c.startswith("s:9:0:pick:") for c in callbacks)
    assert any(c.startswith("s:9:0:cashout") for c in callbacks)
    assert "rules:mines" in callbacks


def test_menu_and_games_keyboards():
    menu = menu_keyboard()
    callbacks = [b.callback_data for row in menu.inline_keyboard for b in row]
    assert "cat:instant" in callbacks
    assert "lb:all" in callbacks
    games = games_keyboard("slots")
    callbacks = [b.callback_data for row in games.inline_keyboard for b in row]
    assert "pick:pharaoh" in callbacks
    assert games.inline_keyboard[-1][0].callback_data == "menu"


def test_roulette_text_parser():
    assert _parse_roulette_text("red 100") == {"type": "color", "sel": "red", "amount": 10_000}
    assert _parse_roulette_text("split 1-2 50") == {"type": "split", "sel": [1, 2], "amount": 5_000}
    assert _parse_roulette_text("corner 1-2-4-5 100")["sel"] == [1, 2, 4, 5]
    assert _parse_roulette_text("straight 17 100")["sel"] == [17]
    assert _parse_roulette_text("dozen 2 100") == {"type": "dozen", "sel": "2", "amount": 10_000}
    assert _parse_roulette_text("nonsense") is None
    assert _parse_roulette_text("straight 99 100") is None
