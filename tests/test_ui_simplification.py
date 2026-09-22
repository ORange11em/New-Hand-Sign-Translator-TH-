"""Keep the simplified controls equivalent to their explicit, safe actions."""

import unittest
from unittest.mock import Mock, patch

from handvox.ui import (
    Disclosure,
    HandVoxApp,
    TrainingPage,
    experiment_primary_action,
    experiment_time_label,
)


class UiSimplificationTests(unittest.TestCase):
    def test_sidebar_keeps_training_as_the_single_dataset_entry_point(self):
        keys = [key for key, label in HandVoxApp.NAV_ITEMS]
        self.assertNotIn("dataset", keys)
        self.assertEqual(keys.count("training"), 1)
        self.assertEqual(len(keys), len(set(keys)))

    def test_primary_action_depends_on_installation_and_evaluation(self):
        scenarios = (
            (None, "", ("ติดตั้งโมเดล", "none")),
            ({"id": "current", "passed": False}, "current", ("เปิดกล้องโมเดลนี้", "camera")),
            ({"id": "current", "passed": True}, "current", ("เปิดกล้องโมเดลนี้", "camera")),
            ({"id": "new", "passed": True}, "current", ("ติดตั้งโมเดล", "install")),
            ({"id": "new", "passed": False}, "current", ("ติดตั้งแบบทดลอง", "trial")),
        )
        for experiment, installed_id, expected in scenarios:
            with self.subTest(experiment=experiment):
                self.assertEqual(experiment_primary_action(experiment, installed_id), expected)

    def test_existing_model_camera_action_never_reinstalls(self):
        page = TrainingPage.__new__(TrainingPage)
        page.app = Mock()
        page._selected_experiment = Mock(return_value={"id": "current", "passed": False})
        page.activate_trial_selected = Mock()
        with patch("handvox.ui.installed_experiment_id", return_value="current"), patch(
            "handvox.ui.activate_experiment"
        ) as activate:
            page.activate_selected()
        page.app.open_detector.assert_called_once_with()
        page.activate_trial_selected.assert_not_called()
        activate.assert_not_called()

    def test_failed_result_still_uses_the_trial_confirmation(self):
        page = TrainingPage.__new__(TrainingPage)
        page._selected_experiment = Mock(return_value={"id": "new", "passed": False})
        page.activate_trial_selected = Mock()
        with patch("handvox.ui.installed_experiment_id", return_value="current"), patch(
            "handvox.ui.activate_experiment"
        ) as activate:
            page.activate_selected()
        page.activate_trial_selected.assert_called_once_with()
        activate.assert_not_called()

    def test_cancelled_trial_does_not_modify_the_model(self):
        page = TrainingPage.__new__(TrainingPage)
        page._selected_experiment = Mock(return_value={"id": "new", "passed": False})
        with patch("handvox.ui.messagebox.askyesno", return_value=False) as confirm, patch(
            "handvox.ui.activate_experiment"
        ) as activate:
            page.activate_trial_selected()
        confirm.assert_called_once()
        activate.assert_not_called()

    def test_disclosure_hides_controls_without_destroying_them(self):
        disclosure = Disclosure.__new__(Disclosure)
        disclosure.title = "รายละเอียด"
        disclosure.toggle_button = Mock()
        disclosure.body = Mock()
        disclosure.set_expanded(False)
        self.assertFalse(disclosure.expanded)
        disclosure.body.pack_forget.assert_called_once_with()
        disclosure.body.destroy.assert_not_called()
        disclosure.set_expanded(True)
        self.assertTrue(disclosure.expanded)
        disclosure.body.pack.assert_called_once_with(fill="both", expand=True)

    def test_step_completion_is_shown_on_the_existing_tab(self):
        page = TrainingPage.__new__(TrainingPage)
        page.notebook = Mock()
        page._set_step_state(2, "complete", "ตรวจครบ")
        page.notebook.tab.assert_called_once_with(2, text=page.STEP_TITLES[2] + " ✓")

    def test_results_keep_ids_for_actions_but_show_readable_values(self):
        page = TrainingPage.__new__(TrainingPage)
        page.experiment_tree = Mock()
        page.experiment_tree.get_children.return_value = []
        page.experiment_tree.selection.return_value = ()
        page._update_experiment_actions = Mock()
        experiment = {
            "id": "current", "created_at": "2026-09-15T11:28:22+07:00",
            "target_gesture": "น้ำ", "evaluation_strategy": "known_signers_session_holdout",
            "accuracy": 0.7615, "macro_f1": 0.7937, "passed": False,
        }
        with patch("handvox.ui.installed_experiment_id", return_value="current"):
            page._refresh_experiments([experiment])
        values = page.experiment_tree.insert.call_args.kwargs
        self.assertEqual(values["iid"], "current")
        self.assertEqual(values["values"], (
            "15/09/2026 11:28", "น้ำ", "คนเดิม / แยกรอบ", "76.15%", "79.37%", "ใช้งานอยู่ (ทดลอง)"
        ))
        self.assertEqual(page._last_experiments, [experiment])
        page.experiment_tree.selection_set.assert_called_once_with("current")

    def test_empty_results_refresh_disables_actions(self):
        page = TrainingPage.__new__(TrainingPage)
        page._selected_experiment = Mock(return_value=None)
        page.experiment_detail_var = Mock()
        for name in ("activate_button", "open_report_button", "external_evaluation_button"):
            setattr(page, name, Mock())
        page._update_experiment_actions()
        for button in (page.activate_button, page.open_report_button, page.external_evaluation_button):
            button.state.assert_called_once_with(["disabled"])

    def test_unknown_timestamp_is_preserved(self):
        self.assertEqual(experiment_time_label("older report"), "older report")


if __name__ == "__main__":
    unittest.main()
