from __future__ import annotations

import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import Settings
from bot.core.bet_engine import Play
from bot.games.base import Button
from bot.texts import en

SHORTCUT = re.compile(r"^(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[kKmM]?)$")


def parse_amount(text: str, balance: int, settings: Settings) -> int:
    """Parse '100', '2.5k', 'max', 'half', 'min' into integer cents."""
    raw = text.strip().lower().replace(",", "").replace("🪙", "").strip()
    if raw in ("max", "all", "allin", "all-in"):
        return max(0, min(balance, settings.max_bet))
    if raw == "half":
        return max(0, min(balance // 2, settings.max_bet))
    if raw == "min":
        return settings.min_bet
    match = SHORTCUT.match(raw)
    if not match:
        raise ValueError("Send a number, or max / half / min / 1k / 2.5k.")
    number = float(match.group("num"))
    unit = match.group("unit").lower()
    if unit == "k":
        number *= 1_000
    elif unit == "m":
        number *= 1_000_000
    cents = int(round(number * 100))
    if cents <= 0:
        raise ValueError("Your bet must be positive.")
    return cents


def game_callback(action: str, play: Play, arg: str = "") -> str:
    return f"s:{play.bet.id}:{play.bet.step}:{action}:{arg}"[:64]


def keyboard(rows: list[list[Button]], play: Play) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=b.label, callback_data=game_callback(b.action, play, b.arg))
                for b in row
            ]
            for row in rows
        ]
    )


def finished_keyboard(play: Play) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🔁 Play again", callback_data=f"again:{play.bet.id}"),
            InlineKeyboardButton(text="✖️ Double", callback_data=f"againd:{play.bet.id}"),
            InlineKeyboardButton(text="½ Half", callback_data=f"againh:{play.bet.id}"),
        ],
        [InlineKeyboardButton(text="ℹ️ Rules", callback_data=f"rules:{play.game.key}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def celebration(multiplier: float) -> str:
    for threshold, template in en.WIN_TIERS:
        if multiplier >= threshold:
            return template.format(mult=en.fmtx(multiplier))
    return ""


def play_text(play: Play) -> str:
    bet = play.bet
    header = f"{play.game.emoji} <b>{play.game.name}</b> · bet {en.money(bet.amount)}"
    body = play.round.text or "…"
    if bet.status == "ACTIVE":
        footer = f"\n\nStake: <b>{en.money(bet.amount)}</b> · Balance: <b>{en.money(play.balance)}</b>"
        return f"{header}\n\n{body}{footer}"
    win = celebration(bet.multiplier) if bet.payout > bet.amount else ""
    footer = (
        f"\n\nStake <b>{en.money(bet.amount)}</b> · Multiplier <b>{bet.multiplier:.2f}x</b> · "
        f"Payout <b>{en.money(bet.payout)}</b> · Balance <b>{en.money(play.balance)}</b>"
    )
    if win:
        footer += f"\n{win}"
    return f"{header}\n\n{body}{footer}"


def play_keyboard(play: Play) -> InlineKeyboardMarkup:
    if play.bet.status == "ACTIVE":
        rows = [row for row in play.round.buttons]
        rows.append([Button("ℹ️ Rules", "noop")])
        kb = keyboard(rows, play)
        # Rules button is a separate callback, not a game step.
        kb.inline_keyboard[-1] = [
            InlineKeyboardButton(text="ℹ️ Rules", callback_data=f"rules:{play.game.key}")
        ]
        return kb
    return finished_keyboard(play)


def menu_keyboard() -> InlineKeyboardMarkup:
    from bot.games import CATEGORIES

    rows = []
    for i in range(0, len(CATEGORIES), 2):
        rows.append(
            [
                InlineKeyboardButton(text=label, callback_data=f"cat:{key}")
                for key, label in CATEGORIES[i : i + 2]
            ]
        )
    rows.append([InlineKeyboardButton(text="🏆 Leaderboard", callback_data="lb:all")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def games_keyboard(category: str) -> InlineKeyboardMarkup:
    from bot.games import games_by_category

    games = games_by_category(category)
    rows = []
    for i in range(0, len(games), 2):
        rows.append(
            [
                InlineKeyboardButton(text=f"{g.emoji} {g.name}", callback_data=f"pick:{g.key}")
                for g in games[i : i + 2]
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def starters_keyboard(game_key: str, starters, cents: int) -> InlineKeyboardMarkup:
    rows = []
    for start in range(0, len(starters), 2):
        row = []
        for index in range(start, min(start + 2, len(starters))):
            row.append(
                InlineKeyboardButton(
                    text=starters[index].label[:60],
                    callback_data=f"go:{game_key}:{cents}:{index}",
                )
            )
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="games")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
