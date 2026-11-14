from __future__ import annotations

import builtins
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Seed, utcnow

DEFAULT_CLIENT_SEED = "chipcity"


def new_server_seed() -> str:
    """32 random bytes as hex. Only the hash is shown before rotation."""
    return secrets.token_hex(32)


def hash_server_seed(server_seed_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(server_seed_hex)).hexdigest()


@dataclass
class FairRNG:
    """HMAC-SHA256 provably-fair stream.

    value(cursor) = first 4 bytes of HMAC_SHA256(server_seed, f"{client_seed}:{nonce}:{cursor}")
    scaled to [0, 1).  Game logic must consume values through this object only.
    """

    server_seed: str
    client_seed: str
    nonce: int
    cursor: int = 0
    proof: list[str] = field(default_factory=list)

    def _raw(self) -> bytes:
        msg = f"{self.client_seed}:{self.nonce}:{self.cursor}".encode()
        digest = hmac.new(bytes.fromhex(self.server_seed), msg, hashlib.sha256).digest()
        self.cursor += 1
        self.proof.append(digest[:4].hex())
        return digest

    def next(self) -> float:
        raw = self._raw()
        return int.from_bytes(raw[:4], "big") / 4294967296.0

    def floats(self, n: int) -> list[float]:
        return [self.next() for _ in range(n)]

    def int(self, n: int) -> int:
        """Uniform integer in [0, n). Uses the next float (no modulo bias)."""
        if n <= 0:
            raise ValueError("n must be positive")
        return min(n - 1, int(self.next() * n))

    def shuffle(self, items: list) -> list:
        """Fisher-Yates driven by the fair stream."""
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.int(i + 1)
            out[i], out[j] = out[j], out[i]
        return out

    def seek(self, cursor: builtins.int) -> None:
        self.cursor = cursor


def floats_from_seed(
    server_seed: str, client_seed: str, nonce: int, count: int
) -> list[float]:
    """Deterministic replay used by /verify after the seed is revealed."""
    rng = FairRNG(server_seed, client_seed, nonce)
    return rng.floats(count)


async def get_active_seed(session: AsyncSession, user_id: int) -> Seed:
    result = await session.execute(
        select(Seed).where(Seed.user_id == user_id, Seed.active.is_(True)).limit(1)
    )
    seed = result.scalar_one_or_none()
    if seed is None:
        server_seed = new_server_seed()
        seed = Seed(
            user_id=user_id,
            server_seed=server_seed,
            server_seed_hash=hash_server_seed(server_seed),
            client_seed=DEFAULT_CLIENT_SEED,
            nonce=0,
            active=True,
        )
        session.add(seed)
        await session.flush()
    return seed


async def allocate_nonce(session: AsyncSession, user_id: int) -> Seed:
    """Reserve the next nonce for a bet and persist the increment."""
    seed = await get_active_seed(session, user_id)
    seed.nonce += 1
    await session.flush()
    return seed


async def rotate_seed(session: AsyncSession, user_id: int) -> tuple[Seed, Seed]:
    old = await get_active_seed(session, user_id)
    old.active = False
    old.revealed_at = utcnow()
    server_seed = new_server_seed()
    fresh = Seed(
        user_id=user_id,
        server_seed=server_seed,
        server_seed_hash=hash_server_seed(server_seed),
        client_seed=old.client_seed,
        nonce=0,
        active=True,
    )
    session.add(fresh)
    await session.flush()
    return old, fresh


async def set_client_seed(session: AsyncSession, user_id: int, client_seed: str) -> Seed:
    seed = await get_active_seed(session, user_id)
    seed.client_seed = client_seed[:128]
    await session.flush()
    return seed
