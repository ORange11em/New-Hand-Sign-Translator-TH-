"""Camera layout, action safety and rendering regression tests without a webcam."""

from dataclasses import replace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from gesture_state import DetectionPhase, DetectionResult
from handvox.detector_view import (
    DetectionPresentation, DetectorView, DetectorViewState, detection_presentation,
)


class DetectorViewTests(unittest.TestCase):
    def setUp(self):
        self.view = DetectorView()
        self.state = DetectorViewState(experimental=True)

    def test_empty_sentence_disables_data_actions(self):
        self.assertEqual(set(self.view.action_regions(self.state)), {"details", "close"})
        self.assertIsNone(self.view.action_at(self.state, 780, 490))

    def test_confirmed_word_and_sentence_enable_expected_actions(self):
        state = replace(self.state, can_add=True, can_speak=True, word_count=1, sentence="น้ำ")
        self.assertEqual(set(self.view.action_regions(state)), set(self.view.button_bounds))
        for action, bounds in self.view.action_regions(state).items():
            self.assertEqual(self.view.action_at(state, (bounds[0] + bounds[2]) // 2,
                                                (bounds[1] + bounds[3]) // 2), action)

    def test_unavailable_speech_is_disabled(self):
        self.assertNotIn("speak", self.view.action_regions(replace(self.state, word_count=1)))

    def test_all_buttons_are_outside_camera_and_inside_canvas(self):
        camera = self.view.camera_bounds
        for bounds in self.view.button_bounds.values():
            self.assertGreaterEqual(bounds[0], 0)
            self.assertGreaterEqual(bounds[1], 0)
            self.assertLessEqual(bounds[2], self.view.size[0])
            self.assertLessEqual(bounds[3], self.view.size[1])
            overlap = min(bounds[2], camera[2]) > max(bounds[0], camera[0]) and (
                min(bounds[3], camera[3]) > max(bounds[1], camera[1]))
            self.assertFalse(overlap)

    def test_render_preserves_input_and_does_only_two_color_conversions(self):
        frame = np.full((720, 1280, 3), 125, dtype=np.uint8)
        original = frame.copy()
        with patch("handvox.detector_view.cv2.cvtColor", wraps=cv2.cvtColor) as convert:
            rendered = self.view.render(frame, self.state, (0, 0, 1280, 720))
        self.assertEqual(rendered.shape, (680, 1080, 3))
        self.assertEqual(convert.call_count, 2)
        np.testing.assert_array_equal(frame, original)

    def test_cached_chrome_still_updates_camera(self):
        first = np.zeros((360, 640, 3), dtype=np.uint8)
        second = np.full_like(first, 255)
        with patch.object(self.view, "chrome", wraps=self.view.chrome) as chrome:
            result_one = self.view.render(first, self.state)
            result_two = self.view.render(second, self.state)
        self.assertEqual(chrome.call_count, 1)
        self.assertFalse(np.array_equal(result_one, result_two))

    def test_experimental_warning_is_always_present(self):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        trial = self.view.render(frame, self.state)
        normal = self.view.render(frame, replace(self.state, experimental=False))
        self.assertFalse(np.array_equal(trial[76:109, 20:1061], normal[76:109, 20:1061]))

    def test_long_thai_sentence_and_largest_font_render(self):
        state = replace(self.state, sentence="ช่วยด้วย ฉันต้องการน้ำ ขอบคุณ " * 30,
                        word_count=90, details=True,
                        timing=("กล้อง 30 ms · จุดมือ 60 ms · โมเดล 4 ms · UI 3 ms", "ช่วงข้อมูล 3.5 วิ"),
                        detection=DetectionPresentation("ไม่เป็นไร", "กำลังยืนยัน", "pending", 0.5))
        rendered = DetectorView(font_scale=1.75).render(np.zeros((480, 640, 3), dtype=np.uint8), state)
        self.assertEqual(rendered.shape, (680, 1080, 3))

    def test_missing_landmarks_hide_stale_label(self):
        decision = DetectionResult(DetectionPhase.CONFIRMED, label="น้ำ", confidence=0.99)
        presentation = detection_presentation(decision, visible=False, frame_count=30, sequence_length=30)
        self.assertEqual(presentation.label, "รอท่ามือ")

    def test_candidate_is_not_presented_as_confirmed(self):
        decision = DetectionResult(DetectionPhase.CANDIDATE, candidate_label="น้ำ", confirm_progress=0.5)
        presentation = detection_presentation(decision, visible=True, frame_count=30, sequence_length=30)
        self.assertEqual(presentation.tone, "pending")
        self.assertIn("ยังไม่เพิ่ม", presentation.status)

    def test_policy_rejection_does_not_claim_unknown_gesture(self):
        decision = DetectionResult(DetectionPhase.IDLE, reason="unknown")
        presentation = detection_presentation(decision, visible=True, frame_count=30,
                                             sequence_length=30, unknown=True, policy_rejected=True)
        self.assertEqual(presentation.label, "ยังไม่แน่ใจ")

    def test_warmup_counts_frames_without_changing_sequence(self):
        decision = DetectionResult(DetectionPhase.IDLE)
        presentation = detection_presentation(decision, visible=True, frame_count=6, sequence_length=30)
        self.assertAlmostEqual(presentation.progress, 0.2)


if __name__ == "__main__":
    unittest.main()
