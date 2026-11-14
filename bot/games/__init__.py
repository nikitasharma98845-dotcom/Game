from __future__ import annotations

# Importing a module registers its game. Add game #29 here and it appears everywhere.
from bot.games import (  # noqa: E402,F401
    baccarat,
    bars,
    blackjack,
    cases,
    chicken,
    crash,
    darts,
    diamonds,
    dice,
    dragon_tower,
    duel,
    flip,
    hilo,
    keno,
    limbo,
    mines,
    moles,
    plinko,
    pump,
    roulette,
    rps,
    sicbo,
    slide,
    slots,
    snakes,
    tarot,
    video_poker,
    wheel,
)
from bot.games.registry import CATEGORIES, REGISTRY, all_games, games_by_category, get_game

__all__ = [
    "CATEGORIES",
    "REGISTRY",
    "all_games",
    "games_by_category",
    "get_game",
]
