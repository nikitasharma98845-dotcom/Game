from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Button, Round, Starter
from bot.games.registry import register

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["♠", "♥", "♦", "♣"]
DECKS = 8


def card_value(rank: str) -> int:
    if rank in ("10", "J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def hand_value(cards: list[list]) -> tuple[int, bool]:
    total = 0
    aces = 0
    for card in cards:
        total += card_value(str(card[0]))
        if str(card[0]) == "A":
            aces += 1
    soft = aces > 0
    while total > 21 and aces:
        total -= 10
        aces -= 1
        soft = aces > 0
    return total, soft


def card_text(card: list) -> str:
    return f"{card[0]}{card[1]}"


def show(cards: list[list]) -> str:
    return " ".join(card_text(c) for c in cards)


def is_blackjack(cards: list[list]) -> bool:
    return len(cards) == 2 and hand_value(cards)[0] == 21


def fresh_shoe(rng: FairRNG) -> list[list]:
    shoe = [[rank, suit] for _ in range(DECKS) for rank in RANKS for suit in SUITS]
    return rng.shuffle(shoe)


@register
class BlackjackGame(BaseGame):
    key = "blackjack"
    name = "Blackjack"
    emoji = "♠️"
    category = "cards"
    multi_step = True
    order = 42
    rules_text = (
        "Eight-deck blackjack. Dealer stands on soft 17. Blackjack pays 3:2, insurance pays "
        "2:1, double and split up to four hands are available. A split ace receives one card."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter("♠️ Deal a hand", {})]

    # ------------------------------------------------------------------ helpers
    def _can_double(self, hand: dict) -> bool:
        return len(hand["cards"]) == 2 and hand["status"] == "playing" and not hand["doubled"]

    def _can_split(self, state: dict, hand: dict) -> bool:
        if len(state["hands"]) >= 4 or len(hand["cards"]) != 2:
            return False
        if hand["status"] != "playing":
            return False
        return card_value(str(hand["cards"][0][0])) == card_value(str(hand["cards"][1][0]))

    def _buttons(self, state: dict) -> list[list[Button]]:
        if state["phase"] != "player":
            return []
        hand = state["hands"][int(state["active"])]
        rows = [[Button("👊 Hit", "hit"), Button("✋ Stand", "stand")]]
        extra = []
        if self._can_double(hand):
            extra.append(Button("💥 Double", "double"))
        if self._can_split(state, hand):
            extra.append(Button("✂️ Split", "split"))
        if extra:
            rows.append(extra)
        dealer_up = str(state["dealer"][0][0])
        if dealer_up == "A" and not state.get("insurance"):
            rows.append([Button("🛡 Insurance", "insurance")])
        return rows

    def _screen(self, state: dict, reveal: bool = False) -> str:
        dealer = state["dealer"]
        if reveal or state["phase"] != "player":
            dealer_line = f"{show(dealer)} = <b>{hand_value(dealer)[0]}</b>"
        else:
            dealer_line = f"{card_text(dealer[0])} 🂠"
        lines = [f"♠️ <b>Blackjack</b> · dealer: {dealer_line}", ""]
        for i, hand in enumerate(state["hands"]):
            value, soft = hand_value(hand["cards"])
            marker = "👉 " if i == int(state["active"]) and state["phase"] == "player" else ""
            status = f" · {hand['status']}" if hand["status"] != "playing" else ""
            lines.append(
                f"{marker}<b>Hand {i + 1}</b> {show(hand['cards'])} = <b>{value}</b>"
                f"{' (soft)' if soft else ''} · bet {hand['bet'] / 100:,.2f}{status}"
            )
        if state.get("insurance"):
            lines.append(f"🛡 Insurance: {state['insurance'] / 100:,.2f}")
        return "\n".join(lines)

    def _round_finished(self, state: dict, staked: int, returns: int, text: str, detail: dict | None = None) -> Round:
        multiplier = returns / staked if staked else 0.0
        return Round(
            finished=True,
            multiplier=round(multiplier, 4),
            status="WON" if returns > staked else ("CASHED_OUT" if returns >= staked else "LOST"),
            text=text,
            detail=detail or {},
        )

    def _resolve(self, state: dict) -> Round:
        dealer = state["dealer"]
        while True:
            value, soft = hand_value(dealer)
            if value < 17 or (value == 17 and soft):
                dealer.append(state["deck"].pop())
            else:
                break
        dealer_value = hand_value(dealer)[0]
        dealer_bj = is_blackjack(dealer)
        returns = 0
        lines = [self._screen(state, reveal=True), ""]
        for i, hand in enumerate(state["hands"]):
            value = hand_value(hand["cards"])[0]
            bet = int(hand["bet"])
            if value > 21:
                lines.append(f"Hand {i + 1}: bust 💥 — lost {bet / 100:,.2f}")
                continue
            if hand.get("blackjack"):
                won = int(bet * 2.5)
                returns += won
                lines.append(f"Hand {i + 1}: BLACKJACK 🎉 — {won / 100:,.2f}")
                continue
            if dealer_bj:
                lines.append(f"Hand {i + 1}: dealer blackjack 🂡 — lost {bet / 100:,.2f}")
                continue
            if dealer_value > 21:
                returns += bet * 2
                lines.append(f"Hand {i + 1}: dealer bust 🎉 — {bet * 2 / 100:,.2f}")
            elif value > dealer_value:
                returns += bet * 2
                lines.append(f"Hand {i + 1}: <b>{value}</b> beats {dealer_value} 🟢 — {bet * 2 / 100:,.2f}")
            elif value == dealer_value:
                returns += bet
                lines.append(f"Hand {i + 1}: push at {value} — {bet / 100:,.2f} returned")
            else:
                lines.append(f"Hand {i + 1}: <b>{value}</b> loses to {dealer_value} 🔴 — lost {bet / 100:,.2f}")
        if state.get("insurance"):
            if dealer_bj:
                insurance_return = int(state["insurance"]) * 3
                returns += insurance_return
                lines.append(f"🛡 Insurance paid {insurance_return / 100:,.2f}")
            else:
                lines.append("🛡 Insurance lost")
        staked = int(state["staked"])
        lines.append(f"\nReturned: <b>{returns / 100:,.2f} 🪙</b>")
        return self._round_finished(state, staked, returns, "\n".join(lines), {"dealer": dealer, "returns": returns})

    def _advance(self, state: dict) -> Round | None:
        for i, hand in enumerate(state["hands"]):
            if hand["status"] == "playing":
                state["active"] = i
                return None
        state["phase"] = "dealer"
        return self._resolve(state)

    def _active(self, state: dict) -> dict:
        return state["hands"][int(state["active"])]

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        deck = fresh_shoe(rng)
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]
        hand = {
            "cards": player,
            "bet": stake,
            "status": "playing",
            "doubled": False,
            "blackjack": is_blackjack(player),
        }
        state = {
            "deck": deck,
            "hands": [hand],
            "dealer": dealer,
            "active": 0,
            "staked": stake,
            "insurance": 0,
            "phase": "player",
        }
        player_bj = hand["blackjack"]
        dealer_bj = is_blackjack(dealer)
        if player_bj and dealer_bj:
            return self._round_finished(
                state, stake, stake, "🤝 <b>Both blackjack — push.</b>\nYour stake is returned."
            )
        if player_bj:
            return self._round_finished(
                state, stake, int(stake * 2.5), "🎉 <b>Blackjack!</b> Pays 3:2."
            )
        if dealer_bj:
            return self._round_finished(state, stake, 0, "🂡 <b>Dealer blackjack.</b> Lost.")
        text = self._screen(state) + "\n\nHit, stand, double or split."
        return Round(
            finished=False,
            multiplier=1.0,
            text=text,
            state=state,
            buttons=self._buttons(state),
        )

    def step(self, state: dict, action: str, arg: str, rng: FairRNG) -> Round:
        if state["phase"] != "player":
            raise GameError("The hand is already over.")
        hand = self._active(state)
        extra = 0
        if action == "hit":
            hand["cards"].append(state["deck"].pop())
            value = hand_value(hand["cards"])[0]
            if value > 21:
                hand["status"] = "bust"
            elif value == 21:
                hand["status"] = "stand"
        elif action == "stand":
            hand["status"] = "stand"
        elif action == "double":
            if not self._can_double(hand):
                raise GameError("You cannot double now.")
            extra = int(hand["bet"])
            hand["bet"] = int(hand["bet"]) * 2
            hand["doubled"] = True
            state["staked"] = int(state["staked"]) + extra
            hand["cards"].append(state["deck"].pop())
            if hand_value(hand["cards"])[0] > 21:
                hand["status"] = "bust"
            else:
                hand["status"] = "stand"
        elif action == "split":
            if not self._can_split(state, hand):
                raise GameError("You cannot split this hand.")
            extra = int(hand["bet"])
            state["staked"] = int(state["staked"]) + extra
            first = hand["cards"][0]
            second = hand["cards"][1]
            aces = str(first[0]) == "A"
            hand["cards"] = [first, state["deck"].pop()]
            hand["blackjack"] = False
            new_hand = {
                "cards": [second, state["deck"].pop()],
                "bet": int(hand["bet"]),
                "status": "stand" if aces else "playing",
                "doubled": False,
                "blackjack": False,
            }
            if aces:
                hand["status"] = "stand"
            state["hands"].insert(int(state["active"]) + 1, new_hand)
        elif action == "insurance":
            dealer_up = str(state["dealer"][0][0])
            if dealer_up != "A" or state.get("insurance"):
                raise GameError("Insurance is not available.")
            extra = max(1, int(state["hands"][0]["bet"]) // 2)
            state["insurance"] = extra
            state["staked"] = int(state["staked"]) + extra
        else:
            raise GameError("Unknown action.")

        # communicated to BetEngine which debits the extra stake atomically
        extra_marker = extra or 0

        finished = self._advance(state)
        if finished is not None:
            finished.detail["_extra_stake"] = extra_marker
            return finished
        return Round(
            finished=False,
            multiplier=1.0,
            text=self._screen(state) + "\n\nHit, stand or cash out?",
            state=state,
            buttons=self._buttons(state),
            detail={"_extra_stake": extra_marker},
        )

    def view(self, state: dict) -> Round:
        return Round(
            finished=False,
            multiplier=1.0,
            text=self._screen(state) + "\n\nYour move.",
            state=state,
            buttons=self._buttons(state),
        )

    def auto_settle(self, state: dict) -> Round:
        return Round(
            finished=True,
            multiplier=0.0,
            status="LOST",
            text="⏰ Round timed out — the hand was forfeited (all stakes lost).",
            detail={"auto": True, "forfeit": True},
        )

    def theoretical_rtp(self) -> float:
        return 0.9954
