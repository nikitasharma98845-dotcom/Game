from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.db.url import normalize_database_url

CHIP = 100  # one Chip == 100 integer cents


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    owner_telegram_id: int = 1857417752
    owner_telegram_username: str = "krisnn_ka_bhakt"

    database_url: str = "sqlite+aiosqlite:///./data/chipcity.db"
    redis_url: str = ""

    mode: Literal["polling", "webhook"] = "polling"
    webhook_url: str = ""
    webhook_secret: str = "change-me-please"
    web_host: str = "0.0.0.0"
    # Railway (and most PaaS hosts) inject PORT; WEB_PORT still takes precedence.
    web_port: int = Field(8080, validation_alias=AliasChoices("WEB_PORT", "PORT"))

    default_house_edge: float = 0.01
    min_bet_chips: int = Field(1, validation_alias="MIN_BET")
    max_bet_chips: int = Field(100_000, validation_alias="MAX_BET")
    max_profit_chips: int = Field(1_000_000, validation_alias="MAX_PROFIT_PER_BET")
    starting_balance_chips: int = Field(0, validation_alias="STARTING_BALANCE")

    session_timeout_seconds: int = 600
    bets_per_second: int = 3
    render_images: bool = True

    log_level: str = "INFO"
    log_file: str = "logs/bot.log"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        return normalize_database_url(str(value)) if value else value

    @property
    def min_bet(self) -> int:
        return self.min_bet_chips * CHIP

    @property
    def max_bet(self) -> int:
        return self.max_bet_chips * CHIP

    @property
    def max_profit(self) -> int:
        return self.max_profit_chips * CHIP

    @property
    def starting_balance(self) -> int:
        return self.starting_balance_chips * CHIP


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
