"""Telegram Tech News Bot - v4

Fetches tech RSS headlines from multiple trusted sources, clusters related
stories, rewrites them with AI into a fixed Telegram format, and posts
regular digest stories on a fixed schedule, with urgent stories checked
separately and posted anytime.

Schedule:
  - Regular digest: fixed times at 5am and 5pm (DIGEST_SCHEDULE_HOUR_AM/PM)
  - Urgent keyword check: hourly, posts immediately regardless of time
  - Use /fetch for on-demand checks (subject to cooldown)

Setup:
  pip install -e .

Env vars needed — create a .env file in this folder (see .env.example):
    TELEGRAM_BOT_TOKEN     - from @BotFather
    GROQ_API_KEY           - your Groq API key (console.groq.com/keys, free tier)

How people join:
    Anyone sends /start to the bot once. They're saved to subscribers.json
    and get every future news post automatically. /stop unsubscribes.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import threading
import time as time_mod

from telegram.ext import Application, CommandHandler, ContextTypes, filters

from newsbot.bot import fetch_and_post, fetch_urgent_and_post
from newsbot import config
from newsbot.config import (
    DIGEST_SCHEDULE_HOUR_AM,
    DIGEST_SCHEDULE_HOUR_PM,
    DONATION_QR_IMAGE,
    DONATION_SCHEDULE_HOUR,
    FETCH_COOLDOWN_SECONDS,
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
# httpx logs the full request URL at INFO level, which includes the bot
# token (api.telegram.org/bot<TOKEN>/...). Silence it so the token never
# ends up in logs again.
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

_fetch_last_run: dict[int, float] = {}


async def poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fixed-schedule digest job — runs at 5am and 5pm, posts new stories found since last run."""
    await fetch_and_post(context)


