from __future__ import annotations

import itertools
from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register

MAJORS = [
    "🃏 The Fool",
    "🎩 The Magician",
    "🌙 The High Priestess",
    "👑 The Empress",
    "🏛️ The Emperor",
    "📜 The Hierophant",
    "💞 The Lovers",
    "⚔️ The Chariot",
    "⚖️ Justice",
    "🕯️ The Hermit",
    "🎡 Wheel of Fortune",
    "💪 Strength",
    "🙃 The Hanged Man",
    "☠️ Death",
    "🧪 Temperance",
    "😈 The Devil",
    "🗼 The Tower",
    "⭐ The Star",
    "🌕 The Moon",
    "☀️ The Sun",
    "📯 Judgement",
    "🌍 The World",
]
BASE_VALUES = [0.35, 0.55, 0.75, 0.95, 1.1, 1.3, 1.6, 2.0, 2.6, 3.5, 5.0, 7.0]
SHAPE = [BASE_VALUES[i % len(BASE_VALUES)] for i in range(len(MAJORS))]


@lru_cache(maxsize=1)
def tarot_table() -> tuple[tuple[str, float], ...]:
    base = SHAPE
    combos = list(itertools.combinations(range(len(base)), 3))
    mean_product = sum(base[a] * base[b] * base[c] for a, b, c in combos) / len(combos)
    factor = (0.99 / mean_product) ** (1 / 3)
    return tuple((MAJORS[i], round(base[i] * factor, 2)) for i in range(len(MAJORS)))


@register
class TarotGame(BaseGame):
    key = "tarot"
    name = "Tarot"
    emoji = "🔮"
    category = "instant"
    order = 9
    rules_text = (
        "Draw three cards from the 22 Major Arcana. Their multipliers multiply together. "
        "Two modest cards can beat one strong card — the spread decides."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter("🔮 Draw three cards", {})]

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        table = tarot_table()
        order = rng.shuffle(list(range(len(table))))
        picked = [table[i] for i in order[:3]]
        multiplier = 1.0
        for _, m in picked:
            multiplier *= m
        multiplier = round(multiplier, 2)
        cards = "\n".join(f"• {name} — {m:.2f}x" for name, m in picked)
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=f"🔮 <b>Your spread</b>\n{cards}\n\nCombined: <b>{multiplier:.2f}x</b>",
            detail={"cards": [name for name, _ in picked], "values": [m for _, m in picked]},
        )

    def theoretical_rtp(self) -> float:
        table = tarot_table()
        values = [m for _, m in table]
        combos = list(itertools.combinations(values, 3))
        return sum(a * b * c for a, b, c in combos) / len(combos)
