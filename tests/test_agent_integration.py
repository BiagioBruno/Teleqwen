import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from teleqwen.agent.agent import agent
from teleqwen.bot.telegram import TelegramBot
from teleqwen.config import Settings
from teleqwen.storage.history import History


class AgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_clear_and_chat_ownership_share_history(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings("secret", history_file=Path(directory) / "history.json")
            assistant = agent(settings)
            bot = TelegramBot(settings, assistant)

            def update(text, chat_id=1):
                return SimpleNamespace(
                    effective_chat=SimpleNamespace(id=chat_id),
                    message=SimpleNamespace(text=text, reply_text=AsyncMock()),
                )

            with patch("teleqwen.agent.agent.chat", new_callable=AsyncMock,
                       return_value={"role": "assistant", "content": "answer"}) as chat:
                message = update("hello")
                await bot.handle_message(message, None)
                message.message.reply_text.assert_awaited_once_with("answer")
                self.assertEqual(chat.call_args.args[1:], (
                    assistant.tools, settings.ollama_url, settings.model,
                ))
                saved = History(settings.history_file)
                self.assertEqual(saved.chat_id, 1)
                self.assertEqual(len(saved.messages), 2)

                await bot.handle_message(update("/clear"), None)
                await bot.handle_message(update("again"), None)
                self.assertEqual(chat.call_args.args[0][1:], [
                    {"role": "user", "content": "again"},
                    {"role": "assistant", "content": "answer"},
                ])

                restarted = TelegramBot(settings, agent(settings))
                chat.reset_mock()
                await restarted.handle_message(update("hello", chat_id=2), None)
                chat.assert_not_awaited()

    async def test_tool_result_is_sent_back_before_final_reply(self):
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            if len(requests) == 1:
                message = {
                    "role": "assistant", "content": "",
                    "tool_calls": [{"function": {
                        "name": "sum_two_numbers", "arguments": {"a": 2, "b": 3},
                    }}],
                }
            else:
                message = {"role": "assistant", "content": "5"}
            return httpx.Response(200, json={"message": message})

        client_class = httpx.AsyncClient

        def make_client(**kwargs):
            return client_class(transport=httpx.MockTransport(respond), **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            settings = Settings("secret", history_file=Path(directory) / "history.json")
            assistant = agent(settings)
            with patch("teleqwen.services.ollama.httpx.AsyncClient", side_effect=make_client):
                self.assertEqual(await assistant.handle_prompt("2 + 3"), "5")
            self.assertEqual(len(requests), 2)
            self.assertEqual(requests[1]["messages"][-1], {
                "role": "tool", "tool_name": "sum_two_numbers", "content": "5",
            })
            self.assertEqual(History(settings.history_file).messages, [
                {"role": "user", "content": "2 + 3"},
                {"role": "assistant", "content": "5"},
            ])
