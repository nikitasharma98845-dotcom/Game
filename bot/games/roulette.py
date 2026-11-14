from __future__ import annotations

import json

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register

RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
PAYS = {
    "straight": 35,
    "split": 17,
    "street": 11,
    "corner": 8,
    "line": 5,
    "dozen": 2,
    "column": 2,
    "color": 1,
    "parity": 1,
    "half": 1,
}
VALID_SIZES = {"straight": 1, "split": 2, "street": 3, "corner": 4, "line": 6}


def color_of(n: int) -> str:
    if n == 0:
        return "green"
    return "red" if n in RED else "black"


def bet_wins(kind: str, sel, number: int) -> bool:
    if number == 0:
        return kind == "straight" and 0 in sel
    if kind in VALID_SIZES:
        return number in sel
    if kind == "dozen":
        return (number - 1) // 12 + 1 == int(sel)
    if kind == "column":
        return (number - 1) % 3 + 1 == int(sel)
    if kind == "color":
        return color_of(number) == sel
    if kind == "parity":
        return number % 2 == (1 if sel == "odd" else 0)
    if kind == "half":
        return number <= 18 if sel == "low" else number >= 19
    return False


@register
class RouletteGame(BaseGame):
    key = "roulette"
    name = "Roulette"
    emoji = "🎡"
    category = "wheel"
    order = 21
    rules_text = (
        "European single-zero roulette. Build a bet slip with straight, split, street, corner, "
        "line, dozen, column, colour, odd/even and high/low bets, then spin. Zero loses every "
        "outside bet."
    )

    def quick_starts(self) -> list[Starter]:
        return [Starter("🎡 Open the bet slip", {})]

    def validate(self, raw: dict[str, str]) -> dict:
        raw_bets: object = raw.get("bets", [])
        if isinstance(raw_bets, str):
            try:
                raw_bets = json.loads(raw_bets)
            except json.JSONDecodeError as exc:
                raise GameError("Invalid bet slip.") from exc
        if not isinstance(raw_bets, list) or not raw_bets:
            raise GameError("Place at least one bet.")
        bets = []
        for entry in raw_bets:
            try:
                kind = str(entry["type"])
                amount = int(entry["amount"])
                sel = entry["sel"]
            except (KeyError, TypeError, ValueError) as exc:
                raise GameError("Invalid bet slip entry.") from exc
            if kind not in PAYS:
                raise GameError("Unknown roulette bet type.")
            if amount <= 0:
                raise GameError("Every bet must be positive.")
            if kind in VALID_SIZES:
                if not isinstance(sel, list) or len(sel) != VALID_SIZES[kind]:
                    raise GameError("Wrong amount of numbers for that bet.")
                sel = sorted({int(n) for n in sel})
                if any(not 0 <= n <= 36 for n in sel) or len(sel) != VALID_SIZES[kind]:
                    raise GameError("Invalid roulette numbers.")
            else:
                sel = str(sel).lower()
            bets.append({"type": kind, "sel": sel, "amount": amount})
        return {"bets": bets}

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        bets = params["bets"]
        total = sum(b["amount"] for b in bets)
        if total != stake:
            raise GameError("Bet slip total does not match the stake.")
        number = rng.int(37)
        returned = 0
        lines = []
        for entry in bets:
            kind, sel, amount = entry["type"], entry["sel"], entry["amount"]
            if bet_wins(kind, sel, number):
                won = amount * (PAYS[kind] + 1)
                returned += won
                lines.append(f"✅ {kind.title()} {sel} — <b>+{won / 100:,.2f}</b>")
            else:
                lines.append(f"➖ {kind.title()} {sel} — lost")
        multiplier = returned / stake if stake else 0.0
        colour = color_of(number)
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if returned > 0 else "LOST",
            text=(
                f"🎡 <b>{number} {colour}</b>\n\n"
                + "\n".join(lines)
                + f"\n\nReturn: <b>{returned / 100:,.2f} 🪙</b> ({multiplier:.2f}x)"
            ),
            detail={"number": number, "color": colour, "bets": bets, "returned": returned, "image": "roulette"},
        )

    def theoretical_rtp(self) -> float:
        return 36 / 37
