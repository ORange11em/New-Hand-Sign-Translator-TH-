"""ทดสอบกฎแผนเก็บข้อมูล 2 คน 4 รอบ และเป้าหมายราย session."""

from dataclasses import replace
import unittest

from handvox.errors import ConfigurationError
from handvox.training_config import load_training_config, session_clip_target


class TrainingConfigTests(unittest.TestCase):
    def test_default_plan_is_two_people_four_sessions_four_clips_each(self):
        config = load_training_config()
        self.assertEqual(len(config.collection.signers), 2)
        self.assertEqual(len(config.collection.sessions), 4)
        self.assertEqual(
            config.training.evaluation_strategy,
            "known_signers_session_holdout",
        )
        self.assertEqual(
            [session_clip_target(config, name) for name in config.collection.sessions],
            [4, 4, 4, 4],
        )
        self.assertEqual(config.expected_clip_count, 18 * 2 * 16)

    def test_duplicate_session_ids_are_rejected(self):
        config = load_training_config()
        invalid = replace(
            config,
            collection=replace(
                config.collection,
                sessions=("session_01", "session_01"),
            ),
        )
        with self.assertRaisesRegex(ConfigurationError, "session ห้ามซ้ำ"):
            invalid.validate()

    def test_unknown_session_has_clear_error(self):
        with self.assertRaisesRegex(ConfigurationError, "ไม่พบ session"):
            session_clip_target(load_training_config(), "session_99")

    def test_invalid_gpu_device_is_rejected_before_training(self):
        config = load_training_config()
        invalid = replace(
            config,
            training=replace(
                config.training,
                parameters={**config.training.parameters, "device": "gpu"},
            ),
        )
        with self.assertRaisesRegex(ConfigurationError, "cuda:N"):
            invalid.validate()


if __name__ == "__main__":
    unittest.main()
