from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from bot.core.errors import GameError
from bot.core.fairness import FairRNG


@dataclass(slots=True)
class Button:
    label: str
    action: str
    arg: str = ""


@dataclass(slots=True)
class Starter:
    """One-tap way to start a game with preset parameters."""

    label: str
    params: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Round:
    finished: bool = False
    multiplier: float = 0.0
    status: str = "WON"  # WON | LOST | CASHED_OUT (used when finished)
    text: str = ""
    buttons: list[list[Button]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)


class BaseGame:
    """A game is a pure state machine; all money movement lives in BetEngine."""

    key: ClassVar[str] = ""
    name: ClassVar[str] = ""
    emoji: ClassVar[str] = "🎲"
    category: ClassVar[str] = "instant"
    multi_step: ClassVar[bool] = False
    edge: ClassVar[float] = 0.01
    rules_text: ClassVar[str] = ""
    order: ClassVar[int] = 100

    def quick_starts(self) -> list[Starter]:
        return [Starter("▶️ Play")]

    def validate(self, raw: dict[str, str]) -> dict[str, Any]:
        return dict(raw)

    def start(self, rng: FairRNG, params: dict[str, Any], stake: int) -> Round:
        raise GameError("This game cannot be started.")

    def step(self, state: dict[str, Any], action: str, arg: str, rng: FairRNG) -> Round:
        raise GameError("This round has no further actions.")

    def view(self, state: dict[str, Any]) -> Round:
        return Round(finished=False, text=state.get("screen", ""), state=state)

    def auto_settle(self, state: dict[str, Any]) -> Round:
        multiplier = float(state.get("multiplier", 0.0))
        return Round(
            finished=True,
            multiplier=multiplier,
            status="CASHED_OUT",
            text=f"⏰ Round timed out and was auto-cashed-out at **{multiplier:.2f}x**.",
            detail={"auto": True},
        )

    def theoretical_rtp(self) -> float:
        return 1.0 - self.edge


def cashout_button(multiplier: float) -> Button:
    return Button(f"💰 Cash out {multiplier:.2f}x", "cashout")
