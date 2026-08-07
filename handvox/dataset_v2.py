"""Metadata-first storage helpers for the future HandVox Dataset V2."""

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path

from handvox.errors import DataFileError
from handvox.paths import DATASET_V2_DIR


QUALITY_VALUES = ("pending", "accepted", "rejected")
LIGHTING_VALUES = ("unknown", "bright", "normal", "dim", "backlit")


@dataclass
class ClipMetadata:
    clip_id: str
    gesture_name: str
    signer_id: str
    session_id: str
    recorded_at: str
    camera_index: int
    lighting: str = "unknown"
    clip_number: int = 1
    quality: str = "pending"
    reference_url: str = ""
    sequence_file: str = ""
    preview_file: str = ""
    duration_frames: int = 30
    feature_count: int = 0
    dataset_version: int = 2
    notes: str = ""

    def validate(self):
        for name in ("clip_id", "gesture_name", "signer_id", "session_id", "recorded_at"):
            if not str(getattr(self, name)).strip():
                raise DataFileError(f"{name} ห้ามว่าง")
        try:
            datetime.fromisoformat(self.recorded_at)
        except ValueError as error:
            raise DataFileError("recorded_at ต้องเป็นเวลาแบบ ISO 8601") from error
        if not isinstance(self.camera_index, int) or self.camera_index < 0:
            raise DataFileError("camera_index ต้องเป็นจำนวนเต็มตั้งแต่ 0")
        if not isinstance(self.clip_number, int) or self.clip_number < 1:
            raise DataFileError("clip_number ต้องเป็นจำนวนเต็มตั้งแต่ 1")
        if not isinstance(self.duration_frames, int) or self.duration_frames < 1:
            raise DataFileError("duration_frames ต้องเป็นจำนวนเต็มตั้งแต่ 1")
        if not isinstance(self.feature_count, int) or self.feature_count < 0:
            raise DataFileError("feature_count ต้องเป็นจำนวนเต็มตั้งแต่ 0")
        if self.dataset_version != 2:
            raise DataFileError("dataset_version ต้องเป็น 2")
        if self.lighting not in LIGHTING_VALUES:
            raise DataFileError(
                f"lighting ต้องเป็นหนึ่งใน {', '.join(LIGHTING_VALUES)}"
            )
        if self.quality not in QUALITY_VALUES:
            raise DataFileError(f"quality ต้องเป็นหนึ่งใน {', '.join(QUALITY_VALUES)}")
        for field_name in ("sequence_file", "preview_file"):
            value = getattr(self, field_name)
            if value:
                path = Path(value)
                if path.is_absolute() or ".." in path.parts:
                    raise DataFileError(f"{field_name} ต้องเป็น path ภายใน Dataset V2")
        return self

    @classmethod
    def from_dict(cls, data):
        try:
            return cls(**data).validate()
        except (TypeError, KeyError) as error:
            raise DataFileError(f"metadata คลิปไม่ถูกต้อง: {error}") from error


class DatasetV2Store:
    def __init__(self, root=DATASET_V2_DIR):
        self.root = Path(root)
        self.manifest = self.root / "metadata.jsonl"
        self.clips_dir = self.root / "clips"

    def initialize(self):
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest.exists():
            self.manifest.write_text("", encoding="utf-8")

    def append(self, metadata):
        metadata.validate()
        self.initialize()
        if any(item.clip_id == metadata.clip_id for item in self.records()):
            raise DataFileError(f"clip_id ซ้ำ: {metadata.clip_id}")
        with self.manifest.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(asdict(metadata), ensure_ascii=False) + "\n")

    def save_records(self, records):
        validated = [record.validate() for record in records]
        ids = [record.clip_id for record in validated]
        if len(ids) != len(set(ids)):
            raise DataFileError("พบ clip_id ซ้ำใน metadata")
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest.with_suffix(".jsonl.tmp")
        content = "".join(
            json.dumps(asdict(record), ensure_ascii=False) + "\n"
            for record in validated
        )
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(self.manifest)

    def set_quality(self, clip_ids, quality):
        if quality not in QUALITY_VALUES:
            raise DataFileError(f"quality ต้องเป็นหนึ่งใน {', '.join(QUALITY_VALUES)}")
        selected = set(clip_ids)
        if not selected:
            return 0
        records = self.records()
        updated = 0
        for record in records:
            if record.clip_id in selected:
                record.quality = quality
                updated += 1
        if updated:
            self.save_records(records)
        return updated

    def resolve_data_path(self, relative_path):
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise DataFileError("path ต้องอยู่ภายใน Dataset V2")
        resolved = (self.root / path).resolve()
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as error:
            raise DataFileError("path ต้องอยู่ภายใน Dataset V2") from error
        return resolved

    def next_clip_number(self, gesture_name, signer_id, session_id):
        numbers = [
            item.clip_number
            for item in self.records()
            if item.gesture_name == gesture_name
            and item.signer_id == signer_id
            and item.session_id == session_id
        ]
        return max(numbers, default=0) + 1

    def records(self):
        if not self.manifest.exists():
            return []
        records = []
        for number, line in enumerate(
            self.manifest.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                records.append(ClipMetadata.from_dict(json.loads(line)))
            except (json.JSONDecodeError, DataFileError) as error:
                raise DataFileError(f"metadata.jsonl บรรทัด {number}: {error}") from error
        return records

    def summary(self):
        records = self.records()
        return {
            "clips": len(records),
            "gestures": dict(
                sorted(Counter(item.gesture_name for item in records).items())
            ),
            "signers": len({item.signer_id for item in records}),
            "sessions": len({item.session_id for item in records}),
            "quality": dict(sorted(Counter(item.quality for item in records).items())),
        }

    def inventory(self, classes=(), signers=()):
        records = self.records()
        class_names = tuple(classes) or tuple(
            sorted({record.gesture_name for record in records})
        )
        signer_names = tuple(signers) or tuple(sorted({record.signer_id for record in records}))
        rows = []
        for gesture_name in class_names:
            for signer_id in signer_names:
                relevant = [
                    record
                    for record in records
                    if record.gesture_name == gesture_name and record.signer_id == signer_id
                ]
                counts = Counter(record.quality for record in relevant)
                rows.append(
                    {
                        "gesture_name": gesture_name,
                        "signer_id": signer_id,
                        "accepted": counts["accepted"],
                        "pending": counts["pending"],
                        "rejected": counts["rejected"],
                        "total": len(relevant),
                        "sessions": len(
                            {
                                record.session_id
                                for record in relevant
                                if record.quality == "accepted"
                            }
                        ),
                    }
                )
        return rows
