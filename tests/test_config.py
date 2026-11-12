import os
import unittest
from unittest.mock import patch

from teleqwen.config import load_settings
from teleqwen.bot.telegram import chunks


class ConfigTests(unittest.TestCase):
    def test_defaults_and_base_url(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'token', 'OLLAMA_URL':'http://localhost:11434'}, clear=True):
            settings = load_settings('entered-token')
            self.assertTrue(settings.ollama_url.endswith('/api/chat'))
            self.assertEqual(settings.context_length, 8192)

    def test_invalid_settings(self):
        for extra in [{'OLLAMA_CONTEXT_LENGTH': '0'}, {'OLLAMA_CONTEXT_LENGTH': 'wrong'}, {'OLLAMA_TIMEOUT':'nan'}, {'OLLAMA_URL':'http://localhost/api/generate'}]:
            env = {'TELEGRAM_BOT_TOKEN':'token', **extra} if extra else {}
            with patch.dict(os.environ, env, clear=True), self.assertRaises(ValueError):
                load_settings('entered-token')

    def test_token_comes_only_from_input(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'old-env-secret'}, clear=True):
            settings = load_settings(' entered-secret ')
            self.assertEqual(settings.token, 'entered-secret')
            self.assertNotIn('entered-secret', repr(settings))
            with self.assertRaises(ValueError):
                load_settings(' ')

    def test_custom_context(self):
        with patch.dict(os.environ, {'OLLAMA_CONTEXT_LENGTH': '32768'}, clear=True):
            self.assertEqual(load_settings('token').context_length, 32768)

    def test_legacy_allowlist_is_ignored(self):
        with patch.dict(os.environ, {'TELEGRAM_ALLOWED_USER_IDS': 'unused'}, clear=True):
            self.assertEqual(load_settings('entered-token').token, 'entered-token')

    def test_unicode_chunks(self):
        text = '😀' * 4500 + 'a' * 5000
        parts = list(chunks(text))
        self.assertEqual(''.join(parts), text)
        self.assertTrue(all(len(p.encode('utf-16-le')) // 2 <= 4000 for p in parts))


if __name__ == "__main__":
    unittest.main()
