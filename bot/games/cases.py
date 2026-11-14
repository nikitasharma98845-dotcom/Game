from __future__ import annotations

from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register
from bot.games.tables import payout_for, table_rtp, weighted_table

CASES: dict[str, dict] = {
    "starter": {
        "emoji": "📦",
        "name": "Starter Crate",
        "mults": [1.4, 2.0, 3.0, 6.0],
        "weights": [0.55, 0.3, 0.12, 0.03],
        "zero": 0.42,
    },
    "vault": {
        "emoji": "🗃️",
        "name": "Vault Case",
        "mults": [1.6, 2.5, 4.0, 10.0, 40.0],
        "weights": [0.45, 0.3, 0.17, 0.07, 0.01],
        "zero": 0.56,
    },
    "dragon": {
        "emoji": "🐉",
        "name": "Dragon Hoard",
        "mults": [2.0, 4.0, 8.0, 25.0, 250.0],
        "weights": [0.4, 0.3, 0.2, 0.09, 0.01],
        "zero": 0.68,
    },
}


@lru_cache(maxsize=8)
def case_table(case: str) -> tuple[tuple[float, float], ...]:
    spec = CASES[case]
    return tuple(
        weighted_table(spec["mults"], spec["weights"], zero_prob=spec["zero"], edge=0.01)
    )


@register
class CasesGame(BaseGame):
    key = "cases"
    name = "Cases"
    emoji = "📦"
    category = "instant"
    order = 7
    rules_text = (
        "Open a case and receive the multiplier inside. Rarer cases have more empty slots "
        "but much bigger payers."
    )

    def quick_starts(self) -> list[Starter]:
        out = []
        for key in CASES:
            spec = CASES[key]
            table = case_table(key)
            top = max(m for m, _ in table)
            out.append(
                Starter(f"{spec['emoji']} {spec['name']} · up to {top:,.0f}x", {"case": key})
            )
        return out

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        from bot.core.errors import GameError

        case = str(raw.get("case", "starter")).lower()
        if case not in CASES:
            raise GameError("Unknown case.")
        return {"case": case}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        case = params["case"]
        spec = CASES[case]
        table = case_table(case)
        multiplier = payout_for(table, rng.next())
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"{spec['emoji']} <b>{spec['name']}</b>\n\n"
                + (
                    f"🎉 You found <b>{multiplier:.2f}x</b>!"
                    if multiplier
                    else "💨 The case was empty. Better luck next time."
                )
            ),
            detail={"case": case, "multiplier": multiplier},
        )

    def theoretical_rtp(self) -> float:
        return table_rtp(case_table("starter"))
