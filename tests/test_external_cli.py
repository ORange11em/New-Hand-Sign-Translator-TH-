"""ทดสอบคำสั่งเก็บและวัดผู้ใช้ใหม่โดยไม่เปิดกล้องหรือแก้โมเดลจริง."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import collect_dataset_v2
from handvox.errors import HandVoxError
from handvox.paths import EXPERIMENTS_DIR, ROOT
from handvox.training_config import load_training_config
import training_cli


class ExternalCollectorTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.config = load_training_config()
        self.stack.enter_context(
            patch.object(collect_dataset_v2, "load_training_config", return_value=self.config)
        )
        self.catalog = self.stack.enter_context(
            patch.object(collect_dataset_v2, "GestureCatalog")
        ).return_value
        self.catalog.load_active.return_value = []
        self.catalog.load_planned.return_value = []
        self.camera = self.stack.enter_context(
            patch.object(collect_dataset_v2.cv2, "VideoCapture")
        )
        self.sequence_length = self.stack.enter_context(
            patch.object(collect_dataset_v2, "get_experiment_sequence_length", return_value=30)
        )
        self.store_factory = self.stack.enter_context(
            patch.object(collect_dataset_v2, "DatasetV2Store")
        )
        self.training_signers = self.stack.enter_context(
            patch.object(collect_dataset_v2, "get_training_signers")
        )
        self.experiment_classes = self.stack.enter_context(
            patch.object(collect_dataset_v2, "get_experiment_classes")
        )
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(redirect_stderr(io.StringIO()))

    def arguments(self, signer="person_03", gesture=None):
        return [
            "--signer", signer,
            "--session", self.config.collection.sessions[0],
            "--gesture", gesture or self.config.visible_gestures[0],
        ]

    def assert_rejected_before_capture(self, arguments):
        with self.assertRaises(SystemExit) as raised:
            collect_dataset_v2.main(arguments)
        self.assertEqual(raised.exception.code, 2)
        self.camera.assert_not_called()
        self.store_factory.assert_not_called()

    def complete_collection(self, signer, gesture):
        self.store_factory.return_value.records.return_value = [
            SimpleNamespace(
                gesture_name=gesture,
                signer_id=signer,
                session_id=self.config.collection.sessions[0],
                quality="accepted",
            )
            for _ in range(4)
        ]

    def test_training_collector_rejects_unconfigured_signer(self):
        self.assert_rejected_before_capture(self.arguments())

    def test_external_collector_rejects_configured_training_signer(self):
        self.assert_rejected_before_capture(
            self.arguments(signer=self.config.collection.signers[0])
            + ["--external-evaluation"]
        )

    def test_external_collector_rejects_unsafe_signer_ids(self):
        for signer in ("", "../person_03", "person 03", "person_03/clip"):
            with self.subTest(signer=signer):
                self.assert_rejected_before_capture(
                    self.arguments(signer=signer) + ["--external-evaluation"]
                )

    def test_external_collector_rejects_source_training_signer(self):
        self.training_signers.return_value = ("person_03",)
        self.experiment_classes.return_value = self.config.visible_gestures
        self.assert_rejected_before_capture(
            self.arguments() + ["--external-evaluation", "--experiment", "saved_run"]
        )
        self.training_signers.assert_called_once_with(EXPERIMENTS_DIR / "saved_run")

    def test_external_collector_uses_separate_dataset(self):
        gesture = self.config.visible_gestures[0]
        self.complete_collection("person_03", gesture)
        result = collect_dataset_v2.main(self.arguments() + ["--external-evaluation"])
        self.assertEqual(result, 0)
        self.store_factory.assert_called_once_with(ROOT / "dataset_external_v2")
        self.camera.assert_not_called()

    def test_frozen_source_allows_retired_class(self):
        self.training_signers.return_value = self.config.collection.signers
        self.experiment_classes.return_value = ("retired_gesture", "neutral", "unknown")
        self.complete_collection("person_03", "retired_gesture")
        with TemporaryDirectory() as directory:
            result = collect_dataset_v2.main(
                self.arguments(gesture="retired_gesture")
                + ["--external-evaluation", "--experiment", directory]
            )
            self.assertEqual(result, 0)
            self.experiment_classes.assert_called_once_with(Path(directory))
        self.camera.assert_not_called()

    def test_frozen_source_rejects_class_outside_saved_model(self):
        self.training_signers.return_value = self.config.collection.signers
        self.experiment_classes.return_value = ("different_gesture", "neutral", "unknown")
        self.assert_rejected_before_capture(
            self.arguments() + ["--external-evaluation", "--experiment", "saved_run"]
        )

    def test_external_collector_preserves_session_choices(self):
        arguments = self.arguments()
        arguments[3] = "session_99"
        self.assert_rejected_before_capture(arguments + ["--external-evaluation"])

    def test_new_test_session_is_not_allowed_for_training(self):
        arguments = self.arguments(signer="person_01")
        arguments[3] = "session_05"
        self.assert_rejected_before_capture(arguments)

    def test_completed_new_test_session_does_not_open_camera(self):
        gesture = self.config.visible_gestures[0]
        self.complete_collection("person_03", gesture)
        for record in self.store_factory.return_value.records.return_value:
            record.session_id = "session_05"
        arguments = self.arguments()
        arguments[3] = "session_05"
        self.assertEqual(collect_dataset_v2.main(arguments + ["--external-evaluation"]), 0)
        self.store_factory.assert_called_once_with(ROOT / "dataset_external_v2")
        self.camera.assert_not_called()

    def test_new_test_session_resumes_and_saves_only_missing_clips_as_pending(self):
        gesture = self.config.visible_gestures[0]
        self.complete_collection("person_03", gesture)
        store = self.store_factory.return_value
        store.records.return_value = store.records.return_value[:2]
        for record in store.records.return_value:
            record.session_id = "session_05"
        store.next_clip_number.side_effect = [3, 4]
        self.camera.return_value.isOpened.return_value = True
        for name in ("save_sequence", "save_preview", "reference_for"):
            self.stack.enter_context(patch.object(collect_dataset_v2, name))
        self.stack.enter_context(patch.object(collect_dataset_v2.mp.solutions.holistic, "Holistic"))
        self.stack.enter_context(patch.object(collect_dataset_v2.cv2, "namedWindow"))
        self.stack.enter_context(patch.object(collect_dataset_v2.cv2, "destroyAllWindows"))
        self.stack.enter_context(patch.object(collect_dataset_v2, "countdown", return_value=True))
        capture = self.stack.enter_context(patch.object(
            collect_dataset_v2, "collect_clip", return_value=(np.zeros((30, 171), dtype=np.float32), [])
        ))
        arguments = self.arguments()
        arguments[3] = "session_05"
        self.assertEqual(collect_dataset_v2.main(arguments + ["--external-evaluation"]), 0)
        self.assertEqual(capture.call_count, 2)
        self.assertEqual(store.append.call_count, 2)
        for call in store.append.call_args_list:
            record = call.args[0]
            self.assertEqual((record.signer_id, record.session_id, record.quality),
                             ("person_03", "session_05", "pending"))
            self.assertIn("วัดผู้ใช้ใหม่", record.notes)
        store.mark_superseded.assert_not_called()
        self.store_factory.assert_called_once_with(ROOT / "dataset_external_v2")
        self.camera.return_value.release.assert_called_once()

    def test_source_requires_external_mode(self):
        self.assert_rejected_before_capture(
            self.arguments(signer=self.config.collection.signers[0])
            + ["--experiment", "saved_run"]
        )


class ExternalEvaluationCommandTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.evaluator = self.stack.enter_context(
            patch.object(training_cli, "evaluate_external")
        )
        self.store_factory = self.stack.enter_context(
            patch.object(training_cli, "DatasetV2Store")
        )
        self.activation = self.stack.enter_context(
            patch.object(training_cli, "activate_experiment")
        )
        self.trainer = self.stack.enter_context(
            patch.object(training_cli, "train_and_evaluate")
        )
        self.output = io.StringIO()
        self.stack.enter_context(redirect_stdout(self.output))
        self.evaluator.return_value = (
            Path("external_report"),
            {
                "aggregate": {"accuracy": 0.5, "macro_f1": 0.4},
                "signers": ["person_03"],
                "accepted_clips": 4,
                "missing_classes": ["unknown"],
            },
        )

    def test_evaluation_defaults_to_separate_dataset_without_training_or_activation(self):
        result = training_cli.main(["evaluate-external", "saved_run"])
        self.assertEqual(result, 0)
        self.store_factory.assert_called_once_with(ROOT / "dataset_external_v2")
        self.evaluator.assert_called_once_with(
            EXPERIMENTS_DIR / "saved_run", self.store_factory.return_value
        )
        self.activation.assert_not_called()
        self.trainer.assert_not_called()
        self.assertIn("0.5000", self.output.getvalue())
        self.assertIn("unknown", self.output.getvalue())

    def test_evaluation_accepts_explicit_source_and_dataset_paths(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            dataset = Path(directory) / "new_people"
            result = training_cli.main(
                ["evaluate-external", str(source), "--dataset", str(dataset)]
            )
            self.assertEqual(result, 0)
            self.store_factory.assert_called_once_with(dataset)
            self.evaluator.assert_called_once_with(source, self.store_factory.return_value)

    def test_evaluation_failure_returns_error_without_activation(self):
        self.evaluator.side_effect = HandVoxError("ข้อมูลผู้ใช้ใหม่ยังไม่พร้อม")
        result = training_cli.main(["evaluate-external", "saved_run"])
        self.assertEqual(result, 2)
        self.assertIn("ข้อมูลผู้ใช้ใหม่ยังไม่พร้อม", self.output.getvalue())
        self.activation.assert_not_called()
        self.trainer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
