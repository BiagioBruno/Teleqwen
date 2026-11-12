# Teleqwen

Teleqwen is my personal project: a small personal assistant that I can talk to
through Telegram, while the AI model runs directly on my own computer.

The idea is to use a very small model, **Qwen 3.5 2B**, through Ollama, with a
machine such as a **MacBook Air M1 with 8 GB of RAM** in mind. This is a project
I'm building and experimenting with, not a finished product or a performance
promise for every machine.

The model runs locally. Telegram carries the messages, so you still need an
internet connection and your computer needs to stay awake.

## What you need

- **Ollama**, installed from [ollama.com](https://ollama.com/download).
  Make sure the `ollama` command works in your terminal.
- **Python 3.15** and **uv** to run the project.
- A **Telegram account and bot**. Create a bot by talking to `@BotFather`
  on Telegram, then keep the bot token it gives you.

Download the model once before using Teleqwen. Open Ollama, then run:

```bash
ollama pull qwen3.5:2b
```

If you use Ollama from the terminal instead of the Mac app, run `ollama serve`
in a separate terminal first. These are standard [Ollama commands](https://docs.ollama.com/cli).

## First run

Open a terminal in the project folder and install the dependencies:

```bash
uv sync --locked
```

Then start the assistant:

```bash
uv run teleqwen
```

It will ask for your **Telegram bot token**. Paste it and press Enter. Nothing
will appear while you type or paste: that is intentional. The token is requested
each time you start the program and is not saved to disk.

Teleqwen checks whether Ollama is responding. If it is already running, it uses
that service. Otherwise, it tries to start `ollama serve` and waits for it to be
ready. If Ollama is not installed or the model has not been downloaded, it tells
you what is missing.

Open your bot on Telegram and send `/start`. You can start chatting straight away:
there are no user IDs to configure and no registration step. Use `/help` to see
all commands.

The token connects the program to your bot; it does not identify who is messaging
it. Anyone who finds the bot can use it in a private chat. Each chat has its own
separate history. Group chats are not supported.

## Everyday use

Start it with `uv run teleqwen`, enter the token, and talk to your bot in a private
Telegram chat. You can send ordinary messages or use `/ask` followed by a question.

- `/new` starts a fresh conversation.
- `/chats` lists your saved conversations.
- `/delete ID` deletes one conversation, such as `/delete 3`.
- `/clear confirm` deletes all your saved conversations.
- `/help` lists all commands.

Teleqwen saves conversation history locally, so it survives a restart. It keeps up to **10 conversations per user**;
creating another one deletes the oldest. Deleting local history does not remove
the messages you can still see in Telegram.

Use Ctrl+C to stop the program. If Teleqwen started Ollama, it stops that process
too. If Ollama was already running, it leaves it running.

## Conversation memory

The limit of 10 applies to **separate saved chats**, not to messages in a chat.
Teleqwen sends the full active conversation to Ollama, without cutting it down
to 10 exchanges or a fixed number of characters. Ollama fits it into the model's
context window; older messages can still fall out of context when that window fills.

By default, Teleqwen uses **8,192 tokens** of context: a modest starting point
for a personal assistant on a computer with limited RAM. This is separate from
the limit of 10 saved conversations. It has not been benchmarked on the target Mac.

You can adjust the `OLLAMA_CONTEXT_LENGTH` environment variable if needed.
[Larger contexts need more memory](https://docs.ollama.com/context-length).
There is no separate output-token cap, but the request timeout still applies
(`OLLAMA_TIMEOUT`, 120 seconds by default).

## A few details

No configuration file is needed. Optional settings can be passed in the terminal,
for example `OLLAMA_CONTEXT_LENGTH=4096 uv run teleqwen`.

The default model is `qwen3.5:2b`. Set `OLLAMA_MODEL` to use another installed model.
Other optional environment variables are `OLLAMA_URL` (default:
`http://localhost:11434/api/chat`), `OLLAMA_TIMEOUT` (120 seconds), and
`TELEQWEN_DB` (`data/teleqwen.sqlite3`). Automatic startup is only available for
a local Ollama HTTP address.

The code lives in `src/teleqwen`: `bot/` handles Telegram, `services/` talks to
Ollama and manages its startup, and `storage/` saves conversations in SQLite.
The database is created automatically at `data/teleqwen.sqlite3`; you do not need
to install a separate database application.

To run the tests:

```bash
uv run python -m unittest discover -s tests -v
```

Tests use temporary databases and simulated Telegram/Ollama responses. They do
not send real Telegram messages or measure performance on your computer.
