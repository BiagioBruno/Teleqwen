import teleqwen.config as conf
from teleqwen.telegram_bot import TelegramBot


def main() -> None:
    bot = TelegramBot(conf.TELEGRAM_BOT_TOKEN, conf.OLLAMA_URL)
    bot.run()


if __name__ == "__main__":
    main()
