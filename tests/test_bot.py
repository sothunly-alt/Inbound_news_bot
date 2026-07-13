"""Tests for bot.py — state management and broadcast logic."""

import os
import tempfile
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override file paths to use temp directory before importing bot
import config  # noqa: E402
config.SUBSCRIBERS_LOG = os.path.join(tempfile.gettempdir(), "test_subscribers.json")
config.POSTED_LOG = os.path.join(tempfile.gettempdir(), "test_posted_ids.json")

from bot import (  # noqa: E402
    load_subscribers,
    save_subscribers,
    load_posted_ids,
    save_posted_ids,
)


class TestSubscribers:
    def setup_method(self):
        """Clean up before each test."""
        for f in [config.SUBSCRIBERS_LOG, config.POSTED_LOG]:
            if os.path.exists(f):
                os.remove(f)

    def teardown_method(self):
        """Clean up after each test."""
        for f in [config.SUBSCRIBERS_LOG, config.POSTED_LOG]:
            if os.path.exists(f):
                os.remove(f)

    def test_load_empty(self):
        assert load_subscribers() == set()

    def test_save_and_load(self):
        ids = {123, 456, 789}
        save_subscribers(ids)
        loaded = load_subscribers()
        assert loaded == ids

    def test_corrupt_file_returns_empty(self):
        with open(config.SUBSCRIBERS_LOG, "w") as f:
            f.write("not valid json {{{")
        assert load_subscribers() == set()


class TestPostedIds:
    def setup_method(self):
        for f in [config.SUBSCRIBERS_LOG, config.POSTED_LOG]:
            if os.path.exists(f):
                os.remove(f)

    def teardown_method(self):
        for f in [config.SUBSCRIBERS_LOG, config.POSTED_LOG]:
            if os.path.exists(f):
                os.remove(f)

    def test_load_empty(self):
        assert load_posted_ids() == set()

    def test_save_and_load(self):
        ids = {"entry-1", "entry-2", "entry-3"}
        save_posted_ids(ids)
        loaded = load_posted_ids()
        assert loaded == ids

    def test_corrupt_file_returns_empty(self):
        with open(config.POSTED_LOG, "w") as f:
            f.write("{broken}")
        assert load_posted_ids() == set()
