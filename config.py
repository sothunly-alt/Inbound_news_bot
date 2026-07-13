"""Configuration constants and environment variable loading."""

import os
from typing import Optional

import pytz
from dotenv import load_dotenv

load_dotenv()

# ---- RSS ----
RSS_FEEDS: list[str] = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.wired.com/feed/rss",
    "https://www.theguardian.com/technology/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://www.bleepingcomputer.com/feed/",
    "https://krebsonsecurity.com/feed/",
]
MAX_ITEMS_PER_FEED: int = 5

# ---- Clustering ----
CLUSTER_SIMILARITY_THRESHOLD: float = 0.45

# ---- AI ----
GROQ_MODEL: str = "llama-3.3-70b-versatile"
GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

# ---- Scheduling ----
TIMEZONE = pytz.timezone("Asia/Phnom_Penh")
URGENT_CHECK_INTERVAL_SECONDS: int = 15 * 60
DIGEST_MIN_SOURCES: int = 2
URGENT_MIN_SOURCES: int = 3

# ---- Rate limiting ----
MAX_URGENT_POSTS_PER_RUN: int = 5

# ---- Urgency keywords ----
URGENT_KEYWORDS: tuple[str, ...] = (
    "zero-day", "0-day", "critical vulnerability", "rce", "exploit",
    "data breach", "ransomware", "outage", "down globally", "major outage",
    "security incident", "product recall", "actively exploited",
    "emergency patch", "widespread outage",
)

# ---- File paths ----
POSTED_LOG: str = "posted_ids.json"
SUBSCRIBERS_LOG: str = "subscribers.json"

# ---- Telegram ----
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
PORT: int = int(os.environ.get("PORT", "10000"))

_CHANNEL_RAW: str = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
TELEGRAM_CHANNEL_ID: Optional[int] = int(_CHANNEL_RAW) if _CHANNEL_RAW else None
_THREAD_RAW: str = os.environ.get("TELEGRAM_THREAD_ID", "").strip()
TELEGRAM_THREAD_ID: Optional[int] = int(_THREAD_RAW) if _THREAD_RAW else None

# ---- Groq client (imported from openai SDK) ----
from openai import OpenAI  # noqa: E402

client: OpenAI = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url=GROQ_BASE_URL,
)
