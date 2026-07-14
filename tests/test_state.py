"""Tests for state.py — FileState backend (no Redis required)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import FileState, reset_state


class TestFileState:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._sub_path = os.path.join(self._tmp, "subscribers.json")
        self._posted_path = os.path.join(self._tmp, "posted_ids.json")
        self.state = FileState(self._sub_path, self._posted_path)

    def teardown_method(self):
        for f in [self._sub_path, self._posted_path]:
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self._tmp)
        reset_state()

    def test_load_subscribers_empty(self):
        assert self.state.load_subscribers() == set()

    def test_save_and_load_subscribers(self):
        ids = {123, 456, 789}
        self.state.save_subscribers(ids)
        assert self.state.load_subscribers() == ids

    def test_save_subscribers_replaces_previous(self):
        self.state.save_subscribers({111})
        self.state.save_subscribers({222, 333})
        assert self.state.load_subscribers() == {222, 333}

    def test_corrupt_subscribers_file_returns_empty(self):
        with open(self._sub_path, "w") as f:
            f.write("not valid json {{{")
        assert self.state.load_subscribers() == set()

    def test_missing_subscribers_file_returns_empty(self):
        assert self.state.load_subscribers() == set()

    def test_load_posted_ids_empty(self):
        assert self.state.load_posted_ids() == set()

    def test_save_and_load_posted_ids(self):
        ids = {"entry-1", "entry-2", "entry-3"}
        self.state.save_posted_ids(ids)
        assert self.state.load_posted_ids() == ids

    def test_save_posted_ids_replaces_previous(self):
        self.state.save_posted_ids({"old-id"})
        self.state.save_posted_ids({"new-id"})
        assert self.state.load_posted_ids() == {"new-id"}

    def test_corrupt_posted_ids_file_returns_empty(self):
        with open(self._posted_path, "w") as f:
            f.write("{broken}")
        assert self.state.load_posted_ids() == set()

    def test_missing_posted_ids_file_returns_empty(self):
        assert self.state.load_posted_ids() == set()

    def test_add_posted_ids_merges(self):
        self.state.save_posted_ids({"a"})
        self.state.add_posted_ids({"b", "c"})
        assert self.state.load_posted_ids() == {"a", "b", "c"}

    def test_add_posted_ids_no_duplicates(self):
        self.state.save_posted_ids({"a", "b"})
        self.state.add_posted_ids({"b", "c"})
        assert self.state.load_posted_ids() == {"a", "b", "c"}

    def test_add_posted_ids_to_empty(self):
        self.state.add_posted_ids({"x"})
        assert self.state.load_posted_ids() == {"x"}
