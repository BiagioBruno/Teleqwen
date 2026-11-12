"""Local conversation storage. All queries are scoped to the Telegram chat."""
import sqlite3
from pathlib import Path

SYSTEM_PROMPT = "You are a personal assistant. Respond clearly and concisely. If you do not know something, say so."
MAX_CONVERSATIONS = 10


class History:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA secure_delete = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL DEFAULT 'New conversation'
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active
                ON conversations(chat_id) WHERE active = 1;
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id, id);
        """)
        # Apply retention to databases created by earlier versions too.
        with self.db:
            # Translate only empty placeholder titles from the original schema.
            self.db.execute("""UPDATE conversations SET title = 'New conversation'
                WHERE title = ? AND NOT EXISTS (
                    SELECT 1 FROM messages WHERE conversation_id = conversations.id
                )""", ("Nuova conversazione",))
            for row in self.db.execute("SELECT DISTINCT chat_id FROM conversations").fetchall():
                self._trim(row["chat_id"])

    def _trim(self, chat_id: int):
        self.db.execute("""DELETE FROM conversations WHERE chat_id = ? AND id NOT IN (
            SELECT id FROM conversations WHERE chat_id = ?
            ORDER BY active DESC, id DESC LIMIT ?
        )""", (chat_id, chat_id, MAX_CONVERSATIONS))

    def close(self):
        self.db.close()

    def new(self, chat_id: int) -> int:
        with self.db:
            self.db.execute("UPDATE conversations SET active = 0 WHERE chat_id = ?", (chat_id,))
            # Explicit title also supports older databases with an Italian SQL default.
            cursor = self.db.execute("INSERT INTO conversations(chat_id, title) VALUES (?, ?)", (chat_id, "New conversation"))
            self._trim(chat_id)
        return cursor.lastrowid

    def active(self, chat_id: int) -> int:
        row = self.db.execute("SELECT id FROM conversations WHERE chat_id = ? AND active = 1", (chat_id,)).fetchone()
        return row["id"] if row else self.new(chat_id)

    def list(self, chat_id: int):
        return self.db.execute("SELECT id, title, active FROM conversations WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, MAX_CONVERSATIONS)).fetchall()

    def delete(self, chat_id: int, conversation_id: int) -> bool:
        with self.db:
            cursor = self.db.execute("DELETE FROM conversations WHERE chat_id = ? AND id = ?", (chat_id, conversation_id))
        return cursor.rowcount > 0

    def clear(self, chat_id: int) -> int:
        with self.db:
            cursor = self.db.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
        return cursor.rowcount

    def prompt(self, chat_id: int, conversation_id: int, text: str) -> list[dict[str, str]]:
        rows = self.db.execute("""SELECT m.role, m.content FROM messages m JOIN conversations c
            ON c.id = m.conversation_id WHERE c.chat_id = ? AND c.id = ? ORDER BY m.id""",
            (chat_id, conversation_id)).fetchall()
        # Ollama applies its token-based context window; do not guess using characters.
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[dict(row) for row in rows],
            {"role": "user", "content": text},
        ]

    def append_turn(self, chat_id: int, conversation_id: int, text: str, answer: str):
        with self.db:
            row = self.db.execute("SELECT id FROM conversations WHERE chat_id = ? AND id = ?", (chat_id, conversation_id)).fetchone()
            if row is None:
                raise ValueError("Conversation does not belong to chat")
            self.db.executemany("INSERT INTO messages(conversation_id, role, content) VALUES (?, ?, ?)",
                [(conversation_id, "user", text), (conversation_id, "assistant", answer)])
            self.db.execute("""UPDATE conversations SET title = ? WHERE id = ?
                AND (SELECT count(*) FROM messages WHERE conversation_id = ?) = 2""",
                (" ".join(text.split())[:60], conversation_id, conversation_id))
