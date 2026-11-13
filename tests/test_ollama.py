import json
import unittest
from unittest.mock import patch

import httpx

from teleqwen.services.ollama import OllamaError, chat


class OllamaTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, handler):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("teleqwen.services.ollama.httpx.AsyncClient", return_value=client):
            return await chat([{"role": "user", "content": "hello"}], "http://localhost:11434/api/chat", "test")

    async def test_request_and_answer(self):
        def handler(request):
            self.assertEqual(request.url.path, "/api/chat")
            self.assertEqual(json.loads(request.content), {
                "model": "test",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
                "think": False,
                "options": {"num_ctx": 4096, "num_predict": 512},
            })
            return httpx.Response(200, json={"message": {"content": " answer "}})
        self.assertEqual(await self.request(handler), "answer")

    async def test_unavailable_server_or_model(self):
        for status in [404, 500]:
            with self.subTest(status=status), self.assertRaisesRegex(OllamaError, "running"):
                await self.request(lambda request: httpx.Response(status, text="private details"))
        for error in [httpx.ConnectError("private details"), httpx.ReadTimeout("private details")]:
            def handler(request):
                raise error
            with self.subTest(error=error), self.assertRaisesRegex(OllamaError, "running"):
                await self.request(handler)

    async def test_invalid_responses(self):
        for body in ["invalid", "[]", '{"message": null}', '{"message": {"content": ""}}', '{"message": {"content": 123}}']:
            with self.subTest(body=body), self.assertRaisesRegex(OllamaError, "invalid response"):
                await self.request(lambda request: httpx.Response(200, text=body))
