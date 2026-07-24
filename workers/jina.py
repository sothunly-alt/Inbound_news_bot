"""Jina AI Reader — extracts clean Markdown content from any URL.

Free tier: No API key required for basic use.
Just prepend https://r.jina.ai/ to any URL to get clean, LLM-ready Markdown.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_READER_BASE = "https://r.jina.ai"
_TIMEOUT = 30


def extract_content(
    url: str,
    return_format: str = "markdown",
) -> dict[str, Any]:
    """Extract clean content from a URL using Jina AI Reader.

    Args:
        url: The URL to extract content from.
        return_format: "markdown" (default) or "text".

    Returns:
        Dict with keys: url, title, content, description, source_domain.
    """
    reader_url = f"{_READER_BASE}/{url}"

    headers = {
        "Accept": f"application/{return_format}",
        "X-Return-Format": return_format,
    }

    try:
        resp = httpx.get(reader_url, headers=headers, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
    except httpx.TimeoutException:
        logger.warning("Jina Reader timed out for: %s", url)
        return {"url": url, "title": "", "content": "", "description": "", "source_domain": ""}
    except Exception:
        logger.exception("Jina Reader failed for: %s", url)
        return {"url": url, "title": "", "content": "", "description": "", "source_domain": ""}

    content = resp.text.strip()

    # Extract title from first line if present (Jina returns title on first line)
    title = ""
    lines = content.split("\n", 1)
    if lines and lines[0].startswith("Title: "):
        title = lines[0].replace("Title: ", "").strip()
        content = lines[1].strip() if len(lines) > 1 else ""

    # Truncate to reasonable length
    if len(content) > 5000:
        content = content[:5000] + "..."

    domain = ""
    try:
        domain = urlparse(url).netloc.replace("www.", "")
    except Exception:
        pass

    return {
        "url": url,
        "title": title,
        "content": content,
        "description": content[:300] if content else "",
        "source_domain": domain,
    }


def extract_batch(
    urls: list[str],
    max_concurrent: int = 5,
) -> list[dict[str, Any]]:
    """Extract content from multiple URLs concurrently.

    Args:
        urls: List of URLs to extract.
        max_concurrent: Max concurrent requests.

    Returns:
        List of extraction results.
    """
    import concurrent.futures

    results: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        future_to_url = {pool.submit(extract_content, u): u for u in urls}
        for future in concurrent.futures.as_completed(future_to_url, timeout=60):
            try:
                result = future.result(timeout=_TIMEOUT + 5)
                results.append(result)
            except Exception:
                url = future_to_url[future]
                logger.warning("Jina batch extraction failed for: %s", url)

    return results


def fetch_article_for_ingestion(url: str) -> dict[str, Any] | None:
    """Extract article content for the ingestion pipeline.

    Returns a dict matching the standardized article schema, or None if extraction fails.
    """
    result = extract_content(url)
    if not result.get("content"):
        return None

    domain = result.get("source_domain", "")

    return {
        "title": result.get("title") or f"Article from {domain}",
        "url": url,
        "source_name": f"Jina Reader ({domain})",
        "source_domain": domain,
        "summary": result.get("description", ""),
        "published_at": None,
        "language": "en",
        "category": None,
        "raw_json": {"content": result.get("content", "")},
    }
