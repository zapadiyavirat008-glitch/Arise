import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from google import genai
from google.genai import types

# ---- Config ----
BOT_TOKEN = os.environ["BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

client = genai.Client(api_key=GEMINI_API_KEY)

DEFAULT_MODEL = "gemini-3.6-flash"
IMAGE_MODEL = "imagen-4.0-fast-generate-001"  # a.k.a. "Nano Banana"

# ---- Arise's default personality ----
# Edit this to change her behavior everywhere. Individual chats can still
# override it with /persona without touching this default.
DEFAULT_PERSONA = (
    "You are Arise, a personal AI assistant. Your owner and the person you "
    "talk to is named Virat. You have a warm, mature, feminine personality — "
    "confident, a little witty, genuinely caring about Virat's goals, and "
    "you speak casually like a close friend rather than a formal assistant. "
    "You help with academics, answer questions clearly, and remember context "
    "from the conversation. You do not use excessive emojis or baby talk. "
    "Keep responses natural and conversational, not robotic."
)

MAX_TURNS = 20  # exchanges to keep in full detail per thread before summarizing

# ---- In-memory state ----
# user_data[chat_id] = {
#   "threads": { name: {"history": [...], "summary": "", "persona_override": None} },
#   "active_thread": "default",
#   "model": DEFAULT_MODEL,
#   "global_persona": DEFAULT_PERSONA,
# }
user_data = {}


def get_user(chat_id):
    if chat_id not in user_data:
        user_data[chat_id] = {
            "threads": {"default": {"history": [], "summary": "", "persona_override": None}},
            "active_thread": "default",
            "model": DEFAULT_MODEL,
            "global_persona": DEFAULT_PERSONA,
        }
    return user_data[chat_id]


def effective_persona(u, thread):
    return thread["persona_override"] or u["global_persona"]


def build_history(history):
    contents = []
    for turn in history:
        role = turn["role"]
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=turn["text"])]))
    return contents


