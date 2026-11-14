from __future__ import annotations

import html
from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.core import fairness
from bot.db import repo
from bot.db.models import utcnow
from bot.games import CATEGORIES, all_games, get_game
from bot.handlers.ui import games_keyboard, menu_keyboard, parse_amount
from bot.texts import en

router = Router(name="user")


def display_name(user) -> str:
    if user is None:
        return "unknown"
    if user.username:
        return f"@{user.username}"
    return html.escape(user.first_name or str(user.telegram_id))


async def _menu_text(user_row) -> str:
    return en.MENU_TITLE.format(brand=en.BRAND, balance=en.money(user_row.balance))


@router.message(CommandStart())
async def cmd_start(message: Message, user_row) -> None:
    text = en.WELCOME.format(
        brand=en.BRAND,
        name=html.escape(message.from_user.first_name or "player"),
        edge="1",
        disclaimer=en.DISCLAIMER,
    )
    await message.answer(text, reply_markup=menu_keyboard())


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, user_row) -> None:
    text = await _menu_text(user_row)
    try:
        await call.message.edit_text(text, reply_markup=menu_keyboard())
    except Exception:
        await call.message.answer(text, reply_markup=menu_keyboard())
    await call.answer()


@router.callback_query(F.data == "games")
async def cb_games(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "🎰 <b>Choose a category</b>\n\nPick a game and I'll ask for your bet.",
        reply_markup=menu_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery) -> None:
    category = call.data.split(":", 1)[1]
    labels = dict(CATEGORIES)
    await call.message.edit_text(
        f"<b>{labels.get(category, category)}</b>\n\nChoose a game:",
        reply_markup=games_keyboard(category),
    )
    await call.answer()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        en.HELP.format(brand=en.BRAND, disclaimer=en.DISCLAIMER),
        reply_markup=menu_keyboard(),
    )


@router.message(Command("balance"))
async def cmd_balance(message: Message, user_row) -> None:
    await message.answer(f"🪙 Balance: <b>{en.money(user_row.balance)}</b>")


@router.message(Command("games"))
async def cmd_games(message: Message) -> None:
    names = "\n".join(f"{g.emoji} <code>{g.key}</code> — {g.name}" for g in all_games())
    await message.answer(
        f"<b>🎮 All games</b>\n\n{names}\n\nPlay with <code>/play &lt;game&gt; &lt;bet&gt;</code>.",
        reply_markup=menu_keyboard(),
    )


@router.message(Command("rules"))
async def cmd_rules(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /rules <game>")
        return
    game = get_game(args[1].strip().lower())
    if game is None:
        await message.answer("Unknown game.")
        return
    await message.answer(
        en.RULES.format(
            name=game.name,
            emoji=game.emoji,
            rules=game.rules_text,
            edge=f"{game.edge * 100:g}",
            rtp=f"{game.theoretical_rtp() * 100:.2f}",
        )
    )


@router.callback_query(F.data.startswith("rules:"))
async def cb_rules(call: CallbackQuery) -> None:
    key = call.data.split(":", 1)[1]
    game = get_game(key)
    if game is None:
        await call.answer("Unknown game.", show_alert=True)
        return
    await call.message.answer(
        en.RULES.format(
            name=game.name,
            emoji=game.emoji,
            rules=game.rules_text,
            edge=f"{game.edge * 100:g}",
            rtp=f"{game.theoretical_rtp() * 100:.2f}",
        )
    )
    await call.answer()


@router.message(Command("history"))
async def cmd_history(message: Message, session_factory) -> None:
    await _send_history(message, 0, session_factory)


@router.callback_query(F.data.startswith("hist:"))
async def cb_history(call: CallbackQuery, session_factory) -> None:
    if not isinstance(call.message, Message):
        await call.answer()
        return
    page = int(call.data.split(":", 1)[1])
    await _send_history(call.message, page, session_factory, user_id=call.from_user.id, edit=True)
    await call.answer()


async def _send_history(message: Message, page: int, session_factory, user_id: int | None = None, edit: bool = False) -> None:
    uid = user_id or message.from_user.id
    async with session_factory() as session:
        bets = await repo.user_bets(session, uid, limit=10, offset=page * 10)
    lines = [en.HISTORY_HEADER, ""]
    for bet in bets:
        mark = {"WON": "🟢", "LOST": "🔴", "CASHED_OUT": "💰", "REFUNDED": "↩️", "ACTIVE": "⏳"}.get(bet.status, "•")
        lines.append(
            f"{mark} <code>#{bet.id}</code> {bet.game} · {en.money(bet.amount)} → "
            f"{bet.multiplier:.2f}x · {en.money(bet.payout)}"
        )
    if not bets:
        lines.append("No bets yet — pick a game from the menu.")
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Newer", callback_data=f"hist:{page - 1}"))
    if len(bets) == 10:
        nav.append(InlineKeyboardButton(text="Older ➡️", callback_data=f"hist:{page + 1}"))
    if nav:
        rows.append(nav)
    markup = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=markup)


