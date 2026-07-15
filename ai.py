"""AI-powered story rewriting via Groq API with output validation."""

from __future__ import annotations

import html
import logging
import re

from config import (
    DIGEST_MIN_SOURCES,
    GROQ_MODEL,
    client,
)
from feeds import Entry

logger = logging.getLogger(__name__)

# Validation patterns — AI output must not contain these
_FORBIDDEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(buy|sell|should invest|price prediction|guaranteed|not financial advice)\b", re.IGNORECASE),
    re.compile(r"\b(I think|I believe|in my opinion|arguably|perhaps)\b", re.IGNORECASE),
]

# Max content length for a Telegram message (Telegram limit: 4096)
_MAX_TELEGRAM_LENGTH: int = 4000
_CAPTION_MAX: int = 1024


def _validate_output(text: str) -> tuple[bool, str | None]:
    """Validate AI output against quality constraints.

    Returns (is_valid, reason_if_invalid).
    """
    if len(text) > _MAX_TELEGRAM_LENGTH:
        return False, f"Output too long ({len(text)} chars, max {_MAX_TELEGRAM_LENGTH})"

    for pattern in _FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        if match:
            return False, f"Forbidden pattern detected: '{match.group()}'"

    if text.count("**") < 2:
        return False, "Missing expected markdown bold formatting"

    return True, None


def _md_bold_to_html(text: str) -> str:
    """Convert **bold** markers to Telegram HTML <b> tags; escape the rest."""
    parts: list[str] = []
    i = 0
    while i < len(text):
        start = text.find("**", i)
        if start == -1:
            parts.append(html.escape(text[i:]))
            break
        parts.append(html.escape(text[i:start]))
        end = text.find("**", start + 2)
        if end == -1:
            parts.append(html.escape(text[start:]))
            break
        parts.append(f"<b>{html.escape(text[start + 2:end])}</b>")
        i = end + 2
    return "".join(parts)


def format_story_html(body_md: str, header: str | None = None) -> str:
    """Build a message with blank lines around a bold title (visual centerpiece)."""
    body = re.sub(r"\n+-?\s*Sources?:.*$", "", body_md, flags=re.IGNORECASE | re.DOTALL).strip()
    body_html = _md_bold_to_html(body)
    # Ensure title stands alone with spacing
    body_html = re.sub(r"(<b>.*?</b>)\n*", r"\1\n\n", body_html, count=1, flags=re.DOTALL)
    parts: list[str] = []
    if header:
        parts.append(html.escape(header))
        parts.append("")
    parts.append(body_html.strip())
    return "\n".join(parts).strip()


def trim_for_caption(text: str, limit: int = _CAPTION_MAX) -> str:
    """Trim HTML caption to Telegram's photo caption limit."""
    if len(text) <= limit:
        return text
    truncated = text[: limit - 1].rsplit("\n", 1)[0]
    if len(truncated) < limit // 2:
        truncated = text[: limit - 1]
    return truncated.rstrip() + "…"


def collect_links(cluster: list[Entry], urgent: bool = False) -> list[str]:
    """Unique article links from a cluster (capped)."""
    links: list[str] = []
    seen: set[str] = set()
    for entry in cluster:
        if entry.link not in seen:
            seen.add(entry.link)
            links.append(entry.link)
    return links[:3] if urgent else links[:5]


def pick_image_url(cluster: list[Entry]) -> str | None:
    """First available image URL from the cluster."""
    for entry in cluster:
        if entry.image_url:
            return entry.image_url
    return None


def rewrite_with_ai(cluster: list[Entry], urgent: bool = False, header: str | None = None) -> str:
    """Produce Telegram HTML body (title + bullets). No source links in text."""
    links = collect_links(cluster, urgent=urgent)

    source_note = ""
    if len(links) < DIGEST_MIN_SOURCES:
        source_note = (
            f"\nNote: only {len(links)} source(s) available so far "
            f"(prefer {DIGEST_MIN_SOURCES}+ when possible)."
        )

    headlines = "\n".join(
        f"- [{e.source_name}] {e.title}: {e.summary[:200]}"
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

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Groq API returned empty content")
        body = content.strip()
    except Exception:
        logger.exception("Groq API call failed for cluster starting with '%s'", cluster[0].title)
        raise

    # Strip any Source line the model may still emit; we own that section.
    body = re.sub(r"\n+-?\s*Sources?:.*$", "", body, flags=re.IGNORECASE | re.DOTALL).strip()

    # Validate AI output
    is_valid, reason = _validate_output(body)
    if not is_valid:
        logger.warning("AI output validation failed (%s), using fallback", reason)
        body = _fallback_format(cluster, urgent)

    capped = links[:3] if urgent else links[:5]
    label = "Source" if len(capped) == 1 else "Sources"
    return f"{body}\n- {label}: {' | '.join(capped)}"


def _fallback_format(cluster: list[Entry], urgent: bool) -> str:
    """Produce a simple formatted post when AI output fails validation."""
    primary = cluster[0]
    prefix = "[URGENT] " if urgent else ""
    lines = [
        f"**{prefix}{primary.title}**",
        f"- What happened: {primary.summary[:200]}",
    ]
    if not urgent and len(cluster) > 1:
        lines.append(f"- Also reported by: {', '.join(e.source_name for e in cluster[1:3])}")
    return "\n".join(lines)
