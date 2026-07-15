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

TELEGRAM_MAX_LEN = 4096


def _chunk_text(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    """Split text into <= limit-character chunks, breaking on newlines when possible.

    A single AI-rewritten story should almost never exceed 4096 chars, but
    this keeps a freak long post from failing outright instead of silently
    not sending.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            if len(line) > limit:
                for i in range(0, len(line), limit):
                    chunks.append(line[i : i + limit])
                current = ""
            else:
                current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def broadcast(context: ContextTypes.DEFAULT_TYPE, posts: list[str]) -> int:
    """Send posts to the configured channel (if any) plus /start subscribers.

    Each post is chunked individually if it exceeds Telegram's 4096-char
    limit, so one long story never breaks the whole send.

    Returns the number of chat targets that successfully received *all*
    posts, so callers can tell real delivery apart from a silent no-op.
    """
    targets: dict[int, Optional[int]] = {}

    if TELEGRAM_CHANNEL_ID is not None:
        targets[TELEGRAM_CHANNEL_ID] = TELEGRAM_THREAD_ID

    for chat_id in get_state().load_subscribers():
        targets.setdefault(int(chat_id), None)

    if not targets:
        logger.warning("No channel or subscribers configured — nothing to send.")
        return 0

    delivered = 0
    for chat_id, thread_id in targets.items():
        ok = True
        for post_text in posts:
            for chunk in _chunk_text(post_text):
                kwargs: dict = {"chat_id": chat_id, "text": chunk}
                if thread_id is not None:
                    kwargs["message_thread_id"] = thread_id
                try:
                    await context.bot.send_message(**kwargs)
                except Exception:
                    logger.exception("Failed to send to %s", chat_id)
                    ok = False
        if ok:
            delivered += 1

    if delivered == 0:
        logger.error("Broadcast had %d target(s) but delivered to none.", len(targets))

    return delivered


async def fetch_and_post(
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Fetch feeds, cluster, rewrite, and post each story individually
    as soon as it's ready — no digest bundling, no waiting to batch.

    Returns the number of stories actually delivered this run (0 if
    nothing new), so callers like /fetch can report an accurate count.
    """
    state = get_state()
    posted_ids = state.load_posted_ids()
    entries = collect_new_entries(posted_ids)
    if not entries:
        logger.info("No new entries.")
        return 0

    clusters = cluster_entries(entries)
    posted_count = 0

    for cluster in clusters:
        urgent = looks_urgent(cluster)
        title = cluster[0].title if cluster else "?"

        try:
            post_text = rewrite_with_ai(cluster, urgent=urgent)
        except Exception:
            logger.exception("Failed to generate post for '%s'", title)
            continue

        delivered = await broadcast(context, [post_text])
        if delivered == 0:
            logger.error("Generated post for '%s' but delivered to 0 chats.", title)
            # Don't mark as posted — retry this story next poll instead
            # of losing it silently.
            continue

        for entry in cluster:
            posted_ids.add(entry.id)
        posted_count += 1

        # Save after every successful post, not just at the end — if the
        # process dies mid-run, already-delivered stories stay marked done.
        state.save_posted_ids(posted_ids)

    if posted_count == 0:
        logger.info("No posts delivered this run.")
    else:
        logger.info(
            "Posted %d individual stor%s this run.",
            posted_count,
            "y" if posted_count == 1 else "ies",
        )

    return posted_count