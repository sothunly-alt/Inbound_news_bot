"""Telegram bot handlers, broadcast logic, and state management."""

import logging
from typing import Optional

from telegram.ext import ContextTypes

from ai import rewrite_with_ai
from config import (
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_THREAD_ID,
)
from feeds import cluster_entries, collect_new_entries, looks_urgent
from state import get_state

logger = logging.getLogger(__name__)


async def broadcast(context: ContextTypes.DEFAULT_TYPE, posts: list[str]) -> None:
    """Send posts to the configured channel (if any) plus /start subscribers."""
    targets: dict[int, Optional[int]] = {}

    if TELEGRAM_CHANNEL_ID is not None:
        targets[TELEGRAM_CHANNEL_ID] = TELEGRAM_THREAD_ID

    for chat_id in get_state().load_subscribers():
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
) -> int:
    """Fetch feeds, cluster, rewrite, and broadcast.

    All clusters are processed. Urgent stories get the [URGENT: ...] prefix.
    Everything is bundled into a single digest message.

    Returns the number of individual stories actually posted (0 if there
    was nothing new, or nothing could be turned into a post), so callers
    like the /fetch command can tell "ran fine, nothing new" apart from
    "posted N stories" instead of staying silent either way.
    """
    state = get_state()
    posted_ids = state.load_posted_ids()
    entries = collect_new_entries(posted_ids)
    if not entries:
        logger.info("No new entries.")
        return 0

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
        return 0

    if len(new_posts) > 1:
        header = f"Tech digest — {len(new_posts)} stories\n\n"
        digest = header + "\n\n———\n\n".join(new_posts)
        await broadcast(context, [digest])
    else:
        await broadcast(context, new_posts)

    state.save_posted_ids(posted_ids)
    logger.info("Sent %d post(s).", len(new_posts))
    return len(new_posts)
