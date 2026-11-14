# Decisions and game math

This file records every assumption made while building ChipCity, plus the payout rules behind each game.
All money is integer **cents** (`1 Chip = 100`); displayed balances use two decimals and thousands separators.

---

## 1. Concept and safety

- **Brand:** ChipCity, original name and copy. No Stake branding, logos, artwork or trademarked game names.
  All game names are generic mechanics (Dice, Mines, Plinko, …) or original slot names
  (Pharaoh Spin, Ronin Reels, Spell Book).
- **Play money only.** Chips have no monetary value, cannot be bought, sold, transferred or redeemed.
- **No payment code exists**, not even a stub. No deposits, withdrawals, Telegram Stars, crypto, wallets,
  gift cards, tips or player-to-player transfers.
- **Only the owner creates Chips.** `OWNER_TELEGRAM_ID` is checked server-side on every admin command.
  `STARTING_BALANCE` defaults to 0; a configured welcome balance is still an owner decision and is written as
  an `ADMIN_CREDIT` ledger row.
- The disclaimer appears on `/start` and `/help` and is stored once in `texts/en.py`.

## 2. Wallet and ledger

- `users.balance` is a cache; the **ledger is the source of truth**. Every change writes a `ledger` row with
  `balance_after`, and `wallet.credit_in_session` refuses to go negative.
- Balance changes happen only in `bot/core/wallet.py`. Bet starts, wins, refunds, admin credits/debits and
  resets all go through it.
- Concurrency: a per-user asyncio lock plus `SELECT … FOR UPDATE` (PostgreSQL) inside a transaction. SQLite
  is single-writer and uses the in-process lock. `/audit` and a test assert `balance == SUM(ledger.amount)`
  after 1,000 concurrent changes.
- Ledger types: `ADMIN_CREDIT | ADMIN_DEBIT | BET | WIN | REFUND | RESET`.
- A bet is settled exactly once: the engine re-reads the bet `FOR UPDATE` and returns early if it is no longer
  `ACTIVE`. Every callback carries `(bet_id, step)`; stale or duplicate taps raise `StaleBet`.
- `MAX_PROFIT_PER_BET` caps profit (`stake + max_profit`) and therefore the effective multiplier. This can
  lower realised RTP on extreme rolls; published RTP assumes the cap is not hit.

## 3. Fairness

- `HMAC_SHA256(server_seed, f"{client_seed}:{nonce}:{cursor}")`; first 4 bytes → float in `[0,1)`. Each game
  consumes floats in a fixed order, and the proofs are stored with the bet.
- Seeds are per user; the active server seed is hidden, only `SHA256(seed)` is shown. `/rotateseed` reveals it
  and creates a new one. `/setseed` changes the client seed without changing the stream history.
- Before rotation `/verify` proves only that the stored proof is intact and the commitment matches. Full
  HMAC verification requires the revealed seed; revealing a live seed would allow predicting every future bet.
- Group rounds generate a fresh random seed per round, display its hash in the lobby, and reveal the seed in
  the final message.
- Python's `random` is never used for outcomes. It appears only in the test simulator.

## 4. Edge handling and RTP

Default edge is 1% (`DEFAULT_HOUSE_EDGE=0.01`). Two different mechanisms are used:

1. **One-shot games** (dice, limbo, plinko, wheel, keno, diamonds, cases, bars, tarot, darts, slide, slots,
   roulette-style tables) compute payouts directly from the edge.
2. **Compounding cash-out games** (coin flip, HiLo, Dragon Tower, Pump, Chicken, Snakes) use **fair per-step
   odds** (`1/p`) and take the 1% edge **once** when the player cashes out. This keeps RTP at 99% regardless of
   how many steps the player survives. Mines and Moles recompute the multiplier from the total survival
   probability on every reveal, so their 1% is already one-shot.
3. **Fixed-table casino games** (roulette, Sic Bo, baccarat, blackjack, video poker) keep their standard rules
   and house edges. They are excluded from `/setedge` rescaling.

