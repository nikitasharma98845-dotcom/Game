from __future__ import annotations

import math
import time

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter
from bot.games.registry import register

GROWTH = 1.06  # multiplier growth per second


def score_at(elapsed: float) -> float:
    return max(1.0, round(GROWTH ** max(0.0, elapsed), 2))


def crash_point(rng: FairRNG, edge: float = 0.01) -> float:
    u = rng.next()
    if u >= 1.0:
        u = 1 - 1e-12
    value = (1 - edge) / (1 - u)
    return max(1.0, math.floor(value * 100) / 100)


@register
class CrashGame(BaseGame):
    key = "crash"
    name = "Crash"
    emoji = "🚀"
    category = "group"
    multi_step = True
    order = 60
    rules_text = (
        "The multiplier climbs from 1.00x in real time. Cash out before the rocket crashes. "
        "Set an auto-cashout to lock in a target. In groups the round is shared by everyone."
    )

    def quick_starts(self) -> list[Starter]:
        out = [Starter("🚀 Manual cash-out", {})]
        for target in ("1.5", "2", "3", "5", "10"):
            out.append(Starter(f"🤖 Auto {target}x", {"auto": target}))
        return out

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        auto = raw.get("auto")
        if auto in (None, "", "none"):
            return {}
        try:
            value = float(auto)
        except (TypeError, ValueError) as exc:
            raise GameError("Auto-cashout must be a number.") from exc
        if not 1.01 <= value <= 1_000_000:
            raise GameError("Auto-cashout must be between 1.01x and 1,000,000x.")
        return {"auto": f"{value:g}"}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        crash = crash_point(rng, self.edge)
        auto = float(params["auto"]) if params.get("auto") else None
        if auto is not None:
            won = crash >= auto
            multiplier = auto if won else 0.0
            return Round(
                finished=True,
                multiplier=multiplier,
                status="WON" if won else "LOST",
                text=(
                    f"🚀 <b>Crash · auto {auto:.2f}x</b>\n"
                    f"The rocket crashed at <b>{crash:.2f}x</b>.\n\n"
                    + (
                        f"🟢 Your auto-cashout triggered at {auto:.2f}x."
                        if won
                        else "🔴 It crashed before your target."
                    )
                ),
                detail={"crash": crash, "auto": auto},
            )
        state = {
            "crash": crash,
            "started_at": time.time(),
            "screen": "",
            "auto": None,
        }
        text = (
            "🚀 <b>Crash</b>\n"
            "The multiplier is climbing. Tap cash out before it crashes!\n\n"
            "Current: <b>1.00x</b>"
        )
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=1.0,
            text=text,
            state=state,
            buttons=[[Button("💰 Cash out", "cashout")]],
        )

    def _score(self, state: dict) -> float:
        return score_at(time.time() - float(state["started_at"]))

    def view(self, state: dict) -> Round:
        score = self._score(state)
        crash = float(state["crash"])
        text = (
            f"💥 <b>Crashed at {crash:.2f}x</b>"
            if score >= crash
            else f"🚀 <b>Current: {score:.2f}x</b>"
        )
        return Round(
            finished=False,
            multiplier=score,
            text=text,
            state=state,
            buttons=[[Button(f"💰 Cash out {score:.2f}x", "cashout")]],
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action != "cashout":
            raise GameError("Unknown action.")
        crash = float(state["crash"])
        score = self._score(state)
        if score >= crash:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=f"💥 <b>Crashed at {crash:.2f}x.</b> You were too late.",
                detail={"crash": crash, "score": score},
            )
        return Round(
            finished=True,
            multiplier=score,
            status="CASHED_OUT",
            text=(
                f"💰 <b>Cashed out at {score:.2f}x</b>\n"
                f"The rocket crashed at {crash:.2f}x."
            ),
            detail={"crash": crash, "score": score},
        )

    def auto_settle(self, state: dict) -> Round:
        crash = float(state.get("crash", 1.0))
        score = self._score(state)
        if score < crash:
            return Round(
                finished=True,
                multiplier=score,
                status="CASHED_OUT",
                text=f"⏰ Round timed out — cashed out at <b>{score:.2f}x</b> (crash was {crash:.2f}x).",
                detail={"crash": crash, "auto": True},
            )
        return Round(
            finished=True,
            multiplier=0.0,
            status="LOST",
            text=f"💥 Crashed at {crash:.2f}x before the timeout.",
            detail={"crash": crash, "auto": True},
        )

    def theoretical_rtp(self) -> float:
        return 0.99
