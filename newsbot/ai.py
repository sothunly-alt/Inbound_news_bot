"""AI-powered story rewriting via Groq API with structured JSON output and template rendering."""

from __future__ import annotations

import html
import json
import logging
import re
import time
from typing import Any

from newsbot.config import (
    DIGEST_MIN_SOURCES,
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    LINK_CAP_NORMAL,
    LINK_CAP_URGENT,
    NEWS_CATEGORIES_SET,
    URGENCY_LEVELS_SET,
)
from newsbot.feeds import Entry

__all__ = [
    "render_template",
    "trim_for_caption",
    "collect_links",
    "pick_image_url",
    "rewrite_with_ai",
]

logger = logging.getLogger(__name__)

_MAX_TELEGRAM_LENGTH: int = 4096
_CAPTION_MAX: int = 1024
_MAX_RETRIES: int = 3
_RETRY_BASE_DELAY: float = 1.0

_REQUIRED_JSON_KEYS = ("urgency", "headline", "summary", "category")


def _html_escape(text: str) -> str:
    """HTML-escape text for Telegram (no quote escaping — Telegram doesn't need it)."""
    return html.escape(text, quote=False)


def _parse_ai_json(raw: str) -> dict:
    """Parse JSON from AI output, handling markdown code fences and preamble text."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*?\}", raw, re.DOTALL)
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

    if data["urgency"] not in URGENCY_LEVELS_SET:
        return False, f"Invalid urgency level: '{data['urgency']}'"

    if data["category"] not in NEWS_CATEGORIES_SET:
        return False, f"Invalid category: '{data['category']}'"

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


def _bullet_list(items: list[str], limit: int = 5) -> str:
    """Render items as bullet points."""
    return "\n".join(f"• {_html_escape(item)}" for item in items[:limit])


_CATEGORY_LABELS: dict[str, str] = {
    "startups": "Startups",
    "ai": "AI & ML",
    "cybersecurity": "Cybersecurity",
    "defi": "DeFi & Crypto",
    "big_tech": "Big Tech",
    "hardware": "Hardware & Devices",
    "science": "Science & Research",
    "regulation": "Regulation & Policy",
}


def _render_header(data: dict) -> list[str]:
    """Render the shared header (headline prefix, category, date) for all templates."""
    headline = _html_escape(data.get("headline", "Untitled"))
    category_label = _CATEGORY_LABELS.get(data.get("category", ""), "")
    published_date = data.get("published_date", "")
    sections: list[str] = []
    if category_label:
        sections.append(f"📂 {category_label}")
    if published_date:
        sections.append(f"📅 {_html_escape(published_date)}")
    if sections:
        sections.append("")
    return sections


def _render_footer(data: dict) -> list[str]:
    """Render the shared footer (source, tags) for all templates."""
    sections: list[str] = []
    source_name = data.get("source_name", "")
    if source_name:
        sections.append("")
        sections.append(f"📌 Source: {_html_escape(source_name)}")
    tags = data.get("tags", [])
    if tags:
        tag_str = " ".join(f"#{_html_escape(t)}" for t in tags[:5])
        sections.append(f"🏷️ {tag_str}")
    return sections


def render_template(data: dict) -> str:
    """Render AI-structured data into a Telegram HTML message using the appropriate template."""
    urgency = data.get("urgency", "analysis")
    headline = _html_escape(data.get("headline", "Untitled"))
    summary = _html_escape(data.get("summary", ""))
    key_points = data.get("key_points", [])

    sections: list[str] = []

    if urgency == "breaking":
        sections.append(f"🚨 CRITICAL: <b>{headline}</b>")
        sections.extend(_render_header(data))
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
            sections.append(_html_escape(why_matters))
        if key_points:
            sections.append("")
            sections.append("🔍 DETAILS:")
            sections.append(_bullet_list(key_points))
        timeline = data.get("timeline", "")
        if timeline:
            sections.append("")
            sections.append(f"⏰ {_html_escape(timeline)}")

    elif urgency == "alert":
        sections.append(f"⚠️ ALERT: <b>{headline}</b>")
        sections.extend(_render_header(data))
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
            sections.append(f"⏰ {_html_escape(timeline)}")

    elif urgency == "market":
        sections.append(f"💹 <b>{headline}</b>")
        sections.extend(_render_header(data))
        sections.append(summary)
        if key_points:
            sections.append("")
            sections.append("📊 KEY POINTS:")
            sections.append(_bullet_list(key_points))
        market_impact = data.get("market_impact", "")
        if market_impact:
            sections.append("")
            sections.append("📈 MARKET IMPACT:")
            sections.append(_html_escape(market_impact))

    elif urgency == "explainer":
        sections.append(f"📚 EXPLAINER: <b>{headline}</b>")
        sections.extend(_render_header(data))
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
            sections.append(f"💡 TL;DR: {_html_escape(tldr)}")

    else:  # analysis (default)
        sections.append(f"📊 <b>{headline}</b>")
        sections.extend(_render_header(data))
        sections.append(summary)
        if key_points:
            sections.append("")
            sections.append("💡 KEY POINTS:")
            sections.append(_bullet_list(key_points))
        market_impact = data.get("market_impact", "")
        if market_impact:
            sections.append("")
            sections.append("📈 MARKET IMPACT:")
            sections.append(_html_escape(market_impact))
        who = data.get("who_affected", [])
        if who:
            sections.append("")
            sections.append("🎯 WHO THIS AFFECTS:")
            sections.append(_bullet_list(who))
        context = data.get("context", "")
        if context:
            sections.append("")
            sections.append("💬 CONTEXT:")
            sections.append(_html_escape(context))

    sections.extend(_render_footer(data))

    text = "\n".join(sections).strip()
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
    cap = LINK_CAP_URGENT if urgent else LINK_CAP_NORMAL
    return links[:cap]


def pick_image_url(cluster: list[Entry]) -> str | None:
    """First available image URL from the cluster."""
    for entry in cluster:
        if entry.image_url:
            return entry.image_url
    return None


def _build_prompt(cluster: list[Entry], source_note: str) -> str:
    """Build the AI prompt for a cluster of related stories."""
    headlines = "\n".join(
        f"- [{e.source_name}] {e.title}: {e.summary[:200]}"
        for e in cluster[:5]
    )
    return f"""You are a tech news bot analyzing stories for a Telegram channel.

