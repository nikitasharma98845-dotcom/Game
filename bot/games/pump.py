from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter, cashout_button
from bot.games.registry import register

LEVELS = {"easy": 0.92, "medium": 0.82, "hard": 0.68}
MAX_PUMPS = 60


@register
class PumpGame(BaseGame):
    key = "pump"
    name = "Pump"
    emoji = "🎈"
    category = "risk"
    multi_step = True
    order = 32
    rules_text = (
        "Pump the balloon one step at a time. Every pump raises your multiplier but adds "
        "pressure. Pop it and you lose everything — cash out before that happens."
    )

    def quick_starts(self) -> list[Starter]:
        return [
            Starter(f"🎈 {risk.title()} · {1 / p:.2f}x per pump", {"difficulty": risk})
            for risk, p in LEVELS.items()
        ]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        difficulty = str(raw.get("difficulty", "medium")).lower()
        if difficulty not in LEVELS:
            raise GameError("Unknown difficulty.")
        return {"difficulty": difficulty}

    def _factor(self, difficulty: str) -> float:
        return 1 / LEVELS[difficulty]  # edge is applied once at cash-out

    def _screen(self, state: dict) -> str:
        pumps = int(state["pumps"])
        mult = float(state["multiplier"])
        size = "🎈" if pumps < 5 else "🎈💨"
        return (
            f"🎈 <b>Pump</b> · {state['difficulty'].title()}\n"
            f"Pumps: {pumps} · multiplier <b>{mult:.2f}x</b>\n"
            f"Next pump: <b>{mult * self._factor(state['difficulty']):.2f}x</b> {size}"
        )

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        state = {
            "difficulty": params["difficulty"],
            "pumps": 0,
            "multiplier": 1.0,
            "screen": "",
        }
        text = self._screen(state)
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=1.0,
            text=text + "\n\nPump or cash out?",
            state=state,
            buttons=[[Button("💨 Pump", "pump")], [cashout_button(1.0)]],
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action == "cashout":
            raw = float(state["multiplier"])
            m = round(raw * (1 - self.edge), 4) if raw > 1 else 1.0
            return Round(
                finished=True,
                multiplier=m,
                status="CASHED_OUT",
                text=f"💰 Cashed out the balloon after {int(state['pumps'])} pumps at <b>{m:.2f}x</b>.",
                detail={"pumps": state["pumps"]},
            )
        if action != "pump":
            raise GameError("Unknown action.")
        pumps = int(state["pumps"])
        if pumps >= MAX_PUMPS:
            raise GameError("The balloon is at its limit — cash out.")
        p = LEVELS[state["difficulty"]]
        if rng.next() >= p:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=f"💥 <b>POP!</b> The balloon burst after {pumps} pumps. Lost.",
                detail={"pumps": pumps, "popped": True},
            )
        multiplier = round(float(state["multiplier"]) * self._factor(state["difficulty"]), 4)
        pumps += 1
        state = {**state, "pumps": pumps, "multiplier": multiplier}
        if pumps >= MAX_PUMPS:
            paid = round(multiplier * (1 - self.edge), 4) if multiplier > 1 else 1.0
            return Round(
                finished=True,
                multiplier=paid,
                status="CASHED_OUT",
                text=f"🏆 Maximum pressure reached — paid <b>{paid:.2f}x</b>.",
                detail={"pumps": pumps, "max": True},
            )
        text = self._screen(state)
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=multiplier,
            text=text + "\n\nPump or cash out?",
            state=state,
            buttons=[[Button("💨 Pump", "pump")], [cashout_button(multiplier)]],
            detail={"pumps": pumps},
        )

    def view(self, state: dict) -> Round:
        m = float(state.get("multiplier", 1.0))
        return Round(
            finished=False,
            multiplier=m,
            text=state.get("screen", "") + "\n\nPump or cash out?",
            state=state,
            buttons=[[Button("💨 Pump", "pump")], [cashout_button(m)]],
        )

    def auto_settle(self, state: dict) -> Round:
        raw = float(state.get("multiplier", 0.0))
        m = round(raw * (1 - self.edge), 4) if raw > 1 else raw
        return Round(
            finished=True,
            multiplier=m,
            status="CASHED_OUT",
            text=f"⏰ Round timed out — auto-cashed-out at <b>{m:.2f}x</b>.",
            detail={"auto": True},
        )

    def theoretical_rtp(self) -> float:
        return 1 - self.edge
