from __future__ import annotations

import asyncio
import contextlib
import html
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import Settings
from bot.core.bet_engine import BetEngine, Play
from bot.core.errors import (
    BettingClosed,
    GameError,
    InsufficientFunds,
    RateLimited,
    StaleBet,
)
from bot.db.models import Bet
from bot.games import get_game
from bot.handlers.ui import (
    finished_keyboard,
    parse_amount,
    play_keyboard,
    play_text,
    starters_keyboard,
)
from bot.texts import en

router = Router(name="play")
_slip: dict[tuple[int, int], dict] = {}
_crash_tasks: set[asyncio.Task] = set()
_engine: BetEngine | None = None


class BetFlow(StatesGroup):
    waiting_bet = State()
    roulette = State()


def configure(engine: BetEngine) -> None:
    global _engine
    _engine = engine


def _user_key(message_or_call) -> tuple[int, int]:
    return (message_or_call.chat.id, message_or_call.from_user.id)


async def begin_game(
    message: Message,
    user_id: int,
    game_key: str,
    cents: int,
    state: FSMContext,
    settings: Settings,
) -> None:
    game = get_game(game_key)
    if game is None:
        await message.answer("Unknown game.")
        return
    if game.key == "duel":
        await message.answer("⚔️ Dice Duel is played in a group: send <code>/duel &lt;bet&gt;</code>.")
        return
    if game.key == "roulette":
        await state.set_state(BetFlow.roulette)
        await state.update_data(slip_stake=cents)
        _slip[(message.chat.id, user_id)] = {"stake": cents, "bets": []}
        await message.answer(
            "🎡 <b>Roulette bet slip</b>\n\n"
            f"Unit size: <b>{en.money(cents)}</b>\n"
            "Tap outside bets or a number to add the unit. Typed bets: "
            "<code>red 200</code>, <code>split 1-2 100</code>, "
            "<code>corner 1-2-4-5 100</code>, <code>line 1-6 100</code>.\n"
            "Press Spin when ready.",
            reply_markup=_roulette_keyboard(),
        )
        return
    starters = game.quick_starts()
    await state.clear()
    await message.answer(
        f"{game.emoji} <b>{game.name}</b>\nBet: <b>{en.money(cents)}</b>\n\n"
        "Choose how to play:\n"
        f"<i>Unfinished rounds auto-cash-out after {max(1, settings.session_timeout_seconds // 60)} min.</i>",
        reply_markup=starters_keyboard(game_key, starters, cents),
    )


