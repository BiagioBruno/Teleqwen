import getpass
import logging
import warnings

from teleqwen.bot.telegram import TelegramBot
from teleqwen.config import load_settings


def read_token() -> str:
    # Stop reading if the terminal cannot hide the token.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass("Telegram bot token (hidden): ")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    logging.info("Starting Teleqwen. Press Ctrl+C to stop.")
    try:
        settings = load_settings(read_token())
        TelegramBot(settings).run()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    except (EOFError, getpass.GetPassWarning):
        raise SystemExit("Run Teleqwen in an interactive terminal to enter the token.") from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
