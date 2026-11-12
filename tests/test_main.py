import getpass
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from teleqwen.main import main, read_token


class StartupTests(unittest.TestCase):
    def test_hidden_prompt(self):
        with patch('teleqwen.main.getpass.getpass', return_value=' entered-secret ') as prompt:
            self.assertEqual(read_token(), 'entered-secret')
            prompt.assert_called_once_with('Telegram bot token (hidden): ')

    def test_empty_or_unavailable_prompt(self):
        for value in ['', EOFError(), getpass.GetPassWarning()]:
            with self.subTest(value=value):
                with patch('teleqwen.main.getpass.getpass') as prompt:
                    if isinstance(value, Exception):
                        prompt.side_effect = value
                    else:
                        prompt.return_value = value
                    with self.assertRaises(ValueError):
                        read_token()

    def test_main_checks_ollama_before_running_bot(self):
        with patch('teleqwen.main.read_token', return_value='secret'), \
             patch('teleqwen.main.load_settings') as load, \
             patch('teleqwen.main.ensure_ollama', return_value=nullcontext()) as ensure, \
             patch('teleqwen.main.TelegramBot') as bot:
            main()
            load.assert_called_once_with('secret')
            ensure.assert_called_once_with(load.return_value.ollama_url, load.return_value.model)
            bot.assert_called_once_with(load.return_value)
            bot.return_value.run.assert_called_once()

    def test_prompt_cancelled_without_starting_services(self):
        with patch('teleqwen.main.read_token', side_effect=KeyboardInterrupt), \
             patch('teleqwen.main.ensure_ollama') as ensure:
            with self.assertRaises(SystemExit):
                main()
            ensure.assert_not_called()


if __name__ == '__main__':
    unittest.main()
