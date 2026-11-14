from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register
from bot.games.tables import binomial

PAYLINES = [
    (1, 1, 1, 1, 1),
    (0, 0, 0, 0, 0),
    (2, 2, 2, 2, 2),
    (0, 1, 2, 1, 0),
    (2, 1, 0, 1, 2),
    (0, 0, 1, 2, 2),
    (2, 2, 1, 0, 0),
    (1, 0, 1, 0, 1),
    (1, 2, 1, 2, 1),
    (0, 1, 0, 1, 0),
]
FREE_SPINS = 10
SCATTER_CELLS = 15


@dataclass(frozen=True)
class Symbol:
    emoji: str
    weight: int
    pays: tuple[float, float, float]  # 3, 4, 5 of a kind on a line


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    emoji: str
    symbols: tuple[Symbol, ...]
    scatter: str
    scatter_weight: int


THEMES: tuple[Theme, ...] = (
    Theme(
        "pharaoh",
        "Pharaoh Spin",
        "🐫",
        (
            Symbol("🐫", 2, (2.5, 8.0, 25.0)),
            Symbol("🦅", 4, (1.2, 4.0, 12.0)),
            Symbol("🐍", 7, (0.6, 2.0, 6.0)),
            Symbol("🐈‍⬛", 10, (0.4, 1.2, 4.0)),
            Symbol("🏺", 13, (0.25, 0.8, 2.5)),
            Symbol("👁️", 16, (0.15, 0.5, 1.5)),
        ),
        "⚱️",
        2,
    ),
    Theme(
        "ronin",
        "Ronin Reels",
        "⚔️",
        (
            Symbol("🐉", 2, (2.6, 8.5, 26.0)),
            Symbol("🏯", 4, (1.3, 4.2, 12.0)),
            Symbol("🗡️", 7, (0.65, 2.1, 6.2)),
            Symbol("🥋", 10, (0.4, 1.25, 4.0)),
            Symbol("🀄", 13, (0.24, 0.75, 2.4)),
            Symbol("🌸", 16, (0.14, 0.48, 1.5)),
        ),
        "⛩️",
        2,
    ),
    Theme(
        "spell",
        "Spell Book",
        "🔮",
        (
            Symbol("🦉", 2, (2.4, 7.8, 24.0)),
            Symbol("🧪", 4, (1.2, 3.9, 11.5)),
            Symbol("📖", 7, (0.6, 1.95, 5.8)),
            Symbol("🕯️", 10, (0.38, 1.15, 3.8)),
            Symbol("🌙", 13, (0.23, 0.72, 2.3)),
            Symbol("✨", 16, (0.14, 0.46, 1.45)),
        ),
        "🔮",
        2,
    ),
)


def _scatter_probability(theme: Theme) -> float:
    total = sum(s.weight for s in theme.symbols) + theme.scatter_weight
    return theme.scatter_weight / total


@lru_cache(maxsize=8)
def theme_tables(theme_key: str) -> tuple[dict[str, tuple[float, ...]], float, float]:
    theme = next(t for t in THEMES if t.key == theme_key)
    total = sum(s.weight for s in theme.symbols) + theme.scatter_weight
    line_ev = 0.0
    for sym in theme.symbols:
        p = sym.weight / total
        p3, p4, p5 = sym.pays
        line_ev += p**3 * p3 * (1 - p) + p**4 * p4 * (1 - p) + p**5 * p5
    line_ev *= len(PAYLINES)
    q = _scatter_probability(theme)
    trigger = sum(binomial(SCATTER_CELLS, k, q) for k in range(3, SCATTER_CELLS + 1))
    expected_free = trigger * (FREE_SPINS / (1 - FREE_SPINS * trigger)) if FREE_SPINS * trigger < 1 else 0.0
    factor = 0.99 / (line_ev * (1 + expected_free))
    pays = {
        s.emoji: tuple(round(v * factor, 2) for v in s.pays)  # type: ignore[misc]
        for s in theme.symbols
    }
    # RTP with the rounded paytable
    line_ev2 = 0.0
    for sym in theme.symbols:
        p = sym.weight / total
        p3, p4, p5 = pays[sym.emoji]
        line_ev2 += p**3 * p3 * (1 - p) + p**4 * p4 * (1 - p) + p**5 * p5
    line_ev2 *= len(PAYLINES)
    return pays, trigger, line_ev2 * (1 + expected_free)


