from __future__ import annotations

DISCLAIMER = (
    "⚠️ <b>This is a just-for-fun game.</b> Chips have no monetary value, cannot be "
    "bought, sold, transferred or redeemed."
)

BRAND = "ChipCity"
EMOJI_CHIP = "🪙"


def fmt(cents: int) -> str:
    return f"{cents / 100:,.2f}"


def money(cents: int) -> str:
    return f"{fmt(cents)} {EMOJI_CHIP}"


def fmtx(multiplier: float) -> str:
    return f"{multiplier:,.2f}x"


def chip_amount(cents: int) -> str:
    """Short form used on buttons: 1,250."""
    value = cents / 100
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


WELCOME = (
    "🎰 <b>Welcome to {brand}</b>, {name}!\n\n"
    "Play-money casino games with your friends. Every round is provably fair, "
    "and the house edge is only {edge}%.\n\n"
    "Use the menu below to pick a game, or /help for every command.\n\n"
    "{disclaimer}"
)

HELP = (
    "<b>🎮 {brand} — commands</b>\n\n"
    "<b>Play</b>\n"
    "/start – main menu\n"
    "/games – browse every game\n"
    "/play &lt;game&gt; &lt;bet&gt; – quick play (e.g. <code>/play dice 100</code>)\n"
    "/resume – continue an unfinished round\n"
    "/balance – your Chips\n"
    "/history – last 10 bets\n"
    "/stats – your stats\n"
    "/leaderboard [daily|weekly|all] – top players\n\n"
    "<b>Fairness</b>\n"
    "/fairness – current seed hash, client seed and nonce\n"
    "/setseed &lt;text&gt; – change your client seed\n"
    "/rotateseed – reveal the old server seed and start a new one\n"
    "/verify &lt;bet_id&gt; – re-check a settled bet\n\n"
    "<b>Responsible play</b>\n"
    "/limit daily &lt;chips&gt; – daily wagering cap (0 to remove)\n"
    "/pause &lt;hours&gt; – take a break\n\n"
    "{disclaimer}\n\n"
    "Bet shortcuts: <code>min</code>, <code>max</code>, <code>half</code>, <code>1k</code>, <code>2.5k</code>."
)

MENU_TITLE = (
    "🎰 <b>{brand}</b> · balance: <b>{balance}</b>\n"
    f"{EMOJI_CHIP} Play money only — no deposits, no withdrawals.\n\n"
    "Pick a category:"
)

BET_PROMPT = (
    "💵 <b>{name}</b>\n{emoji} Send your bet — for example <code>100</code>, "
    "<code>2.5k</code>, <code>max</code> or <code>half</code>."
)

INSUFFICIENT = "❌ Not enough Chips. Ask the owner for a top-up."
BANNED = "🚫 You are banned from playing."
PAUSED = "⏸ You paused play until {until} UTC. Take care of yourself."
DAILY_LIMIT = "🛑 Daily limit reached ({limit}). It resets at midnight UTC."
GAME_OFF = "🔒 This game is currently disabled by the owner."
NOT_YOURS = "This isn't your game."
STALE = "⏱ This round is already closed."
UNKNOWN = "Unknown command."
RATE_LIMITED = "🐢 Slow down a little — try again in {seconds}s."
REFUNDED = "↩️ Something went wrong and your stake was refunded."

WIN_TIERS = [
    (1000, "🌟💥 <b>LEGENDARY!</b> A {mult} hit!"),
    (100, "🔥🔥 <b>MASSIVE!</b> {mult}!"),
    (10, "🔥 <b>Huge win!</b> {mult}!"),
]

RULES = "{name} {emoji}\n\n{rules}\n\nHouse edge: {edge}%\nTheoretical RTP: {rtp}%"

HISTORY_HEADER = "<b>🧾 Your last bets</b>"
STATS = (
    "<b>📊 Your stats</b>\n"
    "Balance: <b>{balance}</b>\n"
    "Total wagered: <b>{wagered}</b>\n"
    "Total won: <b>{won}</b>\n"
    "Games played: <b>{games}</b>\n"
    "Biggest payout: <b>{biggest}</b>\n"
    "Favourite game: <b>{favourite}</b>"
)

FAIRNESS = (
    "<b>🔐 Provable fairness</b>\n\n"
    "Server seed hash: <code>{hash}</code>\n"
    "Client seed: <code>{client}</code>\n"
    "Nonce: <b>{nonce}</b>\n\n"
    "Each roll is HMAC-SHA256(server_seed, <code>client:nonce:cursor</code>). "
    "Rotate to reveal the current server seed and verify old bets with /verify."
)
