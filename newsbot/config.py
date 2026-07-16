"""Configuration constants and environment variable loading."""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

__all__ = [
    "validate_config",
    "create_groq_client",
    "REDIS_URL",
    "RSS_FEEDS",
    "MAX_ITEMS_PER_FEED",
    "MAX_ENTRY_AGE_HOURS",
    "FEED_TIMEOUT_SECONDS",
    "CLUSTER_SIMILARITY_THRESHOLD",
    "CLUSTER_TITLE_WEIGHT",
    "CLUSTER_SUMMARY_WEIGHT",
    "CONTENT_DEDUP_THRESHOLD",
    "GROQ_MODEL",
    "GROQ_BASE_URL",
    "GROQ_MAX_TOKENS",
    "TIMEZONE",
    "DIGEST_MIN_SOURCES",
    "DIGEST_MAX_STORIES",
    "DIGEST_SCHEDULE_HOUR_AM",
    "DIGEST_SCHEDULE_HOUR_PM",
    "URGENT_CHECK_INTERVAL_SECONDS",
    "URGENT_FIRST_DELAY_SECONDS",
    "MAX_URGENT_POSTS_PER_RUN",
    "URGENT_KEYWORDS",
    "URGENCY_LEVELS",
    "NEWS_CATEGORIES",
    "POSTED_LOG",
    "SUBSCRIBERS_LOG",
    "FETCH_COOLDOWN_SECONDS",
    "LINK_CAP_URGENT",
    "LINK_CAP_NORMAL",
    "TELEGRAM_BOT_TOKEN",
    "PORT",
    "TELEGRAM_CHANNEL_ID",
    "TELEGRAM_THREAD_ID",
]

# ---- Redis (optional — enables persistent state on Railway/Render) ----
REDIS_URL: str = os.environ.get("REDIS_URL", "").strip()

# ---- RSS ----
RSS_FEEDS: list[str] = [
    # Startups
    "https://techcrunch.com/feed/",
    "https://techfundingnews.com/feed/",
    "https://techstartups.com/feed/",
    # AI & ML
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://medium.com/feed/tag/artificial-intelligence",
    # Cybersecurity
    "https://www.bleepingcomputer.com/feed/",
    "https://krebsonsecurity.com/feed/",
    "https://medium.com/feed/tag/cybersecurity",
    # DeFi & Crypto
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://medium.com/feed/tag/cryptocurrency",
    # Hardware
    "https://www.tomshardware.com/feeds/all",
    # Regulation
    "https://techpolicy.press/rss/feed.xml",
    # Science
    "https://www.sciencedaily.com/rss/top/technology.xml",
    # General Tech
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.wired.com/feed/rss",
    "https://www.theguardian.com/technology/rss",
    "https://www.technologyreview.com/feed/",
    "https://medium.com/feed/tag/technology",
    "https://medium.com/feed/better-programming",
    "https://medium.com/feed/towards-data-science",
    "https://medium.com/feed/tag/startups",
]
MAX_ITEMS_PER_FEED: int = 5
MAX_ENTRY_AGE_HOURS: int = 24
FEED_TIMEOUT_SECONDS: int = 15
FEED_GLOBAL_TIMEOUT_EXTRA: int = 10

# ---- Clustering ----
CLUSTER_SIMILARITY_THRESHOLD: float = 0.45
CLUSTER_TITLE_WEIGHT: float = 0.7
CLUSTER_SUMMARY_WEIGHT: float = 0.3
CONTENT_DEDUP_THRESHOLD: float = 0.65
SUMMARY_SIM_WORD_LIMIT: int = 100

# ---- AI ----
GROQ_MODEL: str = "llama-3.3-70b-versatile"
GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
GROQ_MAX_TOKENS: int = 500

# ---- Scheduling ----
TIMEZONE = ZoneInfo("Asia/Phnom_Penh")
DIGEST_MIN_SOURCES: int = 2
DIGEST_MAX_STORIES: int = 10
DIGEST_SCHEDULE_HOUR_AM: int = 5
DIGEST_SCHEDULE_HOUR_PM: int = 17
URGENT_CHECK_INTERVAL_SECONDS: int = 60 * 60  # once per hour
URGENT_FIRST_DELAY_SECONDS: int = 60
POLL_INTERVAL_SECONDS: int = int(os.environ.get("POLL_INTERVAL_SECONDS", "1200"))

# ---- Rate limiting ----
MAX_URGENT_POSTS_PER_RUN: int = 5
FETCH_COOLDOWN_SECONDS: int = 300  # 5 minutes

# ---- Link caps ----
LINK_CAP_URGENT: int = 3
LINK_CAP_NORMAL: int = 5

# ---- Urgency keywords ----
URGENT_KEYWORDS: tuple[str, ...] = (
    "zero-day", "0-day", "critical vulnerability", "rce", "exploit",
    "data breach", "ransomware", "outage", "down globally", "major outage",
    "security incident", "product recall", "actively exploited",
    "emergency patch", "widespread outage", "breach", "cve", "downtime",
)

# ---- Template urgency levels ----
URGENCY_LEVELS: tuple[str, ...] = ("breaking", "alert", "analysis", "market", "explainer")
URGENCY_LEVELS_SET: frozenset[str] = frozenset(URGENCY_LEVELS)

# ---- News categories ----
NEWS_CATEGORIES: tuple[str, ...] = (
    "startups", "ai", "cybersecurity", "defi",
    "big_tech", "hardware", "science", "regulation",
)
NEWS_CATEGORIES_SET: frozenset[str] = frozenset(NEWS_CATEGORIES)

# ---- File paths ----
POSTED_LOG: str = "posted_ids.json"
SUBSCRIBERS_LOG: str = "subscribers.json"

# ---- Telegram (populated by validate_config) ----
TELEGRAM_BOT_TOKEN: str = ""
PORT: int = 10000
TELEGRAM_CHANNEL_ID: int | None = None
TELEGRAM_THREAD_ID: int | None = None


def validate_config() -> None:
    """Validate required env vars and populate Telegram settings.

    Call once from main() — not at import time.
    """
    global TELEGRAM_BOT_TOKEN, PORT, TELEGRAM_CHANNEL_ID, TELEGRAM_THREAD_ID

    required_vars = ["TELEGRAM_BOT_TOKEN", "GROQ_API_KEY"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}. Set them in Railway → Variables tab.")

    TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    PORT = int(os.environ.get("PORT", "10000"))

    channel_raw = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if channel_raw:
        try:
            TELEGRAM_CHANNEL_ID = int(channel_raw)
        except (ValueError, TypeError):
            raise SystemExit(f"Invalid TELEGRAM_CHANNEL_ID: {channel_raw!r} — must be an integer.")

    thread_raw = os.environ.get("TELEGRAM_THREAD_ID", "").strip()
    if thread_raw:
        try:
            TELEGRAM_THREAD_ID = int(thread_raw)
        except (ValueError, TypeError):
            raise SystemExit(f"Invalid TELEGRAM_THREAD_ID: {thread_raw!r} — must be an integer.")


def create_groq_client():
    """Create and return the OpenAI-compatible Groq client."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url=GROQ_BASE_URL,
    )
