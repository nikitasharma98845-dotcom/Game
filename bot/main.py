from __future__ import annotations

import asyncio
import contextlib
import logging
import logging.handlers
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import Settings, get_settings
from bot.core.bet_engine import BetEngine
from bot.core.rate_limit import build_limiter
from bot.db import repo
from bot.db.session import create_engine, create_session_factory, init_models
from bot.games import all_games
from bot.handlers import admin, group, play, user
from bot.middlewares import UserContextMiddleware


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key in ("bet_id", "game", "user_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        import json

        return json.dumps(payload)


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(stream)
    try:
        import pathlib

        pathlib.Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)
        rotating = logging.handlers.RotatingFileHandler(
            settings.log_file, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        rotating.setFormatter(JsonFormatter())
        root.addHandler(rotating)
    except OSError:
        pass
    logging.getLogger("aiogram").setLevel(logging.WARNING)


async def _timeout_loop(engine: BetEngine) -> None:
    while True:
        await asyncio.sleep(30)
        try:
            settled = await engine.timeout_active()
            if settled:
                logging.getLogger("chipcity").info("auto-settled %s timed-out rounds", settled)
        except Exception:
            logging.getLogger("chipcity").exception("timeout job failed")


async def run() -> None:
    settings = get_settings()
    setup_logging(settings)
    log = logging.getLogger("chipcity")
    log.info("starting ChipCity")

    engine_db = create_engine(settings.database_url)
    session_factory = create_session_factory(engine_db)
    await init_models(engine_db)
    async with session_factory() as session:
        await repo.ensure_settings(
            session,
            [game.key for game in all_games()],
            min_bet=settings.min_bet,
            max_bet=settings.max_bet,
            edge=settings.default_house_edge,
        )

    limiter = build_limiter(settings.redis_url, settings.bets_per_second)
    engine = BetEngine(settings, session_factory, limiter)
    play.configure(engine)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["engine"] = engine
    dispatcher["session_factory"] = session_factory
    dispatcher["settings"] = settings

    middleware = UserContextMiddleware(settings, session_factory)
    dispatcher.message.middleware(middleware)
    dispatcher.callback_query.middleware(middleware)

    dispatcher.include_router(admin.router)
    dispatcher.include_router(group.router)
    dispatcher.include_router(user.router)
    dispatcher.include_router(play.router)

    @dispatcher.errors()
    async def on_error(event: ErrorEvent) -> None:
        log.exception("update failed", exc_info=event.exception)
        if settings.owner_telegram_id:
            with contextlib.suppress(Exception):
                await event.update.bot.send_message(
                    settings.owner_telegram_id,
                    f"⚠️ Error: <code>{type(event.exception).__name__}</code>\n"
                    f"{str(event.exception)[:300]}",
                )

    timeout_task = asyncio.create_task(_timeout_loop(engine))
    shutdown_done = False

    async def on_shutdown() -> None:
        nonlocal shutdown_done
        if shutdown_done:
            return
        shutdown_done = True
        timeout_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await timeout_task
        await group.shutdown_rounds(engine)
        with contextlib.suppress(Exception):
            await engine.settle_all_active()
        await engine_db.dispose()

    dispatcher.shutdown.register(on_shutdown)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Main menu"),
            BotCommand(command="games", description="Browse games"),
            BotCommand(command="balance", description="Your Chips"),
            BotCommand(command="resume", description="Resume a round"),
            BotCommand(command="fairness", description="Provable fairness"),
            BotCommand(command="help", description="All commands"),
        ]
    )

    if settings.mode == "webhook":
        app = web.Application()
        SimpleRequestHandler(
            dispatcher=dispatcher, bot=bot, secret_token=settings.webhook_secret or None
        ).register(app, path="/webhook")
        setup_application(app, dispatcher, bot=bot)
        await bot.set_webhook(
            f"{settings.webhook_url.rstrip('/')}/webhook",
            secret_token=settings.webhook_secret or None,
            drop_pending_updates=False,
        )
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, settings.web_host, settings.web_port)
        await site.start()
        log.info("webhook mode on %s:%s", settings.web_host, settings.web_port)
        try:
            await asyncio.Event().wait()
        finally:
            await on_shutdown()
            await runner.cleanup()
    else:
        log.info("polling mode")
        await bot.delete_webhook(drop_pending_updates=False)
        try:
            await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
        finally:
            await on_shutdown()


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(run())


if __name__ == "__main__":
    main()
