import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from teleqwen.agent.agent import agent
from teleqwen.bot.telegram import TelegramBot
from teleqwen.config import Settings
from teleqwen.services.ollama import OllamaError
from teleqwen.storage.history import History


class AgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_notes_survive_clear_and_restart_and_can_be_deleted(self):
        requests = []
        responses = []

        def respond(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"message": responses.pop(0)})

        async def run_turn(assistant, text, name, arguments, answer):
            responses.extend([
                {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": name, "arguments": arguments}},
                ]},
                {"role": "assistant", "content": answer},
            ])
            self.assertEqual(await assistant.handle_prompt(text), answer)

        client_class = httpx.AsyncClient

        def make_client(**kwargs):
            return client_class(transport=httpx.MockTransport(respond), **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            settings = Settings("secret", history_file=Path(directory) / "history.json")
            notes_file = Path(directory) / "notes.json"
            with patch.dict(os.environ, {"TELEQWEN_NOTES": str(notes_file)}), \
                 patch("teleqwen.services.ollama.httpx.AsyncClient", side_effect=make_client):
                assistant = agent(settings)
                assistant.history.connect(123)
                await run_turn(assistant, "Remember the boiler filter was replaced in November.",
                               "save_note", {"text": "Boiler filter replaced in November"}, "Note saved.")
                note = json.loads(notes_file.read_text())[0]
                self.assertIn(note["id"], requests[-1]["messages"][-1]["content"])
                assistant.history.clear()

                assistant = agent(settings)
                self.assertEqual(assistant.history.messages, [])
                await run_turn(assistant, "When was the boiler filter replaced?",
                               "search_notes", {"query": "boiler filter"}, "In November.")
                result = requests[-1]["messages"][-1]
                self.assertEqual(result["tool_name"], "search_notes")
                self.assertIn(note["text"], result["content"])

                await run_turn(assistant, "Delete the boiler filter note.",
                               "delete_note", {"note_id": note["id"]}, "Note deleted.")
                self.assertEqual(json.loads(notes_file.read_text()), [])

    async def test_invalid_tool_arguments_can_be_corrected(self):
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            if len(requests) <= 2:
                arguments = {"timezone": "UTC"} if len(requests) == 1 else {}
                message = {
                    "role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": "current_time", "arguments": arguments}}],
                }
            else:
                message = {"role": "assistant", "content": "2026-11-15T12:00:00"}
            return httpx.Response(200, json={"message": message})

        client_class = httpx.AsyncClient

        def make_client(**kwargs):
            return client_class(transport=httpx.MockTransport(respond), **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            settings = Settings("secret", history_file=Path(directory) / "history.json")
            assistant = agent(settings)
            with patch("teleqwen.services.ollama.httpx.AsyncClient", side_effect=make_client), \
                 patch("teleqwen.agent.tools.current_time.datetime") as clock, \
                 self.assertLogs(level="ERROR"):
                clock.now.return_value = datetime(2026, 11, 15, 12)
                self.assertEqual(await assistant.handle_prompt("What time is it?"), "2026-11-15T12:00:00")
            self.assertEqual(len(requests), 3)
            self.assertIn("Tool execution failed", requests[1]["messages"][-1]["content"])
            self.assertEqual(requests[2]["messages"][-1]["content"], "2026-11-15T12:00:00")
            self.assertEqual(History(settings.history_file).messages, [
                {"role": "user", "content": "What time is it?"},
                {"role": "assistant", "content": "2026-11-15T12:00:00"},
            ])

    async def test_invalid_response_does_not_change_saved_context(self):
        messages = [
            {"role": "assistant", "content": 123},
            {"role": "assistant", "content": " \n"},
            {"role": "assistant", "tool_calls": [{"function": {"name": "current_time"}}]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings("secret", history_file=Path(directory) / "history.json")
            assistant = agent(settings)
            assistant.history.append("saved", "answer")
            before = settings.history_file.read_bytes()
            prompt = assistant.history.prompt("next")
            for message in messages:
                client = httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"message": message}),
                ))
                with self.subTest(message=message):
                    with patch("teleqwen.services.ollama.httpx.AsyncClient", return_value=client):
                        with self.assertRaises(OllamaError):
                            await assistant.handle_prompt("failed")
                    self.assertEqual(settings.history_file.read_bytes(), before)
                    self.assertEqual(assistant.history.prompt("next"), prompt)

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
                        "name": "current_time", "arguments": {},
                    }}],
                }
            else:
                message = {"role": "assistant", "content": "2026-11-15T12:00:00"}
            return httpx.Response(200, json={"message": message})

        client_class = httpx.AsyncClient

        def make_client(**kwargs):
            return client_class(transport=httpx.MockTransport(respond), **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            settings = Settings("secret", history_file=Path(directory) / "history.json")
            assistant = agent(settings)
            with patch("teleqwen.services.ollama.httpx.AsyncClient", side_effect=make_client), \
                 patch("teleqwen.agent.tools.current_time.datetime") as clock:
                clock.now.return_value = datetime(2026, 11, 15, 12)
                self.assertEqual(await assistant.handle_prompt("What time is it?"), "2026-11-15T12:00:00")
            self.assertEqual(len(requests), 2)
            self.assertEqual(requests[1]["messages"][-1], {
                "role": "tool", "tool_name": "current_time", "content": "2026-11-15T12:00:00",
            })
            self.assertEqual(History(settings.history_file).messages, [
                {"role": "user", "content": "What time is it?"},
                {"role": "assistant", "content": "2026-11-15T12:00:00"},
            ])
