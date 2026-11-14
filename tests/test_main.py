import getpass
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teleqwen.config import Settings
from teleqwen.main import main, read_token


class MainTests(unittest.TestCase):
    def test_hidden_prompt(self):
        with patch("teleqwen.main.getpass.getpass", return_value="secret") as prompt:
            self.assertEqual(read_token(), "secret")
        prompt.assert_called_once_with("Telegram bot token (hidden): ")

    def test_main_starts_bot(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("teleqwen.main.read_token", return_value="secret"), \
             patch("teleqwen.main.load_settings", return_value=Settings(
                 "secret", history_file=Path(directory) / "history.json"
             )) as settings, \
             patch("teleqwen.main.TelegramBot") as bot:
            main()
        settings.assert_called_once_with("secret")
        bot.assert_called_once()
        configured_settings, configured_agent = bot.call_args.args
        self.assertIs(configured_settings, settings.return_value)
        self.assertIs(configured_agent.settings, configured_settings)
        self.assertIsInstance(configured_agent.tools, list)
        bot.return_value.run.assert_called_once()

    def test_unavailable_or_empty_prompt_does_not_start_bot(self):
        for value in [EOFError(), getpass.GetPassWarning(), " "]:
            with self.subTest(value=value), \
                 patch("teleqwen.main.read_token") as prompt, \
                 patch("teleqwen.main.TelegramBot") as bot:
                if isinstance(value, Exception):
                    prompt.side_effect = value
                else:
                    prompt.return_value = value
                with self.assertRaises(SystemExit):
                    main()
                bot.assert_not_called()

    def test_cancelled_prompt_does_not_start_bot(self):
        with patch("teleqwen.main.read_token", side_effect=KeyboardInterrupt), \
             patch("teleqwen.main.TelegramBot") as bot:
            main()
        bot.assert_not_called()
