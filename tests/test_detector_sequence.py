"""A new gesture must not inherit a stale, incomplete warmup window."""

from collections import deque
import unittest

from handvox.detector_sequence import expire_missing_motion


class DetectorSequenceTests(unittest.TestCase):
    def test_brief_loss_preserves_samples_and_timestamps(self):
        frames = deque(["first", "second"], maxlen=30)
        timestamps = deque([1.0, 1.1], maxlen=30)
        self.assertFalse(expire_missing_motion(frames, timestamps, now=1.2, release_seconds=0.35))
        self.assertEqual(list(frames), ["first", "second"])
        self.assertEqual(list(timestamps), [1.0, 1.1])

    def test_long_loss_clears_incomplete_window_before_prediction(self):
        frames = deque(["old"], maxlen=30)
        timestamps = deque([1.0], maxlen=30)
        self.assertTrue(expire_missing_motion(frames, timestamps, now=1.5, release_seconds=0.35))
        self.assertEqual(list(frames), [])
        self.assertEqual(list(timestamps), [])
        frames.append("new")
        self.assertEqual(list(frames), ["new"])
        self.assertEqual(frames.maxlen, 30)

    def test_empty_window_is_safe(self):
        self.assertFalse(expire_missing_motion(deque(), deque(), now=100, release_seconds=0.35))

    def test_zero_release_timeout_expires_on_first_missing_frame(self):
        frames = deque(["old"])
        timestamps = deque([1.0])
        self.assertTrue(expire_missing_motion(frames, timestamps, now=1.01, release_seconds=0))


if __name__ == "__main__":
    unittest.main()
