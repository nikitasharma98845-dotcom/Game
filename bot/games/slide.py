from __future__ import annotations

from functools import lru_cache

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register

N = 24
TARGET_INDEXES = (3, 8, 11, 14, 17, 20, 23)


@lru_cache(maxsize=1)
def strip() -> tuple[float, ...]:
    return tuple(round(0.99 * N / (N - j), 2) for j in range(N))


@lru_cache(maxsize=1)
def targets() -> tuple[float, ...]:
    return tuple(strip()[i] for i in TARGET_INDEXES)


@register
class SlideGame(BaseGame):
    key = "slide"
    name = "Slide"
    emoji = "🎚️"
    category = "instant"
    order = 13
    rules_text = (
        "Choose a target multiplier, then a marker slides across a 24-step strip and stops "
        "on one value. If the stop is at or above your target, you win the target multiplier."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter(f"🎚️ Target {t:,.2f}x", {"target": f"{t:g}"}) for t in targets()]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        try:
            target = float(raw.get("target", 2))
        except (TypeError, ValueError) as exc:
            raise GameError("Target must be a number.") from exc
        allowed = targets()
        if not any(abs(target - allowed_t) < 0.005 for allowed_t in allowed):
            raise GameError("Choose one of the offered Slide targets.")
        return {"target": f"{target:g}"}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        target = float(params["target"])
        values = strip()
        index = rng.int(N)
        landed = values[index]
        win = landed >= target
        multiplier = target if win else 0.0
        strip_view = " ".join(
            f"[{v:,.2f}]" if i == index else f"{v:,.2f}" for i, v in enumerate(values)
        )
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if win else "LOST",
            text=(
                f"🎚️ <b>Slide stopped at {landed:,.2f}x</b> (step {index + 1}/{N})\n"
                f"Your target: {target:,.2f}x\n\n"
                f"{'🟢 Target reached!' if win else '🔴 Below target.'}\n"
                f"<code>{strip_view}</code>"
            ),
            detail={"index": index, "landed": landed, "target": target, "strip": list(values)},
        )

    def theoretical_rtp(self) -> float:
        target = targets()[2]
        values = strip()
        wins = sum(1 for v in values if v >= target)
        return wins / N * target
