from __future__ import annotations

import asyncio
import contextlib
import hashlib
import secrets
import time
from dataclasses import dataclass, field

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from bot.config import Settings
from bot.core.bet_engine import BetEngine
from bot.core.errors import BettingClosed, ChipCityError, GameError, InsufficientFunds, RateLimited
from bot.core.fairness import FairRNG, new_server_seed
from bot.db.models import Bet, User
from bot.games.crash import crash_point, score_at
from bot.games.slide import strip as slide_strip
from bot.games.slide import targets as slide_targets
from bot.handlers.ui import parse_amount
from bot.texts import en

router = Router(name="group")

JOIN_SECONDS = 10
ROUNDS: dict[int, GroupRound] = {}
CHALLENGES: dict[str, dict] = {}
TASKS: set[asyncio.Task] = set()


@dataclass
class Player:
    user_id: int
    bet_id: int
    target: float
    name: str


@dataclass
class GroupRound:
    rid: str
    chat_id: int
    game: str
    stake: int
    message_id: int | None = None
    players: dict[int, Player] = field(default_factory=dict)
    seed: str = ""
    closed: bool = False
    task: asyncio.Task | None = None


def _track(task: asyncio.Task) -> None:
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)


def _round_by_id(rid: str) -> GroupRound | None:
    for group_round in ROUNDS.values():
        if group_round.rid == rid:
            return group_round
    return None


def _lobby_text(group_round: GroupRound) -> str:
    kind = "Crash" if group_round.game == "crash" else "Slide"
    icon = "🚀" if group_round.game == "crash" else "🎚️"
    lines = [
        f"{icon} <b>Group {kind}</b> · {group_round.rid}",
        f"Stake: <b>{en.money(group_round.stake)}</b> · joining closes in {JOIN_SECONDS}s",
        "",
        "<b>Players</b>",
    ]
    if group_round.players:
        for player in group_round.players.values():
            lines.append(f"• {player.name} — target {player.target:.2f}x")
    else:
        lines.append("No players yet — be the first.")
    lines.append("\nPick an auto target to join:")
    return "\n".join(lines)


