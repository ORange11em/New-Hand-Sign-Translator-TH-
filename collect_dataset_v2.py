"""เก็บ Dataset V2 ทีละผู้ทำท่า เซสชัน และคำ พร้อม metadata ที่ตรวจสอบย้อนหลังได้."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import time
import uuid

from handvox.external_evaluation import (
    get_experiment_classes,
    get_experiment_sequence_length,
    get_training_signers,
)
from handvox.external_collection import external_session_choices, external_session_target

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from body_features import FEATURE_COUNT, extract_features, upper_body_bbox
from handvox.dataset_v2 import (
    CAPTURE_MODE_VALUES,
    ClipMetadata,
    DatasetV2Store,
    LIGHTING_VALUES,
)
from handvox.gesture_catalog import GestureCatalog
from handvox.errors import HandVoxError
from handvox.paths import EXPERIMENTS_DIR, ROOT
from handvox.settings import SettingsStore
from handvox.training_config import load_training_config, session_clip_target


WINDOW_TITLE = "HandVox - Dataset V2 Collector"


def load_font(size):
    """เลือกฟอนต์ภาษาไทยสำหรับข้อความบนภาพกล้อง."""
    for path in ("C:/Windows/Fonts/THSarabunNew.ttf", "C:/Windows/Fonts/tahoma.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT_LARGE = load_font(44)
FONT_MEDIUM = load_font(28)
FONT_SMALL = load_font(21)


def thai_text(image, text, position, font, color=(255, 255, 255)):
    """วาดข้อความไทยบนภาพ OpenCV ผ่าน Pillow."""
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    drawer = ImageDraw.Draw(pil)
    drawer.text(position, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def centered_text(image, text, y, font, color=(255, 255, 255)):
    """วาดข้อความไว้กึ่งกลางเฟรมตามตำแหน่งแนวตั้ง."""
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    drawer = ImageDraw.Draw(pil)
    box = drawer.textbbox((0, 0), text, font=font)
    x = (image.shape[1] - (box[2] - box[0])) // 2
    drawer.text((x, y), text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def session_target(config, session_id):
    """แบ่งจำนวนคลิปเป้าหมายต่อคน/คลาสให้แต่ละ session อย่างสมดุล."""
    return session_clip_target(config, session_id)


def capture_instruction(gesture_name):
    """คืนคำแนะนำสั้นที่แยกท่าพัก ท่านอกระบบ และคำภาษามือจริง."""
    if gesture_name == "neutral":
        return "พักมือในท่าธรรมชาติ ไม่ทำคำภาษามือ"
    if gesture_name == "unknown":
        return "ขยับมือแบบที่ไม่ใช่คำใดในระบบ"
    return f"ทำท่า {gesture_name} ให้ครบหนึ่งครั้ง"


def count_usable(records, gesture_name, signer_id, session_id):
    """นับคลิปที่ยังใช้ได้และตรงกับชุดเก็บข้อมูลปัจจุบัน."""
    return sum(
        1
        for item in records
        if item.gesture_name == gesture_name
        and item.signer_id == signer_id
        and item.session_id == session_id
        and item.quality != "rejected"
    )


def countdown(camera, gesture_name, seconds):
    """แสดงชื่อท่าและเวลานับถอยหลัง; คืน False เมื่อผู้ใช้กดยกเลิก."""
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
                frame,
                capture_instruction(gesture_name) + " | Q หยุด",
                315,
                FONT_SMALL,
            )
            cv2.imshow(WINDOW_TITLE, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return False
    return True


def collect_clip(camera, detector, sequence_length, save_preview):
    """เก็บ landmark sequence และภาพ preview เสริมจนครบจำนวนเฟรม."""
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
    """เขียนอาร์เรย์ landmark ผ่านไฟล์ชั่วคราวก่อนแทนไฟล์จริง."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.npy")
    np.save(temporary, sequence.astype(np.float32))
    temporary.replace(path)


def save_preview(path, frames, fps=30.0):
    """เข้ารหัสเฟรมตัวอย่างเป็น MP4 เพื่อใช้ตรวจคุณภาพภายหลัง."""
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
    """ค้นหา URL อ้างอิงของท่าจากแผนคำศัพท์."""
    if gesture_name in {"neutral", "unknown"}:
        return ""
    planned = GestureCatalog().load_planned()
    item = next((gesture for gesture in planned if gesture.name == gesture_name), None)
    return item.reference_url if item else ""


