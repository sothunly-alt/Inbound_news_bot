# Deploying the Inbound News Bot (Railway / Render)

This bot needs to run 24/7 to catch the 5 AM / 5 PM scheduled posts — it can't rely on anyone's laptop staying open. This doc covers deploying it to either **Railway** or **Render**, both of which have free/cheap tiers that work for this.

Pick one — you don't need both. Railway is generally the faster setup; Render's free tier has more restrictions (see notes below).

---

## Before you start (either platform)

This bot is a **background worker**, not a web server — it doesn't listen on an HTTP port, it just polls Telegram continuously. Both platforms default to expecting a web service, so we need to explicitly tell them this is a worker/background process. Details below per platform.

Make sure these two files exist in the repo root (create them if missing):

**`requirements.txt`**
```
python-telegram-bot[job-queue]
feedparser
openai
pytz
python-dotenv
```

**`Procfile`** (no file extension, just `Procfile`)
```
worker: python news_bot.py
```

Commit and push both to the repo before deploying.

---

## Option A: Railway

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select `sothunly-alt/Inbound_news_bot`
4. Railway will detect the `Procfile` and set up a worker service automatically. If it instead tries to spin up a web service, go to the service's **Settings → Deploy** and manually set the **Start Command** to:
   ```
   python news_bot.py
   ```
5. Go to the service's **Variables** tab and add:
   - `TELEGRAM_BOT_TOKEN` = (the real token)
   - `GROQ_API_KEY` = (the real key)
6. Deploy. Check the **Logs** tab — you should see:
   ```
   Bot running. Anyone can /start to subscribe. Scheduled for 5 AM / 5 PM (Phnom Penh time).
   ```
7. Test it — send `/fetch` to the bot on Telegram and confirm the logs show activity and a message lands in the subscribed chat.

**Cost note:** Railway's free tier gives a small monthly credit (check current limits on their pricing page — this changes over time). A lightweight polling bot like this uses very little compute, so it should comfortably fit unless the trial credit runs out — worth checking the billing tab after the first week.

---

## Option B: Render

1. Go to [render.com](https://render.com) and sign in with GitHub
2. Click **New → Background Worker** (important — NOT "Web Service", since this bot has no HTTP endpoint)
3. Connect the `sothunly-alt/Inbound_news_bot` repo
4. Configure:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python news_bot.py`
5. Under **Environment Variables**, add:
   - `TELEGRAM_BOT_TOKEN` = (the real token)
   - `GROQ_API_KEY` = (the real key)
6. Click **Create Background Worker** and wait for the build/deploy to finish
7. Check the **Logs** tab for the "Bot running..." message, then test with `/fetch`

**Free tier note:** Render's free tier for background workers may have monthly runtime limits or spin-down behavior — check Render's current free tier docs before relying on it long-term, since these limits change. If the free tier doesn't support always-on background workers, their cheapest paid tier (a few dollars/month) is the reliable option for a bot that needs to fire on a schedule.

---

## After deploying (either platform)

- **`subscribers.json` and `posted_ids.json`** are created locally at runtime and are gitignored — meaning on a fresh deploy, they start empty. Everyone (including previous subscribers) will need to send `/start` again to the deployed bot once it's live, since the local subscriber list from anyone's laptop testing doesn't carry over.
- **Only one instance of the bot can poll Telegram at a time** with the same token. Once it's deployed and running on Railway/Render, make sure nobody is also running `python news_bot.py` locally with the same `TELEGRAM_BOT_TOKEN` — you'll get a `Conflict: terminated by other getUpdates request` error if two instances run simultaneously.
- If you rotate the Telegram bot token or Groq key for security reasons, remember to update the environment variables on Railway/Render too, not just in your local `.env`.

## Quick platform comparison

| | Railway | Render |
|---|---|---|
| Setup speed | Faster, auto-detects Procfile | Slightly more manual (must pick "Background Worker" explicitly) |
| Free tier | Small monthly usage credit | Free tier may not support always-on workers — check current docs |
| Best for | Getting this running today | Fine too, just double-check worker support on free tier first |

If unsure, try Railway first — it's the more forgiving setup for a first deploy.
