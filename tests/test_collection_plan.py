"""ทดสอบเป้าหมายรายรอบและคำแนะนำสำหรับคลาสภายในของหน้าถ่ายคลิป."""

import unittest

from collect_dataset_v2 import capture_instruction, session_target
from handvox.training_config import load_training_config


class CollectionPlanTests(unittest.TestCase):
    def test_sixteen_clips_are_split_into_four_equal_sessions(self):
        config = load_training_config()
        self.assertEqual(
            [session_target(config, session) for session in config.collection.sessions],
            [4, 4, 4, 4],
        )

    def test_internal_classes_have_clear_capture_instructions(self):
        self.assertIn("พักมือ", capture_instruction("neutral"))
        self.assertIn("ไม่ใช่คำ", capture_instruction("unknown"))
        self.assertIn("น้ำ", capture_instruction("น้ำ"))


if __name__ == "__main__":
    unittest.main()
