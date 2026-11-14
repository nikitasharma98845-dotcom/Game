from __future__ import annotations

import itertools
from collections import Counter
from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register

GEMS = ["💎", "🔶", "🟣", "🔵", "🟢", "🔴", "🟡"]
PATTERNS = ("pair", "two_pair", "three", "full_house", "four", "five")


def _pattern(counts: list[int]) -> str:
    groups = sorted(counts, reverse=True)
    if groups[0] == 5:
        return "five"
    if groups[0] == 4:
        return "four"
    if groups[0] == 3 and groups[1] == 2:
        return "full_house"
    if groups[0] == 3:
        return "three"
    if groups[0] == 2 and groups[1] == 2:
        return "two_pair"
    if groups[0] == 2:
        return "pair"
    return "none"


@lru_cache(maxsize=1)
def diamond_odds() -> dict[str, float]:
    counts: Counter[str] = Counter()
    total = 0
    for combo in itertools.product(range(7), repeat=5):
        counts[_pattern(list(Counter(combo).values()))] += 1
        total += 1
    return {k: v / total for k, v in counts.items()}


@lru_cache(maxsize=1)
def diamond_table() -> dict[str, float]:
    odds = diamond_odds()
    paid = [p for p in PATTERNS if p != "pair"]
    return {p: round(0.99 / (len(paid) * odds[p]), 2) for p in paid}


@register
class DiamondsGame(BaseGame):
    key = "diamonds"
    name = "Diamonds"
    emoji = "💎"
    category = "instant"
    order = 6
    rules_text = (
        "Draw five gems from seven colours. Two pair or better pays; five of a kind is "
        "the jackpot. Pairs alone return nothing."
    )

    def quick_starts(self) -> list[Starter]:
        table = diamond_table()
        return [
            Starter("💎 Draw 5 gems", {}),
            Starter(f"ℹ️ Top prize {table['five']:,.0f}x", {}),
        ]

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        draw = [GEMS[rng.int(len(GEMS))] for _ in range(5)]
        pattern = _pattern(list(Counter(draw).values()))
        multiplier = diamond_table().get(pattern, 0.0)
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"💎 <b>{' '.join(draw)}</b>\n"
                f"Pattern: <b>{pattern.replace('_', ' ').title()}</b>\n\n"
                f"{'🟢' if multiplier else '⚫'} {multiplier:.2f}x"
            ),
            detail={"draw": draw, "pattern": pattern},
        )

    def theoretical_rtp(self) -> float:
        odds = diamond_odds()
        return sum(odds[p] * m for p, m in diamond_table().items())
