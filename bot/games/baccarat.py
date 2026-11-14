from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["♠", "♥", "♦", "♣"]


def card_value(rank: str) -> int:
    if rank in ("10", "J", "Q", "K"):
        return 0
    if rank == "A":
        return 1
    return int(rank)


def total(cards: list[list]) -> int:
    return sum(card_value(str(c[0])) for c in cards) % 10


def card_text(card: list) -> str:
    return f"{card[0]}{card[1]}"


def show(cards: list[list]) -> str:
    return " ".join(card_text(c) for c in cards)


@register
class BaccaratGame(BaseGame):
    key = "baccarat"
    name = "Baccarat"
    emoji = "🃏"
    category = "cards"
    order = 41
    rules_text = (
        "Bet on Player, Banker or Tie. Standard third-card rules apply. Banker wins pay 0.95x "
        "(5% commission); Tie pays 8:1."
    )

    def quick_starts(self) -> list[Starter]:
        return [
            Starter("👤 Player · 1:1", {"bet": "player"}),
            Starter("🏦 Banker · 0.95:1", {"bet": "banker"}),
            Starter("🤝 Tie · 8:1", {"bet": "tie"}),
        ]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        bet = str(raw.get("bet", "player")).lower()
        if bet not in ("player", "banker", "tie"):
            raise GameError("Bet on player, banker or tie.")
        return {"bet": bet}

    def _third_card(self, banker: list[list], player_third: list | None) -> bool:
        value = total(banker)
        if player_third is None:
            return value <= 5
        t = card_value(str(player_third[0]))
        if value <= 2:
            return True
        if value == 3:
            return t != 8
        if value == 4:
            return 2 <= t <= 7
        if value == 5:
            return 4 <= t <= 7
        if value == 6:
            return t in (6, 7)
        return False

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        deck = rng.shuffle([[rank, suit] for _ in range(8) for rank in RANKS for suit in SUITS])
        player = [deck.pop(), deck.pop()]
        banker = [deck.pop(), deck.pop()]
        player_third = None
        banker_third = None
        p_total, b_total = total(player), total(banker)
        if p_total < 8 and b_total < 8:
            if p_total <= 5:
                player_third = deck.pop()
                player.append(player_third)
            if self._third_card(banker, player_third):
                banker_third = deck.pop()
                banker.append(banker_third)
        p_total, b_total = total(player), total(banker)
        if p_total > b_total:
            winner = "player"
        elif b_total > p_total:
            winner = "banker"
        else:
            winner = "tie"
        bet = params["bet"]
        if bet == winner:
            multiplier = {"player": 2.0, "banker": 1.95, "tie": 9.0}[bet]
        elif winner == "tie" and bet in ("player", "banker"):
            multiplier = 1.0  # tie pushes Player and Banker bets
        else:
            multiplier = 0.0
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"🃏 <b>Player</b> {show(player)} = <b>{p_total}</b>\n"
                f"🃏 <b>Banker</b> {show(banker)} = <b>{b_total}</b>\n\n"
                f"Winner: <b>{winner.title()}</b>\n"
                f"Your bet: {bet.title()} · {'🟢 ' + f'{multiplier:.2f}x' if multiplier else '🔴 lost'}"
            ),
            detail={
                "player": player,
                "banker": banker,
                "player_total": p_total,
                "banker_total": b_total,
                "winner": winner,
                "player_third": player_third,
                "banker_third": banker_third,
            },
        )

    def theoretical_rtp(self) -> float:
        return 0.9894
