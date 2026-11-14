from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round
from bot.games.registry import register

FEE = 0.01


@register
class DiceDuelGame(BaseGame):
    key = "duel"
    name = "Dice Duel"
    emoji = "⚔️"
    category = "group"
    order = 61
    rules_text = (
        "Two players stake equal Chips. Each rolls a fair dice roll; the higher roll takes "
        "the pot minus a 1% fee that is burned. Ties refund both players. Start with "
        "/duel <bet> in a group and a friend taps Accept."
    )

    def validate(self, params: dict[str, str]) -> dict[str, str]:
        return dict(params)

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        raise GameError("Dice Duel is started with /duel in a group.")

    def theoretical_rtp(self) -> float:
        return 0.99
