# Teleqwen

A small personal Telegram bot powered by Qwen through Ollama. It connects to one
private chat and saves the last 10 exchanges locally, so it remembers recent
messages after a restart. The agent can use tools for addition, multiplication,
and the current local date and time.

## Requirements

- Python 3.15 and `uv`.
- Ollama, with the `ollama` command available in your terminal.
- Bash and `curl` for the startup script.
- A Telegram bot token created through `@BotFather`.

## First-time setup

Start Ollama by opening its app or running `ollama serve` in a separate terminal.
If it is already running, leave it running. Then download the default model once:

```bash
ollama pull qwen3.5:2b
```

Open a terminal in the project folder and install the Python dependencies:

```bash
uv sync --locked
```

## Start the bot

From the project folder, run:

```bash
bash start.sh
```

No executable permission is needed when using `bash start.sh`. You can also run
it from another folder by passing its path, for example
`bash /path/to/Teleqwen/start.sh`.

The script checks whether Ollama is responding. If a local server is unavailable,
it starts Ollama in the background and waits for it to be ready. It then launches
the bot with `uv run --locked teleqwen`. The script does not download models.

Enter your bot token when prompted; the input is hidden. The token is requested
each time you start the bot. Keep the terminal open while using it.

Send `/start` to your bot on Telegram, then send a message. The first private
chat that contacts it becomes the connected chat; other chats are rejected.

Press **Ctrl+C** in the terminal to stop the bot. Ollama stays running and can be
reused the next time you run `bash start.sh`.

## Commands and conversation history

- `/start`: show usage instructions.
- `/clear`: erase the saved conversation while keeping the same connected chat.

History is stored in `data/history.json` by default. The system prompt is defined
in `src/teleqwen/storage/history.py`. It asks for natural, conversational replies
in English, with plain text preferred. Restart the bot after changing
the prompt; use `/clear` if you also want to start a fresh conversation.

## Configuration

Set environment variables before starting the bot:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL; an `/api/chat` suffix is also accepted. |
| `OLLAMA_MODEL` | `qwen3.5:2b` | Model to use; it must already be downloaded on the server. |
| `TELEQWEN_HISTORY` | `data/history.json` | History file path, relative to the project folder when using `start.sh`. |

For example, to use a remote Ollama server:

```bash
OLLAMA_URL=http://your-server:11434 bash start.sh
```

The script can start local HTTP servers at `localhost` or `127.0.0.1`.
A remote server must already be running.

## Troubleshooting

- If a required command is missing, install it and make sure it is on your `PATH`.
- If Ollama fails to start, check the temporary log file printed by `start.sh`.
- If the model is unavailable, run `ollama pull qwen3.5:2b` on the Ollama server,
  or download the model selected by `OLLAMA_MODEL`.
- If the token prompt fails, run the script in an interactive terminal.