`/setedge` rescales settlement for adjustable games: final multiplier is multiplied by
`(1 - target_edge) / (1 - game.edge)` when the multiplier is above 1. Fixed-table games are unaffected and
say so in the admin reply.

Theoretical RTP by game (see [RTP_REPORT.md](RTP_REPORT.md) for the Monte Carlo measurements):

| Game | Key | RTP | Notes |
|---|---|---|---|
| Dice | `dice` | 98.99% | rounding to 4 decimal multipliers |
| Limbo | `limbo` | 99.00% | target payouts |
| Coin Flip | `coinflip` | 99.00% | 2× fair flips, edge at cash-out |
| Plinko | `plinko` | 99.14% | rounded table |
| Keno | `keno` | 99.00% | computed tiers |
| Diamonds | `diamonds` | 99.00% | pattern table |
| Cases | `cases` | 98.86% | rounded weighted table |
| Bars | `bars` | 98.99% | rounded weighted table |
| Tarot | `tarot` | 98.94% | product of three cards |
| Darts | `darts` | 99.00% | 20-segment board |
| Sic Bo | `sicbo` | 97.22% | Small/Big representative |
| Rock Paper Scissors | `rps` | 99.00% | draw refunds |
| Slide | `slide` | 99.12% | rounded strip |
| Mines | `mines` | 98.99% | rounding |
| Dragon Tower | `dragontower` | 99.00% | edge at cash-out |
| Pump | `pump` | 99.00% | edge at cash-out |
| Chicken | `chicken` | 99.00% | edge at cash-out |
| Moles | `moles` | 98.99% | rounding |
| Snakes | `snakes` | 99.00% | edge at cash-out |
| HiLo | `hilo` | 99.00% | edge at cash-out |
| Blackjack | `blackjack` | 99.54% | 8 decks, S17, 3:2 |
| Baccarat | `baccarat` | 98.94% | Banker with 5% commission |
| Video Poker | `videopoker` | 99.54% | 9/6 Jacks or Better, 800× royal |
| Wheel | `wheel` | 98.90% | 20-segment medium representative |
| Roulette | `roulette` | 97.30% | European single zero |
| Pharaoh Spin | `pharaoh` | 99.11% | rounded pays |
| Ronin Reels | `ronin` | 99.02% | rounded pays |
| Spell Book | `spellbook` | 98.97% | rounded pays |
| Crash | `crash` | 99.00% | any cash-out target |
| Dice Duel | `duel` | 99.00% | 1.98× winner, ties refund |

Accepted small drift comes from rounding multipliers to 2–4 decimals. Monte Carlo tolerance is derived from
the measured standard error, not a fixed ±0.5%, because rare top prizes (keno, slots, long-shot limbo) need
millions of rounds to reach that precision.

## 5. Per-game rules

### Dice
Roll is an integer `0…9999` shown as `0.00…99.99`. Under wins when `roll < target×100`; over wins when
`roll > target×100` (an exact tie loses). Win chance is computed exactly, and
`multiplier = floor((1−edge)/chance, 4dp)`. Targets are offered from 2% to 98%.

### Limbo
`result = max(1.00, floor((1−edge)/u, 2dp))` with `u` uniform in `(0,1]`. A win pays the **target**, not the
result. `P(result ≥ target) = (1−edge)/target`, so RTP is exactly 99% before rounding. Targets up to 1,000,000×.

### Coin Flip
Each correct call multiplies the bank by 2.00× at fair odds; cashing out applies 1% once, so the first
cash-out is 1.98×. Chained cash-out after *k* correct flips is `2^k × 0.99`. A wrong call loses everything.

### Plinko
8–16 rows; each row uses one fair float (`< 0.5` left, else right). The slot is the number of right moves.
Per risk, the shape is `base^|i − rows/2|` with `base = 1.45 / 2.10 / 3.40`, scaled so the binomial-weighted
mean is 0.99, then rounded to 2 decimals. A Pillow board is rendered.

