"""ทดสอบการยืนยันผล การปฏิเสธ และ cooldown ของตัวตรวจจับ."""

import unittest

from gesture_state import DetectionPhase, GestureStateMachine


class GestureStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.machine = GestureStateMachine(
            min_confidence=0.65, confirm_frames=3, release_seconds=0.30
        )

    def confirm(self, label="สวัสดี", start=0.0):
        result = None
        for offset in range(3):
            result = self.machine.update(label, 0.90, True, start + offset * 0.05)
        return result

    def test_rejects_low_confidence(self):
        result = self.machine.update("สวัสดี", 0.40, True, 0.0)
        self.assertEqual(result.phase, DetectionPhase.IDLE)
        self.assertEqual(result.label, "")

    def test_requires_repeated_predictions_before_confirmation(self):
        first = self.machine.update("สวัสดี", 0.90, True, 0.0)
        second = self.machine.update("สวัสดี", 0.88, True, 0.1)
        third = self.machine.update("สวัสดี", 0.92, True, 0.2)

        self.assertEqual(first.phase, DetectionPhase.CANDIDATE)
        self.assertEqual(first.label, "")
        self.assertEqual(second.label, "")
        self.assertEqual(third.phase, DetectionPhase.CONFIRMED)
        self.assertEqual(third.label, "สวัสดี")

    def test_uncertain_frame_never_exposes_stale_label(self):
        self.confirm()
        rejected = self.machine.update("สวัสดี", 0.20, True, 0.20)

        self.assertEqual(rejected.phase, DetectionPhase.CONFIRMED)
        self.assertEqual(rejected.label, "")
        self.assertEqual(rejected.confidence, 0.0)

    def test_sustained_rejection_releases_state(self):
        self.confirm()
        self.machine.update("", 0.0, False, 0.20)
        released = self.machine.update("", 0.0, False, 0.51)

        self.assertTrue(released.released)
        self.assertEqual(released.phase, DetectionPhase.IDLE)
        self.assertEqual(self.machine.label, "")

    def test_cooldown_requires_release_or_a_different_label(self):
        confirmed = self.confirm()
        self.assertTrue(self.machine.mark_emitted(confirmed.label))

        held = self.machine.update("สวัสดี", 0.91, True, 0.20)
        changed = self.machine.update("ขอบคุณ", 0.92, True, 0.25)

        self.assertEqual(held.phase, DetectionPhase.COOLDOWN)
        self.assertEqual(held.label, "")
        self.assertEqual(held.reason, "wait_neutral")
        self.assertFalse(self.machine.speech_armed)
        self.assertEqual(changed.phase, DetectionPhase.CANDIDATE)
        self.assertEqual(changed.label, "")

    def test_same_word_is_unlocked_only_after_neutral_frames(self):
        confirmed = self.confirm()
        self.machine.mark_emitted(confirmed.label)

        first = self.machine.update(
            "", 0.0, True, 0.20, neutral_detected=True
        )
        second = self.machine.update(
            "", 0.0, True, 0.25, neutral_detected=True
        )
        released = self.machine.update(
            "", 0.0, True, 0.30, neutral_detected=True
        )

        self.assertEqual(first.phase, DetectionPhase.COOLDOWN)
        self.assertGreater(first.neutral_progress, 0.0)
        self.assertFalse(second.released)
        self.assertTrue(released.released)
        self.assertEqual(released.phase, DetectionPhase.IDLE)

    def test_probability_margin_must_be_wide_enough(self):
        machine = GestureStateMachine(
            min_confidence=0.65,
            min_probability_margin=0.15,
            confirm_frames=2,
        )
        result = machine.update(
            "สวัสดี", 0.90, True, 0.0, probability_margin=0.05
        )

        self.assertEqual(result.phase, DetectionPhase.IDLE)
        self.assertEqual(result.reason, "low_margin")

    def test_unknown_is_rejected_and_does_not_unlock_cooldown(self):
        confirmed = self.confirm()
        self.machine.mark_emitted(confirmed.label)

        result = self.machine.update(
            "", 0.91, True, 0.20, unknown_detected=True
        )

        self.assertEqual(result.phase, DetectionPhase.COOLDOWN)
        self.assertEqual(result.label, "")
        self.assertEqual(result.reason, "unknown")
        self.assertFalse(result.released)


if __name__ == "__main__":
    unittest.main()