class _SlotBase(BaseGame):
    theme_key = ""
    category = "slots"
    rules_text = (
        "5×3 reels with 10 paylines. Three or more matching symbols from the left pay. "
        "Three or more scatters award 10 free spins, which can retrigger."
    )

    @property
    def theme(self) -> Theme:
        return next(t for t in THEMES if t.key == self.theme_key)

    def quick_starts(self) -> list[Starter]:
        return [Starter(f"{self.theme.emoji} Spin", {})]

    def _grid(self, rng: FairRNG) -> list[list[str]]:
        theme = self.theme
        pool = []
        for sym in theme.symbols:
            pool.extend([sym.emoji] * sym.weight)
        pool.extend([theme.scatter] * theme.scatter_weight)
        return [[pool[rng.int(len(pool))] for _ in range(3)] for _ in range(5)]

    def _spin_wins(self, grid: list[list[str]]) -> tuple[float, list[str]]:
        pays, _, _ = theme_tables(self.theme_key)
        total = 0.0
        wins = []
        for line in PAYLINES:
            symbols = [grid[col][row] for col, row in enumerate(line)]
            first = symbols[0]
            if first not in pays:
                continue
            count = 1
            for s in symbols[1:]:
                if s != first:
                    break
                count += 1
            if count < 3:
                continue
            pay = pays[first][count - 3]
            if pay <= 0:
                continue
            total += pay
            wins.append(f"{first}×{count} → {pay:.2f}x")
        return total, wins

    def _scatters(self, grid: list[list[str]]) -> int:
        return sum(1 for col in grid for s in col if s == self.theme.scatter)

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        theme = self.theme
        grid = self._grid(rng)
        base_win, wins = self._spin_wins(grid)
        scatters = self._scatters(grid)
        free_spins = 0
        free_win = 0.0
        retriggers = 0
        if scatters >= 3:
            free_spins = FREE_SPINS
            played = 0
            while played < free_spins and played < 120:
                fgrid = self._grid(rng)
                win, _ = self._spin_wins(fgrid)
                free_win += win
                played += 1
                if self._scatters(fgrid) >= 3 and retriggers < 3:
                    free_spins += FREE_SPINS
                    retriggers += 1
        total = round(base_win + free_win, 2)
        rows = [
            "  ".join(grid[col][row] for col in range(5))
            for row in range(3)
        ]
        body = "\n".join(rows)
        extra = []
        if scatters >= 3:
            extra.append(
                f"⭐ {scatters} scatters → {free_spins} free spins"
                + (f" (+{retriggers} retrigger)" if retriggers else "")
                + f" · free-spin win {free_win:.2f}x"
            )
        if wins:
            extra.append("Paylines: " + ", ".join(wins[:6]))
        text = (
            f"{theme.emoji} <b>{theme.name}</b>\n\n<code>{body}</code>\n\n"
            + ("\n".join(extra) if extra else "No win this spin.")
            + f"\n\nTotal: <b>{total:.2f}x</b>"
        )
        return Round(
            finished=True,
            multiplier=total,
            status="WON" if total > 0 else "LOST",
            text=text,
            detail={
                "grid": grid,
                "scatters": scatters,
                "free_spins": free_spins,
                "free_win": free_win,
                "lines": wins,
            },
        )

    def theoretical_rtp(self) -> float:
        return theme_tables(self.theme_key)[2]


@register
class PharaohSpin(_SlotBase):
    key = "pharaoh"
    name = "Pharaoh Spin"
    emoji = "🐫"
    theme_key = "pharaoh"
    order = 50


@register
class RoninReels(_SlotBase):
    key = "ronin"
    name = "Ronin Reels"
    emoji = "⚔️"
    theme_key = "ronin"
    order = 51


@register
class SpellBook(_SlotBase):
    key = "spellbook"
    name = "Spell Book"
    emoji = "🔮"
    theme_key = "spell"
    order = 52
