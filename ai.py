"""AI-powered story rewriting via Groq API with structured JSON output and template rendering."""

from __future__ import annotations

import html
import json
import logging
import re
import time

from config import (
    DIGEST_MIN_SOURCES,
    GROQ_MODEL,
    client,
)
from feeds import Entry

logger = logging.getLogger(__name__)

_MAX_TELEGRAM_LENGTH: int = 4000
_CAPTION_MAX: int = 1024
_MAX_RETRIES: int = 3
_RETRY_BASE_DELAY: float = 1.0

_REQUIRED_JSON_KEYS = ("urgency", "headline", "summary")


def _parse_ai_json(raw: str) -> dict:
    """Parse JSON from AI output, handling markdown code fences and preamble text."""
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` blocks
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse AI output as JSON")


def _validate_ai_data(data: dict) -> tuple[bool, str | None]:
    """Validate that the AI-returned dict has required fields and correct types."""
    for key in _REQUIRED_JSON_KEYS:
        if key not in data:
            return False, f"Missing required key: '{key}'"
        if not isinstance(data[key], str) or not data[key].strip():
            return False, f"Key '{key}' must be a non-empty string"

    valid_levels = {"breaking", "alert", "analysis", "market", "explainer"}
    if data["urgency"] not in valid_levels:
        return False, f"Invalid urgency level: '{data['urgency']}'"

    # Validate list fields
    for key in ("key_points", "metrics", "who_affected", "what_to_do", "tags"):
        if key in data and not isinstance(data[key], list):
            return False, f"Key '{key}' must be a list"

    return True, None


def _md_bold_to_html(text: str) -> str:
    """Convert **bold** markers to Telegram HTML <b> tags; escape the rest."""
    parts: list[str] = []
    i = 0
    while i < len(text):
        start = text.find("**", i)
        if start == -1:
            parts.append(html.escape(text[i:], quote=False))
            break
        parts.append(html.escape(text[i:start], quote=False))
        end = text.find("**", start + 2)
        if end == -1:
            parts.append(html.escape(text[start:], quote=False))
            break
        parts.append(f"<b>{html.escape(text[start + 2:end], quote=False)}</b>")
        i = end + 2
    return "".join(parts)


def _escape(text: str) -> str:
    """HTML-escape text for Telegram (no quote escaping — Telegram doesn't need it)."""
    return html.escape(text, quote=False)


def _bullet_list(items: list[str], limit: int = 5) -> str:
    """Render items as bullet points."""
    return "\n".join(f"• {_escape(item)}" for item in items[:limit])


def render_template(data: dict) -> str:
    """Render AI-structured data into a Telegram HTML message using the appropriate template."""
    urgency = data.get("urgency", "analysis")
    headline = _escape(data["headline"])
    summary = _escape(data["summary"])
    key_points = data.get("key_points", [])
    tags = data.get("tags", [])

    sections: list[str] = []

    if urgency == "breaking":
        sections.append(f"🚨 CRITICAL: <b>{headline}</b>")
        sections.append("")
        sections.append(summary)

        metrics = data.get("metrics", [])
        if metrics:
            sections.append("")
            sections.append("📊 KEY METRICS:")
            sections.append(_bullet_list(metrics))

        why_matters = data.get("context", "")
        if why_matters:
            sections.append("")
            sections.append("⚠️ WHY IT MATTERS:")
            sections.append(_escape(why_matters))

        if key_points:
            sections.append("")
            sections.append("🔍 DETAILS:")
            sections.append(_bullet_list(key_points))

        timeline = data.get("timeline", "")
        if timeline:
            sections.append("")
            sections.append(f"⏰ {_escape(timeline)}")

    elif urgency == "alert":
        sections.append(f"⚠️ ALERT: <b>{headline}</b>")
        sections.append("")
        sections.append(summary)

        what_to_do = data.get("what_to_do", [])
        if what_to_do:
            sections.append("")
            sections.append("🛡️ WHAT TO DO:")
            sections.append(_bullet_list(what_to_do))

        who = data.get("who_affected", [])
        if who:
            sections.append("")
            sections.append("📍 AFFECTED:")
            sections.append(_bullet_list(who))

        timeline = data.get("timeline", "")
        if timeline:
            sections.append("")
            sections.append(f"⏰ {_escape(timeline)}")

    elif urgency == "market":
        sections.append(f"💹 <b>{headline}</b>")
        sections.append("")
        sections.append(summary)

        if key_points:
            sections.append("")
            sections.append("📊 KEY POINTS:")
            sections.append(_bullet_list(key_points))

        market_impact = data.get("market_impact", "")
        if market_impact:
            sections.append("")
            sections.append("📈 MARKET IMPACT:")
            sections.append(_escape(market_impact))

    elif urgency == "explainer":
        sections.append(f"📚 EXPLAINER: <b>{headline}</b>")
        sections.append("")
        sections.append(summary)

        if key_points:
            sections.append("")
            sections.append("🔹 KEY POINTS:")
            sections.append(_bullet_list(key_points, limit=8))

        what_to_watch = data.get("what_to_watch", [])
        if what_to_watch:
            sections.append("")
            sections.append("🔹 WHAT TO WATCH:")
            sections.append(_bullet_list(what_to_watch))

        tldr = data.get("tldr", "")
        if tldr:
            sections.append("")
            sections.append(f"💡 TL;DR: {_escape(tldr)}")

    else:  # analysis (default)
        sections.append(f"📊 <b>{headline}</b>")
        sections.append("")
        sections.append(summary)

        if key_points:
            sections.append("")
            sections.append("💡 KEY POINTS:")
            sections.append(_bullet_list(key_points))

        market_impact = data.get("market_impact", "")
        if market_impact:
            sections.append("")
            sections.append("📈 MARKET IMPACT:")
            sections.append(_escape(market_impact))

        who = data.get("who_affected", [])
        if who:
            sections.append("")
            sections.append("🎯 WHO THIS AFFECTS:")
            sections.append(_bullet_list(who))

        context = data.get("context", "")
        if context:
            sections.append("")
            sections.append("💬 CONTEXT:")
            sections.append(_escape(context))

    # Source and tags are always appended
    source_name = data.get("source_name", "")
    if source_name:
        sections.append("")
        sections.append(f"📌 Source: {_escape(source_name)}")

    if tags:
        tag_str = " ".join(f"#{_escape(t)}" for t in tags[:5])
        sections.append(f"🏷️ {tag_str}")

    text = "\n".join(sections).strip()

    # Truncate if over Telegram limit
    if len(text) > _MAX_TELEGRAM_LENGTH:
        text = text[: _MAX_TELEGRAM_LENGTH - 1].rsplit("\n", 1)[0] + "\n…"

    return text


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
    """Produce a formatted Telegram HTML post using AI-structured data and templates.

    Returns the rendered HTML string ready to send with parse_mode='HTML'.
    """
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

    source_names = list(dict.fromkeys(e.source_name for e in cluster))
    source_name_str = source_names[0] if source_names else "Unknown"

    prompt = f"""You are a tech news bot analyzing stories for a Telegram channel.

Given the following stories about the same event, return a JSON object with these fields:

{{
  "urgency": "breaking|alert|analysis|market|explainer",
  "headline": "short punchy headline",
  "summary": "1-2 sentence summary of what happened",
  "key_points": ["point 1", "point 2", "point 3"],
  "metrics": ["metric 1 if available"],
  "timeline": "when it happened / status timeline if available",
  "market_impact": "how it affects prices or market if relevant",
  "who_affected": ["protocol/user type affected"],
  "what_to_do": ["actionable steps if alert/breaking"],
  "context": "why this matters, background or precedent",
  "tldr": "one sentence summary",
  "tags": ["Topic1", "Topic2", "Topic3"]
}}

Classification guide:
- "breaking": active exploit, major outage, critical vulnerability being exploited NOW
- "alert": vulnerability disclosed, action required, upcoming deadline
- "analysis": regulation, governance, policy, research report
- "market": price action, trading volume, ETF flows, token launches
- "explainer": education, how something works, deep dive context

Rules:
- Report facts only — no opinions, no speculation, no buy/sell advice
- Never closely mirror any single article's wording
- If sources disagree, note it in context
- Return ONLY valid JSON, no preamble, no markdown code fences
{source_note}

Stories covering the same event:
{headlines}"""

    raw_output = None
    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("Groq API returned empty content")
            raw_output = content.strip()
            break
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Groq API attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt, _MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.exception(
                    "Groq API failed after %d attempts for cluster starting with '%s'",
                    _MAX_RETRIES, cluster[0].title,
                )

    # Parse JSON from AI output
    if raw_output is None:
        data = _fallback_data(cluster, urgent)
    else:
        try:
            data = _parse_ai_json(raw_output)
        except ValueError:
            logger.warning("Failed to parse AI output as JSON, using fallback. Raw: %.200s", raw_output)
            data = _fallback_data(cluster, urgent)

    # Validate
    is_valid, reason = _validate_ai_data(data)
    if not is_valid:
        logger.warning("AI output validation failed (%s), using fallback", reason)
        data = _fallback_data(cluster, urgent)

    # Inject source info
    data["source_name"] = source_name_str

    # Override urgency if caller specified urgent
    if urgent and data.get("urgency") not in ("breaking", "alert"):
        data["urgency"] = "alert"

    return render_template(data)


def _fallback_data(cluster: list[Entry], urgent: bool) -> dict:
    """Produce a minimal valid dict when AI output fails parsing/validation."""
    primary = cluster[0]
    urgency = "alert" if urgent else "analysis"
    source_names = list(dict.fromkeys(e.source_name for e in cluster))

    return {
        "urgency": urgency,
        "headline": primary.title,
        "summary": primary.summary[:200],
        "key_points": [f"Reported by: {', '.join(source_names[:3])}"],
        "tags": ["News"],
    }
