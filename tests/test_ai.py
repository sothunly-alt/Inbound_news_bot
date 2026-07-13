"""Tests for ai.py — output validation and fallback formatting."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feeds import Entry
from ai import _validate_output, _fallback_format


class TestValidateOutput:
    def test_valid_normal_output(self):
        text = "**New iPhone Released**\n- What happened: Apple launched iPhone 16.\n- Why it matters: Competition increases.\n- Extra context: Samsung also has a new phone."
        is_valid, reason = _validate_output(text)
        assert is_valid is True
        assert reason is None

    def test_valid_urgent_output(self):
        text = "**[URGENT: Critical Vulnerability]**\n- What happened: Chrome has a zero-day.\n- Why it matters: Users are at risk."
        is_valid, reason = _validate_output(text)
        assert is_valid is True
        assert reason is None

    def test_too_long(self):
        text = "**Test**\n" + "x" * 5000
        is_valid, reason = _validate_output(text)
        assert is_valid is False
        assert "too long" in reason.lower()

    def test_forbidden_buy_sell(self):
        text = "**Stock Tips**\n- What happened: You should buy now.\n- Why it matters: Guaranteed returns."
        is_valid, reason = _validate_output(text)
        assert is_valid is False
        assert reason is not None

    def test_forbidden_opinion(self):
        text = "**Market Update**\n- What happened: I think stocks will rise.\n- Why it matters: In my opinion, it's good."
        is_valid, reason = _validate_output(text)
        assert is_valid is False
        assert "Forbidden" in reason

    def test_missing_bold(self):
        text = "No bold formatting here\n- What happened: Test\n- Why it matters: Test"
        is_valid, reason = _validate_output(text)
        assert is_valid is False
        assert "bold" in reason.lower()


class TestFallbackFormat:
    def test_fallback_normal(self):
        entries = [Entry(id="1", title="Test Story", summary="Test summary", link="http://a.com", source_name="A")]
        result = _fallback_format(entries, urgent=False)
        assert "**Test Story**" in result
        assert "What happened" in result

    def test_fallback_urgent(self):
        entries = [Entry(id="1", title="Critical Bug", summary="Major issue", link="http://a.com", source_name="A")]
        result = _fallback_format(entries, urgent=True)
        assert "[URGENT]" in result
        assert "Critical Bug" in result

    def test_fallback_with_multiple_sources(self):
        entries = [
            Entry(id="1", title="Story", summary="summary", link="http://a.com", source_name="TechCrunch"),
            Entry(id="2", title="Story", summary="summary", link="http://b.com", source_name="Verge"),
        ]
        result = _fallback_format(entries, urgent=False)
        assert "Also reported by" in result
        assert "Verge" in result
