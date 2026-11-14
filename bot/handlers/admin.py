from __future__ import annotations

import contextlib
import csv
import html
import io
import secrets
import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select

from bot.config import Settings
from bot.core import wallet as wallet_mod
from bot.core.bet_engine import BetEngine
from bot.core.errors import ChipCityError
from bot.db import repo
from bot.db.models import Bet, GameSetting, Ledger, User
from bot.games import get_game
from bot.texts import en

router = Router(name="admin")

PENDING: dict[str, dict] = {}


def _is_owner(message_or_call, settings: Settings) -> bool:
    return (message_or_call.from_user.id if message_or_call.from_user else 0) == settings.owner_telegram_id


async def _deny(message: Message) -> None:
    await message.answer(en.UNKNOWN)


async def _target(session, token: str) -> User | None:
    token = token.strip()
    if token.startswith("@"):
        return (
            await session.execute(
                select(User).where(func.lower(User.username) == token[1:].lower())
            )
        ).scalar_one_or_none()
    if token.isdigit():
        return await session.get(User, int(token))
    return None


def _chips(raw: str) -> int:
    value = raw.lower().replace(",", "").strip()
    multiplier = 1
    if value.endswith("k"):
        multiplier = 1_000
        value = value[:-1]
    elif value.endswith("m"):
        multiplier = 1_000_000
        value = value[:-1]
    return int(round(float(value) * multiplier * 100))


async def _confirm_owner(message: Message, text: str) -> None:
    if message.chat.type == "private":
        await message.answer(text)
    else:
        with contextlib.suppress(Exception):
            await message.bot.send_message(message.chat.id, text)


@router.message(Command("addcredits"))
async def cmd_addcredits(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        await message.answer("Usage: /addcredits <@user|id> <chips> [note]")
        return
    async with session_factory() as session:
        target = await _target(session, args[1])
    if target is None:
        await message.answer("Player not found (they must /start first).")
        return
    try:
        cents = _chips(args[2])
    except ValueError:
        await message.answer("Invalid amount.")
        return
    note = args[3] if len(args) > 3 else None
    try:
        _, balance = await wallet_mod.change(
            session_factory,
            target.telegram_id,
            cents,
            wallet_mod.CREDIT,
            admin_id=message.from_user.id,
            note=note,
        )
    except ChipCityError as exc:
        await message.answer(f"❌ {exc}")
        return
    async with session_factory() as session:
        await repo.add_admin_log(
            session,
            message.from_user.id,
            "addcredits",
            target_id=target.telegram_id,
            after={"amount": cents, "balance": balance},
            note=note,
        )
        await session.commit()
    await message.answer(
        f"✅ Added <b>{en.money(cents)}</b> to <code>{target.telegram_id}</code>. New balance "
        f"<b>{en.money(balance)}</b>.",
        reply_markup=None,
    )


@router.message(Command("removecredits"))
async def cmd_removecredits(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        await message.answer("Usage: /removecredits <@user|id> <chips> [note]")
        return
    async with session_factory() as session:
        target = await _target(session, args[1])
    if target is None:
        await message.answer("Player not found.")
        return
    try:
        cents = _chips(args[2])
    except ValueError:
        await message.answer("Invalid amount.")
        return
    try:
        _, balance = await wallet_mod.change(
            session_factory,
            target.telegram_id,
            -cents,
            wallet_mod.DEBIT,
            admin_id=message.from_user.id,
            note=args[3] if len(args) > 3 else None,
        )
    except ChipCityError as exc:
        await message.answer(f"❌ {exc}")
        return
    async with session_factory() as session:
        await repo.add_admin_log(
            session,
            message.from_user.id,
            "removecredits",
            target_id=target.telegram_id,
            after={"amount": -cents, "balance": balance},
        )
        await session.commit()
    await message.answer(f"✅ Removed. New balance <b>{en.money(balance)}</b>.")


@router.message(Command("setbalance"))
async def cmd_setbalance(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Usage: /setbalance <@user|id> <chips>")
        return
    async with session_factory() as session:
        target = await _target(session, args[1])
    if target is None:
        await message.answer("Player not found.")
        return
    try:
        cents = _chips(args[2])
    except ValueError:
        await message.answer("Invalid amount.")
        return
    try:
        _, balance = await wallet_mod.change(
            session_factory,
            target.telegram_id,
            cents - target.balance,
            wallet_mod.RESET,
            admin_id=message.from_user.id,
            note="setbalance",
        )
    except ChipCityError as exc:
        await message.answer(f"❌ {exc}")
        return
    async with session_factory() as session:
        await repo.add_admin_log(
            session,
            message.from_user.id,
            "setbalance",
            target_id=target.telegram_id,
            before={"balance": target.balance},
            after={"balance": balance},
        )
        await session.commit()
    await message.answer(f"✅ Balance set to <b>{en.money(balance)}</b>.")


@router.message(Command("resetuser"))
async def cmd_resetuser(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /resetuser <@user|id>")
        return
    async with session_factory() as session:
        target = await _target(session, args[1])
    if target is None:
        await message.answer("Player not found.")
        return
    try:
        await wallet_mod.change(
            session_factory,
            target.telegram_id,
            -target.balance,
            wallet_mod.RESET,
            admin_id=message.from_user.id,
            note="resetuser",
        )
    except ChipCityError as exc:
        await message.answer(f"❌ {exc}")
        return
    async with session_factory() as session:
        await repo.add_admin_log(
            session, message.from_user.id, "resetuser", target_id=target.telegram_id
        )
        await session.commit()
    await message.answer(f"✅ <code>{target.telegram_id}</code> balance reset to 0.")


@router.message(Command("resetall"))
async def cmd_resetall(message: Message, settings: Settings) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    token = secrets.token_hex(4)
    PENDING[token] = {"action": "resetall", "chat_id": message.chat.id, "ts": time.time()}
    await message.answer(
        "⚠️ <b>Reset every player's balance to 0?</b>\nThis writes a RESET ledger row for each user.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Confirm", callback_data=f"confirm:{token}"),
                    InlineKeyboardButton(text="✖️ Cancel", callback_data=f"cancel:{token}"),
                ]
            ]
        ),
    )


