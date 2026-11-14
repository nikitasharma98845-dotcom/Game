from __future__ import annotations

from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register
from bot.games.tables import binomial

BASES = {"low": 1.45, "medium": 2.1, "high": 3.4}


@lru_cache(maxsize=64)
def plinko_table(rows: int, risk: str) -> tuple[float, ...]:
    probs = [binomial(rows, i) for i in range(rows + 1)]
    base = BASES[risk]
    shape = [base ** abs(i - rows / 2) for i in range(rows + 1)]
    raw_rtp = sum(p * m for p, m in zip(probs, shape, strict=True))
    factor = 0.99 / raw_rtp
    return tuple(round(m * factor, 2) for m in shape)


@register
class PlinkoGame(BaseGame):
    key = "plinko"
    name = "Plinko"
    emoji = "🔻"
    category = "instant"
    order = 4
    rules_text = (
        "Drop a ball through 8–16 rows of pegs. Each bounce goes left or right, and the "
        "final slot pays its multiplier. Low risk hugs the middle; high risk chases the edges."
    )

    def quick_starts(self) -> list[Starter]:
        out = []
        for rows in (8, 12, 16):
            for risk in ("low", "medium", "high"):
                table = plinko_table(rows, risk)
                out.append(
                    Starter(
                        f"{rows} rows · {risk.title()} · {max(table):.0f}x",
                        {"rows": str(rows), "risk": risk},
                    )
                )
        return out

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        from bot.core.errors import GameError

        try:
            rows = int(raw.get("rows", 12))
        except (TypeError, ValueError) as exc:
            raise GameError("Rows must be a whole number.") from exc
        if not 8 <= rows <= 16:
            raise GameError("Rows must be between 8 and 16.")
        risk = str(raw.get("risk", "medium")).lower()
        if risk not in BASES:
            raise GameError("Risk must be low, medium or high.")
        return {"rows": str(rows), "risk": risk}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        rows = int(params["rows"])
        risk = params["risk"]
        table = plinko_table(rows, risk)
        slot = 0
        path = []
        for _ in range(rows):
            if rng.next() < 0.5:
                path.append("L")
            else:
                path.append("R")
                slot += 1
        multiplier = table[slot]
        strip = " ".join(("▶️" if i == slot else f"{m:g}") for i, m in enumerate(table))
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"🔻 <b>Ball landed in slot {slot + 1} · {multiplier:.2f}x</b>\n"
                f"Path: <code>{''.join(path)}</code>\n\n"
                f"<code>{strip}</code>"
            ),
            detail={"rows": rows, "risk": risk, "slot": slot, "path": path, "table": list(table), "image": "plinko"},
        )

    def theoretical_rtp(self) -> float:
        table = plinko_table(12, "medium")
        return sum(binomial(12, i) * m for i, m in enumerate(table))
