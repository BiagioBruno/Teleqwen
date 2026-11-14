import logging

from telegram import BotCommand, Update
from telegram.error import TelegramError
from telegram.ext import Application, MessageHandler, filters

from teleqwen.config import Settings
from teleqwen.services.ollama import OllamaError
from teleqwen.storage.history import MAX_TURNS


class TelegramBot:
    def __init__(self, settings: Settings, agent):
        self.settings = settings
        self.history = agent.history
        self.agent = agent

    async def setup_commands(self, application):
        logging.info("Setting up Telegram commands")
        await application.bot.set_my_commands([
            BotCommand("start", "Show instructions"),
            BotCommand("clear", "Clear the context"),
        ])
        logging.info("Connected to Telegram. Starting polling...")

    async def handle_message(self, update: Update, context):
        logging.info("Message received")
        if not self.history.connect(update.effective_chat.id):
            logging.warning("Message rejected: another chat is already connected")
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
            logging.info("Instructions sent")
            return

        # Send a message to the agent
        answer = await self.agent.handle_prompt(text)

        # Short chunks stay within Telegram's message limit, even with emoji.
        logging.info("Sending reply to Telegram")
        for start in range(0, len(answer), 2000):
            await update.message.reply_text(answer[start:start + 2000])
        logging.info("Reply sent")

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
        logging.info("Starting Telegram bot")
        application = Application.builder().token(self.settings.token).post_init(self.setup_commands).build()
        application.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE,
            self.handle_message,
        ))
        application.add_error_handler(self.on_error)
        application.run_polling(allowed_updates=["message"])
