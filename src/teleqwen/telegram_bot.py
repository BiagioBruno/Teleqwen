from teleqwen.ollama import handle_ollama_comunication
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

class TelegramBot:
    def __init__(self, token: str, ollama_url: str):
        self.application = Application.builder().token(token).build()

        # Register command handlers
        self.application.add_handler(CommandHandler("start", self.start))

        # Register text message handler
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_message
            )
        )

        self.url = ollama_url

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("Hello! I'm Teleqwen.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        message = update.message.text
        print(f"Received: {message}")
        ollama_msg = handle_ollama_comunication(self.url, message)
        await update.message.reply_text(f"{ollama_msg}")

    def run(self) -> None:
        print("Starting Telegram bot...")
        self.application.run_polling()