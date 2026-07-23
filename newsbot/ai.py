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

_TAG_RE = re.compile(r"<[^>]+>")
_KHMER_RE = re.compile(r"[\u1780-\u17FF]")


def _strip_html(text: str) -> str:
    """Remove HTML tags, collapse whitespace, and decode common entities."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


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
        km_key = f"{key}_km"
        if km_key in data and not isinstance(data[km_key], list):
            return False, f"Key '{km_key}' must be a list"

    return True, None


def _sanitize_ai_data(data: dict) -> dict:
    """Strip HTML tags from all string fields and list items in AI output."""
    _STRING_KEYS = (
        "headline", "headline_km", "summary", "summary_km",
        "context", "context_km", "timeline", "timeline_km",
        "market_impact", "market_impact_km", "tldr", "tldr_km",
    )
    _LIST_KEYS = (
        "key_points", "key_points_km", "metrics", "metrics_km",
        "what_to_do", "what_to_do_km", "who_affected", "who_affected_km",
        "what_to_watch", "what_to_watch_km", "tags",
    )
    for key in _STRING_KEYS:
        if key in data and isinstance(data[key], str):
            data[key] = _strip_html(data[key])
    for key in _LIST_KEYS:
        if key in data and isinstance(data[key], list):
            data[key] = [_strip_html(item) for item in data[key] if isinstance(item, str)]
    return data


def _has_khmer(text: str) -> bool:
    """Check if a string contains Khmer script characters."""
    return bool(_KHMER_RE.search(text))


def _validate_khmer_fields(data: dict) -> tuple[bool, list[str]]:
    """Validate that _km fields contain actual Khmer text, not just English fallback."""
    missing: list[str] = []
    string_keys = [
        ("headline", "headline_km"),
        ("summary", "summary_km"),
        ("context", "context_km"),
        ("timeline", "timeline_km"),
        ("market_impact", "market_impact_km"),
        ("tldr", "tldr_km"),
    ]
    list_keys = [
        ("key_points", "key_points_km"),
        ("metrics", "metrics_km"),
        ("what_to_do", "what_to_do_km"),
        ("who_affected", "who_affected_km"),
    ]
    for eng_key, km_key in string_keys:
        km_val = data.get(km_key, "")
        eng_val = data.get(eng_key, "")
        if km_val and not _has_khmer(str(km_val)):
            missing.append(km_key)
            logger.warning("Khmer field '%s' has no Khmer characters: %.50s", km_key, km_val)
        elif not km_val and eng_val:
            missing.append(km_key)
            logger.warning("Khmer field '%s' is missing (empty)", km_key)
    for eng_key, km_key in list_keys:
        km_val = data.get(km_key, [])
        eng_val = data.get(eng_key, [])
        if km_val:
            has_khmer_in_list = any(_has_khmer(str(item)) for item in km_val if isinstance(item, str))
            if not has_khmer_in_list:
                missing.append(km_key)
                logger.warning("Khmer field '%s' list has no Khmer characters: %s", km_key, km_val)
        elif eng_val:
            missing.append(km_key)
            logger.warning("Khmer field '%s' list is missing (empty)", km_key)
    return len(missing) == 0, missing


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


def _dedup_timeline(timeline: str, published_date: str) -> str:
    """Strip timeline if it just echoes the publication date."""
    if not timeline or not published_date:
        return timeline
    cleaned = re.sub(r"^(published\s+(?:on|:)?\s*)", "", timeline, flags=re.IGNORECASE).strip()
    if cleaned.lower() == published_date.strip().lower():
        return ""
    return timeline


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


_SEPARATOR = "\n\n➖➖➖➖➖➖➖\n\n"


def _get(data: dict, key: str, km: bool = False) -> Any:
    """Get a field from data, using _km variant if km=True, falling back to English."""
    if km:
        return data.get(f"{key}_km", data.get(key, ""))
    return data.get(key, "")


def _get_list(data: dict, key: str, km: bool = False) -> list[str]:
    """Get a list field from data, using _km variant if km=True, falling back to English."""
    if km:
        return data.get(f"{key}_km", data.get(key, []))
    return data.get(key, [])


def _render_one_language(data: dict, *, km: bool, urgency: str) -> str:
    """Render a single-language version of the story."""
    headline = _html_escape(str(_get(data, "headline", km=km) or "Untitled"))
    summary = _html_escape(str(_get(data, "summary", km=km) or ""))
    key_points = _get_list(data, "key_points", km=km)
    category_label = _CATEGORY_LABELS.get(data.get("category", ""), "")
    published_date = data.get("published_date", "")

    sections: list[str] = []

    if urgency == "breaking":
        critical = "⚠️ ប្រកាសអាសន្ន" if km else "🚨 CRITICAL"
        sections.append(f"{critical}: <b>{headline}</b>")
        if category_label or published_date:
            parts = []
            if category_label:
                parts.append(f"📂 {category_label}")
            if published_date:
                parts.append(f"📅 {_html_escape(published_date)}")
            sections.append(" | ".join(parts))
        sections.append("")
        sections.append(summary)
        metrics = _get_list(data, "metrics", km=km)
        if metrics:
            sections.append("")
            sections.append("📊 " + ("សូម្បីតែសំខាន់ៗ" if km else "KEY METRICS:"))
            sections.append(_bullet_list(metrics))
        what_to_do = _get_list(data, "what_to_do", km=km)
        if what_to_do:
            sections.append("")
            sections.append("🛡️ " + ("ជំហានដែលត្រូវធ្វើ" if km else "WHAT TO DO:"))
            sections.append(_bullet_list(what_to_do))
        context_val = str(_get(data, "context", km=km) or "")
        if context_val:
            sections.append("")
            sections.append("⚠️ " + ("ហេតុអ្វីសំខាន់" if km else "WHY IT MATTERS:"))
            sections.append(_html_escape(context_val))
        if key_points:
            sections.append("")
            sections.append("🔍 " + ("ព័ត៌មានលម្អិត" if km else "DETAILS:"))
            sections.append(_bullet_list(key_points))
        timeline = str(_get(data, "timeline", km=km) or "")
        if timeline:
            timeline = _dedup_timeline(timeline, data.get("published_date", ""))
            if timeline:
                sections.append("")
                sections.append(f"⏰ {_html_escape(timeline)}")

    elif urgency == "alert":
        alert_label = "⚠️ ព្រមាន" if km else "⚠️ ALERT"
        sections.append(f"{alert_label}: <b>{headline}</b>")
        if category_label or published_date:
            parts = []
            if category_label:
                parts.append(f"📂 {category_label}")
            if published_date:
                parts.append(f"📅 {_html_escape(published_date)}")
            sections.append(" | ".join(parts))
        sections.append("")
        sections.append(summary)
        what_to_do = _get_list(data, "what_to_do", km=km)
        if what_to_do:
            sections.append("")
            sections.append("🛡️ " + ("ជំហានដែលត្រូវធ្វើ" if km else "WHAT TO DO:"))
            sections.append(_bullet_list(what_to_do))
        who = _get_list(data, "who_affected", km=km)
        if who:
            sections.append("")
            sections.append("📍 " + ("រងផលប៉ះពាល់" if km else "AFFECTED:"))
            sections.append(_bullet_list(who))
        timeline = str(_get(data, "timeline", km=km) or "")
        if timeline:
            timeline = _dedup_timeline(timeline, data.get("published_date", ""))
            if timeline:
                sections.append("")
                sections.append(f"⏰ {_html_escape(timeline)}")

    elif urgency == "market":
        sections.append(f"💹 <b>{headline}</b>")
        if category_label or published_date:
            parts = []
            if category_label:
                parts.append(f"📂 {category_label}")
            if published_date:
                parts.append(f"📅 {_html_escape(published_date)}")
            sections.append(" | ".join(parts))
        sections.append("")
        sections.append(summary)
        if key_points:
            sections.append("")
            sections.append("📊 " + ("ចំណុចសំខាន់ៗ" if km else "KEY POINTS:"))
            sections.append(_bullet_list(key_points))
        market_impact = str(_get(data, "market_impact", km=km) or "")
        if market_impact:
            sections.append("")
            sections.append("📈 " + ("ផលប៉ះពាល់ទីផ្សារ" if km else "MARKET IMPACT:"))
            sections.append(_html_escape(market_impact))

    elif urgency == "explainer":
        explain_label = "📚 ពន្យល់" if km else "📚 EXPLAINER"
        sections.append(f"{explain_label}: <b>{headline}</b>")
        if category_label or published_date:
            parts = []
            if category_label:
                parts.append(f"📂 {category_label}")
            if published_date:
                parts.append(f"📅 {_html_escape(published_date)}")
            sections.append(" | ".join(parts))
        sections.append("")
        sections.append(summary)
        if key_points:
            sections.append("")
            sections.append("🔹 " + ("ចំណុចសំខាន់ៗ" if km else "KEY POINTS:"))
            sections.append(_bullet_list(key_points, limit=8))
        what_to_watch = _get_list(data, "what_to_watch", km=km)
        if what_to_watch:
            sections.append("")
            sections.append("🔹 " + ("ត្រូវចាប់អារម្មណ៍" if km else "WHAT TO WATCH:"))
            sections.append(_bullet_list(what_to_watch))
        tldr = str(_get(data, "tldr", km=km) or "")
        if tldr:
            sections.append("")
            sections.append("💡 TL;DR: " + _html_escape(tldr))

    else:  # analysis (default)
        sections.append(f"📊 <b>{headline}</b>")
        if category_label or published_date:
            parts = []
            if category_label:
                parts.append(f"📂 {category_label}")
            if published_date:
                parts.append(f"📅 {_html_escape(published_date)}")
            sections.append(" | ".join(parts))
        sections.append("")
        sections.append(summary)
        if key_points:
            sections.append("")
            sections.append("💡 " + ("ចំណុចសំខាន់ៗ" if km else "KEY POINTS:"))
            sections.append(_bullet_list(key_points))
        market_impact = str(_get(data, "market_impact", km=km) or "")
        if market_impact:
            sections.append("")
            sections.append("📈 " + ("ផលប៉ះពាល់ទីផ្សារ" if km else "MARKET IMPACT:"))
            sections.append(_html_escape(market_impact))
        who = _get_list(data, "who_affected", km=km)
        if who:
            sections.append("")
            sections.append("🎯 " + ("អ្នកដែលរងផលប៉ះពាល់" if km else "WHO THIS AFFECTS:"))
            sections.append(_bullet_list(who))
        context_val = str(_get(data, "context", km=km) or "")
        if context_val:
            sections.append("")
            sections.append("💬 " + ("បរិបទ" if km else "CONTEXT:"))
            sections.append(_html_escape(context_val))

    return "\n".join(sections)


def _render_footer(data: dict) -> str:
    """Render the shared footer (source, tags) — same for both languages."""
    sections: list[str] = []
    source_name = data.get("source_name", "")
    if source_name:
        sections.append(f"📌 Source: {_html_escape(source_name)}")
    tags = data.get("tags", [])
    if tags:
        tag_str = " ".join(f"#{_html_escape(t)}" for t in tags[:5])
        sections.append(f"🏷️ {tag_str}")
    return "\n".join(sections)


def render_template(data: dict) -> str:
    """Render AI-structured data into a bilingual Telegram HTML message (Khmer first, English second)."""
    urgency = data.get("urgency", "analysis")
    footer = _render_footer(data)

    km_text = _render_one_language(data, km=True, urgency=urgency)
    en_text = _render_one_language(data, km=False, urgency=urgency)

    text = f"{km_text}\n\n{_SEPARATOR}\n\n{en_text}"
    if footer:
        text = f"{text}\n\n{footer}"

    text = "\n".join(line for line in text.split("\n")).strip()
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
        f"- [{e.source_name}] {e.title}: {_strip_html(e.summary)[:200]} (Published: {e.published_date or 'unknown date'})"
        for e in cluster[:5]
    )
    return f"""You are a tech news bot analyzing stories for a bilingual Telegram channel (Khmer + English).