async def summarize_if_needed(chat_id, thread_name):
    """Plan B for memory: once a thread gets long, compress older turns into
    a running summary instead of losing them entirely."""
    u = get_user(chat_id)
    thread = u["threads"][thread_name]
    history = thread["history"]

    if len(history) <= MAX_TURNS * 2:
        return

    old_part = history[: len(history) - MAX_TURNS * 2]
    keep_part = history[len(history) - MAX_TURNS * 2:]

    transcript = ""
    for turn in old_part:
        speaker = "Virat" if turn["role"] == "user" else "Arise"
        transcript += f"{speaker}: {turn['text']}\n"

    try:
        prompt = (
            "Summarize the key facts, context, and preferences from this "
            "conversation in a short paragraph, written so it can be used "
            "as background memory for future replies:\n\n" + transcript
        )
        result = client.models.generate_content(model=DEFAULT_MODEL, contents=[prompt])
        new_summary = result.text
    except Exception:
        new_summary = ""

    thread["summary"] = (thread["summary"] + "\n" + new_summary).strip()
    thread["history"] = keep_part


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_user(chat_id)
    await update.message.reply_text(
        "Hey, I'm Arise. Just talk to me normally — I'll remember our "
        "conversation as we go.\n\n"
        "Commands:\n"
        "/newchat <name> — start a separate conversation thread\n"
        "/chats — see your threads\n"
        "/switch <name> — switch threads\n"
        "/reset — clear memory in current thread\n"
        "/models — see available AI models\n"
        "/model <name> — switch model\n"
        "/persona <text> — change how I behave in THIS chat\n"
        "/persona reset — undo your changes, back to default for this chat\n"
        "(Changing /persona while in the 'default' chat changes the base "
        "personality for every chat that hasn't been customized separately.)\n"
        "/imagine <description> — generate an image"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = get_user(chat_id)
    thread_name = u["active_thread"]
    override = u["threads"][thread_name]["persona_override"]
    u["threads"][thread_name] = {"history": [], "summary": "", "persona_override": override}
    await update.message.reply_text(f"Memory cleared for '{thread_name}'.")


async def newchat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = get_user(chat_id)
    if not context.args:
        await update.message.reply_text("Usage: /newchat study")
        return
    name = " ".join(context.args)
    u["threads"][name] = {"history": [], "summary": "", "persona_override": None}
    u["active_thread"] = name
    await update.message.reply_text(f"Started new chat '{name}'. This is now active.")


async def chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = get_user(chat_id)
    names = list(u["threads"].keys())
    active = u["active_thread"]
    lines = [f"- {n} (active)" if n == active else f"- {n}" for n in names]
    await update.message.reply_text("Your chats:\n" + "\n".join(lines))


async def switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = get_user(chat_id)
    if not context.args:
        await update.message.reply_text("Usage: /switch study")
        return
    name = " ".join(context.args)
    if name not in u["threads"]:
        await update.message.reply_text(
            f"No chat called '{name}' yet. Use /newchat {name} to create it."
        )
        return
    u["active_thread"] = name
    await update.message.reply_text(f"Switched to '{name}'.")


async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        lines = []
        for m in client.models.list():
            lines.append("- " + m.name.replace("models/", ""))
        text = "Models available on your key:\n" + "\n".join(lines[:30])
        text += (
            "\n\nRough guide: 'flash' = fast/everyday, 'flash-lite' = "
            "fastest and highest free quota, 'pro' = deeper reasoning, "
            "'flash-image' = image generation."
        )
    except Exception as e:
        text = f"Couldn't fetch model list: {e}"
    await update.message.reply_text(text)


async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = get_user(chat_id)
    if not context.args:
        await update.message.reply_text(
            f"Current model: {u['model']}\nUsage: /model gemini-3.5-flash-lite"
        )
        return
    u["model"] = context.args[0]
    await update.message.reply_text(f"Model switched to {u['model']}.")


async def set_persona(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = get_user(chat_id)
    thread_name = u["active_thread"]
    thread = u["threads"][thread_name]

    if not context.args:
        current = effective_persona(u, thread)
        await update.message.reply_text(f"Current persona for '{thread_name}':\n{current}")
        return

    if context.args[0].lower() == "reset":
        if thread_name == "default":
            u["global_persona"] = DEFAULT_PERSONA
            await update.message.reply_text("Reset to the default personality (applies everywhere it isn't overridden).")
        else:
            thread["persona_override"] = None
            await update.message.reply_text(f"'{thread_name}' now follows the default personality again.")
        return

    text = " ".join(context.args)
    if thread_name == "default":
        u["global_persona"] = text
        await update.message.reply_text("Updated the base personality — this applies to every chat that doesn't have its own override.")
    else:
        thread["persona_override"] = text
        await update.message.reply_text(f"Updated persona for '{thread_name}' only. Other chats are unaffected.")


async def imagine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /imagine a cat wearing sunglasses")
        return
    prompt = " ".join(context.args)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")

    try:
        response = client.models.generate_content(model=IMAGE_MODEL, contents=[prompt])
        for part in response.candidates[0].content.parts:
            if getattr(part, "inline_data", None) is not None:
                await update.message.reply_photo(photo=part.inline_data.data)
                return
        await update.message.reply_text("Didn't get an image back — try rephrasing.")
    except Exception as e:
        await update.message.reply_text(f"Image generation failed: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    u = get_user(chat_id)
    thread_name = u["active_thread"]
    thread = u["threads"][thread_name]

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    persona = effective_persona(u, thread)
    if thread["summary"]:
        persona += "\n\nBackground memory from earlier in this conversation: " + thread["summary"]

    try:
        chat = client.chats.create(
            model=u["model"],
            config=types.GenerateContentConfig(system_instruction=persona),
            history=build_history(thread["history"]),
        )
        response = chat.send_message(text)
        reply = response.text
    except Exception as e:
        await update.message.reply_text(f"Something went wrong: {e}")
        return

    thread["history"].append({"role": "user", "text": text})
    thread["history"].append({"role": "model", "text": reply})

    await summarize_if_needed(chat_id, thread_name)
    await update.message.reply_text(reply)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = get_user(chat_id)
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    caption = update.message.caption or "Describe and analyze this image."

    try:
        response = client.models.generate_content(
            model=u["model"],
            contents=[
                types.Part.from_bytes(data=bytes(image_bytes), mime_type="image/jpeg"),
                caption,
            ],
        )
        reply = response.text
    except Exception as e:
        reply = f"Couldn't process that image: {e}"

    await update.message.reply_text(reply)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = get_user(chat_id)
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    doc = update.message.document
    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()
    mime_type = doc.mime_type or "application/pdf"
    caption = update.message.caption or "Summarize and analyze this document."

    try:
        response = client.models.generate_content(
            model=u["model"],
            contents=[
                types.Part.from_bytes(data=bytes(file_bytes), mime_type=mime_type),
                caption,
            ],
        )
        reply = response.text
    except Exception as e:
        reply = f"Couldn't process that document: {e}"

    await update.message.reply_text(reply)


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
    application.add_handler(CommandHandler("newchat", newchat))
    application.add_handler(CommandHandler("chats", chats))
    application.add_handler(CommandHandler("switch", switch))
    application.add_handler(CommandHandler("models", list_models))
    application.add_handler(CommandHandler("model", set_model))
    application.add_handler(CommandHandler("persona", set_persona))
    application.add_handler(CommandHandler("imagine", imagine))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Arise starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
