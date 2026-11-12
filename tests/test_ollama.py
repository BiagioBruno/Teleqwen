import asyncio
import json
import unittest

import httpx
from teleqwen.services.ollama import OllamaClient, OllamaError


class OllamaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ollama = OllamaClient('http://localhost:11434/api/chat', 'test')
        await self.ollama.close()

    async def asyncTearDown(self):
        await self.ollama.close()

    def transport(self, handler):
        self.ollama.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def test_success_payload(self):
        def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(payload['messages'][0]['content'], 'hello')
            self.assertFalse(payload['stream'])
            self.assertFalse(payload['think'])
            self.assertEqual(payload['options'], {'num_ctx': 8192, 'num_predict': -1})
            return httpx.Response(200, json={'message': {'content': ' answer '}})
        self.transport(handler)
        self.assertEqual(await self.ollama.chat([{'role':'user','content':'hello'}]), 'answer')

    async def test_configurable_context(self):
        self.ollama.context_length = 32768
        def handler(request):
            self.assertEqual(json.loads(request.content)['options']['num_ctx'], 32768)
            return httpx.Response(200, json={'message': {'content': 'answer'}})
        self.transport(handler)
        await self.ollama.chat([])

    async def test_bad_responses(self):
        responses = [httpx.Response(500, text='private diagnostic'), httpx.Response(404),
                     httpx.Response(200, text='bad json'), httpx.Response(200, json=[]),
                     httpx.Response(200, json={'message': None}),
                     httpx.Response(200, json={'message': {'content': ''}}),
                     httpx.Response(200, json={'message': {'content': 123}})]
        for response in responses:
            with self.subTest(response=response):
                self.transport(lambda request: response)
                with self.assertRaises(OllamaError) as error:
                    await self.ollama.chat([])
                self.assertNotIn('private diagnostic', str(error.exception))
                await self.ollama.close()

    async def test_network_failures(self):
        for error in [httpx.ConnectError('unreachable'), httpx.ReadTimeout('slow')]:
            def handler(request):
                raise error
            self.transport(handler)
            with self.assertRaises(OllamaError):
                await self.ollama.chat([])
            await self.ollama.close()

    async def test_total_deadline(self):
        async def handler(request):
            await asyncio.sleep(1)
            return httpx.Response(200)
        self.transport(handler)
        self.ollama.timeout = .01
        with self.assertRaises(OllamaError):
            await self.ollama.chat([])


if __name__ == "__main__":
    unittest.main()
