"""Tests for bot.py — broadcast and fetch_and_post logic."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBotImports:
    def test_import_bot(self):
        from bot import fetch_and_post
        assert callable(fetch_and_post)
