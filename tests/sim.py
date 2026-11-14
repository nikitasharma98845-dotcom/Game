from __future__ import annotations

import math
import random

from bot.games.blackjack import card_value, hand_value
from bot.games.hilo import rank_index
from bot.games.video_poker import RANKS, evaluate


class FastRNG:
    """Deterministic stand-in for FairRNG in simulations."""

    def __init__(self, seed: int = 1234) -> None:
        self._r = random.Random(seed)

    def next(self) -> float:
        return self._r.random()

    def int(self, n: int) -> int:
        return self._r.randrange(n)

    def shuffle(self, items: list) -> list:
        out = list(items)
        self._r.shuffle(out)
        return out

    def floats(self, n: int) -> list[float]:
        return [self.next() for _ in range(n)]

    def seek(self, cursor: int) -> None:  # compatibility with FairRNG
        return None


def cashout_after(key: str, count: int, action: str, arg: str = ""):
    def policy(game, state, rng):
        value = state.get(key, 0)
        current = len(value) if isinstance(value, list) else int(value)
        if current >= count:
            return "cashout", ""
        return action, arg

    return policy


def mines_policy(game, state, rng):
    if len(state["revealed"]) >= 3:
        return "cashout", ""
    hidden = [i for i in range(25) if i not in state["revealed"]]
    return "pick", str(hidden[rng.int(len(hidden))])


def moles_policy(game, state, rng):
    if len(state["revealed"]) >= 3:
        return "cashout", ""
    hidden = [i for i in range(9) if i not in state["revealed"]]
    return "pick", str(hidden[rng.int(len(hidden))])


def dragon_policy(game, state, rng):
    if int(state["floor"]) >= 3:
        return "cashout", ""
    return "pick", str(rng.int(int(state["eggs"])))


def hilo_policy(game, state, rng):
    if int(state["index"]) >= 4:
        return "cashout", ""
    current = str(state["card"][0])
    guess = "lower" if rank_index(current) >= len(RANKS) - 1 else "higher"
    return guess, ""


def rps_policy(game, state, rng):
    return "continue", ""


def play_round(game, params, rng: FastRNG, stake: int, policy=None):
    rnd = game.start(rng, params, stake)
    steps = 0
    while not rnd.finished and steps < 250:
        action, arg = policy(game, rnd.state, rng) if policy else ("cashout", "")
        rnd = game.step(rnd.state, action, arg, rng)
        steps += 1
    return rnd


def simulate(game, params: dict, rounds: int, policy=None, stake: int = 100) -> tuple[float, float]:
    rng = FastRNG(20240501)
    total = 0.0
    square = 0.0
    for _ in range(rounds):
        rnd = play_round(game, params, rng, stake, policy)
        value = float(rnd.multiplier)
        total += value
        square += value * value
    mean = total / rounds
    variance = max(0.0, square / rounds - mean * mean)
    standard_error = math.sqrt(variance / rounds)
    return mean, standard_error


def blackjack_action(game, state) -> tuple[str, str]:
    hand = state["hands"][int(state["active"])]
    cards = hand["cards"]
    value, soft = hand_value(cards)
    dealer = card_value(str(state["dealer"][0][0]))
    pair_value = card_value(str(cards[0][0])) if len(cards) == 2 and card_value(
        str(cards[0][0])
    ) == card_value(str(cards[1][0])) else 0
    can_split = len(state["hands"]) < 4 and pair_value > 0 and len(cards) == 2
    can_double = len(cards) == 2 and not hand["doubled"]

    if can_split:
        if pair_value in (11, 8):
            return "split", ""
        if pair_value == 9 and dealer not in (7, 10, 11):
            return "split", ""
        if pair_value == 7 and dealer <= 7:
            return "split", ""
        if pair_value == 6 and dealer <= 6:
            return "split", ""
        if pair_value in (2, 3) and dealer <= 7:
            return "split", ""
        if pair_value == 4 and dealer in (5, 6):
            return "split", ""

    if soft:
        if value >= 19:
            return "stand", ""
        if value == 18:
            if can_double and 3 <= dealer <= 6:
                return "double", ""
            return "stand", ""
        if 15 <= value <= 17:
            if can_double and 4 <= dealer <= 6:
                return "double", ""
            return "hit", ""
        if can_double and 5 <= dealer <= 6:
            return "double", ""
        return "hit", ""

    if value >= 17:
        return "stand", ""
    if value == 11:
        return ("double", "") if can_double else ("hit", "")
    if value == 10 and can_double and dealer <= 9:
        return "double", ""
    if value == 9 and can_double and 3 <= dealer <= 6:
        return "double", ""
    if 13 <= value <= 16:
        return ("stand", "") if dealer <= 6 else ("hit", "")
    if value == 12:
        return ("stand", "") if 4 <= dealer <= 6 else ("hit", "")
    return "hit", ""