Given the following stories about the same event, return a JSON object with these fields:

{{
  "urgency": "breaking|alert|analysis|market|explainer",
  "category": "startups|ai|cybersecurity|defi|big_tech|hardware|science|regulation",
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

Urgency classification:
- "breaking": active exploit, major outage, critical vulnerability being exploited NOW
- "alert": vulnerability disclosed, action required, upcoming deadline
- "analysis": regulation, governance, policy, research report
- "market": price action, trading volume, ETF flows, token launches
- "explainer": education, how something works, deep dive context

Category classification:
- "startups": funding rounds, new company launches, founder stories, acquisitions, startup trends
- "ai": AI/ML models, tools, research breakthroughs, AI applications, AI companies
- "cybersecurity": vulnerabilities, breaches, threats, malware, security research, ransomware
- "defi": crypto tokens, DeFi protocols, blockchain, exchanges, Web3
- "big_tech": Apple, Google, Meta, Microsoft, Amazon, Netflix — product moves, strategy, antitrust
- "hardware": chips, GPUs, CPUs, devices, phones, wearables, robotics,半导体
- "science": research breakthroughs, academic papers, quantum, materials, space, batteries
- "regulation": government policy, legislation, antitrust, privacy law, compliance, court rulings

Rules:
- Report facts only — no opinions, no speculation, no buy/sell advice
- Never closely mirror any single article's wording
- If sources disagree, note it in context
- Return ONLY valid JSON, no preamble, no markdown code fences
{source_note}

Stories covering the same event:
{headlines}"""


def _call_groq_with_retry(prompt: str) -> str | None:
    """Call the Groq API with retry logic. Returns raw output or None on failure."""
    from newsbot.config import create_groq_client

    client = create_groq_client()
    raw_output = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=GROQ_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("Groq API returned empty content")
            raw_output = content.strip()
            break
        except Exception as exc:
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Groq API attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt, _MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.exception("Groq API failed after %d attempts", _MAX_RETRIES)
    return raw_output


def _process_ai_output(
    raw_output: str | None,
    cluster: list[Entry],
    urgent: bool,
) -> dict:
    """Parse and validate AI output, falling back gracefully on failure."""
    if raw_output is None:
        data = _fallback_data(cluster, urgent)
    else:
        try:
            data = _parse_ai_json(raw_output)
        except ValueError:
            logger.warning("Failed to parse AI output as JSON, using fallback. Raw: %.200s", raw_output)
            data = _fallback_data(cluster, urgent)

    is_valid, reason = _validate_ai_data(data)
    if not is_valid:
        logger.warning("AI output validation failed (%s), using fallback", reason)
        data = _fallback_data(cluster, urgent)
        is_valid, _ = _validate_ai_data(data)
        if not is_valid:
            logger.error("Fallback data also failed validation — using hardcoded minimal data")
            data = {
                "urgency": "alert",
                "category": "startups",
                "headline": cluster[0].title or "Untitled Story",
                "summary": (cluster[0].summary or "No summary available.")[:200],
                "key_points": [],
                "tags": [],
            }
    return data


def rewrite_with_ai(cluster: list[Entry], urgent: bool = False, header: str | None = None) -> str:
    """Produce a formatted Telegram HTML post using AI-structured data and templates."""
    links = collect_links(cluster, urgent=urgent)

    source_note = ""
    if len(links) < DIGEST_MIN_SOURCES:
        source_note = (
            f"\nNote: only {len(links)} source(s) available so far "
            f"(prefer {DIGEST_MIN_SOURCES}+ when possible)."
        )

    source_names = list(dict.fromkeys(e.source_name for e in cluster))
    source_name_str = source_names[0] if source_names else "Unknown"

    prompt = _build_prompt(cluster, source_note)
    raw_output = _call_groq_with_retry(prompt)
    data = _process_ai_output(raw_output, cluster, urgent)

    data["source_name"] = source_name_str

    primary_date = cluster[0].published_date if cluster else None
    if primary_date:
        data["published_date"] = primary_date

    if urgent and data.get("urgency") not in ("breaking", "alert"):
        data["urgency"] = "alert"

    rendered = render_template(data)
    if header:
        rendered = f"{header}\n\n{rendered}"

    return rendered


def _fallback_data(cluster: list[Entry], urgent: bool) -> dict:
    """Produce a minimal valid dict when AI output fails parsing/validation."""
    primary = cluster[0]
    urgency = "alert" if urgent else "analysis"
    source_names = list(dict.fromkeys(e.source_name for e in cluster))

    title = (primary.title or "").strip() or "Untitled Story"
    summary = (primary.summary or "No summary available.")[:200]

    return {
        "urgency": urgency,
        "category": "startups",
        "headline": title,
        "summary": summary,
        "key_points": [f"Reported by: {', '.join(source_names[:3])}"],
        "tags": ["News"],
    }
