"""Telegram bot handlers, broadcast logic, and fetch pipelines."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from newsbot.ai import collect_links, pick_image_url, rewrite_with_ai, trim_for_caption
from newsbot.config import (
    DIGEST_MAX_STORIES,
    MAX_URGENT_POSTS_PER_RUN,
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_THREAD_ID,
    TIMEZONE,
)
from newsbot.feeds import Entry, cluster_entries, collect_new_entries, looks_urgent, normalize_title_key
from newsbot.state import get_state

__all__ = [
    "StoryPost",
    "broadcast_stories",
    "fetch_and_post",
    "fetch_urgent_and_post",
]

logger = logging.getLogger(__name__)

_pipeline_lock = asyncio.Lock()


@dataclass
class StoryPost:
    """One Telegram story ready to send."""

    text: str
    primary_url: str
    extra_urls: list[str] = field(default_factory=list)
    image_url: str | None = None
    entry_ids: set[str] = field(default_factory=set)
    entry_titles: set[str] = field(default_factory=set)


def _source_keyboard(post: StoryPost) -> InlineKeyboardMarkup:
    """Inline URL buttons: primary Read more + up to 2 more sources."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("Read more", url=post.primary_url)]
    ]
    extras: list[InlineKeyboardButton] = []
    for i, url in enumerate(post.extra_urls[:2], start=2):
        extras.append(InlineKeyboardButton(f"Source {i}", url=url))
    if extras:
        rows.append(extras)
    return InlineKeyboardMarkup(rows)


async def broadcast_stories(
    context: ContextTypes.DEFAULT_TYPE,
    stories: list[StoryPost],
) -> set[str]:
    """Send each story separately. Returns entry IDs that succeeded at least once."""
    targets: dict[int, int | None] = {}

    if TELEGRAM_CHANNEL_ID is not None:
        targets[TELEGRAM_CHANNEL_ID] = TELEGRAM_THREAD_ID

    state = get_state()
    for chat_id in state.load_subscribers():
        targets.setdefault(int(chat_id), None)

    if not targets:
        logger.warning("No channel or subscribers configured — nothing to send.")
        return set()

    succeeded_ids: set[str] = set()
    blocked_chats: set[int] = set()

    for post in stories:
        keyboard = _source_keyboard(post)
        story_ok = False
        for chat_id, thread_id in targets.items():
            if chat_id in blocked_chats:
                continue
            base: dict[str, Any] = {
                "chat_id": chat_id,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            }
            if thread_id is not None:
                base["message_thread_id"] = thread_id
            try:
                if post.image_url:
                    try:
                        await context.bot.send_photo(
                            photo=post.image_url,
                            caption=trim_for_caption(post.text),
                            **base,
                        )
                    except Forbidden:
                        logger.warning("Chat %s blocked the bot — will skip remaining stories", chat_id)
                        blocked_chats.add(chat_id)
                        continue
                    except BadRequest:
                        logger.warning("Photo failed for %s (bad request) — falling back to text", chat_id)
                        await context.bot.send_message(
                            text=post.text,
                            disable_web_page_preview=True,
                            **base,
                        )
                    except Exception:
                        logger.exception("Photo send failed for %s — falling back to text", chat_id)
                        await context.bot.send_message(
                            text=post.text,
                            disable_web_page_preview=True,
                            **base,
                        )
                else:
                    await context.bot.send_message(
                        text=post.text,
                        disable_web_page_preview=True,
                        **base,
                    )
                story_ok = True
            except Forbidden:
                logger.warning("Chat %s blocked the bot — will skip remaining stories", chat_id)
                blocked_chats.add(chat_id)
            except Exception:
                logger.exception("Failed to send story to %s", chat_id)
        if story_ok:
            succeeded_ids.update(post.entry_ids)

    if blocked_chats:
        subscribers = state.load_subscribers()
        removed = subscribers & blocked_chats
        if removed:
            state.save_subscribers(subscribers - blocked_chats)
            logger.info("Auto-unsubscribed %d blocked chat(s): %s", len(removed), removed)

    return succeeded_ids


def _rank_clusters(clusters: list[list[Entry]]) -> list[list[Entry]]:
    """Prefer multi-source clusters, then keep feed order within the same size."""
    indexed = list(enumerate(clusters))
    indexed.sort(key=lambda item: (-len(item[1]), item[0]))
    return [c for _, c in indexed]


def _cluster_to_story(
    cluster: list[Entry],
    *,
    urgent: bool,
    header: str | None = None,
) -> StoryPost | None:
    try:
        text = rewrite_with_ai(cluster, urgent=urgent, header=header)
    except Exception:
        title = cluster[0].title if cluster else "?"
        logger.exception("Failed to generate post for '%s'", title)
        return None

    links = collect_links(cluster, urgent=urgent)
    if not links:
        return None

    return StoryPost(
        text=text,
        primary_url=links[0],
        extra_urls=links[1:],
        image_url=pick_image_url(cluster),
        entry_ids={e.id for e in cluster},
        entry_titles={e.title for e in cluster},
    )


def _prepare_entries(urgent: bool = False, header: str | None = None) -> list[StoryPost]:
    """Shared pipeline: collect, cluster, rewrite entries."""
    state = get_state()
    posted_ids = state.load_posted_ids()
    posted_titles = state.load_posted_titles()
    entries = collect_new_entries(posted_ids, posted_titles)
    if not entries:
        logger.info("No new entries for %s.", "urgent" if urgent else "digest")
        return []

    if urgent:
        clusters = [
            c for c in cluster_entries(entries) if looks_urgent(c)
        ][:MAX_URGENT_POSTS_PER_RUN]
    else:
        clusters = _rank_clusters(cluster_entries(entries))[:DIGEST_MAX_STORIES]

    stories: list[StoryPost] = []
    n = len(clusters)
    for index, cluster in enumerate(clusters, start=1):
        if header and not urgent:
            today = datetime.now(TIMEZONE).strftime("%B %d, %Y")
            item_header = f"📰 {index}/{n} · {today}"
        else:
            item_header = None
        story = _cluster_to_story(cluster, urgent=urgent, header=item_header)
        if story:
            stories.append(story)
    return stories


def _mark_posted(stories: list[StoryPost], succeeded: set[str]) -> None:
    """Mark successfully sent stories as posted in state."""
    state = get_state()
    state.add_posted_ids(succeeded)
    titles = set()
    for s in stories:
        if s.entry_ids & succeeded:
            titles.update(normalize_title_key(t) for t in s.entry_titles)
    state.add_posted_titles(titles)


async def _run_pipeline(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    urgent: bool = False,
) -> int:
    """Shared async pipeline: prepare → broadcast → mark posted."""
    async with _pipeline_lock:
        stories = await asyncio.to_thread(_prepare_entries, urgent=urgent)
        if not stories:
            label = "urgent" if urgent else "digest"
            logger.info("No posts generated this %s run.", label)
            return 0

        succeeded = await broadcast_stories(context, stories)
        if succeeded:
            _mark_posted(stories, succeeded)
            count = sum(1 for s in stories if s.entry_ids & succeeded)
            label = "urgent" if urgent else "digest"
            logger.info("Sent %d %s stor(y/ies).", count, label)
            return count

        logger.error("Broadcast failed — not marking posted IDs.")
        return 0


async def fetch_and_post(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetch feeds, send each story separately (max DIGEST_MAX_STORIES)."""
    return await _run_pipeline(context, urgent=False)


async def fetch_urgent_and_post(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hourly urgent path: keyword matches only; skip already-posted IDs."""
    return await _run_pipeline(context, urgent=True)