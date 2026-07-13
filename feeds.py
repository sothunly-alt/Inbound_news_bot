"""RSS feed fetching, title normalization, clustering, and urgency detection."""

import logging
import re
from dataclasses import dataclass

import feedparser

from config import (
    CLUSTER_SIMILARITY_THRESHOLD,
    MAX_ITEMS_PER_FEED,
    RSS_FEEDS,
    URGENT_KEYWORDS,
)

logger = logging.getLogger(__name__)

# Stop words for title normalization
_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with",
    "as", "at", "by", "from", "is", "are", "its", "it", "this", "that",
})


@dataclass
class Entry:
    """A single news item from an RSS feed."""
    id: str
    title: str
    summary: str
    link: str
    source_name: str


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


def collect_new_entries(posted_ids: set[str]) -> list[Entry]:
    """Pull fresh entries from all feeds, skipping already-posted IDs.

    Each feed is fetched independently — a failure in one feed does not
    prevent the others from being collected.
    """
    entries: list[Entry] = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
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
                entries.append(Entry(
                    id=entry_id,
                    title=entry.get("title", "").strip(),
                    summary=(entry.get("summary", "") or "")[:500],
                    link=entry.link,
                    source_name=source_name,
                ))
                count += 1
        except Exception:
            logger.exception("Failed to fetch feed %s", feed_url)
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
