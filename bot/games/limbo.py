from __future__ import annotations

import math

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register


@register
class LimboGame(BaseGame):
    key = "limbo"
    name = "Limbo"
    emoji = "🚀"
    category = "instant"
    order = 2
    rules_text = (
        "Set a target multiplier from 1.01x to 1,000,000x. A result is generated and "
        "you win the target multiplier if the result reaches it. The higher the target, "
        "the lower your chance."
    )

    TARGETS = ("1.01", "1.5", "2", "3", "5", "10", "25", "50", "100", "1000")

    def quick_starts(self) -> list[Starter]:
        return [Starter(f"🎯 {t}x", {"target": t}) for t in self.TARGETS]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        try:
            target = float(raw.get("target", 2))
        except (TypeError, ValueError) as exc:
            raise GameError("Target must be a number.") from exc
        if not 1.01 <= target <= 1_000_000:
            raise GameError("Target must be between 1.01x and 1,000,000x.")
        return {"target": f"{target:g}"}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        target = float(params["target"])
        r = rng.next()
        if r <= 0:
            r = 1e-12
        result = max(1.0, math.floor((1 - self.edge) / r * 100) / 100)
        win = result >= target
        multiplier = target if win else 0.0
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if win else "LOST",
            text=(
                f"🚀 <b>Limbo touched {result:,.2f}x</b>\n"
                f"Your target: {target:,.2f}x\n\n"
                f"{'🟢 <b>Target reached!</b>' if win else '🔴 <b>Fell short.</b>'}"
            ),
            detail={"result": result, "target": target},
        )

    def theoretical_rtp(self) -> float:
        return 1 - self.edge
