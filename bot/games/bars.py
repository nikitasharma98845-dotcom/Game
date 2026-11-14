from __future__ import annotations

from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register
from bot.games.tables import payout_for, table_rtp, weighted_table

RISK_SPECS: dict[str, dict] = {
    "low": {"mults": [1.2, 1.6, 2.2, 4.0], "weights": [0.5, 0.3, 0.15, 0.05], "zero": 0.4},
    "medium": {"mults": [1.5, 2.0, 3.0, 6.0, 15.0], "weights": [0.45, 0.3, 0.15, 0.08, 0.02], "zero": 0.55},
    "high": {"mults": [2.0, 3.0, 5.0, 12.0, 60.0], "weights": [0.4, 0.3, 0.18, 0.1, 0.02], "zero": 0.7},
}


@lru_cache(maxsize=4)
def bars_table(risk: str) -> tuple[tuple[float, float], ...]:
    spec = RISK_SPECS[risk]
    return tuple(weighted_table(spec["mults"], spec["weights"], zero_prob=spec["zero"], edge=0.01))


@register
class BarsGame(BaseGame):
    key = "bars"
    name = "Bars"
    emoji = "📊"
    category = "instant"
    order = 8
    rules_text = (
        "Three bars are revealed. You pick bar 1, 2 or 3 before they open, and receive "
        "the multiplier shown on your bar. Empty bars pay nothing."
    )

    def quick_starts(self) -> list[Starter]:
        return [
            Starter(f"1️⃣ Bar 1 · {risk.title()}", {"bar": "1", "risk": risk})
            for risk in RISK_SPECS
        ] + [
            Starter(f"2️⃣ Bar 2 · {risk.title()}", {"bar": "2", "risk": risk})
            for risk in RISK_SPECS
        ] + [
            Starter(f"3️⃣ Bar 3 · {risk.title()}", {"bar": "3", "risk": risk})
            for risk in RISK_SPECS
        ]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        from bot.core.errors import GameError

        try:
            bar = int(raw.get("bar", 1))
        except (TypeError, ValueError) as exc:
            raise GameError("Bar must be 1, 2 or 3.") from exc
        if bar not in (1, 2, 3):
            raise GameError("Bar must be 1, 2 or 3.")
        risk = str(raw.get("risk", "medium")).lower()
        if risk not in RISK_SPECS:
            raise GameError("Risk must be low, medium or high.")
        return {"bar": str(bar), "risk": risk}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        table = bars_table(params["risk"])
        values = [payout_for(table, rng.next()) for _ in range(3)]
        chosen = int(params["bar"])
        multiplier = values[chosen - 1]
        marks = "  ".join(
            f"{'👉' if i == chosen - 1 else '▫️'} {v:.2f}x" for i, v in enumerate(values)
        )
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"📊 <b>Bars opened</b>\n{marks}\n\n"
                f"{'🟢' if multiplier else '⚫'} Bar {chosen} paid <b>{multiplier:.2f}x</b>"
            ),
            detail={"values": values, "bar": chosen},
        )

    def theoretical_rtp(self) -> float:
        return table_rtp(bars_table("medium"))
