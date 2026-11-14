from __future__ import annotations

from collections import Counter

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter
from bot.games.registry import register

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["♠", "♥", "♦", "♣"]
PAYTABLE = {
    "royal_flush": 800.0,
    "straight_flush": 50.0,
    "four": 25.0,
    "full_house": 9.0,
    "flush": 6.0,
    "straight": 4.0,
    "three": 3.0,
    "two_pair": 2.0,
    "jacks": 1.0,
    "none": 0.0,
}
NAMES = {
    "royal_flush": "Royal flush",
    "straight_flush": "Straight flush",
    "four": "Four of a kind",
    "full_house": "Full house",
    "flush": "Flush",
    "straight": "Straight",
    "three": "Three of a kind",
    "two_pair": "Two pair",
    "jacks": "Jacks or better",
    "none": "No pair",
}


def card_text(card: list) -> str:
    return f"{card[0]}{card[1]}"


def evaluate(cards: list[list]) -> str:
    ranks = [str(c[0]) for c in cards]
    suits = [str(c[1]) for c in cards]
    counts = Counter(ranks)
    flush = len(set(suits)) == 1
    values = sorted(RANKS.index(r) for r in ranks)
    straight = values == list(range(values[0], values[0] + 5))
    if values == [0, 1, 2, 3, 12]:  # A-2-3-4-5
        straight = True
    if flush and set(ranks) == {"10", "J", "Q", "K", "A"}:
        return "royal_flush"
    if flush and straight:
        return "straight_flush"
    if 4 in counts.values():
        return "four"
    if 3 in counts.values() and 2 in counts.values():
        return "full_house"
    if flush:
        return "flush"
    if straight:
        return "straight"
    if 3 in counts.values():
        return "three"
    pairs = [r for r, c in counts.items() if c == 2]
    if len(pairs) == 2:
        return "two_pair"
    if len(pairs) == 1:
        high = all(RANKS.index(r) >= RANKS.index("J") for r in pairs)
        return "jacks" if high else "none"
    return "none"


@register
class VideoPokerGame(BaseGame):
    key = "videopoker"
    name = "Video Poker"
    emoji = "🃏"
    category = "cards"
    multi_step = True
    order = 43
    rules_text = (
        "Jacks or Better, 9/6 pay table. Hold any cards you like, then draw once. "
        "Royal flush pays 800x; jacks or better pays 1x."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter("🃏 Deal five cards", {})]

    def _keyboard(self, state: dict) -> list[list[Button]]:
        holds = state["holds"]
        row = []
        for i, card in enumerate(state["hand"]):
            mark = "🔒" if holds[i] else "▫️"
            row.append(Button(f"{mark}{card_text(card)}", "hold", str(i)))
        return [row, [Button("🔄 Draw", "draw")]]

    def _screen(self, state: dict) -> str:
        return (
            "🃏 <b>Video Poker</b> · Jacks or Better\n"
            f"Hand: {' '.join(card_text(c) for c in state['hand'])}\n"
            f"Holds: {' '.join('🔒' if h else '▫️' for h in state['holds'])}\n\n"
            "Tap a card to hold it, then draw."
        )

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        deck = rng.shuffle([[rank, suit] for rank in RANKS for suit in SUITS])
        hand = deck[:5]
        state = {"deck": deck, "index": 5, "hand": hand, "holds": [False] * 5}
        return Round(
            finished=False,
            multiplier=1.0,
            text=self._screen(state),
            state=state,
            buttons=self._keyboard(state),
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if action == "hold":
            try:
                idx = int(arg)
            except ValueError as exc:
                raise GameError("Invalid card.") from exc
            if not 0 <= idx < 5:
                raise GameError("Invalid card.")
            holds = list(state["holds"])
            holds[idx] = not holds[idx]
            state = {**state, "holds": holds}
            return Round(
                finished=False,
                multiplier=1.0,
                text=self._screen(state),
                state=state,
                buttons=self._keyboard(state),
            )
        if action != "draw":
            raise GameError("Unknown action.")
        deck = state["deck"]
        index = int(state["index"])
        hand = list(state["hand"])
        for i in range(5):
            if not state["holds"][i]:
                hand[i] = deck[index]
                index += 1
        category = evaluate(hand)
        multiplier = PAYTABLE[category]
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"🃏 <b>{' '.join(card_text(c) for c in hand)}</b>\n"
                f"{NAMES[category]}\n\n"
                f"{'🟢' if multiplier else '⚫'} {multiplier:,.2f}x"
            ),
            detail={"hand": hand, "category": category},
        )

    def view(self, state: dict) -> Round:
        return Round(
            finished=False,
            multiplier=1.0,
            text=self._screen(state),
            state=state,
            buttons=self._keyboard(state),
        )

    def auto_settle(self, state: dict) -> Round:
        return Round(
            finished=True,
            multiplier=0.0,
            status="LOST",
            text="⏰ Round timed out — the hand was forfeited.",
            detail={"auto": True, "forfeit": True},
        )

    def theoretical_rtp(self) -> float:
        return 0.9954
