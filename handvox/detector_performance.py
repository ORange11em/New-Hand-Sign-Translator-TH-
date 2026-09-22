"""Bounded, passive timing measurements; never resamples model input."""

from collections import deque
import json
import math
from pathlib import Path


class DetectorPerformance:
    def __init__(self, window_size=120):
        if window_size < 2:
            raise ValueError("window_size must be at least 2")
        self.frames = deque(maxlen=window_size)
        self.total_frames = 0

    def record(self, durations, *, predicted=False, features_visible=False):
        values = {name: float(value) for name, value in durations.items()}
        if any(not math.isfinite(value) or value < 0 for value in values.values()):
            raise ValueError("durations must be finite and nonnegative")
        if values.get("total", 0) <= 0:
            raise ValueError("total frame duration must be positive")
        self.frames.append((values, bool(predicted), bool(features_visible)))
        self.total_frames += 1

    def snapshot(self):
        if not self.frames:
            return {"frames": 0, "fps": 0.0, "prediction_fps": 0.0, "feature_fps": 0.0, "stages": {}}
        elapsed = sum(frame[0]["total"] for frame in self.frames)
        stages = {}
        for name in self.frames[-1][0]:
            samples = sorted(frame[0].get(name, 0.0) * 1000 for frame in self.frames)
            stages[name] = {
                "mean_ms": sum(samples) / len(samples),
                "p95_ms": samples[max(0, math.ceil(0.95 * len(samples)) - 1)],
            }
        return {
            "frames": len(self.frames),
            "fps": len(self.frames) / elapsed,
            "prediction_fps": sum(frame[1] for frame in self.frames) / elapsed,
            "feature_fps": sum(frame[2] for frame in self.frames) / elapsed,
            "stages": stages,
        }

    def save(self, path, *, metadata=None):
        report = {
            "total_frames": self.total_frames,
            "sampling_policy": "processed_valid_frames_no_resampling",
            "training_frame_timestamps_available": False,
            "rolling_measurement": self.snapshot(),
            "metadata": metadata or {},
        }
        destination = Path(path)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(destination)


def timing_lines(snapshot, sequence_seconds=None):
    stages = snapshot.get("stages", {})
    if not stages:
        return ("กำลังวัดความเร็ว...", "คงจังหวะรับข้อมูลเดิม ไม่ข้ามหรือเติมเฟรม")

    def milliseconds(name):
        return stages.get(name, {}).get("mean_ms", 0.0)

    first = (
        f"กล้อง {milliseconds('camera'):.0f} ms · จุดมือ {milliseconds('landmarks'):.0f} ms"
        f" · โมเดล {milliseconds('inference'):.0f} ms · UI {milliseconds('render'):.0f} ms"
    )
    span = f" · ช่วงข้อมูล {sequence_seconds:.1f} วิ" if sequence_seconds is not None else ""
    second = f"ทำนายจริง {snapshot.get('prediction_fps', 0):.1f} ครั้ง/วิ{span} · ไม่ปรับจังหวะเฟรม"
    return first, second
