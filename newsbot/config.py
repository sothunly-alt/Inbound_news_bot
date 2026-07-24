"""Configuration constants and environment variable loading.

Feed Tier System:
  Tier 1 (this file): ~130 curated feeds — Telegram bot (fast, reliable, <15s)
  Tier 2 (feeds_bulk.txt): ~4,400 feeds — website ingestion pipeline (future)
  Tier 3 (APIs): GDELT, NewsData.io, Guardian, NYTimes — website ingestion (future)

The Telegram bot only fetches Tier 1 feeds. Tier 2/3 are for the website
at inboundreports.com and are not loaded by the bot.
"""

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
    "DONATION_SCHEDULE_HOUR",
    "DONATION_QR_IMAGE",
    "URGENT_CHECK_INTERVAL_SECONDS",
    "URGENT_FIRST_DELAY_SECONDS",
    "MAX_URGENT_POSTS_PER_RUN",
    "URGENT_KEYWORDS",
    "URGENCY_LEVELS",
    "NEWS_CATEGORIES",
    "DISABLE_POSTING",
    "POSTED_LOG",
    "SUBSCRIBERS_LOG",
    "FETCH_COOLDOWN_SECONDS",
    "LINK_CAP_URGENT",
    "LINK_CAP_NORMAL",
    "TELEGRAM_BOT_TOKEN",
    "PORT",
    "TELEGRAM_CHANNEL_ID",
    "TELEGRAM_THREAD_ID",
    "TELEGRAM_GROUP_CHAT_ID",
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
    # Cybersecurity
    "https://www.bleepingcomputer.com/feed/",
    "https://krebsonsecurity.com/feed/",
    "https://www.darkreading.com/rss.xml",
    "https://feeds.feedburner.com/TheHackersNews",
    # DeFi & Crypto
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    # Hardware
    "https://www.tomshardware.com/feeds/all",
    # Mobile
    "https://9to5google.com/feed/",
    "https://9to5mac.com/feed/",
    "https://www.androidpolice.com/feed/",
    # Regulation
    "https://techpolicy.press/rss/feed.xml",
    # Science
    "https://www.sciencedaily.com/rss/top/technology.xml",
    "https://www.nature.com/subjects/technology.rss",
    # General Tech
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.wired.com/feed/rss",
    "https://www.theguardian.com/technology/rss",
    "https://www.technologyreview.com/feed/",
    "https://www.zdnet.com/news/rss.xml",
    # Curated Medium publications
    "https://medium.com/feed/better-programming",
    "https://medium.com/feed/towards-data-science",
    # SE Asia & Regional Tech
    "https://www.techinasia.com/feed",
    "https://kr-asia.com/feed",
    "https://e27.co/feed/",
    "https://restofworld.org/feed/",
    "https://asia.nikkei.com/rss/feed/technology",
    # AI & Research
    "https://blog.openai.com/rss/",
    "https://deepmind.google/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://news.mit.edu/rss/topic/artificial-intelligence2",
    "https://www.marktechpost.com/feed/",
    # Mainstream Tech
    "https://feeds.venturebeat.com/Venturebeat",
    "https://www.engadget.com/rss.xml",
    "https://spectrum.ieee.org/feeds/feed.rss",
    "https://www.vox.com/rss/recode/index.xml",
    # Cloud & DevOps
    "https://thenewstack.io/feed/",
    "https://cloudblog.withgoogle.com/rss/",
    "https://www.docker.com/feed/",
    # Developer & Open Source
    "https://github.blog/feed/",
    "https://stackoverflow.blog/feed/",
    "https://devblogs.microsoft.com/feed/",
    # Gaming
    "https://www.polygon.com/rss/index.xml",
    # Climate Tech
    "https://electrek.co/feed/",
    # Space
    "https://spacenews.com/feed/",
    "https://www.space.com/feeds.xml",
    # Community & Discovery
    "https://hnrss.org/frontpage",
    "https://www.producthunt.com/feed",
    # AI Research
    "https://www.anthropic.com/blog/rss",
    "https://blog.research.google/rss",
    # Security
    "https://therecord.media/feed",
    # Developer
    "https://feed.infoq.com/",
    "https://dev.to/feed",
    # Apple Ecosystem
    "http://feeds.macrumors.com/MacRumors-Front",
    "https://appleinsider.com/rss/news/",
    "https://www.macworld.com/feed",
    # Linux & Open Source
    "https://www.phoronix.com/rss.php",
    "https://www.linuxfoundation.org/feed/",
    "https://blog.mozilla.org/feed/",
    "https://www.eff.org/rss/updates.xml",
    # Windows & Microsoft
    "https://www.windowscentral.com/feed.xml",
    "https://betanews.com/feed",
    "https://www.neowin.net/feed/",
    # Consumer Tech
    "https://www.cnet.com/rss/news/",
    "https://www.techradar.com/feeds.xml",
    "https://www.digitaltrends.com/feed/",
    "https://gizmodo.com/rss",
    "https://mashable.com/rss",
    "https://www.pcworld.com/feed",
    "https://www.makeuseof.com/feed/",
    "https://feeds.howtogeek.com/HowToGeek",
    "https://www.slashgear.com/feed",
    # Business Tech
    "https://feeds.bloomberg.com/technology/news.rss",
    "https://feeds.businessinsider.com/custom/all",
    "https://www.fastcompany.com/rss",
    # Enterprise IT
    "https://www.theregister.com/headlines.atom",
    "https://www.computerworld.com/feed",
    "https://www.techrepublic.com/rssfeeds/",
    "https://siliconangle.com/feed/",
    # AI & ML
    "https://openai.com/news/rss.xml",
    "https://blog.google/technology/ai/rss/",
    "https://ai.meta.com/blog/rss/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.unite.ai/feed/",
    "https://www.kdnuggets.com/feed",
    "https://developer.nvidia.com/blog/feed/",
    "https://research.google/blog/rss/",
    # Cybersecurity
    "https://www.securityweek.com/feed/",
    "https://www.helpnetsecurity.com/feed/",
    "https://www.csoonline.com/feed",
    "https://cyberscoop.com/feed/",
    "https://blog.talosintelligence.com/rss/",
    "https://www.schneier.com/feed/atom/",
    "https://grahamcluley.com/feed/",
    "https://www.scworld.com/feed",
    # Cloud & DevOps
    "https://aws.amazon.com/blogs/aws/feed/",
    "https://azure.microsoft.com/blog/feed/",
    "https://blog.cloudflare.com/rss/",
    "https://www.hashicorp.com/feed.xml",
    "https://kubernetes.io/feed.xml",
    "https://www.cncf.io/blog/feed/",
    # Mobile
    "https://www.androidauthority.com/feed/",
    "https://www.androidcentral.com/feed",
    "https://www.gsmarena.com/rss-news-reviews.php",
    "https://www.xda-developers.com/feed/",
    # Science & Hardware
    "https://phys.org/rss-feed/",
    "https://www.livescience.com/feed",
    "https://www.quantamagazine.org/feed/",
    "https://semiengineering.com/feed/",
    # Developer
    "https://www.freecodecamp.org/news/rss/",
    "https://www.smashingmagazine.com/feed/",
    "https://hackernoon.com/feed",
    # Regional & Global
    "https://technode.com/feed/",
    "https://www.siliconrepublic.com/feed",
    "https://tech.eu/feed/",
    "https://www.itnews.com.au/rss.xml",
    "https://mobilesyrup.com/feed/",
    # Startups & Business
    "https://www.geekwire.com/feed/",
    "https://www.saastr.com/feed/",
    "https://a16z.com/feed/",
    # Community & Discovery
    "https://www.techmeme.com/feed.xml",
    "https://slashdot.org/rss/slashdot.rss",
    "https://www.techspot.com/feed/",
    # Additional Tech News
    "https://www.extremetech.com/feed",
    "https://readwrite.com/feed/",
    "https://fossbytes.com/feed/",
    # Lobste.rs — strictly moderated, invite-only deep tech
    "https://lobste.rs/rss",
    # arXiv — academic preprints (AI, ML, security)
    "http://arxiv.org/rss/cs.AI",
    "http://arxiv.org/rss/cs.LG",
    "http://arxiv.org/rss/cs.CR",
    # Hacker News — high-score stories (via hnrss.org)
    "https://hnrss.org/frontpage?points=100",
]

