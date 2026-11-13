import os
import unittest
from pathlib import Path
from unittest.mock import patch

from teleqwen.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_defaults_and_hidden_token(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings(" secret ")
        self.assertEqual(settings.token, "secret")
        self.assertNotIn("secret", repr(settings))
        self.assertEqual(settings.model, "qwen3.5:2b")
        self.assertEqual(settings.ollama_url, "http://localhost:11434/api/chat")
        self.assertEqual(settings.history_file, Path("data/history.json"))

    def test_settings_from_environment(self):
        for url in ["http://server:11434/", "http://server:11434/api/chat"]:
            with patch.dict(os.environ, {
                "OLLAMA_URL": url,
                "OLLAMA_MODEL": "another-model",
                "TELEQWEN_HISTORY": "custom.json",
            }, clear=True):
                settings = load_settings("token")
            self.assertEqual(settings.ollama_url, "http://server:11434/api/chat")
            self.assertEqual(settings.model, "another-model")
            self.assertEqual(settings.history_file, Path("custom.json"))

    def test_empty_token_is_rejected(self):
        with self.assertRaises(ValueError):
            load_settings(" ")
