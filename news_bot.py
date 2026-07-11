"""
Telegram Tech News Bot - v3
Fetches tech RSS headlines from multiple trusted sources, clusters related
stories, rewrites them with AI into a fixed Telegram format, and broadcasts
to everyone who has messaged the bot with /start.

Schedule:
  - Digest posts at 5:00 AM and 5:00 PM (Phnom Penh time)
  - Urgent breaking news checked every 15 minutes and sent immediately

Setup:
  pip install python-telegram-bot feedparser openai pytz python-dotenv "python-telegram-bot[job-queue]"

Env vars needed — create a .env file in this folder (see .env.example):
  TELEGRAM_BOT_TOKEN   - from @BotFather
  GROQ_API_KEY         - your Groq API key (console.groq.com/keys, free tier)

How people join:
  Anyone sends /start to the bot once. They're saved to subscribers.json
  and get every future news post automatically. /stop unsubscribes.
"""

import asyncio
import json
import os
import re
import threading
from datetime import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser
import pytz
from dotenv import load_dotenv
from openai import OpenAI
from telegram.ext import Application, CommandHandler, ContextTypes, filters

load_dotenv()

# ---- Config ----
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.wired.com/feed/rss",
    "https://www.theguardian.com/technology/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://www.bleepingcomputer.com/feed/",
    "https://krebsonsecurity.com/feed/",
]

POSTED_LOG = "posted_ids.json"
SUBSCRIBERS_LOG = "subscribers.json"
MAX_ITEMS_PER_FEED = 5
GROQ_MODEL = "llama-3.3-70b-versatile"
TIMEZONE = pytz.timezone("Asia/Phnom_Penh")
URGENT_CHECK_INTERVAL_SECONDS = 15 * 60
MIN_SOURCES_NORMAL = 2
MIN_SOURCES_URGENT = 3

# Keyword heuristics for fast urgent triage before AI confirms.
URGENT_KEYWORDS = (
    "zero-day", "0-day", "critical vulnerability", "rce", "exploit",
    "data breach", "ransomware", "outage", "down globally", "major outage",
    "security incident", "product recall", "actively exploited",
    "emergency patch", "widespread outage",
)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "10000"))

# Optional: always post here (needed on Render — local subscribers.json is ephemeral)
_CHANNEL_RAW = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
TELEGRAM_CHANNEL_ID = int(_CHANNEL_RAW) if _CHANNEL_RAW else None
_THREAD_RAW = os.environ.get("TELEGRAM_THREAD_ID", "").strip()
TELEGRAM_THREAD_ID = int(_THREAD_RAW) if _THREAD_RAW else None

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


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, drop common filler words for clustering."""
    text = title.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    stop = {
        "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with",
        "as", "at", "by", "from", "is", "are", "its", "it", "this", "that",
    }
    tokens = [t for t in text.split() if t and t not in stop]
    return " ".join(tokens)


def _title_similarity(a: str, b: str) -> float:
    """Jaccard similarity over normalized title tokens."""
    sa, sb = set(_normalize_title(a).split()), set(_normalize_title(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def collect_new_entries(posted_ids: set) -> list[dict]:
    """Pull fresh entries from all feeds, skipping already-posted IDs."""
    entries = []
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        source_name = feed.feed.get("title", feed_url)
        count = 0
        for entry in feed.entries:
            if count >= MAX_ITEMS_PER_FEED:
                break
            entry_id = entry.get("id", entry.link)
            if entry_id in posted_ids:
                continue
            entries.append({
                "id": entry_id,
                "title": entry.get("title", "").strip(),
                "summary": (entry.get("summary", "") or "")[:500],
                "link": entry.link,
                "source_name": source_name,
            })
            count += 1
    return entries


def cluster_entries(entries: list[dict], threshold: float = 0.45) -> list[list[dict]]:
    """
    Group related headlines across feeds so one story can cite multiple sources.
    Greedy clustering by title similarity.
    """
    clusters: list[list[dict]] = []
    for entry in entries:
        placed = False
        for cluster in clusters:
            if _title_similarity(entry["title"], cluster[0]["title"]) >= threshold:
                cluster.append(entry)
                placed = True
                break
        if not placed:
            clusters.append([entry])
    return clusters


def looks_urgent(entries: list[dict]) -> bool:
    blob = " ".join(
        f"{e['title']} {e['summary']}" for e in entries
    ).lower()
    return any(kw in blob for kw in URGENT_KEYWORDS)


def rewrite_with_ai(cluster: list[dict], urgent: bool = False) -> str:
    """
    Produce a deterministic Telegram post. Source links are appended in code
    so the model cannot invent or omit them.
    """
    primary = cluster[0]
    links = []
    seen = set()
    for entry in cluster:
        if entry["link"] not in seen:
            seen.add(entry["link"])
            links.append(entry["link"])

    # Prefer more sources for urgent/major stories; still allow single-source
    # when nothing else has covered it yet.
    preferred = MIN_SOURCES_URGENT if urgent else MIN_SOURCES_NORMAL
    source_note = ""
    if len(links) < preferred:
        source_note = (
            f"\nNote: only {len(links)} source(s) available so far "
            f"(prefer {preferred}+ when possible)."
        )

    headlines = "\n".join(
        f"- [{e['source_name']}] {e['title']}: {e['summary'][:200]}"
        for e in cluster[:5]
    )

    if urgent:
        format_rules = """Return EXACTLY this structure (no extra sections, no preamble):