### Mines
5×5 board, 1–24 mines. After *k* safe reveals, `P = C(25−m,k)/C(25,k)` and
`multiplier = floor(0.99/P, 4dp)`. Mines are placed with a Fisher–Yates shuffle from the fair stream. Cash out
any time; revealing every safe tile auto-cashes-out.

### Keno
40 numbers, 10 drawn, 1–10 picks. Paid hit tiers by risk:
`low ≥ max(1, floor(p·0.5))`, `classic ≥ max(2, ceil(p·0.6))`, `medium ≥ max(2, ceil(p·0.7))`,
`high ≥ max(3, ceil(p·0.9))`, with very low tiers removed if their fair multiplier would be under 1.
Each paid tier gets `0.99 / (tiers × P(hits))`, so the hypergeometric table sums to 99%.
Draws use two independent Fisher–Yates shuffles (picks and drawn numbers).

### HiLo
One 52-card deck per round, shuffled by the fair stream. After each card the remaining deck composition gives
`p` for higher/lower/same; a correct guess multiplies by `1/p`. The 1% edge is applied once at cash-out (or
when the deck ends). A wrong guess loses the accumulated multiplier.

### Wheel
10–50 segments. Risk shapes are tiled and scaled so the mean is 0.99:
low `[1.2,1.1,1.0,1.1,1.2,0.9]`, medium `[0,0.5,1,1.5,2,0.5]`, high `[0,0,0.5,1,2,4,8]`.
The landing segment is uniform. A Pillow wheel is rendered.

### Roulette
European single-zero wheel. Bets: straight 35:1, split 17:1, street 11:1, corner 8:1, line 5:1, dozen/column
2:1, red/black/odd/even/low/high 1:1. Zero loses all outside bets. RTP is the standard 36/37 = 97.30%.
A multi-chip slip is built with buttons and typed bets (`/bet split 1-2 100`). The slip is in memory and is
not debited until Spin, so a restart only loses the slip, never money.

### Blackjack
Eight decks reshuffled every hand. Dealer stands on soft 17. Blackjack pays 3:2. Hit, stand, double (any
two-card hand, including after a split), split up to four hands, insurance (2:1, offered on an Ace up-card).
Split aces get one card and stand. No surrender, no double-after-split restriction. Dealer peeks for
blackjack. Extra stakes for double/split/insurance are debited atomically by the engine; if the balance is
too low the action is refused. Timeout forfeits the hand (stated in the game).
Theoretical RTP 99.54% assumes strong basic strategy.

### Baccarat
Standard third-card rules with an eight-deck shoe. Player 1:1, Banker 1:1 minus 5% commission (1.95× total),
Tie 8:1. **A tie pushes Player and Banker bets** (stake returned); only the Tie bet wins on a tie. Banker RTP
98.94%, Player 98.76%.

### Video Poker
Jacks or Better, 9/6 pay table: royal 800×, straight flush 50×, four 25×, full house 9×, flush 6×, straight 4×,
three 3×, two pair 2×, jacks or better 1×. Royal is 800× for every bet size (no max-coin requirement). Hold any
cards, one draw. RTP depends on player strategy; 99.54% is the optimal-strategy figure, and the bundled test
uses a conservative simple strategy (~97%) and reports it honestly.

### Dragon Tower
Nine floors. Eggs (safe/total) and per-floor survival: easy 4/1 (75%), medium 3/1 (66.7%), hard 2/1 (50%),
expert 3/2 (33.3%), master 4/3 (25%). Each safe floor multiplies at fair odds `1/p`; the 1% edge is taken at
cash-out or on clearing the tower. `bad` positions are generated per floor from the fair stream.

