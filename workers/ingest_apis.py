"""API ingestion worker — pulls from GDELT + NewsData.io, writes to Supabase.

Run: python -m workers.ingest_apis

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    NEWSDATA_API_KEY (optional)
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from workers.db import get_supabase
from workers.gdelt import fetch_all_gdelt
from workers.newsdata import fetch_all_newsdata

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _upsert_articles(articles: list[dict[str, Any]]) -> int:
    """Insert articles into Supabase, skipping duplicates by URL. Returns count inserted."""
    if not articles:
        return 0

    supabase = get_supabase()
    inserted = 0

    # Batch insert — Supabase handles conflict on UNIQUE(url)
    batch_size = 100
    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        rows = []
        for a in batch:
            raw = a.get("raw_json")
            rows.append({
                "title": a["title"],
                "summary": a.get("summary", ""),
                "url": a["url"],
                "source_name": a.get("source_name", ""),
                "source_domain": a.get("source_domain", ""),
                "category": a.get("category"),
                "language": a.get("language", "en"),
                "published_at": a.get("published_at"),
                "raw_json": json.dumps(raw) if raw else None,
            })

        try:
            result = supabase.table("articles").upsert(
                rows, on_conflict="url", ignore_duplicates=True
            ).execute()
            inserted += len(result.data) if result.data else 0
        except Exception:
            logger.exception("Failed to upsert batch %d–%d", i, i + batch_size)

    return inserted


def run() -> None:
    logger.info("Starting API ingestion run...")

    # 1. GDELT
    logger.info("Fetching from GDELT...")
    gdelt_articles = fetch_all_gdelt()
    logger.info("GDELT returned %d unique articles", len(gdelt_articles))

    # 2. NewsData.io
    logger.info("Fetching from NewsData.io...")
    newsdata_articles = fetch_all_newsdata()
    logger.info("NewsData.io returned %d unique articles", len(newsdata_articles))

    # 3. Merge and dedup by URL
    seen: set[str] = set()
    all_articles: list[dict[str, Any]] = []
    for a in gdelt_articles + newsdata_articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            all_articles.append(a)

    logger.info("Total unique articles: %d", len(all_articles))

    # 4. Upsert to Supabase
    if all_articles:
        inserted = _upsert_articles(all_articles)
        logger.info("Inserted %d articles into Supabase", inserted)
    else:
        logger.warning("No articles to insert")

    logger.info("API ingestion run complete.")


if __name__ == "__main__":
    run()
