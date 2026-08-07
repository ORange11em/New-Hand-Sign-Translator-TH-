"""Collect auditable HandVox V2 clips for one signer/session/gesture."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import time
import uuid

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from body_features import FEATURE_COUNT, extract_features, upper_body_bbox
from handvox.dataset_v2 import ClipMetadata, DatasetV2Store, LIGHTING_VALUES
from handvox.gesture_catalog import GestureCatalog
from handvox.settings import SettingsStore
from handvox.training_config import load_training_config


WINDOW_TITLE = "HandVox - Dataset V2 Collector"


def load_font(size):
    for path in ("C:/Windows/Fonts/THSarabunNew.ttf", "C:/Windows/Fonts/tahoma.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT_LARGE = load_font(44)
FONT_MEDIUM = load_font(28)
FONT_SMALL = load_font(21)


def thai_text(image, text, position, font, color=(255, 255, 255)):
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    drawer = ImageDraw.Draw(pil)
    drawer.text(position, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def centered_text(image, text, y, font, color=(255, 255, 255)):
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    drawer = ImageDraw.Draw(pil)
    box = drawer.textbbox((0, 0), text, font=font)
    x = (image.shape[1] - (box[2] - box[0])) // 2
    drawer.text((x, y), text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def session_target(config, session_id):
    sessions = config.collection.sessions
    target = config.collection.target_clips_per_signer_per_class
    base, remainder = divmod(target, len(sessions))
    return base + (1 if sessions.index(session_id) < remainder else 0)


def count_usable(records, gesture_name, signer_id, session_id):
    return sum(
        1
        for item in records
        if item.gesture_name == gesture_name
        and item.signer_id == signer_id
        and item.session_id == session_id
        and item.quality != "rejected"
    )


def countdown(camera, gesture_name, seconds):
    for remaining in range(seconds, 0, -1):
        started = time.monotonic()
        while time.monotonic() - started < 1.0:
            ok, frame = camera.read()
            if not ok:
                return False
            frame = cv2.flip(frame, 1)
            frame = centered_text(frame, gesture_name, 155, FONT_MEDIUM, (0, 255, 160))
            frame = centered_text(frame, str(remaining), 225, FONT_LARGE, (0, 210, 255))
            frame = centered_text(
                frame, "เตรียมทำท่าให้ครบหนึ่งรอบ | Q หยุด", 315, FONT_SMALL
            )
            cv2.imshow(WINDOW_TITLE, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return False
    return True


def collect_clip(camera, detector, sequence_length, save_preview):
    features_list = []
    preview_frames = []
    while len(features_list) < sequence_length:
        ok, raw_frame = camera.read()
        if not ok:
            return None, None
        raw_frame = cv2.flip(raw_frame, 1)
        height, width = raw_frame.shape[:2]
        result = detector.process(cv2.cvtColor(raw_frame, cv2.COLOR_BGR2RGB))
        features = extract_features(result)
        display = raw_frame.copy()
        if features is not None:
            features_list.append(features)
            if save_preview:
                preview_frames.append(cv2.resize(raw_frame, (640, 360)))
            bbox = upper_body_bbox(result, width, height)
            if bbox:
                cv2.rectangle(display, bbox[:2], bbox[2:], (0, 255, 100), 2)
        display = thai_text(
            display,
            f"บันทึก {len(features_list)}/{sequence_length} เฟรม",
            (18, 14),
            FONT_MEDIUM,
            (0, 255, 160),
        )
        if features is None:
            display = thai_text(
                display,
                "รอให้เห็นช่วงบนและมืออย่างน้อยหนึ่งข้าง",
                (18, 58),
                FONT_SMALL,
                (0, 120, 255),
            )
        cv2.imshow(WINDOW_TITLE, display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            return None, None
    return np.asarray(features_list, dtype=np.float32), preview_frames


def save_sequence(path, sequence):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.npy")
    np.save(temporary, sequence.astype(np.float32))
    temporary.replace(path)


def save_preview(path, frames, fps=30.0):
    if not frames:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 360)
    )
    if not writer.isOpened():
        return False
    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()
    return True


def reference_for(gesture_name):
    if gesture_name == "neutral":
        return ""
    planned = GestureCatalog().load_planned()
    item = next((gesture for gesture in planned if gesture.name == gesture_name), None)
    return item.reference_url if item else ""


def main():
    config = load_training_config()
    parser = argparse.ArgumentParser(description="Collect HandVox Dataset V2 clips")
    parser.add_argument("--signer", required=True, choices=config.collection.signers)
    parser.add_argument("--session", required=True, choices=config.collection.sessions)
    parser.add_argument("--gesture", required=True, choices=config.all_classes)
    parser.add_argument("--lighting", default="unknown", choices=LIGHTING_VALUES)
    args = parser.parse_args()

    store = DatasetV2Store()
    store.initialize()
    records = store.records()
    target = session_target(config, args.session)
    current = count_usable(records, args.gesture, args.signer, args.session)
    if current >= target:
        print(
            f"ข้อมูลครบแล้ว: {args.gesture} / {args.signer} / {args.session} "
            f"({current}/{target} คลิป)"
        )
        return 0

    settings = SettingsStore().load_or_default()
    detector = mp.solutions.holistic.Holistic(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
    )
    camera = cv2.VideoCapture(settings.camera_index)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not camera.isOpened():
        detector.close()
        print("เปิดกล้องไม่ได้")
        return 1

    cv2.namedWindow(WINDOW_TITLE)
    try:
        first_clip = True
        while current < target:
            wait_seconds = 3 if first_clip else 1
            if not countdown(camera, args.gesture, wait_seconds):
                break
            sequence, preview_frames = collect_clip(
                camera,
                detector,
                config.collection.sequence_length,
                config.collection.save_preview_video,
            )
            if sequence is None:
                break
            clip_id = uuid.uuid4().hex
            sequence_relative = Path("clips") / args.gesture / f"{clip_id}.npy"
            preview_relative = Path("previews") / args.gesture / f"{clip_id}.mp4"
            save_sequence(store.resolve_data_path(sequence_relative), sequence)
            preview_saved = False
            if config.collection.save_preview_video:
                preview_saved = save_preview(
                    store.resolve_data_path(preview_relative), preview_frames
                )
            clip_number = store.next_clip_number(
                args.gesture, args.signer, args.session
            )
            store.append(
                ClipMetadata(
                    clip_id=clip_id,
                    gesture_name=args.gesture,
                    signer_id=args.signer,
                    session_id=args.session,
                    recorded_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    camera_index=settings.camera_index,
                    lighting=args.lighting,
                    clip_number=clip_number,
                    quality="pending",
                    reference_url=reference_for(args.gesture),
                    sequence_file=sequence_relative.as_posix(),
                    preview_file=preview_relative.as_posix() if preview_saved else "",
                    duration_frames=len(sequence),
                    feature_count=sequence.shape[1],
                    dataset_version=2,
                    notes="รอตรวจคุณภาพก่อนนำไปเทรน",
                )
            )
            current += 1
            first_clip = False
            print(
                f"{args.gesture} / {args.signer} / {args.session}: "
                f"{current}/{target} (pending)"
            )
    finally:
        detector.close()
        camera.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
