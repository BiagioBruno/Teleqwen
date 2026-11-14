import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram import Chat, Message, Update
from telegram.error import NetworkError
from telegram.ext import Application

from teleqwen.bot.telegram import TelegramBot
from teleqwen.config import Settings
from teleqwen.services.ollama import OllamaError
from teleqwen.storage.history import History


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.bot = TelegramBot(Settings("123456:test-token", history_file=Path(temporary.name) / "history.json"))
        self.chat = self.enterContext(patch("teleqwen.bot.telegram.chat", new_callable=AsyncMock, return_value="answer"))

    def update(self, text="hello", chat_id=1):
        return SimpleNamespace(
            message=SimpleNamespace(text=text, reply_text=AsyncMock()),
            effective_chat=SimpleNamespace(id=chat_id),
        )

    async def test_message_uses_saved_context_and_saves_answer(self):
        await self.bot.handle_message(self.update("first"), None)
        update = self.update("second")
        await self.bot.handle_message(update, None)
        prompt = self.chat.call_args.args[0]
        self.assertEqual([item["content"] for item in prompt[1:]], ["first", "answer", "second"])
        update.message.reply_text.assert_awaited_once_with("answer")
        self.assertEqual(len(History(self.bot.settings.history_file).messages), 4)

    async def test_other_chat_cannot_use_or_clear_context_after_restart(self):
        await self.bot.handle_message(self.update(), None)
        self.bot = TelegramBot(self.bot.settings)
        self.chat.reset_mock()
        for text in ["hello", "/clear", "/start", "/create"]:
            update = self.update(text, chat_id=2)
            await self.bot.handle_message(update, None)
            self.assertIn("another private chat", update.message.reply_text.call_args.args[0])
        self.chat.assert_not_awaited()
        self.assertEqual(len(self.bot.history.messages), 2)

    async def test_start_and_clear(self):
        update = self.update("/start")
        await self.bot.handle_message(update, None)
        self.assertIn("/clear", update.message.reply_text.call_args.args[0])
        self.chat.assert_not_awaited()
        await self.bot.handle_message(self.update(), None)
        await self.bot.handle_message(self.update("/clear@Teleqwen"), None)
        self.assertEqual(History(self.bot.settings.history_file).messages, [])
        await self.bot.handle_message(self.update("again"), None)
        self.assertEqual(len(self.chat.call_args.args[0]), 2)

    async def test_failed_generation_does_not_change_context(self):
        await self.bot.handle_message(self.update(), None)
        before = self.bot.history.prompt("next")
        self.chat.side_effect = OllamaError("Ollama is unavailable")
        update = self.update("failed")
        with self.assertRaises(OllamaError):
            await self.bot.handle_message(update, None)
        self.assertEqual(self.bot.history.prompt("next"), before)
        with self.assertLogs(level="ERROR"):
            await self.bot.on_error(update, SimpleNamespace(error=self.chat.side_effect))
        update.message.reply_text.assert_awaited_once_with("Ollama is unavailable")

    async def test_long_unicode_answer_is_delivered_in_safe_parts(self):
        answer = "😀" * 4500 + "hello"
        self.chat.return_value = answer
        update = self.update()
        await self.bot.handle_message(update, None)
        parts = [call.args[0] for call in update.message.reply_text.call_args_list]
        self.assertEqual("".join(parts), answer)
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 4096 for part in parts))

    async def test_create_sends_completed_script_in_safe_parts(self):
        answer = "# " + "😀" * 4500 + "\n# Pippozzo"
        self.chat.return_value = answer
        update = self.update("/create")
        await self.bot.handle_message(update, None)
        self.chat.assert_awaited_once()
        parts = [call.args[0] for call in update.message.reply_text.call_args_list]
        self.assertEqual("".join(parts), answer)
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 4096 for part in parts))
        prompt = self.chat.call_args.args[0]
        self.assertEqual(self.bot.history.messages[0], prompt[-1])

    async def test_create_retries_with_the_actual_prompt_and_previous_answer(self):
        self.bot.history.append("old question", "old answer")
        self.chat.side_effect = ["unfinished script", "completed script\n# Pippozzo"]
        update = self.update("/create@Teleqwen")
        await self.bot.handle_message(update, None)
        self.assertEqual(self.chat.await_count, 2)
        first_prompt = self.chat.call_args_list[0].args[0]
        second_prompt = self.chat.call_args_list[1].args[0]
        self.assertEqual(len(first_prompt), 2)
        self.assertEqual(second_prompt[1], first_prompt[-1])
        self.assertEqual(second_prompt[2], {"role": "assistant", "content": "unfinished script"})
        update.message.reply_text.assert_awaited_once_with("completed script\n# Pippozzo")

    async def test_create_stops_after_ten_unsuccessful_attempts(self):
        self.chat.return_value = "unfinished script"
        update = self.update("/create")
        await self.bot.handle_message(update, None)
        self.assertEqual(self.chat.await_count, 10)
        update.message.reply_text.assert_awaited_once_with("Stopped after 10 attempts without a completed script.")

    async def test_delivery_failure_keeps_the_completed_exchange(self):
        update = self.update()
        update.message.reply_text.side_effect = NetworkError("offline")
        with self.assertRaises(NetworkError):
            await self.bot.handle_message(update, None)
        self.assertEqual(len(History(self.bot.settings.history_file).messages), 2)
        with self.assertLogs(level="ERROR"):
            await self.bot.on_error(update, SimpleNamespace(error=NetworkError("offline")))

    async def test_only_private_text_messages_are_processed_sequentially(self):
        with patch.object(Application, "run_polling", autospec=True) as polling:
            self.bot.run()
        application = polling.call_args.args[0]
        self.assertEqual(application.update_processor.max_concurrent_updates, 1)
        handler = application.handlers[0][0]
        for kind, expected in [("private", True), ("group", False), ("supergroup", False), ("channel", False)]:
            message = Message(1, datetime.now(timezone.utc), Chat(1, kind), text="hello")
            self.assertEqual(bool(handler.check_update(Update(1, message=message))), expected)
            self.assertFalse(handler.check_update(Update(1, edited_message=message)))
        photo = Message(2, datetime.now(timezone.utc), Chat(1, "private"))
        self.assertFalse(handler.check_update(Update(2, message=photo)))

    async def test_menu_replaces_old_conversation_commands(self):
        application = SimpleNamespace(bot=SimpleNamespace(set_my_commands=AsyncMock()))
        await self.bot.setup_commands(application)
        commands = application.bot.set_my_commands.call_args.args[0]
        self.assertEqual([command.command for command in commands], ["start", "clear", "create"])
