"""Database URL helpers shared by settings, Alembic and the engine factory."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_database_url(value: str) -> str:
    """Accept the URL forms Railway/Heroku-style hosts provide.

    ``postgres://`` and ``postgresql://`` are rewritten to SQLAlchemy's asyncpg
    driver, and libpq's ``sslmode`` query parameter is translated to the ``ssl``
    parameter understood by asyncpg. Other URLs are returned unchanged.
    """
    if not value:
        return value
    url = value.strip()
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    elif url.startswith("postgresql+psycopg2://"):
        url = "postgresql+asyncpg://" + url[len("postgresql+psycopg2://") :]
    elif url.startswith("postgresql+psycopg://"):
        url = "postgresql+asyncpg://" + url[len("postgresql+psycopg://") :]

    if not url.startswith("postgresql+asyncpg://"):
        return url

    parts = urlsplit(url)
    query: list[tuple[str, str]] = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            query.append(("ssl", val))
        elif key == "channel_binding":
            # asyncpg does not accept libpq's channel_binding parameter.
            continue
        else:
            query.append((key, val))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