async def urgent_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hourly urgent check — keyword matches not already posted."""
    await fetch_urgent_and_post(context)


DONATION_TEXT_KM = (
    "🧩 <b>ចូលរួមជាមួយយើង ដើម្បីស្វែងយល់ពីរឿងរ៉ាវគ្រប់ជ្រុងជ្រោយ</b>\n\n"
    "ដើម្បីផ្តល់ជូនលោកអ្នកនូវទិដ្ឋភាពព័ត៌មានពេញលេញ Inbound Reports "
    "មិនពឹងផ្អែកលើទស្សនៈតែមួយជ្រុងនោះទេ។ វេទិការបស់យើងធ្វើការប្រមូលផ្តុំព័ត៌មានបច្ចេកវិទ្យាពីប្រភពចម្រុះ "
    "និង APIs ពីបណ្តាញអ៊ីនធឺណិត ដើម្បីនាំយកគ្រប់ទិដ្ឋភាពទាំងអស់មកដាក់បញ្ចូលគ្នានៅកន្លែងតែមួយ។\n\n"
    "តាមរយៈការប្រៀបធៀបប្រភពព័ត៌មាន យើងជួយដល់អ្នកអាននៅកម្ពុជាឱ្យ៖\n\n"
    "🌐 ចៀសផុតពីភាពរញ៉េរញ៉ៃនៃព័ត៌មាន និងមិនជាប់ផុងក្នុងការទទួលព័ត៌មានតែមួយជ្រុង។\n"
    "⚖️ ទទួលបានទស្សនៈប្រកបដោយតុល្យភាព ជុំវិញវិស័យបច្ចេកវិទ្យា។\n"
    "📖 ស្វែងយល់ពីសាច់រឿងទាំងមូល ដើម្បីចូលរួមលើកកម្ពស់អក្ខរកម្មឌីជីថលនៅកម្ពុជា។\n\n"
    "ការដំណើរការប្រព័ន្ធប្រមូលផ្តុំទិន្នន័យនេះ រួមជាមួយនឹងការចំណាយលើការទាញយកទិន្នន័យ "
    "ទាមទារឱ្យមានធនធានច្រើន។ ប្រសិនបើលោកអ្នកឱ្យតម្លៃទៅលើវេទិកាព័ត៌មានដែលផ្តល់នូវតុល្យភាព "
    "និងមានប្រភពចម្រុះ សូមមេត្តាពិចារណាចូលរួមគាំទ្រដល់ការងាររបស់យើងខ្ញុំ!\n\n"
    "👇 លោកអ្នកអាចធ្វើការចូលរួមវិភាគទានយ៉ាងងាយស្រួល និងរហ័ស "
    "តាមរយៈតំណភ្ជាប់ ABA ខាងក្រោម៖\n\n"
    '🔗 <a href="https://pay.ababank.com/oRF8/puropy03">ABA Payment Link</a>'
)

DONATION_TEXT = (
    "🧩 <b>Help Us Connect the Dots</b>\n\n"
    "To give you the full picture, Inbound Reports doesn't just rely on one perspective. "
    "Our platform aggregates tech news from multiple sources and APIs across the web, "
    "putting every angle in one place.\n\n"
    "By comparing sources, we help Cambodian readers:\n\n"
    "🌐 Step outside the noise and avoid echo chambers.\n"
    "⚖️ Access balanced perspectives from across the tech landscape.\n"
    "📖 See the complete story to build better digital literacy.\n\n"
    "Running this aggregation engine—and paying for data access—takes resources. "
    "If you value having a balanced, multi-source feed, please consider supporting our work!\n\n"
    "👇 Tap the ABA link below to make a quick contribution:\n\n"
    '🔗 <a href="https://pay.ababank.com/oRF8/puropy03">ABA Payment Link</a>'
)


async def donation_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send donation message with QR image to channel and text to group chat at 10 PM."""
    # --- channel target ---
    channel_id = config.TELEGRAM_CHANNEL_ID
    thread_id = config.TELEGRAM_THREAD_ID
    if channel_id is None:
        raw_channel = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
        if raw_channel:
            try:
                channel_id = int(raw_channel)
            except (ValueError, TypeError):
                pass
        raw_thread = os.environ.get("TELEGRAM_THREAD_ID", "").strip()
        if raw_thread:
            try:
                thread_id = int(raw_thread)
            except (ValueError, TypeError):
                pass

    # --- group chat target ---
    group_chat_id = config.TELEGRAM_GROUP_CHAT_ID
    if group_chat_id is None:
        raw_group = os.environ.get("TELEGRAM_GROUP_CHAT_ID", "").strip()
        if raw_group:
            try:
                group_chat_id = int(raw_group)
            except (ValueError, TypeError):
                pass

    qr_path = DONATION_QR_IMAGE

    # Send to channel: Khmer first (with QR image), then English
    if channel_id is not None:
        try:
            if os.path.isfile(qr_path):
                with open(qr_path, "rb") as f:
                    await context.bot.send_photo(
                        chat_id=channel_id,
                        photo=f,
                        caption=DONATION_TEXT_KM,
                        parse_mode="HTML",
                    )
            else:
                await context.bot.send_message(
                    chat_id=channel_id,
                    text=DONATION_TEXT_KM,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            await context.bot.send_message(
                chat_id=channel_id,
                text=DONATION_TEXT,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            if thread_id is not None:
                logger.info("Donation message sent to channel %s thread %s", channel_id, thread_id)
            else:
                logger.info("Donation message sent to channel %s", channel_id)
        except Exception:
            logger.exception("Failed to send donation message to channel %s", channel_id)

    # Send text-only donation messages to group chat (Khmer then English)
    if group_chat_id is not None and group_chat_id != channel_id:
        try:
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=DONATION_TEXT_KM,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=DONATION_TEXT,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            logger.info("Donation message sent to group chat %s", group_chat_id)
        except Exception:
            logger.exception("Failed to send donation message to group chat %s", group_chat_id)


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
    logger.info("[/start] chat_id=%s name=%s", chat_id, chat_title)

    if chat_id not in subscribers:
        subscribers.add(chat_id)
        state.save_subscribers(subscribers)
        await _reply(
            update,
            "Subscribed! Regular stories post at 5am and 5pm. Urgent alerts send anytime.",
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
    """Manual trigger: /fetch — runs a full check now and reports the outcome."""
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

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

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

    # Fixed digest schedule — regular stories post at 5am and 5pm only.
    # Urgent stories still get their own separate hourly check below.
    app.job_queue.run_daily(
        poll_job,
        time=dt.time(hour=DIGEST_SCHEDULE_HOUR_AM, minute=0, tzinfo=TIMEZONE),
    )
    app.job_queue.run_daily(
        poll_job,
        time=dt.time(hour=DIGEST_SCHEDULE_HOUR_PM, minute=0, tzinfo=TIMEZONE),
    )
    app.job_queue.run_repeating(
        urgent_job,
        interval=URGENT_CHECK_INTERVAL_SECONDS,
        first=URGENT_FIRST_DELAY_SECONDS,
    )
    app.job_queue.run_daily(
        donation_job,
        time=dt.time(hour=DONATION_SCHEDULE_HOUR, minute=0, tzinfo=TIMEZONE),
    )

    logger.info(
        "Bot running. Digest at %02d:00 and %02d:00 (%s). Donation at %02d:00. Urgent checks every %ds. Use /fetch for on-demand.",
        DIGEST_SCHEDULE_HOUR_AM,
        DIGEST_SCHEDULE_HOUR_PM,
        TIMEZONE,
        DONATION_SCHEDULE_HOUR,
        URGENT_CHECK_INTERVAL_SECONDS,
    )

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()