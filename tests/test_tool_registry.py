import unittest
from unittest.mock import patch

from teleqwen.agent.tool_registry import ToolRegistry


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()

        def repeat_text(text: str, count: int) -> str:
            return text * count

        self.enterContext(patch.dict(self.registry.registry, {"repeat_text": repeat_text}))

    def test_valid_arguments_are_accepted(self):
        self.assertEqual(self.registry.execute("repeat_text", {"text": "hello", "count": 2}), "hellohello")

    def test_incompatible_arguments_are_rejected(self):
        for value in ["2", True, 2.5, None, [], {}]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Invalid type"):
                self.registry.execute("repeat_text", {"text": "hello", "count": value})

    def test_missing_and_extra_arguments_are_rejected(self):
        for arguments in [{"text": "hello"}, {"text": "hello", "count": 2, "extra": 4}]:
            with self.subTest(arguments=arguments), self.assertRaises(TypeError):
                self.registry.execute("repeat_text", arguments)

    def test_arguments_must_be_an_object(self):
        for arguments in [None, [], "{}"]:
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValueError, "must be an object"):
                self.registry.execute("current_time", arguments)

    def test_unknown_tool_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown tool"):
            self.registry.execute("unknown", {})

    def test_time_tool_accepts_no_arguments(self):
        self.assertIsInstance(self.registry.execute("current_time", {}), str)
