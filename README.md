# ChipCity 🎰

A **play-money** casino bot for a private Telegram friend group. Thirty registered games, provably-fair
outcomes, a ledger-backed wallet, owner-only chip issuance and no payment code anywhere.

> ⚠️ **This is a just-for-fun game. Chips have no monetary value, cannot be bought, sold, transferred or
> redeemed.** There are no deposits, withdrawals, tips or cash-outs to real money. Only the bot owner can
> create Chips.

---

## Contents

- [What is included](#what-is-included)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Docker](#docker)
- [Deploying](#deploying)
- [Commands](#commands)
- [Owner commands](#owner-commands)
- [Game list and RTP](#game-list-and-rtp)
- [Provable fairness](#provable-fairness)
- [How a bet flows](#how-a-bet-flows)
- [Tests and RTP report](#tests-and-rtp-report)
- [Project layout](#project-layout)
- [Adding game #31](#adding-game-31)
- [Backups and restore](#backups-and-restore)
- [Operational notes](#operational-notes)

---

## What is included

- **30 game registrations across 28 game types** (three original slot themes) in six categories:
  instant, cards, risk/cash-out,
  wheel & roulette, slots, group.
- **Provably fair** HMAC-SHA256 outcome stream with seed rotation, client seeds and `/verify`.
- **Ledger wallet**: every balance change is one `ledger` row and `users.balance == SUM(ledger.amount)`.
  Rows are locked with per-user asyncio locks plus `SELECT … FOR UPDATE` on PostgreSQL.
- **Multi-step games** (mines, HiLo, blackjack, tower, chicken, pump, moles, snakes, video poker, coin flip,
  crash) with resume, stale-button protection and a configurable timeout that auto-cashes-out or forfeits.
- **Owner-only chip creation**, bans, limits, broadcast, audit, CSV export, per-game RTP stats.
- **Group play**: shared Crash and Slide rounds, PvP Dice Duel, per-chat leaderboard.
- **Pillow boards** for Plinko, Wheel, Roulette and Mines.
- **Docker Compose** with PostgreSQL and Redis, Alembic migrations, pytest suite and a Monte Carlo
  [RTP report](RTP_REPORT.md).

---

## Quick start

Requirements: Python 3.12, a Telegram account.

### 1. Create the bot

1. Open [@BotFather](https://t.me/BotFather), send `/newbot`, pick a name and username (the bot name is
   independent of the `ChipCity` branding used in messages).
2. Copy the token it gives you.
3. For group play, send `/setprivacy` to BotFather, choose the bot and **Disable** privacy mode so typed
   bets and roulette slips are visible to the bot. Commands work without this, typed bet slips do not.

### 2. Find your Telegram ID

Send `/start` to [@userinfobot](https://t.me/userinfobot); it replies with your numeric ID. That ID is
`OWNER_TELEGRAM_ID`. It is the only ID that can create Chips or run admin commands.

### 3. Configure

```bash
git clone <this repo> chipcity && cd chipcity
cp .env.example .env
# edit .env: BOT_TOKEN=..., OWNER_TELEGRAM_ID=...
```

### 4. Install and run

```bash
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

.venv/bin/alembic upgrade head
.venv/bin/python -m bot
```

The bot starts in long-polling mode. Open a DM, send `/start`, then credit yourself from the owner account:

```
/addcredits <your_id> 10000
```

New players start with `STARTING_BALANCE` (default **0** Chips) — only the owner creates Chips. They must
`/start` the bot once before `/addcredits` can find them.

---

## Configuration

All settings live in `.env`; see [`.env.example`](.env.example). Amounts in env are **whole Chips**;
internally everything is integer cents (`1 Chip = 100`).

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | — | BotFather token. Required. |
| `OWNER_TELEGRAM_ID` | `0` | The only account allowed to create Chips / administer. |
| `DATABASE_URL` | SQLite file | `sqlite+aiosqlite:///…` or Postgres. Railway's `postgres://`, `postgresql://` and `sslmode=require` forms are normalized automatically. |
| `REDIS_URL` | empty | Reserved for a shared rate limiter; empty uses the in-process bucket. |
| `MODE` | `polling` | `polling` for dev/Railway workers, `webhook` for a public HTTPS host. |
| `WEBHOOK_URL` | — | Public base URL, e.g. `https://chips.example.com` (webhook mode). |
| `WEBHOOK_SECRET` | `change-me-please` | Telegram secret token for the webhook. |
| `WEB_HOST` / `WEB_PORT` | `0.0.0.0` / `8080` | Webhook listener. `PORT` (Railway) is used when `WEB_PORT` is unset. |
| `DEFAULT_HOUSE_EDGE` | `0.01` | Initial edge for games created on first boot. |
| `MIN_BET` / `MAX_BET` | `1` / `100000` | Global default limits in Chips (per-game overrides exist). |
| `MAX_PROFIT_PER_BET` | `1000000` | Hard cap on profit per bet in Chips. |
| `STARTING_BALANCE` | `0` | Welcome balance. Zero by default: only the owner issues Chips. |
| `SESSION_TIMEOUT_SECONDS` | `600` | Multi-step rounds auto-settle after this. |
| `BETS_PER_SECOND` | `3` | Per-user token bucket. |
| `RENDER_IMAGES` | `true` | Pillow boards for Plinko/Wheel/Roulette/Mines. |
| `LOG_LEVEL` / `LOG_FILE` | `INFO` / `logs/bot.log` | JSON logs, rotated at 5 MB × 3. |

---

## Docker

```bash
cp .env.example .env    # fill BOT_TOKEN + OWNER_TELEGRAM_ID
docker compose up --build
```

`docker-compose.yml` starts PostgreSQL 16, Redis 7 and the bot. The Docker image runs
`alembic upgrade head` before `python -m bot`, waits for a healthy database and keeps `data/` and `logs/`
on the host. The Compose environment overrides `DATABASE_URL` to the Postgres service; `env_file: .env`
still supplies the token and owner ID.

---

## Deploying

### VPS with Docker + webhook

1. Point a DNS record at the server.
2. Set `MODE=webhook`, `WEBHOOK_URL=https://chips.example.com`, a random `WEBHOOK_SECRET`.
3. Run `docker compose up -d --build`.
4. Put Caddy in front:

```caddyfile
chips.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Telegram's webhook is registered automatically at startup. No inbound ports other than 80/443 are needed.

### Railway (recommended)

The Dockerfile is the deployment unit: its `CMD` runs `alembic upgrade head` and then the bot, so Railway
does not need a custom build or start command.

1. Push this repository to GitHub, then in Railway choose **New Project → Deploy from GitHub repo** and
   select it. Railway detects the Dockerfile automatically.
2. Choose **New → Database → PostgreSQL**. Wait until it is healthy.
3. Open the bot service → **Variables** and add:

   | Variable | Value |
   |---|---|
   | `BOT_TOKEN` | The BotFather token. Set it in the dashboard only, never in Git. |
   | `OWNER_TELEGRAM_ID` | Your numeric Telegram ID. |
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (use your database service's name if different). |
   | `MODE` | `polling` |
   | `STARTING_BALANCE` | `0` |

   All other settings are optional; see [Configuration](#configuration). Railway's Postgres URL is accepted
   as-is, including `postgres://`, `postgresql://` and `sslmode=require`.
4. Deploy. The logs should show Alembic running, then `starting ChipCity` and `polling mode`. No public
   domain, port or health check is needed in polling mode; Railway can run the service as a worker.
5. DM the bot `/start`, then credit Chips from the owner account: `/addcredits <your_id> 10000`.

For webhook mode instead: set `MODE=webhook`, add `WEBHOOK_URL=https://<your-service>.up.railway.app`,
and expose a Railway domain. The app binds `0.0.0.0` and reads Railway's injected `PORT`; `/health` is
available for a Railway health check.

### Render

Create a **Background Worker** from the Dockerfile (polling mode), attach a Render PostgreSQL instance and
set the same variables. Webhooks are also supported on a Web Service with `MODE=webhook`.

### PostgreSQL vs SQLite

SQLite is fine for a small friend group and local development. For production, use PostgreSQL so row locks
(`SELECT … FOR UPDATE`) serialize concurrent settlements properly. The wallet also holds per-user asyncio
locks in-process, so a single bot instance is safe either way.

---

## Commands

### Everyone

| Command | Description |
|---|---|
| `/start` | Register, show the disclaimer and category menu. |
| `/help` | Every command and the disclaimer. |
| `/games` | All games and their keys. |
| `/play <game> <bet>` | Quick play, e.g. `/play dice 100`, `/play mines 2.5k`. |
| `/rules <game>` | Rules, edge and theoretical RTP. |
| `/balance` | Balance in Chips. |
| `/resume` | Reopen an unfinished round. |
| `/history` | Last bets, paginated. |
| `/stats` | Wagered, won, biggest payout, favourite game. |
| `/leaderboard` | Global (DM) or this chat's (group) leaderboard. |
| `/fairness` | Current server hash, client seed, nonce. |
| `/setseed <text>` | Change your client seed. |
| `/rotateseed` | Reveal the old server seed; start a new commitment. |
| `/verify <bet_id>` | Check a settled bet. |
| `/limit daily <chips>` | Daily wagering cap; `0` removes it. |
| `/pause <hours>` | Cool-off break. |
| `/bet <selection> <chips>` | Add a typed roulette bet while a slip is open. |

Bet shortcuts: `min`, `max`, `half`, `1k`, `2.5k`, `1m`.

### Groups

| Command | Description |
|---|---|
| `/crash <bet>` | Open a 10-second shared Crash lobby; buttons pick an auto-cash-out target. |
| `/slide <bet>` | Shared Slide round; each player picks a target. |
| `/duel <bet>` | Challenge the chat; another player taps Accept. |
| `/leaderboard` or `/groupstats` | This chat's top players. |

Buttons on a bet only work for the player who placed it. Anyone else gets "This isn't your game."

### Owner only

| Command | Description |
|---|---|
| `/addcredits <@user\|id> <chips> [note]` | Create Chips (the only way Chips enter circulation). |
| `/removecredits <@user\|id> <chips> [note]` | Remove Chips. |
| `/setbalance <@user\|id> <chips>` | Set an exact balance (ledger `RESET` row). |
| `/resetuser <@user\|id>` | Reset one player to zero. |
| `/resetall` | Reset every balance after a confirm button. |
| `/ban` / `/unban <@user\|id>` | Block or restore play. |
| `/userinfo <@user\|id>` | Balance, ledger history, recent bets. |
| `/toggle <game> on\|off` | Enable/disable a game. |
| `/setedge <game> <percent>` | Change house edge; adjustable games rescale at settlement. |
| `/setlimits <game> <min> <max>` | Per-game limits in Chips. |
| `/broadcast <text>` | Send to every player after a confirm button. |
| `/audit` | Compare every balance with its ledger sum. |
| `/export` | CSV of users and ledger rows. |
| `/botstats` | Bets, wagered, house P/L, actual vs theoretical RTP. |

Non-owners see only "Unknown command." for admin commands.

---

## Game list and RTP

Thirty registrations (the three slot machines share one engine). RTP is measured/theoretical as documented in
[DECISIONS.md](DECISIONS.md); the Monte Carlo run is in [RTP_REPORT.md](RTP_REPORT.md).

| Game | Key | Category | Theoretical RTP |
|---|---|---|---|
| Dice | `dice` | instant | 98.99% |
| Limbo | `limbo` | instant | 99.00% |
| Coin Flip | `coinflip` | instant | 99.00% |
| Plinko | `plinko` | instant | 99.14% |
| Keno | `keno` | instant | 99.00% |
| Diamonds | `diamonds` | instant | 99.00% |
| Cases | `cases` | instant | 98.86% |
| Bars | `bars` | instant | 98.99% |
| Tarot | `tarot` | instant | 98.94% |
| Darts | `darts` | instant | 99.00% |
| Sic Bo | `sicbo` | instant | 97.22% |
| Rock Paper Scissors | `rps` | instant | 99.00% |
| Slide | `slide` | instant | 99.12% |
| Mines | `mines` | risk | 98.99% |
| Dragon Tower | `dragontower` | risk | 99.00% |
| Pump | `pump` | risk | 99.00% |
| Chicken | `chicken` | risk | 99.00% |
| Moles | `moles` | risk | 98.99% |
| Snakes | `snakes` | risk | 99.00% |
| HiLo | `hilo` | cards | 99.00% |
| Blackjack | `blackjack` | cards | 99.54% |
| Baccarat | `baccarat` | cards | 98.94% |
| Video Poker | `videopoker` | cards | 99.54% |
| Wheel | `wheel` | wheel | 98.90% |
| Roulette | `roulette` | wheel | 97.30% |
| Pharaoh Spin | `pharaoh` | slots | 99.11% |
| Ronin Reels | `ronin` | slots | 99.02% |
| Spell Book | `spellbook` | slots | 98.97% |
| Crash | `crash` | group | 99.00% |
| Dice Duel | `duel` | group | 99.00% |

Roulette, Sic Bo, Baccarat, Blackjack and Video Poker use their standard casino rules and therefore their
fixed house edges, not the 1% default. `MAX_PROFIT_PER_BET` can lower the realised RTP on extreme multipliers;
the published tables assume the cap is not hit.

---

## Provable fairness

Every bet uses the standard HMAC-SHA256 scheme:

```
byte_chunk(cursor) = HMAC_SHA256(key=server_seed, msg=f"{client_seed}:{nonce}:{cursor}")[0:4]
value              = int(byte_chunk) / 2**32          # uniform in [0, 1)
```

- The server seed is 32 random bytes from `secrets`. Before play only `SHA256(server_seed)` is shown.
- The player may change their client seed at any time; the nonce increases once per bet.
- All shuffles (cards, mines, keno, reels) are Fisher–Yates driven by these values.
- `/fairness` shows the hash, client seed and nonce.
- `/rotateseed` sets the old seed inactive, reveals it, and commits to a new hash.
- `/verify <bet_id>` replays the stored HMAC chunks from the revealed seed and compares them with the stored
  proof. Before rotation it confirms the commitment and the number of stored values; full HMAC verification
  needs the revealed seed (this is deliberate — revealing a live seed would leak all future bets).
- Group rounds store their per-round seed in the round message and reveal it at the end.

No game uses Python's `random` module for outcomes.

---

## How a bet flows

1. Validate user (ban, pause, daily limit), game (enabled, limits) and balance.
2. Reserve the next nonce and lock the user row.
3. Debit the stake and write a `BET` ledger row.
4. Run the game's pure state machine with the fair RNG.
5. On finish: cap the payout, credit `WIN`, update the bet/ledger in the same transaction.
6. On multi-step action: persist state + HMAC proof + cursor, bump the step number.
7. Stale/duplicate callbacks are rejected by `(bet_id, step)`; the engine is idempotent.
8. On timeout the round is auto-cashed-out at its locked multiplier (or forfeited where a cash-out value does
   not exist, e.g. blackjack); the behaviour is stated in the game text.

---

## Tests and RTP report

```bash
.venv/bin/python -m pytest -q          # 114 tests
.venv/bin/ruff check bot tests scripts
.venv/bin/mypy bot
.venv/bin/python -m scripts.rtp_report --rounds 100000 --slow-rounds 20000
```

- `tests/test_fairness.py` — determinism, HMAC vectors, shuffle.
- `tests/test_wallet.py` — 1,000 concurrent credits/debits; balance always equals the ledger sum.
- `tests/test_engine.py` — settle once, stale callbacks, timeout, refund, caps, daily limits, edge scaling.
- `tests/test_games.py` — payout math and validation for every game.
- `tests/test_all_games.py` — every game through the real engine, plus group settlement.
- `tests/test_rtp_simulation.py` — Monte Carlo against theoretical RTP with reported standard error.

The spec's full 1,000,000-round run:

```bash
SIM_ROUNDS=1000000 SIM_ROUNDS_SLOW=1000000 .venv/bin/python -m pytest tests/test_rtp_simulation.py -s
```

`scripts/rtp_report.py --rounds 1000000 --slow-rounds 200000 --markdown RTP_REPORT.md` writes the full table.
The checked-in [RTP_REPORT.md](RTP_REPORT.md) was produced with 100,000 fast / 20,000 slow rounds.

---

## Project layout

```
bot/
  main.py                startup, routers, polling/webhook, timeout job
  config.py              env settings, chip↔cent helpers
  db/                    models, session factory, repository, Alembic migrations
  core/
    wallet.py            the only place balances change (ledger + locks)
    fairness.py          HMAC RNG and seed lifecycle
    bet_engine.py        validate → debit → play → settle/refund, edge scaling
    rate_limit.py        per-user token bucket
  games/                 one plugin per game + registry + shared payout helpers
  handlers/              user, play, admin, group routers and UI helpers
  render/boards.py       Pillow images
  texts/en.py            shared strings (game copy lives beside each plugin)
tests/                   pytest suite and Monte Carlo strategies
scripts/                 RTP report and audit CLI
DECISIONS.md             assumptions, payout tables, RTP math
docker-compose.yml       bot + PostgreSQL + Redis
```

---

## Adding game #31

Games are plugins. Create `bot/games/mygame.py`:

```python
from bot.games.base import BaseGame, Round, Starter
from bot.games.registry import register


@register
class MyGame(BaseGame):
    key = "mygame"
    name = "My Game"
    emoji = "🎲"
    category = "instant"
    rules_text = "Roll over 50 to win 1.98x. Outcomes come from the fair RNG."

    def quick_starts(self):
        return [Starter("Play", {"mode": "standard"})]

    def validate(self, raw):
        return {"mode": raw.get("mode", "standard")}

    def start(self, rng, params, stake):
        roll = rng.next() * 100
        won = roll > 50
        return Round(
            finished=True,
            multiplier=1.98 if won else 0.0,
            status="WON" if won else "LOST",
            text=f"Rolled {roll:.2f}",
            detail={"roll": roll},
        )
```

Add `mygame` to the imports in `bot/games/__init__.py`, define `theoretical_rtp()` if you want it reported,
and add a test. No engine, handler, wallet or admin changes are needed: the registry drives the menus, the
engine settles the stake, and `/botstats` includes the new RTP.

---

## Backups and restore

**PostgreSQL**

```bash
# backup
docker compose exec -T db pg_dump -U chipcity chipcity > chipcity-$(date +%F).sql
# restore (empty database)
cat chipcity-2026-11-14.sql | docker compose exec -T db psql -U chipcity chipcity
```

**SQLite**

Stop the bot, copy `data/chipcity.db` (plus `-wal`/`-shm` if present), restart. Restore by replacing the file
while the bot is stopped. Test a restore on a copy before relying on it.

Ledger rows are append-only from the bot's perspective; `/audit` verifies every balance against its ledger.

---

## Operational notes

- **One bot instance per SQLite database.** For multiple instances use PostgreSQL and set `REDIS_URL`;
  the rate limiter currently ships with the in-process bucket, so multi-instance flood control would need a
  Redis-backed implementation behind the same `check()` interface.
- **Group Crash/Slide use auto-cash-out targets.** A shared round cannot rely on everyone tapping in time;
  solo Crash supports manual cash-out with a live message.
- **Telegram editing.** The bot edits one message per solo Crash round about every 1.2 s and group rounds
  every 2 s, well inside Telegram's limits. Multi-step games edit their own message.
- **Payment code does not exist.** There is no deposit, withdrawal, Telegram Stars, wallet, transfer, tip or
  redemption flow. Do not add one: it would change the legal character of the bot.
- **Locale.** Shared strings are in `texts/en.py`; game-specific copy sits beside each plugin so a second
  language can be added without touching the engine.
- **Logs** are JSON (one object per line) with rotation; webhook secret and bot token are never logged.
