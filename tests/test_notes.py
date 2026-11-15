import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teleqwen.agent.tool_registry import discover_tools
from teleqwen.agent.tools.notes import delete_note, save_note, search_notes


class NotesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "data" / "notes.json"
        self.enterContext(patch.dict(os.environ, {"TELEQWEN_NOTES": str(self.path)}))

    def test_notes_are_saved_and_loaded_from_disk(self):
        note = save_note("  Boiler filter replaced on November 15. 🔧  ")
        self.assertEqual(note["text"], "Boiler filter replaced on November 15. 🔧")
        self.assertTrue(note["id"])
        self.assertEqual(json.loads(self.path.read_text()), [note])
        self.assertEqual(search_notes(""), [note])

    def test_empty_notes_are_rejected_and_duplicates_are_not_added(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            save_note(" \n\t")
        self.assertFalse(self.path.exists())
        note = save_note("A saved note")
        self.assertEqual(save_note(" A saved note "), note)
        self.assertEqual(search_notes(""), [note])

    def test_search_matches_all_keywords_without_case_sensitivity(self):
        boiler = save_note("Boiler filter replaced in November")
        other = save_note("Car filter replaced in October")
        self.assertEqual(search_notes("NOVEMBER boiler"), [boiler])
        self.assertEqual(search_notes("filter"), [boiler, other])
        self.assertEqual(search_notes("boiler October"), [])
        self.assertEqual(search_notes(" \n"), [boiler, other])

    def test_searching_without_notes_does_not_create_a_file(self):
        self.assertEqual(search_notes("boiler"), [])
        self.assertFalse(self.path.exists())

    def test_delete_removes_only_the_requested_note(self):
        first = save_note("First note")
        second = save_note("Second note")
        self.assertEqual(delete_note(first["id"]), "Note deleted")
        self.assertEqual(search_notes(""), [second])
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Note not found"):
            delete_note(first["id"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_writes_keep_existing_notes(self):
        note = save_note("Keep this note")
        before = self.path.read_bytes()
        for operation in [lambda: save_note("New note"), lambda: delete_note(note["id"])]:
            for failure in ["write_text", "replace"]:
                with self.subTest(operation=operation, failure=failure):
                    with patch.object(Path, failure, side_effect=OSError("disk error")):
                        with self.assertRaises(OSError):
                            operation()
                    self.assertEqual(self.path.read_bytes(), before)
                    self.assertEqual(search_notes(""), [note])

    def test_invalid_notes_file_is_not_overwritten(self):
        self.path.parent.mkdir()
        for content in ["invalid json", "{}", "[{}]", '[{"id": "one", "text": 123}]']:
            with self.subTest(content=content):
                self.path.write_text(content)
                with self.assertRaises(ValueError):
                    save_note("New note")
                self.assertEqual(self.path.read_text(), content)

    def test_only_public_tools_are_discovered(self):
        registry, schemas = discover_tools()
        self.assertTrue({"save_note", "search_notes", "delete_note"}.issubset(registry))
        self.assertFalse(any(name.startswith("_") for name in registry))
        self.assertEqual({schema["function"]["name"] for schema in schemas}, set(registry))
