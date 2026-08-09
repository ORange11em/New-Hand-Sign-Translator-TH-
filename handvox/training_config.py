"""โหลดและตรวจ training_config.json เพื่อให้การทดลอง Dataset V2 ทำซ้ำได้."""

from dataclasses import dataclass
import json
from pathlib import Path

from handvox.errors import ConfigurationError
from handvox.paths import TRAINING_CONFIG_FILE


@dataclass(frozen=True)
class CollectionConfig:
    """แผนผู้ทำท่า เซสชัน จำนวนคลิป และรูปแบบลำดับเฟรม."""

    signers: tuple[str, ...]
    sessions: tuple[str, ...]
    target_clips_per_signer_per_class: int
    minimum_accepted_per_signer_per_class: int
    sequence_length: int
    save_preview_video: bool


@dataclass(frozen=True)
class TrainingOptions:
    """ชื่ออัลกอริทึม พารามิเตอร์ วิธีแบ่งชุดทดสอบ และ seed."""

    algorithm: str
    parameters: dict
    evaluation_strategy: str
    random_seed: int


@dataclass(frozen=True)
class AcceptanceCriteria:
    """เกณฑ์ขั้นต่ำที่ experiment ต้องผ่านก่อนอนุญาตให้ติดตั้ง."""

    minimum_accuracy: float
    minimum_macro_f1: float
    minimum_class_recall: float
    minimum_critical_recall: float
    maximum_neutral_false_positive_rate: float


@dataclass(frozen=True)
class TrainingConfig:
    """ขอบเขตคำศัพท์ 16 ท่า คลาสภายใน และค่ากระบวนการทั้งหมด."""

    schema_version: int
    project_name: str
    visible_gestures: tuple[str, ...]
    internal_classes: tuple[str, ...]
    critical_gestures: tuple[str, ...]
    collection: CollectionConfig
    training: TrainingOptions
    acceptance: AcceptanceCriteria

    @property
    def all_classes(self):
        return self.visible_gestures + self.internal_classes

    @property
    def expected_clip_count(self):
        return (
            len(self.all_classes)
            * len(self.collection.signers)
            * self.collection.target_clips_per_signer_per_class
        )

    def validate(self):
        """ตรวจความสอดคล้องของแผนก่อนอ่าน Dataset หรือเริ่มเทรน."""
        if self.schema_version != 1:
            raise ConfigurationError("training_config schema_version ต้องเป็น 1")
        if len(self.visible_gestures) != 16:
            raise ConfigurationError("แผนนี้ต้องมีคำศัพท์ที่แสดงแก่ผู้ใช้ 16 ท่า")
        if len(set(self.all_classes)) != len(self.all_classes):
            raise ConfigurationError("ชื่อคลาสใน training_config ห้ามซ้ำกัน")
        if "neutral" not in self.internal_classes:
            raise ConfigurationError("ต้องมีคลาส neutral สำหรับลดการตรวจผิด")
        if len(self.collection.signers) != 2:
            raise ConfigurationError("แผน MVP นี้กำหนดสมาชิกเก็บข้อมูล 2 คน")
        if len(set(self.collection.signers)) != len(self.collection.signers):
            raise ConfigurationError("รหัสผู้ทำท่าห้ามซ้ำกัน")
        if not self.collection.sessions:
            raise ConfigurationError("ต้องกำหนด session อย่างน้อยหนึ่งรายการ")
        if self.collection.minimum_accepted_per_signer_per_class < 2:
            raise ConfigurationError("จำนวนคลิปขั้นต่ำต่อคนต่อคลาสต้องไม่น้อยกว่า 2")
        if (
            self.collection.target_clips_per_signer_per_class
            < self.collection.minimum_accepted_per_signer_per_class
        ):
            raise ConfigurationError("จำนวนคลิปเป้าหมายต้องไม่น้อยกว่าจำนวนขั้นต่ำ")
        if self.collection.sequence_length <= 0:
            raise ConfigurationError("sequence_length ต้องมากกว่า 0")
        if self.training.algorithm != "SVC":
            raise ConfigurationError("ขณะนี้รองรับ algorithm แบบ SVC เท่านั้น")
        if self.training.evaluation_strategy != "leave_one_signer_out":
            raise ConfigurationError("ต้องประเมินแบบ leave_one_signer_out")
        if not set(self.critical_gestures).issubset(self.visible_gestures):
            raise ConfigurationError("critical_gestures ต้องอยู่ใน visible_gestures")
        for name, value in vars(self.acceptance).items():
            if not 0.0 <= value <= 1.0:
                raise ConfigurationError(f"{name} ต้องอยู่ระหว่าง 0 ถึง 1")
        return self


def _nonempty_strings(values, field_name):
    """แปลง JSON list เป็น tuple ของข้อความที่ไม่มีค่าว่าง."""
    if not isinstance(values, list):
        raise ConfigurationError(f"{field_name} ต้องเป็นรายการ")
    result = tuple(str(value).strip() for value in values)
    if not result or any(not value for value in result):
        raise ConfigurationError(f"{field_name} ห้ามมีค่าว่าง")
    return result


def load_training_config(path=TRAINING_CONFIG_FILE):
    """โหลด JSON เป็น dataclass หลายชั้น แล้วตรวจแผนทั้งชุด."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        collection = payload["collection"]
        training = payload["training"]
        acceptance = payload["acceptance"]
        config = TrainingConfig(
            schema_version=int(payload["schema_version"]),
            project_name=str(payload["project_name"]).strip(),
            visible_gestures=_nonempty_strings(
                payload["visible_gestures"], "visible_gestures"
            ),
            internal_classes=_nonempty_strings(
                payload["internal_classes"], "internal_classes"
            ),
            critical_gestures=_nonempty_strings(
                payload["critical_gestures"], "critical_gestures"
            ),
            collection=CollectionConfig(
                signers=_nonempty_strings(collection["signers"], "collection.signers"),
                sessions=_nonempty_strings(collection["sessions"], "collection.sessions"),
                target_clips_per_signer_per_class=int(
                    collection["target_clips_per_signer_per_class"]
                ),
                minimum_accepted_per_signer_per_class=int(
                    collection["minimum_accepted_per_signer_per_class"]
                ),
                sequence_length=int(collection["sequence_length"]),
                save_preview_video=bool(collection["save_preview_video"]),
            ),
            training=TrainingOptions(
                algorithm=str(training["algorithm"]),
                parameters=dict(training["parameters"]),
                evaluation_strategy=str(training["evaluation_strategy"]),
                random_seed=int(training["random_seed"]),
            ),
            acceptance=AcceptanceCriteria(
                minimum_accuracy=float(acceptance["minimum_accuracy"]),
                minimum_macro_f1=float(acceptance["minimum_macro_f1"]),
                minimum_class_recall=float(acceptance["minimum_class_recall"]),
                minimum_critical_recall=float(acceptance["minimum_critical_recall"]),
                maximum_neutral_false_positive_rate=float(
                    acceptance["maximum_neutral_false_positive_rate"]
                ),
            ),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"อ่าน training_config.json ไม่ได้: {error}") from error
    if not config.project_name:
        raise ConfigurationError("project_name ห้ามว่าง")
    return config.validate()
