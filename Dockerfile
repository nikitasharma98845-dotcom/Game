FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY bot ./bot
RUN pip install --upgrade pip && pip install .

RUN useradd --create-home --uid 10001 chipcity \
    && mkdir -p /app/data /app/logs \
    && chown -R chipcity:chipcity /app
USER chipcity

ENV LOG_FILE=/app/logs/bot.log \
    DATABASE_URL=sqlite+aiosqlite:////app/data/chipcity.db

# Railway, Compose and plain `docker run` all migrate before starting the bot.
CMD ["sh", "-c", "alembic upgrade head && exec python -m bot"]
