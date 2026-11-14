from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter, cashout_button
from bot.games.registry import register

LEVELS = {"easy": 0.95, "medium": 0.88, "hard": 0.75}
LANES = 20


@register
class ChickenGame(BaseGame):
    key = "chicken"
    name = "Chicken"
    emoji = "🐔"
    category = "risk"
    multi_step = True
    order = 33
    rules_text = (
        "Cross twenty lanes of traffic one at a time. Each lane raises your multiplier; "
        "getting hit ends the round. Cash out whenever you reach safety."
    )

    def quick_starts(self) -> list[Starter]:
        return [
            Starter(f"🐔 {risk.title()} · {1 / p:.2f}x per lane", {"difficulty": risk})
            for risk, p in LEVELS.items()
        ]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        difficulty = str(raw.get("difficulty", "medium")).lower()
        if difficulty not in LEVELS:
            raise GameError("Unknown difficulty.")
        return {"difficulty": difficulty}

    def _factor(self, difficulty: str) -> float:
        return 1 / LEVELS[difficulty]  # edge is applied once at cash-out

    def _road(self, state: dict) -> str:
        lane = int(state["lane"])
        cells = ["🐔" if i == lane else ("🏁" if i == LANES else "🛣️") for i in range(LANES + 1)]
        return "".join(cells)

    def _screen(self, state: dict) -> str:
        lane = int(state["lane"])
        mult = float(state["multiplier"])
        return (
            f"🐔 <b>Chicken</b> · {state['difficulty'].title()}\n"
            f"Lane {lane}/{LANES} · multiplier <b>{mult:.2f}x</b>\n"
            f"Next lane: <b>{mult * self._factor(state['difficulty']):.2f}x</b>\n\n"
            f"{self._road(state)}"
        )

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        state = {
            "difficulty": params["difficulty"],
            "lane": 0,
            "multiplier": 1.0,
            "screen": "",
        }
        text = self._screen(state)
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=1.0,
            text=text + "\n\nCross or cash out?",
            state=state,
            buttons=[[Button("🚦 Cross", "cross")], [cashout_button(1.0)]],
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action == "cashout":
            raw = float(state["multiplier"])
            m = round(raw * (1 - self.edge), 4) if raw > 1 else 1.0
            return Round(
                finished=True,
                multiplier=m,
                status="CASHED_OUT",
                text=f"💰 Cashed out after {int(state['lane'])} lanes at <b>{m:.2f}x</b>.",
                detail={"lane": state["lane"]},
            )
        if action != "cross":
            raise GameError("Unknown action.")
        lane = int(state["lane"])
        if lane >= LANES:
            raise GameError("You already crossed.")
        p = LEVELS[state["difficulty"]]
        if rng.next() >= p:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=f"🚗 <b>Splat!</b> Hit on lane {lane + 1}. Lost the {float(state['multiplier']):.2f}x.",
                detail={"lane": lane + 1, "hit": True},
            )
        multiplier = round(float(state["multiplier"]) * self._factor(state["difficulty"]), 4)
        lane += 1
        state = {**state, "lane": lane, "multiplier": multiplier}
        if lane >= LANES:
            paid = round(multiplier * (1 - self.edge), 4) if multiplier > 1 else 1.0
            return Round(
                finished=True,
                multiplier=paid,
                status="CASHED_OUT",
                text=f"🏁 <b>Made it across!</b> Paid <b>{paid:.2f}x</b>.",
                detail={"lane": lane, "cleared": True},
            )
        text = self._screen(state)
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=multiplier,
            text=text + "\n\nCross or cash out?",
            state=state,
            buttons=[[Button("🚦 Cross", "cross")], [cashout_button(multiplier)]],
            detail={"lane": lane},
        )

    def view(self, state: dict) -> Round:
        m = float(state.get("multiplier", 1.0))
        return Round(
            finished=False,
            multiplier=m,
            text=state.get("screen", "") + "\n\nCross or cash out?",
            state=state,
            buttons=[[Button("🚦 Cross", "cross")], [cashout_button(m)]],
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
