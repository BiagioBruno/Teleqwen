# Teleqwen

A small personal Telegram bot powered by Qwen through Ollama. It uses one private
chat and saves a short conversation history locally, so it remembers recent
messages after a restart.

## Getting started

You need Python 3.15, uv, Ollama, and a bot token from Telegram's `@BotFather`.

Open Ollama and download the model once:

```bash
ollama pull qwen3.5:2b
```

From the project folder, install and run:

```bash
uv sync --locked
uv run teleqwen
```

Enter your bot token when prompted, then send `/start` to your bot on Telegram.
The bot connects to the first private chat that messages it.

Use `/clear` to reset its memory and **Ctrl+C** in the terminal to stop it.
