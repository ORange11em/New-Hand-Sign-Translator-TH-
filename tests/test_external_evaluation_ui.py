"""Evaluation controls must show the scope of the selected model."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from handvox.external_evaluation_ui import ExternalEvaluationDialog, external_result_summary


class ExternalEvaluationUiTests(unittest.TestCase):
    def make_dialog(self, records, *, busy=False):
        dialog = ExternalEvaluationDialog.__new__(ExternalEvaluationDialog)
        dialog.classes = ("wave",)
        dialog.records = {
            str(index): SimpleNamespace(clip_id=str(index), gesture_name=name, quality=quality)
            for index, (name, quality) in enumerate(records)
        }
        dialog.collection_busy = busy
        dialog.future = None
        dialog.scope_var = Mock()
        dialog.evaluate_button = Mock()
        return dialog

    def test_mixed_dataset_enables_evaluation_and_shows_exclusions(self):
        dialog = self.make_dialog([("wave", "accepted"), ("neutral", "accepted"), ("unknown", "accepted")])
        dialog.update_evaluation_scope()
        dialog.evaluate_button.state.assert_called_once_with(["!disabled"])
        summary = dialog.scope_var.set.call_args.args[0]
        self.assertIn("ตรงกับโมเดล 1 คลิป", summary)
        self.assertIn("ข้าม 2 คลิป", summary)
        self.assertIn("neutral, unknown", summary)

    def test_unusable_or_busy_dataset_keeps_evaluation_disabled(self):
        for records, busy in (
            ([], False),
            ([("neutral", "accepted")], False),
            ([("wave", "pending")], False),
            ([("wave", "accepted")], True),
        ):
            with self.subTest(records=records, busy=busy):
                dialog = self.make_dialog(records, busy=busy)
                dialog.update_evaluation_scope()
                dialog.evaluate_button.state.assert_called_once_with(["disabled"])

    def test_result_summary_identifies_model_coverage_and_excluded_clips(self):
        payload = {
            "aggregate": {"accuracy": 0.5, "macro_f1": 0.4},
            "missing_classes": [],
            "excluded_clip_count": 32,
            "excluded_classes": ["neutral", "unknown"],
        }
        summary = external_result_summary(payload)
        self.assertIn("ครบทุกคลาสของโมเดล", summary)
        self.assertIn("ข้าม 32 คลิป", summary)
        self.assertIn("neutral, unknown", summary)
        self.assertIn("ไม่รวมในคะแนน", summary)
        del payload["excluded_clip_count"]
        del payload["excluded_classes"]
        self.assertNotIn("ข้าม", external_result_summary(payload))


if __name__ == "__main__":
    unittest.main()
