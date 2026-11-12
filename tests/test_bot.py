import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.error import NetworkError
from teleqwen.config import Settings
from teleqwen.bot.messages import COMMANDS
from teleqwen.bot.telegram import TelegramBot
from teleqwen.services.ollama import OllamaError


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bot = TelegramBot(Settings('123456:test-token', 'http://localhost:11434/api/chat', 'test', Path(self.temp.name)/'db'))
        self.bot.ollama.chat = AsyncMock(return_value='answer')
        self.context = SimpleNamespace(args=[])

    async def asyncTearDown(self):
        await self.bot.shutdown(self.bot.application)
        self.temp.cleanup()

    def update(self, user=1, text='hello', kind='private'):
        return SimpleNamespace(message=SimpleNamespace(text=text, reply_text=AsyncMock()),
                               effective_chat=SimpleNamespace(id=user, type=kind), effective_user=SimpleNamespace(id=user))

    async def test_groups_are_rejected(self):
        for update in [self.update(kind='group'), self.update(kind='supergroup')]:
            await self.bot.handle_message(update, self.context)
        self.bot.ollama.chat.assert_not_awaited()
        self.assertEqual(self.bot.history.list(3), [])

    async def test_full_active_history_reaches_model(self):
        archived = self.bot.history.new(1)
        self.bot.history.append_turn(1, archived, 'Archived question', 'Archived answer')
        active = self.bot.history.new(1)
        for n in range(15):
            self.bot.history.append_turn(1, active, f'Question {n}', 'a' * 1000)
        await self.bot.handle_message(self.update(text='Follow-up'), self.context)
        prompt = self.bot.ollama.chat.call_args.args[0]
        self.assertEqual(len(prompt), 32)
        self.assertEqual(prompt[1]['content'], 'Question 0')
        self.assertEqual(prompt[-1]['content'], 'Follow-up')
        self.assertNotIn('Archived question', [m['content'] for m in prompt])
        self.assertEqual(self.bot.ollama.context_length, self.bot.settings.context_length)

    async def test_success_and_failure_history(self):
        update = self.update()
        await self.bot.handle_message(update, self.context)
        self.bot.ollama.chat.side_effect = OllamaError('offline')
        await self.bot.handle_message(update, self.context)
        conversation = self.bot.history.active(1)
        self.assertEqual(len(self.bot.history.prompt(1, conversation, 'next')), 4)
        self.assertIsNone(self.bot.busy_chat)

    async def test_delete_commands(self):
        update = self.update()
        await self.bot.handle_message(update, self.context)
        conversation = self.bot.history.active(1)
        self.context.args = [str(conversation)]
        await self.bot.delete(self.update(2), self.context)
        self.assertEqual(len(self.bot.history.list(1)), 1)
        await self.bot.delete(update, self.context)
        self.assertEqual(self.bot.history.list(1), [])
        await self.bot.handle_message(update, self.context)
        self.context.args = []
        await self.bot.clear(update, self.context)
        self.assertEqual(len(self.bot.history.list(1)), 1)
        self.context.args = ['confirm']
        await self.bot.clear(update, self.context)
        self.assertEqual(self.bot.history.list(1), [])

    async def test_concurrent_delete_does_not_resurrect_history(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        async def slow(prompt):
            entered.set()
            await finish.wait()
            return 'done'
        self.bot.ollama.chat.side_effect = slow
        update = self.update()
        task = asyncio.create_task(self.bot.handle_message(update, self.context))
        await entered.wait()
        self.context.args = ['confirm']
        await self.bot.clear(update, self.context)
        self.assertIn('Wait', update.message.reply_text.call_args.args[0])
        await self.bot.handle_message(self.update(2), self.context)
        self.bot.ollama.chat.assert_awaited_once()
        finish.set()
        await task
        await self.bot.clear(update, self.context)
        self.assertEqual(self.bot.history.list(1), [])

    async def test_delivery_error_releases_busy(self):
        update = self.update()
        update.message.reply_text.side_effect = RuntimeError('delivery failed')
        with self.assertRaises(RuntimeError):
            await self.bot.handle_message(update, self.context)
        self.assertIsNone(self.bot.busy_chat)

    async def test_cancellation_releases_capacity_without_partial_turn(self):
        entered = asyncio.Event()
        async def slow(prompt):
            entered.set()
            await asyncio.Event().wait()
        self.bot.ollama.chat.side_effect = slow
        task = asyncio.create_task(self.bot.handle_message(self.update(), self.context))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(self.bot.busy_chat)
        conversation = self.bot.history.active(1)
        self.assertEqual(len(self.bot.history.prompt(1, conversation, 'next')), 2)

    async def test_long_answer_delivered_in_parts(self):
        answer = '😀' * 4500
        self.bot.ollama.chat.return_value = answer
        update = self.update()
        await self.bot.handle_message(update, self.context)
        parts = [call.args[0] for call in update.message.reply_text.call_args_list]
        self.assertEqual(''.join(parts), answer)
        self.assertEqual(len(parts), 3)

    async def test_private_chat_needs_no_user_setup(self):
        update = self.update(999)
        await self.bot.start(update, self.context)
        self.assertIn('/help', update.message.reply_text.call_args.args[0])
        await self.bot.handle_message(update, self.context)
        self.bot.ollama.chat.assert_awaited_once()
        self.assertEqual(len(self.bot.history.list(999)), 1)

    async def test_group_history_commands_are_rejected(self):
        conversation = self.bot.history.new(3)
        update = self.update(3, kind='group')
        self.context.args = [str(conversation)]
        await self.bot.delete(update, self.context)
        self.context.args = ['confirm']
        await self.bot.clear(update, self.context)
        await self.bot.chats(update, self.context)
        await self.bot.new(update, self.context)
        self.assertEqual(len(self.bot.history.list(3)), 1)
        self.assertTrue(all('private chat' in call.args[0] for call in update.message.reply_text.call_args_list))

    async def test_start_and_complete_help(self):
        update = self.update()
        await self.bot.start(update, self.context)
        welcome = update.message.reply_text.call_args.args[0]
        self.assertIn('/help', welcome)
        self.assertNotIn('/delete', welcome)
        await self.bot.help(update, self.context)
        help_text = update.message.reply_text.call_args.args[0]
        for command, _ in COMMANDS:
            self.assertIn('/' + command, help_text)
        self.bot.ollama.chat.assert_not_awaited()

    async def test_command_menu_registration(self):
        application = SimpleNamespace(bot=SimpleNamespace(set_my_commands=AsyncMock()))
        await self.bot.setup_commands(application)
        commands = application.bot.set_my_commands.call_args.args[0]
        self.assertEqual([command.command for command in commands], [name for name, _ in COMMANDS])
        application.bot.set_my_commands.side_effect = NetworkError('offline')
        with self.assertLogs('teleqwen.bot.telegram', level='WARNING'):
            await self.bot.setup_commands(application)

    async def test_ask_preserves_prompt_and_rejects_empty_command(self):
        await self.bot.ask(self.update(text='/ask'), self.context)
        self.bot.ollama.chat.assert_not_awaited()
        self.assertEqual(self.bot.history.list(1), [])
        await self.bot.ask(self.update(text='/ask@Teleqwen How are you?\nSecond line'), self.context)
        prompt = self.bot.ollama.chat.call_args.args[0]
        self.assertEqual(prompt[-1]['content'], 'How are you?\nSecond line')

    async def test_new_notifies_retention(self):
        for _ in range(10):
            self.bot.history.new(1)
        update = self.update()
        await self.bot.new(update, self.context)
        self.assertIn('oldest', update.message.reply_text.call_args.args[0])
        self.assertEqual(len(self.bot.history.list(1)), 10)

    async def test_unknown_command_points_to_help(self):
        update = self.update(text='/unknown')
        await self.bot.unknown_command(update, self.context)
        self.assertIn('/help', update.message.reply_text.call_args.args[0])
        self.bot.ollama.chat.assert_not_awaited()

    async def test_invalid_delete_id(self):
        for arg in ['bad', '-1', str(2**100)]:
            self.context.args = [arg]
            update = self.update()
            await self.bot.delete(update, self.context)
            self.assertIn('Use /delete', update.message.reply_text.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