**[URGENT: <short title>]**
- What happened: <one sentence>
- Why it matters: <one sentence>
Do NOT include a Source line — sources are appended separately."""
    else:
        format_rules = """Return EXACTLY this structure (no extra sections, no preamble):
**<short title>**
- What happened: <one sentence>
- Why it matters: <one sentence>
- Extra context: <one short sentence with background or comparison>
Do NOT include a Source line — sources are appended separately.
If sources disagree on a fact, say so clearly in Extra context instead of guessing."""

    prompt = f"""You are a tech news bot writing for Telegram.
Rewrite the story below into the required format. Report facts only —
no opinions, no speculation, no buy/sell advice, no calls to action.
Never closely mirror any single article's wording.
{source_note}

Stories covering the same event:
{headlines}

{format_rules}

Return ONLY the formatted post text, nothing else."""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )
    body = response.choices[0].message.content.strip()

    # Strip any Source line the model may still emit; we own that section.
    body = re.sub(r"\n+-?\s*Sources?:.*$", "", body, flags=re.IGNORECASE | re.DOTALL).strip()

    capped = links[:3] if urgent else links[:5]
    label = "Source" if len(capped) == 1 else "Sources"
    return f"{body}\n- {label}: {' | '.join(capped)}"


async def broadcast(context: ContextTypes.DEFAULT_TYPE, posts: list[str]):
    """Send posts to the configured channel (if any) plus /start subscribers."""
    targets: dict[int, int | None] = {}

    if TELEGRAM_CHANNEL_ID is not None:
        targets[TELEGRAM_CHANNEL_ID] = TELEGRAM_THREAD_ID

    for chat_id in load_subscribers():
        targets.setdefault(int(chat_id), None)

    if not targets:
        print("No channel or subscribers configured — nothing to send.")
        return

    for chat_id, thread_id in targets.items():
        for post_text in posts:
            kwargs = {"chat_id": chat_id, "text": post_text}
            if thread_id is not None:
                kwargs["message_thread_id"] = thread_id
            try:
                await context.bot.send_message(**kwargs)
            except Exception as e:
                print(f"Failed to send to {chat_id}: {e}")


async def fetch_and_post(context: ContextTypes.DEFAULT_TYPE, urgent_only: bool = False):
    """
    Fetch feeds, cluster related stories, rewrite, and broadcast.

    urgent_only=True  -> only post clusters that look urgent (immediate alerts)
    urgent_only=False -> scheduled digest of non-urgent (and any urgent not yet sent)
    """
    posted_ids = load_posted_ids()
    entries = collect_new_entries(posted_ids)
    if not entries:
        print("No new entries.")
        return

    clusters = cluster_entries(entries)
    new_posts = []

    for cluster in clusters:
        urgent = looks_urgent(cluster)
        if urgent_only and not urgent:
            continue
        try:
            post_text = rewrite_with_ai(cluster, urgent=urgent)
            new_posts.append(post_text)
            for entry in cluster:
                posted_ids.add(entry["id"])
        except Exception as e:
            title = cluster[0].get("title", "?")
            print(f"Failed to generate post for '{title}': {e}")

    if not new_posts:
        print("No posts generated this run.")
        return

    if not urgent_only and len(new_posts) > 1:
        header = f"Tech digest — {len(new_posts)} stories\n\n"
        digest = header + "\n\n———\n\n".join(new_posts)
        await broadcast(context, [digest])
    else:
        await broadcast(context, new_posts)

    save_posted_ids(posted_ids)
    kind = "urgent" if urgent_only else "digest"
    print(f"Sent {len(new_posts)} {kind} post(s).")


async def digest_job(context: ContextTypes.DEFAULT_TYPE):
    await fetch_and_post(context, urgent_only=False)


async def urgent_job(context: ContextTypes.DEFAULT_TYPE):
    await fetch_and_post(context, urgent_only=True)


async def _reply(update, text: str):
    msg = update.effective_message
    if msg:
        await msg.reply_text(text)


async def start_command(update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone who sends /start gets subscribed to future news broadcasts."""
    subscribers = load_subscribers()
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title or update.effective_chat.first_name or "unknown"
    print(f"[/start] chat_id={chat_id}  name={chat_title}")
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers(subscribers)
        await _reply(
            update,
            "Subscribed! Digests at 5 AM / 5 PM (Phnom Penh). Urgent alerts send immediately.",
        )
    else:
        await _reply(update, "You're already subscribed.")


