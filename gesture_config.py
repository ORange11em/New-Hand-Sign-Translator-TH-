"""รายการท่ามือมาตรฐานของโปรเจกต์ HandVox.

แก้ไขชื่อ คำอธิบาย และสีของท่ามือจากไฟล์นี้เพียงจุดเดียว
แล้วเก็บข้อมูลและเทรนโมเดลใหม่ทุกครั้งเมื่อเปลี่ยนรายการท่า.

ท่าที่เพิ่มผ่าน Add_New_Gesture.bat จะถูกเก็บใน custom_gestures.json
โดยอัตโนมัติ จึงไม่จำเป็นต้องแก้ไขไฟล์นี้เอง.
"""

import json
from pathlib import Path

GESTURES = {}
GESTURE_COLORS = {}


def _load_custom_gestures():
    """Load gestures added through the guided add-gesture workflow."""
    custom_file = Path(__file__).with_name("custom_gestures.json")
    if not custom_file.exists():
        return

    try:
        entries = json.loads(custom_file.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("รายการท่าต้องเป็น list")

        for entry in entries:
            name = entry.get("name", "").strip()
            description = entry.get("description", "").strip()
            color = entry.get("color", (0, 220, 255))
            if (not name or not description or name in GESTURES or
                    not isinstance(color, list) or len(color) != 3 or
                    not all(isinstance(value, int) and 0 <= value <= 255
                            for value in color)):
                print(f"ข้ามข้อมูลท่าที่ไม่ถูกต้องใน {custom_file.name}: {entry}")
                continue
            GESTURES[name] = description
            GESTURE_COLORS[name] = tuple(color)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"อ่าน {custom_file.name} ไม่ได้: {error}")


_load_custom_gestures()
GESTURE_NAMES = list(GESTURES)
