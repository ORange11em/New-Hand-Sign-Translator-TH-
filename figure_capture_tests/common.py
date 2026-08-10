"""Shared helpers for document-figure capture tools.

The tools in this folder are deliberately read-only with respect to the
HandVox dataset and model.  They write PNG files only under their own output
folders.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
POSE_IDS = (0, 2, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 23, 24)
POSE_COLOR = (220, 90, 35)       # blue in BGR
LEFT_HAND_COLOR = (55, 190, 70)  # green in BGR
RIGHT_HAND_COLOR = (0, 145, 255) # orange in BGR


def thai_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts/THSarabunNew.ttf",
        Path("C:/Windows/Fonts/THSarabunNew.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw_thai(frame: np.ndarray, text: str, xy: tuple[int, int], size: int = 30,
              color: tuple[int, int, int] = (255, 255, 255),
              anchor: str | None = None) -> np.ndarray:
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image)
    rgb = (color[2], color[1], color[0])
    draw.text(xy, text, font=thai_font(size), fill=rgb, anchor=anchor)
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def point_xy(point, width: int, height: int) -> tuple[int, int]:
    return int(point.x * width), int(point.y * height)


def draw_selected_landmarks(frame: np.ndarray, results) -> np.ndarray:
    """Draw exactly the 15 pose points and 21 points for each detected hand."""
    height, width = frame.shape[:2]
    selected = set(POSE_IDS)
    if results.pose_landmarks:
        landmarks = results.pose_landmarks.landmark
        for start, end in mp.solutions.pose.POSE_CONNECTIONS:
            if start in selected and end in selected:
                cv2.line(frame, point_xy(landmarks[start], width, height),
                         point_xy(landmarks[end], width, height), POSE_COLOR, 2)
        for index in POSE_IDS:
            cv2.circle(frame, point_xy(landmarks[index], width, height), 5,
                       POSE_COLOR, -1, cv2.LINE_AA)

    for hand, color in (
        (results.left_hand_landmarks, LEFT_HAND_COLOR),
        (results.right_hand_landmarks, RIGHT_HAND_COLOR),
    ):
        if hand is None:
            continue
        for start, end in mp.solutions.hands.HAND_CONNECTIONS:
            cv2.line(frame, point_xy(hand.landmark[start], width, height),
                     point_xy(hand.landmark[end], width, height), color, 2)
        for point in hand.landmark:
            cv2.circle(frame, point_xy(point, width, height), 4, color, -1,
                       cv2.LINE_AA)
    return frame


def draw_legend(frame: np.ndarray) -> np.ndarray:
    overlay = frame.copy()
    cv2.rectangle(overlay, (15, 15), (375, 155), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
    items = (
        ("Pose ช่วงบน 15 จุด", POSE_COLOR),
        ("มือซ้าย 21 จุด", LEFT_HAND_COLOR),
        ("มือขวา 21 จุด", RIGHT_HAND_COLOR),
    )
    for row, (label, color) in enumerate(items):
        y = 48 + row * 38
        cv2.circle(frame, (38, y), 8, color, -1, cv2.LINE_AA)
        frame = draw_thai(frame, label, (58, y - 19), 26)
    return frame


def open_camera(index: int = 0) -> cv2.VideoCapture:
    camera = cv2.VideoCapture(index)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not camera.isOpened():
        raise RuntimeError(f"ไม่สามารถเปิดกล้องหมายเลข {index} ได้")
    return camera


def new_holistic():
    return mp.solutions.holistic.Holistic(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
    )


def save_png(output_dir: Path, stem: str, frame: np.ndarray) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{stem}_{timestamp}.png"
    if not cv2.imwrite(str(path), frame):
        raise RuntimeError(f"บันทึกภาพไม่ได้: {path}")
    return path

