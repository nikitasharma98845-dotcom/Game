from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_wagered: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_won: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    games_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    daily_wagered: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    daily_reset_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_active: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    ledger: Mapped[list[Ledger]] = relationship(back_populates="user", lazy="noload")
    bets: Mapped[list[Bet]] = relationship(back_populates="user", lazy="noload")


class Ledger(Base):
    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    game: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bet_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    user: Mapped[User] = relationship(back_populates="ledger")


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    game: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    payout: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    profit: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    seed_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    server_seed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_seed: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False, index=True)
    step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    settled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="bets")


class Seed(Base):
    __tablename__ = "seeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    server_seed: Mapped[str] = mapped_column(String(128), nullable=False)
    server_seed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_seed: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revealed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_seeds_user_active", "user_id", "active"),)


class GameSetting(Base):
    __tablename__ = "game_settings"

    game: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_bet: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_bet: Mapped[int] = mapped_column(BigInteger, nullable=False)
    house_edge: Mapped[float] = mapped_column(Float, default=0.01, nullable=False)


class AdminLog(Base):
    __tablename__ = "admin_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
