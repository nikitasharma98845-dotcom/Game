from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter, cashout_button
from bot.games.registry import register

LEVELS = {"easy": 0.10, "medium": 0.17, "hard": 0.25}
BOARD = 100


@register
class SnakesGame(BaseGame):
    key = "snakes"
    name = "Snakes"
    emoji = "🐍"
    category = "risk"
    multi_step = True
    order = 35
    rules_text = (
        "Roll two dice and move along a 100-tile board. Each safe roll grows your multiplier; "
        "land on a snake and the round is over. Cash out between rolls."
    )

    def quick_starts(self) -> list[Starter]:
        return [
            Starter(f"🐍 {risk.title()} · snake chance {p * 100:.0f}%", {"difficulty": risk})
            for risk, p in LEVELS.items()
        ]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        difficulty = str(raw.get("difficulty", "medium")).lower()
        if difficulty not in LEVELS:
            raise GameError("Unknown difficulty.")
        return {"difficulty": difficulty}

    def _factor(self, difficulty: str) -> float:
        return 1 / (1 - LEVELS[difficulty])  # edge is applied once at cash-out

    def _board(self, state: dict) -> str:
        pos = int(state["position"]) % BOARD
        step = BOARD // 20
        cells = []
        for i in range(0, BOARD, step):
            if i <= pos < i + step:
                cells.append("🐔")
            elif i < pos:
                cells.append("🟩")
            else:
                cells.append("⬜")
        return "".join(cells)

    def _screen(self, state: dict) -> str:
        mult = float(state["multiplier"])
        return (
            f"🐍 <b>Snakes</b> · {state['difficulty'].title()}\n"
            f"Tile {int(state['position']) % BOARD}/100 · rolls {int(state['rolls'])}\n"
            f"Multiplier: <b>{mult:.2f}x</b>"
        )

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        state = {
            "difficulty": params["difficulty"],
            "position": 0,
            "rolls": 0,
            "multiplier": 1.0,
            "screen": "",
        }
        text = self._screen(state)
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=1.0,
            text=text + "\n\nRoll or cash out?",
            state=state,
            buttons=[[Button("🎲 Roll", "roll")], [cashout_button(1.0)]],
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action == "cashout":
            raw = float(state["multiplier"])
            m = round(raw * (1 - self.edge), 4) if raw > 1 else 1.0
            return Round(
                finished=True,
                multiplier=m,
                status="CASHED_OUT",
                text=f"💰 Cashed out after {int(state['rolls'])} rolls at <b>{m:.2f}x</b>.",
                detail={"rolls": state["rolls"]},
            )
        if action != "roll":
            raise GameError("Unknown action.")
        d1 = rng.int(6) + 1
        d2 = rng.int(6) + 1
        roll = d1 + d2
        snake_chance = LEVELS[state["difficulty"]]
        if rng.next() < snake_chance:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=(
                    f"🐍 <b>A snake!</b> Rolled {roll} and landed on a snake.\n"
                    f"Lost the {float(state['multiplier']):.2f}x multiplier."
                ),
                detail={"roll": roll, "snake": True},
            )
        position = (int(state["position"]) + roll) % BOARD
        rolls = int(state["rolls"]) + 1
        multiplier = round(float(state["multiplier"]) * self._factor(state["difficulty"]), 4)
        state = {**state, "position": position, "rolls": rolls, "multiplier": multiplier}
        text = (
            f"🎲 Rolled <b>{d1} + {d2} = {roll}</b> — safe!\n"
            + self._screen(state)
            + f"\n\n{self._board(state)}"
        )
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=multiplier,
            text=text + "\n\nRoll or cash out?",
            state=state,
            buttons=[[Button("🎲 Roll", "roll")], [cashout_button(multiplier)]],
            detail={"roll": roll, "position": position},
        )

    def view(self, state: dict) -> Round:
        m = float(state.get("multiplier", 1.0))
        return Round(
            finished=False,
            multiplier=m,
            text=state.get("screen", "") + "\n\nRoll or cash out?",
            state=state,
            buttons=[[Button("🎲 Roll", "roll")], [cashout_button(m)]],
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
