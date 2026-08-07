import unittest

from handvox.camera_sentence import GestureHoldTimer


class GestureHoldTimerTests(unittest.TestCase):
    def test_emits_once_after_hold_duration(self):
        timer = GestureHoldTimer(hold_seconds=1.0)
        self.assertEqual(timer.update("น้ำ", True, 10.0).ready_label, "")
        self.assertAlmostEqual(timer.update("น้ำ", True, 10.5).progress, 0.5)
        self.assertEqual(timer.update("น้ำ", True, 11.0).ready_label, "น้ำ")
        self.assertEqual(timer.update("น้ำ", True, 12.0).ready_label, "")

    def test_release_allows_same_label_again(self):
        timer = GestureHoldTimer(hold_seconds=1.0)
        timer.update("ขอบคุณ", True, 1.0)
        self.assertEqual(timer.update("ขอบคุณ", True, 2.0).ready_label, "ขอบคุณ")
        timer.update("", False, 2.1)
        timer.update("ขอบคุณ", True, 3.0)
        self.assertEqual(timer.update("ขอบคุณ", True, 4.0).ready_label, "ขอบคุณ")

    def test_changed_label_restarts_timer(self):
        timer = GestureHoldTimer(hold_seconds=1.0)
        timer.update("น้ำ", True, 1.0)
        timer.update("น้ำ", True, 1.8)
        changed = timer.update("กิน", True, 1.9)
        self.assertEqual(changed.progress, 0.0)
        self.assertEqual(timer.update("กิน", True, 3.0).ready_label, "กิน")

    def test_rejects_invalid_duration(self):
        with self.assertRaises(ValueError):
            GestureHoldTimer(0)


if __name__ == "__main__":
    unittest.main()
