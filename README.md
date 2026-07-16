# Inbound News Bot

A Telegram bot that fetches tech, crypto, and cybersecurity news from 15 RSS feeds, clusters related stories, rewrites them with AI into urgency-based templates, and broadcasts digests to subscribers.

- **Schedule**: 5 AM & 5 PM Phnom Penh time (UTC+7)
- **On-demand**: `/fetch` triggers a digest immediately (5-minute cooldown)
- **Format**: Facts only — no opinions, no speculation, no buy/sell advice

## How It Works

```
15 RSS Feeds → fetch (with timeout) → cluster → looks_urgent → rewrite_with_ai → broadcast
```

1. **Fetch** — pulls latest items from 15 RSS feeds (5 per feed max, 15s timeout per feed)
2. **Cluster** — groups related headlines using title+summary similarity (threshold 0.45)
3. **Rewrite** — Groq (Llama 3.3 70B) classifies urgency + category and returns structured JSON
4. **Render** — one of 5 templates is selected based on urgency level
5. **Broadcast** — sends story to the channel thread + all subscribers
6. **Dedup** — logs posted entry IDs so nothing repeats

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
| `/fetch` | Trigger a digest right now (5-min cooldown) |

## News Categories

Stories are classified into one of 8 categories:

| Category | Topics |
|----------|--------|
| Startups | Funding rounds, launches, founder stories, acquisitions |
| AI & ML | Models, tools, research breakthroughs, AI applications |
| Cybersecurity | Vulnerabilities, breaches, threats, security research |
| DeFi & Crypto | Tokens, protocols, blockchain, exchanges, Web3 |
| Big Tech | Apple, Google, Meta, Microsoft, Amazon — product moves, antitrust |
| Hardware & Devices | Chips, GPUs, phones, wearables, robotics |
| Science & Research | Breakthroughs, quantum, materials, space, batteries |
| Regulation & Policy | Government policy, legislation, privacy law, court rulings |

## Output Templates

Each story is classified by urgency and rendered with the matching template:

**Breaking** 🚨 — Active exploit, major outage, critical vulnerability:
```
🚨 CRITICAL: <headline>
📂 Cybersecurity

<summary>

📊 KEY METRICS:
• metric 1
• metric 2

⚠️ WHY IT MATTERS:
<context>

🔍 DETAILS:
• point 1
• point 2

⏰ <timeline>

📌 Source: <name> | <links>

#Tag1 #Tag2
```

**Alert** ⚠️ — Vulnerability disclosed, action required:
```
⚠️ ALERT: <headline>
📂 <category>

<summary>

🛡️ WHAT TO DO:
• action 1
• action 2

📍 AFFECTED:
• affected group

⏰ <timeline>

📌 Source: <name> | <links>

#Tag1 #Tag2
```

**Analysis** 📊 — Regulation, governance, policy, research:
```
📊 <headline>
📂 <category>

<summary>

💡 KEY POINTS:
• point 1
• point 2

📈 MARKET IMPACT:
<impact>

🎯 WHO THIS AFFECTS:
• group 1

💬 CONTEXT:
<context>

📌 Source: <name> | <links>

#Tag1 #Tag2
```

**Market** 💹 — Price action, trading volume, token launches:
```
💹 <headline>
📂 <category>

<summary>

📊 KEY POINTS:
• data 1
• data 2

📈 MARKET IMPACT:
<impact>

📌 Source: <name> | <links>

#Tag1 #Tag2
```

**Explainer** 📚 — Education, how something works, deep dive:
```
📚 EXPLAINER: <headline>
📂 <category>

<summary>

🔹 KEY POINTS:
• point 1

🔹 WHAT TO WATCH:
• trend 1

💡 TL;DR:
<one-line summary>

📌 Source: <name> | <links>

#Tag1 #Tag2
```

## Project Structure

```
news_bot.py     Entry point — scheduler, handlers, main loop
config.py       RSS feeds (15), categories, urgency levels, constants
feeds.py        RSS fetching (with timeout), normalization, clustering, urgency detection
ai.py           AI prompt, structured JSON parsing (3-level fallback), 5 templates, retry logic
bot.py          State management, broadcast logic, auto-unsubscribe on blocked users
health.py       HTTP health server for Render
tests/          83 tests (feeds, AI validation, templates, state management)
```

## Testing

```bash
python -m pytest tests/ -v
ruff check . --exclude venv
```

## Reliability Features

- **AI retry** — 3 attempts with exponential backoff on API failures
- **Feed timeout** — 15s timeout per feed; slow/dead feeds don't block the pipeline
- **Rate limiting** — `/fetch` limited to once per 5 minutes per chat
- **Auto-unsubscribe** — users who block the bot are automatically removed
- **Structured JSON** — AI output parsed with 3-level fallback (direct → code fence → regex)

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
