from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import Settings
from bot.db import repo
from bot.db.models import utcnow


class UserContextMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings, session_factory) -> None:
        self.settings = settings
        self.sf = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None and not user.is_bot:
            async with self.sf() as session:
                row, _ = await repo.get_or_create_user(
                    session,
                    user.id,
                    username=user.username,
                    first_name=user.first_name,
                    starting_balance=self.settings.starting_balance,
                )
                row.last_active = utcnow()
                await session.commit()
                data["user_row"] = row
        data["settings"] = self.settings
        return await handler(event, data)
