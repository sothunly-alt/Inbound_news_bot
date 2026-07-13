"""Telegram Tech News Bot - v3

Fetches tech RSS headlines from multiple trusted sources, clusters related
stories, rewrites them with AI into a fixed Telegram format, and broadcasts
to everyone who has messaged the bot with /start.

Schedule:
  - Digest posts at 5:00 AM and 5:00 PM (Phnom Penh time)
  - Use /fetch for on-demand news

Setup:
  pip install -r requirements.txt

Env vars needed — create a .env file in this folder (see .env.example):
  TELEGRAM_BOT_TOKEN   - from @BotFather
  GROQ_API_KEY         - your Groq API key (console.groq.com/keys, free tier)

How people join:
  Anyone sends /start to the bot once. They're saved to subscribers.json
  and get every future news post automatically. /stop unsubscribes.
"""

import asyncio
import logging
import threading
from datetime import time as dt_time

from telegram.ext import Application, CommandHandler, ContextTypes, filters

from bot import fetch_and_post
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_THREAD_ID,
    TIMEZONE,
)
from health import start_health_server
from state import get_state

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled digest job — all new stories at 5 AM and 5 PM."""
    await fetch_and_post(context)


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
            "Subscribed! Digests at 5 AM / 5 PM (Phnom Penh). Urgent alerts send immediately.",
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
    """Manual trigger: /fetch — runs a full digest now and reports the outcome."""
    effective_chat = getattr(update, "effective_chat", None)
    chat_id = effective_chat.id if effective_chat else "?"
    logger.info("[/fetch] from chat_id=%s", chat_id)
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
    # Bind PORT first so Render's port scanner succeeds during startup.
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

    # Scheduled digests: 5:00 AM and 5:00 PM, Phnom Penh time
    assert app.job_queue is not None, "job_queue must be available (install python-telegram-bot[job-queue])"
    app.job_queue.run_daily(digest_job, time=dt_time(hour=5, minute=0, tzinfo=TIMEZONE))
    app.job_queue.run_daily(digest_job, time=dt_time(hour=17, minute=0, tzinfo=TIMEZONE))

    logger.info(
        "Bot running. Digests at 5 AM / 5 PM (Phnom Penh). Use /fetch for on-demand."
    )

    # Python 3.12+ no longer auto-creates an event loop in the main thread
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling()


if __name__ == "__main__":
    main()