"""Tests for ai.py — JSON parsing, validation, template rendering, and utilities."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feeds import Entry
from ai import (
    _parse_ai_json,
    _validate_ai_data,
    _md_bold_to_html,
    _fallback_data,
    render_template,
    trim_for_caption,
    collect_links,
    pick_image_url,
)


# --- JSON Parsing ---

class TestParseAiJson:
    def test_direct_json(self):
        raw = '{"urgency": "analysis", "headline": "Test", "summary": "Sum"}'
        result = _parse_ai_json(raw)
        assert result["urgency"] == "analysis"
        assert result["headline"] == "Test"

    def test_json_in_code_fence(self):
        raw = '```json\n{"urgency": "breaking", "headline": "X", "summary": "Y"}\n```'
        result = _parse_ai_json(raw)
        assert result["urgency"] == "breaking"

    def test_json_in_code_fence_without_label(self):
        raw = '```\n{"urgency": "alert", "headline": "A", "summary": "B"}\n```'
        result = _parse_ai_json(raw)
        assert result["urgency"] == "alert"

    def test_json_with_preamble(self):
        raw = 'Here is the result:\n{"urgency": "market", "headline": "BTC", "summary": "Up"}'
        result = _parse_ai_json(raw)
        assert result["urgency"] == "market"

    def test_invalid_json_raises(self):
        raw = "This is not JSON at all"
        try:
            _parse_ai_json(raw)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


# --- Validation ---

class TestValidateAiData:
    def test_valid_data(self):
        data = {"urgency": "analysis", "headline": "Test", "summary": "Sum"}
        is_valid, reason = _validate_ai_data(data)
        assert is_valid is True
        assert reason is None

    def test_missing_urgency(self):
        data = {"headline": "Test", "summary": "Sum"}
        is_valid, reason = _validate_ai_data(data)
        assert is_valid is False
        assert "urgency" in reason

    def test_missing_headline(self):
        data = {"urgency": "analysis", "summary": "Sum"}
        is_valid, reason = _validate_ai_data(data)
        assert is_valid is False
        assert "headline" in reason

    def test_empty_headline(self):
        data = {"urgency": "analysis", "headline": "  ", "summary": "Sum"}
        is_valid, reason = _validate_ai_data(data)
        assert is_valid is False
        assert "headline" in reason

    def test_invalid_urgency(self):
        data = {"urgency": "invalid", "headline": "Test", "summary": "Sum"}
        is_valid, reason = _validate_ai_data(data)
        assert is_valid is False
        assert "urgency" in reason

    def test_non_list_key_points(self):
        data = {"urgency": "analysis", "headline": "Test", "summary": "Sum", "key_points": "not a list"}
        is_valid, reason = _validate_ai_data(data)
        assert is_valid is False
        assert "key_points" in reason


# --- Template Rendering ---

class TestRenderTemplate:
    def test_breaking_template(self):
        data = {
            "urgency": "breaking",
            "headline": "Major Exploit",
            "summary": "Protocol hacked for $10M.",
            "key_points": ["Flash loan used", "Oracle manipulated"],
            "metrics": ["Loss: $10M", "Status: Investigating"],
            "context": "This is the third attack this month.",
            "timeline": "2:00 AM UTC | Discovered 3:30 AM UTC",
            "tags": ["DeFi", "Security"],
            "source_name": "CoinDesk",
        }
        result = render_template(data)
        assert "🚨 CRITICAL:" in result
        assert "<b>Major Exploit</b>" in result
        assert "Protocol hacked" in result
        assert "📊 KEY METRICS:" in result
        assert "Loss: $10M" in result
        assert "⚠️ WHY IT MATTERS:" in result
        assert "third attack" in result
        assert "🔍 DETAILS:" in result
        assert "Flash loan used" in result
        assert "⏰ 2:00 AM UTC" in result
        assert "📌 Source: CoinDesk" in result
        assert "#DeFi #Security" in result

    def test_alert_template(self):
        data = {
            "urgency": "alert",
            "headline": "Vulnerability in Compound V2",
            "summary": "Medium-severity bug disclosed.",
            "what_to_do": ["Check positions", "De-risk if needed"],
            "who_affected": ["Users with <150% collateral"],
            "timeline": "Patch in 7-10 days",
            "tags": ["Security", "DeFi"],
            "source_name": "Compound Forum",
        }
        result = render_template(data)
        assert "⚠️ ALERT:" in result
        assert "<b>Vulnerability in Compound V2</b>" in result
        assert "🛡️ WHAT TO DO:" in result
        assert "Check positions" in result
        assert "📍 AFFECTED:" in result
        assert "Users with" in result
        assert "⏰ Patch in 7-10 days" in result
        assert "📌 Source: Compound Forum" in result

    def test_analysis_template(self):
        data = {
            "urgency": "analysis",
            "headline": "SEC Proposes DeFi Framework",
            "summary": "New guidance on governance tokens.",
            "key_points": ["Governance tokens may be securities", "2-year safe harbor"],
            "market_impact": "Bitcoin +1.2% on clarity.",
            "who_affected": ["DAOs", "DeFi protocols"],
            "context": "First clear language on DAO tokens.",
            "tags": ["Regulation", "DeFi"],
            "source_name": "The Block",
        }
        result = render_template(data)
        assert "📊 <b>SEC Proposes" in result
        assert "💡 KEY POINTS:" in result
        assert "Governance tokens may be securities" in result
        assert "📈 MARKET IMPACT:" in result
        assert "Bitcoin +1.2%" in result
        assert "🎯 WHO THIS AFFECTS:" in result
        assert "💬 CONTEXT:" in result
        assert "📌 Source: The Block" in result

    def test_market_template(self):
        data = {
            "urgency": "market",
            "headline": "BTC Breaks $65K",
            "summary": "Bitcoin surges on ETF inflows.",
            "key_points": ["Current: $65,420", "+3.2% 24h"],
            "market_impact": "Bullish breakout confirmed.",
            "tags": ["BTC", "Bitcoin"],
            "source_name": "CoinGecko",
        }
        result = render_template(data)
        assert "💹 <b>BTC Breaks $65K</b>" in result
        assert "📊 KEY POINTS:" in result
        assert "📈 MARKET IMPACT:" in result
        assert "Bullish breakout" in result
        assert "📌 Source: CoinGecko" in result

    def test_explainer_template(self):
        data = {
            "urgency": "explainer",
            "headline": "How Oracle Attacks Work",
            "summary": "DeFi relies on price feeds attackers can manipulate.",
            "key_points": ["Oracles feed prices", "Flash loans amplify attacks"],
            "what_to_watch": ["Chainlink v2 adoption", "Regulatory response"],
            "tldr": "DeFi price feeds are a weak link.",
            "tags": ["Oracles", "DeFi"],
            "source_name": "Messari",
        }
        result = render_template(data)
        assert "📚 EXPLAINER:" in result
        assert "<b>How Oracle Attacks Work</b>" in result
        assert "🔹 KEY POINTS:" in result
        assert "🔹 WHAT TO WATCH:" in result
        assert "💡 TL;DR:" in result
        assert "DeFi price feeds are a weak link." in result
        assert "📌 Source: Messari" in result

    def test_defaults_to_analysis(self):
        data = {"urgency": "unknown", "headline": "Test", "summary": "Sum"}
        result = render_template(data)
        assert "📊 <b>Test</b>" in result

    def test_truncation_over_limit(self):
        data = {
            "urgency": "analysis",
            "headline": "Test",
            "summary": "x" * 4500,
        }
        result = render_template(data)
        assert len(result) <= 4000
        assert result.endswith("…")


# --- Fallback Data ---

class TestFallbackData:
    def test_fallback_normal(self):
        entries = [Entry(id="1", title="Test Story", summary="Summary text", link="http://a.com", source_name="TechCrunch")]
        data = _fallback_data(entries, urgent=False)
        assert data["urgency"] == "analysis"
        assert data["headline"] == "Test Story"
        assert data["summary"] == "Summary text"
        assert "TechCrunch" in data["key_points"][0]

    def test_fallback_urgent(self):
        entries = [Entry(id="1", title="Critical Bug", summary="Major issue", link="http://a.com", source_name="A")]
        data = _fallback_data(entries, urgent=True)
        assert data["urgency"] == "alert"
        assert data["headline"] == "Critical Bug"

    def test_fallback_multiple_sources(self):
        entries = [
            Entry(id="1", title="Story", summary="s", link="http://a.com", source_name="TechCrunch"),
            Entry(id="2", title="Story", summary="s", link="http://b.com", source_name="The Verge"),
        ]
        data = _fallback_data(entries, urgent=False)
        assert "TechCrunch" in data["key_points"][0]
        assert "The Verge" in data["key_points"][0]


# --- Existing Utilities ---

class TestMdBoldToHtml:
    def test_bold_conversion(self):
        assert _md_bold_to_html("**Hello** world") == "<b>Hello</b> world"

    def test_multiple_bold(self):
        result = _md_bold_to_html("**A** and **B**")
        assert result == "<b>A</b> and <b>B</b>"

    def test_no_bold(self):
        result = _md_bold_to_html("No bold here")
        assert result == "No bold here"

    def test_html_escaping(self):
        result = _md_bold_to_html("**<script>**")
        assert "<b>&lt;script&gt;</b>" in result

    def test_apostrophe_not_escaped(self):
        result = _md_bold_to_html("It's a test")
        assert "It's" in result


class TestTrimForCaption:
    def test_short_text(self):
        assert trim_for_caption("hello", limit=100) == "hello"

    def test_long_text(self):
        long = "a" * 2000
        result = trim_for_caption(long, limit=100)
        assert len(result) <= 100
        assert result.endswith("…")


class TestCollectLinks:
    def test_unique_links(self):
        entries = [
            Entry(id="1", title="A", summary="", link="http://a.com", source_name="A"),
            Entry(id="2", title="B", summary="", link="http://a.com", source_name="B"),
            Entry(id="3", title="C", summary="", link="http://c.com", source_name="C"),
        ]
        links = collect_links(entries)
        assert len(links) == 2
        assert "http://a.com" in links
        assert "http://c.com" in links

    def test_urgent_cap(self):
        entries = [Entry(id=str(i), title=str(i), summary="", link=f"http://{i}.com", source_name="X") for i in range(5)]
        links = collect_links(entries, urgent=True)
        assert len(links) == 3

    def test_normal_cap(self):
        entries = [Entry(id=str(i), title=str(i), summary="", link=f"http://{i}.com", source_name="X") for i in range(8)]
        links = collect_links(entries, urgent=False)
        assert len(links) == 5


class TestPickImageUrl:
    def test_first_image(self):
        entries = [
            Entry(id="1", title="A", summary="", link="http://a.com", source_name="A", image_url=None),
            Entry(id="2", title="B", summary="", link="http://b.com", source_name="B", image_url="http://img.com/x.jpg"),
        ]
        assert pick_image_url(entries) == "http://img.com/x.jpg"

    def test_no_image(self):
        entries = [Entry(id="1", title="A", summary="", link="http://a.com", source_name="A")]
        assert pick_image_url(entries) is None
