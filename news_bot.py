"""Telegram Tech News Bot - v4

Fetches tech RSS headlines from multiple trusted sources, clusters related
stories, rewrites them with AI into a fixed Telegram format, and broadcasts
to everyone who has messaged the bot with /start.

Schedule:
  - Digest posts at 5 AM and 5 PM (Phnom Penh time) — up to 10 stories
  - Urgent keyword check once per hour
  - Use /fetch for on-demand digests

Setup:
  pip install -e .

Env vars needed — create a .env file in this folder (see .env.example):
  TELEGRAM_BOT_TOKEN   - from @BotFather
  GROQ_API_KEY         - your Groq API key (console.groq.com/keys, free tier)

How people join:
  Anyone sends /start to the bot once. They're saved to subscribers.json
  and get every future news post automatically. /stop unsubscribes.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time as time_mod
from datetime import time as dt_time

from telegram.ext import Application, CommandHandler, ContextTypes, filters

from newsbot.bot import fetch_and_post, fetch_urgent_and_post
from newsbot.config import (
    DIGEST_SCHEDULE_HOUR_AM,
    DIGEST_SCHEDULE_HOUR_PM,
    FETCH_COOLDOWN_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_THREAD_ID,
    TIMEZONE,
    URGENT_CHECK_INTERVAL_SECONDS,
    URGENT_FIRST_DELAY_SECONDS,
    validate_config,
)
from newsbot.health import start_health_server
from newsbot.state import get_state

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_fetch_last_run: dict[int, float] = {}


async def digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled digest job — up to 10 stories."""
    await fetch_and_post(context)


async def urgent_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hourly urgent check — keyword matches not already posted."""
    await fetch_urgent_and_post(context)


async def _reply(update: object, text: str) -> None:
    """Reply to a Telegram message (works for DMs, groups, and channels)."""
    msg = getattr(update, "effective_message", None)
    if msg:
        await msg.reply_text(text)


async def start_command(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Subscribe the current chat to future news broadcasts."""
    state = get_state()
    subscribers = state.load_subscribers()
    effective_chat = getattr(update, "effective_chat", None)
    chat_id = effective_chat.id if effective_chat else 0
    chat_title = (effective_chat.title or effective_chat.first_name or "unknown") if effective_chat else "unknown"
    logger.info("[/start] chat_id=%s  name=%s", chat_id, chat_title)
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        state.save_subscribers(subscribers)
        await _reply(
            update,
            "Subscribed! Digests at 5 AM / 5 PM (Phnom Penh). Urgent news is checked every hour.",
        )
    else:
        await _reply(update, "You're already subscribed.")


async def stop_command(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unsubscribe from broadcasts."""
    state = get_state()
    subscribers = state.load_subscribers()
    effective_chat = getattr(update, "effective_chat", None)
    chat_id = effective_chat.id if effective_chat else 0
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        state.save_subscribers(subscribers)
        await _reply(update, "Unsubscribed. Send /start anytime to rejoin.")
    else:
        await _reply(update, "You weren't subscribed.")


async def fetch_command(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manual trigger: /fetch — runs a digest now and reports the outcome."""
    effective_chat = getattr(update, "effective_chat", None)
    chat_id = effective_chat.id if effective_chat else 0

    now = time_mod.time()
    last_run = _fetch_last_run.get(chat_id, 0)
    remaining = FETCH_COOLDOWN_SECONDS - (now - last_run)
    if remaining > 0:
        minutes = int(remaining // 60) + 1
        await _reply(update, f"Please wait {minutes} minute{'s' if minutes > 1 else ''} before requesting another fetch.")
        return

    logger.info("[/fetch] from chat_id=%s", chat_id)
    _fetch_last_run[chat_id] = now
    await _reply(update, "Fetching latest tech news...")
    try:
        posted_count = await fetch_and_post(context)
    except Exception:
        logger.exception("[/fetch] fetch_and_post raised for chat_id=%s", chat_id)
        await _reply(update, "Couldn't fetch news right now — something went wrong. Check the logs.")
        return

    if posted_count == 0:
        await _reply(update, "No new updates right now — checked all feeds, nothing new to post.")
    else:
        await _reply(update, f"Posted {posted_count} new stor{'y' if posted_count == 1 else 'ies'}.")


def _add_command(app: Application, name: str, handler: object) -> None:
    """Register a command for DMs/groups and for channel posts."""
    app.add_handler(CommandHandler(name, handler))  # type: ignore[arg-type]
    app.add_handler(CommandHandler(name, handler, filters=filters.UpdateType.CHANNEL_POSTS))  # type: ignore[arg-type]


def main() -> None:
    """Entry point — initialize all subsystems and start the bot."""
    validate_config()

    threading.Thread(target=start_health_server, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    _add_command(app, "start", start_command)
    _add_command(app, "stop", stop_command)
    _add_command(app, "fetch", fetch_command)

    if TELEGRAM_CHANNEL_ID is not None:
        logger.info(
            "Channel target: %s%s",
            TELEGRAM_CHANNEL_ID,
            f" thread={TELEGRAM_THREAD_ID}" if TELEGRAM_THREAD_ID else "",
        )
    else:
        logger.warning("TELEGRAM_CHANNEL_ID not set — only /start subscribers get posts.")

    if app.job_queue is None:
        raise RuntimeError("job_queue must be available (install python-telegram-bot[job-queue])")

    app.job_queue.run_daily(digest_job, time=dt_time(hour=DIGEST_SCHEDULE_HOUR_AM, minute=0, tzinfo=TIMEZONE))
    app.job_queue.run_daily(digest_job, time=dt_time(hour=DIGEST_SCHEDULE_HOUR_PM, minute=0, tzinfo=TIMEZONE))
    app.job_queue.run_repeating(
        urgent_job,
        interval=URGENT_CHECK_INTERVAL_SECONDS,
        first=URGENT_FIRST_DELAY_SECONDS,
    )

    logger.info(
        "Bot running. Digests at %d:00 / %d:00 (Phnom Penh). "
        "Urgent checks hourly. Use /fetch for on-demand.",
        DIGEST_SCHEDULE_HOUR_AM,
        DIGEST_SCHEDULE_HOUR_PM,
    )

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
