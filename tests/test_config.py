from __future__ import annotations

from bot.config import Settings
from bot.db.url import normalize_database_url


def test_normalizes_railway_postgres_schemes():
    assert (
        normalize_database_url("postgres://u:p@containers.railway.app:5432/railway")
        == "postgresql+asyncpg://u:p@containers.railway.app:5432/railway"
    )
    assert (
        normalize_database_url("postgresql://u:p@db:5432/chipcity")
        == "postgresql+asyncpg://u:p@db:5432/chipcity"
    )
    assert (
        normalize_database_url("postgresql+psycopg://u:p@db:5432/chipcity")
        == "postgresql+asyncpg://u:p@db:5432/chipcity"
    )


def test_normalizes_sslmode_for_asyncpg():
    normalized = normalize_database_url(
        "postgresql://u:p@db:5432/chipcity?sslmode=require&channel_binding=require"
    )
    assert normalized == "postgresql+asyncpg://u:p@db:5432/chipcity?ssl=require"


def test_sqlite_url_is_unchanged():
    assert (
        normalize_database_url("sqlite+aiosqlite:///./data/chipcity.db")
        == "sqlite+aiosqlite:///./data/chipcity.db"
    )


def test_settings_normalizes_railway_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db:5432/chipcity?sslmode=require")
    settings = Settings(_env_file=None)
    assert (
        settings.database_url
        == "postgresql+asyncpg://u:p@db:5432/chipcity?ssl=require"
    )


def test_railway_port_variable_is_accepted(monkeypatch):
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.delenv("WEB_PORT", raising=False)
    settings = Settings(_env_file=None)
    assert settings.web_port == 9090


def test_web_port_takes_precedence_over_port(monkeypatch):
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("WEB_PORT", "8080")
    settings = Settings(_env_file=None)
    assert settings.web_port == 8080