Given the following stories about the same event, return a JSON object with these fields.
ALL English fields must have a matching _km field with a natural Khmer translation (not robotic/machine-translated — write like a Cambodian tech journalist would).

CRITICAL: The _km fields MUST contain Khmer script (អក្សរខ្មែរ), NOT English text. Every _km field must use Khmer characters.

Example of correct Khmer output:
- headline_km: "ក្រុមហ៊ុន OpenAI ប្រកាសផលិតផល AI ថ្មីសម្រាប់អាជីវកម្ម"
- summary_km: "ក្រុមហ៊ុន OpenAI បានប្រកាសឧបករណ៍ AI ថ្មីដែលជួយសហគ្រិនក្នុងការបង្កើនប្រសិទ្ធផលិតភាព។ ឧបករណ៍នេះនឹងដាក់លក់នៅខែក្រោយ។"
- key_points_km: ["OpenAI ប្រកាសផលិតផល AI ថ្មី", "ឧបករណ៍នេះសម្រាប់អាជីវកម្ម", "នឹងដាក់លក់នៅខែក្រោយ"]

{{
  "urgency": "breaking|alert|analysis|market|explainer",
  "category": "startups|ai|cybersecurity|defi|big_tech|hardware|science|regulation",
  "headline": "short punchy headline in English",
  "headline_km": "ចំណងជើងខ្លីជាភាសាខ្មែរ",
  "summary": "1-2 sentence summary in English",
  "summary_km": "សង្ខេប ១-២ ឃ្លាជាភាសាខ្មែរ",
  "key_points": ["point 1", "point 2", "point 3"],
  "key_points_km": ["ចំណុច ១", "ចំណុច ២", "ចំណុច ៣"],
  "metrics": ["metric 1 if available"],
  "metrics_km": ["សូម្បីតែមាន"],
  "what_to_do": ["actionable steps if alert/breaking"],
  "what_to_do_km": ["ជំហានដែលត្រូវធ្វើ"],
  "who_affected": ["protocol/user type affected"],
  "who_affected_km": ["ប្រភេទអ្នកដែលរងផលប៉ះពាល់"],
  "context": "why this matters, background or precedent in English",
  "context_km": "ហេតុអ្វីនេះសំខាន់ជាភាសាខ្មែរ",
  "timeline": "status timeline or resolution updates only — do NOT repeat the publication date",
  "timeline_km": "ស្ថានភាពពេលវេលាជាភាសាខ្មែរ",
  "market_impact": "how it affects prices or market if relevant",
  "market_impact_km": "ផលប៉ះពាល់ទីផ្សារជាភាសាខ្មែរ",
  "tldr": "one sentence summary in English",
  "tldr_km": "សង្ខេបមួយឃ្លាជាភាសាខ្មែរ",
  "tags": ["Topic1", "Topic2", "Topic3"],
  "published_date": "the publication date from the sources, e.g. 'Jul 16, 2026'"
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
- "hardware": chips, GPUs, CPUs, devices, phones, wearables, robotics
- "science": research breakthroughs, academic papers, quantum, materials, space, batteries
- "regulation": government policy, legislation, antitrust, privacy law, compliance, court rulings

Rules:
- Report facts only — no opinions, no speculation, no buy/sell advice
- Never closely mirror any single article's wording
- If sources disagree, note it in context
- Khmer translations must sound natural — use proper Khmer tech vocabulary, not word-for-word translation
- CRITICAL: ALL _km fields MUST contain Khmer text, never English. The Khmer section is for Cambodian readers.
- CRITICAL: Do NOT include any HTML tags (no <div>, <p>, <a>, <img>, <br>, <span>, etc.) in any field — plain text only
- Return ONLY valid JSON, no preamble, no markdown code fences
{source_note}

Stories covering the same event:
{headlines}"""


def _build_km_retry_prompt(cluster: list[Entry], source_note: str, missing_km: list[str]) -> str:
    """Build a retry prompt focused on generating missing Khmer fields."""
    headlines = "\n".join(
        f"- [{e.source_name}] {e.title}: {_strip_html(e.summary)[:200]}"
        for e in cluster[:5]
    )
    km_fields = ", ".join(f'"{k}"' for k in missing_km)
    return f"""You are a Cambodian tech journalist writing for a bilingual Telegram channel.

Generate ONLY the following Khmer fields for a news story:
{km_fields}

Write natural, fluent Khmer — like a real Cambodian tech journalist, not machine-translated.

Example of good Khmer tech writing:
- "ក្រុមហ៊ុន Apple បានប្រកាសផលិតផលថ្មី" (Apple announced a new product)
- "ការវាយប្រហារ סיបर​មានការកើនឡើង" (Cyberattacks are increasing)
- "តម្លៃ Bitcoin បានកើនឡើង ៥% ក្នុងរយៈពេល ២៤ ម៉ោង" (Bitcoin price rose 5% in 24 hours)

Return ONLY valid JSON with the requested fields, no preamble.

Stories:
{headlines}{source_note}"""


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
) -> tuple[dict, list[str]]:
    """Parse and validate AI output, falling back gracefully on failure.
    
    Returns:
        Tuple of (data dict, list of missing Khmer fields)
    """
    if raw_output is None:
        data = _fallback_data(cluster, urgent)
    else:
        try:
            data = _parse_ai_json(raw_output)
        except ValueError:
            logger.warning("Failed to parse AI output as JSON, using fallback. Raw: %.200s", raw_output)
            data = _fallback_data(cluster, urgent)

    data = _sanitize_ai_data(data)

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
                "headline_km": cluster[0].title or "Untitled Story",
                "summary": (cluster[0].summary or "No summary available.")[:200],
                "summary_km": (cluster[0].summary or "No summary available.")[:200],
                "key_points": [],
                "key_points_km": [],
                "tags": [],
            }
    
    khmer_ok, missing_km = _validate_khmer_fields(data)
    return data, missing_km if not khmer_ok else []


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
    data, missing_km = _process_ai_output(raw_output, cluster, urgent)

    # Retry once with Khmer-focused prompt if Khmer fields are missing
    if missing_km:
        logger.warning(
            "Khmer fields missing after first attempt: %s — retrying with Khmer-focused prompt",
            missing_km,
        )
        km_prompt = _build_km_retry_prompt(cluster, source_note, missing_km)
        km_raw = _call_groq_with_retry(km_prompt)
        if km_raw is not None:
            try:
                km_data = _parse_ai_json(km_raw)
                km_data = _sanitize_ai_data(km_data)
                km_ok, _ = _validate_khmer_fields(km_data)
                if km_ok:
                    logger.info("Khmer retry succeeded — merging Khmer fields into data")
                    for key in missing_km:
                        if key in km_data:
                            data[key] = km_data[key]
                else:
                    logger.warning("Khmer retry still missing fields — using best effort")
            except ValueError:
                logger.warning("Khmer retry failed to parse as JSON — using best effort")

    data["source_name"] = source_name_str

    # Inject publication date from the primary entry
    primary_date = cluster[0].published_date if cluster else None
    if primary_date:
        data["published_date"] = primary_date

    # Override urgency if caller specified urgent
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
        "headline_km": title,
        "summary": summary,
        "summary_km": summary,
        "key_points": [f"Reported by: {', '.join(source_names[:3])}"],
        "key_points_km": [f"រាយការណ៍ដោយ: {', '.join(source_names[:3])}"],
        "tags": ["News"],
        "published_date": primary.published_date or "",
    }