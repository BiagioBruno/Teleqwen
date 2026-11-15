import json
import logging
from pathlib import Path

MAX_TURNS = 10
SYSTEM_PROMPT = (
    "You are a personal assistant. Respond naturally and conversationally, "
    "as in a conversation between people. Always respond in the language of "
    "the request and adapt your tone and level of detail to their request. "
    "Get to the point for simple questions and explain clearly when needed. "
    "Avoid canned phrases, excessive formality, and unnecessary explanations. "
    "Prefer plain text that is easy to read in chat, without special "
    "formatting unless requested or necessary. "
    "Use the available tools whenever they can perform the requested operation "
    "or provide the information needed, even when the task seems simple. "
    "For the current date or time, use the time tool. "
    "Save persistent notes only when the user asks you to remember information. "
    "Search notes when the user asks about previously saved information. "
    "Use short keywords for searches, or an empty query to list all notes. "
    "Delete notes only when the user asks, using the IDs returned by search_notes. "
    "If it is unclear which note to delete, ask the user to clarify. "
    "Wait for tool results before answering and base your reply on those results. "
    "Answer directly when no tool is relevant. "
    "If you don't know something, say so clearly instead of making it up."
)


class History:
    def __init__(self, path: Path):
        self.path = path
        logging.info("Loading history")
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.chat_id = data.get("chat_id")
        self.messages = data.get("messages", [])[-2 * MAX_TURNS:]
        logging.info("History ready: %s messages", len(self.messages))

    def connect(self, chat_id: int) -> bool:
        if self.chat_id is None:
            self.save(chat_id, self.messages)
            logging.info("Private chat connected")
        return self.chat_id == chat_id

    def prompt(self, text: str) -> list[dict[str, str]]:
        # Ollama's chat API expects messages in order, each with a role and content.
        logging.info("Preparing prompt")
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self.messages,
            {"role": "user", "content": text},
        ]

    def append(self, text: str, answer: str):
        # Keep only the last complete question-and-answer exchanges.
        messages = self.messages + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": answer},
        ]
        self.save(self.chat_id, messages[-2 * MAX_TURNS:])

    def clear(self):
        self.save(self.chat_id, [])
        logging.info("Context cleared")

    def save(self, chat_id, messages):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"chat_id": chat_id, "messages": messages}
        # Replace the file only after writing the new content in full.
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        self.chat_id = chat_id
        self.messages = messages
        logging.info("History saved")
