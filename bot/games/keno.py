from __future__ import annotations

import math
from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register
from bot.games.tables import hypergeom

RISKS = ("low", "classic", "medium", "high")


@lru_cache(maxsize=64)
def keno_paid_hits(picks: int, risk: str) -> tuple[int, ...]:
    thresholds = {
        "low": max(1, math.floor(picks * 0.5)),
        "classic": max(2, math.ceil(picks * 0.6)),
        "medium": max(2, math.ceil(picks * 0.7)),
        "high": max(3, math.ceil(picks * 0.9)),
    }
    hits = list(range(min(picks, thresholds[risk]), picks + 1))
    if not hits:
        hits = [picks]
    # Drop tiers that would pay less than the stake.
    while len(hits) > 1:
        mult = 0.99 / (len(hits) * hypergeom(40, 10, picks, hits[0]))
        if mult >= 1.0:
            break
        hits.pop(0)
    return tuple(hits)


@lru_cache(maxsize=64)
def keno_table(picks: int, risk: str) -> tuple[tuple[int, float], ...]:
    hits = keno_paid_hits(picks, risk)
    table = []
    for h in hits:
        p = hypergeom(40, 10, picks, h)
        table.append((h, round(0.99 / (len(hits) * p), 2)))
    return tuple(table)


@register
class KenoGame(BaseGame):
    key = "keno"
    name = "Keno"
    emoji = "🔢"
    category = "instant"
    order = 5
    rules_text = (
        "Pick 1–10 numbers from 40. Ten are drawn. Higher tiers pay more; risk sets how "
        "many catches you need before a payout."
    )

    def quick_starts(self) -> list[Starter]:
        out = []
        for picks in (1, 3, 5, 10):
            for risk in ("low", "classic", "high"):
                table = keno_table(picks, risk)
                top = table[-1][1]
                out.append(
                    Starter(
                        f"{picks} picks · {risk.title()} · {top:,.0f}x",
                        {"picks": str(picks), "risk": risk},
                    )
                )
        return out

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        from bot.core.errors import GameError

        try:
            picks = int(raw.get("picks", 5))
        except (TypeError, ValueError) as exc:
            raise GameError("Picks must be a whole number.") from exc
        if not 1 <= picks <= 10:
            raise GameError("Pick between 1 and 10 numbers.")
        risk = str(raw.get("risk", "classic")).lower()
        if risk not in RISKS:
            raise GameError("Risk must be low, classic, medium or high.")
        return {"picks": str(picks), "risk": risk}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        picks = int(params["picks"])
        risk = params["risk"]
        chosen = sorted(rng.shuffle(list(range(1, 41)))[:picks])
        drawn = sorted(rng.shuffle(list(range(1, 41)))[:10])
        hits = len(set(chosen) & set(drawn))
        table = dict(keno_table(picks, risk))
        multiplier = table.get(hits, 0.0)
        marks = " ".join(f"<b>{n:02d}</b>" if n in chosen else f"{n:02d}" for n in drawn)
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"🔢 <b>{hits} hit{'s' if hits != 1 else ''}</b> · {multiplier:.2f}x\n"
                f"Your picks: <code>{' '.join(f'{n:02d}' for n in chosen)}</code>\n"
                f"Drawn: {marks}"
            ),
            detail={"chosen": chosen, "drawn": drawn, "hits": hits, "risk": risk},
        )

    def theoretical_rtp(self) -> float:
        from bot.games.tables import hypergeom as hg

        return sum(hg(40, 10, 5, h) * m for h, m in keno_table(5, "classic"))
