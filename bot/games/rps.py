from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter
from bot.games.registry import register

WIN_PAYOUT = 1.97
MOVES = {"rock": "✊ Rock", "paper": "✋ Paper", "scissors": "✌️ Scissors"}
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


@register
class RPSGame(BaseGame):
    key = "rps"
    name = "Rock Paper Scissors"
    emoji = "✊"
    category = "instant"
    multi_step = True
    order = 12
    rules_text = (
        "Play against the house. A win pays 1.97x, a loss takes the stake, and a draw lets "
        "you refund or continue the same round."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter(label, {"choice": key}) for key, label in MOVES.items()]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        choice = str(raw.get("choice", "rock")).lower()
        if choice not in MOVES:
            raise GameError("Choose rock, paper or scissors.")
        return {"choice": choice}

    def _round(self, rng: FairRNG, choice: str) -> tuple[str, str]:
        house = rng.shuffle(list(MOVES))[0] if rng.next() < 0.5 else list(MOVES)[rng.int(3)]
        return house, choice

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        choice = params["choice"]
        house = list(MOVES)[rng.int(3)]
        text = f"You {MOVES[choice]} · House {MOVES[house]}"
        if choice == house:
            return Round(
                finished=False,
                multiplier=1.0,
                text=f"✊ <b>Draw!</b>\n{text}\n\nRefund your stake or continue the round.",
                state={"choice": choice, "rounds": 1, "screen": f"✊ Draw! {text}"},
                buttons=[[Button("↩️ Refund", "refund")], [Button("🔁 Continue", "continue")]],
                detail={"house": house, "result": "draw"},
            )
        if BEATS[choice] == house:
            return Round(
                finished=True,
                multiplier=WIN_PAYOUT,
                status="WON",
                text=f"✊ <b>You win!</b>\n{text}\n\n🎉 {WIN_PAYOUT:.2f}x",
                detail={"house": house, "result": "win"},
            )
        return Round(
            finished=True,
            multiplier=0.0,
            status="LOST",
            text=f"✊ <b>House wins.</b>\n{text}\n\n🔴 Lost.",
            detail={"house": house, "result": "loss"},
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action == "refund":
            return Round(
                finished=True,
                multiplier=1.0,
                status="WON",
                text="↩️ Draw refunded — your stake is back.",
                detail={"result": "refund"},
            )
        if action != "continue":
            raise GameError("Unknown action.")
        choice = state["choice"]
        house = list(MOVES)[rng.int(3)]
        text = f"You {MOVES[choice]} · House {MOVES[house]}"
        if choice == house:
            rounds = int(state.get("rounds", 1)) + 1
            return Round(
                finished=False,
                multiplier=1.0,
                text=f"✊ <b>Draw again!</b>\n{text}\n\nRefund or continue.",
                state={"choice": choice, "rounds": rounds, "screen": f"✊ Draw! {text}"},
                buttons=[[Button("↩️ Refund", "refund")], [Button("🔁 Continue", "continue")]],
                detail={"house": house, "result": "draw"},
            )
        if BEATS[choice] == house:
            return Round(
                finished=True,
                multiplier=WIN_PAYOUT,
                status="WON",
                text=f"✊ <b>You win!</b>\n{text}\n\n🎉 {WIN_PAYOUT:.2f}x",
                detail={"house": house, "result": "win"},
            )
        return Round(
            finished=True,
            multiplier=0.0,
            status="LOST",
            text=f"✊ <b>House wins.</b>\n{text}\n\n🔴 Lost.",
            detail={"house": house, "result": "loss"},
        )

    def view(self, state: dict) -> Round:
        return Round(
            finished=False,
            multiplier=1.0,
            text=state.get("screen", "Draw — choose an option.") + "\n\nRefund or continue.",
            state=state,
            buttons=[[Button("↩️ Refund", "refund")], [Button("🔁 Continue", "continue")]],
        )

    def theoretical_rtp(self) -> float:
        return (WIN_PAYOUT + 1.0) / 3
