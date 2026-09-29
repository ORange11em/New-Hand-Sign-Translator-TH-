"""ตรวจการวัดโมเดลที่ตรึงไว้ ผู้ทดสอบใหม่ และการป้องกันข้อมูลซ้ำกับชุดเทรน."""

from dataclasses import asdict
import json
from pathlib import Path
import pickle
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from sklearn.preprocessing import LabelEncoder

from body_features import FEATURE_COUNT
from handvox.dataset_v2 import ClipMetadata, DatasetV2Store
from handvox.errors import DataFileError
from handvox.external_evaluation import evaluate_external, get_training_signers
from handvox.feature_pipeline import (
    FEATURE_SCHEMA_VERSION,
    FeaturePipelineConfig,
    OUTPUT_FEATURE_COUNT,
    TemporalFeaturePipeline,
)


class SavedSVC:
    classes_ = np.asarray([2, 0, 1])
    n_features_in_ = 4 * FEATURE_COUNT

    def predict(self, features):
        return np.rint(features[:, 0]).astype(int)

    def predict_proba(self, features):
        return np.tile([0.6, 0.1, 0.3], (len(features), 1))

    def fit(self, *args, **kwargs):
        raise AssertionError("External evaluation must never fit a model")


class ExternalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.experiment = self.root / "experiment"
        self.experiment.mkdir()
        self.store = DatasetV2Store(self.root / "external")
        self.store.initialize()
        self.manifest = {
            "experiment_id": "saved_model",
            "model_backend": "svc",
            "model_artifact": "model.pkl",
            "sequence_length": 4,
            "feature_count": FEATURE_COUNT,
            "visible_gestures": [{"name": "wave"}],
            "internal_classes": ["neutral", "unknown"],
        }
        self.write_manifest()
        (self.experiment / "training_config.snapshot.json").write_text(
            json.dumps({"collection": {"signers": ["person_01", "person_02"]}}),
            encoding="utf-8",
        )
        (self.experiment / "metrics.json").write_text(
            json.dumps({"signers": ["person_01", "person_02"], "aggregate": {"passed": False}}),
            encoding="utf-8",
        )
        self.training_clips = np.full((2, 4, FEATURE_COUNT), -10, dtype=np.float32)
        self.save_training_archive()
        with (self.experiment / "model.pkl").open("wb") as target:
            pickle.dump(SavedSVC(), target)
        with (self.experiment / "labels.pkl").open("wb") as target:
            pickle.dump(LabelEncoder().fit(["wave", "neutral", "unknown"]), target)

    def write_manifest(self):
        (self.experiment / "model_manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def save_training_archive(self, signers=("person_01", "person_02")):
        np.savez_compressed(
            self.experiment / "training_sequences.npz",
            clips=self.training_clips,
            labels=np.asarray(["wave", "neutral"]),
            signer_ids=np.asarray(signers),
            session_ids=np.asarray(["session_01", "session_02"]),
        )

    def append(self, label="wave", signer="person_03", value=2, quality="accepted", sequence=None):
        clip_id = f"external_{len(self.store.records())}"
        relative_path = f"clips/{clip_id}.npy"
        values = np.full((4, FEATURE_COUNT), value, dtype=np.float32) if sequence is None else sequence
        np.save(self.store.root / relative_path, values, allow_pickle=False)
        record = ClipMetadata(
            clip_id=clip_id,
            gesture_name=label,
            signer_id=signer,
            session_id="new_session",
            recorded_at="2026-09-15T12:00:00+07:00",
            camera_index=0,
            quality=quality,
            sequence_file=relative_path,
            duration_frames=4,
            feature_count=FEATURE_COUNT,
        )
        self.store.append(record)
        return record

    def test_evaluates_saved_svc_and_preserves_original_artifacts(self):
        self.append()
        self.append(label="neutral", value=0)
        self.append(label="unknown", value=1, signer="person_04")
        before = {path.name: path.read_bytes() for path in self.experiment.iterdir()}
        report_dir, payload = evaluate_external(self.experiment, self.store)
        self.assertEqual(payload["aggregate"]["accuracy"], 1.0)
        self.assertEqual(payload["aggregate"]["macro_f1"], 1.0)
        self.assertEqual(payload["signers"], ["person_03", "person_04"])
        self.assertEqual(payload["classes"], ["wave", "neutral", "unknown"])
        self.assertEqual(payload["prediction_policy"], "raw_model_predictions")
        self.assertTrue(payload["coverage_complete"])
        self.assertFalse(payload["affects_installation"])
        self.assertNotIn("passed", payload["aggregate"])
        for filename, original in before.items():
            self.assertEqual((self.experiment / filename).read_bytes(), original)
        for filename in ("metrics.json", "predictions.csv", "per_class_metrics.csv", "confusion_matrix.csv", "report.md"):
            self.assertTrue((report_dir / filename).is_file())
        first_report = (report_dir / "metrics.json").read_bytes()
        other_dir, _ = evaluate_external(self.experiment, self.store)
        self.assertNotEqual(report_dir, other_dir)
        self.assertEqual((report_dir / "metrics.json").read_bytes(), first_report)

    def test_missing_classes_are_explicit_and_macro_includes_every_model_class(self):
        self.append()
        _, payload = evaluate_external(self.experiment, self.store)
        self.assertFalse(payload["coverage_complete"])
        self.assertEqual(payload["missing_classes"], ["neutral", "unknown"])
        self.assertAlmostEqual(payload["aggregate"]["macro_f1"], 1 / 3)
        self.assertEqual(payload["aggregate"]["accuracy"], 1.0)

    def test_applies_saved_policy_and_respects_probability_class_order(self):
        self.manifest["recognition_policy"] = {"minimum_confidence": 0.72, "minimum_probability_margin": 0.12}
        self.write_manifest()
        self.append()
        _, payload = evaluate_external(self.experiment, self.store)
        self.assertEqual(payload["clips"][0]["prediction"], "unknown")
        self.assertEqual(payload["aggregate"]["accuracy"], 0.0)
        self.assertEqual(payload["prediction_policy"], "saved_recognition_policy")

    def test_rejects_signers_from_every_source_of_training_provenance(self):
        self.save_training_archive(signers=("archived_person", "person_02"))
        self.assertEqual(get_training_signers(self.experiment), ("archived_person", "person_01", "person_02"))
        for signer in get_training_signers(self.experiment):
            with self.subTest(signer=signer):
                self.store.save_records([])
                self.append(signer=signer)
                with self.assertRaisesRegex(DataFileError, "ใช้เทรนแล้ว"):
                    evaluate_external(self.experiment, self.store)

    def test_rejects_training_clip_copied_with_new_person_id(self):
        self.append(sequence=self.training_clips[0].astype(np.float64))
        with self.assertRaisesRegex(DataFileError, "ซ้ำกับข้อมูลเทรน"):
            evaluate_external(self.experiment, self.store)
        self.assertFalse((self.experiment / "external_evaluations").exists())

    def test_rejects_duplicate_external_sequences(self):
        self.append()
        self.append()
        with self.assertRaisesRegex(DataFileError, "ซ้ำในชุดวัดผล"):
            evaluate_external(self.experiment, self.store)

    def test_rejects_incomplete_signer_metadata(self):
        self.save_training_archive(signers=("person_01", ""))
        self.append()
        with self.assertRaisesRegex(DataFileError, "ยืนยันข้อมูลผู้เทรน"):
            evaluate_external(self.experiment, self.store)

    def test_pending_and_rejected_records_are_excluded(self):
        self.append(signer="person_01", quality="pending")
        self.append(signer="person_02", quality="rejected")
        with self.assertRaisesRegex(DataFileError, "ยังไม่มีคลิป accepted"):
            evaluate_external(self.experiment, self.store)
        self.append()
        _, payload = evaluate_external(self.experiment, self.store)
        self.assertEqual(payload["accepted_clips"], 1)

    def test_rejects_invalid_sequences_and_missing_files(self):
        for values in (np.zeros((3, FEATURE_COUNT)), np.full((4, FEATURE_COUNT), np.nan)):
            with self.subTest(shape=values.shape):
                self.store.save_records([])
                self.append(sequence=values)
                with self.assertRaisesRegex(DataFileError, "ใช้วัดผลไม่ได้"):
                    evaluate_external(self.experiment, self.store)
        self.store.save_records([])
        record = self.append()
        (self.store.root / record.sequence_file).unlink()
        with self.assertRaisesRegex(DataFileError, "ใช้วัดผลไม่ได้"):
            evaluate_external(self.experiment, self.store)

    def test_provisional_includes_pending_without_changing_review_status(self):
        self.append(label="wave", value=2)
        self.append(label="neutral", value=0, quality="pending")
        self.append(label="unknown", value=1, quality="rejected")
        metadata_before = self.store.manifest.read_bytes()
        report_dir, payload = evaluate_external(self.experiment, self.store, include_pending=True)
        self.assertEqual(payload["evaluated_clips"], 2)
        self.assertEqual(payload["accepted_clips"], 1)
        self.assertEqual(payload["pending_clips"], 1)
        self.assertEqual(payload["evaluation_scope"], "external_new_signers_provisional")
        self.assertEqual(payload["evaluation_status"], "provisional_pending_review")
        self.assertEqual({row["quality"] for row in payload["clips"]}, {"accepted", "pending"})
        self.assertEqual(payload["per_session"]["new_session"]["evaluated_clips"], 2)
        self.assertEqual(self.store.manifest.read_bytes(), metadata_before)
        self.assertIn("เบื้องต้น", (report_dir / "report.md").read_text(encoding="utf-8"))
        _, reviewed = evaluate_external(self.experiment, self.store)
        self.assertEqual(reviewed["evaluated_clips"], 1)
        self.assertEqual(reviewed["evaluation_scope"], "external_new_signers")

    def test_provisional_still_rejects_pending_clip_from_training_person(self):
        self.append(signer="person_01", quality="pending")
        with self.assertRaisesRegex(DataFileError, "ใช้เทรนแล้ว"):
            evaluate_external(self.experiment, self.store, include_pending=True)

    def test_provisional_can_measure_all_pending_without_claiming_accepted(self):
        self.append(quality="pending")
        _, payload = evaluate_external(self.experiment, self.store, include_pending=True)
        self.assertEqual(payload["accepted_clips"], 0)
        self.assertEqual(payload["evaluated_clips"], 1)
        self.assertEqual(payload["pending_clips"], 1)

    def test_rejects_labels_that_model_does_not_know(self):
        self.append(label="new_gesture")
        with self.assertRaisesRegex(DataFileError, "ไม่มีในโมเดล"):
            evaluate_external(self.experiment, self.store)
        self.assertFalse((self.experiment / "external_evaluations").exists())

    def test_shared_dataset_excludes_other_model_classes_and_preserves_data(self):
        self.append()
        outside = self.append(label="new_gesture", value=3)
        self.append(label="unreviewed", quality="pending", value=4)
        self.append(label="rejected_gesture", quality="rejected", value=5)
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        report_dir, payload = evaluate_external(self.experiment, self.store)
        self.assertEqual(payload["evaluated_clips"], 1)
        self.assertEqual(payload["accepted_clips"], 1)
        self.assertEqual(payload["excluded_clip_count"], 1)
        self.assertEqual(payload["excluded_classes"], ["new_gesture"])
        self.assertEqual(payload["excluded_clips"][0]["clip_id"], outside.clip_id)
        self.assertEqual(payload["excluded_clips"][0]["reason"], "class_not_in_model")
        self.assertEqual(payload["class_scope"], "model_classes_only")
        self.assertEqual(payload["missing_classes"], ["neutral", "unknown"])
        self.assertAlmostEqual(payload["aggregate"]["macro_f1"], 1 / 3)
        self.assertEqual(payload["aggregate"]["accuracy"], 1.0)
        self.assertIn(outside.clip_id, (report_dir / "excluded_clips.csv").read_text(encoding="utf-8-sig"))
        report = (report_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("ข้าม 1 คลิป", report)
        self.assertIn("new_gesture", report)
        for path, original in before.items():
            self.assertEqual(path.read_bytes(), original)

    def test_quick_model_without_internal_classes_can_use_shared_dataset(self):
        self.manifest["internal_classes"] = []
        self.write_manifest()
        model = SavedSVC()
        model.classes_ = np.asarray([0])
        with (self.experiment / "model.pkl").open("wb") as target:
            pickle.dump(model, target)
        with (self.experiment / "labels.pkl").open("wb") as target:
            pickle.dump(LabelEncoder().fit(["wave"]), target)
        self.append(value=0)
        self.append(label="neutral", value=1)
        self.append(label="unknown", value=2)
        _, payload = evaluate_external(self.experiment, self.store)
        self.assertEqual(payload["classes"], ["wave"])
        self.assertEqual(payload["excluded_classes"], ["neutral", "unknown"])
        self.assertEqual(payload["excluded_clip_count"], 2)
        self.assertEqual(payload["evaluated_clips"], 1)
        self.assertEqual(payload["aggregate"]["accuracy"], 1.0)
        self.assertTrue(payload["coverage_complete"])

    def test_excluded_pending_clips_do_not_make_reviewed_results_provisional(self):
        self.append()
        self.append(label="other_model_class", quality="pending", value=3)
        _, payload = evaluate_external(self.experiment, self.store, include_pending=True)
        self.assertEqual(payload["excluded_clip_count"], 1)
        self.assertEqual(payload["pending_clips"], 0)
        self.assertEqual(payload["evaluation_scope"], "external_new_signers")

    def test_excluding_other_classes_does_not_bypass_training_data_checks(self):
        self.append(label="other_model_class", value=3)
        record = self.append(signer="person_01")
        with self.assertRaisesRegex(DataFileError, "ใช้เทรนแล้ว"):
            evaluate_external(self.experiment, self.store)
        self.store.save_records([item for item in self.store.records() if item.clip_id != record.clip_id])
        self.append(sequence=self.training_clips[0])
        with self.assertRaisesRegex(DataFileError, "ซ้ำกับข้อมูลเทรน"):
            evaluate_external(self.experiment, self.store)

    def test_tcn_uses_saved_feature_pipeline_and_only_cpu_inference(self):
        pipeline_config = FeaturePipelineConfig(target_length=4, max_missing_gap=0)
        self.manifest.update(
            model_backend="temporal_tcn",
            model_artifact="model.pt",
            feature_count=OUTPUT_FEATURE_COUNT,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            feature_schema={"schema_version": FEATURE_SCHEMA_VERSION, "pipeline_config": asdict(pipeline_config)},
        )
        self.write_manifest()
        (self.experiment / "model.pt").write_bytes(b"mocked TCN artifact")
        self.append()
        model = Mock(
            classes_=np.asarray(["wave", "neutral", "unknown"]),
            sequence_length=4,
            input_size=OUTPUT_FEATURE_COUNT,
            schema_version=FEATURE_SCHEMA_VERSION,
        )
        model.predict.return_value = np.asarray(["wave"])
        with patch("handvox.external_evaluation.TemporalClassifier.load", return_value=model) as loader:
            _, payload = evaluate_external(self.experiment, self.store)
        loader.assert_called_once_with((self.experiment / "model.pt").resolve(), device="cpu")
        model.fit.assert_not_called()
        expected = TemporalFeaturePipeline(pipeline_config).transform(
            np.full((4, FEATURE_COUNT), 2, dtype=np.float32), training=False
        )
        np.testing.assert_allclose(model.predict.call_args.args[0], expected[np.newaxis])
        self.assertEqual(payload["aggregate"]["accuracy"], 1.0)

    def test_external_store_must_be_separate_from_training_directory(self):
        with patch("handvox.external_evaluation.DATASET_V2_DIR", self.store.root):
            with self.assertRaisesRegex(DataFileError, "โฟลเดอร์แยก"):
                evaluate_external(self.experiment, self.store)


if __name__ == "__main__":
    unittest.main()
