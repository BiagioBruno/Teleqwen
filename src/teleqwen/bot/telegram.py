import logging

from telegram import BotCommand, Update
from telegram.error import TelegramError
from telegram.ext import Application, MessageHandler, filters

from teleqwen.config import Settings
from teleqwen.services.ollama import OllamaError, chat
from teleqwen.storage.history import History, MAX_TURNS


class TelegramBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.history = History(settings.history_file)

    async def setup_commands(self, application):
        await application.bot.set_my_commands([
            BotCommand("start", "Show instructions"),
            BotCommand("clear", "Clear the context"),
        ])
        logging.info("Connected to Telegram. Starting polling...")

    async def handle_message(self, update: Update, context):
        if not self.history.connect(update.effective_chat.id):
            await update.message.reply_text("This bot is already connected to another private chat.")
            return

        text = update.message.text.strip()
        command = text.split(maxsplit=1)[0].split("@")[0] if text else ""
        if command == "/clear":
            self.history.clear()
            await update.message.reply_text("Context cleared. Send a message to start again.")
            return
        if not text or text.startswith("/"):
            await update.message.reply_text(f"Send me a message. I remember the last {MAX_TURNS} exchanges. Use /clear to reset the context.")
            return

        # Send message to Ollama server
        answer = await chat(self.history.prompt(text), self.settings.ollama_url, self.settings.model)
        self.history.append(text, answer)
        # Short chunks stay within Telegram's message limit, even with emoji.
        for start in range(0, len(answer), 2000):
            await update.message.reply_text(answer[start:start + 2000])

    async def on_error(self, update, context):
        logging.error("Request failed (%s)", type(context.error).__name__)
        message = str(context.error) if isinstance(context.error, OllamaError) else "Could not complete the request. Try again."
        if update and update.message:
            try:
                await update.message.reply_text(message)
            except TelegramError:
                logging.warning("Could not send the error message")

    def run(self):
        # Process one message at a time, so no locks or busy flags are needed.
        application = Application.builder().token(self.settings.token).post_init(self.setup_commands).build()
        application.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE,
            self.handle_message,
        ))
        application.add_error_handler(self.on_error)
        application.run_polling(allowed_updates=["message"])
