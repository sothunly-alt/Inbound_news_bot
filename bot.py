"""Telegram bot handlers, broadcast logic, and state management."""

import json
import logging
import os
from typing import Optional

from telegram.ext import ContextTypes

from ai import rewrite_with_ai
from config import (
    POSTED_LOG,
    SUBSCRIBERS_LOG,
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_THREAD_ID,
)
from feeds import cluster_entries, collect_new_entries, looks_urgent

logger = logging.getLogger(__name__)


def load_subscribers() -> set[int]:
    """Load subscriber chat IDs from the local JSON file."""
    if os.path.exists(SUBSCRIBERS_LOG):
        try:
            with open(SUBSCRIBERS_LOG, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to load %s", SUBSCRIBERS_LOG)
    return set()


def save_subscribers(ids: set[int]) -> None:
    """Persist subscriber chat IDs to the local JSON file."""
    try:
        with open(SUBSCRIBERS_LOG, "w") as f:
            json.dump(list(ids), f)
    except OSError:
        logger.exception("Failed to save %s", SUBSCRIBERS_LOG)


def load_posted_ids() -> set[str]:
    """Load already-posted entry IDs for deduplication."""
    if os.path.exists(POSTED_LOG):
        try:
            with open(POSTED_LOG, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to load %s", POSTED_LOG)
    return set()


def save_posted_ids(ids: set[str]) -> None:
    """Persist posted entry IDs to the local JSON file."""
    try:
        with open(POSTED_LOG, "w") as f:
            json.dump(list(ids), f)
    except OSError:
        logger.exception("Failed to save %s", POSTED_LOG)


async def broadcast(context: ContextTypes.DEFAULT_TYPE, posts: list[str]) -> None:
    """Send posts to the configured channel (if any) plus /start subscribers."""
    targets: dict[int, Optional[int]] = {}

    if TELEGRAM_CHANNEL_ID is not None:
        targets[TELEGRAM_CHANNEL_ID] = TELEGRAM_THREAD_ID

    for chat_id in load_subscribers():
        targets.setdefault(int(chat_id), None)

    if not targets:
        logger.warning("No channel or subscribers configured — nothing to send.")
        return

    for chat_id, thread_id in targets.items():
        for post_text in posts:
            kwargs: dict = {"chat_id": chat_id, "text": post_text}
            if thread_id is not None:
                kwargs["message_thread_id"] = thread_id
            try:
                await context.bot.send_message(**kwargs)
            except Exception:
                logger.exception("Failed to send to %s", chat_id)


async def fetch_and_post(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Fetch feeds, cluster, rewrite, and broadcast.

    All clusters are processed. Urgent stories get the [URGENT: ...] prefix.
    Everything is bundled into a single digest message.
    """
    posted_ids = load_posted_ids()
    entries = collect_new_entries(posted_ids)
    if not entries:
        logger.info("No new entries.")
        return

    clusters = cluster_entries(entries)
    new_posts: list[str] = []

    for cluster in clusters:
        urgent = looks_urgent(cluster)
        try:
            post_text = rewrite_with_ai(cluster, urgent=urgent)
            new_posts.append(post_text)
            for entry in cluster:
                posted_ids.add(entry.id)
        except Exception:
            title = cluster[0].title if cluster else "?"
            logger.exception("Failed to generate post for '%s'", title)

    if not new_posts:
        logger.info("No posts generated this run.")
        return

    if len(new_posts) > 1:
        header = f"Tech digest — {len(new_posts)} stories\n\n"
        digest = header + "\n\n———\n\n".join(new_posts)
        await broadcast(context, [digest])
    else:
        await broadcast(context, new_posts)

    save_posted_ids(posted_ids)
    logger.info("Sent %d post(s).", len(new_posts))
