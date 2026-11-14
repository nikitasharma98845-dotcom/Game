from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter, cashout_button
from bot.games.registry import register

LEVELS = {
    "easy": (4, 1),
    "medium": (3, 1),
    "hard": (2, 1),
    "expert": (3, 2),
    "master": (4, 3),
}
FLOORS = 9


def floor_factor(eggs: int, bad: int, edge: float = 0.01) -> float:
    safe = eggs - bad
    return eggs / safe  # edge is applied once at cash-out


@register
class DragonTowerGame(BaseGame):
    key = "dragontower"
    name = "Dragon Tower"
    emoji = "🐉"
    category = "risk"
    multi_step = True
    order = 31
    rules_text = (
        "Climb nine floors. On each floor pick an egg; one (or more) hides a dragon. Safe "
        "picks compound your multiplier, and you can cash out between floors."
    )

    def quick_starts(self) -> list[Starter]:
        out = []
        for key, (eggs, bad) in LEVELS.items():
            out.append(
                Starter(
                    f"🐉 {key.title()} · {eggs} eggs, {bad} bad · {floor_factor(eggs, bad):.2f}x/floor",
                    {"difficulty": key},
                )
            )
        return out

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        difficulty = str(raw.get("difficulty", "medium")).lower()
        if difficulty not in LEVELS:
            raise GameError("Unknown difficulty.")
        return {"difficulty": difficulty}

    def _eggs(self, state: dict) -> list[list[Button]]:
        eggs, _ = LEVELS[state["difficulty"]]
        floor = int(state["floor"])
        if floor >= FLOORS:
            return []
        row = [Button(f"🥚 {i + 1}", "pick", str(i)) for i in range(eggs)]
        return [row, [cashout_button(float(state["multiplier"]))]]

    def _screen(self, state: dict) -> str:
        floor = int(state["floor"])
        eggs, bad = LEVELS[state["difficulty"]]
        mult = float(state["multiplier"])
        return (
            f"🐉 <b>Dragon Tower</b> · {state['difficulty'].title()}\n"
            f"Floor {min(floor + 1, FLOORS)}/{FLOORS} · {eggs} eggs ({bad} dragon{'s' if bad > 1 else ''})\n"
            f"Multiplier: <b>{mult:.2f}x</b>"
        )

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        eggs, bad = LEVELS[params["difficulty"]]
        bad_positions = [rng.int(eggs) for _ in range(FLOORS)]
        state = {
            "difficulty": params["difficulty"],
            "floor": 0,
            "multiplier": 1.0,
            "bad": bad_positions,
            "eggs": eggs,
            "bad_count": bad,
            "screen": "",
        }
        text = self._screen(state)
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=1.0,
            text=text + "\n\nPick an egg 🥚",
            state=state,
            buttons=self._eggs(state),
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action == "cashout":
            m = float(state["multiplier"])
            paid = round(m * (1 - self.edge), 4) if m > 1 else 1.0
            return Round(
                finished=True,
                multiplier=paid,
                status="CASHED_OUT",
                text=f"💰 Cashed out at floor {int(state['floor'])} for <b>{paid:.2f}x</b>.",
                detail={"floor": state["floor"]},
            )
        if action != "pick":
            raise GameError("Unknown action.")
        try:
            choice = int(arg)
        except ValueError as exc:
            raise GameError("Invalid egg.") from exc
        floor = int(state["floor"])
        eggs = int(state["eggs"])
        bad = int(state["bad_count"])
        if not 0 <= choice < eggs:
            raise GameError("Invalid egg.")
        if floor >= FLOORS:
            raise GameError("The tower is already climbed.")
        if choice in self._bad_on_floor(state, floor):
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=(
                    f"🐉 <b>A dragon was in that egg!</b>\n"
                    f"Fell from floor {floor + 1}. Lost the {float(state['multiplier']):.2f}x multiplier."
                ),
                detail={"floor": floor, "bad": True},
            )
        factor = floor_factor(eggs, bad)
        multiplier = round(float(state["multiplier"]) * factor, 4)
        floor += 1
        state = {**state, "floor": floor, "multiplier": multiplier}
        if floor >= FLOORS:
            paid = round(multiplier * (1 - self.edge), 4) if multiplier > 1 else 1.0
            return Round(
                finished=True,
                multiplier=paid,
                status="CASHED_OUT",
                text=f"🏆 <b>Tower conquered!</b> Paid <b>{paid:.2f}x</b>.",
                detail={"floor": floor, "cleared": True},
            )
        text = self._screen(state)
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=multiplier,
            text=text + "\n\nPick an egg 🥚",
            state=state,
            buttons=self._eggs(state),
            detail={"floor": floor},
        )

    def _bad_on_floor(self, state: dict, floor: int) -> list[int]:
        eggs = int(state["eggs"])
        bad = int(state["bad_count"])
        start = int(state["bad"][floor])
        # rotate so the generated start index yields `bad` distinct bad eggs
        return [(start + i) % eggs for i in range(bad)]

    def view(self, state: dict) -> Round:
        return Round(
            finished=False,
            multiplier=float(state.get("multiplier", 1.0)),
            text=state.get("screen", ""),
            state=state,
            buttons=self._eggs(state),
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
