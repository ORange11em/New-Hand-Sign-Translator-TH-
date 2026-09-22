"""Compare detector stages on a local replay, without camera, speech or history writes."""

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from handvox.temporal_model import TemporalClassifier

import cv2
import mediapipe as mp
import numpy as np

from handvox.settings import SettingsStore


class SilentSpeech:
    available = False
    engine_name = "benchmark-disabled"

    def __init__(self, **kwargs):
        pass

    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "run_detector.py")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()
    if args.frames < 2:
        parser.error("--frames must be at least 2")
    capture = cv2.VideoCapture(str(args.video))
    frames = []
    while True:
        readable, frame = capture.read()
        if not readable:
            break
        frames.append(cv2.resize(frame, (1280, 720)))
    capture.release()
    if not frames:
        parser.error("The replay video has no readable frames")
    rows = []
    current = {}
    inference_inputs = hashlib.sha256()
    probabilities = []
    settings = replace(SettingsStore().load_or_default(), auto_add_words=False, auto_tts=False)
    original_holistic = mp.solutions.holistic.Holistic
    original_load = TemporalClassifier.load

    class ReplayCamera:
        position = 0

        def isOpened(self):
            return True

        def set(self, *_args):
            return True

        def read(self):
            if self.position >= args.frames:
                return False, None
            current.clear()
            current.update(start=time.perf_counter(), landmarks_ms=0.0, inference_ms=0.0)
            frame = frames[self.position % len(frames)].copy()
            self.position += 1
            return True, frame

        def release(self):
            pass

    class TimedHolistic:
        def __init__(self, **kwargs):
            self.detector = original_holistic(**kwargs)

        def process(self, frame):
            started = time.perf_counter()
            result = self.detector.process(frame)
            current["landmarks_ms"] = (time.perf_counter() - started) * 1000
            return result

        def close(self):
            self.detector.close()

    def load_model(*load_args, **kwargs):
        model = original_load(*load_args, **kwargs)
        predict = model.predict_proba

        def timed_predict(values):
            started = time.perf_counter()
            result = predict(values)
            current["inference_ms"] = (time.perf_counter() - started) * 1000
            inference_inputs.update(np.ascontiguousarray(values).tobytes())
            probabilities.append(result.tolist())
            return result

        model.predict_proba = timed_predict
        return model

    def show_frame(_title, frame):
        current["frame_ms"] = (time.perf_counter() - current["start"]) * 1000
        rows.append({key: value for key, value in current.items() if key != "start"})
        if len(rows) == args.frames:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(args.output.with_suffix(".png")), frame)

    with (
        patch.object(cv2, "VideoCapture", return_value=ReplayCamera()),
        patch.object(cv2, "namedWindow"),
        patch.object(cv2, "resizeWindow"),
        patch.object(cv2, "setMouseCallback"),
        patch.object(cv2, "destroyAllWindows"),
        patch.object(cv2, "getWindowProperty", return_value=1.0),
        patch.object(cv2, "waitKey", return_value=-1),
        patch.object(cv2, "imshow", side_effect=show_frame),
        patch.object(mp.solutions.holistic, "Holistic", TimedHolistic),
        patch.object(TemporalClassifier, "load", side_effect=load_model),
        patch.object(SettingsStore, "load_or_default", return_value=settings),
        patch("tts_service.SpeechService", SilentSpeech),
        patch("handvox.history.HistoryStore"),
    ):
        runpy.run_path(str(args.source), run_name="__main__")
    measured = rows[min(10, len(rows) // 4):]
    summary = {
        "mode": "offline_replay_no_camera_driver_or_display",
        "source": str(args.source),
        "video": str(args.video),
        "processed_frames": len(rows),
        "measured_frames_after_warmup": len(measured),
        "inference_count": len(probabilities),
        "inference_input_sha256": inference_inputs.hexdigest(),
        "probabilities": probabilities,
        "stages": {
            stage: {
                "mean_ms": float(np.mean([row[stage] for row in measured])),
                "p95_ms": float(np.percentile([row[stage] for row in measured], 95)),
            }
            for stage in ("frame_ms", "landmarks_ms", "inference_ms")
        },
    }
    summary["processed_fps"] = 1000 / summary["stages"]["frame_ms"]["mean_ms"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "probabilities"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
