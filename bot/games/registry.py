from __future__ import annotations

from bot.games.base import BaseGame

REGISTRY: dict[str, BaseGame] = {}


def register(cls: type[BaseGame]) -> type[BaseGame]:
    instance = cls()
    if not instance.key:
        raise ValueError(f"{cls.__name__} has no key")
    REGISTRY[instance.key] = instance
    return cls


def get_game(key: str) -> BaseGame | None:
    return REGISTRY.get(key)


def all_games() -> list[BaseGame]:
    return sorted(REGISTRY.values(), key=lambda g: (g.category, g.order, g.name))


def games_by_category(category: str) -> list[BaseGame]:
    return [g for g in all_games() if g.category == category]


CATEGORIES: list[tuple[str, str]] = [
    ("instant", "🎲 Instant"),
    ("cards", "🃏 Cards"),
    ("risk", "💣 Risk / Cash-out"),
    ("wheel", "🎡 Wheel & Roulette"),
    ("slots", "🎰 Slots"),
    ("group", "👥 Group & Crash"),
]
