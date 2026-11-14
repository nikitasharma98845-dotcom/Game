from __future__ import annotations

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter
from bot.games.registry import register

PAYOUT = 2.0


@register
class CoinFlipGame(BaseGame):
    key = "coinflip"
    name = "Coin Flip"
    emoji = "🪙"
    category = "instant"
    multi_step = True
    order = 3
    rules_text = (
        "Call the coin. A correct call pays 1.98x. Before each extra flip you can cash "
        "out your current multiplier or let it ride for another 1.98x."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter("👑 Heads", {"choice": "heads"}), Starter("🦅 Tails", {"choice": "tails"})]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        from bot.core.errors import GameError

        choice = str(raw.get("choice", "heads")).lower()
        if choice not in ("heads", "tails"):
            raise GameError("Call heads or tails.")
        return {"choice": choice}

    def _flip(self, rng: FairRNG, choice: str) -> tuple[bool, str]:
        result = "heads" if rng.next() < 0.5 else "tails"
        return result == choice, result

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        won, result = self._flip(rng, params["choice"])
        if not won:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=f"🪙 The coin landed on <b>{result}</b>.\n🔴 You called {params['choice']}. Lost.",
                detail={"result": result},
            )
        multiplier = PAYOUT
        paid = round(multiplier * (1 - self.edge), 4)
        state = {
            "multiplier": multiplier,
            "choice": params["choice"],
            "streak": 1,
            "screen": f"🪙 <b>{result}</b> — correct! Streak: 1",
        }
        return Round(
            finished=False,
            multiplier=paid,
            text=state["screen"] + f"\n\nCurrent cash-out: <b>{paid:.2f}x</b>",
            state=state,
            buttons=[[Button(f"🪙 Flip again → {multiplier * PAYOUT:.2f}x", "flip")], [Button(f"💰 Cash out {paid:.2f}x", "cashout")]],
            detail={"result": result, "streak": 1},
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action == "cashout":
            paid = round(float(state["multiplier"]) * (1 - self.edge), 4)
            return Round(
                finished=True,
                multiplier=paid,
                status="CASHED_OUT",
                text=f"💰 Cashed out a {int(state['streak'])}-flip streak at <b>{paid:.2f}x</b>.",
                detail={"streak": state["streak"]},
            )
        if action != "flip":
            from bot.core.errors import GameError

            raise GameError("Unknown action.")
        won, result = self._flip(rng, state["choice"])
        if not won:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=f"🪙 <b>{result}</b> — wrong call. The streak of {state['streak']} is gone.",
                detail={"result": result, "streak": state["streak"]},
            )
        multiplier = round(float(state["multiplier"]) * PAYOUT, 4)
        paid = round(multiplier * (1 - self.edge), 4)
        streak = int(state["streak"]) + 1
        state = {
            "multiplier": multiplier,
            "choice": state["choice"],
            "streak": streak,
            "screen": f"🪙 <b>{result}</b> — correct! Streak: {streak}",
        }
        return Round(
            finished=False,
            multiplier=paid,
            text=state["screen"] + f"\n\nCurrent cash-out: <b>{paid:.2f}x</b>",
            state=state,
            buttons=[
                [Button(f"🪙 Flip again → {multiplier * PAYOUT:.2f}x", "flip")],
                [Button(f"💰 Cash out {paid:.2f}x", "cashout")],
            ],
            detail={"result": result, "streak": streak},
        )

    def view(self, state: dict) -> Round:
        m = float(state.get("multiplier", 1.0))
        paid = round(m * (1 - self.edge), 4) if m > 1 else 1.0
        return Round(
            finished=False,
            multiplier=paid,
            text=state.get("screen", "") + f"\n\nCurrent cash-out: <b>{paid:.2f}x</b>",
            state=state,
            buttons=[[Button(f"🪙 Flip again → {m * PAYOUT:.2f}x", "flip")], [Button(f"💰 Cash out {paid:.2f}x", "cashout")]],
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
        return 0.99