def main(argv=None):
    """ตรวจ argument เปิดกล้อง และบันทึก sequence/preview/metadata ทีละคลิป."""
    config = load_training_config()
    catalog = GestureCatalog()
    # คำใหม่ไม่ได้ถูกจำกัดไว้แค่ 16 คำตั้งต้น: ทันทีที่บันทึกลงคลังคำศัพท์
    # collector ต้องรับชื่อนั้นได้ แม้ยังไม่ถูกติดตั้งอยู่ในโมเดลปัจจุบัน
    collectable_gestures = tuple(
        dict.fromkeys(
            (
                *config.visible_gestures,
                *(item.name for item in catalog.load_active()),
                *(item.name for item in catalog.load_planned()),
                *config.internal_classes,
            )
        )
    )
    parser = argparse.ArgumentParser(description="Collect HandVox Dataset V2 clips")
    parser.add_argument("--signer", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--gesture", required=True)
    parser.add_argument(
        "--external-evaluation",
        action="store_true",
        help="เก็บผู้ใช้ใหม่ใน dataset_external_v2 เพื่อวัดผลภายหลัง",
    )
    parser.add_argument(
        "--experiment",
        help="รหัสหรือ path ของโมเดลที่จะวัด ใช้ร่วมกับ --external-evaluation",
    )
    parser.add_argument("--lighting", default="unknown", choices=LIGHTING_VALUES)
    parser.add_argument(
        "--mode",
        default="standard",
        choices=CAPTURE_MODE_VALUES,
        help="standard=เก็บให้ครบเป้า, extra=เพิ่มหนึ่งคลิป, retake=ถ่ายแทนคลิปเดิม",
    )
    parser.add_argument(
        "--retake-clip",
        default="",
        help="clip_id เดิมที่คลิปใหม่จะใช้แทนเมื่อ mode=retake",
    )
    args = parser.parse_args(argv)
    sequence_length = config.collection.sequence_length

    allowed_sessions = (
        external_session_choices(config)
        if args.external_evaluation else config.collection.sessions
    )
    if args.session not in allowed_sessions:
        parser.error("รอบถ่ายไม่อยู่ในแผน: " + ", ".join(allowed_sessions))
    if args.experiment and not args.external_evaluation:
        parser.error("--experiment ต้องใช้ร่วมกับ --external-evaluation")
    if args.external_evaluation:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.signer):
            parser.error("รหัสผู้ใช้ใหม่ต้องใช้ตัวอักษรอังกฤษ ตัวเลข _ หรือ - และห้ามว่าง")
        training_signers = set(config.collection.signers)
        if args.experiment:
            experiment_dir = Path(args.experiment)
            if not experiment_dir.is_absolute() and not experiment_dir.is_dir():
                experiment_dir = EXPERIMENTS_DIR / experiment_dir
            try:
                training_signers.update(get_training_signers(experiment_dir))
                collectable_gestures = get_experiment_classes(experiment_dir)
                sequence_length = get_experiment_sequence_length(experiment_dir)
            except HandVoxError as error:
                parser.error(str(error))
        if args.signer.casefold() in {signer.casefold() for signer in training_signers}:
            parser.error("ผู้ใช้ใหม่ต้องไม่ใช่ผู้ทำท่าที่ใช้เทรนโมเดล")
    elif args.signer not in config.collection.signers:
        parser.error("ผู้ทำท่าไม่อยู่ในแผนเทรน: " + ", ".join(config.collection.signers))
    if args.gesture not in collectable_gestures:
        parser.error("ท่าไม่อยู่ในขอบเขตที่เก็บได้: " + ", ".join(collectable_gestures))

    store = (
        DatasetV2Store(ROOT / "dataset_external_v2")
        if args.external_evaluation
        else DatasetV2Store()
    )
    store.initialize()
    records = store.records()
    target = (
        external_session_target(config, args.session)
        if args.external_evaluation else session_target(config, args.session)
    )
    current = count_usable(records, args.gesture, args.signer, args.session)
    retake_record = None
    if args.mode == "retake":
        if not args.retake_clip:
            parser.error("mode=retake ต้องระบุ --retake-clip")
        retake_record = next(
            (record for record in records if record.clip_id == args.retake_clip), None
        )
        if retake_record is None:
            parser.error(f"ไม่พบคลิปที่ต้องการถ่ายใหม่: {args.retake_clip}")
        if (
            retake_record.gesture_name != args.gesture
            or retake_record.signer_id != args.signer
            or retake_record.session_id != args.session
        ):
            parser.error("คลิปเดิมไม่ตรงกับคำ ผู้ทำท่า หรือ session ที่ระบุ")

    if args.mode == "standard" and current >= target:
        print(
            f"ข้อมูลครบแล้ว: {args.gesture} / {args.signer} / {args.session} "
            f"({current}/{target} คลิป) — ใช้โหมด extra หากต้องการถ่ายเพิ่ม"
        )
        return 0
    capture_limit = target - current if args.mode == "standard" else 1

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
        captured = 0
        while captured < capture_limit:
            wait_seconds = 3 if first_clip else 1
            if not countdown(camera, args.gesture, wait_seconds):
                break
            sequence, preview_frames = collect_clip(
                camera,
                detector,
                sequence_length,
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
                    notes=(
                        "คลิปวัดผู้ใช้ใหม่ รอตรวจคุณภาพก่อนวัดผล"
                        if args.external_evaluation
                        else "คลิปถ่ายเพิ่ม รอตรวจคุณภาพก่อนนำไปเทรน"
                        if args.mode == "extra"
                        else "คลิปถ่ายใหม่ รอตรวจคุณภาพก่อนนำไปเทรน"
                        if args.mode == "retake"
                        else "รอตรวจคุณภาพก่อนนำไปเทรน"
                    ),
                    capture_mode=args.mode,
                    supersedes_clip_id=(
                        args.retake_clip if args.mode == "retake" else ""
                    ),
                )
            )
            if args.mode == "retake":
                store.mark_superseded(args.retake_clip, clip_id)
            current += 1
            captured += 1
            first_clip = False
            print(
                f"{args.gesture} / {args.signer} / {args.session}: "
                + (
                    f"เพิ่มแล้ว {captured}/{capture_limit} คลิป (pending)"
                    if args.mode != "standard"
                    else f"{current}/{target} (pending)"
                )
            )
    finally:
        detector.close()
        camera.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
