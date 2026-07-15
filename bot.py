"""Telegram bot handlers, broadcast logic, and fetch pipelines."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ai import collect_links, pick_image_url, rewrite_with_ai, trim_for_caption
from config import (
    DIGEST_MAX_STORIES,
    MAX_URGENT_POSTS_PER_RUN,
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_THREAD_ID,
    TIMEZONE,
)
from feeds import Entry, cluster_entries, collect_new_entries, looks_urgent, normalize_title_key
from state import get_state

logger = logging.getLogger(__name__)


@dataclass
class StoryPost:
    """One Telegram story ready to send."""
    text: str
    primary_url: str
    extra_urls: list[str] = field(default_factory=list)
    image_url: Optional[str] = None
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
    targets: dict[int, Optional[int]] = {}

    if TELEGRAM_CHANNEL_ID is not None:
        targets[TELEGRAM_CHANNEL_ID] = TELEGRAM_THREAD_ID

    for chat_id in get_state().load_subscribers():
        targets.setdefault(int(chat_id), None)

    if not targets:
        logger.warning("No channel or subscribers configured — nothing to send.")
        return set()

    succeeded_ids: set[str] = set()

    for post in stories:
        keyboard = _source_keyboard(post)
        story_ok = False
        for chat_id, thread_id in targets.items():
            base: dict = {
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
                    except Exception:
                        logger.exception(
                            "Photo send failed for %s — falling back to text",
                            chat_id,
                        )
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
            except Exception:
                logger.exception("Failed to send story to %s", chat_id)
        if story_ok:
            succeeded_ids.update(post.entry_ids)

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


def _prepare_digest() -> list[StoryPost]:
    """Sync work: collect, cluster, rewrite up to DIGEST_MAX_STORIES."""
    state = get_state()
    posted_ids = state.load_posted_ids()
    posted_titles = state.load_posted_titles()
    entries = collect_new_entries(posted_ids, posted_titles)
    if not entries:
        logger.info("No new entries for digest.")
        return []

    today = datetime.now(TIMEZONE).strftime("%B %d, %Y")
    clusters = _rank_clusters(cluster_entries(entries))[:DIGEST_MAX_STORIES]
    n = len(clusters)
    stories: list[StoryPost] = []

    for index, cluster in enumerate(clusters, start=1):
        story = _cluster_to_story(
            cluster,
            urgent=False,
            header=f"📰 {index}/{n} · {today}",
        )
        if story:
            stories.append(story)

    return stories


def _prepare_urgent() -> list[StoryPost]:
    """Sync work: collect unseen entries, keep only keyword-urgent clusters."""
    state = get_state()
    posted_ids = state.load_posted_ids()
    posted_titles = state.load_posted_titles()
    entries = collect_new_entries(posted_ids, posted_titles)
    if not entries:
        logger.info("No new entries for urgent check.")
        return []

    urgent_clusters = [
        c for c in cluster_entries(entries) if looks_urgent(c)
    ][:MAX_URGENT_POSTS_PER_RUN]

    stories: list[StoryPost] = []
    for cluster in urgent_clusters:
        story = _cluster_to_story(cluster, urgent=True)
        if story:
            stories.append(story)
    return stories


async def fetch_and_post(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetch feeds, send each story separately (max DIGEST_MAX_STORIES)."""
    stories = await asyncio.to_thread(_prepare_digest)
    if not stories:
        logger.info("No posts generated this digest run.")
        return 0

    succeeded = await broadcast_stories(context, stories)
    if succeeded:
        state = get_state()
        state.add_posted_ids(succeeded)
        titles = set()
        for s in stories:
            if s.entry_ids & succeeded:
                titles.update(normalize_title_key(t) for t in s.entry_titles)
        state.add_posted_titles(titles)
        count = sum(1 for s in stories if s.entry_ids & succeeded)
        logger.info("Sent %d digest stor(y/ies).", count)
        return count

    logger.error("Digest broadcast failed — not marking posted IDs.")
    return 0


async def fetch_urgent_and_post(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hourly urgent path: keyword matches only; skip already-posted IDs."""
    stories = await asyncio.to_thread(_prepare_urgent)
    if not stories:
        logger.info("No urgent posts this hour.")
        return 0

    succeeded = await broadcast_stories(context, stories)
    if succeeded:
        state = get_state()
        state.add_posted_ids(succeeded)
        titles = set()
        for s in stories:
            if s.entry_ids & succeeded:
                titles.update(normalize_title_key(t) for t in s.entry_titles)
        state.add_posted_titles(titles)
        count = sum(1 for s in stories if s.entry_ids & succeeded)
        logger.info("Sent %d urgent post(s).", count)
        return count

    logger.error("Urgent broadcast failed — not marking posted IDs.")
    return 0
