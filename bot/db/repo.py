from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminLog, Bet, GameSetting, Ledger, Seed, User, utcnow


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.get(User, telegram_id)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    starting_balance: int = 0,
) -> tuple[User, bool]:
    user = await session.get(User, telegram_id)
    created = False
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            balance=starting_balance,
            daily_reset_at=utcnow(),
        )
        session.add(user)
        if starting_balance:
            session.add(
                Ledger(
                    user_id=telegram_id,
                    type="ADMIN_CREDIT",
                    amount=starting_balance,
                    balance_after=starting_balance,
                    note="Welcome balance",
                )
            )
        await session.flush()
        created = True
    else:
        changed = False
        if username is not None and user.username != username:
            user.username = username
            changed = True
        if first_name is not None and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if changed:
            await session.flush()
    return user, created


async def get_setting(session: AsyncSession, game: str, *, min_bet: int, max_bet: int, edge: float) -> GameSetting:
    setting = await session.get(GameSetting, game)
    if setting is None:
        setting = GameSetting(game=game, enabled=True, min_bet=min_bet, max_bet=max_bet, house_edge=edge)
        session.add(setting)
        await session.flush()
    return setting


async def ensure_settings(
    session: AsyncSession, games: list[str], *, min_bet: int, max_bet: int, edge: float
) -> None:
    for key in games:
        await get_setting(session, key, min_bet=min_bet, max_bet=max_bet, edge=edge)
    await session.commit()


async def all_settings(session: AsyncSession) -> dict[str, GameSetting]:
    rows = (await session.execute(select(GameSetting))).scalars().all()
    return {row.game: row for row in rows}


async def add_admin_log(
    session: AsyncSession,
    admin_id: int,
    action: str,
    *,
    target_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    note: str | None = None,
) -> AdminLog:
    log = AdminLog(
        admin_id=admin_id,
        action=action,
        target_id=target_id,
        before=before,
        after=after,
        note=note,
    )
    session.add(log)
    await session.flush()
    return log


async def active_seed(session: AsyncSession, user_id: int) -> Seed | None:
    return (
        await session.execute(
            select(Seed).where(Seed.user_id == user_id, Seed.active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()


async def user_ledger(session: AsyncSession, user_id: int, limit: int = 20) -> list[Ledger]:
    return list(
        (
            await session.execute(
                select(Ledger)
                .where(Ledger.user_id == user_id)
                .order_by(Ledger.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def user_bets(session: AsyncSession, user_id: int, limit: int = 10, offset: int = 0) -> list[Bet]:
    return list(
        (
            await session.execute(
                select(Bet)
                .where(Bet.user_id == user_id)
                .order_by(Bet.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )


async def active_bets(session: AsyncSession, user_id: int) -> list[Bet]:
    return list(
        (
            await session.execute(
                select(Bet).where(Bet.user_id == user_id, Bet.status == "ACTIVE").order_by(Bet.id.desc())
            )
        )
        .scalars()
        .all()
    )


async def stale_active_bets(session: AsyncSession, older_than: datetime, limit: int = 50) -> list[Bet]:
    return list(
        (
            await session.execute(
                select(Bet)
                .where(Bet.status == "ACTIVE", Bet.created_at < older_than)
                .order_by(Bet.id.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def stats_for_user(session: AsyncSession, user_id: int) -> dict:
    user = await session.get(User, user_id)
    biggest = (
        await session.execute(
            select(func.max(Bet.payout)).where(Bet.user_id == user_id, Bet.status.in_(("WON", "CASHED_OUT")))
        )
    ).scalar() or 0
    favourite = (
        await session.execute(
            select(Bet.game, func.count(Bet.id))
            .where(Bet.user_id == user_id)
            .group_by(Bet.game)
            .order_by(func.count(Bet.id).desc())
            .limit(1)
        )
    ).first()
    return {
        "wagered": user.total_wagered if user else 0,
        "won": user.total_won if user else 0,
        "games": user.games_played if user else 0,
        "biggest_win": biggest,
        "favourite": favourite[0] if favourite else None,
        "balance": user.balance if user else 0,
    }


def period_start(period: str) -> datetime | None:
    now = datetime.now(UTC)
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "weekly":
        start = now - __import__("datetime").timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    return None


async def leaderboard_balance(session: AsyncSession, limit: int = 10) -> list[User]:
    return list(
        (
            await session.execute(
                select(User).where(User.is_banned.is_(False)).order_by(User.balance.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def leaderboard_wagered(session: AsyncSession, period: str = "all", limit: int = 10) -> list[tuple[int, int]]:
    start = period_start(period)
    query = select(Bet.user_id, func.sum(Bet.amount).label("total")).group_by(Bet.user_id)
    if start:
        query = query.where(Bet.created_at >= start)
    rows = (await session.execute(query.order_by(func.sum(Bet.amount).desc()).limit(limit))).all()
    return [(row[0], int(row[1] or 0)) for row in rows]


async def leaderboard_multiplier(session: AsyncSession, period: str = "all", limit: int = 10) -> list[tuple[int, float]]:
    start = period_start(period)
    query = select(Bet.user_id, func.max(Bet.multiplier).label("m")).where(Bet.status.in_(("WON", "CASHED_OUT")))
    if start:
        query = query.where(Bet.created_at >= start)
    rows = (
        await session.execute(query.group_by(Bet.user_id).order_by(func.max(Bet.multiplier).desc()).limit(limit))
    ).all()
    return [(row[0], float(row[1] or 0)) for row in rows]


async def per_game_stats(session: AsyncSession) -> list[tuple[str, int, int, int]]:
    rows = (
        await session.execute(
            select(
                Bet.game,
                func.count(Bet.id),
                func.sum(Bet.amount),
                func.sum(Bet.payout),
            )
            .where(Bet.status.in_(("WON", "CASHED_OUT", "LOST")))
            .group_by(Bet.game)
        )
    ).all()
    return [(r[0], int(r[1]), int(r[2] or 0), int(r[3] or 0)) for r in rows]
