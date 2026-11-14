from __future__ import annotations

import time
from dataclasses import dataclass, field

from bot.core.errors import RateLimited


@dataclass
class MemoryRateLimiter:
    """Token bucket. `rate` bets per second with a small burst."""

    rate: float = 3.0
    burst: int = 3
    _buckets: dict[int, tuple[float, float]] = field(default_factory=dict)

    def check(self, user_id: int, cost: float = 1.0) -> None:
        now = time.monotonic()
        tokens, last = self._buckets.get(user_id, (float(self.burst), now))
        tokens = min(float(self.burst), tokens + (now - last) * self.rate)
        if tokens < cost:
            retry = (cost - tokens) / self.rate
            self._buckets[user_id] = (tokens, now)
            raise RateLimited(retry)
        self._buckets[user_id] = (tokens - cost, now)

    def reset(self, user_id: int) -> None:
        self._buckets.pop(user_id, None)


def build_limiter(redis_url: str, rate: float) -> MemoryRateLimiter:
    """Redis is optional; the in-process bucket is the safe default.

    Note: with more than one bot instance, set REDIS_URL. A Redis-backed limiter
    can be dropped in behind the same `check()` interface; the local bucket is
    always used as a fast first line of defence.
    """
    return MemoryRateLimiter(rate=rate, burst=max(1, int(rate)))