@router.message(Command("stats"))
async def cmd_stats(message: Message, session_factory) -> None:
    async with session_factory() as session:
        stats = await repo.stats_for_user(session, message.from_user.id)
    favourite = get_game(stats["favourite"]).name if stats["favourite"] and get_game(stats["favourite"]) else "—"
    await message.answer(
        en.STATS.format(
            balance=en.money(stats["balance"]),
            wagered=en.money(stats["wagered"]),
            won=en.money(stats["won"]),
            games=f"{stats['games']:,}",
            biggest=en.money(stats["biggest_win"]),
            favourite=favourite,
        )
    )


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message, session_factory) -> None:
    if message.chat.type != "private":
        from bot.handlers.group import cmd_groupstats

        await cmd_groupstats(message, session_factory)
        return
    args = message.text.split(maxsplit=1)
    period = args[1].strip().lower() if len(args) > 1 else "all"
    await _send_leaderboard(message, period, message, session_factory)


@router.callback_query(F.data.startswith("lb:"))
async def cb_leaderboard(call: CallbackQuery, session_factory) -> None:
    if not isinstance(call.message, Message):
        await call.answer()
        return
    period = call.data.split(":", 1)[1]
    await _send_leaderboard(call.message, period, call.message, session_factory, edit=True, user_id=call.from_user.id)
    await call.answer()


async def _send_leaderboard(message: Message, period: str, origin: Message, session_factory, edit: bool = False, user_id: int | None = None) -> None:
    if period not in ("daily", "weekly", "all"):
        period = "all"
    async with session_factory() as session:
        balance_rows = await repo.leaderboard_balance(session, 5)
        wagered = await repo.leaderboard_wagered(session, period, 5)
        multipliers = await repo.leaderboard_multiplier(session, period, 5)
    inline = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Today", callback_data="lb:daily"),
                InlineKeyboardButton(text="Week", callback_data="lb:weekly"),
                InlineKeyboardButton(text="All time", callback_data="lb:all"),
            ]
        ]
    )
    lines = [f"<b>🏆 Leaderboard · {period}</b>", "", "<b>💰 Balances</b>"]
    for i, user in enumerate(balance_rows, 1):
        lines.append(f"{i}. {display_name(user)} — {en.money(user.balance)}")
    lines.append("\n<b>🎯 Total wagered</b>")
    for i, (uid, amount) in enumerate(wagered, 1):
        lines.append(f"{i}. <code>{uid}</code> — {en.money(amount)}")
    lines.append("\n<b>🔥 Biggest multiplier</b>")
    for i, (uid, mult) in enumerate(multipliers, 1):
        lines.append(f"{i}. <code>{uid}</code> — {en.fmtx(mult)}")
    text = "\n".join(lines)
    if edit:
        try:
            await origin.edit_text(text, reply_markup=inline)
            return
        except Exception:
            pass
    await origin.answer(text, reply_markup=inline)


@router.message(Command("fairness"))
async def cmd_fairness(message: Message, session_factory) -> None:
    async with session_factory() as session:
        seed = await fairness.get_active_seed(session, message.from_user.id)
        await session.commit()
    await message.answer(
        en.FAIRNESS.format(hash=seed.server_seed_hash, client=html.escape(seed.client_seed), nonce=seed.nonce)
    )


@router.message(Command("setseed"))
async def cmd_setseed(message: Message, session_factory) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("Usage: /setseed <any text>")
        return
    client_seed = "".join(ch for ch in args[1].strip() if ch.isprintable())[:128]
    async with session_factory() as session:
        seed = await fairness.set_client_seed(session, message.from_user.id, client_seed)
        await session.commit()
    await message.answer(f"✅ Client seed set to <code>{html.escape(seed.client_seed)}</code>.")


@router.message(Command("rotateseed"))
async def cmd_rotateseed(message: Message, session_factory) -> None:
    async with session_factory() as session:
        old, fresh = await fairness.rotate_seed(session, message.from_user.id)
        await session.commit()
    await message.answer(
        "🔄 <b>Seed rotated</b>\n\n"
        f"Old server seed (now revealed):\n<code>{old.server_seed}</code>\n"
        f"Old hash: <code>{old.server_seed_hash}</code>\n\n"
        f"New server seed hash:\n<code>{fresh.server_seed_hash}</code>\n\n"
        "Use /verify on any old bet to check it."
    )


