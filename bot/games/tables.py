from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


def comb(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def hypergeom(pop: int, successes: int, draws: int, hits: int) -> float:
    return comb(successes, hits) * comb(pop - successes, draws - hits) / comb(pop, draws)


def binomial(n: int, k: int, p: float = 0.5) -> float:
    return comb(n, k) * (p**k) * ((1 - p) ** (n - k))


def scale_to_rtp(shape: Sequence[float], edge: float = 0.01, decimals: int = 2) -> list[float]:
    """Scale an equal-probability segment shape so its mean equals 1 - edge."""
    mean = sum(shape) / len(shape)
    if mean <= 0:
        raise ValueError("shape mean must be positive")
    target = (1 - edge) / mean
    return [round(v * target, decimals) for v in shape]


def weighted_table(
    multipliers: Sequence[float],
    weights: Sequence[float],
    *,
    zero_prob: float = 0.0,
    edge: float = 0.01,
    decimals: int = 2,
) -> list[tuple[float, float]]:
    """Build (multiplier, probability) pairs with an exact-ish RTP.

    Non-zero prizes get probabilities proportional to weight/multiplier (more
    likely when the prize is smaller); all prizes are then scaled by a single
    factor so the total return is 1 - edge.  `zero_prob` reserves mass for a
    losing slice.
    """
    if len(multipliers) != len(weights):
        raise ValueError("multipliers and weights must have equal length")
    if not 0 <= zero_prob < 1:
        raise ValueError("zero_prob out of range")
    raw = [(w, m) for w, m in zip(weights, multipliers, strict=True) if m > 0 and w > 0]
    if not raw:
        raise ValueError("no paying prizes")
    denom = sum(w / m for w, m in raw)
    mass = 1.0 - zero_prob
    entries = [(m, mass * (w / m) / denom) for w, m in raw]
    rtp0 = sum(m * p for m, p in entries)
    factor = (1 - edge) / rtp0
    priced = [(round(m * factor, decimals), p) for m, p in entries]
    if zero_prob > 0:
        priced.append((0.0, zero_prob))
    return priced


@dataclass(frozen=True)
class Payout:
    multiplier: float
    probability: float


def table_rtp(table: Sequence[tuple[float, float]]) -> float:
    return sum(m * p for m, p in table)


def multipliers(table: Sequence[tuple[float, float]]) -> list[float]:
    return [m for m, _ in table]


def probability(table: Sequence[tuple[float, float]], index: int) -> float:
    return table[index][1]


def payout_for(table: Sequence[tuple[float, float]], r: float) -> float:
    """Pick a multiplier from a weighted table using r in [0,1)."""
    acc = 0.0
    for m, p in table:
        acc += p
        if r < acc:
            return m
    return table[-1][0]
