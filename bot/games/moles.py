from __future__ import annotations

import math

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter, cashout_button
from bot.games.registry import register
from bot.games.tables import comb

HOLES = 9
LEVELS = {"easy": 1, "medium": 2, "hard": 3}


def mole_multiplier(bombs: int, revealed: int, edge: float = 0.01) -> float:
    if revealed <= 0:
        return 1.0
    p = comb(HOLES - bombs, revealed) / comb(HOLES, revealed)
    if p <= 0:
        return 1.0
    return math.floor((1 - edge) / p * 10_000) / 10_000


@register
class MolesGame(BaseGame):
    key = "moles"
    name = "Moles"
    emoji = "🐹"
    category = "risk"
    multi_step = True
    order = 34
    rules_text = (
        "Whack-a-mole on a 3×3 grid. Some holes hide bombs. Every mole you whack raises the "
        "multiplier; a bomb ends the round. Cash out any time."
    )

    def quick_starts(self) -> list[Starter]:
        return [
            Starter(f"🐹 {risk.title()} · {bombs} bomb{'s' if bombs > 1 else ''}", {"difficulty": risk})
            for risk, bombs in LEVELS.items()
        ]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        difficulty = str(raw.get("difficulty", "medium")).lower()
        if difficulty not in LEVELS:
            raise GameError("Unknown difficulty.")
        return {"difficulty": difficulty}

    def _keyboard(self, state: dict) -> list[list[Button]]:
        revealed = set(state["revealed"])
        rows = []
        for r in range(3):
            row = []
            for c in range(3):
                idx = r * 3 + c
                row.append(Button("🐹" if idx in revealed else "🕳️", "noop" if idx in revealed else "pick", str(idx)))
            rows.append(row)
        rows.append([cashout_button(float(state["multiplier"]))])
        return rows

    def _board(self, state: dict, reveal: bool = False) -> str:
        revealed = set(state["revealed"])
        bombs = set(state["bombs"])
        cells = []
        for idx in range(HOLES):
            if idx in revealed:
                cells.append("🐹")
            elif reveal and idx in bombs:
                cells.append("💣")
            else:
                cells.append("🕳️")
        return "\n".join("".join(cells[r * 3 : r * 3 + 3]) for r in range(3))

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        bombs = LEVELS[params["difficulty"]]
        positions = rng.shuffle(list(range(HOLES)))[:bombs]
        state = {
            "difficulty": params["difficulty"],
            "bombs": positions,
            "revealed": [],
            "multiplier": 1.0,
            "bomb_count": bombs,
            "screen": "",
        }
        text = (
            f"🐹 <b>Moles</b> · {bombs} bomb{'s' if bombs > 1 else ''}\n"
            f"Next mole: <b>{mole_multiplier(bombs, 1):.2f}x</b>\n\n{self._board(state)}"
        )
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=1.0,
            text=text,
            state=state,
            buttons=self._keyboard(state),
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action == "noop":
            raise GameError("You already whacked that hole.")
        if action == "cashout":
            m = float(state["multiplier"])
            return Round(
                finished=True,
                multiplier=m,
                status="CASHED_OUT",
                text=f"💰 Cashed out at {m:.2f}x\n{self._board(state)}",
                detail={"revealed": state["revealed"]},
            )
        if action != "pick":
            raise GameError("Unknown action.")
        try:
            idx = int(arg)
        except ValueError as exc:
            raise GameError("Invalid hole.") from exc
        if idx in state["revealed"]:
            raise GameError("You already whacked that hole.")
        bombs = int(state["bomb_count"])
        if idx in state["bombs"]:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=f"💥 <b>Bomb!</b> Lost after {len(state['revealed'])} moles.\n{self._board(state, reveal=True)}",
                detail={"bomb": idx},
            )
        revealed = list(state["revealed"]) + [idx]
        multiplier = mole_multiplier(bombs, len(revealed))
        left = HOLES - bombs - len(revealed)
        state = {**state, "revealed": revealed, "multiplier": multiplier}
        if left <= 0:
            return Round(
                finished=True,
                multiplier=multiplier,
                status="CASHED_OUT",
                text=f"🏆 All moles whacked! Paid <b>{multiplier:.2f}x</b>.\n{self._board(state)}",
                detail={"revealed": revealed},
            )
        text = (
            f"🐹 <b>Moles</b> · {bombs} bomb{'s' if bombs > 1 else ''}\n"
            f"Moles: {len(revealed)} · <b>{multiplier:.2f}x</b>\n"
            f"Next mole: <b>{mole_multiplier(bombs, len(revealed) + 1):.2f}x</b>\n\n{self._board(state)}"
        )
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=multiplier,
            text=text,
            state=state,
            buttons=self._keyboard(state),
            detail={"revealed": revealed},
        )

    def view(self, state: dict) -> Round:
        return Round(
            finished=False,
            multiplier=float(state.get("multiplier", 1.0)),
            text=state.get("screen", ""),
            state=state,
            buttons=self._keyboard(state),
        )

    def auto_settle(self, state: dict) -> Round:
        m = float(state.get("multiplier", 0.0))
        return Round(
            finished=True,
            multiplier=m,
            status="CASHED_OUT",
            text=f"⏰ Round timed out — auto-cashed-out at <b>{m:.2f}x</b>.",
            detail={"auto": True},
        )

    def theoretical_rtp(self) -> float:
        return 0.99 - 0.0001
