"""Safely remove a custom HandVox gesture, its samples, and retrain."""

import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CSV_FILE = ROOT / "gesture_data.csv"
CUSTOM_FILE = ROOT / "custom_gestures.json"
BACKUP_DIR = ROOT / "gesture_backups"


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


def count_samples(name):
    if not CSV_FILE.exists():
        return 0
    with CSV_FILE.open("r", newline="", encoding="utf-8") as file:
        return sum(1 for row in csv.reader(file) if row and row[-1] == name)


def create_backup():
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if CSV_FILE.exists():
        shutil.copy2(CSV_FILE, BACKUP_DIR / f"gesture_data_{stamp}.csv")
    if CUSTOM_FILE.exists():
        shutil.copy2(CUSTOM_FILE, BACKUP_DIR / f"custom_gestures_{stamp}.json")
    return BACKUP_DIR


def remove_samples(name):
    if not CSV_FILE.exists():
        return 0
    temporary_file = CSV_FILE.with_suffix(".tmp")
    removed = 0
    with (CSV_FILE.open("r", newline="", encoding="utf-8") as source,
          temporary_file.open("w", newline="", encoding="utf-8") as target):
        reader = csv.reader(source)
        writer = csv.writer(target)
        header = next(reader, None)
        if header:
            writer.writerow(header)
        for row in reader:
            if row and row[-1] == name:
                removed += 1
            else:
                writer.writerow(row)
    temporary_file.replace(CSV_FILE)
    return removed


def main():
    entries = read_custom_gestures()
    if not entries:
        print("ยังไม่มีท่าที่เพิ่มเองให้ลบ")
        return 0

    print("=" * 54)
    print("          HandVox - ลบท่าที่เพิ่มเอง")
    print("=" * 54)
    print("ท่าที่เพิ่มเอง:")
    for index, entry in enumerate(entries, start=1):
        name = entry.get("name", "")
        print(f"  [{index}] {name} ({count_samples(name)} ตัวอย่าง)")

    while True:
        try:
            selected = input(
                "\nเลือกหมายเลขท่าที่ต้องการลบ (หรือ Q เพื่อยกเลิก): "
            ).strip()
        except EOFError:
            print("\nยกเลิกการลบ")
            return 0
        if selected.lower() == "q":
            return 0
        try:
            entry = entries[int(selected) - 1]
            break
        except (ValueError, IndexError):
            print("กรุณาเลือกหมายเลขจากรายการ")

    name = entry["name"]
    try:
        confirmation = input(
            f"พิมพ์ชื่อท่า '{name}' เพื่อยืนยันการลบ: "
        ).strip()
    except EOFError:
        print("\nยกเลิกการลบ")
        return 0
    if confirmation != name:
        print("ยกเลิกการลบ")
        return 0

    backup_dir = create_backup()
    save_custom_gestures([item for item in entries if item.get("name") != name])
    removed = remove_samples(name)
    print(f"\nลบท่า '{name}' และตัวอย่าง {removed} รายการแล้ว")
    print(f"สำรองข้อมูลก่อนลบไว้ที่: {backup_dir}")

    print("\nกำลังฝึกโมเดลใหม่...")
    result = subprocess.run([sys.executable, "train_model.py"], cwd=ROOT)
    if result.returncode == 0:
        print("\nเสร็จแล้ว! เปิด Run_Detector.bat เพื่อใช้งานโมเดลใหม่")
    else:
        print("\nฝึกโมเดลไม่สำเร็จ แต่ข้อมูลก่อนลบอยู่ในโฟลเดอร์สำรอง")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
