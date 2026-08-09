"""เก็บคลิป landmark แบบเดิมสำหรับแต่ละท่าผ่านกล้องเว็บแคม."""

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
    """เลือกฟอนต์ Windows ที่แสดงภาษาไทยได้ตามขนาดที่ต้องการ."""
    for path in ("C:/Windows/Fonts/THSarabunNew.ttf", "C:/Windows/Fonts/tahoma.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT_LARGE = load_font(48)
FONT_MEDIUM = load_font(30)
FONT_SMALL = load_font(22)
WINDOW_TITLE = "HandVox - Clip Collector"


def thai_text(image, text, position, font, color=(255, 255, 255)):
    """วาดข้อความไทยด้วย Pillow แล้วแปลงภาพกลับเป็นรูปแบบ OpenCV."""
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    drawer = ImageDraw.Draw(pil)
    drawer.text(position, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def centered_text(image, text, y, font, color=(255, 255, 255)):
    """วาดข้อความไทยให้อยู่กึ่งกลางแนวนอนของภาพ."""
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    drawer = ImageDraw.Draw(pil)
    box = drawer.textbbox((0, 0), text, font=font)
    drawer.text(((image.shape[1] - (box[2] - box[0])) // 2, y), text, font=font,
                fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def wait_for_start(camera, name, description, remaining):
    """แสดงคำอธิบายท่าและรอ Space/คลิกเพื่อเริ่ม หรือ Q เพื่อยกเลิก."""
    record_requested = {"value": False, "rect": None}

    def on_mouse(event, x, y, flags, parameter):
        """แปลงการคลิกปุ่มบนภาพเป็นคำสั่งเริ่มของลูปหลัก."""
        if event != cv2.EVENT_LBUTTONDOWN or record_requested["rect"] is None:
            return
        x1, y1, x2, y2 = record_requested["rect"]
        if x1 <= x <= x2 and y1 <= y <= y2:
            record_requested["value"] = True

    cv2.namedWindow(WINDOW_TITLE)
    cv2.setMouseCallback(WINDOW_TITLE, on_mouse)
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
        height, width = frame.shape[:2]
        button_width, button_height = 330, 58
        button_x = (width - button_width) // 2
        button_y = min(height - button_height - 24, 430)
        record_requested["rect"] = (
            button_x, button_y, button_x + button_width, button_y + button_height
        )
        cv2.rectangle(frame, record_requested["rect"][:2], record_requested["rect"][2:],
                      (0, 190, 255), -1)
        cv2.rectangle(frame, record_requested["rect"][:2], record_requested["rect"][2:],
                      (255, 255, 255), 2)
        frame = centered_text(frame, "บันทึกคลิป (นับ 3 วิ)", button_y + 10, FONT_SMALL, (0, 0, 0))
        frame = centered_text(frame, "หรือกด SPACE | Q ออก", button_y + button_height + 10,
                              FONT_SMALL, (0, 210, 255))
        cv2.imshow(WINDOW_TITLE, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" ") or record_requested["value"]:
            return True
        if key == ord("q"):
            return False


def countdown(camera, name, clip_number):
    """เว้นและนับถอยหลังสามวินาทีก่อนบันทึกแต่ละคลิปอัตโนมัติ."""
    for seconds in (3, 2, 1):
        started = time.time()
        while time.time() - started < 1:
            ok, frame = camera.read()
            if not ok:
                return False
            frame = cv2.flip(frame, 1)
            frame = centered_text(frame, name, 160, FONT_MEDIUM, (0, 255, 160))
            frame = centered_text(frame, f"คลิปที่ {clip_number}/{CLIPS_PER_GESTURE}", 215,
                                  FONT_SMALL, (230, 230, 230))
            frame = centered_text(frame, str(seconds), 265, FONT_LARGE, (0, 220, 255))
            frame = centered_text(frame, "เตรียมพร้อม... กด Q เพื่อหยุด", 340,
                                  FONT_SMALL, (230, 230, 230))
            cv2.imshow(WINDOW_TITLE, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return False
    return True


def collect_clip(camera, detector):
    """เก็บเฉพาะเฟรมที่ดึงคุณลักษณะได้จนครบ SEQUENCE_LENGTH."""
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
        cv2.imshow(WINDOW_TITLE, frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            return None
    return np.asarray(frames, dtype=np.float32)


def main():
    """เปิดกล้อง วนตามท่าที่ยังคลิปไม่ครบ และบันทึกลง Dataset รุ่นเดิม."""
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
            remaining = CLIPS_PER_GESTURE - count_clips(name)
            if remaining <= 0:
                continue
            if not wait_for_start(camera, name, GESTURES[name], remaining):
                return 1
            while count_clips(name) < CLIPS_PER_GESTURE:
                clip_number = count_clips(name) + 1
                if not countdown(camera, name, clip_number):
                    return 1
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