# ---- Extra feeds (Tier 2 — NOT loaded by Telegram bot) ----
# Bulk feeds live in feeds_bulk.txt for the website ingestion pipeline.
# Do NOT load them here — the bot only uses the curated Tier 1 feeds above.
# To use bulk feeds in a future website worker, load feeds_bulk.txt directly.

MAX_ITEMS_PER_FEED: int = 3
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
GROQ_MAX_TOKENS: int = 2200

# ---- Scheduling ----
TIMEZONE = ZoneInfo("Asia/Phnom_Penh")
DIGEST_MIN_SOURCES: int = 2
DIGEST_MAX_STORIES: int = 10
DIGEST_SCHEDULE_HOUR_AM: int = 5
DIGEST_SCHEDULE_HOUR_PM: int = 17
DONATION_SCHEDULE_HOUR: int = 22  # 10 PM
DONATION_QR_IMAGE: str = os.environ.get("DONATION_QR_IMAGE", "qr_aba_news.jpg")
URGENT_CHECK_INTERVAL_SECONDS: int = 60 * 30  # every 30 minutes
URGENT_FIRST_DELAY_SECONDS: int = 60
POLL_INTERVAL_SECONDS: int = int(os.environ.get("POLL_INTERVAL_SECONDS", "7200"))

# ---- Rate limiting ----
MAX_URGENT_POSTS_PER_RUN: int = 2
FETCH_COOLDOWN_SECONDS: int = 300  # 5 minutes

# ---- Link caps ----
LINK_CAP_URGENT: int = 3
LINK_CAP_NORMAL: int = 5

# ---- Batching ----
BATCH_STORIES: bool = True
BATCH_MAX_STORIES: int = 6
BATCH_POLL_INTERVAL_MINUTES: int = 15
URGENT_POST_IMMEDIATELY: bool = True

# ---- Feature toggles ----
DISABLE_POSTING: bool = False

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
    "cloud", "opensource", "gaming", "climate",
    "telecom", "mobile", "regional",
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
TELEGRAM_GROUP_CHAT_ID: int | None = None


def validate_config() -> None:
    """Validate required env vars and populate Telegram settings.

    Call once from main() — not at import time.
    """
    global TELEGRAM_BOT_TOKEN, PORT, TELEGRAM_CHANNEL_ID, TELEGRAM_THREAD_ID, TELEGRAM_GROUP_CHAT_ID

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

    group_raw = os.environ.get("TELEGRAM_GROUP_CHAT_ID", "").strip()
    if group_raw:
        try:
            TELEGRAM_GROUP_CHAT_ID = int(group_raw)
        except (ValueError, TypeError):
            raise SystemExit(f"Invalid TELEGRAM_GROUP_CHAT_ID: {group_raw!r} — must be an integer.")


def create_groq_client():
    """Create and return the OpenAI-compatible Groq client."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url=GROQ_BASE_URL,
    )