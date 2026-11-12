import logging

from telegram import BotCommand, Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from teleqwen.bot.messages import COMMANDS, HELP, WELCOME
from teleqwen.config import Settings
from teleqwen.storage.history import History, MAX_CONVERSATIONS
from teleqwen.services.ollama import OllamaClient, OllamaError

logger = logging.getLogger(__name__)


def chunks(text: str, limit: int = 4000):
    """Bound UTF-16 units too, including emoji outside the BMP."""
    current, size = [], 0
    for char in text:
        units = 2 if ord(char) > 0xFFFF else 1
        if size + units > limit:
            yield "".join(current)
            current, size = [], 0
        current.append(char)
        size += units
    if current:
        yield "".join(current)


class TelegramBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.history = History(settings.database)
        self.ollama = OllamaClient(settings.ollama_url, settings.model, settings.timeout, settings.context_length)
        self.busy_chat: int | None = None
        self.application = (Application.builder().token(settings.token).concurrent_updates(8)
                            .post_init(self.setup_commands).post_shutdown(self.shutdown).build())

        for command, _ in COMMANDS:
            self.application.add_handler(CommandHandler(command, getattr(self, command)))

        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_error_handler(self.on_error)

    async def private_chat(self, update: Update) -> bool:
        if not update.message or not update.effective_user or not update.effective_chat:
            return False
        if update.effective_chat.type != "private":
            await update.message.reply_text("Please use me in a private chat.")
            return False
        return True

    async def available(self, update: Update) -> bool:
        """Allow commands unless this chat has a response in flight."""
        if not await self.private_chat(update):
            return False
        if update.effective_chat.id == self.busy_chat:
            await update.message.reply_text("I am processing a request. Wait for the response and try again.")
            return False
        return True

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self.private_chat(update):
            await update.message.reply_text(WELCOME)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self.private_chat(update):
            await update.message.reply_text(HELP)

    async def setup_commands(self, application: Application):
        try:
            await application.bot.set_my_commands([BotCommand(name, description) for name, description in COMMANDS])
        except TelegramError:
            logger.warning("Unable to update the command menu; commands remain available through /help")

    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self.private_chat(update):
            await update.message.reply_text("Unknown command. Use /help to list all features.")

    async def ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        parts = (update.message.text or "").split(maxsplit=1) if update.message else []
        if len(parts) < 2:
            if await self.private_chat(update):
                await update.message.reply_text("Use /ask followed by your question, for example: /ask How does Ollama work?")
            return
        await self.reply(update, parts[1])

    async def new(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.available(update):
            return
        chat_id = update.effective_chat.id
        at_limit = len(self.history.list(chat_id)) >= MAX_CONVERSATIONS
        conversation_id = self.history.new(chat_id)
        notice = " The oldest conversation was deleted to keep the 10-chat limit." if at_limit else ""
        await update.message.reply_text(f"New conversation #{conversation_id}.{notice}")

    async def chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.available(update):
            return
        rows = self.history.list(update.effective_chat.id)
        text = "\n".join(f"#{row['id']}{' (active)' if row['active'] else ''}: {row['title']}" for row in rows)
        await update.message.reply_text(text or "No saved conversations.")

    async def delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.available(update):
            return
        try:
            if len(context.args) != 1:
                raise ValueError
            conversation_id = int(context.args[0])
            if not 0 < conversation_id < 2**63:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Use /delete ID, for example /delete 3. Find conversation IDs with /chats.")
            return
        deleted = self.history.delete(update.effective_chat.id, conversation_id)
        await update.message.reply_text("Local conversation deleted." if deleted else "Conversation not found.")

    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.available(update):
            return
        if context.args != ["confirm"]:
            await update.message.reply_text("To delete all your local history, use /clear confirm.")
            return
        count = self.history.clear(update.effective_chat.id)
        await update.message.reply_text(f"Deleted {count} local conversations.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.reply(update, update.message.text if update.message else "")

    async def reply(self, update: Update, text: str):
        if not await self.available(update):
            return
        text = (text or "").strip()
        if not text:
            await update.message.reply_text("Send a message or use /help to see the available commands.")
            return
        if self.busy_chat is not None:
            await update.message.reply_text("Ollama is busy. Try again shortly.")
            return

        # No await between checking and setting: one generation, one state variable.
        chat_id = self.busy_chat = update.effective_chat.id
        try:
            conversation_id = self.history.active(chat_id)
            prompt = self.history.prompt(chat_id, conversation_id, text)
            answer = await self.ollama.chat(prompt)
            # Save complete exchanges even if Telegram delivery subsequently fails.
            self.history.append_turn(chat_id, conversation_id, text, answer)
            for part in chunks(answer):
                await update.message.reply_text(part)
        except OllamaError as exc:
            await update.message.reply_text(str(exc))
        finally:
            self.busy_chat = None

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        # Do not log message text, tokens, request URLs or raw exception strings.
        logger.error("Update failed (%s)", type(context.error).__name__)
        if isinstance(update, Update) and update.message:
            try:
                await update.message.reply_text("An error occurred. Your request may already have been saved; try again shortly.")
            except TelegramError:
                logger.warning("Unable to deliver error notification")

    async def shutdown(self, application: Application):
        await self.ollama.close()
        self.history.close()

    def run(self):
        self.application.run_polling(allowed_updates=["message"], bootstrap_retries=3)
