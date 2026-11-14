from __future__ import annotations

import math

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register


@register
class DiceGame(BaseGame):
    key = "dice"
    name = "Dice"
    emoji = "🎲"
    category = "instant"
    order = 1
    rules_text = (
        "Pick a win chance and whether the roll must land under or over your target. "
        "Rolls are 0.00–99.99. Payout = (100% − house edge) ÷ win chance."
    )

    def _mult(self, chance: float) -> float:
        return math.floor((1 - self.edge) / chance * 10_000) / 10_000

    def quick_starts(self) -> list[Starter]:
        out: list[Starter] = []
        for chance in (2, 10, 25, 50, 75, 95, 98):
            out.append(
                Starter(
                    f"⬇️ Under {chance}% · {self._mult(chance / 100):.2f}x",
                    {"direction": "under", "target": str(chance)},
                )
            )
            out.append(
                Starter(
                    f"⬆️ Over {chance}% · {self._mult(chance / 100):.2f}x",
                    {"direction": "over", "target": str(chance)},
                )
            )
        return out

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        direction = str(raw.get("direction", "under")).lower()
        if direction not in ("under", "over"):
            raise GameError("Direction must be under or over.")
        try:
            target = float(raw.get("target", 50))
        except (TypeError, ValueError) as exc:
            raise GameError("Target must be a number.") from exc
        if not 2 <= target <= 98:
            raise GameError("Win chance must be between 2% and 98%.")
        target = round(target, 2)
        return {"direction": direction, "target": f"{target:g}"}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        direction = params["direction"]
        target = float(params["target"])
        target_int = int(round(target * 100))
        roll_int = rng.int(10_000)
        roll = roll_int / 100
        if direction == "under":
            win = roll_int < target_int
            chance = target_int / 10_000
            label = f"under {target:g}"
        else:
            win = roll_int > target_int
            chance = (10_000 - target_int - 1) / 10_000
            label = f"over {target:g}"
        if chance <= 0:
            raise GameError("That target has no winning outcomes.")
        multiplier = self._mult(chance) if win else 0.0
        icon = "🟢" if win else "🔴"
        text = (
            f"🎲 <b>Rolled {roll:,.2f}</b>\n"
            f"Bet: {label} · win chance {chance * 100:.2f}%\n\n"
            f"{icon} <b>{'WIN' if win else 'LOSS'}</b> at {multiplier:.2f}x"
        )
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if win else "LOST",
            text=text,
            detail={"roll": roll, "target": target, "direction": direction},
        )

    def theoretical_rtp(self) -> float:
        return 1 - self.edge - 0.0001
