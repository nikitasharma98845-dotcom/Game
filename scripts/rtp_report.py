"""Monte Carlo RTP report.

Usage:
    python -m scripts.rtp_report --rounds 100000
    python -m scripts.rtp_report --rounds 1000000 --markdown RTP_REPORT.md

The reported standard error is the Monte Carlo standard error of the mean
multiplier, not a confidence interval. With 1,000,000 rounds most games land
well inside ±0.5%; high-variance games (keno top tiers, slots, limbo longshots)
need the larger sample to reach the same precision, which is why the default
slow-game sample is smaller unless you ask for a full run.
"""

from __future__ import annotations

import argparse
import time

from bot.games import get_game
from bot.games.keno import keno_table
from bot.games.plinko import plinko_table
from bot.games.tables import binomial, hypergeom
from bot.games.wheel import wheel_values
from tests.sim import (
    cashout_after,
    dragon_policy,
    hilo_policy,
    mines_policy,
    moles_policy,
    rps_policy,
    simulate,
    simulate_blackjack,
    simulate_video_poker,
)


def plinko_rtp(rows: int, risk: str) -> float:
    table = plinko_table(rows, risk)
    return sum(binomial(rows, i) * m for i, m in enumerate(table))


def keno_rtp(picks: int, risk: str) -> float:
    return sum(hypergeom(40, 10, picks, h) * m for h, m in keno_table(picks, risk))


def wheel_rtp(segments: int, risk: str) -> float:
    values = wheel_values(segments, risk)
    return sum(values) / len(values)


CASES = [
    ("dice", "under 50", {"direction": "under", "target": "50"}, None, 0.99),
    ("dice", "over 95", {"direction": "over", "target": "95"}, None, 0.99),
    ("limbo", "2x", {"target": "2"}, None, 0.99),
    ("limbo", "10x", {"target": "10"}, None, 0.99),
    ("coinflip", "cash out 1", {"choice": "heads"}, cashout_after("streak", 1, "flip"), 0.99),
    ("plinko", "12 rows medium", {"rows": "12", "risk": "medium"}, None, plinko_rtp(12, "medium")),
    ("plinko", "16 rows high", {"rows": "16", "risk": "high"}, None, plinko_rtp(16, "high")),
    ("keno", "5 picks classic", {"picks": "5", "risk": "classic"}, None, keno_rtp(5, "classic")),
    ("diamonds", "draw 5", {}, None, get_game("diamonds").theoretical_rtp()),
    ("cases", "vault", {"case": "vault"}, None, get_game("cases").theoretical_rtp()),
    ("bars", "bar 1 medium", {"bar": "1", "risk": "medium"}, None, get_game("bars").theoretical_rtp()),
    ("tarot", "3 cards", {}, None, get_game("tarot").theoretical_rtp()),
    ("darts", "medium", {"risk": "medium"}, None, get_game("darts").theoretical_rtp()),
    ("sicbo", "small", {"bet": "small"}, None, 0.9722),
    ("rps", "continue draws", {"choice": "rock"}, rps_policy, 0.99),
    ("slide", "target 2.16x", {"target": "2.16"}, None, get_game("slide").theoretical_rtp()),
    ("mines", "3 mines, 3 picks", {"mines": "3"}, mines_policy, 0.99),
    ("dragontower", "medium", {"difficulty": "medium"}, dragon_policy, 0.99),
    ("pump", "medium 3 pumps", {"difficulty": "medium"}, cashout_after("pumps", 3, "pump"), 0.99),
    ("chicken", "medium 3 lanes", {"difficulty": "medium"}, cashout_after("lane", 3, "cross"), 0.99),
    ("moles", "medium", {"difficulty": "medium"}, moles_policy, 0.99),
    ("snakes", "medium 3 rolls", {"difficulty": "medium"}, cashout_after("rolls", 3, "roll"), 0.99),
    ("wheel", "20 seg medium", {"segments": "20", "risk": "medium"}, None, wheel_rtp(20, "medium")),
    (
        "roulette",
        "red",
        {"bets": [{"type": "color", "sel": "red", "amount": 100}]},
        None,
        18 / 37 * 2,
    ),
    ("baccarat", "banker", {"bet": "banker"}, None, 0.9894),
    ("crash", "auto 2x", {"auto": "2"}, None, 0.99),
    ("hilo", "3 guesses", {}, hilo_policy, 0.99),
    ("pharaoh", "spin", {}, None, get_game("pharaoh").theoretical_rtp()),
    ("ronin", "spin", {}, None, get_game("ronin").theoretical_rtp()),
    ("spellbook", "spin", {}, None, get_game("spellbook").theoretical_rtp()),
]

