import json
from pathlib import Path

MAX_TURNS = 10
SYSTEM_PROMPT = "You are a personal assistant. Reply clearly and concisely."


class History:
    def __init__(self, path: Path):
        self.path = path
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.chat_id = data.get("chat_id")
        self.messages = data.get("messages", [])[-2 * MAX_TURNS:]

    def connect(self, chat_id: int) -> bool:
        if self.chat_id is None:
            self.chat_id = chat_id
            self.save()
        return self.chat_id == chat_id

    def prompt(self, text: str) -> list[dict[str, str]]:
        # Ollama's chat API expects messages in order, each with a role and content.
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self.messages,
            {"role": "user", "content": text},
        ]

    def append(self, text: str, answer: str):
        # Keep only the last 10 complete question-and-answer exchanges.
        self.messages.extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": answer},
        ])
        self.messages = self.messages[-2 * MAX_TURNS:]
        self.save()

    def clear(self):
        self.messages.clear()
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"chat_id": self.chat_id, "messages": self.messages}
        # Replace the file only after writing the new content in full.
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
