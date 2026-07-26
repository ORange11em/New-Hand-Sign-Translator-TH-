"""Guided one-pass workflow for adding a HandVox gesture."""

import csv
import json
import subprocess
import sys
from pathlib import Path

from gesture_config import GESTURES


ROOT = Path(__file__).resolve().parent
CSV_FILE = ROOT / "gesture_data.csv"
CUSTOM_FILE = ROOT / "custom_gestures.json"
SAMPLES = 300
COLORS = [
    [0, 220, 255], [255, 120, 0], [0, 220, 100], [255, 0, 160],
    [180, 80, 255], [0, 180, 255], [120, 220, 0], [255, 200, 0],
]


def sample_count(name):
    if not CSV_FILE.exists():
        return 0
    with CSV_FILE.open("r", newline="", encoding="utf-8") as file:
        return sum(1 for row in csv.reader(file) if row and row[-1] == name)


def read_custom_gestures():
    if not CUSTOM_FILE.exists():
        return []
    try:
        entries = json.loads(CUSTOM_FILE.read_text(encoding="utf-8"))
        return entries if isinstance(entries, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_custom_gestures(entries):
    temporary_file = CUSTOM_FILE.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_file.replace(CUSTOM_FILE)


def ask_for_gesture():
    print("=" * 54)
    print("       HandVox - เพิ่มท่าใหม่แบบครั้งเดียว")
    print("=" * 54)
    print(f"เก็บตัวอย่าง {SAMPLES} ตัวอย่าง แล้วฝึกโมเดลให้ทันที\n")

    while True:
        name = input("ชื่อท่าใหม่: ").strip()
        if name:
            break
        print("กรุณาใส่ชื่อท่า")

    existing_count = sample_count(name)
    if name in GESTURES:
        if existing_count >= SAMPLES:
            print(f"\nท่า '{name}' มีตัวอย่างครบแล้ว ({existing_count})")
            return name, False
        print(f"\nพบท่า '{name}' อยู่แล้ว จะเก็บต่อจาก {existing_count}/{SAMPLES} ตัวอย่าง")
        return name, True

    while True:
        description = input("อธิบายวิธีทำท่า: ").strip()
        if description:
            break
        print("กรุณาใส่คำอธิบายสั้น ๆ")

    entries = read_custom_gestures()
    entries.append({
        "name": name,
        "description": description,
        "color": COLORS[len(entries) % len(COLORS)],
    })
    save_custom_gestures(entries)
    return name, True


def main():
    name, needs_collection = ask_for_gesture()
    if needs_collection:
        result = subprocess.run(
            [sys.executable, "collect_data.py", "--gesture", name], cwd=ROOT
        )
        if result.returncode != 0:
            print("\nการเก็บข้อมูลไม่สำเร็จ จึงยังไม่ได้ฝึกโมเดล")
            return result.returncode

    collected = sample_count(name)
    if collected < SAMPLES:
        print(f"\nเก็บได้ {collected}/{SAMPLES} ตัวอย่าง ยังไม่ฝึกโมเดล")
        print("เปิด Add_New_Gesture.bat อีกครั้ง แล้วใส่ชื่อเดิมเพื่อเก็บต่อ")
        return 1

    with CSV_FILE.open("r", newline="", encoding="utf-8") as file:
        gesture_count = len({row[-1] for row in list(csv.reader(file))[1:] if row})
    if gesture_count < 2:
        print("\nบันทึกท่าแรกแล้ว เพิ่มอีกอย่างน้อย 1 ท่าก่อนฝึกโมเดล")
        return 0

    print("\nกำลังฝึกโมเดล...")
    result = subprocess.run([sys.executable, "train_model.py"], cwd=ROOT)
    if result.returncode == 0:
        print("\nเสร็จแล้ว! เปิด Run_Detector.bat เพื่อทดสอบท่าใหม่ได้เลย")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
