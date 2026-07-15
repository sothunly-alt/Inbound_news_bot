"""Tests for bot.py — ranking, StoryPost keyboard, and prepare helpers."""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feeds import Entry
from bot import (
    StoryPost,
    _rank_clusters,
    _source_keyboard,
    _prepare_digest,
    _prepare_urgent,
    broadcast_stories,
)


def _entry(
    id_: str,
    title: str = "Title",
    summary: str = "summary",
    link: str = "http://a.com",
    image_url: str | None = None,
) -> Entry:
    return Entry(
        id=id_,
        title=title,
        summary=summary,
        link=link,
        source_name="Src",
        image_url=image_url,
    )


class TestBotImports:
    def test_import_bot(self):
        from bot import fetch_and_post, fetch_urgent_and_post
        assert callable(fetch_and_post)
        assert callable(fetch_urgent_and_post)


class TestRankClusters:
    def test_prefers_multi_source(self):
        single = [_entry("1")]
        multi = [_entry("2"), _entry("3")]
        ranked = _rank_clusters([single, multi])
        assert ranked[0] is multi
        assert ranked[1] is single


class TestSourceKeyboard:
    def test_primary_read_more_button(self):
        post = StoryPost(text="x", primary_url="https://example.com/a")
        markup = _source_keyboard(post)
        assert markup.inline_keyboard[0][0].text == "Read more"
        assert markup.inline_keyboard[0][0].url == "https://example.com/a"

    def test_extra_source_buttons(self):
        post = StoryPost(
            text="x",
            primary_url="https://a.com",
            extra_urls=["https://b.com", "https://c.com", "https://d.com"],
        )
        markup = _source_keyboard(post)
        assert len(markup.inline_keyboard) == 2
        assert len(markup.inline_keyboard[1]) == 2
        assert markup.inline_keyboard[1][0].text == "Source 2"


class TestPrepareDigest:
    @patch("bot.cluster_entries")
    @patch("bot.collect_new_entries")
    @patch("bot.get_state")
    def test_returns_separate_stories(self, mock_state, mock_collect, mock_cluster):
        mock_state.return_value.load_posted_ids.return_value = set()
        mock_collect.return_value = [_entry(str(i), link=f"http://x.com/{i}") for i in range(12)]
        mock_cluster.return_value = [
            [_entry(str(i), title=f"T{i}", link=f"http://x.com/{i}")] for i in range(12)
        ]

        def fake_rewrite(cluster, urgent=False, header=None):
            prefix = f"{header}\n\n" if header else ""
            return f"{prefix}<b>{cluster[0].title}</b>\n\n▸ What happened: x"

        with patch("bot.rewrite_with_ai", side_effect=fake_rewrite) as mock_ai:
            stories = _prepare_digest()
        assert len(stories) == 10
        assert all(isinstance(s, StoryPost) for s in stories)
        assert "📰 1/10" in stories[0].text
        assert all("———" not in s.text for s in stories)
        assert mock_ai.call_count == 10


class TestPrepareUrgent:
    @patch("bot.rewrite_with_ai", return_value="<b>[URGENT: X]</b>")
    @patch("bot.looks_urgent")
    @patch("bot.cluster_entries")
    @patch("bot.collect_new_entries")
    @patch("bot.get_state")
    def test_only_urgent_and_skips_posted(
        self, mock_state, mock_collect, mock_cluster, mock_urgent, mock_ai
    ):
        mock_state.return_value.load_posted_ids.return_value = {"already"}
        mock_collect.return_value = [_entry("new1"), _entry("new2")]
        mock_cluster.return_value = [[_entry("new1")], [_entry("new2")]]
        mock_urgent.side_effect = [True, False]

        stories = _prepare_urgent()
        assert len(stories) == 1
        assert stories[0].entry_ids == {"new1"}
        mock_collect.assert_called_once_with({"already"})


def test_broadcast_stories_sends_separately_with_button():
    post1 = StoryPost(text="<b>One</b>", primary_url="https://a.com", entry_ids={"1"})
    post2 = StoryPost(
        text="<b>Two</b>",
        primary_url="https://b.com",
        image_url="https://img.com/x.jpg",
        entry_ids={"2"},
    )

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()
    mock_bot.send_photo = AsyncMock()
    context = MagicMock()
    context.bot = mock_bot

    async def _run():
        with patch("bot.TELEGRAM_CHANNEL_ID", -100), patch("bot.TELEGRAM_THREAD_ID", None), patch(
            "bot.get_state"
        ) as mock_state:
            mock_state.return_value.load_subscribers.return_value = set()
            return await broadcast_stories(context, [post1, post2])

    ids = asyncio.run(_run())

    assert ids == {"1", "2"}
    assert mock_bot.send_message.await_count == 1
    assert mock_bot.send_photo.await_count == 1
    msg_kwargs = mock_bot.send_message.await_args.kwargs
    assert msg_kwargs["reply_markup"].inline_keyboard[0][0].text == "Read more"
    photo_kwargs = mock_bot.send_photo.await_args.kwargs
    assert photo_kwargs["photo"] == "https://img.com/x.jpg"
    assert photo_kwargs["reply_markup"].inline_keyboard[0][0].url == "https://b.com"
