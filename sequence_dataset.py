"""อ่าน เขียน นับ และลบคลิปการเคลื่อนไหวใน Dataset รุ่นเดิม."""

import shutil
from datetime import datetime
from pathlib import Path

import numpy as np

from body_features import FEATURE_COUNT


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "gesture_sequences.npz"
SEQUENCE_LENGTH = 30
CLIPS_PER_GESTURE = 30
LEGACY_FILES = (
    "gesture_data.csv",
    "gesture_model.pkl",
    "gesture_labels.pkl",
    "training_results.png",
)


def empty_dataset():
    """คืนอาร์เรย์ว่างที่มี shape และ dtype พร้อมนำไปต่อคลิป."""
    return (np.empty((0, SEQUENCE_LENGTH, FEATURE_COUNT), dtype=np.float32),
            np.empty((0,), dtype=str))


def load_dataset():
    """โหลด clips/labels หรือคืน Dataset ว่างเมื่อยังไม่มีไฟล์."""
    if not DATA_FILE.exists():
        return empty_dataset()
    with np.load(DATA_FILE, allow_pickle=False) as data:
        return data["clips"].astype(np.float32), data["labels"].astype(str)


def save_dataset(clips, labels):
    """บีบอัดและบันทึก Dataset รุ่นเดิมผ่านไฟล์ชั่วคราว."""
    temporary = DATA_FILE.with_suffix(".tmp.npz")
    np.savez_compressed(temporary, clips=clips.astype(np.float32), labels=labels.astype(str))
    temporary.replace(DATA_FILE)


def count_clips(name):
    """นับคลิปของชื่อท่าหนึ่งรายการ."""
    _, labels = load_dataset()
    return int(np.sum(labels == name))


def append_clip(name, clip):
    """ตรวจ shape แล้วต่อคลิปหนึ่งชุดเข้ากับ Dataset."""
    clips, labels = load_dataset()
    clip = np.asarray(clip, dtype=np.float32)
    if clip.shape != (SEQUENCE_LENGTH, FEATURE_COUNT):
        raise ValueError(f"Expected {SEQUENCE_LENGTH}x{FEATURE_COUNT} clip, got {clip.shape}")
    clips = np.concatenate((clips, clip.reshape(1, SEQUENCE_LENGTH, FEATURE_COUNT)))
    labels = np.concatenate((labels, np.array([name])))
    save_dataset(clips, labels)


def remove_gesture(name):
    """ตัดทุกคลิปของท่าที่ระบุและคืนจำนวนที่ถูกลบ."""
    clips, labels = load_dataset()
    keep = labels != name
    removed = int(np.sum(~keep))
    save_dataset(clips[keep], labels[keep])
    return removed


def archive_legacy_data():
    """ย้ายข้อมูลภาพนิ่งที่ใช้ร่วมกันไม่ได้ไปสำรอง โดยไม่ลบทิ้ง."""
    candidates = [ROOT / filename for filename in LEGACY_FILES if (ROOT / filename).exists()]
    if not candidates:
        return None
    backup_dir = ROOT / "gesture_backups" / (
        "frame_data_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    for source in candidates:
        shutil.move(source, backup_dir / source.name)
    return backup_dir
