import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from teleqwen.storage.history import History


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'history.sqlite3'
        self.history = History(self.path)

    def tearDown(self):
        self.history.close()
        self.temp.cleanup()

    def test_persistence_and_new_conversation(self):
        first = self.history.active(1)
        self.history.append_turn(1, first, 'hello', 'hi')
        self.history.close()
        self.history = History(self.path)
        self.assertEqual(self.history.active(1), first)
        self.assertEqual(len(self.history.prompt(1, first, 'again')), 4)
        second = self.history.new(1)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.history.prompt(1, second, 'new')), 2)

    def test_legacy_titles_and_sql_default(self):
        legacy_path = Path(self.temp.name) / 'legacy.sqlite3'
        with closing(sqlite3.connect(legacy_path)) as db:
            db.executescript("""
                CREATE TABLE conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    title TEXT NOT NULL DEFAULT 'Nuova conversazione'
                );
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content TEXT NOT NULL
                );
                INSERT INTO conversations(chat_id) VALUES (1), (2);
                INSERT INTO messages(conversation_id, role, content)
                    VALUES (2, 'user', 'Nuova conversazione'), (2, 'assistant', 'Saved answer');
            """)
        legacy = History(legacy_path)
        try:
            self.assertEqual(legacy.list(1)[0]['title'], 'New conversation')
            self.assertEqual(legacy.list(2)[0]['title'], 'Nuova conversazione')
            legacy.new(1)
            self.assertEqual(legacy.list(1)[0]['title'], 'New conversation')
            self.assertEqual(legacy.prompt(2, 2, 'next')[1]['content'], 'Nuova conversazione')
        finally:
            legacy.close()

    def test_first_message_sets_title_only_once(self):
        conversation = self.history.new(1)
        self.history.append_turn(1, conversation, 'New conversation', 'Hello')
        self.history.append_turn(1, conversation, 'A follow-up', 'Answer')
        self.assertEqual(self.history.list(1)[0]['title'], 'New conversation')

    def test_delete_is_scoped_and_cascades(self):
        first = self.history.active(1)
        self.history.append_turn(1, first, 'private', 'answer')
        self.assertFalse(self.history.delete(2, first))
        self.assertEqual(len(self.history.prompt(2, first, 'hello')), 2)
        with self.assertRaises(ValueError):
            self.history.append_turn(2, first, 'wrong', 'owner')
        self.assertTrue(self.history.delete(1, first))
        self.assertEqual(self.history.db.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
        self.assertNotEqual(self.history.active(1), first)

    def test_clear_keeps_other_users(self):
        self.history.new(1)
        self.history.new(1)
        other = self.history.new(2)
        self.assertEqual(self.history.clear(1), 2)
        self.assertEqual(self.history.active(2), other)
        self.assertEqual(self.history.clear(1), 0)

    def test_retention_deletes_oldest_with_messages_and_keeps_other_users(self):
        other = self.history.new(2)
        ids = []
        for index in range(11):
            conversation = self.history.new(1)
            ids.append(conversation)
            self.history.append_turn(1, conversation, f'question {index}', 'answer')
        rows = self.history.list(1)
        self.assertEqual([row['id'] for row in rows], list(reversed(ids[1:])))
        self.assertEqual(self.history.active(1), ids[-1])
        self.assertEqual(self.history.active(2), other)
        self.assertEqual(self.history.db.execute('SELECT count(*) FROM messages WHERE conversation_id = ?', (ids[0],)).fetchone()[0], 0)
        self.assertEqual(self.history.db.execute('SELECT count(*) FROM conversations WHERE chat_id = 1').fetchone()[0], 10)

    def test_existing_database_trimmed_at_startup(self):
        with patch('teleqwen.storage.history.MAX_CONVERSATIONS', 20):
            ids = [self.history.new(1) for _ in range(14)]
            self.history.append_turn(1, ids[0], 'old', 'answer')
        self.history.close()
        self.history = History(self.path)
        self.assertEqual([row['id'] for row in self.history.list(1)], list(reversed(ids[-10:])))
        self.assertEqual(self.history.active(1), ids[-1])
        self.assertEqual(self.history.db.execute('SELECT count(*) FROM messages').fetchone()[0], 0)

    def test_retention_failure_rolls_back_new_conversation(self):
        ids = [self.history.new(1) for _ in range(10)]
        self.history.db.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON conversations BEGIN SELECT RAISE(ABORT, 'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.history.new(1)
        self.assertEqual(self.history.active(1), ids[-1])
        self.assertEqual([row['id'] for row in self.history.list(1)], list(reversed(ids)))

    def test_prompt_includes_entire_conversation_in_order(self):
        conversation = self.history.active(1)
        for n in range(25):
            self.history.append_turn(1, conversation, f'{n}'+ 'u'*1000, 'a'*1000)
        prompt = self.history.prompt(1, conversation, 'next')
        self.assertEqual(len(prompt), 52)
        self.assertGreater(sum(len(m['content']) for m in prompt), 12000)
        self.assertEqual(prompt[1]['content'], '0' + 'u'*1000)
        self.assertEqual(prompt[-1]['content'], 'next')
        self.assertEqual(prompt[-3]['content'], '24'+'u'*1000)
        self.assertEqual([m['role'] for m in prompt[1:-1]], ['user', 'assistant'] * ((len(prompt)-2)//2))


if __name__ == "__main__":
    unittest.main()
