from __future__ import annotations

import copy
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.core import fairness, wallet
from bot.core.errors import BettingClosed, GameError, InsufficientFunds, StaleBet
from bot.core.fairness import FairRNG
from bot.core.rate_limit import MemoryRateLimiter
from bot.db import repo
from bot.db.models import Bet, Seed, User, utcnow
from bot.games.base import BaseGame, Round
from bot.games.registry import get_game

log = logging.getLogger(__name__)


@dataclass
class Play:
    bet: Bet
    round: Round
    game: BaseGame
    balance: int


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.UTC)


class BetEngine:
    # Games whose paytables are fixed by their casino rules and cannot be rescaled.
    FIXED_TABLE = {"roulette", "sicbo", "baccarat", "blackjack", "videopoker"}

    def __init__(self, settings: Settings, session_factory, limiter: MemoryRateLimiter | None = None):
        self.settings = settings
        self.sf = session_factory
        self.limiter = limiter or MemoryRateLimiter(settings.bets_per_second)

    # ------------------------------------------------------------------ helpers
    async def _setting(self, session: AsyncSession, game: BaseGame):
        return await repo.get_setting(
            session,
            game.key,
            min_bet=self.settings.min_bet,
            max_bet=self.settings.max_bet,
            edge=game.edge,
        )

    def _cap_multiplier(self, stake: int, multiplier: float) -> float:
        if stake <= 0 or multiplier <= 1:
            return max(0.0, multiplier)
        max_payout = stake + self.settings.max_profit
        return min(multiplier, max_payout / stake)

    def _edge_scale(self, game: BaseGame, setting) -> float:
        """Rescale payouts when the owner changes a game's house edge."""
        if game.key in self.FIXED_TABLE or game.edge <= 0:
            return 1.0
        target = min(0.5, max(0.0, float(setting.house_edge)))
        return (1 - target) / (1 - game.edge)

    async def _ensure_no_active(self, session: AsyncSession, user_id: int, game_key: str) -> None:
        active = (
            await session.execute(
                select(Bet.id)
                .where(Bet.user_id == user_id, Bet.game == game_key, Bet.status == "ACTIVE")
                .limit(1)
            )
        ).scalar_one_or_none()
        if active is not None:
            raise GameError(
                "You already have an open round in this game — finish it or use /resume."
            )

    def _finish(
        self,
        session: AsyncSession,
        bet: Bet,
        user: User,
        rnd: Round,
        proof: list[str] | None,
        scale: float = 1.0,
    ) -> int:
        stake = bet.amount
        multiplier = max(0.0, float(rnd.multiplier))
        if multiplier > 1.0 and scale != 1.0:
            multiplier *= scale
            rnd.text += f"\n\n<i>House-edge adjustment ×{scale:.3f}</i>"
        payout = int(stake * multiplier)
        payout = min(payout, stake + self.settings.max_profit)
        if multiplier == 0:
            payout = 0
        bet.multiplier = round(multiplier, 4)
        bet.payout = payout
        bet.profit = payout - stake
        bet.step += 1
        if payout <= 0:
            bet.status = "LOST"
        elif rnd.status == "CASHED_OUT":
            bet.status = "CASHED_OUT"
        else:
            bet.status = "WON"
        bet.settled_at = utcnow()
        result = dict(bet.result or {})
        result.update(
            {
                "detail": rnd.detail,
                "state": {},
                "screen": rnd.text,
                "proof": proof if proof is not None else result.get("proof", []),
            }
        )
        bet.result = result
        if payout:
            wallet.credit_in_session(
                session, user, payout, wallet.WIN, game=bet.game, bet_id=bet.id
            )
            user.total_won += payout
        return payout

    async def place(
        self,
        user_id: int,
        game_key: str,
        stake: int,
        raw_params: dict[str, str] | None = None,
        *,
        chat_id: int | None = None,
    ) -> Play:
        game = get_game(game_key)
        if game is None:
            raise GameError("Unknown game.")
        stake = int(stake)
        if stake <= 0:
            raise GameError("Your bet must be a positive number of Chips.")
        self.limiter.check(user_id)
        params = game.validate(dict(raw_params or {}))

        async with wallet.user_lock(user_id):
            async with self.sf() as session:
                async with session.begin():
                    user, _ = await repo.get_or_create_user(
                        session,
                        user_id,
                        starting_balance=self.settings.starting_balance,
                    )
                    setting = await self._setting(session, game)
                    now = utcnow()
                    if user.is_banned:
                        raise BettingClosed("banned")
                    paused = _aware(user.paused_until)
                    if paused and paused > now:
                        raise BettingClosed("paused")
                    if not setting.enabled:
                        raise BettingClosed("disabled")
                    if stake < setting.min_bet:
                        raise GameError(f"Minimum bet for {game.name} is {setting.min_bet / 100:,.0f} 🪙.")
                    if stake > setting.max_bet:
                        raise GameError(f"Maximum bet for {game.name} is {setting.max_bet / 100:,.0f} 🪙.")
                    if user.balance < stake:
                        raise InsufficientFunds("Not enough Chips.")

                    reset_at = _aware(user.daily_reset_at)
                    if reset_at is None or reset_at.date() < now.date():
                        user.daily_wagered = 0
                        user.daily_reset_at = now
                    if user.daily_limit and user.daily_wagered + stake > user.daily_limit:
                        raise BettingClosed("daily_limit")
                    await self._ensure_no_active(session, user_id, game.key)

                    seed = await fairness.get_active_seed(session, user_id)
                    nonce = seed.nonce
                    seed.nonce += 1
                    rng = FairRNG(seed.server_seed, seed.client_seed, nonce)

                    wallet.credit_in_session(
                        session, user, -stake, wallet.BET, game=game.key
                    )
                    user.total_wagered += stake
                    user.games_played += 1
                    user.daily_wagered += stake
                    user.last_active = now

                    bet = Bet(
                        user_id=user_id,
                        game=game.key,
                        amount=stake,
                        params=params,
                        result={},
                        seed_id=seed.id,
                        server_seed_hash=seed.server_seed_hash,
                        client_seed=seed.client_seed,
                        nonce=nonce,
                        status="ACTIVE",
                        chat_id=chat_id,
                    )
                    session.add(bet)
                    await session.flush()

                    try:
                        rnd = game.start(rng, params, stake)
                    except GameError:
                        raise
                    except Exception as exc:  # never leave a debited, unplayed bet
                        log.exception("game start failed", extra={"game": game.key})
                        raise GameError("Round could not start; your stake was not taken.") from exc

                    proof = list(rng.proof)
                    rnd.multiplier = self._cap_multiplier(stake, rnd.multiplier)
                    if rnd.finished:
                        self._finish(session, bet, user, rnd, proof, self._edge_scale(game, setting))
                    else:
                        bet.step = 0
                        bet.result = {
                            "state": rnd.state,
                            "proof": proof,
                            "cursor": rng.cursor,
                            "screen": rnd.text,
                            "detail": rnd.detail,
                        }
                    await session.flush()
                    balance = user.balance

        return Play(bet=bet, round=rnd, game=game, balance=balance)

    async def step(
        self,
        user_id: int,
        bet_id: int,
        step_no: int,
        action: str,
        arg: str = "",
        *,
        chat_id: int | None = None,
    ) -> Play:
        async with self.sf() as probe:
            existing = await probe.get(Bet, bet_id)
            if existing is None:
                raise StaleBet("missing")
            owner = existing.user_id
            game = get_game(existing.game)
        if game is None:
            raise StaleBet("unknown game")
        if owner != user_id:
            raise GameError("not_yours")

        async with wallet.bet_lock(bet_id), wallet.user_lock(owner):
            async with self.sf() as session:
                async with session.begin():
                    bet = await session.get(Bet, bet_id, with_for_update=True)
                    if bet is None or bet.status != "ACTIVE":
                        raise StaleBet("closed")
                    if bet.step != step_no:
                        raise StaleBet("stale")
                    user = await session.get(User, bet.user_id, with_for_update=True)
                    if user is None:
                        raise StaleBet("user missing")
                    if user.is_banned:
                        raise BettingClosed("banned")
                    if chat_id is not None and bet.chat_id is not None and chat_id != bet.chat_id:
                        raise GameError("not_yours")

                    seed = await session.get(Seed, bet.seed_id) if bet.seed_id else None
                    if seed is None or seed.server_seed is None:
                        raise StaleBet("seed missing")
                    rng = FairRNG(seed.server_seed, bet.client_seed, bet.nonce)
                    stored = bet.result or {}
                    rng.seek(int(stored.get("cursor", 0)))
                    rng.proof = list(stored.get("proof", []))

                    state = copy.deepcopy(stored.get("state") or {})
                    rnd = game.step(state, action, arg, rng)
                    extra = int(rnd.detail.pop("_extra_stake", 0) or 0)
                    if extra:
                        if user.balance < extra:
                            raise GameError("Not enough Chips for that action.")
                        wallet.credit_in_session(
                            session, user, -extra, wallet.BET, game=bet.game, bet_id=bet.id
                        )
                        bet.amount += extra
                        user.total_wagered += extra
                    rnd.multiplier = self._cap_multiplier(bet.amount, rnd.multiplier)

                    if rnd.finished:
                        setting = await self._setting(session, game)
                        self._finish(
                            session, bet, user, rnd, list(rng.proof), self._edge_scale(game, setting)
                        )
                    else:
                        bet.step += 1
                        bet.result = {
                            "state": rnd.state,
                            "proof": list(rng.proof),
                            "cursor": rng.cursor,
                            "screen": rnd.text,
                            "detail": rnd.detail,
                        }
                    await session.flush()
                    balance = user.balance
        return Play(bet=bet, round=rnd, game=game, balance=balance)

    async def view(self, bet_id: int) -> Play | None:
        async with self.sf() as session:
            bet = await session.get(Bet, bet_id)
            if bet is None:
                return None
            game = get_game(bet.game)
            user = await session.get(User, bet.user_id)
            if game is None or user is None:
                return None
            if bet.status != "ACTIVE":
                return None
            state = (bet.result or {}).get("state") or {}
            rnd = game.view(state)
            return Play(bet=bet, round=rnd, game=game, balance=user.balance)

    async def auto_settle(self, bet_id: int, reason: str = "timeout") -> Play | None:
        async with self.sf() as probe:
            existing = await probe.get(Bet, bet_id)
            if existing is None:
                return None
            owner = existing.user_id
            game = get_game(existing.game)
        if game is None:
            return None
        async with wallet.bet_lock(bet_id), wallet.user_lock(owner):
            async with self.sf() as session:
                async with session.begin():
                    bet = await session.get(Bet, bet_id, with_for_update=True)
                    if bet is None or bet.status != "ACTIVE":
                        return None
                    user = await session.get(User, bet.user_id, with_for_update=True)
                    if user is None:
                        return None
                    state = copy.deepcopy((bet.result or {}).get("state") or {})
                    try:
                        rnd = game.auto_settle(state)
                    except Exception:
                        log.exception("auto settle failed", extra={"bet_id": bet_id})
                        rnd = Round(finished=True, multiplier=0.0, status="LOST", text="")
                    rnd.detail = {**rnd.detail, "auto": reason}
                    setting = await self._setting(session, game)
                    self._finish(session, bet, user, rnd, None, self._edge_scale(game, setting))
                    await session.flush()
                    balance = user.balance
        return Play(bet=bet, round=rnd, game=game, balance=balance)

    async def open_bet(
        self,
        user_id: int,
        game_key: str,
        stake: int,
        params: dict[str, str] | None = None,
        *,
        chat_id: int | None = None,
        text: str = "Waiting for the round…",
    ) -> Bet:
        """Debit a stake and open an ACTIVE bet for a shared/group round."""
        game = get_game(game_key)
        if game is None:
            raise GameError("Unknown game.")
        stake = int(stake)
        if stake <= 0:
            raise GameError("Your bet must be positive.")
        self.limiter.check(user_id)
        async with wallet.user_lock(user_id):
            async with self.sf() as session:
                async with session.begin():
                    user, _ = await repo.get_or_create_user(
                        session, user_id, starting_balance=self.settings.starting_balance
                    )
                    setting = await self._setting(session, game)
                    now = utcnow()
                    if user.is_banned:
                        raise BettingClosed("banned")
                    paused = _aware(user.paused_until)
                    if paused and paused > now:
                        raise BettingClosed("paused")
                    if not setting.enabled:
                        raise BettingClosed("disabled")
                    if stake < setting.min_bet or stake > setting.max_bet:
                        raise GameError(
                            f"Bet must be between {setting.min_bet / 100:,.0f} and {setting.max_bet / 100:,.0f} 🪙."
                        )
                    if user.balance < stake:
                        raise InsufficientFunds("Not enough Chips.")
                    reset_at = _aware(user.daily_reset_at)
                    if reset_at is None or reset_at.date() < now.date():
                        user.daily_wagered = 0
                        user.daily_reset_at = now
                    if user.daily_limit and user.daily_wagered + stake > user.daily_limit:
                        raise BettingClosed("daily_limit")
                    await self._ensure_no_active(session, user_id, game.key)
                    seed = await fairness.get_active_seed(session, user_id)
                    nonce = seed.nonce
                    seed.nonce += 1
                    wallet.credit_in_session(session, user, -stake, wallet.BET, game=game.key)
                    user.total_wagered += stake
                    user.games_played += 1
                    user.daily_wagered += stake
                    user.last_active = now
                    bet = Bet(
                        user_id=user_id,
                        game=game.key,
                        amount=stake,
                        params=params or {},
                        result={"state": {}, "proof": [], "cursor": 0, "screen": text, "detail": {}},
                        seed_id=seed.id,
                        server_seed_hash=seed.server_seed_hash,
                        client_seed=seed.client_seed,
                        nonce=nonce,
                        status="ACTIVE",
                        chat_id=chat_id,
                    )
                    session.add(bet)
                    await session.flush()
                    return bet

    async def settle_manual(
        self,
        bet_id: int,
        multiplier: float,
        status: str = "WON",
        *,
        text: str = "",
        detail: dict[str, Any] | None = None,
    ) -> Bet | None:
        """Settle an ACTIVE bet opened for a shared round. Idempotent."""
        async with self.sf() as probe:
            existing = await probe.get(Bet, bet_id)
            if existing is None:
                return None
            owner = existing.user_id
        async with wallet.bet_lock(bet_id), wallet.user_lock(owner):
            async with self.sf() as session:
                async with session.begin():
                    bet = await session.get(Bet, bet_id, with_for_update=True)
                    if bet is None or bet.status != "ACTIVE":
                        return bet
                    user = await session.get(User, bet.user_id, with_for_update=True)
                    if user is None:
                        return bet
                    game = get_game(bet.game)
                    setting = await self._setting(session, game) if game else None
                    scale = self._edge_scale(game, setting) if game and setting else 1.0
                    rnd = Round(
                        finished=True,
                        multiplier=self._cap_multiplier(bet.amount, max(0.0, multiplier)),
                        status=status if multiplier > 0 else "LOST",
                        text=text,
                        detail=detail or {},
                    )
                    self._finish(session, bet, user, rnd, None, scale)
                    await session.flush()
                    return bet

    async def settle_all_active(self) -> int:
        """Graceful-shutdown helper: cash out or refund everything still open."""
        async with self.sf() as session:
            bets = list(
                (await session.execute(Bet.__table__.select().where(Bet.status == "ACTIVE"))).mappings()
            )
        settled = 0
        for row in bets:
            try:
                if await self.auto_settle(int(row["id"]), "shutdown"):
                    settled += 1
            except Exception:
                log.exception("shutdown settlement failed", extra={"bet_id": row["id"]})
        return settled

    async def refund(self, bet_id: int, note: str = "error") -> int | None:
        async with self.sf() as probe:
            existing = await probe.get(Bet, bet_id)
            if existing is None:
                return None
            owner = existing.user_id
        async with wallet.bet_lock(bet_id), wallet.user_lock(owner):
            async with self.sf() as session:
                async with session.begin():
                    bet = await session.get(Bet, bet_id, with_for_update=True)
                    if bet is None or bet.status != "ACTIVE":
                        return None
                    user = await session.get(User, bet.user_id, with_for_update=True)
                    if user is None:
                        return None
                    wallet.credit_in_session(
                        session,
                        user,
                        bet.amount,
                        wallet.REFUND,
                        game=bet.game,
                        bet_id=bet.id,
                        note=note,
                    )
                    bet.status = "REFUNDED"
                    bet.settled_at = utcnow()
                    bet.multiplier = 0.0
                    bet.payout = bet.amount
                    bet.profit = 0
                    result = dict(bet.result or {})
                    result["state"] = {}
                    result["detail"] = {"refund": True, "note": note}
                    result["screen"] = "↩️ Stake refunded."
                    bet.result = result
                    await session.flush()
                    return bet.amount

    async def timeout_active(self, older_than_seconds: int | None = None) -> int:
        seconds = older_than_seconds or self.settings.session_timeout_seconds
        cutoff = utcnow() - dt.timedelta(seconds=seconds)
        async with self.sf() as session:
            bets = await repo.stale_active_bets(session, cutoff)
        settled = 0
        for bet in bets:
            try:
                if await self.auto_settle(bet.id, "timeout"):
                    settled += 1
            except Exception:
                log.exception("timeout settlement failed", extra={"bet_id": bet.id})
        return settled

    async def verify(self, bet_id: int) -> dict[str, Any]:
        async with self.sf() as session:
            bet = await session.get(Bet, bet_id)
            if bet is None:
                return {"ok": False, "reason": "not_found"}
            seed = await session.get(Seed, bet.seed_id) if bet.seed_id else None
            proof = list((bet.result or {}).get("proof") or [])
            if seed is None:
                return {"ok": False, "reason": "seed_missing", "bet": bet}
            if not seed.revealed_at:
                return {
                    "ok": True,
                    "revealed": False,
                    "bet": bet,
                    "hash": seed.server_seed_hash,
                    "proof_len": len(proof),
                    "message": "Seed is still secret. The commitment hash matches; rotate the seed to fully verify.",
                }
            replay = FairRNG(seed.server_seed, bet.client_seed, bet.nonce)
            regenerated = [replay._raw()[:4].hex() for _ in range(len(proof))]
            return {
                "ok": True,
                "revealed": True,
                "bet": bet,
                "hash": seed.server_seed_hash,
                "matches": regenerated == proof,
                "server_seed": seed.server_seed,
                "proof_len": len(proof),
            }