### Diamonds
Five draws from seven colours. Patterns: five of a kind, four, full house, three, two pair. A plain pair pays
nothing. Payouts are `0.99 / (5 × P(pattern))`, so the pattern table returns 99%. Probabilities are computed by
enumerating the 16,807 ordered draws at import time (cached).

### Cases
Three original cases (Starter Crate, Vault Case, Dragon Hoard). Each has a list of prize multipliers and
weights; `weighted_table` assigns probabilities proportional to `weight/multiplier`, reserves a losing
probability and rescales prizes so total RTP is 99% before rounding to 2 decimals.

### Bars
Pick bar 1, 2 or 3; all three reveal a multiplier from the same weighted table (risk low/medium/high) and the
chosen bar pays. This is the documented interpretation of "payout = sum/product per rules you define": a single
column's value, not a product across bars. Weights and empty probability set the volatility; RTP is 99%.

### Tarot
22 Major Arcana, three drawn without replacement. Each card has a multiplier; the payout is their **product**.
Base card values are tiled from `[0.35 … 7.0]` and scaled by the cube root of `0.99 / mean(product)` so the exact
enumeration of all 1,540 three-card spreads returns 99%.

### Darts
20 segments, each equally likely, with risk-shaped multiplier arrays scaled to a 0.99 mean. Outcomes come from
the fair RNG; Telegram's dice animation is not used for outcomes. Rings label the result (bullseye, inner,
outer, miss).

### Sic Bo
Three dice. Standard pay table: Small (4–10) and Big (11–17) 1:1 (triples lose), Odd/Even 1:1,
totals 4/17 60:1, 5/16 30:1, 6/15 17:1, 7/14 12:1, 8/13 8:1, 9/12 and 10/11 6:1, any triple 30:1,
specific triple 180:1, specific double 10:1, specific combo 5:1. These are standard casino pays, so RTP varies
by bet (Small/Big 97.22%). Not rescaled by `/setedge`.

### Rock Paper Scissors
House picks uniformly. Win pays 1.97×; loss loses; a draw offers **Refund** (1.00×) or **Continue** the same
round. `(1.97 + 1.00)/3 = 0.99`. Continuing preserves the same EV.

### Slide
24-step strip with `v_j = round(0.99 × 24 / (24 − j), 2)`, increasing from 0.99× to 23.76×. The marker is
uniform; choosing one of the offered strip values as the target pays the target when the stop is at or above it.
Only strip values are offered so RTP stays 99% (rounded values cause the small drift). Group Slide uses one
shared stop for everyone.

### Mines-like Moles
3×3 grid, 1–3 bombs by difficulty. Same survival-probability formula as Mines with nine holes:
`multiplier = floor(0.99 × C(9,k)/C(9−b,k), 4dp)`.

### Chicken
20 lanes; survival probability 0.95 / 0.88 / 0.75. Fair per-lane growth `1/p`; 1% edge once at cash-out.
A hit loses the accumulated multiplier.

### Snakes
100-tile board (visual progress), two dice per roll. Snake chance 10% / 17% / 25% by difficulty; survival
multiplier `1/(1−p)` per roll; edge once at cash-out. The board position is cosmetic progress, the survival roll
is the fair outcome.

### Pump
Balloon pumps; survival 92% / 82% / 68%; growth `1/p`; 1% at cash-out; cap 60 pumps. A pop loses everything.

### Crash
Crash point `max(1.00, floor(0.99/(1−u), 2dp))`. The multiplier grows as `1.06^(seconds elapsed)`. Manual
players tap cash out before the crash; auto mode resolves immediately at the chosen target if
`crash ≥ target`. Any target yields 99% RTP. Group Crash uses a 10-second lobby and per-player auto targets —
a shared round cannot rely on every player tapping in time. Solo Crash edits its message every 1.2 seconds.

### Dice Duel
Group challenge: both players stake the same amount. Each rolls 1–100 from a fresh fair stream; higher wins
`1.98 ×` their stake (the 2% difference is burned, not credited anywhere), ties refund both. Starting RTP 99%.
No chips are debited until the challenge is accepted, which avoids stranded stakes.

