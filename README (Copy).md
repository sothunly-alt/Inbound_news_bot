# Inbound News Bot

A Telegram bot that fetches tech, crypto, and cybersecurity news from 8 trusted RSS feeds, clusters related stories, rewrites them with AI into a clean fixed format, and broadcasts daily digests to subscribers.

- **Schedule**: 5 AM & 5 PM Phnom Penh time (UTC+7)
- **On-demand**: `/fetch` triggers a digest immediately
- **Format**: Facts only — no opinions, no speculation, no buy/sell advice

## How It Works

```
8 RSS Feeds → collect → cluster → looks_urgent → rewrite_with_ai → broadcast
```

1. **Fetch** — pulls latest items from 8 RSS feeds (5 per feed max)
2. **Cluster** — groups related headlines using title+summary similarity (threshold 0.45)
3. **Rewrite** — Groq (Llama 3.3 70B) rewrites into a fixed format with source links
4. **Broadcast** — sends a single digest message to the channel + all subscribers
5. **Dedup** — logs posted entry IDs so nothing repeats

## Setup

```bash
git clone https://github.com/sothunly-alt/Inbound_news_bot.git
cd Inbound_news_bot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your tokens
python news_bot.py
```

### Environment Variables

```
TELEGRAM_BOT_TOKEN=     # from @BotFather (required)
GROQ_API_KEY=           # from console.groq.com (required)
TELEGRAM_CHANNEL_ID=    # group/channel chat ID (required)
TELEGRAM_THREAD_ID=     # forum topic thread ID (optional)
PORT=                   # health server port (default: 10000)
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Subscribe to daily digests |
| `/stop` | Unsubscribe |
| `/fetch` | Trigger a digest right now |

## Output Format

**Normal:**
```
**<title>**
- What happened: <one sentence>
- Why it matters: <one sentence>
- Extra context: <one sentence>
- Sources: <link> | <link>
```

**Urgent:**
```
**[URGENT: <title>]**
- What happened: <one sentence>
- Why it matters: <one sentence>
- Sources: <link> | <link>
```

## Project Structure

```
news_bot.py     Entry point — scheduler, handlers, main loop
config.py       Configuration constants and env vars
feeds.py        RSS fetching, normalization, clustering, urgency detection
ai.py           AI rewriting with output validation and fallback
bot.py          State management (subscribers, dedup) and broadcast logic
health.py       HTTP health server for Render
tests/          38 tests (feeds, AI validation, state management)
```

## Testing

```bash
python -m pytest tests/ -v
ruff check . --exclude venv
```

## Deployment

- **Render**: Health server on port 10000 keeps bot alive. Set env vars in dashboard.
- **GitHub Actions**: Runs on cron `0 22` and `0 10` UTC (5 AM/5 PM Phnom Penh). Set secrets in repo settings.

## Adding News Sources

Add a URL to `RSS_FEEDS` in `config.py`:
```python
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://your-new-feed-url-here/",
]
```

## Known Limitations

- `posted_ids.json` is local/ephemeral — restarts can cause reposts
- Clustering is similarity-based — very different headlines on the same topic may stay separate
- Only one bot instance can run per token at a time

## Questions / Bugs

Ping Sothun, Vichea, Raksa, or Hourmeng in the team group.