def simulate_blackjack(game, rounds: int, stake: int = 100) -> tuple[float, float]:
    rng = FastRNG(777)
    total = 0.0
    square = 0.0
    for _ in range(rounds):
        rnd = game.start(rng, {}, stake)
        steps = 0
        while not rnd.finished and steps < 40:
            action, arg = blackjack_action(game, rnd.state)
            rnd = game.step(rnd.state, action, arg, rng)
            steps += 1
        value = float(rnd.multiplier)
        total += value
        square += value * value
    mean = total / rounds
    variance = max(0.0, square / rounds - mean * mean)
    return mean, math.sqrt(variance / rounds)


def vp_holds(hand) -> list[bool]:
    from itertools import combinations

    category = evaluate(hand)
    ranks = [str(c[0]) for c in hand]
    suits = [str(c[1]) for c in hand]
    royal = {"10", "J", "Q", "K", "A"}

    def mask(indexes):
        return [i in indexes for i in range(5)]

    counts: dict[str, list[int]] = {}
    for index, rank in enumerate(ranks):
        counts.setdefault(rank, []).append(index)

    if category in ("royal_flush", "straight_flush", "four", "full_house", "flush", "straight"):
        return [True] * 5
    if category == "two_pair":
        pairs = [i for idx in counts.values() if len(idx) == 2 for i in idx]
        return mask(pairs)
    if category == "three":
        return mask(next(idx for idx in counts.values() if len(idx) == 3))
    if category == "jacks":
        return mask(next(idx for idx in counts.values() if len(idx) == 2))
    for indexes in counts.values():
        if len(indexes) == 2:
            return mask(indexes)

    four_flush: list[int] | None = None
    for drop in range(5):
        kept = [i for i in range(5) if i != drop]
        if len({suits[i] for i in kept}) == 1:
            if all(ranks[i] in royal for i in kept):
                return mask(kept)
            four_flush = kept
    if four_flush:
        return mask(four_flush)

    for drop in range(5):
        kept = [i for i in range(5) if i != drop]
        if len({ranks[i] for i in kept}) != 4:
            continue
        values = sorted({RANKS.index(ranks[i]) for i in kept})
        if values[-1] - values[0] <= 4:
            return mask(kept)

    for combo in combinations(range(5), 3):
        if len({suits[i] for i in combo}) == 1 and all(ranks[i] in royal for i in combo):
            return mask(combo)

    for combo in combinations(range(5), 3):
        if len({suits[i] for i in combo}) != 1:
            continue
        values = sorted({RANKS.index(ranks[i]) for i in combo})
        if len(values) == 3 and values[-1] - values[0] <= 2:
            return mask(combo)

    highs = [i for i in range(5) if ranks[i] in {"J", "Q", "K", "A"}]
    for i, j in combinations(highs, 2):
        if suits[i] == suits[j]:
            return mask([i, j])
    if highs:
        return mask([highs[0]])
    return [False] * 5


def simulate_video_poker(game, rounds: int, stake: int = 100) -> tuple[float, float]:
    rng = FastRNG(999)
    total = 0.0
    square = 0.0
    for _ in range(rounds):
        rnd = game.start(rng, {}, stake)
        holds = vp_holds(rnd.state["hand"])
        for index, hold in enumerate(holds):
            if hold:
                rnd = game.step(rnd.state, "hold", str(index), rng)
        rnd = game.step(rnd.state, "draw", "", rng)
        value = float(rnd.multiplier)
        total += value
        square += value * value
    mean = total / rounds
    variance = max(0.0, square / rounds - mean * mean)
    return mean, math.sqrt(variance / rounds)
