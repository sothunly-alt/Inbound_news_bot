# Inbound News Bot

Auto-generated news bot that fetches tech + crypto headlines from multiple trusted RSS sources, clusters related stories, rewrites them with AI into a fixed Telegram format (facts only, no advice/opinions), and broadcasts digests to subscribers. Scheduled digests at 5 AM / 5 PM Phnom Penh time; urgent alerts send immediately. Telegram first — website sync comes later.

## How it works

1. **Fetch** — pulls the latest items from multiple trusted RSS feeds (tech, security, crypto)
2. **Cluster** — groups related headlines across feeds so one story can cite 2+ sources
3. **Rewrite** — Groq (Llama 3.3 70B) rewrites into a fixed format: What happened / Why it matters / Extra context / Sources. Urgent posts use a shorter URGENT template.
4. **Broadcast** — digests go to everyone who subscribed via `/start`; urgent alerts bypass the schedule
5. **Dedup** — keeps a local log of what's already been posted so nothing repeats

No manual chat ID entry needed. Anyone (you, teammates, the group, family) just sends `/start` to the bot once and they're subscribed to every future post. `/stop` unsubscribes.

## Setup (do this once)

**1. Clone the repo**
```bash
git clone https://github.com/yourusername/inbound-news.git
cd inbound-news
```

**2. Create a virtual environment**
```bash
python -m venv venv
```
Activate it:
- Windows (PowerShell): `.\venv\Scripts\Activate.ps1`
- Mac/Linux: `source venv/bin/activate`

**3. Install dependencies**
```bash
pip install python-telegram-bot feedparser openai pytz python-dotenv "python-telegram-bot[job-queue]"
```
(On Linux/Mac, add `--break-system-packages` if pip complains.)

**4. Set up your `.env` file**

Copy the example file and fill in your own keys — never commit this file, it's already gitignored.
```bash
cp .env.example .env
```
Then open `.env` and fill in:
```
TELEGRAM_BOT_TOKEN=
GROQ_API_KEY=
```

- **TELEGRAM_BOT_TOKEN** — ask in the team group for the shared bot token, or create your own test bot via @BotFather on Telegram (`/newbot`) for local development.
- **GROQ_API_KEY** — free, no card needed. Sign up at console.groq.com/keys and generate a key.

**5. Run it**
```bash
python news_bot.py
```

You should see:
```
Bot running. Anyone can /start to subscribe. Scheduled for 5 AM / 5 PM (Phnom Penh time).
```

## Using the bot

- **`/start`** — subscribes the current chat (DM, group, or channel) to digests + urgent alerts
- **`/stop`** — unsubscribes
- **`/fetch`** — manually triggers a full digest right now (use this for testing instead of waiting for 5 AM/5 PM)

Subscriptions are stored locally in `subscribers.json` (gitignored — each person running the bot has their own local copy, not shared through git).

## Project structure

```
news_bot.py       - main bot script
.env              - your local secrets (never committed)
.env.example      - template showing which env vars are needed
subscribers.json  - local list of subscribed chat IDs (auto-created, gitignored)
posted_ids.json   - local dedup log of already-posted items (auto-created, gitignored)
```

## Things to know before touching the code

- **Copyright**: the AI must rewrite in its own words, never closely mirror the original article. Every post includes a `Source:` link back to the original — this is required, don't remove it.
- **Trading content is facts-only**: no "buy", "sell", "should", or price predictions. Only report what happened (e.g. "Bitcoin dropped 8% in the last hour"). If you touch the prompt in `rewrite_with_ai()`, keep these constraints intact.
- **Only one bot instance can run at a time** per token — if you get a `Conflict: terminated by other getUpdates request` error, someone else (or another terminal) is already running the same token. Close other instances first.

## Adding more news sources

Add a URL to the `RSS_FEEDS` list near the top of `news_bot.py`:
```python
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://your-new-feed-url-here/",
]
```
No other code changes needed — the fetch loop handles any number of feeds.

## Known limitations / next steps

- Website sync (Telegram → website) not built yet — this is Telegram-only for now
- Story clustering is title-similarity based — related stories with very different headlines may stay separate
- No moderation/filter pass on AI output yet — currently trusting the prompt constraints
- Live crypto price data (not just news) not wired in yet — could pull from CoinGecko's free API
- Hosting / secrets setup is outside the bot script — use `.env` locally or your host's secret store

## Questions / bugs

Ping Sothun, Vichea, Raksa, or Hourmeng in the team group.
