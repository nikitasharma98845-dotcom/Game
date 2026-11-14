from __future__ import annotations

import math

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter, cashout_button
from bot.games.registry import register
from bot.games.tables import comb

GRID = 25


def mines_multiplier(mines: int, revealed: int, edge: float = 0.01) -> float:
    if revealed <= 0:
        return 1.0
    p = comb(GRID - mines, revealed) / comb(GRID, revealed)
    if p <= 0:
        return 1.0
    return math.floor((1 - edge) / p * 10_000) / 10_000


@register
class MinesGame(BaseGame):
    key = "mines"
    name = "Mines"
    emoji = "💣"
    category = "risk"
    multi_step = True
    order = 30
    rules_text = (
        "A 5×5 board hides 1–24 mines. Reveal safe tiles to grow your multiplier and cash "
        "out whenever you like. One mine ends the round."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter(f"💣 {m} mine{'s' if m > 1 else ''}", {"mines": str(m)}) for m in (1, 3, 5, 10, 24)]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        try:
            mines = int(raw.get("mines", 3))
        except (TypeError, ValueError) as exc:
            raise GameError("Mines must be a whole number.") from exc
        if not 1 <= mines <= 24:
            raise GameError("Choose between 1 and 24 mines.")
        return {"mines": str(mines)}

    def _keyboard(self, state: dict) -> list[list[Button]]:
        revealed = set(state["revealed"])
        rows = []
        for r in range(5):
            row = []
            for c in range(5):
                idx = r * 5 + c
                if idx in revealed:
                    row.append(Button("💎", "noop"))
                else:
                    row.append(Button("⬜", "pick", str(idx)))
            rows.append(row)
        rows.append([cashout_button(float(state["multiplier"]))])
        return rows

    def _board(self, state: dict, reveal_mines: bool = False) -> str:
        revealed = set(state["revealed"])
        mines = set(state["mines"])
        cells = []
        for idx in range(GRID):
            if idx in revealed:
                cells.append("💎")
            elif reveal_mines and idx in mines:
                cells.append("💣")
            else:
                cells.append("⬜")
        return "\n".join("".join(cells[r * 5 : r * 5 + 5]) for r in range(5))

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        mines = int(params["mines"])
        picks = rng.shuffle(list(range(GRID)))[:mines]
        state = {
            "mines": picks,
            "revealed": [],
            "multiplier": 1.0,
            "mine_count": mines,
            "screen": "",
        }
        text = (
            f"💣 <b>Mines</b> · {mines} mine{'s' if mines > 1 else ''}\n"
            f"Next safe pick: <b>{mines_multiplier(mines, 1):.2f}x</b>\n\n"
            f"{self._board(state)}"
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
            raise GameError("That tile is already revealed.")
        if action == "cashout":
            m = float(state["multiplier"])
            return Round(
                finished=True,
                multiplier=m,
                status="CASHED_OUT",
                text=(
                    f"💰 <b>Cashed out at {m:.2f}x</b>\n"
                    f"{self._board(state)}\n"
                    f"Safe tiles revealed: {len(state['revealed'])}"
                ),
                detail={
                    "revealed": state["revealed"],
                    "mines": state["mines"],
                    "image": "mines",
                },
            )
        if action != "pick":
            raise GameError("Unknown action.")
        try:
            idx = int(arg)
        except ValueError as exc:
            raise GameError("Invalid tile.") from exc
        if idx in state["revealed"]:
            raise GameError("That tile is already revealed.")
        mine_count = int(state["mine_count"])
        if idx in state["mines"]:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=(
                    f"💥 <b>Boom — that was a mine.</b>\n"
                    f"{self._board(state, reveal_mines=True)}\n"
                    f"Lost after {len(state['revealed'])} safe tiles."
                ),
                detail={
                    "hit_mine": idx,
                    "revealed": state["revealed"],
                    "mines": state["mines"],
                    "reveal": True,
                    "image": "mines",
                },
            )
        revealed = list(state["revealed"]) + [idx]
        multiplier = mines_multiplier(mine_count, len(revealed))
        safe_left = GRID - mine_count - len(revealed)
        state = {
            **state,
            "revealed": revealed,
            "multiplier": multiplier,
        }
        if safe_left <= 0:
            return Round(
                finished=True,
                multiplier=multiplier,
                status="CASHED_OUT",
                text=(
                    f"🏆 <b>Board cleared at {multiplier:.2f}x!</b>\n"
                    f"{self._board(state)}\nEvery safe tile revealed."
                ),
                detail={"revealed": revealed, "mines": state["mines"], "image": "mines"},
            )
        text = (
            f"💣 <b>Mines</b> · {mine_count} mine{'s' if mine_count > 1 else ''}\n"
            f"Safe tiles: {len(revealed)} · current <b>{multiplier:.2f}x</b>\n"
            f"Next safe pick: <b>{mines_multiplier(mine_count, len(revealed) + 1):.2f}x</b>\n\n"
            f"{self._board(state)}"
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