@router.message(Command("ban"))
async def cmd_ban(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /ban <@user|id>")
        return
    async with session_factory() as session:
        target = await _target(session, args[1])
        if target:
            target.is_banned = True
            await repo.add_admin_log(session, message.from_user.id, "ban", target_id=target.telegram_id)
            await session.commit()
    await message.answer("🚫 Banned." if target else "Player not found.")


@router.message(Command("unban"))
async def cmd_unban(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /unban <@user|id>")
        return
    async with session_factory() as session:
        target = await _target(session, args[1])
        if target:
            target.is_banned = False
            await repo.add_admin_log(session, message.from_user.id, "unban", target_id=target.telegram_id)
            await session.commit()
    await message.answer("✅ Unbanned." if target else "Player not found.")


@router.message(Command("userinfo"))
async def cmd_userinfo(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /userinfo <@user|id>")
        return
    async with session_factory() as session:
        target = await _target(session, args[1])
        if target is None:
            await message.answer("Player not found.")
            return
        ledger = await repo.user_ledger(session, target.telegram_id, 5)
        bets = await repo.user_bets(session, target.telegram_id, 5)
        total = await wallet_mod.ledger_sum(session, target.telegram_id)
    lines = [
        f"👤 <b>{html.escape(target.first_name or '')}</b> <code>{target.telegram_id}</code>",
        f"@{target.username or '—'} · banned: {target.is_banned}",
        f"Balance: <b>{en.money(target.balance)}</b> · ledger sum: {en.money(total)}",
        f"Wagered: {en.money(target.total_wagered)} · won: {en.money(target.total_won)} · games: {target.games_played}",
        "",
        "<b>Recent ledger</b>",
    ]
    lines += [f"• {row.type} {en.money(row.amount)} → {en.money(row.balance_after)}" for row in ledger]
    lines.append("\n<b>Recent bets</b>")
    lines += [
        f"• #{b.id} {b.game} {en.money(b.amount)} → {b.multiplier:.2f}x ({b.status})" for b in bets
    ]
    await message.answer("\n".join(lines))


@router.message(Command("toggle"))
async def cmd_toggle(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=2)
    if len(args) < 3 or args[2].lower() not in ("on", "off"):
        await message.answer("Usage: /toggle <game> on|off")
        return
    game = get_game(args[1].lower())
    if game is None:
        await message.answer("Unknown game.")
        return
    async with session_factory() as session:
        setting = await session.get(GameSetting, game.key)
        if setting is None:
            setting = await repo.get_setting(
                session, game.key, min_bet=settings.min_bet, max_bet=settings.max_bet, edge=game.edge
            )
        before = setting.enabled
        setting.enabled = args[2].lower() == "on"
        await repo.add_admin_log(
            session,
            message.from_user.id,
            "toggle",
            target_id=None,
            before={"game": game.key, "enabled": before},
            after={"enabled": setting.enabled},
        )
        await session.commit()
    await message.answer(f"✅ {game.name}: {'on' if setting.enabled else 'off'}.")


@router.message(Command("setedge"))
async def cmd_setedge(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Usage: /setedge <game> <percent>  e.g. /setedge dice 1")
        return
    game = get_game(args[1].lower())
    if game is None:
        await message.answer("Unknown game.")
        return
    try:
        percent = float(args[2].replace("%", ""))
    except ValueError:
        await message.answer("Invalid percentage.")
        return
    if not 0 <= percent <= 50:
        await message.answer("Edge must be 0–50%.")
        return
    async with session_factory() as session:
        setting = await session.get(GameSetting, game.key)
        if setting is None:
            setting = await repo.get_setting(
                session, game.key, min_bet=settings.min_bet, max_bet=settings.max_bet, edge=game.edge
            )
        before = setting.house_edge
        setting.house_edge = percent / 100
        await repo.add_admin_log(
            session,
            message.from_user.id,
            "setedge",
            before={"game": game.key, "edge": before},
            after={"edge": setting.house_edge},
        )
        await session.commit()
    await message.answer(
        f"✅ {game.name} house edge set to {percent:g}%.\n"
        "<i>Payouts are rescaled at settlement. Fixed-table games (roulette, sic bo, "
        "baccarat, blackjack, video poker) keep their published casino rules.</i>"
    )


@router.message(Command("setlimits"))
async def cmd_setlimits(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split()
    if len(args) != 4:
        await message.answer("Usage: /setlimits <game> <min> <max>")
        return
    game = get_game(args[1].lower())
    if game is None:
        await message.answer("Unknown game.")
        return
    try:
        min_bet = int(round(float(args[2]) * 100))
        max_bet = int(round(float(args[3]) * 100))
    except ValueError:
        await message.answer("Invalid limits.")
        return
    if min_bet <= 0 or max_bet < min_bet:
        await message.answer("Max must be at least min, and both positive.")
        return
    async with session_factory() as session:
        setting = await session.get(GameSetting, game.key)
        if setting is None:
            setting = await repo.get_setting(
                session, game.key, min_bet=settings.min_bet, max_bet=settings.max_bet, edge=game.edge
            )
        before = {"min": setting.min_bet, "max": setting.max_bet}
        setting.min_bet = min_bet
        setting.max_bet = max_bet
        await repo.add_admin_log(
            session,
            message.from_user.id,
            "setlimits",
            before=before,
            after={"min": min_bet, "max": max_bet},
        )
        await session.commit()
    await message.answer(f"✅ {game.name} limits: {en.money(min_bet)} – {en.money(max_bet)}.")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, settings: Settings) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /broadcast <text>")
        return
    token = secrets.token_hex(4)
    PENDING[token] = {"action": "broadcast", "text": args[1], "ts": time.time()}
    await message.answer(
        f"📣 <b>Send this to every player?</b>\n\n{html.escape(args[1])}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Send", callback_data=f"confirm:{token}"),
                    InlineKeyboardButton(text="✖️ Cancel", callback_data=f"cancel:{token}"),
                ]
            ]
        ),
    )


