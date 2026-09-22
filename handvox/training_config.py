"""โหลดและตรวจ training_config.json เพื่อให้การทดลอง Dataset V2 ทำซ้ำได้."""

from dataclasses import dataclass, replace
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
    minimum_prediction_confidence: float
    minimum_probability_margin: float


@dataclass(frozen=True)
class TrainingConfig:
    """คำตั้งต้น คลาสภายใน และค่ากระบวนการที่ใช้เพิ่มคำได้ต่อเนื่อง."""

    schema_version: int
    project_name: str
    visible_gestures: tuple[str, ...]
    internal_classes: tuple[str, ...]
    critical_gestures: tuple[str, ...]
    collection: CollectionConfig
    training: TrainingOptions
    acceptance: AcceptanceCriteria
    target_gesture: str = ""
    mode: str = "standard"

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
        if self.mode not in {"standard", "quick_trial"}:
            raise ConfigurationError("mode ต้องเป็น standard หรือ quick_trial")
        if self.target_gesture:
            if self.target_gesture not in self.visible_gestures:
                raise ConfigurationError("คำเป้าหมายต้องอยู่ใน visible_gestures ของรอบนี้")
            if not self.visible_gestures:
                raise ConfigurationError("รอบเพิ่มทีละคำต้องมีคำที่แสดงอย่างน้อย 1 ท่า")
        elif not self.visible_gestures:
            raise ConfigurationError("รายการคำตั้งต้นต้องมีอย่างน้อย 1 ท่า")
        if len(set(self.all_classes)) != len(self.all_classes):
            raise ConfigurationError("ชื่อคลาสใน training_config ห้ามซ้ำกัน")
        if self.mode == "standard":
            missing_internal = {"neutral", "unknown"}.difference(self.internal_classes)
            if missing_internal:
                raise ConfigurationError(
                    "โหมดมาตรฐานต้องมีคลาสภายใน neutral และ unknown "
                    f"(ยังขาด: {', '.join(sorted(missing_internal))})"
                )
        if self.mode == "quick_trial" and self.internal_classes:
            raise ConfigurationError("โหมดทดลองด่วนใช้เฉพาะคำที่แสดงและไม่มีคลาสภายใน")
        if len(self.collection.signers) != 2:
            raise ConfigurationError("แผน MVP นี้กำหนดสมาชิกเก็บข้อมูล 2 คน")
        if len(set(self.collection.signers)) != len(self.collection.signers):
            raise ConfigurationError("รหัสผู้ทำท่าห้ามซ้ำกัน")
        if not self.collection.sessions:
            raise ConfigurationError("ต้องกำหนด session อย่างน้อยหนึ่งรายการ")
        if len(set(self.collection.sessions)) != len(self.collection.sessions):
            raise ConfigurationError("รหัส session ห้ามซ้ำกัน")
        if self.collection.minimum_accepted_per_signer_per_class < 2:
            raise ConfigurationError("จำนวนคลิปขั้นต่ำต่อคนต่อคลาสต้องไม่น้อยกว่า 2")
        if (
            self.collection.target_clips_per_signer_per_class
            < self.collection.minimum_accepted_per_signer_per_class
        ):
            raise ConfigurationError("จำนวนคลิปเป้าหมายต้องไม่น้อยกว่าจำนวนขั้นต่ำ")
        if (
            self.collection.target_clips_per_signer_per_class
            < len(self.collection.sessions)
        ):
            raise ConfigurationError(
                "จำนวนคลิปเป้าหมายต้องไม่น้อยกว่าจำนวน session "
                "เพื่อให้แต่ละรอบมีข้อมูลอย่างน้อย 1 คลิป"
            )
        if self.collection.sequence_length <= 0:
            raise ConfigurationError("sequence_length ต้องมากกว่า 0")
        if self.training.algorithm not in {"SVC", "TCN"}:
            raise ConfigurationError("algorithm ต้องเป็น SVC หรือ TCN")
        if self.training.algorithm == "TCN":
            device = str(self.training.parameters.get("device", "auto")).strip().lower()
            valid_device = device in {"auto", "cpu", "cuda"}
            if device.startswith("cuda:"):
                try:
                    valid_device = int(device.split(":", 1)[1]) >= 0
                except ValueError:
                    valid_device = False
            if not valid_device:
                raise ConfigurationError(
                    "training.parameters.device ต้องเป็น auto, cpu, cuda หรือ cuda:N"
                )
            augmentation_copies = self.training.parameters.get(
                "augmentation_copies", 0
            )
            if (
                isinstance(augmentation_copies, bool)
                or not isinstance(augmentation_copies, int)
                or augmentation_copies < 0
            ):
                raise ConfigurationError(
                    "training.parameters.augmentation_copies ต้องเป็นจำนวนเต็มตั้งแต่ 0"
                )
        allowed_strategies = (
            {"grouped_signer_session_holdout"}
            if self.mode == "quick_trial"
            else {"leave_one_signer_out", "known_signers_session_holdout"}
        )
        if self.training.evaluation_strategy not in allowed_strategies:
            choices = ", ".join(sorted(allowed_strategies))
            raise ConfigurationError(f"โหมด {self.mode} ต้องประเมินแบบ {choices}")
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


