"""Collect short upper-body gesture clips for HandVox."""

import argparse
import os
import time

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from body_features import extract_features, upper_body_bbox
from gesture_config import GESTURES
from sequence_dataset import (
    CLIPS_PER_GESTURE, SEQUENCE_LENGTH, append_clip, archive_legacy_data, count_clips,
)


def load_font(size):
    for path in ("C:/Windows/Fonts/THSarabunNew.ttf", "C:/Windows/Fonts/tahoma.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT_LARGE = load_font(48)
FONT_MEDIUM = load_font(30)
FONT_SMALL = load_font(22)


def thai_text(image, text, position, font, color=(255, 255, 255)):
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    drawer = ImageDraw.Draw(pil)
    drawer.text(position, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def centered_text(image, text, y, font, color=(255, 255, 255)):
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    drawer = ImageDraw.Draw(pil)
    box = drawer.textbbox((0, 0), text, font=font)
    drawer.text(((image.shape[1] - (box[2] - box[0])) // 2, y), text, font=font,
                fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def wait_for_start(camera, name, description, remaining):
    while True:
        ok, frame = camera.read()
        if not ok:
            return False
        frame = cv2.flip(frame, 1)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        frame = centered_text(frame, name, 190, FONT_LARGE, (0, 255, 160))
        frame = centered_text(frame, description, 270, FONT_SMALL, (220, 220, 120))
        frame = centered_text(frame, f"เหลือ {remaining} คลิป", 315, FONT_MEDIUM, (180, 180, 180))
        frame = centered_text(frame, "จัดให้เห็นศีรษะถึงสะโพกและมือ", 365, FONT_SMALL, (180, 180, 180))
        frame = centered_text(frame, "กด SPACE เริ่มบันทึกคลิป 1 วินาที | Q ออก", 410, FONT_SMALL, (0, 210, 255))
        cv2.imshow("HandVox - Clip Collector", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            return True
        if key == ord("q"):
            return False


def collect_clip(camera, detector):
    frames = []
    while len(frames) < SEQUENCE_LENGTH:
        ok, frame = camera.read()
        if not ok:
            return None
        frame = cv2.flip(frame, 1)
        height, width = frame.shape[:2]
        result = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        features = extract_features(result)
        if features is not None:
            frames.append(features)
            bbox = upper_body_bbox(result, width, height)
            if bbox:
                cv2.rectangle(frame, bbox[:2], bbox[2:], (0, 255, 100), 2)
        frame = thai_text(frame, f"บันทึกคลิป: {len(frames)}/{SEQUENCE_LENGTH} เฟรม", (20, 18),
                          FONT_MEDIUM, (0, 255, 160))
        if features is None:
            frame = thai_text(frame, "รอให้เห็นช่วงบนและมืออย่างน้อยหนึ่งข้าง", (20, 65),
                              FONT_SMALL, (0, 110, 255))
        cv2.imshow("HandVox - Clip Collector", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            return None
    return np.asarray(frames, dtype=np.float32)


def main():
    parser = argparse.ArgumentParser(description="Collect HandVox gesture clips")
    parser.add_argument("--gesture", help="Collect clips for this gesture only")
    args = parser.parse_args()
    if args.gesture and args.gesture not in GESTURES:
        parser.error(f"ไม่พบท่า '{args.gesture}'")
    if not GESTURES:
        print("ยังไม่มีท่า กรุณาเปิด Add_New_Gesture.bat เพื่อเพิ่มท่าแรก")
        return 1

    archive = archive_legacy_data()
    if archive:
        print(f"เก็บข้อมูลแบบภาพนิ่งเดิมไว้ที่: {archive}")

    gestures = [args.gesture] if args.gesture else list(GESTURES)
    detector = mp.solutions.holistic.Holistic(
        static_image_mode=False, model_complexity=1, smooth_landmarks=True,
        min_detection_confidence=0.7, min_tracking_confidence=0.7,
    )
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not camera.isOpened():
        print("เปิดกล้องไม่ได้")
        return 1

    try:
        for name in gestures:
            while count_clips(name) < CLIPS_PER_GESTURE:
                remaining = CLIPS_PER_GESTURE - count_clips(name)
                if not wait_for_start(camera, name, GESTURES[name], remaining):
                    return 1
                for seconds in (3, 2, 1):
                    started = time.time()
                    while time.time() - started < 1:
                        ok, frame = camera.read()
                        if not ok:
                            return 1
                        frame = cv2.flip(frame, 1)
                        frame = centered_text(frame, str(seconds), 250, FONT_LARGE, (0, 220, 255))
                        cv2.imshow("HandVox - Clip Collector", frame)
                        cv2.waitKey(1)
                clip = collect_clip(camera, detector)
                if clip is None:
                    return 1
                append_clip(name, clip)
                print(f"{name}: {count_clips(name)}/{CLIPS_PER_GESTURE} clips")
    finally:
        detector.close()
        camera.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
