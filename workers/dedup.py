"""Dedup worker — clusters articles into stories using Cohere embeddings + pgvector.

Run: python -m workers.dedup

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    COHERE_API_KEY

This worker:
1. Fetches unprocessed articles from Supabase
2. Generates Cohere embeddings for each article title + summary
3. Searches pgvector for existing stories with cosine similarity ≥ 0.85
4. If similar story found: adds article to that story
5. If no similar story: creates a new story
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import httpx

from workers.db import get_supabase

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = 0.85
_EMBED_MODEL = "embed-multilingual-v3.0"
_EMBED_DIM = 1024
_BATCH_SIZE = 100


def _get_cohere_client():
    import cohere
    api_key = os.environ.get("COHERE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set COHERE_API_KEY env var.")
    return cohere.ClientV2(api_key)


def _embed_texts(client, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using Cohere."""
    if not texts:
        return []

    result = client.embed(
        texts=texts,
        model=_EMBED_MODEL,
        input_type="search_document",
        embedding_types=["float"],
    )
    return [e for e in result.embeddings.float]


def _fetch_unprocessed(supabase, limit: int = 500) -> list[dict[str, Any]]:
    """Fetch articles that haven't been linked to a story yet."""
    # Get articles not yet in story_sources
    result = supabase.table("articles").select("*").not_.in_(
        "id",
        supabase.table("story_sources").select("article_id")
    ).order("ingested_at", desc=True).limit(limit).execute()

    return result.data or []


def _search_similar_stories(supabase, embedding: list[float], threshold: float = 0.85) -> str | None:
    """Search for existing stories with similar embeddings. Returns story_id or None."""
    import json
    embedding_str = json.dumps(embedding)

    result = supabase.rpc("match_stories", {
        "query_embedding": embedding_str,
        "match_threshold": threshold,
        "match_count": 1,
    }).execute()

    matches = result.data or []
    if matches:
        return matches[0]["id"]
    return None


def _create_story(supabase, article: dict, embedding: list[float]) -> str:
    """Create a new story from an article. Returns the story ID."""
    result = supabase.table("stories").insert({
        "title": article["title"],
        "summary_en": article.get("summary", ""),
        "source_count": 1,
        "category": article.get("category"),
        "tags": [],
        "embedding": embedding,
    }).execute()

    story_id = result.data[0]["id"]

    # Link article to story
    supabase.table("story_sources").insert({
        "story_id": story_id,
        "article_id": article["id"],
        "source_name": article.get("source_name", ""),
        "source_url": article.get("url", ""),
    }).execute()

    return story_id


def _add_to_story(supabase, story_id: str, article: dict) -> None:
    """Add an article to an existing story and increment source_count."""
    supabase.table("story_sources").insert({
        "story_id": story_id,
        "article_id": article["id"],
        "source_name": article.get("source_name", ""),
        "source_url": article.get("url", ""),
    }).execute()

    # Increment source_count
    supabase.table("stories").update({
        "source_count": supabase.rpc("increment_source_count", {"sid": story_id}),
    }).eq("id", story_id).execute()


def _add_increment_rpc(supabase) -> None:
    """Ensure the increment_source_count RPC function exists."""
    supabase.rpc("increment_source_count", {"sid": "test"}).execute()


def run() -> None:
    supabase = get_supabase()
    cohere_client = _get_cohere_client()

    logger.info("Fetching unprocessed articles...")
    articles = _fetch_unprocessed(supabase, limit=500)
    logger.info("Found %d unprocessed articles", len(articles))

    if not articles:
        logger.info("Nothing to dedup.")
        return

    # 1. Generate embeddings for all articles
    texts = [
        f"{a.get('title', '')}. {a.get('summary', '')[:200]}"
        for a in articles
    ]
    logger.info("Generating embeddings for %d articles...", len(texts))
    embeddings = _embed_texts(cohere_client, texts)

    # 2. For each article, search for similar stories
    new_stories = 0
    merged = 0

    for article, embedding in zip(articles, embeddings):
        story_id = _search_similar_stories(supabase, embedding, _SIMILARITY_THRESHOLD)

        if story_id:
            _add_to_story(supabase, story_id, article)
            merged += 1
        else:
            _create_story(supabase, article, embedding)
            new_stories += 1

    logger.info("Dedup complete: %d new stories, %d merged into existing", new_stories, merged)

    # 3. Enable vector index if enough stories
    story_count = supabase.table("stories").select("id", count="exact").execute()
    total = story_count.count or 0
    if total >= 100:
        logger.info("Story count: %d — you can now create the vector index in Supabase SQL:", total)
        logger.info("  CREATE INDEX stories_embedding_idx ON stories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);")


if __name__ == "__main__":
    run()
