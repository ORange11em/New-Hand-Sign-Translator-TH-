"""ทดสอบ Lightweight TCN, GPU fallback และ artifact ของ HandVox."""

from pathlib import Path
import tempfile
import unittest

import numpy as np

from handvox.temporal_model import (
    TORCH_AVAILABLE,
    TemporalClassifier,
    TorchUnavailableError,
    is_torch_available,
    select_device,
)


class TemporalModelAvailabilityTests(unittest.TestCase):
    def test_module_is_safe_to_import_without_torch(self):
        self.assertEqual(is_torch_available(), TORCH_AVAILABLE)
        selection = select_device("auto")
        if TORCH_AVAILABLE:
            self.assertIn(selection.selected.split(":", 1)[0], {"cpu", "cuda"})
        else:
            self.assertEqual(selection.selected, "unavailable")
            self.assertTrue(selection.fallback_reason)

    @unittest.skipIf(TORCH_AVAILABLE, "ใช้ตรวจข้อความเมื่อไม่มี PyTorch เท่านั้น")
    def test_fit_explains_that_torch_is_missing(self):
        classifier = TemporalClassifier(
            input_size=3,
            sequence_length=4,
            max_epochs=1,
            device="auto",
        )
        with self.assertRaisesRegex(TorchUnavailableError, "PyTorch"):
            classifier.fit(
                np.zeros((2, 4, 3), dtype=np.float32),
                np.asarray(["a", "b"]),
            )


@unittest.skipUnless(TORCH_AVAILABLE, "เครื่องทดสอบนี้ยังไม่มี PyTorch")
class TemporalClassifierTests(unittest.TestCase):
    @staticmethod
    def _tiny_dataset(seed=21):
        """สร้างสองคลาสที่ต่างกันทั้งรูป feature และทิศทางตามเวลา."""

        rng = np.random.default_rng(seed)
        sample_count = 32
        sequence_length = 8
        input_size = 4
        sequences = rng.normal(
            0.0,
            0.05,
            size=(sample_count, sequence_length, input_size),
        ).astype(np.float32)
        labels = np.asarray(
            ["left"] * (sample_count // 2) + ["right"] * (sample_count // 2)
        )
        progress = np.linspace(-1.0, 1.0, sequence_length, dtype=np.float32)
        sequences[: sample_count // 2, :, 0] += progress
        sequences[: sample_count // 2, :, 1] -= progress
        sequences[sample_count // 2 :, :, 0] -= progress
        sequences[sample_count // 2 :, :, 1] += progress
        return sequences, labels

    @staticmethod
    def _classifier(**overrides):
        settings = {
            "input_size": 4,
            "sequence_length": 8,
            "hidden_channels": (8,),
            "dropout": 0.0,
            "learning_rate": 0.02,
            "batch_size": 8,
            "max_epochs": 30,
            "patience": 6,
            "min_delta": 1e-5,
            "validation_fraction": 0.25,
            "random_state": 7,
            "device": "cpu",
            "schema_version": "test-landmarks-v2",
        }
        settings.update(overrides)
        return TemporalClassifier(**settings)

    def test_fit_predict_proba_and_balanced_class_weights(self):
        sequences, labels = self._tiny_dataset()
        # ทำคลาสไม่สมดุล เพื่อยืนยันว่า loss ไม่ใช้ weight เท่ากันโดยไม่ตั้งใจ
        selected = np.r_[0:16, 16:24]
        classifier = self._classifier().fit(sequences[selected], labels[selected])

        probabilities = classifier.predict_proba(sequences)
        predictions = classifier.predict(sequences)
        self.assertEqual(probabilities.shape, (32, 2))
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, atol=1e-5)
        self.assertGreaterEqual(float(np.mean(predictions == labels)), 0.90)
        self.assertEqual(classifier.class_weights_.shape, (2,))
        self.assertNotAlmostEqual(
            float(classifier.class_weights_[0]),
            float(classifier.class_weights_[1]),
        )
        self.assertGreaterEqual(classifier.best_epoch_, 1)
        self.assertLessEqual(classifier.n_epochs_, classifier.max_epochs)

    def test_same_seed_produces_same_cpu_probabilities(self):
        sequences, labels = self._tiny_dataset()
        first = self._classifier(max_epochs=8, patience=8).fit(sequences, labels)
        second = self._classifier(max_epochs=8, patience=8).fit(sequences, labels)
        np.testing.assert_allclose(
            first.predict_proba(sequences),
            second.predict_proba(sequences),
            rtol=0,
            atol=1e-6,
        )

    def test_save_and_load_preserve_predictions_and_metadata(self):
        sequences, labels = self._tiny_dataset()
        classifier = self._classifier(max_epochs=12, patience=4).fit(
            sequences, labels
        )
        expected = classifier.predict_proba(sequences[:5])

        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "temporal_model.pt"
            saved_path = classifier.save(
                artifact, metadata={"experiment_id": "tiny-test"}
            )
            restored = TemporalClassifier.load(saved_path, device="cpu")

            np.testing.assert_allclose(
                restored.predict_proba(sequences[:5]), expected, rtol=0, atol=1e-6
            )
            self.assertEqual(restored.classes_.tolist(), classifier.classes_.tolist())
            self.assertEqual(restored.input_size, 4)
            self.assertEqual(restored.sequence_length, 8)
            self.assertEqual(restored.schema_version, "test-landmarks-v2")
            self.assertEqual(restored.device_used_, "cpu")
            self.assertEqual(
                restored.artifact_metadata_["custom"]["experiment_id"],
                "tiny-test",
            )

    def test_cuda_request_falls_back_to_cpu_when_cuda_is_unavailable(self):
        selection = select_device("cuda")
        if not selection.accelerator_available:
            self.assertEqual(selection.selected, "cpu")
            self.assertTrue(selection.fallback_reason)
        else:
            self.assertTrue(selection.selected.startswith("cuda"))

    def test_rejects_wrong_sequence_shape(self):
        sequences, labels = self._tiny_dataset()
        with self.assertRaisesRegex(ValueError, "shape"):
            self._classifier(max_epochs=1).fit(sequences[:, :-1], labels)


if __name__ == "__main__":
    unittest.main()
