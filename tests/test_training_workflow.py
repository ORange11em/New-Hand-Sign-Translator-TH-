"""ทดสอบ preflight ตัวชี้วัด เกณฑ์ผ่าน และ experiment ด้วยข้อมูลสังเคราะห์."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from body_features import FEATURE_COUNT
from handvox.dataset_v2 import ClipMetadata, DatasetV2Store
from handvox.errors import ConfigurationError
from handvox.training_config import load_training_config
from handvox.training_workflow import (
    _acceptance_result,
    _metric_payload,
    preflight,
    save_preflight_report,
    train_and_evaluate,
)


class TrainingWorkflowTests(unittest.TestCase):
    def test_training_plan_has_sixteen_visible_and_neutral(self):
        config = load_training_config()
        self.assertEqual(len(config.visible_gestures), 16)
        self.assertEqual(len(config.all_classes), 17)
        self.assertIn("neutral", config.internal_classes)
        self.assertEqual(config.expected_clip_count, 340)

    def test_config_rejects_wrong_visible_class_count(self):
        config = load_training_config()
        invalid = replace(config, visible_gestures=config.visible_gestures[:-1])
        with self.assertRaises(ConfigurationError):
            invalid.validate()

    def test_empty_dataset_is_not_ready_and_report_is_saved(self):
        config = load_training_config()
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetV2Store(Path(directory) / "dataset")
            report = preflight(config, store)
            self.assertFalse(report.ready)
            self.assertTrue(any(item.code == "dataset_empty" for item in report.items))
            output = Path(directory) / "preflight.json"
            save_preflight_report(report, output)
            self.assertIn('"ready": false', output.read_text(encoding="utf-8"))

    def test_metric_payload_records_per_class_and_confusion_matrix(self):
        metrics = _metric_payload(
            [0, 0, 1, 1],
            [0, 1, 1, 1],
            [0, 1],
            ["a", "b"],
        )
        self.assertEqual(metrics["accuracy"], 0.75)
        self.assertEqual(metrics["confusion_matrix"], [[1, 1], [0, 2]])
        self.assertEqual([row["class_name"] for row in metrics["per_class"]], ["a", "b"])

    def test_acceptance_finds_neutral_by_metric_class_order(self):
        config = load_training_config()
        class_names = ["neutral", *config.visible_gestures]
        size = len(class_names)
        metrics = {
            "accuracy": 1.0,
            "macro_f1": 1.0,
            "per_class": [
                {"class_name": name, "recall": 1.0} for name in class_names
            ],
            "confusion_matrix": [
                [1 if row == column else 0 for column in range(size)]
                for row in range(size)
            ],
        }
        passed, checks, neutral_rate = _acceptance_result(config, metrics)
        self.assertTrue(passed)
        self.assertTrue(all(checks.values()))
        self.assertEqual(neutral_rate, 0.0)

    def test_synthetic_workflow_creates_documentation_artifacts(self):
        base_config = load_training_config()
        config = replace(
            base_config,
            collection=replace(
                base_config.collection,
                target_clips_per_signer_per_class=2,
                minimum_accepted_per_signer_per_class=2,
            ),
            training=replace(
                base_config.training,
                parameters={
                    "kernel": "linear",
                    "C": 1.0,
                    "probability": False,
                    "class_weight": "balanced",
                },
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = DatasetV2Store(root / "dataset")
            generator = np.random.default_rng(42)
            clip_number = 0
            for class_index, gesture_name in enumerate(config.all_classes):
                for signer_index, signer_id in enumerate(config.collection.signers):
                    for session_id in config.collection.sessions:
                        clip_number += 1
                        sequence = np.full(
                            (config.collection.sequence_length, FEATURE_COUNT),
                            class_index * 10.0 + signer_index * 0.01,
                            dtype=np.float32,
                        )
                        sequence += generator.normal(0, 0.001, sequence.shape).astype(np.float32)
                        relative = Path("clips") / f"clip-{clip_number}.npy"
                        path = store.resolve_data_path(relative)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        np.save(path, sequence)
                        store.append(
                            ClipMetadata(
                                clip_id=f"clip-{clip_number}",
                                gesture_name=gesture_name,
                                signer_id=signer_id,
                                session_id=session_id,
                                recorded_at=datetime.now(timezone.utc).isoformat(),
                                camera_index=0,
                                clip_number=clip_number,
                                quality="accepted",
                                sequence_file=relative.as_posix(),
                                duration_frames=config.collection.sequence_length,
                                feature_count=FEATURE_COUNT,
                            )
                        )
            with patch("handvox.training_workflow._reference_items", return_value=[]):
                experiment_dir, payload = train_and_evaluate(
                    config=config,
                    store=store,
                    output_root=root / "experiments",
                )
            self.assertTrue(payload["aggregate"]["passed"])
            for filename in (
                "metrics.json",
                "summary.csv",
                "per_class_metrics.csv",
                "fold_summary.csv",
                "confusion_matrix.csv",
                "confusion_matrix.png",
                "per_class_f1.png",
                "report.md",
                "model.pkl",
                "labels.pkl",
            ):
                self.assertTrue((experiment_dir / filename).exists(), filename)
            self.assertTrue((root / "experiments" / "experiment_index.csv").exists())


if __name__ == "__main__":
    unittest.main()
