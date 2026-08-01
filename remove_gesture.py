"""Remove a custom gesture and its recorded motion clips."""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sequence_dataset import DATA_FILE, count_clips, load_dataset, remove_gesture


ROOT = Path(__file__).resolve().parent
CUSTOM_FILE = ROOT / "custom_gestures.json"


def read_custom_gestures():
    if not CUSTOM_FILE.exists():
        return []
    try:
        entries = json.loads(CUSTOM_FILE.read_text(encoding="utf-8"))
        return entries if isinstance(entries, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_custom_gestures(entries):
    CUSTOM_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def backup():
    folder = ROOT / "gesture_backups" / ("remove_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    folder.mkdir(parents=True, exist_ok=False)
    for source in (CUSTOM_FILE, DATA_FILE):
        if source.exists():
            shutil.copy2(source, folder / source.name)
    return folder


def main():
    entries = read_custom_gestures()
    if not entries:
        print("ยังไม่มีท่าที่เพิ่มเองให้ลบ")
        return 0
    for index, entry in enumerate(entries, 1):
        name = entry.get("name", "")
        print(f"[{index}] {name} ({count_clips(name)} คลิป)")
    try:
        selected = input("เลือกหมายเลขท่าที่ต้องการลบ (Q เพื่อยกเลิก): ").strip()
    except EOFError:
        return 0
    if selected.lower() == "q":
        return 0
    try:
        name = entries[int(selected) - 1]["name"]
    except (ValueError, IndexError, KeyError):
        print("เลือกรายการไม่ถูกต้อง")
        return 1
    try:
        confirmed = input(f"พิมพ์ '{name}' เพื่อยืนยัน: ").strip()
    except EOFError:
        return 0
    if confirmed != name:
        print("ยกเลิก")
        return 0

    folder = backup()
    save_custom_gestures([entry for entry in entries if entry.get("name") != name])
    removed = remove_gesture(name)
    print(f"ลบ {name} จำนวน {removed} คลิปแล้ว | สำรองข้อมูล: {folder}")
    _, labels = load_dataset()
    if len(set(labels)) >= 2:
        return subprocess.run([sys.executable, "train_model.py"], cwd=ROOT).returncode
    print("เหลือท่าไม่พอสำหรับฝึกโมเดล จึงยังไม่สร้างโมเดลใหม่")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
