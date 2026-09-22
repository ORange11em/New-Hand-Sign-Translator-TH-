"""Passive measurements must not inflate FPS or assume a training sample rate."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from handvox.detector_performance import DetectorPerformance, timing_lines


class DetectorPerformanceTests(unittest.TestCase):
    def test_fps_uses_full_duration_not_only_inference(self):
        performance = DetectorPerformance()
        performance.record({"total": 0.2, "inference": 0.002}, predicted=True, features_visible=True)
        performance.record({"total": 0.2, "inference": 0.0}, predicted=False)
        snapshot = performance.snapshot()
        self.assertAlmostEqual(snapshot["fps"], 5)
        self.assertAlmostEqual(snapshot["prediction_fps"], 2.5)
        self.assertAlmostEqual(snapshot["feature_fps"], 2.5)
        self.assertAlmostEqual(snapshot["stages"]["inference"]["mean_ms"], 1)

    def test_bounded_rolling_samples(self):
        performance = DetectorPerformance(window_size=2)
        for duration in (0.1, 0.2, 0.4):
            performance.record({"total": duration})
        self.assertEqual(performance.total_frames, 3)
        self.assertEqual(performance.snapshot()["frames"], 2)
        self.assertEqual(performance.snapshot()["stages"]["total"]["p95_ms"], 400)

    def test_empty_snapshot_does_not_invent_fps(self):
        self.assertEqual(DetectorPerformance().snapshot()["fps"], 0)
        self.assertIn("กำลังวัด", timing_lines(DetectorPerformance().snapshot())[0])

    def test_invalid_durations_rejected(self):
        for duration in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                DetectorPerformance().record({"total": duration})

    def test_report_contains_metrics_but_no_frames_or_words(self):
        with TemporaryDirectory() as directory:
            performance = DetectorPerformance()
            performance.record({"total": 0.1, "render": 0.002})
            destination = Path(directory) / "performance.json"
            performance.save(destination)
            report = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(report["sampling_policy"], "processed_valid_frames_no_resampling")
        self.assertIs(report["training_frame_timestamps_available"], False)
        self.assertEqual(report["total_frames"], 1)
        self.assertNotIn("sentence", report)


if __name__ == "__main__":
    unittest.main()