@router.message(Command("audit"))
async def cmd_audit(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    async with session_factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        sums = dict(
            (
                await session.execute(
                    select(Ledger.user_id, func.sum(Ledger.amount)).group_by(Ledger.user_id)
                )
            ).all()
        )
    mismatches = [(u.telegram_id, u.balance, int(sums.get(u.telegram_id, 0))) for u in users if u.balance != int(sums.get(u.telegram_id, 0))]
    lines = [f"🧾 <b>Audit</b> · {len(users)} users", ""]
    if mismatches:
        lines.append(f"❌ {len(mismatches)} mismatches:")
        lines += [f"<code>{uid}</code> balance {b} vs ledger {s}" for uid, b, s in mismatches[:20]]
    else:
        lines.append("✅ Every balance equals its ledger sum.")
    await message.answer("\n".join(lines))


@router.message(Command("export"))
async def cmd_export(message: Message, settings: Settings, session_factory) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["kind", "telegram_id", "username", "balance_cents", "type", "amount_cents", "balance_after", "game", "bet_id", "note", "created_at"])
    async with session_factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        for user in users:
            writer.writerow(["user", user.telegram_id, user.username, user.balance, "", "", "", "", "", "", user.created_at])
        ledger = (await session.execute(select(Ledger).order_by(Ledger.id))).scalars().all()
        for row in ledger:
            writer.writerow([
                "ledger", row.user_id, "", "", row.type, row.amount, row.balance_after,
                row.game or "", row.bet_id or "", row.note or "", row.created_at,
            ])
    data = buffer.getvalue().encode()
    await message.bot.send_document(
        message.chat.id,
        BufferedInputFile(data, filename=f"chipcity-export-{int(time.time())}.csv"),
        caption="📤 Users + ledger export (cents).",
    )