def session_clip_target(config: TrainingConfig, session_id: str) -> int:
    """คืนเป้าหมายคลิปของหนึ่งรอบ โดยกระจายเศษให้รอบต้น ๆ อย่างสมดุล."""
    session = str(session_id).strip()
    sessions = config.collection.sessions
    if session not in sessions:
        raise ConfigurationError(f"ไม่พบ session ในแผนเก็บข้อมูล: {session}")
    target = config.collection.target_clips_per_signer_per_class
    base, remainder = divmod(target, len(sessions))
    return base + (1 if sessions.index(session) < remainder else 0)


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
                minimum_prediction_confidence=float(
                    acceptance.get("minimum_prediction_confidence", 0.72)
                ),
                minimum_probability_margin=float(
                    acceptance.get("minimum_probability_margin", 0.12)
                ),
            ),
            target_gesture=str(payload.get("target_gesture", "")).strip(),
            mode=str(payload.get("mode", "standard")).strip(),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"อ่าน training_config.json ไม่ได้: {error}") from error
    if not config.project_name:
        raise ConfigurationError("project_name ห้ามว่าง")
    return config.validate()


def incremental_targets(config=None, active_names=(), planned_names=()):
    """คืนทุกคำที่ยังไม่อยู่ในโมเดล ตามลำดับโดยไม่แบ่งคำหลัก/คำรอง."""
    config = config or load_training_config()
    active = {str(name).strip() for name in active_names}
    candidates = []
    for raw_name in (*config.visible_gestures, *planned_names):
        name = str(raw_name).strip()
        if name and name not in candidates:
            candidates.append(name)
    return tuple(name for name in candidates if name not in active)


def build_incremental_training_config(
    target_gesture,
    config=None,
    active_names=(),
    planned_names=(),
):
    """สร้างขอบเขตรอบเดียวจากคำเดิมทั้งหมด บวกคำใหม่หนึ่งคำและคลาสภายใน.

    โมเดลจำแนกหลายคลาสต้องฝึก artifact ใหม่จากข้อมูลสะสมของคำเดิมร่วมกับ
    คำเป้าหมาย แต่ผู้ใช้เก็บเพิ่มเฉพาะคำใหม่ในรอบถัด ๆ ไป
    """
    config = config or load_training_config()
    target = str(target_gesture).strip()
    active_order = []
    active = set()
    for raw_name in active_names:
        name = str(raw_name).strip()
        if name and name not in active:
            active.add(name)
            active_order.append(name)
    allowed_targets = set(config.visible_gestures).union(
        str(name).strip() for name in planned_names if str(name).strip()
    )
    if not target:
        raise ConfigurationError("กรุณาเลือกคำที่ต้องการเพิ่มในรอบนี้")
    if target not in allowed_targets:
        raise ConfigurationError(
            f"คำว่า {target} ยังไม่ได้บันทึกไว้ในคลังคำศัพท์"
        )
    if target in active:
        raise ConfigurationError(f"คำว่า {target} อยู่ในโมเดลปัจจุบันแล้ว")

    round_visible = tuple(active_order) + (target,)
    round_critical = tuple(
        name for name in config.critical_gestures if name in round_visible
    )
    return replace(
        config,
        project_name=f"{config.project_name} — เพิ่มคำ {target}",
        visible_gestures=round_visible,
        critical_gestures=round_critical,
        target_gesture=target,
    ).validate()


def build_quick_trial_config(
    target_gesture,
    config=None,
    active_names=(),
    planned_names=(),
):
    """สร้างขอบเขตทดลองด่วนจากคำในโมเดลปัจจุบันบวกคำใหม่หนึ่งคำ.

    โหมดนี้นำข้อมูลฐานเดิมมาใช้ฝึกเท่านั้น จึงไม่บังคับให้ถ่ายคำเดิมหรือ
    neutral ซ้ำ แล้วประเมินคำใหม่ด้วยกลุ่มผู้ทำท่า+รอบถ่ายที่ไม่ทับกัน
    ผลดังกล่าวเป็นผลเบื้องต้น ไม่ใช่ผลมาตรฐานสำหรับรายงานวิจัย
    """
    standard = build_incremental_training_config(
        target_gesture,
        config=config,
        active_names=active_names,
        planned_names=planned_names,
    )
    return replace(
        standard,
        project_name=f"{standard.project_name} — ทดลองด่วน",
        internal_classes=(),
        critical_gestures=(),
        training=replace(
            standard.training,
            evaluation_strategy="grouped_signer_session_holdout",
        ),
        mode="quick_trial",
    ).validate()
