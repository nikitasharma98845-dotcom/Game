from __future__ import annotations

from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register

SEGMENTS = 20
SHAPES = {
    "low": [1.2, 1.0, 0.9, 1.1, 1.3, 0.8, 1.0, 1.4],
    "medium": [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 0.5, 1.0],
    "high": [0.0, 0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 0.0],
}


@lru_cache(maxsize=4)
def dart_board(risk: str) -> tuple[float, ...]:
    pattern = SHAPES[risk]
    shape = [pattern[i % len(pattern)] for i in range(SEGMENTS)]
    mean = sum(shape) / len(shape)
    return tuple(round(v * 0.99 / mean, 2) for v in shape)


@register
class DartsGame(BaseGame):
    key = "darts"
    name = "Darts"
    emoji = "🎯"
    category = "instant"
    order = 10
    rules_text = (
        "Throw a dart at a 20-segment board. Risk changes the rings: low keeps you near "
        "1x, high has many misses and a 25x bullseye. The outcome comes from the fair RNG."
    )

    def quick_starts(self) -> list[Starter]:
        return [
            Starter(f"🎯 {risk.title()} board · up to {max(dart_board(risk)):.0f}x", {"risk": risk})
            for risk in SHAPES
        ]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        from bot.core.errors import GameError

        risk = str(raw.get("risk", "medium")).lower()
        if risk not in SHAPES:
            raise GameError("Risk must be low, medium or high.")
        return {"risk": risk}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        risk = params["risk"]
        board = dart_board(risk)
        index = rng.int(SEGMENTS)
        multiplier = board[index]
        top = max(board)
        if multiplier == top:
            ring = "bullseye 🎯"
        elif multiplier >= 2:
            ring = "inner ring"
        elif multiplier > 0:
            ring = "outer ring"
        else:
            ring = "miss"
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"🎯 <b>Dart lands in the {ring}</b>\n"
                f"Board: {risk} risk · 20 segments\n\n"
                f"{'🟢' if multiplier else '⚫'} {multiplier:.2f}x"
            ),
            detail={"risk": risk, "index": index, "board": list(board), "ring": ring},
        )

    def theoretical_rtp(self) -> float:
        board = dart_board("medium")
        return sum(board) / len(board)