@router.message(Command("botstats"))
async def cmd_botstats(message: Message, settings: Settings, session_factory, engine: BetEngine) -> None:
    if not _is_owner(message, settings):
        return await _deny(message)
    async with session_factory() as session:
        users = (await session.execute(select(func.count(User.telegram_id)))).scalar() or 0
        bets = (await session.execute(select(func.count(Bet.id)))).scalar() or 0
        per_game = await repo.per_game_stats(session)
    lines = [
        "📊 <b>Bot stats</b>",
        f"Players: <b>{users:,}</b> · bets: <b>{bets:,}</b>",
        "",
        "<b>Per game</b> (actual vs theoretical RTP)",
    ]
    for game_key, count, wagered, paid in sorted(per_game, key=lambda r: r[0]):
        game = get_game(game_key)
        actual = paid / wagered if wagered else 0
        theoretical = game.theoretical_rtp() if game else 0
        house = wagered - paid
        lines.append(
            f"{game.emoji if game else '•'} {game_key}: {count:,} bets · "
            f"RTP {actual * 100:.2f}% / {theoretical * 100:.2f}% · house {en.money(house)}"
        )
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(call: CallbackQuery) -> None:
    token = call.data.split(":", 1)[1]
    PENDING.pop(token, None)
    await call.message.edit_text("✖️ Cancelled.")
    await call.answer()


@router.callback_query(F.data.startswith("confirm:"))
async def cb_confirm(call: CallbackQuery, settings: Settings, session_factory) -> None:
    if not _is_owner(call, settings):
        await call.answer(en.UNKNOWN, show_alert=True)
        return
    token = call.data.split(":", 1)[1]
    pending = PENDING.pop(token, None)
    if pending is None:
        await call.answer("This confirmation expired.", show_alert=True)
        return
    if pending["action"] == "resetall":
        async with session_factory() as session:
            users = (await session.execute(select(User).where(User.balance != 0))).scalars().all()
        for user in users:
            try:
                await wallet_mod.change(
                    session_factory,
                    user.telegram_id,
                    -user.balance,
                    wallet_mod.RESET,
                    admin_id=call.from_user.id,
                    note="resetall",
                )
            except ChipCityError:
                continue
        async with session_factory() as session:
            await repo.add_admin_log(session, call.from_user.id, "resetall", note=f"{len(users)} users")
            await session.commit()
        await call.message.edit_text(f"✅ Reset {len(users)} balances.")
    elif pending["action"] == "broadcast":
        async with session_factory() as session:
            users = (await session.execute(select(User))).scalars().all()
        sent = failed = 0
        for user in users:
            try:
                await call.bot.send_message(user.telegram_id, pending["text"])
                sent += 1
            except Exception:
                failed += 1
        await call.message.edit_text(f"📣 Broadcast sent to {sent}, failed {failed}.")
    await call.answer()