def _lobby_keyboard(group_round: GroupRound) -> InlineKeyboardMarkup:
    targets: tuple[float, ...]
    if group_round.game == "crash":
        targets = (1.5, 2.0, 3.0, 5.0, 10.0)
        prefix = "gc"
    else:
        targets = slide_targets()
        prefix = "gs"
    rows = []
    row = []
    for target in targets:
        row.append(
            InlineKeyboardButton(
                text=f"{target:.2f}x",
                callback_data=f"{prefix}:{group_round.rid}:{int(round(target * 100))}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit(bot: Bot, chat_id: int, message_id: int | None, text: str, markup=None) -> None:
    if message_id is None:
        return
    with contextlib.suppress(Exception):
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)


@router.message(Command("crash"))
async def cmd_group_crash(message: Message, user_row, settings: Settings, engine: BetEngine) -> None:
    if message.chat.type == "private":
        await message.answer("Use <code>/play crash &lt;bet&gt;</code> in DM, or /crash in a group.")
        return
    if message.chat.id in ROUNDS:
        await message.answer("🚀 A round is already running in this chat.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /crash <bet>")
        return
    try:
        stake = parse_amount(args[1], user_row.balance, settings)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    if stake < settings.min_bet:
        await message.answer(f"Minimum bet is {en.money(settings.min_bet)}.")
        return
    group_round = GroupRound(
        rid=secrets.token_hex(3),
        chat_id=message.chat.id,
        game="crash",
        stake=stake,
        seed=new_server_seed(),
    )
    ROUNDS[message.chat.id] = group_round
    sent = await message.answer(_lobby_text(group_round), reply_markup=_lobby_keyboard(group_round))
    group_round.message_id = sent.message_id
    if message.bot is None:
        return
    group_round.task = asyncio.create_task(_run_crash(message.bot, group_round, engine))
    _track(group_round.task)


@router.message(Command("slide"))
async def cmd_group_slide(message: Message, user_row, settings: Settings, engine: BetEngine) -> None:
    if message.chat.type == "private":
        await message.answer("Use <code>/play slide &lt;bet&gt;</code> in DM, or /slide in a group.")
        return
    if message.chat.id in ROUNDS:
        await message.answer("🎚️ A round is already running in this chat.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /slide <bet>")
        return
    try:
        stake = parse_amount(args[1], user_row.balance, settings)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    if stake < settings.min_bet:
        await message.answer(f"Minimum bet is {en.money(settings.min_bet)}.")
        return
    group_round = GroupRound(
        rid=secrets.token_hex(3),
        chat_id=message.chat.id,
        game="slide",
        stake=stake,
        seed=new_server_seed(),
    )
    ROUNDS[message.chat.id] = group_round
    sent = await message.answer(_lobby_text(group_round), reply_markup=_lobby_keyboard(group_round))
    group_round.message_id = sent.message_id
    if message.bot is None:
        return
    group_round.task = asyncio.create_task(_run_slide(message.bot, group_round, engine))
    _track(group_round.task)


async def _join(
    call: CallbackQuery,
    engine: BetEngine,
    group_round: GroupRound | None,
    target: float,
) -> None:
    if group_round is None or group_round.closed:
        await call.answer("Joining is closed.", show_alert=True)
        return
    if call.message.chat.id != group_round.chat_id:
        await call.answer("Wrong chat.", show_alert=True)
        return
    if call.from_user.id in group_round.players:
        await call.answer("You already joined this round.", show_alert=True)
        return
    try:
        bet = await engine.open_bet(
            call.from_user.id,
            group_round.game,
            group_round.stake,
            {"target": f"{target:g}"},
            chat_id=group_round.chat_id,
            text=f"Group {group_round.game} target {target:.2f}x",
        )
    except InsufficientFunds:
        await call.answer(en.INSUFFICIENT, show_alert=True)
        return
    except (GameError, BettingClosed, RateLimited) as exc:
        await call.answer(str(exc)[:180], show_alert=True)
        return
    name = call.from_user.first_name or str(call.from_user.id)
    group_round.players[call.from_user.id] = Player(call.from_user.id, bet.id, target, name)
    await call.answer(f"Joined at {target:.2f}x")
    if call.bot is None:
        return
    await _edit(
        call.bot,
        group_round.chat_id,
        group_round.message_id,
        _lobby_text(group_round),
        _lobby_keyboard(group_round),
    )


@router.callback_query(F.data.startswith("gc:"))
async def cb_join_crash(call: CallbackQuery, engine: BetEngine) -> None:
    _, rid, bp = call.data.split(":", 2)
    await _join(call, engine, _round_by_id(rid), int(bp) / 100)


@router.callback_query(F.data.startswith("gs:"))
async def cb_join_slide(call: CallbackQuery, engine: BetEngine) -> None:
    _, rid, bp = call.data.split(":", 2)
    await _join(call, engine, _round_by_id(rid), int(bp) / 100)


async def _run_crash(bot: Bot, group_round: GroupRound, engine: BetEngine) -> None:
    try:
        await asyncio.sleep(JOIN_SECONDS)
        group_round.closed = True
        if not group_round.players:
            await _edit(bot, group_round.chat_id, group_round.message_id, "🚀 No players joined — round cancelled.")
            return
        rng = FairRNG(group_round.seed, f"crash:{group_round.rid}", 0)
        crash = crash_point(rng)
        commit = hashlib.sha256(bytes.fromhex(group_round.seed)).hexdigest()[:16]
        started = time.time()
        while score_at(time.time() - started) < crash:
            current = score_at(time.time() - started)
            await _edit(
                bot,
                group_round.chat_id,
                group_round.message_id,
                f"🚀 <b>Crash is live</b> · commit <code>{commit}</code>\n\n"
                f"Current multiplier: <b>{current:.2f}x</b>\n"
                + "\n".join(f"• {p.name} → {p.target:.2f}x" for p in group_round.players.values()),
            )
            await asyncio.sleep(2)
        lines = [f"💥 <b>Crashed at {crash:.2f}x</b>", ""]
        for player in group_round.players.values():
            won = player.target <= crash
            multiplier = player.target if won else 0.0
            await engine.settle_manual(
                player.bet_id,
                multiplier,
                "CASHED_OUT" if won else "LOST",
                text=f"Group crash: target {player.target:.2f}x, crash {crash:.2f}x",
                detail={"crash": crash, "target": player.target},
            )
            lines.append(
                f"{'🟢' if won else '🔴'} {player.name} — target {player.target:.2f}x → "
                + (en.money(int(group_round.stake * multiplier)) if won else "lost")
            )
        lines.append(f"\nServer seed: <code>{group_round.seed}</code>")
        await _edit(bot, group_round.chat_id, group_round.message_id, "\n".join(lines))
    except asyncio.CancelledError:
        raise
    except Exception:
        await _edit(bot, group_round.chat_id, group_round.message_id, "⚠️ The round failed; stakes are refunded.")
        for player in group_round.players.values():
            with contextlib.suppress(Exception):
                await engine.refund(player.bet_id, "group round error")
    finally:
        ROUNDS.pop(group_round.chat_id, None)


async def _run_slide(bot: Bot, group_round: GroupRound, engine: BetEngine) -> None:
    try:
        await asyncio.sleep(JOIN_SECONDS)
        group_round.closed = True
        if not group_round.players:
            await _edit(bot, group_round.chat_id, group_round.message_id, "🎚️ No players joined — round cancelled.")
            return
        values = slide_strip()
        rng = FairRNG(group_round.seed, f"slide:{group_round.rid}", 0)
        index = rng.int(len(values))
        landed = values[index]
        lines = [f"🎚️ <b>Slide stopped at {landed:.2f}x</b> (step {index + 1}/{len(values)})", ""]
        for player in group_round.players.values():
            won = landed >= player.target
            multiplier = player.target if won else 0.0
            await engine.settle_manual(
                player.bet_id,
                multiplier,
                "CASHED_OUT" if won else "LOST",
                text=f"Group slide: target {player.target:.2f}x, landed {landed:.2f}x",
                detail={"landed": landed, "target": player.target},
            )
            lines.append(
                f"{'🟢' if won else '🔴'} {player.name} — target {player.target:.2f}x → "
                + (en.money(int(group_round.stake * multiplier)) if won else "below target")
            )
        lines.append(f"\nServer seed: <code>{group_round.seed}</code>")
        await _edit(bot, group_round.chat_id, group_round.message_id, "\n".join(lines))
    except asyncio.CancelledError:
        raise
    except Exception:
        await _edit(bot, group_round.chat_id, group_round.message_id, "⚠️ The round failed; stakes are refunded.")
        for player in group_round.players.values():
            with contextlib.suppress(Exception):
                await engine.refund(player.bet_id, "group round error")
    finally:
        ROUNDS.pop(group_round.chat_id, None)


@router.message(Command("duel"))
async def cmd_duel(message: Message, user_row, settings: Settings) -> None:
    if message.chat.type == "private":
        await message.answer("⚔️ Dice Duel is a group game — use /duel in a group chat.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /duel <bet>")
        return
    try:
        stake = parse_amount(args[1], user_row.balance, settings)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    if stake < settings.min_bet:
        await message.answer(f"Minimum bet is {en.money(settings.min_bet)}.")
        return
    rid = secrets.token_hex(3)
    challenge = {
        "id": rid,
        "chat_id": message.chat.id,
        "challenger": message.from_user.id,
        "name": message.from_user.first_name or str(message.from_user.id),
        "stake": stake,
        "message_id": None,
        "settled": False,
    }
    CHALLENGES[rid] = challenge
    sent = await message.answer(
        f"⚔️ <b>Dice Duel</b> · {en.money(stake)} each\n"
        f"{challenge['name']} challenges the chat.\n\n"
        "Higher fair roll wins the pot (winner gets 1.98× their stake, 1% burned). Ties refund. "
        "Expires in 2 minutes.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⚔️ Accept", callback_data=f"gd:{rid}")]]
        ),
    )
    challenge["message_id"] = sent.message_id
    if message.bot is None:
        return
    _track(asyncio.create_task(_expire_duel(message.bot, rid, 120)))


