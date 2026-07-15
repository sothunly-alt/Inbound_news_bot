"""Persistent state backends for subscriber and posted-ID storage.

Uses Redis (Upstash) when REDIS_URL is set — survives Render/Railway restarts.
Falls back to local JSON files for local development.
"""

import json
import logging
import os
import tempfile
import threading
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Posted IDs expire after 30 days to prevent unbounded growth.
POSTED_ID_TTL_SECONDS: int = 30 * 24 * 60 * 60

_SUBSCRIBERS_KEY = "newsbot:subscribers"
_POSTED_ID_PREFIX = "newsbot:posted:"
_POSTED_TITLE_PREFIX = "newsbot:posted_title:"


class StateBackend(ABC):
    """Interface for persistent state storage."""

    @abstractmethod
    def load_subscribers(self) -> set[int]:
        ...

    @abstractmethod
    def save_subscribers(self, ids: set[int]) -> None:
        ...

    @abstractmethod
    def load_posted_ids(self) -> set[str]:
        ...

    @abstractmethod
    def save_posted_ids(self, ids: set[str]) -> None:
        ...

    @abstractmethod
    def add_posted_ids(self, ids: set[str]) -> None:
        ...

    @abstractmethod
    def load_posted_titles(self) -> set[str]:
        ...

    @abstractmethod
    def save_posted_titles(self, titles: set[str]) -> None:
        ...

    @abstractmethod
    def add_posted_titles(self, titles: set[str]) -> None:
        ...


class RedisState(StateBackend):
    """Redis-backed state using sets with TTL for posted IDs."""

    def __init__(self, redis_url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        self._r.ping()
        logger.info("Redis state backend connected.")

    def load_subscribers(self) -> set[int]:
        raw = self._r.smembers(_SUBSCRIBERS_KEY)
        return {int(cid) for cid in raw}

    def save_subscribers(self, ids: set[int]) -> None:
        pipe = self._r.pipeline()
        pipe.delete(_SUBSCRIBERS_KEY)
        if ids:
            pipe.sadd(_SUBSCRIBERS_KEY, *(str(cid) for cid in ids))
        pipe.execute()

    def load_posted_ids(self) -> set[str]:
        posted: set[str] = set()
        cursor = 0
        while True:
            cursor, keys = self._r.scan(cursor, match=f"{_POSTED_ID_PREFIX}*", count=200)
            for key in keys:
                posted.add(key[len(_POSTED_ID_PREFIX):])
            if cursor == 0:
                break
        return posted

    def save_posted_ids(self, ids: set[str]) -> None:
        pipe = self._r.pipeline()
        cursor = 0
        while True:
            cursor, keys = self._r.scan(cursor, match=f"{_POSTED_ID_PREFIX}*", count=200)
            if keys:
                pipe.delete(*keys)
            if cursor == 0:
                break
        for entry_id in ids:
            pipe.set(f"{_POSTED_ID_PREFIX}{entry_id}", "1", ex=POSTED_ID_TTL_SECONDS)
        pipe.execute()

    def add_posted_ids(self, ids: set[str]) -> None:
        pipe = self._r.pipeline()
        for entry_id in ids:
            pipe.set(f"{_POSTED_ID_PREFIX}{entry_id}", "1", ex=POSTED_ID_TTL_SECONDS)
        pipe.execute()

    def load_posted_titles(self) -> set[str]:
        posted: set[str] = set()
        cursor = 0
        while True:
            cursor, keys = self._r.scan(cursor, match=f"{_POSTED_TITLE_PREFIX}*", count=200)
            for key in keys:
                posted.add(key[len(_POSTED_TITLE_PREFIX):])
            if cursor == 0:
                break
        return posted

    def save_posted_titles(self, titles: set[str]) -> None:
        pipe = self._r.pipeline()
        cursor = 0
        while True:
            cursor, keys = self._r.scan(cursor, match=f"{_POSTED_TITLE_PREFIX}*", count=200)
            if keys:
                pipe.delete(*keys)
            if cursor == 0:
                break
        for title in titles:
            pipe.set(f"{_POSTED_TITLE_PREFIX}{title}", "1", ex=POSTED_ID_TTL_SECONDS)
        pipe.execute()

    def add_posted_titles(self, titles: set[str]) -> None:
        pipe = self._r.pipeline()
        for title in titles:
            pipe.set(f"{_POSTED_TITLE_PREFIX}{title}", "1", ex=POSTED_ID_TTL_SECONDS)
        pipe.execute()


class FileState(StateBackend):
    """Local JSON file state — for development and non-Redis deployments.

    All reads/writes are protected by a threading.Lock.
    Writes use atomic temp-file + rename to prevent corruption.
    """

    def __init__(self, subscribers_path: str, posted_path: str) -> None:
        self._subscribers_path = subscribers_path
        self._posted_path = posted_path
        self._lock = threading.Lock()

    def _atomic_write(self, path: str, data: object) -> None:
        """Write JSON atomically: write to temp file, then os.replace (POSIX-safe)."""
        dir_name = os.path.dirname(path) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp_path, path)
        except OSError:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load_subscribers(self) -> set[int]:
        if os.path.exists(self._subscribers_path):
            try:
                with open(self._subscribers_path, "r") as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, OSError):
                logger.exception("Failed to load %s", self._subscribers_path)
        return set()

    def save_subscribers(self, ids: set[int]) -> None:
        try:
            self._atomic_write(self._subscribers_path, list(ids))
        except OSError:
            logger.exception("Failed to save %s", self._subscribers_path)

    def load_posted_ids(self) -> set[str]:
        if os.path.exists(self._posted_path):
            try:
                with open(self._posted_path, "r") as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, OSError):
                logger.exception("Failed to load %s", self._posted_path)
        return set()

    def save_posted_ids(self, ids: set[str]) -> None:
        try:
            self._atomic_write(self._posted_path, list(ids))
        except OSError:
            logger.exception("Failed to save %s", self._posted_path)

    def add_posted_ids(self, ids: set[str]) -> None:
        with self._lock:
            existing = self.load_posted_ids()
            existing.update(ids)
            self.save_posted_ids(existing)

    def _posted_titles_path(self) -> str:
        return self._posted_path.replace(".json", "_titles.json")

    def load_posted_titles(self) -> set[str]:
        path = self._posted_titles_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, OSError):
                logger.exception("Failed to load %s", path)
        return set()

    def save_posted_titles(self, titles: set[str]) -> None:
        try:
            self._atomic_write(self._posted_titles_path(), list(titles))
        except OSError:
            logger.exception("Failed to save %s", self._posted_titles_path())

    def add_posted_titles(self, titles: set[str]) -> None:
        with self._lock:
            existing = self.load_posted_titles()
            existing.update(titles)
            self.save_posted_titles(existing)


_state: StateBackend | None = None
_state_lock = threading.Lock()


def get_state() -> StateBackend:
    """Return the active state backend (Redis if REDIS_URL set, else File).

    Thread-safe: uses double-checked locking for the singleton.
    """
    global _state
    if _state is not None:
        return _state

    with _state_lock:
        if _state is not None:
            return _state

        redis_url = os.environ.get("REDIS_URL", "").strip()
        if redis_url:
            try:
                _state = RedisState(redis_url)
                return _state
            except Exception:
                logger.exception("Failed to connect to Redis — falling back to file state")

        from config import POSTED_LOG, SUBSCRIBERS_LOG

        _state = FileState(SUBSCRIBERS_LOG, POSTED_LOG)
        logger.info("Using file-based state backend.")
        return _state


def reset_state() -> None:
    """Reset the cached state backend (for testing)."""
    global _state
    _state = None
