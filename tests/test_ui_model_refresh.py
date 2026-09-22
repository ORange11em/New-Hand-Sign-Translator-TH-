"""ทดสอบการอัปเดตคำศัพท์ใน UI หลังการเทรนและติดตั้งโมเดล."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from handvox.gesture_catalog import ActiveGesture, PlannedGesture
from handvox.training_config import load_training_config
from handvox.ui import (
    GesturesPage,
    HandVoxApp,
    TrainingPage,
    experiment_preserves_active_words,
    training_plan_progress,
)


class TrainingUiRefreshTests(unittest.TestCase):
    def test_standard_training_busy_state_uses_the_real_train_button(self):
        page = TrainingPage.__new__(TrainingPage)
        page.train_button = Mock()
        page.quick_train_button = Mock()

        page._set_training_busy(True, quick_mode=False)

        page.train_button.configure.assert_called_once_with(
            text="กำลังเทรนและวัดผล..."
        )
        page.train_button.state.assert_called_once_with(["disabled"])
        page.quick_train_button.configure.assert_not_called()

    def test_add_gesture_button_opens_blank_waiting_form(self):
        page = GesturesPage.__new__(GesturesPage)
        page.tabs = Mock()
        page.new_form = Mock()
        page.form_vars = {"priority": Mock()}
        page.notes = Mock()
        page.form_widgets = {"name": Mock()}
        page.app = Mock()

        page.begin_new_gesture()

        page.tabs.select.assert_called_once_with(1)
        page.new_form.assert_called_once_with()
        page.form_vars["priority"].set.assert_called_once_with("5")
        page.notes.insert.assert_called_once()
        page.form_widgets["name"].focus_set.assert_called_once_with()
        page.app.set_status.assert_called_once()

    def test_completed_scope_is_reported_without_treating_words_as_missing(self):
        page = TrainingPage.__new__(TrainingPage)
        config = load_training_config()
        page.app = Mock()
        page.app.catalog.load_active.return_value = [
            ActiveGesture(name, name, (0, 0, 0))
            for name in config.visible_gestures
        ]
        page.app.catalog.load_planned.return_value = []
        page.target_var = Mock()
        page.target_var.get.return_value = ""
        page.gesture_var = Mock()
        page.gesture_var.get.return_value = config.visible_gestures[0]
        page.target_combo = Mock()
        page.collection_combos = [Mock(), Mock(), Mock()]
        page.target_summary_var = Mock()
        page.model_status_var = Mock()

        with patch("handvox.ui.load_training_config", return_value=config):
            page._reload_round_config()

        page.target_combo.configure.assert_called_once_with(
            values=(), state="disabled"
        )
        page.model_status_var.set.assert_called_once_with(
            "ใช้กับกล้องได้ 16 คำ · ไม่มีคำสูญหาย"
        )
        summary = page.target_summary_var.set.call_args.args[0]
        self.assertIn("ไม่มีคำที่รอเพิ่ม", summary)

    def test_every_planned_word_appears_as_next_training_target(self):
        page = TrainingPage.__new__(TrainingPage)
        config = load_training_config()
        page.app = Mock()
        page.app.catalog.load_active.return_value = [
            ActiveGesture(name, name, (0, 0, 0))
            for name in config.visible_gestures
        ]
        page.app.catalog.load_planned.return_value = [
            PlannedGesture("sleep", "นอน", "การกระทำ")
        ]
        page.target_var = Mock()
        page.target_var.get.return_value = "นอน"
        page.gesture_var = Mock()
        page.gesture_var.get.return_value = config.visible_gestures[0]
        page.target_combo = Mock()
        page.collection_combos = [Mock(), Mock(), Mock()]
        page.target_summary_var = Mock()
        page.model_status_var = Mock()

        with patch("handvox.ui.load_training_config", return_value=config):
            page._reload_round_config()

        page.target_combo.configure.assert_called_once_with(
            values=("นอน",), state="readonly"
        )
        self.assertEqual(
            page.config.visible_gestures,
            (*config.visible_gestures, "นอน"),
        )
        collection_values = page.collection_combos[2].configure.call_args.kwargs["values"]
        self.assertEqual(collection_values[0], "นอน")

    def test_pending_experiment_is_marked_stale_when_it_would_drop_a_word(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model_manifest.json").write_text(
                json.dumps(
                    {
                        "visible_gestures": [
                            {"name": "น้ำ"},
                            {"name": "กิน"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            experiment = {"path": root}
            self.assertTrue(
                experiment_preserves_active_words(experiment, {"น้ำ"})
            )
            self.assertFalse(
                experiment_preserves_active_words(experiment, {"น้ำ", "หมอ"})
            )

    def test_passed_training_is_installed_and_all_word_pages_are_reloaded(self):
        page = TrainingPage.__new__(TrainingPage)
        page.app = Mock()
        page.app.pages = {}
        page._set_training_busy = Mock()
        page._refresh_experiments = Mock()
        page.show_step = Mock()
        page.experiment_tree = Mock()
        page._update_experiment_actions = Mock()
        process = Mock()
        process.poll.return_value = 0
        experiment = {
            "id": "quick_test",
            "path": "experiment-path",
            "passed": True,
            "mode": "quick_trial",
            "target_gesture": "น้ำ",
        }

        with (
            patch("handvox.ui.list_experiments", return_value=[experiment]),
            patch("handvox.ui.activate_experiment", return_value="backup-path") as activate,
            patch("handvox.ui.messagebox.showinfo"),
        ):
            page._poll_training(process, "น้ำ", quick_mode=True)

        activate.assert_called_once_with("experiment-path", allow_quick_trial=True)
        page.app.reload_model_state.assert_called_once_with()
        page.app.show_page.assert_called_once_with("gestures")
        page.app.set_status.assert_called_once()

    def test_excess_clips_in_one_session_do_not_mark_collection_complete(self):
        config = load_training_config()
        records = [
            SimpleNamespace(
                gesture_name=config.all_classes[0],
                signer_id=config.collection.signers[0],
                session_id=config.collection.sessions[0],
                quality="accepted",
            )
            for _ in range(config.collection.target_clips_per_signer_per_class * 3)
        ]

        progress = training_plan_progress(config, records)

        self.assertEqual(progress["capture_groups_complete"], 1)
        self.assertLess(
            progress["capture_groups_complete"], progress["capture_groups_total"]
        )
        self.assertEqual(progress["accepted_scopes_complete"], 0)

    def test_quick_readiness_shows_real_blocking_reason(self):
        page = TrainingPage.__new__(TrainingPage)
        page.target_var = Mock()
        page.target_var.get.return_value = "นอน"
        page.app = Mock()
        page.app.dataset_store.records.return_value = []
        page.quick_summary_var = Mock()
        page.quick_train_button = Mock()
        report = SimpleNamespace(
            ready=False,
            items=(
                SimpleNamespace(
                    status="error",
                    message="ต้องมี accepted จากอย่างน้อย 2 กลุ่มผู้ทำท่าและรอบถ่าย",
                ),
            ),
        )

        page._refresh_quick_readiness(report)

        message = page.quick_summary_var.set.call_args.args[0]
        self.assertIn("อย่างน้อย 2 กลุ่ม", message)
        page.quick_train_button.state.assert_called_once_with(["disabled"])

    def test_reload_model_state_refreshes_every_page_that_uses_active_words(self):
        app = HandVoxApp.__new__(HandVoxApp)
        pages = {
            name: Mock()
            for name in ("dashboard", "sentence", "gestures", "training")
        }
        app.pages = pages
        catalog = Mock()
        catalog.load_active.return_value = ["น้ำ"]

        with patch("handvox.ui.GestureCatalog", return_value=catalog):
            app.reload_model_state()

        self.assertEqual(app.active_gestures, ["น้ำ"])
        for page in pages.values():
            page.refresh.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