async def stop_command(update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from broadcasts."""
    subscribers = load_subscribers()
    chat_id = update.effective_chat.id
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        save_subscribers(subscribers)
        await _reply(update, "Unsubscribed. Send /start anytime to rejoin.")
    else:
        await _reply(update, "You weren't subscribed.")


async def fetch_command(update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger: /fetch — runs a full digest now."""
    print(f"[/fetch] from chat_id={update.effective_chat.id}")
    await _reply(update, "Fetching latest tech news...")
    await fetch_and_post(context, urgent_only=False)


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP server so Render Web Services detect an open port."""

    def do_GET(self):
        body = b"ok" if self.path in ("/", "/health") else b"not found"
        code = 200 if body == b"ok" else 404
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003 — silence access logs
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server listening on 0.0.0.0:{PORT} (/ and /health)")
    server.serve_forever()


def _add_command(app: Application, name: str, handler):
    """Register a command for DMs/groups and for channel posts."""
    app.add_handler(CommandHandler(name, handler))
    app.add_handler(CommandHandler(name, handler, filters=filters.UpdateType.CHANNEL_POSTS))


def main():
    # Bind PORT first so Render's port scanner succeeds during startup.
    threading.Thread(target=start_health_server, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    _add_command(app, "start", start_command)
    _add_command(app, "stop", stop_command)
    _add_command(app, "fetch", fetch_command)

    if TELEGRAM_CHANNEL_ID is not None:
        print(
            f"Channel target: {TELEGRAM_CHANNEL_ID}"
            + (f" thread={TELEGRAM_THREAD_ID}" if TELEGRAM_THREAD_ID else "")
        )
    else:
        print("WARNING: TELEGRAM_CHANNEL_ID not set — only /start subscribers get posts.")

    # Scheduled digests: 5:00 AM and 5:00 PM, Phnom Penh time
    app.job_queue.run_daily(digest_job, time=time(hour=5, minute=0, tzinfo=TIMEZONE))
    app.job_queue.run_daily(digest_job, time=time(hour=17, minute=0, tzinfo=TIMEZONE))

    # Urgent breaking news: poll frequently and send immediately
    app.job_queue.run_repeating(
        urgent_job,
        interval=URGENT_CHECK_INTERVAL_SECONDS,
        first=60,
    )

    print(
        "Bot running. Digests at 5 AM / 5 PM (Phnom Penh). "
        "Urgent alerts checked every 15 minutes."
    )
    # Python 3.12+ (and especially 3.14) no longer auto-creates an event loop
    # in the main thread; PTB's run_polling still expects one to exist.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling()


if __name__ == "__main__":
    main()
