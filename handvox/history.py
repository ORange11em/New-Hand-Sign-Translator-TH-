"""Persistent conversation history for the sentence builder."""

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import uuid

from handvox.errors import DataFileError
from handvox.paths import HISTORY_FILE


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    created_at: str
    text: str
    source: str = "manual"

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise DataFileError("รายการประวัติต้องเป็น object")
        try:
            entry = cls(
                id=str(data["id"]),
                created_at=str(data["created_at"]),
                text=str(data["text"]).strip(),
                source=str(data.get("source", "manual")),
            )
        except KeyError as error:
            raise DataFileError(f"ประวัติขาดฟิลด์ {error}") from error
        if not entry.id or not entry.created_at or not entry.text:
            raise DataFileError("รายการประวัติมีข้อมูลว่าง")
        return entry


class HistoryStore:
    def __init__(self, path=HISTORY_FILE):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DataFileError(f"อ่าน {self.path.name} ไม่ได้: {error}") from error
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise DataFileError("ประวัติการสนทนาต้องเป็นรายการ")
        return [HistoryEntry.from_dict(item) for item in items]

    def add(self, text, source="manual", limit=100):
        text = str(text).strip()
        if not text:
            return None
        entries = self.load()
        entry = HistoryEntry(
            id=uuid.uuid4().hex,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            text=text,
            source=source,
        )
        entries.insert(0, entry)
        self.save(entries[: int(limit)])
        return entry

    def delete(self, entry_id):
        entries = self.load()
        filtered = [entry for entry in entries if entry.id != entry_id]
        if len(filtered) == len(entries):
            return False
        self.save(filtered)
        return True

    def clear(self):
        self.save([])

    def save(self, entries):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"version": 1, "items": [asdict(entry) for entry in entries]}
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
