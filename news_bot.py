"""
Telegram Tech News Bot - v2
Fetches tech RSS headlines, rewrites them with AI, and BROADCASTS to everyone
who has messaged the bot with /start — no manual chat ID entry needed.
Runs on a schedule (default 5:00 AM and 5:00 PM, Phnom Penh time).

Setup:
  pip install python-telegram-bot feedparser openai pytz python-dotenv --break-system-packages

Env vars needed — create a .env file in this folder (see .env.example):
  TELEGRAM_BOT_TOKEN   - from @BotFather
  GROQ_API_KEY         - your Groq API key (console.groq.com/keys, free tier)

How people join:
  Anyone (your mom, teammates, the group) just sends /start to the bot once
  (in DM, or in a group with the bot added). They're saved to subscribers.json
  and get every future news post automatically. /stop unsubscribes.
"""

import os
import json
import feedparser
from datetime import time
from openai import OpenAI
from telegram.ext import Application, CommandHandler, ContextTypes
import pytz
from dotenv import load_dotenv

load_dotenv()  # reads TELEGRAM_BOT_TOKEN / GROQ_API_KEY from a local .env file

# ---- Config ----
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]
POSTED_LOG = "posted_ids.json"                  # tracks what's already been posted
SUBSCRIBERS_LOG = "subscribers.json"            # tracks who gets news broadcasts
MAX_ITEMS_PER_RUN = 3                           # cap PER FEED, per run
GROQ_MODEL = "llama-3.3-70b-versatile"          # solid free-tier model on Groq
TIMEZONE = pytz.timezone("Asia/Phnom_Penh")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Groq exposes an OpenAI-compatible endpoint, so we just point the OpenAI
# client at Groq's base_url and use our Groq key.
client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)


def load_subscribers():
    if os.path.exists(SUBSCRIBERS_LOG):
        with open(SUBSCRIBERS_LOG, "r") as f:
            return set(json.load(f))
    return set()


def save_subscribers(ids):
    with open(SUBSCRIBERS_LOG, "w") as f:
        json.dump(list(ids), f)


def load_posted_ids():
    if os.path.exists(POSTED_LOG):
        with open(POSTED_LOG, "r") as f:
            return set(json.load(f))
    return set()


def save_posted_ids(ids):
    with open(POSTED_LOG, "w") as f:
        json.dump(list(ids), f)


def rewrite_with_ai(title: str, summary: str, link: str) -> str:
    prompt = f"""You are a tech news bot. Rewrite the following headline and summary
into a short, punchy Telegram post (max 3 sentences). Report facts only —
no opinions, no speculation, no calls to action. Keep it factual and neutral.

Headline: {title}
Summary: {summary}

Return ONLY the rewritten post text, nothing else."""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    rewritten = response.choices[0].message.content.strip()
    return f"{rewritten}\n\nSource: {link}"


async def fetch_and_post(context: ContextTypes.DEFAULT_TYPE):
    subscribers = load_subscribers()
    if not subscribers:
        print("No subscribers yet — nothing to send.")
        return

    posted_ids = load_posted_ids()
    new_posts = []

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        new_items = [entry for entry in feed.entries if entry.get("id", entry.link) not in posted_ids]
        new_items = new_items[:MAX_ITEMS_PER_RUN]

        for entry in new_items:
            entry_id = entry.get("id", entry.link)
            title = entry.get("title", "")
            summary = entry.get("summary", "")[:500]  # trim long summaries
            link = entry.link

            try:
                post_text = rewrite_with_ai(title, summary, link)
                new_posts.append(post_text)
                posted_ids.add(entry_id)
            except Exception as e:
                print(f"Failed to generate post for '{title}': {e}")

    save_posted_ids(posted_ids)

    # Broadcast every new post to every subscriber
    for chat_id in subscribers:
        for post_text in new_posts:
            try:
                await context.bot.send_message(chat_id=chat_id, text=post_text)
            except Exception as e:
                print(f"Failed to send to {chat_id}: {e}")


async def start_command(update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone who sends /start gets subscribed to future news broadcasts."""
    subscribers = load_subscribers()
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title or update.effective_chat.first_name or "unknown"
    print(f"[/start] chat_id={chat_id}  name={chat_title}")
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers(subscribers)
        await update.message.reply_text("Subscribed! You'll get news updates at 5 AM and 5 PM.")
    else:
        await update.message.reply_text("You're already subscribed.")


async def stop_command(update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from broadcasts."""
    subscribers = load_subscribers()
    chat_id = update.effective_chat.id
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        save_subscribers(subscribers)
        await update.message.reply_text("Unsubscribed. Send /start anytime to rejoin.")
    else:
        await update.message.reply_text("You weren't subscribed.")


async def fetch_command(update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger: /fetch"""
    await update.message.reply_text("Fetching latest tech news...")
    await fetch_and_post(context)


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("fetch", fetch_command))

    # Scheduled runs: 5:00 AM and 5:00 PM, Phnom Penh time
    app.job_queue.run_daily(fetch_and_post, time=time(hour=5, minute=0, tzinfo=TIMEZONE))
    app.job_queue.run_daily(fetch_and_post, time=time(hour=17, minute=0, tzinfo=TIMEZONE))

    print("Bot running. Anyone can /start to subscribe. Scheduled for 5 AM / 5 PM (Phnom Penh time).")
    app.run_polling()


if __name__ == "__main__":
    main()