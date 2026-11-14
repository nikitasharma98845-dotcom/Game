from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter, cashout_button
from bot.games.registry import register

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["♠", "♥", "♦", "♣"]


def fresh_deck() -> list[list]:
    return [[rank, suit] for rank in RANKS for suit in SUITS]


def rank_of(card: list) -> str:
    return str(card[0])


def card_text(card: list) -> str:
    return f"{card[0]}{card[1]}"


def rank_index(rank: str) -> int:
    return RANKS.index(rank)


@register
class HiLoGame(BaseGame):
    key = "hilo"
    name = "HiLo"
    emoji = "🃏"
    category = "cards"
    multi_step = True
    order = 40
    rules_text = (
        "A card is shown. Guess whether the next card is higher, lower or the same. Each "
        "correct guess compounds your multiplier at fair odds. Cash out any time."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter("🃏 Deal a card", {})]

    def _chances(self, deck: list[list], index: int, card: list) -> dict[str, tuple[int, float]]:
        remaining = deck[index:]
        base = rank_index(str(card[0]))
        higher = sum(1 for c in remaining if rank_index(str(c[0])) > base)
        lower = sum(1 for c in remaining if rank_index(str(c[0])) < base)
        same = sum(1 for c in remaining if rank_index(str(c[0])) == base)
        total = max(1, len(remaining))
        return {
            "higher": (higher, higher / total),
            "lower": (lower, lower / total),
            "same": (same, same / total),
        }

    def _buttons(self, state: dict) -> list[list[Button]]:
        chances = self._chances(state["deck"], int(state["index"]), state["card"])
        mult = float(state["multiplier"])
        rows = []
        for action in ("higher", "lower", "same"):
            count, p = chances[action]
            if count == 0 or p <= 0:
                continue
            rows.append([Button(f"{action.title()} → {mult / p:,.2f}x", action)])
        rows.append([cashout_button(mult)])
        return rows

    def _screen(self, state: dict) -> str:
        mult = float(state["multiplier"])
        return (
            f"🃏 <b>Current card: {card_text(state['card'])}</b>\n"
            f"Cards seen: {int(state['index'])}\n"
            f"Multiplier so far: <b>{mult:.2f}x</b>"
        )

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        deck = rng.shuffle(fresh_deck())
        card = deck[0]
        state = {"deck": deck, "index": 1, "card": card, "multiplier": 1.0, "screen": ""}
        text = self._screen(state)
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=1.0,
            text=text + "\n\nHigher, lower, or the same?",
            state=state,
            buttons=self._buttons(state),
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        mult = float(state["multiplier"])
        if action == "cashout":
            paid = round(mult * (1 - self.edge), 4) if mult > 1 else 1.0
            return Round(
                finished=True,
                multiplier=paid,
                status="CASHED_OUT",
                text=f"💰 Cashed out at <b>{paid:.2f}x</b> after {int(state['index']) - 1} correct guesses.",
                detail={"cashout": mult},
            )
        if action not in ("higher", "lower", "same"):
            raise GameError("Unknown action.")
        chances = self._chances(state["deck"], int(state["index"]), state["card"])
        count, p = chances[action]
        if count == 0 or p <= 0:
            raise GameError("No card left can win that guess.")
        deck = state["deck"]
        index = int(state["index"])
        next_card = deck[index]
        base = rank_index(str(state["card"][0]))
        nxt = rank_index(str(next_card[0]))
        won = {"higher": nxt > base, "lower": nxt < base, "same": nxt == base}[action]
        if not won:
            return Round(
                finished=True,
                multiplier=0.0,
                status="LOST",
                text=(
                    f"🃏 <b>{card_text(next_card)}</b> — wrong.\n"
                    f"You guessed {action} against {card_text(state['card'])}.\n"
                    f"Lost the {mult:.2f}x multiplier."
                ),
                detail={"next": next_card, "guess": action},
            )
        multiplier = round(mult / p, 4)
        index += 1
        if index >= len(deck):
            paid = round(multiplier * (1 - self.edge), 4)
            return Round(
                finished=True,
                multiplier=paid,
                status="CASHED_OUT",
                text=f"🃏 Deck exhausted — paid <b>{paid:.2f}x</b>.",
                detail={"next": next_card, "deck_end": True},
            )
        state = {
            "deck": deck,
            "index": index,
            "card": next_card,
            "multiplier": multiplier,
        }
        text = (
            f"🃏 <b>{card_text(next_card)}</b> — correct!\n"
            f"Cards seen: {index}\n"
            f"Multiplier: <b>{multiplier:.2f}x</b>"
        )
        state["screen"] = text
        return Round(
            finished=False,
            multiplier=multiplier,
            text=text + "\n\nHigher, lower, or cash out?",
            state=state,
            buttons=self._buttons(state),
            detail={"next": next_card, "guess": action},
        )

    def view(self, state: dict) -> Round:
        return Round(
            finished=False,
            multiplier=float(state.get("multiplier", 1.0)),
            text=state.get("screen", "") + "\n\nHigher, lower, or cash out?",
            state=state,
            buttons=self._buttons(state),
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