async def _expire_duel(bot: Bot, rid: str, seconds: int) -> None:
    await asyncio.sleep(seconds)
    challenge = CHALLENGES.pop(rid, None)
    if challenge and not challenge["settled"]:
        with contextlib.suppress(Exception):
            await bot.edit_message_text(
                "⌛ Dice Duel expired.",
                chat_id=challenge["chat_id"],
                message_id=challenge["message_id"],
            )


@router.callback_query(F.data.startswith("gd:"))
async def cb_accept_duel(call: CallbackQuery, engine: BetEngine) -> None:
    rid = call.data.split(":", 1)[1]
    challenge = CHALLENGES.get(rid)
    if challenge is None or challenge["settled"]:
        await call.answer("This duel is no longer open.", show_alert=True)
        return
    if call.from_user.id == challenge["challenger"]:
        await call.answer("You cannot accept your own duel.", show_alert=True)
        return
    challenge["settled"] = True
    CHALLENGES.pop(rid, None)
    challenger = challenge["challenger"]
    acceptor = call.from_user.id
    stake = challenge["stake"]
    first = second = None
    try:
        first = await engine.open_bet(
            challenger, "duel", stake, {"opponent": str(acceptor)}, chat_id=challenge["chat_id"]
        )
        second = await engine.open_bet(
            acceptor, "duel", stake, {"opponent": str(challenger)}, chat_id=challenge["chat_id"]
        )
    except ChipCityError as exc:
        if first is not None:
            await engine.refund(first.id, "duel aborted")
        await call.answer(f"Duel cancelled: {exc}", show_alert=True)
        return
    seed = new_server_seed()
    rng = FairRNG(seed, f"duel:{rid}", 0)
    roll_a = rng.int(100) + 1
    roll_b = rng.int(100) + 1
    name_a = challenge["name"]
    name_b = call.from_user.first_name or str(acceptor)
    if roll_a == roll_b:
        await engine.settle_manual(first.id, 1.0, "CASHED_OUT", text="Duel tie — refund")
        await engine.settle_manual(second.id, 1.0, "CASHED_OUT", text="Duel tie — refund")
        result = "🤝 Tie — both stakes refunded."
    elif roll_a > roll_b:
        await engine.settle_manual(first.id, 1.98, "WON", text="Duel win")
        await engine.settle_manual(second.id, 0.0, "LOST", text="Duel loss")
        result = f"🏆 <b>{name_a}</b> wins {en.money(int(stake * 0.98))} profit."
    else:
        await engine.settle_manual(first.id, 0.0, "LOST", text="Duel loss")
        await engine.settle_manual(second.id, 1.98, "WON", text="Duel win")
        result = f"🏆 <b>{name_b}</b> wins {en.money(int(stake * 0.98))} profit."
    with contextlib.suppress(Exception):
        await call.bot.edit_message_text(
            f"⚔️ <b>Dice Duel</b>\n\n"
            f"{name_a}: 🎲 <b>{roll_a}</b>\n{name_b}: 🎲 <b>{roll_b}</b>\n\n"
            f"{result}\n\nSeed: <code>{seed}</code>",
            chat_id=challenge["chat_id"],
            message_id=challenge["message_id"],
        )
    await call.answer()


