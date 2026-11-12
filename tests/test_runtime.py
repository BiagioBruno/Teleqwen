import subprocess
import unittest
from unittest.mock import MagicMock, patch

import httpx
from teleqwen.services.runtime import OllamaStartupError, _models, ensure_ollama

URL = 'http://localhost:11434/api/chat'
MODEL = 'qwen3.5:2b'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.probe = self.enterContext(patch('teleqwen.services.runtime._models'))
        self.popen = self.enterContext(patch('teleqwen.services.runtime.subprocess.Popen'))
        self.which = self.enterContext(patch('teleqwen.services.runtime.shutil.which', return_value='/usr/local/bin/ollama'))
        self.enterContext(patch('teleqwen.services.runtime.time.sleep'))
        self.process = self.popen.return_value
        self.process.poll.return_value = None

    def test_existing_service_is_reused_and_never_stopped(self):
        self.probe.return_value = [MODEL]
        with ensure_ollama(URL, MODEL):
            pass
        self.popen.assert_not_called()
        self.which.assert_not_called()

    def test_starts_waits_and_stops_owned_service(self):
        self.probe.side_effect = [None, None, [MODEL]]
        with patch.dict('os.environ', {'OLLAMA_HOST': '0.0.0.0:9999', 'TELEGRAM_BOT_TOKEN': 'secret'}):
            with ensure_ollama(URL, MODEL):
                self.process.terminate.assert_not_called()
        self.assertEqual(self.popen.call_args.args[0], ['/usr/local/bin/ollama', 'serve'])
        env = self.popen.call_args.kwargs['env']
        self.assertEqual(env['OLLAMA_HOST'], 'localhost:11434')
        self.assertNotIn('TELEGRAM_BOT_TOKEN', env)
        self.process.terminate.assert_called_once()
        self.process.wait.assert_called_once_with(timeout=5)

    def test_missing_binary(self):
        self.probe.return_value = None
        self.which.return_value = None
        with self.assertRaisesRegex(OllamaStartupError, 'Install'):
            with ensure_ollama(URL, MODEL):
                self.fail('Must not start the bot')
        self.popen.assert_not_called()

    def test_remote_unavailable_does_not_start_local_service(self):
        self.probe.return_value = None
        with self.assertRaisesRegex(OllamaStartupError, 'local HTTP'):
            with ensure_ollama('https://example.com/api/chat', MODEL):
                pass
        self.popen.assert_not_called()

    def test_timeout_cleans_up_process(self):
        self.probe.return_value = None
        with self.assertRaisesRegex(OllamaStartupError, 'in time'):
            with ensure_ollama(URL, MODEL, startup_timeout=0):
                pass
        self.process.terminate.assert_called_once()

    def test_early_exit(self):
        self.probe.return_value = None
        self.process.poll.return_value = 1
        with self.assertRaisesRegex(OllamaStartupError, 'exited'):
            with ensure_ollama(URL, MODEL):
                pass
        self.process.terminate.assert_not_called()

    def test_missing_model_cleans_up_owned_service(self):
        self.probe.side_effect = [None, []]
        with self.assertRaisesRegex(OllamaStartupError, 'ollama pull qwen3.5:2b'):
            with ensure_ollama(URL, MODEL):
                pass
        self.process.terminate.assert_called_once()

    def test_bot_failure_stops_owned_service(self):
        self.probe.side_effect = [None, [MODEL]]
        self.process.wait.side_effect = [subprocess.TimeoutExpired('ollama', 5), 0]
        with self.assertRaisesRegex(RuntimeError, 'bot failed'):
            with ensure_ollama(URL, MODEL):
                raise RuntimeError('bot failed')
        self.process.kill.assert_called_once()

    def test_spawn_error_is_actionable(self):
        self.probe.return_value = None
        self.popen.side_effect = OSError('private details')
        with self.assertRaisesRegex(OllamaStartupError, 'manually'):
            with ensure_ollama(URL, MODEL):
                pass

    def test_latest_tag_alias(self):
        self.probe.return_value = ['example:latest']
        with ensure_ollama(URL, 'example'):
            pass


class ProbeTests(unittest.TestCase):
    def test_valid_empty_and_populated_model_lists(self):
        for models in [[], [{'name': MODEL}]]:
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'models': models}))) as client:
                self.assertEqual(_models(client, URL), [item['name'] for item in models])

    def test_invalid_service_does_not_count_as_not_running(self):
        for response in [httpx.Response(403), httpx.Response(200, text='invalid'),
                         httpx.Response(200, json={'models': 'wrong'}), httpx.Response(200, json={'models':[{}]})]:
            with self.subTest(response=response):
                with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
                    with self.assertRaises(OllamaStartupError):
                        _models(client, URL)

    def test_connection_failure_means_not_ready(self):
        client = MagicMock()
        client.get.side_effect = httpx.ConnectError('offline')
        self.assertIsNone(_models(client, URL))


if __name__ == '__main__':
    unittest.main()
