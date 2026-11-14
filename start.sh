#!/usr/bin/env bash
# Usage: bash start.sh (Ollama keeps running after the bot exits).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

for dependency in uv curl; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        echo "Required command not found: $dependency" >&2
        exit 1
    fi
done

ollama_url="${OLLAMA_URL:-http://localhost:11434}"
while [[ "$ollama_url" == */ ]]; do ollama_url="${ollama_url%/}"; done
ollama_url="${ollama_url%/api/chat}"

ollama_ready() {
    curl --fail --silent --output /dev/null --connect-timeout 1 --max-time 2 \
        "$ollama_url/api/version"
}

if ! ollama_ready; then
    # Only start a local server; remote servers must be started on their host.
    case "$ollama_url" in
        http://localhost|http://localhost:*|http://127.0.0.1|http://127.0.0.1:*) ;;
        *)
            echo "Ollama is not responding at $ollama_url. Start it on the configured server." >&2
            exit 1
            ;;
    esac

    if ! command -v ollama >/dev/null 2>&1; then
        echo "The ollama command was not found. Install Ollama before starting the bot." >&2
        exit 1
    fi

    ollama_log="$(mktemp "${TMPDIR:-/tmp}/teleqwen-ollama.XXXXXX")"
    echo "Starting Ollama (log: $ollama_log)..."
    OLLAMA_HOST="$ollama_url" nohup ollama serve >"$ollama_log" 2>&1 < /dev/null &

    ready=false
    for ((attempt = 0; attempt < 30; attempt++)); do
        if ollama_ready; then
            ready=true
            break
        fi
        sleep 1
    done
    if [[ "$ready" != true ]]; then
        echo "Ollama is not ready. Check the log: $ollama_log" >&2
        exit 1
    fi
fi

echo "Ollama is ready. Starting Teleqwen (Ctrl+C to stop the bot)..."
exec uv run --locked teleqwen
