from __future__ import annotations


class ChipCityError(Exception):
    """Base class for expected, user-facing failures."""


class GameError(ChipCityError):
    """Invalid game parameters or action."""


class InsufficientFunds(ChipCityError):
    pass


class BettingClosed(ChipCityError):
    """Game disabled, user banned/paused or limits exceeded."""


class StaleBet(ChipCityError):
    """Callback refers to a settled bet or an outdated step (idempotency guard)."""


class RateLimited(ChipCityError):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"Too fast, retry in {retry_after:.1f}s")
        self.retry_after = retry_after
