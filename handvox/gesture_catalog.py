"""Read active gestures and manage the separate planned vocabulary catalog."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from handvox.errors import DataFileError
from handvox.paths import CUSTOM_GESTURES_FILE, PLANNED_GESTURES_FILE


PLANNED_STATUSES = ("planned", "verified", "collected", "trained")


@dataclass(frozen=True)
class ActiveGesture:
    name: str
    description: str
    color: tuple


@dataclass
class PlannedGesture:
    id: str
    name: str
    category: str
    priority: int = 3
    reference_url: str = ""
    status: str = "planned"
    notes: str = ""

    def validate(self):
        self.id = self.id.strip().lower()
        self.name = self.name.strip()
        self.category = self.category.strip()
        self.reference_url = self.reference_url.strip()
        self.status = self.status.strip()
        self.notes = self.notes.strip()
        if not self.id or not self.name or not self.category:
            raise DataFileError("ท่าที่วางแผนต้องมีรหัส ชื่อ และหมวดหมู่")
        if not self.id.replace("_", "").isalnum() or not self.id.isascii():
            raise DataFileError("รหัสใช้ได้เฉพาะ a-z, 0-9 และขีดล่าง")
        if not isinstance(self.priority, int) or not 1 <= self.priority <= 5:
            raise DataFileError("ลำดับความสำคัญต้องอยู่ระหว่าง 1 ถึง 5")
        if self.status not in PLANNED_STATUSES:
            raise DataFileError(
                f"สถานะต้องเป็นหนึ่งใน {', '.join(PLANNED_STATUSES)}"
            )
        if self.reference_url and not self.reference_url.startswith(("https://", "http://")):
            raise DataFileError("ลิงก์อ้างอิงต้องเริ่มด้วย https:// หรือ http://")
        return self

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise DataFileError("ข้อมูลท่าที่วางแผนต้องเป็น object")
        try:
            gesture = cls(
                id=str(data["id"]),
                name=str(data["name"]),
                category=str(data["category"]),
                priority=int(data.get("priority", 3)),
                reference_url=str(data.get("reference_url", "")),
                status=str(data.get("status", "planned")),
                notes=str(data.get("notes", "")),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise DataFileError(f"ข้อมูลท่าที่วางแผนไม่ถูกต้อง: {error}") from error
        return gesture.validate()


class GestureCatalog:
    def __init__(
        self,
        active_path=CUSTOM_GESTURES_FILE,
        planned_path=PLANNED_GESTURES_FILE,
    ):
        self.active_path = Path(active_path)
        self.planned_path = Path(planned_path)

    def load_active(self):
        if not self.active_path.exists():
            return []
        try:
            items = json.loads(self.active_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DataFileError(f"อ่าน {self.active_path.name} ไม่ได้: {error}") from error
        if not isinstance(items, list):
            raise DataFileError("custom_gestures.json ต้องเป็นรายการ")
        gestures = []
        for item in items:
            if not isinstance(item, dict):
                raise DataFileError("ข้อมูลท่าที่ใช้งานต้องเป็น object")
            name = str(item.get("name", "")).strip()
            description = str(item.get("description", name)).strip()
            color = item.get("color", [0, 220, 255])
            if not name or not isinstance(color, list) or len(color) != 3:
                raise DataFileError(f"ข้อมูลท่าที่ใช้งานไม่ถูกต้อง: {item}")
            try:
                normalized_color = tuple(int(value) for value in color)
            except (TypeError, ValueError) as error:
                raise DataFileError(f"ค่าสีของท่า {name} ไม่ถูกต้อง") from error
            gestures.append(ActiveGesture(name, description or name, normalized_color))
        return gestures

    def load_planned(self):
        if not self.planned_path.exists():
            return []
        try:
            payload = json.loads(self.planned_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DataFileError(f"อ่าน {self.planned_path.name} ไม่ได้: {error}") from error
        items = payload.get("gestures", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise DataFileError("planned_gestures.json ต้องเป็นรายการ")
        gestures = [PlannedGesture.from_dict(item) for item in items]
        ids = [gesture.id for gesture in gestures]
        names = [gesture.name for gesture in gestures]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise DataFileError("พบรหัสหรือชื่อท่าที่วางแผนซ้ำกัน")
        return sorted(gestures, key=lambda item: (item.priority, item.name))

    def save_planned(self, gestures):
        validated = [gesture.validate() for gesture in gestures]
        ids = [gesture.id for gesture in validated]
        names = [gesture.name for gesture in validated]
        active_names = {gesture.name for gesture in self.load_active()}
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise DataFileError("ห้ามใช้รหัสหรือชื่อท่าซ้ำกัน")
        overlap = active_names.intersection(names)
        if overlap:
            raise DataFileError(
                "ท่าที่วางแผนซ้ำกับท่าที่ใช้งานแล้ว: " + ", ".join(sorted(overlap))
            )
        self.planned_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.planned_path.with_suffix(self.planned_path.suffix + ".tmp")
        payload = {
            "version": 1,
            "gestures": [
                asdict(item)
                for item in sorted(
                    validated, key=lambda gesture: (gesture.priority, gesture.name)
                )
            ],
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.planned_path)

    def upsert_planned(self, gesture):
        gestures = self.load_planned()
        replaced = False
        for index, current in enumerate(gestures):
            if current.id == gesture.id:
                gestures[index] = gesture
                replaced = True
                break
        if not replaced:
            gestures.append(gesture)
        self.save_planned(gestures)

    def delete_planned(self, gesture_id):
        gestures = self.load_planned()
        filtered = [gesture for gesture in gestures if gesture.id != gesture_id]
        if len(filtered) == len(gestures):
            return False
        self.save_planned(filtered)
        return True

