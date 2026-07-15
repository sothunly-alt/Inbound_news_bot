"""RSS feed fetching, title normalization, clustering, and urgency detection."""

from __future__ import annotations

import concurrent.futures
import logging
import re
import time
from calendar import timegm
from dataclasses import dataclass
from typing import Any, Optional

import feedparser
import httpx

from config import (
    CLUSTER_SIMILARITY_THRESHOLD,
    CONTENT_DEDUP_THRESHOLD,
    FEED_TIMEOUT_SECONDS,
    MAX_ENTRY_AGE_HOURS,
    MAX_ITEMS_PER_FEED,
    RSS_FEEDS,
    URGENT_KEYWORDS,
)

logger = logging.getLogger(__name__)

# Module-level HTTP client with timeout for real cancellation
_http_client = httpx.Client(timeout=FEED_TIMEOUT_SECONDS, follow_redirects=True)

# Shared thread pool for parallel feed fetching
_feed_pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(RSS_FEEDS), 10))

# Stop words for title normalization
_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with",
    "as", "at", "by", "from", "is", "are", "its", "it", "this", "that",
})

_IMG_SRC_RE = re.compile(
    r'<img[^>]+src=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _is_entry_too_old(raw_entry: Any, max_age_hours: int = MAX_ENTRY_AGE_HOURS) -> bool:
    """Check if an RSS entry is older than max_age_hours.

    Tries published_parsed first, then updated_parsed.
    Returns False (not too old) if no timestamp is available.
    """
    parsed = getattr(raw_entry, "published_parsed", None) or getattr(raw_entry, "updated_parsed", None)
    if parsed is None:
        return False
    try:
        entry_ts = timegm(parsed)
        age_seconds = time.time() - entry_ts
        return age_seconds > max_age_hours * 3600
    except (TypeError, ValueError):
        return False


@dataclass
class Entry:
    """A single news item from an RSS feed."""
    id: str
    title: str
    summary: str
    link: str
    source_name: str
    image_url: Optional[str] = None


def extract_image_url(raw_entry: Any) -> Optional[str]:
    """Pull an image URL from common RSS/Atom media fields, if present."""
    media_content = getattr(raw_entry, "media_content", None) or raw_entry.get("media_content")
    if media_content:
        for item in media_content:
            url = item.get("url") if isinstance(item, dict) else None
            medium = (item.get("medium") or item.get("type") or "") if isinstance(item, dict) else ""
            if url and (not medium or "image" in str(medium).lower() or str(medium).startswith("image/")):
                return url
            if url and str(url).lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                return url

    media_thumbnail = getattr(raw_entry, "media_thumbnail", None) or raw_entry.get("media_thumbnail")
    if media_thumbnail:
        for item in media_thumbnail:
            url = item.get("url") if isinstance(item, dict) else None
            if url:
                return url

    enclosures = getattr(raw_entry, "enclosures", None) or raw_entry.get("enclosures") or []
    for enc in enclosures:
        href = enc.get("href") or enc.get("url") if isinstance(enc, dict) else None
        enc_type = (enc.get("type") or "") if isinstance(enc, dict) else ""
        if href and str(enc_type).startswith("image/"):
            return href
        if href and str(href).lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
            return href

    for field in ("summary", "description", "content"):
        value = raw_entry.get(field) if hasattr(raw_entry, "get") else None
        if value is None:
            value = getattr(raw_entry, field, None)
        if isinstance(value, list) and value:
            value = value[0].get("value", "") if isinstance(value[0], dict) else str(value[0])
        if isinstance(value, str):
            match = _IMG_SRC_RE.search(value)
            if match:
                return match.group(1)

    return None


def _normalize_title(title: str) -> list[str]:
    """Lowercase, strip punctuation, drop stop words for clustering."""
    text = title.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [t for t in text.split() if t and t not in _STOP_WORDS]


def _title_similarity(a: str, b: str) -> float:
    """Jaccard similarity over normalized title tokens."""
    sa = set(_normalize_title(a))
    sb = set(_normalize_title(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _summary_similarity(a: str, b: str) -> float:
    """Jaccard similarity over normalized summary tokens (capped at 100 words each)."""
    def _norm(text: str) -> set[str]:
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        words = [t for t in text.split() if t and t not in _STOP_WORDS]
        return set(words[:100])
    sa = _norm(a)
    sb = _norm(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def normalize_title_key(title: str) -> str:
    """Return a canonical string key for a title used for dedup storage."""
    tokens = _normalize_title(title)
    return " ".join(sorted(tokens))


def _is_title_duplicate(title: str, posted_titles: set[str], threshold: float = CONTENT_DEDUP_THRESHOLD) -> bool:
    """Check if a title is similar enough to any previously posted title."""
    if not posted_titles:
        return False
    tokens = set(_normalize_title(title))
    if not tokens:
        return False
    for posted_key in posted_titles:
        posted_tokens = set(posted_key.split())
        if not posted_tokens:
            continue
        similarity = len(tokens & posted_tokens) / len(tokens | posted_tokens)
        if similarity >= threshold:
            return True
    return False


def _fetch_feed(url: str) -> Any:
    """Fetch a single RSS feed using httpx (real timeout) then parse with feedparser."""
    resp = _http_client.get(url)
    resp.raise_for_status()
    return feedparser.parse(resp.text)


def collect_new_entries(posted_ids: set[str], posted_titles: set[str] | None = None) -> list[Entry]:
    """Pull fresh entries from all feeds in parallel, skipping already-posted IDs and similar titles.

    All feeds are fetched concurrently — a slow/dead feed does not block others.
    """
    if posted_titles is None:
        posted_titles = set()

    # Submit all feeds in parallel
    futures: dict[concurrent.futures.Future, str] = {
        _feed_pool.submit(_fetch_feed, url): url for url in RSS_FEEDS
    }

    entries: list[Entry] = []
    global_timeout = FEED_TIMEOUT_SECONDS + 10

    for future in concurrent.futures.as_completed(futures, timeout=global_timeout):
        feed_url = futures[future]
        try:
            feed = future.result(timeout=FEED_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            logger.warning("Feed %s timed out after %ds", feed_url, FEED_TIMEOUT_SECONDS)
            continue
        except httpx.TimeoutException:
            logger.warning("Feed %s HTTP timeout after %ds", feed_url, FEED_TIMEOUT_SECONDS)
            continue
        except Exception:
            logger.exception("Failed to fetch feed %s", feed_url)
            continue

        if feed.bozo and not feed.entries:
            logger.warning("Feed %s returned an error: %s", feed_url, feed.bozo_exception)
            continue

        source_name: str = feed.feed.get("title", feed_url)
        count = 0
        for entry in feed.entries:
            if count >= MAX_ITEMS_PER_FEED:
                break
            entry_id: str = entry.get("id", entry.link)
            if entry_id in posted_ids:
                continue
            if _is_entry_too_old(entry):
                logger.debug("Skipping stale entry: %s", entry.get("title", ""))
                continue
            title = entry.get("title", "").strip()
            if _is_title_duplicate(title, posted_titles):
                logger.debug("Skipping duplicate title: %s", title)
                continue
            entries.append(Entry(
                id=entry_id,
                title=title,
                summary=(entry.get("summary", "") or "")[:500],
                link=entry.link,
                source_name=source_name,
                image_url=extract_image_url(entry),
            ))
            count += 1

    return entries


def cluster_entries(
    entries: list[Entry],
    threshold: float = CLUSTER_SIMILARITY_THRESHOLD,
) -> list[list[Entry]]:
    """Group related headlines across feeds using combined title + summary similarity.

    Uses a weighted combination: title similarity 0.7 + summary similarity 0.3.
    Greedy clustering — each entry is placed in the first matching cluster.
    """
    clusters: list[list[Entry]] = []
    for entry in entries:
        placed = False
        for cluster in clusters:
            title_sim = _title_similarity(entry.title, cluster[0].title)
            summary_sim = _summary_similarity(entry.summary, cluster[0].summary)
            combined = 0.7 * title_sim + 0.3 * summary_sim
            if combined >= threshold:
                cluster.append(entry)
                placed = True
                break
        if not placed:
            clusters.append([entry])
    return clusters


def looks_urgent(entries: list[Entry]) -> bool:
    """Keyword-based urgency check on combined title + summary text."""
    blob = " ".join(f"{e.title} {e.summary}" for e in entries).lower()
    return any(kw in blob for kw in URGENT_KEYWORDS)