## 6. Sessions, limits and UX

- One active round per user **per game**. Starting another is refused with a link to `/resume`.
- Multi-step state lives in `bets.result` (JSON) rather than Redis: it survives restarts and keeps the ledger
  and the game state in the same transaction. Redis remains optional for a shared rate limiter.
- Timeout (default 10 minutes) auto-cashes-out at the locked multiplier; games without a meaningful cash-out
  value (blackjack, video poker) forfeit, and their texts say so.
- Payout messages show stake, multiplier, payout, balance, bet id, and Play again/Double/Half/Rules buttons.
- Bet shortcuts `min/max/half/1k/2.5k/1m`; values parse to cents without floats in the wallet.
- Gambling-adjacent UX safeguards: `/limit daily`, `/pause`, bans, per-user rate limit (3 bets/s), max bet,
  max profit, owner audit and CSV export.
- Group buttons validate the owning user and the chat id. Others receive "This isn't your game."
- Telegram edit rates: one edited message per live round, 1.2 s solo / 2 s group. Multi-step games edit in place.
- No sounds, GIFs or external assets. Images are generated locally with Pillow.

## 7. Deployment and operations

- SQLite is the dev default; PostgreSQL + Redis is the production Compose stack.
- Long polling for dev/Railway workers; webhook mode uses aiohttp and registers the secret token at startup.
- Graceful shutdown cancels the timeout job, refunds open group-round stakes, auto-settles active bets and
  disposes the engine. Startup reuses the same engine.
- Logs are JSON lines with rotation; tokens/secrets are never logged.
- Alembic's initial revision calls `Base.metadata.create_all`, so a fresh database matches the ORM; later
  changes should use normal Alembic revisions.
- Docker runs as an unprivileged user; data and logs are mounted volumes.

## 8. Known limitations / deliberate deviations

- **Redis limiter**: `REDIS_URL` is read and the interface is in place, but the shipped limiter is the
  in-process token bucket. Multi-instance deployments need a Redis-backed `check()` implementation.
- **Group Crash/Slide** use auto-cash-out targets (no per-second manual tap in a shared message). Solo Crash
  keeps manual cash-out.
- **`/setedge`** rescales adjustable games at settlement; it does not regenerate cached Plinko/Wheel/Slot
  probability tables. Rounding means the realised RTP is within a few hundredths of the target.
- **Fairness verification before rotation** cannot recompute HMACs (the seed is secret); it verifies the
  commitment and integrity of the stored proof. Full recomputation works after `/rotateseed`.
- **Localization**: common strings are in `texts/en.py`; per-game copy lives beside each plugin rather than in
  one file, so adding Hindi/Marathi means translating both places. No locale switch is implemented.
- **Blackjack/Video Poker RTP** is strategy-dependent; the bundled tests report the measured result for the
  conservative strategies they implement, not an assertion that every player achieves 99.5%.
- **Slot RTP** is computed from the rounded published pay table and reported by the same function, so the
  table and the report cannot disagree.
- **Roulette/Sic Bo/Baccarat** deliberately keep standard casino pay tables; they are not forced to 99%.
- **Admin confirmations** are sent to the invoking chat. Used from the owner's DM this is the owner's DM;
  group invocations are confirmed in the group rather than duplicating every message privately.

## 9. Testing evidence

- 114 tests pass (`pytest -q`), including 1,000 concurrent wallet changes and every game through the real
  engine.
- `tests/test_rtp_simulation.py` checks 27 configurations plus blackjack and video poker against theoretical
  values with 4× standard-error tolerances; the checked-in report uses 100k/20k rounds.
- `scripts/rtp_report.py` reproduces the report; the spec's 1,000,000-round run is documented in the README.
- `/audit` verifies ledger consistency in production; `/botstats` compares actual vs theoretical RTP per game.