@router.message(Command("verify"))
async def cmd_verify(message: Message, engine) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Usage: /verify <bet_id>")
        return
    info = await engine.verify(int(args[1]))
    if not info.get("ok"):
        await message.answer("❌ Bet not found.")
        return
    bet = info["bet"]
    lines = [
        f"🔐 <b>Bet #{bet.id}</b> · {bet.game}",
        f"Server seed hash: <code>{info['hash']}</code>",
        f"Client seed: <code>{html.escape(bet.client_seed)}</code> · nonce {bet.nonce}",
        f"Recorded values: {info['proof_len']} · outcome {bet.multiplier:.2f}x · {bet.status}",
    ]
    if info["revealed"]:
        lines.append(f"Server seed (revealed): <code>{info['server_seed']}</code>")
        lines.append("✅ HMAC stream reproduces the stored values." if info["matches"] else "❌ Mismatch! Contact the owner.")
    else:
        lines.append("⏳ Seed still secret — rotate it to reveal and fully verify.")
    await message.answer("\n".join(lines))


@router.message(Command("limit"))
async def cmd_limit(message: Message, session_factory, settings) -> None:
    args = message.text.split()
    if len(args) != 3 or args[1].lower() != "daily":
        await message.answer("Usage: /limit daily <chips>  (0 removes the cap)")
        return
    try:
        chips = float(args[2].replace(",", ""))
    except ValueError:
        await message.answer("Send a number of Chips.")
        return
    if chips < 0:
        await message.answer("The limit cannot be negative.")
        return
    limit = int(chips * 100)
    async with session_factory() as session:
        user = await repo.get_user(session, message.from_user.id)
        if user:
            user.daily_limit = limit or None
            user.daily_wagered = 0
            user.daily_reset_at = utcnow()
            await session.commit()
    await message.answer(
        f"🛡 Daily limit set to <b>{en.money(limit)}</b>." if limit else "🛡 Daily limit removed."
    )


@router.message(Command("pause"))
async def cmd_pause(message: Message, session_factory) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /pause <hours>  (e.g. /pause 24)")
        return
    raw = args[1].strip().lower().rstrip("h")
    try:
        hours = float(raw)
    except ValueError:
        await message.answer("Send a number of hours.")
        return
    if not 0 < hours <= 24 * 30:
        await message.answer("Pause for 1–720 hours.")
        return
    until = utcnow() + timedelta(hours=hours)
    async with session_factory() as session:
        user = await repo.get_user(session, message.from_user.id)
        if user:
            user.paused_until = until
            await session.commit()
    await message.answer(f"⏸ Play paused until <b>{until:%Y-%m-%d %H:%M} UTC</b>. Take care.")


@router.message(Command("resume"))
async def cmd_resume(message: Message, session_factory) -> None:
    async with session_factory() as session:
        bets = await repo.active_bets(session, message.from_user.id)
    if not bets:
        await message.answer("No unfinished rounds.")
        return
    rows = [
        [
            InlineKeyboardButton(
                text=f"{get_game(b.game).emoji if get_game(b.game) else '🎮'} #{b.id} {b.game} · {en.money(b.amount)}",
                callback_data=f"resume:{b.id}",
            )
        ]
        for b in bets
    ]
    await message.answer(
        "⏳ <b>Unfinished rounds</b>\n\nTap one to reopen it. Rounds auto-cash-out after the timeout.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(Command("play"))
async def cmd_play(message: Message, user_row, settings, state: FSMContext) -> None:
    from bot.handlers.play import begin_game

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Usage: /play <game> <bet>  — e.g. /play dice 100")
        return
    game_key = args[1].lower()
    game = get_game(game_key)
    if game is None:
        await message.answer("Unknown game. Try /games.")
        return
    try:
        cents = parse_amount(args[2], user_row.balance, settings)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    if cents < settings.min_bet:
        await message.answer(f"Minimum bet is {en.money(settings.min_bet)}.")
        return
    await begin_game(message, message.from_user.id, game_key, cents, state, settings)


@router.message(Command("bet"))
async def cmd_bet_roulette(message: Message) -> None:
    from bot.handlers.play import add_roulette_bet

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /bet red 100 · /bet split 1-2 50 · /bet straight 17 100")
        return
    await add_roulette_bet(message, message.from_user.id, args[1])
