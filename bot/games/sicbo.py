from __future__ import annotations

from bot.core.errors import GameError
from bot.core.fairness import FairRNG
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register

FACES = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
TOTAL_PAYS = {4: 61, 17: 61, 5: 31, 16: 31, 6: 18, 15: 18, 7: 13, 14: 13, 8: 9, 13: 9, 9: 7, 12: 7, 10: 7, 11: 7}


@register
class SicBoGame(BaseGame):
    key = "sicbo"
    name = "Sic Bo"
    emoji = "🎲"
    category = "instant"
    order = 11
    rules_text = (
        "Three dice are rolled. Available bets: Small (4–10), Big (11–17), Odd/Even, a "
        "specific total, Any Triple, a specific triple, a specific double, or a two-number "
        "combination. Triples beat Small/Big/Odd/Even."
    )

    BETS = [
        ("Small", "small", "4–10 · 1:1"),
        ("Big", "big", "11–17 · 1:1"),
        ("Odd", "odd", "1:1"),
        ("Even", "even", "1:1"),
        ("Any triple", "any_triple", "30:1"),
        ("Total 4 / 17", "total:4", "60:1"),
        ("Total 9 / 12", "total:9", "6:1"),
        ("Total 10 / 11", "total:10", "6:1"),
        ("Triple 6", "triple:6", "180:1"),
        ("Double 5", "double:5", "10:1"),
        ("Combo 2+5", "combo:2-5", "5:1"),
    ]

    def quick_starts(self) -> list[Starter]:
        return [Starter(f"{label} · {note}", {"bet": bet}) for label, bet, note in self.BETS]

    def validate(self, raw: dict[str, str]) -> dict[str, str]:
        bet = str(raw.get("bet", "small")).lower()
        kind, _, arg = bet.partition(":")
        if kind in ("small", "big", "odd", "even", "any_triple"):
            return {"bet": kind}
        if kind == "total":
            try:
                total = int(arg)
            except ValueError as exc:
                raise GameError("Total must be 4–17.") from exc
            if total not in TOTAL_PAYS:
                raise GameError("That total is not offered.")
            return {"bet": f"total:{total}"}
        if kind == "triple":
            try:
                face = int(arg)
            except ValueError as exc:
                raise GameError("Triple must be 1–6.") from exc
            if not 1 <= face <= 6:
                raise GameError("Triple must be 1–6.")
            return {"bet": f"triple:{face}"}
        if kind == "double":
            try:
                face = int(arg)
            except ValueError as exc:
                raise GameError("Double must be 1–6.") from exc
            if not 1 <= face <= 6:
                raise GameError("Double must be 1–6.")
            return {"bet": f"double:{face}"}
        if kind == "combo":
            parts = arg.split("-")
            if len(parts) != 2:
                raise GameError("Combo must be two different faces.")
            try:
                a, b = sorted({int(parts[0]), int(parts[1])})
            except ValueError as exc:
                raise GameError("Combo must be two different faces.") from exc
            if a == b or not (1 <= a <= 6 and 1 <= b <= 6):
                raise GameError("Combo must be two different faces.")
            return {"bet": f"combo:{a}-{b}"}
        raise GameError("Unknown Sic Bo bet.")

    def _payout(self, bet: str, dice: list[int]) -> float:
        total = sum(dice)
        triple = dice[0] == dice[1] == dice[2]
        kind, _, arg = bet.partition(":")
        if kind == "small":
            return 2.0 if total <= 10 and not triple else 0.0
        if kind == "big":
            return 2.0 if total >= 11 and not triple else 0.0
        if kind == "odd":
            return 2.0 if total % 2 == 1 and not triple else 0.0
        if kind == "even":
            return 2.0 if total % 2 == 0 and not triple else 0.0
        if kind == "any_triple":
            return 31.0 if triple else 0.0
        if kind == "total":
            return float(TOTAL_PAYS.get(total, 0)) if int(arg) == total else 0.0
        if kind == "triple":
            return 181.0 if triple and dice[0] == int(arg) else 0.0
        if kind == "double":
            return 11.0 if dice.count(int(arg)) >= 2 else 0.0
        if kind == "combo":
            a, b = (int(x) for x in arg.split("-"))
            return 6.0 if a in dice and b in dice else 0.0
        return 0.0

    def start(self, rng: FairRNG, params: dict, stake: int) -> Round:
        dice = [rng.int(6) + 1 for _ in range(3)]
        multiplier = self._payout(params["bet"], dice)
        total = sum(dice)
        return Round(
            finished=True,
            multiplier=multiplier,
            status="WON" if multiplier > 0 else "LOST",
            text=(
                f"🎲 <b>{' '.join(FACES[d] for d in dice)}</b> · total {total}\n"
                f"Bet: {params['bet']}\n\n"
                f"{'🟢' if multiplier else '🔴'} {multiplier:.2f}x"
            ),
            detail={"dice": dice, "total": total, "bet": params["bet"]},
        )

    def theoretical_rtp(self) -> float:
        from bot.games.tables import binomial

        p_not_triple = 1 - 6 / 216
        p_small = 0.0
        for total in range(3, 19):
            for a in range(1, 7):
                for b in range(1, 7):
                    c = total - a - b
                    if 1 <= c <= 6:
                        triple = a == b == c
                        if 4 <= total <= 10 and not triple:
                            p_small += 1 / 216
        _ = (binomial, p_not_triple)
        return p_small * 2.0
