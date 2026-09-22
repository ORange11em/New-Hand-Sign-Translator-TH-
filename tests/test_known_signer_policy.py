"""Regression coverage for training scope, saved policy and independent evaluation UI."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import numpy as np

from body_features import FEATURE_COUNT
from handvox.dataset_v2 import ClipMetadata, DatasetV2Store
from handvox.errors import HandVoxError
from handvox.external_evaluation_ui import external_result_summary
from handvox.feature_pipeline import (
    FEATURE_SCHEMA_VERSION, OUTPUT_FEATURE_COUNT, FeaturePipelineConfig, TemporalFeaturePipeline
)
from handvox.training_config import load_training_config
from handvox.training_workflow import (
    _known_signers_session_holdout_folds,
    _load_accepted_arrays,
    _manifest,
    _predictions_with_recognition_policy,
    _temporal_feature_manifest,
    activate_experiment,
    preflight,
    quick_trial_readiness,
    temporal_pipeline_from_manifest,
)
from handvox.ui import TrainingPage, experiment_failure_summary


class KnownSignerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_training_config()

    def record(self, signer, clip_id, session="session_01"):
        return ClipMetadata(
            clip_id=clip_id,
            gesture_name=self.config.visible_gestures[0],
            signer_id=signer,
            session_id=session,
            recorded_at="2026-09-15T06:00:00+07:00",
            camera_index=0,
            quality="accepted",
            sequence_file=f"clips/{clip_id}.npy",
            duration_frames=30,
            feature_count=FEATURE_COUNT,
        )

    def test_training_ignores_external_signers_even_with_missing_files(self):
        with TemporaryDirectory() as directory:
            store = DatasetV2Store(directory)
            store.initialize()
            store.append(self.record("person_01", "training"))
            store.append(self.record("person_03", "external", session="new_session"))
            np.save(store.clips_dir / "training.npy", np.zeros((30, FEATURE_COUNT)))
            with patch("handvox.training_workflow._reference_items", return_value=[]):
                report = preflight(self.config, store)
            self.assertEqual(report.accepted_clips, 1)
            self.assertNotIn("sequence_missing", {item.code for item in report.items})
            self.assertNotIn("unexpected_sessions", {item.code for item in report.items})
            features, labels, signers, sessions, records = _load_accepted_arrays(self.config, store)
            self.assertEqual(len(features), 1)
            self.assertEqual(signers.tolist(), ["person_01"])
            self.assertEqual([record.clip_id for record in records], ["training"])

    def test_unplanned_training_session_is_rejected_before_loading(self):
        with TemporaryDirectory() as directory:
            store = DatasetV2Store(directory)
            store.append(self.record("person_01", "unplanned", session="session_05"))
            with self.assertRaisesRegex(HandVoxError, "session นอกแผน"):
                _load_accepted_arrays(self.config, store)

    def test_holdout_does_not_silently_leave_an_extra_session_untested(self):
        labels, signers, sessions = [], [], []
        for signer in self.config.collection.signers:
            for session in (*self.config.collection.sessions, "session_05"):
                labels.append("wave")
                signers.append(signer)
                sessions.append(session)
        with self.assertRaisesRegex(HandVoxError, "session นอกแผน"):
            _known_signers_session_holdout_folds(self.config, labels, signers, sessions)

    def test_quick_readiness_does_not_count_external_signers(self):
        config = replace(self.config, target_gesture=self.config.visible_gestures[0])
        store = Mock()
        store.records.return_value = [self.record("person_03", str(index)) for index in range(4)]
        store.inventory.return_value = []
        with TemporaryDirectory() as directory, patch(
            "handvox.training_workflow.LEGACY_DATA_FILE", Path(directory) / "missing.npz"
        ), patch("handvox.training_workflow._reference_items", return_value=[]):
            report = quick_trial_readiness(config, store)
        self.assertEqual(report.accepted_clips, 0)
        self.assertIn("quick_target_below_minimum", {item.code for item in report.items})

    def test_svc_without_probability_is_not_ready_for_deployment(self):
        config = replace(self.config, training=replace(
            self.config.training, algorithm="SVC", parameters={"probability": False}
        ))
        store = Mock()
        store.records.return_value = []
        store.inventory.return_value = []
        store.summary.return_value = {"quality": {}}
        with patch("handvox.training_workflow._reference_items", return_value=[]):
            report = preflight(config, store)
        self.assertIn("svc_probability_required", {item.code for item in report.items})

    def test_manifest_keeps_evaluation_scope_and_only_evaluated_policy(self):
        metrics = {"accuracy": 0.8, "macro_f1": 0.8, "passed": True}
        manifest = _manifest(self.config, metrics, "test")
        self.assertEqual(manifest["training_signers"], ["person_01", "person_02"])
        self.assertEqual(manifest["evaluation_scope"], "known_signers_session_holdout")
        self.assertEqual(manifest["recognition_policy"]["minimum_confidence"], 0.72)
        quick = _manifest(replace(self.config, mode="quick_trial"), metrics, "quick")
        self.assertNotIn("recognition_policy", quick)

    def test_saved_pipeline_preserves_nondefault_preprocessing(self):
        pipeline = TemporalFeaturePipeline(FeaturePipelineConfig(target_length=30, max_missing_gap=0))
        manifest = {
            "sequence_length": 30,
            "feature_schema": _temporal_feature_manifest(pipeline),
        }
        restored = temporal_pipeline_from_manifest(manifest)
        self.assertEqual(restored.config, pipeline.config)
        manifest["sequence_length"] = 15
        with self.assertRaisesRegex(ValueError, "sequence length"):
            temporal_pipeline_from_manifest(manifest)

    def test_malformed_probabilities_are_rejected(self):
        names = ["neutral", "unknown", self.config.visible_gestures[0]]
        for probabilities in ([[0.1, 0.2, float("nan")]], [[-0.1, 0.1, 1]], [[0, 0, 0]]):
            with self.subTest(probabilities=probabilities), self.assertRaises(HandVoxError):
                _predictions_with_recognition_policy(probabilities, names, self.config)

    def test_failed_result_remains_uninstallable(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = root / "failed"
            experiment.mkdir()
            (experiment / "model_manifest.json").write_text("{}", encoding="utf-8")
            (experiment / "metrics.json").write_text(
                json.dumps({"aggregate": {"passed": False}}), encoding="utf-8"
            )
            with patch("handvox.training_workflow.EXPERIMENTS_DIR", root):
                with self.assertRaisesRegex(HandVoxError, "ไม่ผ่านเกณฑ์"):
                    activate_experiment(experiment)

    def test_failed_model_offers_explicit_trial_action_and_external_evaluation(self):
        page = TrainingPage.__new__(TrainingPage)
        page._selected_experiment = Mock(return_value={"passed": False})
        page.experiment_detail_var = Mock()
        for name in ("external_evaluation_button", "open_report_button", "activate_button"):
            setattr(page, name, Mock())
        page._update_experiment_actions()
        page.external_evaluation_button.state.assert_called_once_with(["!disabled"])
        page.activate_button.state.assert_called_once_with(["!disabled"])
        page.activate_button.configure.assert_called_once_with(text="ติดตั้งแบบทดลอง")

    def test_explicit_trial_install_preserves_failed_scores_and_backs_up_model(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = root / "experiments" / "failed"
            deploy = root / "deploy"
            experiment.mkdir(parents=True)
            deploy.mkdir()
            visible = [{"name": "wave", "description": "wave", "color": [1, 2, 3]}]
            manifest = {
                "model_backend": "temporal_tcn", "sequence_length": 30,
                "visible_gestures": visible, "internal_classes": ["neutral", "unknown"],
                "feature_schema": _temporal_feature_manifest(TemporalFeaturePipeline()),
                "evaluation": {"accuracy": 0.5, "macro_f1": 0.4, "passed": False},
            }
            metrics = {"aggregate": {"passed": False}, "signers": ["person_01", "person_02"]}
            (experiment / "model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (experiment / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
            (experiment / "model.pt").write_bytes(b"new-model-verified-by-mock")
            (deploy / "gesture_model.pkl").write_bytes(b"old-model")
            (deploy / "custom_gestures.json").write_text(json.dumps(visible), encoding="utf-8")
            (deploy / "model_manifest.json").write_text('{"old": true}', encoding="utf-8")
            before_metrics = (experiment / "metrics.json").read_bytes()
            before_manifest = (experiment / "model_manifest.json").read_bytes()
            model = Mock(
                classes_=np.asarray(["wave", "neutral", "unknown"]),
                input_size=OUTPUT_FEATURE_COUNT, sequence_length=30,
                schema_version=FEATURE_SCHEMA_VERSION,
            )
            destinations = {
                "ROOT": root, "EXPERIMENTS_DIR": experiment.parent,
                "MODEL_FILE": deploy / "gesture_model.pkl",
                "TEMPORAL_MODEL_FILE": deploy / "gesture_model.pt",
                "LABEL_FILE": deploy / "gesture_labels.pkl",
                "MODEL_MANIFEST_FILE": deploy / "model_manifest.json",
                "CUSTOM_GESTURES_FILE": deploy / "custom_gestures.json",
                "PLANNED_GESTURES_FILE": deploy / "planned_gestures.json",
                "LEGACY_DATA_FILE": deploy / "gesture_sequences.npz",
            }
            with patch.multiple("handvox.training_workflow", **destinations), patch(
                "handvox.training_workflow.TemporalClassifier.load", return_value=model
            ):
                with self.assertRaisesRegex(HandVoxError, "ไม่ผ่านเกณฑ์"):
                    activate_experiment(experiment)
                backup = activate_experiment(experiment, allow_unvalidated_trial=True)
            installed = json.loads((deploy / "model_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(installed["deployment"]["status"], "experimental_unvalidated")
            self.assertIs(installed["evaluation"]["passed"], False)
            self.assertEqual((backup / "gesture_model.pkl").read_bytes(), b"old-model")
            self.assertEqual((backup / "model_manifest.json").read_text(encoding="utf-8"), '{"old": true}')
            self.assertEqual((experiment / "metrics.json").read_bytes(), before_metrics)
            self.assertEqual((experiment / "model_manifest.json").read_bytes(), before_manifest)
            self.assertEqual((deploy / "gesture_model.pt").read_bytes(), b"new-model-verified-by-mock")

    def test_failure_summary_shows_specific_recall_requirement(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "metrics.json").write_text(json.dumps({"aggregate": {"per_class": [
                {"class_name": "help", "recall": 0.72}
            ]}}), encoding="utf-8")
            (root / "training_config.snapshot.json").write_text(json.dumps({
                "visible_gestures": ["help"], "critical_gestures": ["help"],
                "acceptance": {"minimum_class_recall": 0.5, "minimum_critical_recall": 0.75}
            }), encoding="utf-8")
            summary = experiment_failure_summary({"path": root, "passed": False})
        self.assertIn("help: Recall 72.00% < 75%", summary)

    def test_external_summary_does_not_claim_partial_coverage_is_complete(self):
        summary = external_result_summary({
            "aggregate": {"accuracy": 0.8, "macro_f1": 0.4}, "missing_classes": ["unknown"]
        })
        self.assertIn("80.00%", summary)
        self.assertIn("ยังขาด 1 คลาส", summary)


if __name__ == "__main__":
    unittest.main()
