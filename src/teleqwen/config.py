import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    token: str = field(repr=False)
    ollama_url: str = "http://localhost:11434/api/chat"
    model: str = "qwen3.5:2b"
    history_file: Path = Path("data/history.json")


def load_settings(token: str) -> Settings:
    if not token.strip():
        raise ValueError("The Telegram bot token must not be empty")
    url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    if not url.endswith("/api/chat"):
        url += "/api/chat"
    return Settings(
        token=token.strip(),
        ollama_url=url,
        model=os.getenv("OLLAMA_MODEL", "qwen3.5:2b"),
        history_file=Path(os.getenv("TELEQWEN_HISTORY", "data/history.json")).expanduser(),
    )
