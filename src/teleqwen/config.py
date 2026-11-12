"""Configuration is loaded at startup"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    ollama_url: str
    model: str
    database: Path
    timeout: float = 120
    context_length: int = 8192


def load_settings(token: str) -> Settings:
    token = token.strip()
    if not token:
        raise ValueError("The Telegram bot token must not be empty")
    url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat").strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("OLLAMA_URL must be an HTTP(S) URL without a query or fragment")
    if not parsed.path:
        url += "/api/chat"
    elif parsed.path != "/api/chat":
        raise ValueError("OLLAMA_URL must point to /api/chat or the Ollama base URL")
    model = os.getenv("OLLAMA_MODEL", "qwen3.5:2b").strip()
    if not model:
        raise ValueError("OLLAMA_MODEL must not be empty")
    try:
        timeout = float(os.getenv("OLLAMA_TIMEOUT", "120"))
        if not 1 <= timeout <= 600:
            raise ValueError
    except ValueError as exc:
        raise ValueError("OLLAMA_TIMEOUT must be between 1 and 600 seconds") from exc
    try:
        context_length = int(os.getenv("OLLAMA_CONTEXT_LENGTH", "8192"))
        if context_length <= 0:
            raise ValueError
    except ValueError as exc:
        raise ValueError("OLLAMA_CONTEXT_LENGTH must be a positive token count") from exc
    return Settings(token, url, model,
                    Path(os.getenv("TELEQWEN_DB", "data/teleqwen.sqlite3")).expanduser(),
                    timeout, context_length)
