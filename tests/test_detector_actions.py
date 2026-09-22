"""Exercise the runtime actions without importing camera/model startup code."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from handvox.sentence import SentenceBuilder


class DetectorActionsTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "run_detector.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        selected = {"save_sentence", "speak_sentence", "add_confirmed_word", "perform_sentence_action"}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in selected]
        self.assertEqual(len(functions), len(selected))
        self.context = {
            "sentence": SentenceBuilder(), "history": Mock(), "speech": Mock(),
            "settings": SimpleNamespace(history_limit=100, save_spoken_sentences=True),
            "recognizer": Mock(speech_armed=True), "hold_timer": Mock(),
            "add_cooldown": 0.0, "COOLDOWN_SEC": 1.0,
            "action_feedback": "", "feedback_until": 0.0,
            "print": Mock(),
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), self.context)

    def action(self, action, label="", now=10.0):
        self.context["perform_sentence_action"](action, label, now)

    def test_add_requires_confirmed_label_and_rearms_only_after_release(self):
        self.action("add")
        self.assertEqual(len(self.context["sentence"]), 0)
        self.action("add", "น้ำ")
        self.assertEqual(self.context["sentence"].text, "น้ำ")
        self.context["recognizer"].mark_emitted.assert_called_once_with("น้ำ")
        self.context["recognizer"].speech_armed = False
        self.action("add", "ช่วยด้วย", now=12)
        self.assertEqual(self.context["sentence"].text, "น้ำ")

    def test_save_and_speak_keep_existing_history_path(self):
        self.context["sentence"].add("น้ำ")
        self.action("save")
        self.context["history"].add.assert_called_once_with("น้ำ", source="detector-manual", limit=100)
        self.action("speak")
        self.context["speech"].speak.assert_called_once_with("น้ำ")
        self.context["history"].add.assert_called_with("น้ำ", source="detector-tts", limit=100)

    def test_remove_and_clear_only_modify_current_sentence(self):
        self.context["sentence"].add("น้ำ")
        self.context["sentence"].add("ขอบคุณ")
        self.action("remove")
        self.assertEqual(self.context["sentence"].text, "น้ำ")
        self.action("clear")
        self.assertEqual(len(self.context["sentence"]), 0)
        self.context["history"].add.assert_not_called()

    def test_empty_sentence_does_not_speak_or_write_history(self):
        self.action("speak")
        self.action("save")
        self.context["speech"].speak.assert_not_called()
        self.context["history"].add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
