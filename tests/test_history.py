import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teleqwen.storage.history import History, MAX_TURNS


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "data" / "history.json"
        self.history = History(self.path)

    def test_context_and_chat_survive_restart(self):
        self.assertTrue(self.history.connect(123))
        self.history.append("Ciao 😀", "Ciao!")
        restored = History(self.path)
        self.assertTrue(restored.connect(123))
        self.assertFalse(restored.connect(456))
        self.assertEqual(restored.prompt("Next"), [
            {"role": "system", "content": "You are a personal assistant. Reply clearly and concisely."},
            {"role": "user", "content": "Ciao 😀"},
            {"role": "assistant", "content": "Ciao!"},
            {"role": "user", "content": "Next"},
        ])

    def test_only_recent_complete_exchanges_are_saved(self):
        for number in range(MAX_TURNS + 3):
            self.history.append(str(number), "answer")
        messages = History(self.path).messages
        self.assertEqual(len(messages), 2 * MAX_TURNS)
        self.assertEqual(messages[0]["content"], "3")
        self.assertEqual(messages[-2]["content"], str(MAX_TURNS + 2))
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"] * MAX_TURNS)

    def test_clear_removes_context_but_keeps_the_same_chat(self):
        self.history.connect(123)
        self.history.append("question", "answer")
        self.history.clear()
        restored = History(self.path)
        self.assertEqual(restored.messages, [])
        self.assertFalse(restored.connect(456))
        self.assertEqual(len(restored.prompt("Again")), 2)

    def test_failed_write_keeps_the_previous_file(self):
        self.history.append("saved", "answer")
        before = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                self.history.append("new", "answer")
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_json_is_not_silently_discarded(self):
        self.path.parent.mkdir()
        self.path.write_text("invalid json")
        with self.assertRaises(json.JSONDecodeError):
            History(self.path)
        self.assertEqual(self.path.read_text(), "invalid json")
