import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import google.generativeai as genai

# ---- Config (set these as Environment Variables on Render, not in code) ----
BOT_TOKEN = os.environ["BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)

# Change this if you want a different Gemini model
MODEL_NAME = "gemini-3.6-flash"

SYSTEM_PROMPT = (
    "You are my personal AI assistant. Be helpful, clear, and concise. "
    "Remember context from earlier in our conversation. "
    "If I ask about academics, explain things step by step."
)

model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)

# ---- Simple in-memory conversation history per chat ----
# NOTE: this resets if the bot restarts. We can upgrade to persistent
# storage (a real database) later once this basic version works.
user_histories = {}
MAX_TURNS = 20  # how many back-and-forth messages to remember per user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_histories[chat_id] = []
    await update.message.reply_text(
        "Hi! I'm your personal AI. Just message me anything — questions, "
        "academic help, whatever you need. I'll remember our conversation "
        "as we go. Send /reset anytime to clear memory."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_histories[chat_id] = []
    await update.message.reply_text("Memory cleared. Fresh start!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    history = user_histories.get(chat_id, [])

    try:
        chat = model.start_chat(history=history)
        response = chat.send_message(text)
        reply = response.text
    except Exception as e:
        reply = f"Something went wrong talking to Gemini: {e}"
        await update.message.reply_text(reply)
        return

    # Update stored history with this exchange
    history.append({"role": "user", "parts": [text]})
    history.append({"role": "model", "parts": [reply]})
    user_histories[chat_id] = history[-(MAX_TURNS * 2):]

    await update.message.reply_text(reply)


# ---- Tiny web server so Render's free tier sees an open port ----
def run_health_server():
    app = Flask(__name__)

    @app.route("/")
    def health():
        return "Bot is running"

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