@router.message(Command("groupstats"))
async def cmd_groupstats(message: Message, session_factory) -> None:
    if message.chat.type == "private":
        await message.answer("Use /leaderboard in DM for global stats.")
        return
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Bet.user_id, func.sum(Bet.amount), func.count(Bet.id))
                .where(Bet.chat_id == message.chat.id)
                .group_by(Bet.user_id)
                .order_by(func.sum(Bet.amount).desc())
                .limit(10)
            )
        ).all()
        names = {}
        user_ids = [row[0] for row in rows]
        if user_ids:
            users = (await session.execute(select(User).where(User.telegram_id.in_(user_ids)))).scalars().all()
            names = {u.telegram_id: u for u in users}
    lines = ["<b>🏆 This chat's leaderboard</b>", ""]
    for i, (uid, wagered, count) in enumerate(rows, 1):
        user = names.get(uid)
        label = en.money(int(wagered or 0))
        name = f"@{user.username}" if user and user.username else str(uid)
        lines.append(f"{i}. {name} — {label} · {count} bets")
    if not rows:
        lines.append("No bets in this chat yet.")
    await message.answer("\n".join(lines))


async def shutdown_rounds(engine: BetEngine) -> None:
    for task in list(TASKS):
        task.cancel()
    for group_round in list(ROUNDS.values()):
        for player in group_round.players.values():
            with contextlib.suppress(Exception):
                await engine.refund(player.bet_id, "shutdown")
    ROUNDS.clear()
