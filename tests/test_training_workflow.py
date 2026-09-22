"""ทดสอบ preflight ตัวชี้วัด เกณฑ์ผ่าน และ experiment ด้วยข้อมูลสังเคราะห์."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from body_features import FEATURE_COUNT
from handvox.dataset_v2 import ClipMetadata, DatasetV2Store
from handvox.errors import ConfigurationError, HandVoxError
from handvox.training_config import load_training_config
from handvox.training_config import (
    build_incremental_training_config,
    build_quick_trial_config,
    incremental_targets,
)
from handvox.training_workflow import (
    _acceptance_result,
    _ensure_no_active_gesture_regression,
    _grouped_session_holdout,
    _known_signers_session_holdout_folds,
    _metric_payload,
    _predictions_with_recognition_policy,
    activate_experiment,
    preflight,
    quick_trial_readiness,
    save_preflight_report,
    train_and_evaluate,
    train_quick_trial,
)


class TrainingWorkflowTests(unittest.TestCase):
    def test_seed_config_has_visible_words_and_neutral(self):
        config = load_training_config()
        self.assertGreater(len(config.visible_gestures), 0)
        self.assertEqual(
            len(config.all_classes),
            len(config.visible_gestures) + len(config.internal_classes),
        )
        self.assertIn("neutral", config.internal_classes)
        self.assertIn("unknown", config.internal_classes)
        self.assertGreater(config.expected_clip_count, 0)

    def test_config_allows_any_nonempty_starting_vocabulary(self):
        config = load_training_config()
        smaller = replace(config, visible_gestures=config.visible_gestures[:-1])
        self.assertIs(smaller.validate(), smaller)
        invalid = replace(config, visible_gestures=())
        with self.assertRaises(ConfigurationError):
            invalid.validate()

    def test_incremental_round_contains_active_words_target_and_neutral(self):
        config = load_training_config()
        active = config.visible_gestures[:4]
        target = config.visible_gestures[4]
        round_config = build_incremental_training_config(
            target, config=config, active_names=active
        )
        self.assertEqual(round_config.visible_gestures, (*active, target))
        self.assertEqual(round_config.target_gesture, target)
        self.assertTrue(
            {"neutral", "unknown"}.issubset(round_config.internal_classes)
        )
        self.assertEqual(
            round_config.expected_clip_count,
            len(round_config.all_classes)
            * len(round_config.collection.signers)
            * round_config.collection.target_clips_per_signer_per_class,
        )

    def test_incremental_targets_exclude_active_words(self):
        config = load_training_config()
        active = config.visible_gestures[:4]
        self.assertEqual(
            incremental_targets(config, active), config.visible_gestures[4:]
        )

    def test_incremental_round_rejects_already_active_target(self):
        config = load_training_config()
        target = config.visible_gestures[0]
        with self.assertRaises(ConfigurationError):
            build_incremental_training_config(
                target, config=config, active_names=(target,)
            )

    def test_planned_word_can_extend_model_without_dropping_active_words(self):
        config = load_training_config()
        target = "นอน"
        round_config = build_incremental_training_config(
            target,
            config=config,
            active_names=config.visible_gestures,
            planned_names=(target,),
        )
        self.assertEqual(
            round_config.visible_gestures,
            (*config.visible_gestures, target),
        )
        self.assertEqual(round_config.target_gesture, target)
        self.assertEqual(
            incremental_targets(
                config,
                config.visible_gestures,
                planned_names=(target,),
            ),
            (target,),
        )

    def test_unplanned_word_cannot_become_training_target(self):
        config = load_training_config()
        with self.assertRaises(ConfigurationError):
            build_incremental_training_config(
                "คำที่ไม่ได้บันทึก",
                config=config,
                active_names=config.visible_gestures,
                planned_names=("นอน",),
            )

    def test_old_experiment_cannot_remove_an_active_gesture(self):
        with tempfile.TemporaryDirectory() as directory:
            active_file = Path(directory) / "custom_gestures.json"
            active_file.write_text(
                json.dumps(
                    [
                        {"name": "น้ำ", "description": "น้ำ", "color": [1, 2, 3]},
                        {"name": "กิน", "description": "กิน", "color": [1, 2, 3]},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(HandVoxError, "กิน"):
                _ensure_no_active_gesture_regression(
                    [{"name": "น้ำ"}], active_file
                )

    def test_quick_trial_config_reuses_active_words_without_neutral(self):
        config = load_training_config()
        active = config.visible_gestures[:4]
        target = config.visible_gestures[4]
        quick = build_quick_trial_config(
            target, config=config, active_names=active
        )
        self.assertEqual(quick.visible_gestures, (*active, target))
        self.assertEqual(quick.internal_classes, ())
        self.assertEqual(quick.mode, "quick_trial")
        self.assertEqual(
            quick.training.evaluation_strategy,
            "grouped_signer_session_holdout",
        )

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

    def test_recognition_policy_rejects_uncertain_visible_prediction(self):
        config = replace(
            load_training_config(),
            visible_gestures=("a",),
            internal_classes=("neutral", "unknown"),
            critical_gestures=(),
        ).validate()

        predictions = _predictions_with_recognition_policy(
            np.asarray(
                [
                    [0.10, 0.30, 0.60],
                    [0.05, 0.15, 0.80],
                    [0.80, 0.10, 0.10],
                ]
            ),
            ["neutral", "unknown", "a"],
            config,
        )

        self.assertEqual(predictions.tolist(), ["unknown", "a", "neutral"])

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

    def test_incremental_round_without_critical_word_can_pass(self):
        base_config = load_training_config()
        config = build_incremental_training_config(
            base_config.visible_gestures[4],
            config=base_config,
            active_names=base_config.visible_gestures[:4],
        )
        class_names = list(config.all_classes)
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
        self.assertTrue(checks["minimum_critical_recall"])
        self.assertEqual(neutral_rate, 0.0)

    def test_grouped_session_holdout_has_no_group_leakage(self):
        labels = np.asarray(["a", "b"] * 4)
        signers = np.asarray(
            ["person_01"] * 4 + ["person_02"] * 4
        )
        sessions = np.asarray(
            ["session_01", "session_01", "session_02", "session_02"] * 2
        )
        train_indices, test_indices, groups = _grouped_session_holdout(
            labels,
            signers,
            sessions,
            test_fraction=0.25,
            random_seed=42,
        )
        self.assertFalse(
            set(groups[train_indices]).intersection(groups[test_indices])
        )
        self.assertEqual(set(labels[train_indices]), {"a", "b"})
        self.assertEqual(set(labels[test_indices]), {"a", "b"})

    def test_known_signer_holdout_keeps_both_people_in_train_and_test(self):
        labels = np.asarray(["a", "b"] * 8)
        signers = np.asarray(["person_01"] * 8 + ["person_02"] * 8)
        sessions = np.asarray(
            ["session_01", "session_01", "session_02", "session_02"] * 4
        )

        train_indices, test_indices, groups = _grouped_session_holdout(
            labels,
            signers,
            sessions,
            test_fraction=0.25,
            random_seed=42,
            require_all_signers=True,
        )

        self.assertFalse(
            set(groups[train_indices]).intersection(groups[test_indices])
        )
        self.assertEqual(set(signers[train_indices]), {"person_01", "person_02"})
        self.assertEqual(set(signers[test_indices]), {"person_01", "person_02"})

    def test_known_signer_session_folds_test_each_clip_once(self):
        config = load_training_config()
        labels = np.asarray(list(config.all_classes) * 8)
        signers = np.asarray(
            [signer for signer in config.collection.signers for _ in range(4 * len(config.all_classes))]
        )
        sessions = np.asarray(
            [
                session
                for _ in config.collection.signers
                for session in config.collection.sessions
                for _ in config.all_classes
            ]
        )

        folds, groups = _known_signers_session_holdout_folds(
            config, labels, signers, sessions
        )

        self.assertEqual(len(folds), len(config.collection.sessions))
        tested = np.concatenate([fold["test_indices"] for fold in folds])
        self.assertEqual(set(tested.tolist()), set(range(len(labels))))
        for fold in folds:
            train_groups = set(groups[fold["train_indices"]])
            validation_groups = set(groups[fold["validation_indices"]])
            test_groups = set(groups[fold["test_indices"]])
            self.assertFalse(train_groups.intersection(validation_groups))
            self.assertFalse(train_groups.intersection(test_groups))
            self.assertFalse(validation_groups.intersection(test_groups))

    def test_grouped_session_holdout_rejects_class_with_only_one_group(self):
        with self.assertRaisesRegex(HandVoxError, "ไม่ถึง 2 กลุ่ม"):
            _grouped_session_holdout(
                labels=np.asarray(["a", "a", "b", "b"]),
                signer_ids=np.asarray(
                    ["person_01", "person_02", "person_01", "person_01"]
                ),
                session_ids=np.asarray(
                    ["session_01", "session_02", "session_01", "session_01"]
                ),
            )

    def test_quick_readiness_warns_about_base_without_group_metadata(self):
        base_config = load_training_config()
        active = base_config.visible_gestures[:4]
        target = base_config.visible_gestures[4]
        config = build_quick_trial_config(
            target, config=base_config, active_names=active
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_file = root / "gesture_sequences.npz"
            clips = np.zeros(
                (
                    len(active),
                    config.collection.sequence_length,
                    FEATURE_COUNT,
                ),
                dtype=np.float32,
            )
            np.savez_compressed(base_file, clips=clips, labels=np.asarray(active))
            with (
                patch("handvox.training_workflow.LEGACY_DATA_FILE", base_file),
                patch("handvox.training_workflow._reference_items", return_value=[]),
            ):
                report = quick_trial_readiness(
                    config, DatasetV2Store(root / "dataset")
                )
        metadata_item = next(
            item
            for item in report.items
            if item.code == "base_group_metadata_missing"
        )
        self.assertEqual(metadata_item.status, "warning")

    def test_quick_trial_trains_from_base_and_new_word(self):
        base_config = load_training_config()
        active = base_config.visible_gestures[:4]
        target = base_config.visible_gestures[4]
        config = build_quick_trial_config(
            target, config=base_config, active_names=active
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = DatasetV2Store(root / "dataset")
            generator = np.random.default_rng(123)
            base_clips = []
            base_labels = []
            base_signers = []
            base_sessions = []
            for class_index, name in enumerate(active):
                for sample in range(8):
                    sequence = np.full(
                        (config.collection.sequence_length, FEATURE_COUNT),
                        class_index * 8.0,
                        dtype=np.float32,
                    )
                    sequence += generator.normal(0, 0.001, sequence.shape).astype(np.float32)
                    base_clips.append(sequence)
                    base_labels.append(name)
                    group_index = sample % 4
                    base_signers.append(config.collection.signers[group_index // 2])
                    base_sessions.append(config.collection.sessions[group_index % 2])
            base_file = root / "gesture_sequences.npz"
            np.savez_compressed(
                base_file,
                clips=np.asarray(base_clips),
                labels=np.asarray(base_labels),
                signer_ids=np.asarray(base_signers),
                session_ids=np.asarray(base_sessions),
            )
            for sample in range(8):
                relative = Path("clips") / f"target-{sample}.npy"
                path = store.resolve_data_path(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                sequence = np.full(
                    (config.collection.sequence_length, FEATURE_COUNT),
                    40.0,
                    dtype=np.float32,
                )
                sequence += generator.normal(0, 0.001, sequence.shape).astype(np.float32)
                np.save(path, sequence)
                store.append(
                    ClipMetadata(
                        clip_id=f"target-{sample}",
                        gesture_name=target,
                        signer_id=config.collection.signers[(sample % 4) // 2],
                        session_id=config.collection.sessions[(sample % 4) % 2],
                        recorded_at=datetime.now(timezone.utc).isoformat(),
                        camera_index=0,
                        clip_number=sample + 1,
                        quality="accepted",
                        sequence_file=relative.as_posix(),
                        duration_frames=config.collection.sequence_length,
                        feature_count=FEATURE_COUNT,
                    )
                )
            with (
                patch("handvox.training_workflow.LEGACY_DATA_FILE", base_file),
                patch("handvox.training_workflow._reference_items", return_value=[]),
            ):
                readiness = quick_trial_readiness(config, store)
                self.assertTrue(readiness.ready)
                experiment_dir, payload = train_quick_trial(
                    config, store=store, output_root=root / "experiments"
                )
            self.assertEqual(payload["mode"], "quick_trial")
            self.assertEqual(
                payload["evaluation_strategy"], "grouped_signer_session_holdout"
            )
            self.assertEqual(payload["new_target_clips"], 8)
            self.assertTrue(payload["aggregate"]["passed"])
            fold = payload["folds"][0]
            self.assertFalse(
                set(fold["train_session_groups"]).intersection(
                    fold["test_session_groups"]
                )
            )
            self.assertFalse(fold["group_leakage_detected"])
            self.assertTrue((experiment_dir / "training_sequences.npz").exists())
            self.assertEqual(payload["model_backend"], "temporal_tcn")
            self.assertTrue((experiment_dir / "model.pt").exists())
            with patch("handvox.training_workflow.EXPERIMENTS_DIR", root / "experiments"):
                with self.assertRaises(HandVoxError):
                    activate_experiment(experiment_dir)
            deploy = root / "deployed"
            deploy.mkdir()
            deployed_model = deploy / "gesture_model.pkl"
            deployed_temporal = deploy / "gesture_model.pt"
            deployed_labels = deploy / "gesture_labels.pkl"
            deployed_manifest = deploy / "model_manifest.json"
            deployed_custom = deploy / "custom_gestures.json"
            deployed_planned = deploy / "planned_gestures.json"
            deployed_sequences = deploy / "gesture_sequences.npz"
            with (
                patch("handvox.training_workflow.EXPERIMENTS_DIR", root / "experiments"),
                patch("handvox.training_workflow.ROOT", root),
                patch("handvox.training_workflow.MODEL_FILE", deployed_model),
                patch("handvox.training_workflow.LABEL_FILE", deployed_labels),
                patch("handvox.training_workflow.MODEL_MANIFEST_FILE", deployed_manifest),
                patch("handvox.training_workflow.CUSTOM_GESTURES_FILE", deployed_custom),
                patch("handvox.training_workflow.PLANNED_GESTURES_FILE", deployed_planned),
                patch("handvox.training_workflow.LEGACY_DATA_FILE", deployed_sequences),
            ):
                backup = activate_experiment(
                    experiment_dir, allow_quick_trial=True
                )
            self.assertTrue(backup.exists())
            self.assertTrue(deployed_temporal.exists())
            with np.load(deployed_sequences, allow_pickle=False) as data:
                self.assertEqual(set(data["labels"].tolist()), set((*active, target)))
                self.assertEqual(len(data["signer_ids"]), len(data["labels"]))
                self.assertEqual(len(data["session_ids"]), len(data["labels"]))

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
                algorithm="SVC",
                parameters={
                    "kernel": "linear",
                    "C": 1.0,
                    "probability": True,
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
            self.assertIsInstance(payload["aggregate"]["passed"], bool)
            self.assertEqual(
                payload["aggregate"]["passed"],
                all(payload["aggregate"]["acceptance_checks"].values()),
            )
            self.assertEqual(payload["evaluation_group_key"], "signer_id+session_id")
            for fold in payload["folds"]:
                self.assertEqual(fold["train_clips"], fold["test_clips"] * 3)
                self.assertFalse(
                    set(fold["train_session_groups"]).intersection(
                        fold["test_session_groups"]
                    )
                )
                self.assertFalse(fold["group_leakage_detected"])
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