def _roulette_keyboard() -> InlineKeyboardMarkup:
    outside = [
        ("🔴 Red", "rs:color:red"),
        ("⚫ Black", "rs:color:black"),
        ("Odd", "rs:parity:odd"),
        ("Even", "rs:parity:even"),
        ("1–18", "rs:half:low"),
        ("19–36", "rs:half:high"),
        ("1st 12", "rs:dozen:1"),
        ("2nd 12", "rs:dozen:2"),
        ("3rd 12", "rs:dozen:3"),
        ("Col 1", "rs:column:1"),
        ("Col 2", "rs:column:2"),
        ("Col 3", "rs:column:3"),
    ]
    rows = [
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in outside[i : i + 3]]
        for i in range(0, len(outside), 3)
    ]
    numbers = [InlineKeyboardButton(text=str(n), callback_data=f"rn:{n}") for n in range(37)]
    rows.extend([numbers[i : i + 6] for i in range(0, len(numbers), 6)])
    rows.append(
        [
            InlineKeyboardButton(text="🎡 Spin", callback_data="rspin"),
            InlineKeyboardButton(text="🗑 Clear", callback_data="rclear"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick(call: CallbackQuery, state: FSMContext) -> None:
    game_key = call.data.split(":", 1)[1]
    game = get_game(game_key)
    if game is None:
        await call.answer("Unknown game.", show_alert=True)
        return
    if game.key == "duel":
        await call.answer("Use /duel <bet> in a group.", show_alert=True)
        return
    await state.set_state(BetFlow.waiting_bet)
    await state.update_data(game=game_key)
    await call.message.answer(
        en.BET_PROMPT.format(name=game.name, emoji=game.emoji)
        + "\n\n<i>Shortcuts: 1k, 2.5k, max, half, min</i>"
    )
    await call.answer()


@router.message(BetFlow.waiting_bet)
async def msg_bet(message: Message, state: FSMContext, user_row, settings: Settings) -> None:
    data = await state.get_data()
    game_key = data.get("game")
    if not game_key:
        await state.clear()
        return
    try:
        cents = parse_amount(message.text or "", user_row.balance, settings)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    if cents > user_row.balance:
        await message.answer(en.INSUFFICIENT)
        return
    await state.clear()
    await begin_game(message, message.from_user.id, game_key, cents, state, settings)


@router.callback_query(F.data.startswith("go:"))
async def cb_go(call: CallbackQuery, engine: BetEngine, settings: Settings) -> None:
    _, game_key, cents, index = call.data.split(":", 3)
    game = get_game(game_key)
    if game is None:
        await call.answer("Unknown game.", show_alert=True)
        return
    starters = game.quick_starts()
    try:
        starter = starters[int(index)]
    except IndexError:
        await call.answer("This option is gone.", show_alert=True)
        return
    await call.answer()
    try:
        play = await engine.place(
            call.from_user.id,
            game_key,
            int(cents),
            starter.params,
            chat_id=call.message.chat.id,
        )
    except InsufficientFunds:
        await call.message.answer(en.INSUFFICIENT)
        return
    except RateLimited as exc:
        await call.message.answer(en.RATE_LIMITED.format(seconds=f"{exc.retry_after:.1f}"))
        return
    except BettingClosed as exc:
        await call.message.answer(_closed_text(exc))
        return
    except GameError as exc:
        await call.message.answer(f"❌ {html.escape(str(exc))}")
        return
    await send_play(call.bot, call.message.chat.id, play, settings)


def _closed_text(exc: BettingClosed) -> str:
    reason = str(exc)
    if reason == "banned":
        return en.BANNED
    if reason == "paused":
        return "⏸ You have play paused. Take a break and come back later."
    if reason == "daily_limit":
        return "🛑 Your daily limit is reached. It resets at midnight UTC."
    if reason == "disabled":
        return en.GAME_OFF
    return "🚫 Play is currently unavailable."


def _image_for(play: Play) -> bytes | None:
    detail = play.round.detail or {}
    kind = detail.get("image")
    if not kind:
        return None
    from bot.render import boards

    try:
        if kind == "plinko":
            return boards.plinko_board(detail["table"], detail["slot"])
        if kind == "wheel":
            return boards.wheel_image(detail["values"], detail["index"])
        if kind == "roulette":
            return boards.roulette_image(detail["number"], detail["color"])
        if kind == "mines":
            return boards.mines_board(
                detail.get("revealed", []),
                detail.get("mines", []),
                detail.get("reveal", False),
            )
        if kind == "crash":
            return boards.crash_chart(float(detail.get("crash", 1.0)))
    except Exception:
        return None
    return None


async def send_play(bot, chat_id: int, play: Play, settings: Settings) -> Message | None:
    image = _image_for(play) if settings.render_images else None
    caption = play_text(play)
    markup = play_keyboard(play)
    try:
        if image and len(caption) <= 1024:
            message = await bot.send_photo(
                chat_id,
                BufferedInputFile(image, filename="board.png"),
                caption=caption,
                reply_markup=markup,
            )
        else:
            message = await bot.send_message(chat_id, caption, reply_markup=markup)
    except Exception:
        return None
    if play.game.key == "crash" and play.bet.status == "ACTIVE":
        task = asyncio.create_task(_crash_live(bot, chat_id, message.message_id, play.bet.id))
        _crash_tasks.add(task)
        task.add_done_callback(_crash_tasks.discard)
    return message


async def _crash_live(bot, chat_id: int, message_id: int, bet_id: int) -> None:
    engine = _engine
    if engine is None:
        return
    try:
        while True:
            await asyncio.sleep(1.2)
            current = await engine.view(bet_id)
            if current is None:
                break
            crash = float(((current.bet.result or {}).get("state") or {}).get("crash", 0))
            if current.round.multiplier >= crash:
                settled = await engine.auto_settle(bet_id, "crash")
                if settled is not None:
                    with contextlib.suppress(Exception):
                        await bot.edit_message_text(
                            play_text(settled),
                            chat_id=chat_id,
                            message_id=message_id,
                            reply_markup=finished_keyboard(settled),
                        )
                break
            with contextlib.suppress(Exception):
                await bot.edit_message_text(
                    play_text(current),
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=play_keyboard(current),
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        return


@router.callback_query(F.data.startswith("s:"))
async def cb_step(call: CallbackQuery, engine: BetEngine, settings: Settings) -> None:
    parts = call.data.split(":", 4)
    if len(parts) < 5:
        await call.answer()
        return
    _, bet_id, step, action, arg = parts
    try:
        play = await engine.step(
            call.from_user.id,
            int(bet_id),
            int(step),
            action,
            arg,
            chat_id=call.message.chat.id,
        )
    except StaleBet:
        await call.answer(en.STALE, show_alert=False)
        return
    except GameError as exc:
        if str(exc) == "not_yours":
            await call.answer(en.NOT_YOURS, show_alert=True)
        else:
            await call.answer(f"❌ {exc}", show_alert=True)
        return
    except InsufficientFunds:
        await call.answer("Not enough Chips for that action.", show_alert=True)
        return
    except RateLimited as exc:
        await call.answer(f"Slow down — {exc.retry_after:.1f}s", show_alert=False)
        return
    except BettingClosed as exc:
        await call.answer(_closed_text(exc), show_alert=True)
        return
    await call.answer()
    await _edit_play(call, play, settings)


async def _edit_play(call: CallbackQuery, play: Play, settings: Settings) -> None:
    text = play_text(play)
    markup = play_keyboard(play)
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await send_play(call.bot, call.message.chat.id, play, settings)


@router.callback_query(F.data.startswith("again"))
async def cb_again(call: CallbackQuery, engine: BetEngine, settings: Settings, session_factory) -> None:
    kind, _, bet_id = call.data.partition(":")
    if not bet_id.isdigit():
        await call.answer()
        return
    async with session_factory() as session:
        old = await session.get(Bet, int(bet_id))
        if old is None:
            await call.answer("Bet not found.", show_alert=True)
            return
        game_key = old.game
        params = dict(old.params or {})
        stake = old.amount
    if kind == "againd":
        stake *= 2
    elif kind == "againh":
        stake = max(settings.min_bet, stake // 2)
    try:
        play = await engine.place(call.from_user.id, game_key, stake, params, chat_id=call.message.chat.id)
    except InsufficientFunds:
        await call.answer(en.INSUFFICIENT, show_alert=True)
        return
    except (GameError, BettingClosed) as exc:
        await call.answer(str(exc)[:180], show_alert=True)
        return
    await call.answer()
    await send_play(call.bot, call.message.chat.id, play, settings)


@router.callback_query(F.data.startswith("resume:"))
async def cb_resume(call: CallbackQuery, engine: BetEngine, settings: Settings) -> None:
    bet_id = int(call.data.split(":", 1)[1])
    play = await engine.view(bet_id)
    if play is None or play.bet.user_id != call.from_user.id:
        await call.answer("That round is closed.", show_alert=True)
        return
    await call.answer()
    await send_play(call.bot, call.message.chat.id, play, settings)


# ---------------------------------------------------------------- roulette slip
@router.message(BetFlow.roulette)
async def msg_roulette(message: Message, state: FSMContext, settings: Settings, engine: BetEngine) -> None:
    text = (message.text or "").strip()
    key = _user_key(message)
    slip = _slip.get(key)
    if slip is None:
        await state.clear()
        return
    if text.lower() in ("spin", "/spin"):
        await _spin(message, key, engine, settings, state)
        return
    if text.lower() == "clear":
        slip["bets"] = []
        await message.answer(_slip_text(slip))
        return
    parsed = _parse_roulette_text(text)
    if parsed is None:
        await message.answer(
            "Send e.g. <code>red 100</code>, <code>straight 17 100</code>, "
            "<code>split 1-2 50</code>, <code>street 1-3 50</code>, "
            "<code>corner 1-2-4-5 50</code>, <code>line 1-6 50</code> — or press Spin."
        )
        return
    slip["bets"].append(parsed)
    await message.answer(_slip_text(slip))


def _slip_text(slip: dict) -> str:
    total = sum(b["amount"] for b in slip["bets"])
    lines = ["🎡 <b>Bet slip</b>", f"Total: <b>{en.money(total)}</b>", ""]
    lines.extend(f"• {b['type']} {b['sel']} — {en.money(b['amount'])}" for b in slip["bets"])
    lines.append("\nPress Spin or type more bets.")
    return "\n".join(lines)


def _parse_roulette_text(text: str) -> dict | None:
    parts = text.split()
    if len(parts) < 2:
        return None
    kind_raw = parts[0].lower()
    aliases = {
        "red": ("color", "red"),
        "black": ("color", "black"),
        "odd": ("parity", "odd"),
        "even": ("parity", "even"),
        "low": ("half", "low"),
        "high": ("half", "high"),
        "green": ("straight", [0]),
        "zero": ("straight", [0]),
    }
    try:
        if kind_raw in aliases:
            kind, sel = aliases[kind_raw]
            amount = int(round(float(parts[1].replace(",", "")) * 100))
            return {"type": kind, "sel": sel, "amount": amount} if amount > 0 else None
        if kind_raw in ("dozen", "column"):
            dozen = int(parts[1])
            if dozen not in (1, 2, 3):
                return None
            amount = int(round(float(parts[2].replace(",", "")) * 100))
            return {"type": kind_raw, "sel": str(dozen), "amount": amount} if amount > 0 else None
        if kind_raw == "straight":
            number = int(parts[1])
            if not 0 <= number <= 36:
                return None
            amount = int(round(float(parts[2].replace(",", "")) * 100))
            return {"type": "straight", "sel": [number], "amount": amount} if amount > 0 else None
        if kind_raw in ("split", "street", "corner", "line"):
            numbers = [int(n) for n in re.split(r"[-,]", parts[1])]
            amount = int(round(float(parts[2].replace(",", "")) * 100))
            return {"type": kind_raw, "sel": sorted(set(numbers)), "amount": amount} if amount > 0 else None
    except (IndexError, ValueError):
        return None
    return None


async def _add_slip_bet(call: CallbackQuery, kind: str, sel) -> None:
    key = _user_key(call)
    slip = _slip.get(key)
    if slip is None:
        await call.answer("Open a bet slip first with /play roulette <bet>.", show_alert=True)
        return
    slip["bets"].append({"type": kind, "sel": sel, "amount": slip["stake"]})
    await call.answer(f"Added {kind} {sel}")
    with contextlib.suppress(Exception):
        await call.message.edit_text(_slip_text(slip), reply_markup=_roulette_keyboard())


@router.callback_query(F.data.startswith("rs:"))
async def cb_slip_add(call: CallbackQuery) -> None:
    _, kind, sel = call.data.split(":", 2)
    await _add_slip_bet(call, kind, sel)


@router.callback_query(F.data.startswith("rn:"))
async def cb_slip_number(call: CallbackQuery) -> None:
    number = int(call.data.split(":", 1)[1])
    await _add_slip_bet(call, "straight", [number])


@router.callback_query(F.data == "rclear")
async def cb_slip_clear(call: CallbackQuery) -> None:
    slip = _slip.get(_user_key(call))
    if slip:
        slip["bets"] = []
        with contextlib.suppress(Exception):
            await call.message.edit_text(_slip_text(slip), reply_markup=_roulette_keyboard())
    await call.answer("Cleared")


@router.callback_query(F.data == "rspin")
async def cb_slip_spin(call: CallbackQuery, engine: BetEngine, settings: Settings, state: FSMContext) -> None:
    key = _user_key(call)
    slip = _slip.get(key)
    if not slip or not slip["bets"]:
        await call.answer("Add at least one bet.", show_alert=True)
        return
    total = sum(b["amount"] for b in slip["bets"])
    try:
        play = await engine.place(
            call.from_user.id,
            "roulette",
            total,
            {"bets": slip["bets"]},
            chat_id=call.message.chat.id,
        )
    except (GameError, InsufficientFunds, BettingClosed, RateLimited) as exc:
        await call.answer(str(exc)[:180], show_alert=True)
        return
    _slip.pop(key, None)
    await state.clear()
    await call.answer()
    await send_play(call.bot, call.message.chat.id, play, settings)


async def add_roulette_bet(message: Message, user_id: int, raw: str) -> None:
    key = _user_key(message)
    slip = _slip.get(key)
    if slip is None:
        await message.answer("Open a slip first: /play roulette <bet>")
        return
    parsed = _parse_roulette_text(raw)
    if parsed is None:
        await message.answer("Could not read that bet. Try: red 100 / split 1-2 50 / straight 17 100")
        return
    slip["bets"].append(parsed)
    await message.answer(_slip_text(slip))


async def _spin(message: Message, key, engine: BetEngine, settings: Settings, state: FSMContext) -> None:
    slip = _slip.get(key)
    if not slip or not slip["bets"]:
        await message.answer("Add at least one bet first.")
        return
    total = sum(b["amount"] for b in slip["bets"])
    try:
        play = await engine.place(
            message.from_user.id, "roulette", total, {"bets": slip["bets"]}, chat_id=message.chat.id
        )
    except (GameError, InsufficientFunds, BettingClosed, RateLimited) as exc:
        await message.answer(f"❌ {exc}")
        return
    _slip.pop(key, None)
    await state.clear()
    await send_play(message.bot, message.chat.id, play, settings)
