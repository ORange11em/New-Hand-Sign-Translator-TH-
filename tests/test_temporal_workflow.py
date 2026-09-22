"""ทดสอบการเชื่อม TCN workflow โดยไม่ต้องมี PyTorch ในเครื่อง CI."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from body_features import FEATURE_COUNT
from handvox.dataset_v2 import ClipMetadata, DatasetV2Store
from handvox.feature_pipeline import (
    FEATURE_SCHEMA_VERSION,
    OUTPUT_FEATURE_COUNT,
    FeaturePipelineConfig,
    TemporalFeaturePipeline,
)
from handvox.training_config import build_quick_trial_config, load_training_config
from handvox.training_workflow import activate_experiment, train_quick_trial


class _FakeTemporalClassifier:
    """เลียน API หลัง fit เพื่อทดสอบ orchestration โดยไม่ปลอมผลจาก PyTorch."""

    def __init__(self, classes, prediction):
        self.classes_ = np.asarray(classes, dtype=str)
        self.prediction = prediction
        self.device_used_ = "cpu"
        self.device_selection_ = SimpleNamespace(device_name="CPU")
        self.n_epochs_ = 2
        self.best_epoch_ = 1
        self.input_size = OUTPUT_FEATURE_COUNT
        self.sequence_length = 30
        self.schema_version = FEATURE_SCHEMA_VERSION

    def predict(self, values):
        return np.asarray([self.prediction] * len(values), dtype=str)

    def save(self, path, metadata=None):
        Path(path).write_bytes(b"fake-temporal-state")
        return Path(path)

    def artifact_metadata(self):
        return {
            "classes": self.classes_.tolist(),
            "input_size": self.input_size,
            "sequence_length": self.sequence_length,
            "device_used": self.device_used_,
            "schema_version": self.schema_version,
        }


class TemporalWorkflowTests(unittest.TestCase):
    def test_quick_trial_uses_metadata_less_base_as_training_only(self):
        base_config = load_training_config()
        active = base_config.visible_gestures[:2]
        target = base_config.visible_gestures[2]
        config = build_quick_trial_config(
            target,
            config=base_config,
            active_names=active,
        )
        config = replace(
            config,
            training=replace(
                config.training,
                algorithm="TCN",
                parameters={"augmentation_copies": 0},
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = DatasetV2Store(root / "dataset")
            base_file = root / "gesture_sequences.npz"
            base_clips = np.zeros((4, 30, FEATURE_COUNT), dtype=np.float32)
            np.savez_compressed(
                base_file,
                clips=base_clips,
                labels=np.asarray([active[0], active[0], active[1], active[1]]),
            )
            for index in range(4):
                relative = Path("clips") / f"target-{index}.npy"
                sequence_path = store.resolve_data_path(relative)
                sequence_path.parent.mkdir(parents=True, exist_ok=True)
                np.save(
                    sequence_path,
                    np.full((30, FEATURE_COUNT), index + 1, dtype=np.float32),
                )
                store.append(
                    ClipMetadata(
                        clip_id=f"target-{index}",
                        gesture_name=target,
                        signer_id=f"person_{index // 2 + 1:02d}",
                        session_id=f"session_{index % 2 + 1:02d}",
                        recorded_at=datetime.now(timezone.utc).isoformat(),
                        camera_index=0,
                        clip_number=index + 1,
                        quality="accepted",
                        sequence_file=relative.as_posix(),
                        duration_frames=30,
                        feature_count=FEATURE_COUNT,
                    )
                )

            fake = _FakeTemporalClassifier(config.visible_gestures, target)
            pipeline = TemporalFeaturePipeline(FeaturePipelineConfig(target_length=30))
            with (
                patch("handvox.training_workflow.LEGACY_DATA_FILE", base_file),
                patch("handvox.training_workflow._reference_items", return_value=[]),
                patch(
                    "handvox.training_workflow._temporal_training_components",
                    return_value=(pipeline, 0, {}),
                ),
                patch(
                    "handvox.training_workflow._fit_temporal_classifier",
                    return_value=fake,
                ),
                patch("handvox.training_workflow._write_plots"),
            ):
                experiment, payload = train_quick_trial(
                    config,
                    store=store,
                    output_root=root / "experiments",
                )

            self.assertEqual(payload["model_backend"], "temporal_tcn")
            self.assertEqual(payload["evaluation_scope"], "new_target_only_grouped_holdout")
            self.assertFalse(payload["research_grade"])
            self.assertFalse(payload["base_group_metadata_complete"])
            self.assertTrue(payload["evaluation_limitations"])
            self.assertTrue((experiment / "model.pt").exists())
            self.assertTrue((experiment / "training_sequences.npz").exists())
            with np.load(experiment / "training_sequences.npz", allow_pickle=False) as data:
                self.assertTrue(np.all(data["signer_ids"][:4] == ""))
                self.assertTrue(np.all(~data["group_metadata_available"][:4]))
                self.assertTrue(np.all(data["group_metadata_available"][4:]))

    def test_activate_temporal_artifact_installs_pt_after_schema_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiments = root / "experiments"
            experiment = experiments / "tcn-result"
            deploy = root / "deploy"
            experiment.mkdir(parents=True)
            deploy.mkdir()
            visible = [
                {"name": "สวัสดี", "description": "สวัสดี", "color": [1, 2, 3]}
            ]
            manifest = {
                "schema_version": 1,
                "model_backend": "temporal_tcn",
                "model_artifact": "model.pt",
                "sequence_length": 30,
                "feature_schema": {
                    "schema_version": FEATURE_SCHEMA_VERSION,
                    "output_feature_count": OUTPUT_FEATURE_COUNT,
                    "pipeline_config": {"trim_motion": False},
                },
                "visible_gestures": visible,
                "internal_classes": ["neutral", "unknown"],
            }
            metrics = {"aggregate": {"passed": True}}
            (experiment / "model_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            (experiment / "metrics.json").write_text(
                json.dumps(metrics), encoding="utf-8"
            )
            (experiment / "model.pt").write_bytes(b"validated-by-mock")
            loaded = _FakeTemporalClassifier(
                ["สวัสดี", "neutral", "unknown"], "สวัสดี"
            )
            temporal_destination = deploy / "gesture_model.pt"
            with (
                patch("handvox.training_workflow.EXPERIMENTS_DIR", experiments),
                patch("handvox.training_workflow.ROOT", root),
                patch("handvox.training_workflow.MODEL_FILE", deploy / "gesture_model.pkl"),
                patch("handvox.training_workflow.TEMPORAL_MODEL_FILE", temporal_destination),
                patch("handvox.training_workflow.LABEL_FILE", deploy / "gesture_labels.pkl"),
                patch("handvox.training_workflow.MODEL_MANIFEST_FILE", deploy / "model_manifest.json"),
                patch("handvox.training_workflow.CUSTOM_GESTURES_FILE", deploy / "custom_gestures.json"),
                patch("handvox.training_workflow.PLANNED_GESTURES_FILE", deploy / "planned_gestures.json"),
                patch("handvox.training_workflow.LEGACY_DATA_FILE", deploy / "gesture_sequences.npz"),
                patch("handvox.training_workflow.TemporalClassifier.load", return_value=loaded),
            ):
                backup = activate_experiment(experiment)

            self.assertTrue(backup.exists())
            self.assertEqual(temporal_destination.read_bytes(), b"validated-by-mock")
            deployed_manifest = json.loads(
                (deploy / "model_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(deployed_manifest["model_backend"], "temporal_tcn")


if __name__ == "__main__":
    unittest.main()