SPECIAL = [
    ("blackjack", "basic strategy", 0.9954),
    ("videopoker", "simple strategy", 0.9954),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=100_000)
    parser.add_argument("--slow-rounds", type=int, default=0, help="rounds for slots/cards (default rounds/5)")
    parser.add_argument("--markdown", default="", help="write a markdown report to this path")
    args = parser.parse_args()
    slow = args.slow_rounds or max(2_000, args.rounds // 5)
    rows = []
    started = time.time()
    print(f"{'game':12s} {'config':20s} {'n':>8s} {'measured':>9s} {'theory':>8s} {'diff':>8s} {'se':>8s}")
    for key, config, params, policy, theoretical in CASES:
        rounds = slow if key in ("pharaoh", "ronin", "spellbook") else args.rounds
        game = get_game(key)
        measured, se = simulate(game, params, rounds, policy)
        rows.append((key, config, rounds, measured, theoretical, se))
        print(
            f"{key:12s} {config:20s} {rounds:8,d} {measured:9.4f} {theoretical:8.4f} "
            f"{measured - theoretical:+8.4f} {se:8.4f}"
        )
    for key, config, theoretical in SPECIAL:
        game = get_game(key)
        if key == "blackjack":
            measured, se = simulate_blackjack(game, slow)
        else:
            measured, se = simulate_video_poker(game, slow)
        rows.append((key, config, slow, measured, theoretical, se))
        print(
            f"{key:12s} {config:20s} {slow:8,d} {measured:9.4f} {theoretical:8.4f} "
            f"{measured - theoretical:+8.4f} {se:8.4f}"
        )
    elapsed = time.time() - started
    print(f"\n{len(rows)} configurations in {elapsed:.1f}s")
    if args.markdown:
        write_markdown(args.markdown, rows, args.rounds, slow, elapsed)
        print(f"wrote {args.markdown}")


def write_markdown(path: str, rows, rounds: int, slow: int, elapsed: float) -> None:
    lines = [
        "# ChipCity — Monte Carlo RTP report",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} · "
        f"{rounds:,} rounds per instant game, {slow:,} per slot/card configuration · {elapsed:.1f}s",
        "",
        "| Game | Configuration | Rounds | Measured RTP | Theoretical | Diff | Std. error |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for key, config, n, measured, theoretical, se in rows:
        lines.append(
            f"| {key} | {config} | {n:,} | {measured * 100:.2f}% | {theoretical * 100:.2f}% | "
            f"{(measured - theoretical) * 100:+.2f}% | {se * 100:.2f}% |"
        )
    lines += [
        "",
        "Theoretical values are the game's published tables. Blackjack (0.9954) and Video Poker (0.9954)",
        "assume strong play; the simulated strategies are conservative simplifications, so their measured",
        "values are slightly lower and are reported rather than asserted. Roulette (97.30%), Sic Bo (97.22%)",
        "and Baccarat (98.94%) use their standard casino pay tables, as documented in DECISIONS.md.",
        "",
        "Run the full spec sample with:",
        "",
        "```bash",
        "python -m scripts.rtp_report --rounds 1000000 --slow-rounds 200000",
        "```",
    ]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
