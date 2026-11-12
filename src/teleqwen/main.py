import logging
import getpass
import warnings

from teleqwen.config import load_settings
from teleqwen.bot.telegram import TelegramBot
from teleqwen.services.runtime import OllamaStartupError, ensure_ollama


def read_token() -> str:
    try:
        # Never fall back to a prompt that echoes the secret.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("Telegram bot token (hidden): ").strip()
    except (EOFError, getpass.GetPassWarning):
        raise ValueError("Run Teleqwen in an interactive terminal to enter your bot token securely.") from None
    if not token:
        raise ValueError("The Telegram bot token must not be empty")
    return token


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # HTTP request URLs can contain the Telegram bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        settings = load_settings(read_token())
        with ensure_ollama(settings.ollama_url, settings.model):
            TelegramBot(settings).run()
    except (ValueError, OllamaStartupError) as exc:
        raise SystemExit(str(exc)) from None
    except KeyboardInterrupt:
        raise SystemExit("Startup cancelled.") from None


if __name__ == "__main__":
    main()
