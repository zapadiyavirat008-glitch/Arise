# My Personal AI — Telegram Bot (Python + Gemini)

A private Telegram bot that talks to you using Google Gemini, with memory
of your conversation.

## What you need before deploying

1. Your **Telegram bot token** (from BotFather) — you already have this.
2. Your **Gemini API key** (from aistudio.google.com) — you already have this.
3. A free **GitHub** account.
4. A free **Render** account (render.com) — sign up with GitHub, it's faster.

## Step 1 — Push this code to GitHub

1. Go to github.com, log in, click **"New repository"**.
2. Name it something like `my-ai-bot`. Keep it **Private** if you want.
3. Click **"uploading an existing file"** and upload these 3 files:
   - `main.py`
   - `requirements.txt`
   - `README.md`
4. Commit / save.

## Step 2 — Deploy on Render

1. Go to render.com, sign in with GitHub.
2. Click **"New +"** → **"Web Service"**.
3. Select your `my-ai-bot` repository.
4. Fill in:
   - **Name:** anything, e.g. `my-ai-bot`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Instance Type:** Free
5. Scroll to **Environment Variables** and add:
   - `BOT_TOKEN` = your Telegram bot token
   - `GEMINI_API_KEY` = your Gemini API key
6. Click **"Create Web Service"**.

Render will now build and start your bot. Watch the **Logs** tab — once you
see `Bot starting...` with no errors, it's live.

## Step 3 — Test it

Open Telegram, message your bot with anything (e.g. "hi"). It should reply
using Gemini, and remember earlier messages in the same conversation.

Send `/reset` anytime to wipe its memory of your chat and start fresh.

## Notes on the free tier

- Render's free web services **sleep after inactivity** and take ~30-60
  seconds to wake up on the next message. This is normal on free hosting.
- Conversation memory currently lives in the bot's RAM — if Render restarts
  the service (which can happen on the free tier), memory resets. This is
  fine to start with; we can add permanent memory (a real database) later.

## Next upgrades we can add later

- Document upload & analysis (send a PDF, bot reads and remembers it)
- Persistent memory across restarts
- Web search grounding
- Custom personality / instructions
