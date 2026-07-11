# Inbound News Bot

Auto-generated news bot that fetches tech + crypto headlines, rewrites them with AI (facts only, no advice/opinions), and broadcasts them to Telegram. Runs on a schedule (5 AM / 5 PM Phnom Penh time) or on manual trigger. This is v1 of the pipeline — Telegram first, website sync comes later.

## How it works

1. **Fetch** — pulls the latest items from a list of RSS feeds (tech news + crypto)
2. **Rewrite** — sends each headline/summary to Groq's API (free tier, Llama 3.3 70B) to rewrite as a short, factual Telegram post. No opinions, no "buy/sell" language — just what happened.
3. **Broadcast** — sends the post to everyone who has subscribed via `/start`
4. **Dedup** — keeps a local log of what's already been posted so nothing repeats

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

- **`/start`** — subscribes the current chat (DM, group, or channel) to news broadcasts
- **`/stop`** — unsubscribes
- **`/fetch`** — manually triggers a fetch + broadcast right now (use this for testing instead of waiting for 5 AM/5 PM)

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
- No moderation/filter pass on AI output yet — currently trusting the prompt constraints; consider adding an automated check for advice-language before posting
- Live crypto price data (not just news) not wired in yet — could pull from CoinGecko's free API

## Questions / bugs

Ping Sothun, Vichea, Raksa, or Hourmeng in the team group.
