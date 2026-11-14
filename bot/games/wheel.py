from __future__ import annotations

from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register
from bot.games.tables import scale_to_rtp, table_rtp

SHAPES = {
    "low": [1.2, 1.1, 1.0, 1.1, 1.2, 0.9],
    "medium": [0.0, 0.5, 1.0, 1.5, 2.0, 0.5],
    "high": [0.0, 0.0, 0.5, 1.0, 2.0, 4.0, 8.0],
}


@lru_cache(maxsize=64)
def wheel_values(segments: int, risk: str) -> tuple[float, ...]:
    pattern = SHAPES[risk]
    shape = [pattern[i % len(pattern)] for i in range(segments)]
    return tuple(scale_to_rtp(shape))


@register
class WheelGame(BaseGame):
    key = "wheel"
    name = "Wheel"
    emoji = "🎡"
    category = "wheel"
    order = 20
    rules_text = (
        "Spin a wheel of 10–50 segments. Risk changes the spread: low risk keeps most "
        "segments near 1x, high risk has empty segments and big payers."
    )

    def quick_starts(self) -> list[Starter]:
        out = []
        for seg in (10, 20, 30, 40):
            for risk in ("low", "medium", "high"):
                values = wheel_values(seg, risk)
                out.append(
                    Starter(
                        f"{seg} seg · {risk.title()} · up to {max(values):.1f}x",
                        {"segments": str(seg), "risk": risk},
                    )
                )
        return out

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        from bot.core.errors import GameError

        try:
            segments = int(raw.get("segments", 20))
        except (TypeError, ValueError) as exc:
            raise GameError("Segments must be a whole number.") from exc
        if not 10 <= segments <= 50:
            raise GameError("Segments must be between 10 and 50.")
        risk = str(raw.get("risk", "medium")).lower()
        if risk not in SHAPES:
            raise GameError("Risk must be low, medium or high.")
        return {"segments": str(segments), "risk": risk}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        segments = int(params["segments"])
        risk = params["risk"]
        values = wheel_values(segments, risk)
        index = rng.int(segments)
        multiplier = values[index]
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"🎡 <b>Wheel stopped on {multiplier:.2f}x</b>\n"
                f"{segments} segments · {risk} risk\n\n"
                f"{'🟢' if multiplier > 0 else '⚫'} {multiplier:.2f}x"
            ),
            detail={"segments": segments, "risk": risk, "index": index, "values": list(values)},
        )

    def theoretical_rtp(self) -> float:
        values = wheel_values(20, "medium")
        return sum(values) / len(values)


@lru_cache(maxsize=32)
def wheel_table_rtp(segments: int, risk: str) -> float:
    return table_rtp([(v, 1 / segments) for v in wheel_values(segments, risk)])
