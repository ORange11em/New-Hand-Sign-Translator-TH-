"""ตรวจความพร้อม เทรน วัดผล สร้างรายงาน และติดตั้งโมเดล V2 อย่างปลอดภัย.

ไฟล์นี้ไม่ติดตั้งโมเดลทันทีหลังเทรน แต่สร้าง experiment แยกแต่ละรอบก่อน
การติดตั้งปกติต้องผ่านเกณฑ์ หรือยืนยันติดตั้งแบบทดลองแยกโดยไม่แก้คะแนน
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import pickle
import platform
import shutil
import subprocess
import time

import numpy as np

from body_features import FEATURE_COUNT
from handvox.dataset_v2 import DatasetV2Store
from handvox.errors import DataFileError, HandVoxError
from handvox.feature_pipeline import (
    AugmentationConfig,
    FEATURE_SCHEMA_VERSION,
    OUTPUT_FEATURE_COUNT,
    FeaturePipelineConfig,
    TemporalFeaturePipeline,
    schema_metadata,
)
from handvox.gesture_catalog import GestureCatalog
from handvox.paths import (
    CUSTOM_GESTURES_FILE,
    EXPERIMENTS_DIR,
    LABEL_FILE,
    LEGACY_DATA_FILE,
    MODEL_FILE,
    MODEL_MANIFEST_FILE,
    PLANNED_GESTURES_FILE,
    ROOT,
)
try:
    # paths.py รุ่นใหม่ประกาศตำแหน่งนี้โดยตรง ส่วน fallback ช่วยให้ checkout
    # ระหว่างการอัปเกรดยัง import workflow ได้โดยไม่ทำหน้าแอปล้ม
    from handvox.paths import TEMPORAL_MODEL_FILE
except ImportError:  # pragma: no cover - ใช้เฉพาะช่วงอัปเกรดไฟล์ paths เก่า
    TEMPORAL_MODEL_FILE = ROOT / "gesture_model.pt"
from handvox.temporal_model import (
    TemporalClassifier,
    TorchUnavailableError,
    is_torch_available,
    torch_unavailable_reason,
)
from handvox.training_config import TrainingConfig, load_training_config


@dataclass(frozen=True)
class ReadinessItem:
    """ผลตรวจหนึ่งเงื่อนไข พร้อมระดับสถานะ รหัส และข้อความสำหรับผู้ใช้."""

    status: str
    code: str
    message: str


@dataclass(frozen=True)
class ReadinessReport:
    """ภาพรวม preflight รวมจำนวนคลิป รายการปัญหา และ inventory."""

    ready: bool
    generated_at: str
    accepted_clips: int
    expected_target_clips: int
    items: tuple[ReadinessItem, ...]
    inventory: tuple[dict, ...]

    def to_dict(self):
        """แปลง dataclass ซ้อนเป็นข้อมูลที่เขียน JSON ได้."""
        return {
            "ready": self.ready,
            "generated_at": self.generated_at,
            "accepted_clips": self.accepted_clips,
            "expected_target_clips": self.expected_target_clips,
            "items": [asdict(item) for item in self.items],
            "inventory": list(self.inventory),
        }


# ── ขั้นที่ 1: ตรวจข้อมูลก่อนเทรน ──────────────────────────
def _reference_items(config: TrainingConfig):
    """ตรวจว่าท่าใหม่มีแหล่งอ้างอิงและผ่านการยืนยันรูปแบบท่าแล้ว."""
    active_names = {item.name for item in GestureCatalog().load_active()}
    planned = {item.name: item for item in GestureCatalog().load_planned()}
    issues = []
    for name in config.visible_gestures:
        if name in active_names:
            continue
        item = planned.get(name)
        if item is None:
            issues.append(
                ReadinessItem("error", "gesture_missing", f"ไม่พบคำว่า {name} ในแผนคำศัพท์")
            )
        elif not item.reference_url:
            issues.append(
                ReadinessItem(
                    "error",
                    "reference_missing",
                    f"คำว่า {name} ยังไม่มีลิงก์อ้างอิงภาษามือไทย",
                )
            )
        elif item.status == "planned":
            issues.append(
                ReadinessItem(
                    "error",
                    "reference_unverified",
                    f"คำว่า {name} ยังไม่ได้เปลี่ยนสถานะเป็น verified",
                )
            )
    return issues


def _training_records(config, records):
    return [
        record
        for record in records
        if record.gesture_name in config.all_classes
        and record.signer_id in config.collection.signers
    ]


def _validate_sequence_files(config, store, records):
    """ตรวจว่า accepted clips มีไฟล์จริง shape ถูก และไม่มี NaN/Infinity."""
    invalid = []
    missing = []
    accepted = [
        record
        for record in _training_records(config, records)
        if record.quality == "accepted"
    ]
    for record in accepted:
        if not record.sequence_file:
            missing.append(record.clip_id)
            continue
        path = store.resolve_data_path(record.sequence_file)
        if not path.exists():
            missing.append(record.clip_id)
            continue
        try:
            sequence = np.load(path, allow_pickle=False)
            expected = (config.collection.sequence_length, FEATURE_COUNT)
            if sequence.shape != expected or not np.isfinite(sequence).all():
                invalid.append(record.clip_id)
        except (OSError, ValueError):
            invalid.append(record.clip_id)
    items = []
    if missing:
        items.append(
            ReadinessItem(
                "error",
                "sequence_missing",
                f"คลิป accepted จำนวน {len(missing)} รายการไม่มีไฟล์ sequence",
            )
        )
    if invalid:
        items.append(
            ReadinessItem(
                "error",
                "sequence_invalid",
                f"คลิป accepted จำนวน {len(invalid)} รายการมี shape หรือค่าไม่ถูกต้อง",
            )
        )
    if accepted and not items:
        items.append(
            ReadinessItem(
                "ok", "sequence_valid", f"ไฟล์ sequence ผ่านการตรวจ {len(accepted)} คลิป"
            )
        )
    return items


def preflight(config=None, store=None):
    """รวมทุกกฎความพร้อม และไม่เริ่มเทรนหรือเปลี่ยนโมเดล."""
    config = config or load_training_config()
    store = store or DatasetV2Store()
    records = store.records()
    training_records = _training_records(config, records)
    inventory = store.inventory(config.all_classes, config.collection.signers)
    items = list(_reference_items(config))

    unexpected = sorted(
        {record.gesture_name for record in records}.difference(config.all_classes)
    )
    if unexpected:
        items.append(
            ReadinessItem(
                "warning",
                "unexpected_classes",
                "พบคลาสนอกแผน ซึ่งจะไม่ถูกนำไปเทรน: " + ", ".join(unexpected),
            )
        )

    unexpected_signers = sorted(
        {record.signer_id for record in records}.difference(config.collection.signers)
    )
    if unexpected_signers:
        items.append(
            ReadinessItem(
                "warning",
                "unexpected_signers",
                "เก็บผู้ทำท่านอกแผนไว้สำหรับวัดผลภายหลัง: "
                + ", ".join(unexpected_signers),
            )
        )

    unexpected_sessions = sorted(
        {
            record.session_id
            for record in training_records
            if record.quality == "accepted"
        }.difference(config.collection.sessions)
    )
    if unexpected_sessions:
        items.append(
            ReadinessItem(
                "error",
                "unexpected_sessions",
                "คลิปฝึกมี session นอกแผน กรุณาปรับแผนหรือ metadata ให้ตรงกัน: "
                + ", ".join(unexpected_sessions),
            )
        )
    if (
        config.training.algorithm == "SVC"
        and not config.training.parameters.get("probability", False)
    ):
        items.append(
            ReadinessItem(
                "error",
                "svc_probability_required",
                "โมเดล SVC สำหรับติดตั้งต้องตั้ง probability=true เพื่อใช้กับหน้ากล้อง",
            )
        )
    if (
        config.training.evaluation_strategy == "known_signers_session_holdout"
        and len(config.collection.sessions) < 3
    ):
        items.append(
            ReadinessItem(
                "error",
                "session_holdout_requires_three_sessions",
                "การวัดแบบกัน session ของผู้ใช้ที่เทรนไว้ต้องมีอย่างน้อย 3 session",
            )
        )

    minimum = config.collection.minimum_accepted_per_signer_per_class
    target = config.collection.target_clips_per_signer_per_class
    for row in inventory:
        label = f"{row['gesture_name']} / {row['signer_id']}"
        if row["accepted"] < minimum:
            items.append(
                ReadinessItem(
                    "error",
                    "accepted_below_minimum",
                    f"{label}: accepted {row['accepted']}/{minimum} คลิปขั้นต่ำ",
                )
            )
        elif row["accepted"] < target:
            items.append(
                ReadinessItem(
                    "warning",
                    "accepted_below_target",
                    f"{label}: accepted {row['accepted']}/{target} คลิปเป้าหมาย",
                )
            )
        required_sessions = len(config.collection.sessions)
        if row["accepted"] >= minimum and row["sessions"] < required_sessions:
            items.append(
                ReadinessItem(
                    "error",
                    "session_missing",
                    f"{label}: ต้องมี accepted ครบ {required_sessions} session "
                    f"(ตอนนี้ {row['sessions']})",
                )
            )

    counts = store.summary()["quality"]
    if counts.get("pending", 0):
        items.append(
            ReadinessItem(
                "warning",
                "pending_clips",
                f"มี {counts['pending']} คลิปที่ยังรอตรวจคุณภาพ",
            )
        )
    if counts.get("rejected", 0):
        items.append(
            ReadinessItem(
                "ok",
                "rejected_excluded",
                f"มี {counts['rejected']} คลิป rejected และจะไม่ถูกนำไปเทรน",
            )
        )

    items.extend(_validate_sequence_files(config, store, training_records))
    error_count = sum(item.status == "error" for item in items)
    accepted_count = sum(
        record.quality == "accepted" for record in training_records
    )
    if not records:
        items.append(
            ReadinessItem(
                "error", "dataset_empty", "Dataset V2 ยังไม่มีข้อมูล — ยังเทรนไม่ได้"
            )
        )
        error_count += 1
    if error_count == 0:
        items.insert(
            0,
            ReadinessItem(
                "ok", "ready", "ข้อมูลผ่านเงื่อนไขขั้นต่ำสำหรับเทรนและวัดผล"
            ),
        )
    return ReadinessReport(
        ready=error_count == 0,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        accepted_clips=accepted_count,
        expected_target_clips=config.expected_clip_count,
        items=tuple(items),
        inventory=tuple(inventory),
    )


def save_preflight_report(report, path):
    """เขียนผล preflight เป็น JSON สำหรับ GUI และหลักฐานในอนาคต."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _session_group_ids(signer_ids, session_ids):
    """สร้างรหัสกลุ่มจากผู้ทำท่าและรอบถ่าย โดยตรวจ metadata ให้ตรงกันก่อน."""
    signer_ids = np.asarray(signer_ids, dtype=str)
    session_ids = np.asarray(session_ids, dtype=str)
    if signer_ids.ndim != 1 or session_ids.ndim != 1:
        raise HandVoxError("signer_id และ session_id ต้องเป็นข้อมูลหนึ่งมิติต่อคลิป")
    if len(signer_ids) != len(session_ids):
        raise HandVoxError("จำนวน signer_id และ session_id ไม่ตรงกัน")
    if np.any(np.char.strip(signer_ids) == "") or np.any(
        np.char.strip(session_ids) == ""
    ):
        raise HandVoxError("ทุกคลิปต้องมี signer_id และ session_id ก่อนแบ่งชุดประเมิน")
    return np.asarray(
        [f"{signer}::{session}" for signer, session in zip(signer_ids, session_ids)],
        dtype=str,
    )


def _grouped_session_holdout(
    labels,
    signer_ids,
    session_ids,
    *,
    test_fraction=0.2,
    random_seed=42,
    require_all_signers=False,
):
    """แบ่ง holdout ด้วยกลุ่ม ``signer_id + session_id`` โดยไม่ให้กลุ่มรั่ว.

    แต่ละคลาสต้องปรากฏอย่างน้อยสองกลุ่ม เพื่อให้มีตัวอย่างของคลาสนั้นทั้ง
    train และ test หากทำไม่ได้จะหยุดพร้อมคำอธิบาย แทนการย้อนกลับไปสุ่มคลิป.
    """
    from itertools import combinations

    from sklearn.model_selection import GroupShuffleSplit

    labels = np.asarray(labels, dtype=str)
    signer_ids = np.asarray(signer_ids, dtype=str)
    groups = _session_group_ids(signer_ids, session_ids)
    if labels.ndim != 1 or len(labels) != len(groups):
        raise HandVoxError("จำนวนป้ายกำกับไม่ตรงกับ metadata ผู้ทำท่าและรอบถ่าย")
    if not 0 < test_fraction < 1:
        raise HandVoxError("test_fraction ต้องมากกว่า 0 และน้อยกว่า 1")

    class_names = sorted(set(labels.tolist()))
    unique_groups = sorted(set(groups.tolist()))
    if len(class_names) < 2:
        raise HandVoxError("ต้องมีอย่างน้อย 2 คลาสเพื่อประเมินโมเดล")
    if len(unique_groups) < 2:
        raise HandVoxError(
            "ต้องมีอย่างน้อย 2 กลุ่มผู้ทำท่าและรอบถ่ายเพื่อแบ่ง train/test"
        )
    insufficient = [
        name
        for name in class_names
        if len(set(groups[labels == name].tolist())) < 2
    ]
    if insufficient:
        raise HandVoxError(
            "ยังแบ่ง train/test ตามรอบถ่ายอย่างซื่อสัตย์ไม่ได้ เพราะคลาสต่อไปนี้ "
            "มีข้อมูลไม่ถึง 2 กลุ่ม: "
            + ", ".join(insufficient)
        )

    candidates = []
    # Dataset ของโครงงานมีเพียงไม่กี่กลุ่ม จึงลองทุกชุดเพื่อไม่พลาด split ที่ดี
    # ส่วน Dataset ที่ใหญ่กว่าจะสุ่มระดับกลุ่มหลายครั้งโดยยังไม่แตะระดับคลิป
    if len(unique_groups) <= 12:
        shuffled = np.asarray(unique_groups, dtype=str)
        np.random.default_rng(random_seed).shuffle(shuffled)
        for test_group_count in range(1, len(unique_groups)):
            for selected in combinations(shuffled.tolist(), test_group_count):
                test_mask = np.isin(groups, selected)
                candidates.append(
                    (np.flatnonzero(~test_mask), np.flatnonzero(test_mask))
                )
    else:
        splitter = GroupShuffleSplit(
            n_splits=512,
            test_size=test_fraction,
            random_state=random_seed,
        )
        candidates.extend(splitter.split(np.zeros(len(labels)), labels, groups))

    expected_classes = set(class_names)
    expected_signers = set(signer_ids.tolist())
    best = None
    for train_indices, test_indices in candidates:
        train_groups = set(groups[train_indices].tolist())
        test_groups = set(groups[test_indices].tolist())
        if train_groups.intersection(test_groups):
            continue
        if set(labels[train_indices].tolist()) != expected_classes:
            continue
        if set(labels[test_indices].tolist()) != expected_classes:
            continue
        if require_all_signers and (
            set(signer_ids[train_indices].tolist()) != expected_signers
            or set(signer_ids[test_indices].tolist()) != expected_signers
        ):
            continue
        # เลือก split ที่สัดส่วนจำนวนคลิปและแต่ละคลาสใกล้เป้าหมายที่สุด
        score = abs((len(test_indices) / len(labels)) - test_fraction)
        for name in class_names:
            class_mask = labels == name
            class_test_fraction = np.isin(
                np.flatnonzero(class_mask), test_indices
            ).sum() / int(class_mask.sum())
            score += abs(class_test_fraction - test_fraction)
        candidate = (score, tuple(sorted(test_groups)), train_indices, test_indices)
        if best is None or candidate[:2] < best[:2]:
            best = candidate

    if best is None:
        requirement = (
            " และมีข้อมูลของผู้ทำทุกคนทั้งสองชุด"
            if require_all_signers
            else ""
        )
        raise HandVoxError(
            "ไม่พบวิธีแบ่ง train/test ตามผู้ทำท่าและรอบถ่ายที่ทำให้ทุกคลาส "
            f"อยู่ทั้งสองชุด{requirement} กรุณาเก็บคลาสที่ขาดในรอบถ่ายอื่นเพิ่ม"
        )
    train_indices, test_indices = best[2], best[3]
    return train_indices, test_indices, groups


def _known_signers_session_holdout_folds(config, labels, signers, sessions):
    """คืน fold ที่กันแต่ละ session ของผู้ใช้ที่เทรนไว้เป็น test ครั้งละรอบ.

    ทุก fold มีข้อมูลของผู้ทำทุกคนใน train, validation และ test แต่กลุ่ม
    ``signer_id + session_id`` จะอยู่ได้เพียงชุดเดียว และทุกคลิปจะถูกทดสอบ
    เพียงครั้งเดียว จึงใช้ผลรวมเป็นคะแนนติดตั้งสำหรับผู้ใช้กลุ่มเดิมได้.
    """

    labels = np.asarray(labels, dtype=str)
    signers = np.asarray(signers, dtype=str)
    sessions = np.asarray(sessions, dtype=str)
    groups = _session_group_ids(signers, sessions)
    if labels.ndim != 1 or len(labels) != len(groups):
        raise HandVoxError("จำนวนป้ายกำกับไม่ตรงกับ metadata ผู้ทำท่าและรอบถ่าย")
    expected_signers = set(config.collection.signers)
    expected_classes = set(labels.tolist())
    ordered_sessions = tuple(config.collection.sessions)
    if len(ordered_sessions) < 3:
        raise HandVoxError(
            "การวัดแบบกัน session ของผู้ใช้ที่เทรนไว้ ต้องมีอย่างน้อย 3 session"
        )
    if set(signers.tolist()) != expected_signers:
        raise HandVoxError("ข้อมูลผู้ทำท่าไม่ตรงกับแผนการเทรน")
    unexpected_sessions = sorted(set(sessions.tolist()).difference(ordered_sessions))
    if unexpected_sessions:
        raise HandVoxError(
            "คลิปฝึกมี session นอกแผน: " + ", ".join(unexpected_sessions)
        )

    folds = []
    for index, test_session in enumerate(ordered_sessions):
        validation_session = ordered_sessions[(index + 1) % len(ordered_sessions)]
        test_indices = np.flatnonzero(sessions == test_session)
        validation_indices = np.flatnonzero(sessions == validation_session)
        train_indices = np.flatnonzero(
            (sessions != test_session) & (sessions != validation_session)
        )
        partitions = (train_indices, validation_indices, test_indices)
        if any(
            set(signers[partition].tolist()) != expected_signers
            or set(labels[partition].tolist()) != expected_classes
            for partition in partitions
        ):
            raise HandVoxError(
                "แต่ละ session ต้องมีทุกผู้ทำท่าและทุกคลาสก่อนวัดผลติดตั้ง"
            )
        partition_groups = [set(groups[partition].tolist()) for partition in partitions]
        if (
            partition_groups[0].intersection(partition_groups[1])
            or partition_groups[0].intersection(partition_groups[2])
            or partition_groups[1].intersection(partition_groups[2])
        ):
            raise HandVoxError(
                "พบกลุ่มผู้ทำท่าและรอบถ่ายซ้ำระหว่าง train/validation/test"
            )
        folds.append(
            {
                "name": f"known_signers_session_{test_session}",
                "train_indices": train_indices,
                "validation_indices": validation_indices,
                "test_indices": test_indices,
            }
        )
    return folds, groups


def quick_trial_readiness(config=None, store=None, minimum_target_clips=4):
    """ตรวจเฉพาะสิ่งที่จำเป็นสำหรับเทรนทดลองด่วนหนึ่งคำ.

    คำเดิมต้องมีอยู่ในข้อมูลฐาน ``gesture_sequences.npz`` ส่วนคำใหม่ใช้คลิป
    accepted จาก Dataset V2 อย่างน้อย ``minimum_target_clips`` คลิป
    """
    config = config or load_training_config()
    store = store or DatasetV2Store()
    target = config.target_gesture
    # โหมดด่วนยอมให้ลองก่อนยืนยันแหล่งอ้างอิง แต่ยังแสดงคำเตือนชัดเจน
    items = [
        ReadinessItem("warning", item.code, item.message)
        for item in _reference_items(config)
    ]
    base_count = 0
    base_labels = np.asarray([], dtype=str)
    if not LEGACY_DATA_FILE.exists():
        items.append(
            ReadinessItem("error", "base_dataset_missing", "ไม่พบข้อมูลฐาน gesture_sequences.npz")
        )
    else:
        try:
            with np.load(LEGACY_DATA_FILE, allow_pickle=False) as data:
                clips = data["clips"]
                base_labels = data["labels"].astype(str)
                if {"signer_ids", "session_ids"}.issubset(data.files):
                    base_signers = data["signer_ids"].astype(str)
                    base_sessions = data["session_ids"].astype(str)
                else:
                    base_signers = base_sessions = None
            expected_shape = (config.collection.sequence_length, FEATURE_COUNT)
            if clips.ndim != 3 or tuple(clips.shape[1:]) != expected_shape:
                raise ValueError(f"shape ต้องเป็น (จำนวนคลิป, {expected_shape[0]}, {expected_shape[1]})")
            if base_signers is None:
                items.append(
                    ReadinessItem(
                        "warning",
                        "base_group_metadata_missing",
                        "ข้อมูลฐานเดิมไม่มี signer_ids/session_ids — จะใช้คำเดิมเพื่อฝึกเท่านั้น "
                        "และวัดผลเบื้องต้นเฉพาะคำใหม่จากกลุ่มผู้ทำท่า/รอบถ่ายจริง "
                        "ผลนี้ไม่ใช่ค่าความแม่นยำรวมสำหรับรายงานวิจัย",
                    )
                )
            elif len(base_signers) != len(base_labels) or len(base_sessions) != len(base_labels):
                items.append(
                    ReadinessItem(
                        "error",
                        "base_group_metadata_invalid",
                        "จำนวน signer_ids/session_ids ในข้อมูลฐานไม่ตรงกับจำนวนคลิป",
                    )
                )
            elif np.any(np.char.strip(base_signers) == "") or np.any(
                np.char.strip(base_sessions) == ""
            ):
                items.append(
                    ReadinessItem(
                        "warning",
                        "base_group_metadata_incomplete",
                        "ข้อมูลฐานบางคลิปไม่ทราบผู้ทำท่าหรือรอบถ่าย — "
                        "คลิปฐานทั้งหมดจะใช้ฝึกเท่านั้น และไม่ปะปนในชุดทดสอบคำใหม่",
                    )
                )
            missing_base = [
                name
                for name in config.visible_gestures
                if name != target and name not in set(base_labels.tolist())
            ]
            if missing_base:
                items.append(
                    ReadinessItem(
                        "error",
                        "base_classes_missing",
                        "ข้อมูลฐานยังไม่มีคำเดิม: " + ", ".join(missing_base),
                    )
                )
            else:
                base_count = int(
                    np.isin(base_labels, [name for name in config.visible_gestures if name != target]).sum()
                )
                items.append(
                    ReadinessItem(
                        "ok",
                        "base_dataset_ready",
                        f"ใช้ข้อมูลฐานคำเดิมได้ {base_count} คลิป — ไม่ต้องถ่ายคำเดิมซ้ำ",
                    )
                )
        except (OSError, KeyError, TypeError, ValueError) as error:
            items.append(
                ReadinessItem("error", "base_dataset_invalid", f"ข้อมูลฐานอ่านไม่ได้: {error}")
            )

    target_records = [
        record
        for record in _training_records(config, store.records())
        if record.gesture_name == target and record.quality == "accepted"
    ]
    items.extend(_validate_sequence_files(config, store, target_records))
    if len(target_records) < minimum_target_clips:
        items.append(
            ReadinessItem(
                "error",
                "quick_target_below_minimum",
                f"คำว่า {target}: accepted {len(target_records)}/{minimum_target_clips} คลิปขั้นต่ำสำหรับทดลองด่วน",
            )
        )
    else:
        items.append(
            ReadinessItem(
                "ok",
                "quick_target_ready",
                f"คำว่า {target}: ใช้ accepted {len(target_records)} คลิปสำหรับทดลองด่วน",
            )
        )
        target_groups = {
            f"{record.signer_id}::{record.session_id}" for record in target_records
        }
        if len(target_groups) < 2:
            items.append(
                ReadinessItem(
                    "error",
                    "quick_target_session_groups_missing",
                    f"คำว่า {target}: ต้องมี accepted จากอย่างน้อย 2 กลุ่มผู้ทำท่าและรอบถ่าย",
                )
            )
    error_count = sum(item.status == "error" for item in items)
    if error_count == 0:
        items.insert(
            0,
            ReadinessItem(
                "ok",
                "quick_ready",
                "พร้อมเทรนทดลองด่วน — ผลที่ได้เป็นผลเบื้องต้นและเปิดกล้องทดสอบจริงได้",
            ),
        )
    return ReadinessReport(
        ready=error_count == 0,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        accepted_clips=base_count + len(target_records),
        expected_target_clips=base_count + max(minimum_target_clips, len(target_records)),
        items=tuple(items),
        inventory=tuple(store.inventory((target,), config.collection.signers)),
    )


# ── ขั้นที่ 2: โหลดข้อมูลและคำนวณตัวชี้วัด ──────────────────
def _dataset_fingerprint(store, records):
    """สร้าง SHA-256 จาก metadata และไฟล์ sequence เพื่อระบุ Dataset รุ่นนี้."""
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: item.clip_id):
        digest.update(
            json.dumps(asdict(record), ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        if record.sequence_file:
            path = store.resolve_data_path(record.sequence_file)
            if path.exists():
                with path.open("rb") as file:
                    while chunk := file.read(1024 * 1024):
                        digest.update(chunk)
    return digest.hexdigest()


def _load_accepted_arrays(config, store):
    """โหลดเฉพาะคลิป accepted แล้วคืน features, labels, signers และ sessions."""
    records = [
        item
        for item in _training_records(config, store.records())
        if item.quality == "accepted"
    ]
    unexpected_sessions = sorted(
        {item.session_id for item in records}.difference(config.collection.sessions)
    )
    if unexpected_sessions:
        raise HandVoxError(
            "คลิปฝึกมี session นอกแผน: " + ", ".join(unexpected_sessions)
        )
    records.sort(key=lambda item: item.clip_id)
    clips = []
    labels = []
    signers = []
    sessions = []
    for record in records:
        sequence = np.load(
            store.resolve_data_path(record.sequence_file), allow_pickle=False
        ).astype(np.float32)
        clips.append(sequence.reshape(-1))
        labels.append(record.gesture_name)
        signers.append(record.signer_id)
        sessions.append(record.session_id)
    return (
        np.asarray(clips, dtype=np.float32),
        np.asarray(labels, dtype=str),
        np.asarray(signers, dtype=str),
        np.asarray(sessions, dtype=str),
        records,
    )


def _metric_payload(true_values, predictions, class_ids, class_names):
    """คำนวณ Accuracy, Precision, Recall, F1 และ Confusion Matrix."""
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    precision, recall, f1, support = precision_recall_fscore_support(
        true_values,
        predictions,
        labels=class_ids,
        zero_division=0,
    )
    macro = precision_recall_fscore_support(
        true_values, predictions, average="macro", zero_division=0
    )
    weighted = precision_recall_fscore_support(
        true_values, predictions, average="weighted", zero_division=0
    )
    per_class = [
        {
            "class_name": name,
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }
        for index, name in enumerate(class_names)
    ]
    return {
        "accuracy": float(accuracy_score(true_values, predictions)),
        "macro_precision": float(macro[0]),
        "macro_recall": float(macro[1]),
        "macro_f1": float(macro[2]),
        "weighted_precision": float(weighted[0]),
        "weighted_recall": float(weighted[1]),
        "weighted_f1": float(weighted[2]),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(
            true_values, predictions, labels=class_ids
        ).astype(int).tolist(),
    }


def _predictions_with_recognition_policy(probabilities, class_names, config):
    """แปลง probability เป็นคำทำนายโดยใช้ด่านปฏิเสธเดียวกับหน้ากล้อง.

    เมื่อโมเดลเลือกคำที่แสดงอยู่ แต่ confidence หรือระยะห่างจากอันดับสอง
    ไม่ถึงค่าปลอดภัย จะนับเป็น ``unknown`` แทนการปล่อย false activation.
    """

    probabilities = np.asarray(probabilities, dtype=np.float64)
    names = np.asarray(class_names, dtype=str)
    if (
        names.ndim != 1
        or not len(names)
        or len(set(names.tolist())) != len(names)
        or probabilities.ndim != 2
        or probabilities.shape[1] != len(names)
        or not np.isfinite(probabilities).all()
        or np.any(probabilities < 0)
        or np.any(probabilities > 1)
        or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-5)
    ):
        raise HandVoxError("probability ของโมเดลไม่ตรงกับจำนวนคลาส")
    if "unknown" not in names:
        return names[np.argmax(probabilities, axis=1)]
    best_indices = np.argmax(probabilities, axis=1)
    predictions = names[best_indices].copy()
    best_probabilities = probabilities[np.arange(len(probabilities)), best_indices]
    second_best = (
        np.partition(probabilities, -2, axis=1)[:, -2]
        if len(names) > 1
        else np.zeros(len(probabilities), dtype=np.float64)
    )
    margins = best_probabilities - second_best
    visible = np.isin(predictions, list(config.visible_gestures))
    rejected = visible & (
        (best_probabilities < config.acceptance.minimum_prediction_confidence)
        | (margins < config.acceptance.minimum_probability_margin)
    )
    predictions[rejected] = "unknown"
    return predictions


# ── ขั้นที่ 3: ส่งออกตาราง กราฟ และข้อมูลเวอร์ชัน ───────────
def _write_csv(path, fieldnames, rows):
    """เขียน CSV แบบ UTF-8 with BOM เพื่อเปิดภาษาไทยใน Excel ได้ง่าย."""
    with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_confusion_csv(path, class_names, matrix):
    """แปลง Confusion Matrix เป็นตารางที่มีชื่อคลาสทั้งแถวและคอลัมน์."""
    rows = []
    for true_name, values in zip(class_names, matrix):
        row = {"actual\\predicted": true_name}
        row.update({name: value for name, value in zip(class_names, values)})
        rows.append(row)
    _write_csv(path, ["actual\\predicted", *class_names], rows)


def _write_plots(experiment_dir, class_names, metrics):
    """สร้างภาพ Confusion Matrix และกราฟ F1 แยกคลาสโดยไม่เปิดหน้าต่าง."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import seaborn as sns

    font_path = Path("C:/Windows/Fonts/tahoma.ttf")
    font = font_manager.FontProperties(fname=str(font_path)) if font_path.exists() else None
    matrix = np.asarray(metrics["confusion_matrix"])
    figure, axis = plt.subplots(figsize=(13, 11))
    sns.heatmap(matrix, annot=True, fmt="d", cmap="Blues", cbar=False, ax=axis)
    axis.set_xticklabels(class_names, rotation=45, ha="right", fontproperties=font)
    axis.set_yticklabels(class_names, rotation=0, fontproperties=font)
    axis.set_xlabel("ค่าที่โมเดลทำนาย", fontproperties=font)
    axis.set_ylabel("ค่าจริง", fontproperties=font)
    axis.set_title("HandVox Confusion Matrix", fontproperties=font)
    figure.tight_layout()
    figure.savefig(experiment_dir / "confusion_matrix.png", dpi=180)
    plt.close(figure)

    per_class = metrics["per_class"]
    figure, axis = plt.subplots(figsize=(13, 6))
    axis.bar([row["class_name"] for row in per_class], [row["f1"] for row in per_class])
    axis.set_ylim(0, 1)
    axis.set_ylabel("F1 score")
    axis.set_title("F1 แยกตามท่า", fontproperties=font)
    for label in axis.get_xticklabels():
        label.set_rotation(45)
        label.set_ha("right")
        if font:
            label.set_fontproperties(font)
    figure.tight_layout()
    figure.savefig(experiment_dir / "per_class_f1.png", dpi=180)
    plt.close(figure)


def _version_info():
    """บันทึกเวอร์ชัน Python/ไลบรารี/ระบบและ git commit เพื่อทำซ้ำผล."""
    import sklearn

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        git_commit = result.stdout.strip() if result.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        git_commit = "unknown"
    versions = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "git_commit": git_commit,
    }
    if is_torch_available():
        import torch

        versions.update(
            {
                "pytorch": torch.__version__,
                "cuda_available": bool(torch.cuda.is_available()),
                "cuda_runtime": str(torch.version.cuda or "none"),
                "cuda_device_count": int(torch.cuda.device_count())
                if torch.cuda.is_available()
                else 0,
                "cuda_devices": [
                    torch.cuda.get_device_name(index)
                    for index in range(torch.cuda.device_count())
                ]
                if torch.cuda.is_available()
                else [],
            }
        )
    else:
        versions.update(
            {
                "pytorch": "unavailable",
                "cuda_available": False,
                "cuda_runtime": "unavailable",
                "cuda_device_count": 0,
                "cuda_devices": [],
                "pytorch_unavailable_reason": torch_unavailable_reason(),
            }
        )
    return versions


def _evaluated_recognition_policy(config):
    if config.mode != "standard" or "unknown" not in config.internal_classes:
        return {}
    if (
        config.training.algorithm == "SVC"
        and not config.training.parameters.get("probability", False)
    ):
        return {}
    return {
        "minimum_confidence": config.acceptance.minimum_prediction_confidence,
        "minimum_probability_margin": config.acceptance.minimum_probability_margin,
    }


def _manifest(
    config,
    metrics,
    experiment_id,
    *,
    model_backend=None,
    model_artifact=None,
    feature_schema=None,
    model_metadata=None,
):
    """สร้างรายการท่าที่โมเดลใหม่ใช้สำหรับติดตั้งและตัวตรวจจับ."""
    active = {item.name: item for item in GestureCatalog().load_active()}
    planned = {item.name: item for item in GestureCatalog().load_planned()}
    default_colors = (
        [0, 220, 255], [0, 220, 100], [255, 0, 160], [255, 120, 0],
        [180, 80, 255], [0, 180, 255], [120, 220, 0], [255, 200, 0],
    )
    visible = []
    for index, name in enumerate(config.visible_gestures):
        if name in active:
            item = active[name]
            description = item.description
            color = list(item.color)
        else:
            item = planned.get(name)
            description = item.notes if item and item.notes else name
            color = default_colors[index % len(default_colors)]
        visible.append({"name": name, "description": description, "color": color})
    backend = model_backend or (
        "temporal_tcn" if config.training.algorithm == "TCN" else "svc"
    )
    artifact = model_artifact or ("model.pt" if backend == "temporal_tcn" else "model.pkl")
    resolved_feature_schema = feature_schema or {
        "schema_version": "handvox.raw_landmarks.v1",
        "input_feature_count": FEATURE_COUNT,
        "output_feature_count": FEATURE_COUNT,
    }
    evaluation_scope = (
        "known_signers_session_holdout"
        if config.training.evaluation_strategy == "known_signers_session_holdout"
        else (
            "quick_trial"
            if config.mode == "quick_trial"
            else "cross_person_holdout"
        )
    )
    manifest = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model_backend": backend,
        "model_artifact": artifact,
        "model_file": artifact,
        "mode": config.mode,
        "training_signers": list(config.collection.signers)
        if config.mode == "standard" else [],
        "evaluation_strategy": config.training.evaluation_strategy,
        "evaluation_scope": evaluation_scope,
        "sequence_length": config.collection.sequence_length,
        "feature_schema_version": resolved_feature_schema["schema_version"],
        "feature_count": resolved_feature_schema["output_feature_count"],
        "feature_schema": resolved_feature_schema,
        "visible_gestures": visible,
        "internal_classes": list(config.internal_classes),
        "evaluation": {
            "strategy": config.training.evaluation_strategy,
            "scope": evaluation_scope,
            "accuracy": metrics["accuracy"],
            "macro_f1": metrics["macro_f1"],
            "passed": metrics["passed"],
        },
    }
    recognition_policy = _evaluated_recognition_policy(config)
    if recognition_policy:
        manifest["recognition_policy"] = recognition_policy
    if model_metadata:
        manifest["model_metadata"] = dict(model_metadata)
    return manifest


def _acceptance_result(config, metrics):
    """เทียบผลรวม รายคลาส และการเปิดคำผิดจาก neutral/unknown."""

    recalls = {row["class_name"]: row["recall"] for row in metrics["per_class"]}
    visible_recalls = [recalls[name] for name in config.visible_gestures]
    critical_recalls = [recalls[name] for name in config.critical_gestures]
    metric_class_names = [row["class_name"] for row in metrics["per_class"]]
    visible_indices = [
        metric_class_names.index(name)
        for name in config.visible_gestures
        if name in metric_class_names
    ]

    def visible_activation_rate(internal_name):
        if internal_name not in metric_class_names:
            return 0.0
        row = metrics["confusion_matrix"][metric_class_names.index(internal_name)]
        total = sum(row)
        return sum(row[index] for index in visible_indices) / total if total else 1.0

    neutral_false_positive_rate = visible_activation_rate("neutral")
    unknown_false_activation_rate = visible_activation_rate("unknown")
    metrics["unknown_false_activation_rate"] = float(
        unknown_false_activation_rate
    )
    checks = {
        "accuracy": metrics["accuracy"] >= config.acceptance.minimum_accuracy,
        "macro_f1": metrics["macro_f1"] >= config.acceptance.minimum_macro_f1,
        "minimum_visible_recall": min(visible_recalls, default=0)
        >= config.acceptance.minimum_class_recall,
        "minimum_critical_recall": (
            not critical_recalls
            or min(critical_recalls) >= config.acceptance.minimum_critical_recall
        ),
        "neutral_false_positive_rate": neutral_false_positive_rate
        <= config.acceptance.maximum_neutral_false_positive_rate,
        "unknown_false_activation_rate": unknown_false_activation_rate
        <= config.acceptance.maximum_neutral_false_positive_rate,
    }
    return all(checks.values()), checks, neutral_false_positive_rate


_TEMPORAL_CLASSIFIER_PARAMETERS = {
    "hidden_channels",
    "kernel_size",
    "dropout",
    "learning_rate",
    "weight_decay",
    "batch_size",
    "max_epochs",
    "patience",
    "min_delta",
    "validation_fraction",
    "device",
}
_TEMPORAL_PIPELINE_PARAMETERS = {
    "max_missing_gap",
    "trim_motion",
    "motion_threshold",
    "trim_padding",
    "minimum_trimmed_frames",
}


def _temporal_training_components(config):
    """แยกค่าตั้งโมเดล, feature pipeline และ augmentation อย่างตรวจสอบได้."""

    if not is_torch_available():
        raise HandVoxError(
            "ยังใช้โมเดล TCN ไม่ได้: "
            + torch_unavailable_reason()
            + " กรุณาติดตั้ง PyTorch รุ่นที่ตรงกับ CUDA ของเครื่อง"
        )
    parameters = dict(config.training.parameters)
    try:
        augmentation_copies = int(parameters.pop("augmentation_copies", 1))
    except (TypeError, ValueError) as error:
        raise HandVoxError("augmentation_copies ต้องเป็นจำนวนเต็ม") from error
    if not 0 <= augmentation_copies <= 8:
        raise HandVoxError("augmentation_copies ต้องอยู่ระหว่าง 0 ถึง 8")

    pipeline_values = {
        name: parameters.pop(name)
        for name in tuple(parameters)
        if name in _TEMPORAL_PIPELINE_PARAMETERS
    }
    if pipeline_values.get("trim_motion", False):
        raise HandVoxError(
            "TCN ในหน้ากล้องใช้ sliding window จึงต้องตั้ง trim_motion=false "
            "เพื่อให้ preprocessing ตอนเทรนและใช้งานจริงตรงกัน"
        )
    unknown = sorted(set(parameters).difference(_TEMPORAL_CLASSIFIER_PARAMETERS))
    if unknown:
        raise HandVoxError("ไม่รู้จักพารามิเตอร์ TCN: " + ", ".join(unknown))
    pipeline = TemporalFeaturePipeline(
        FeaturePipelineConfig(
            target_length=config.collection.sequence_length,
            **pipeline_values,
        )
    )
    classifier_parameters = {
        "input_size": OUTPUT_FEATURE_COUNT,
        "sequence_length": config.collection.sequence_length,
        "random_state": config.training.random_seed,
        "schema_version": FEATURE_SCHEMA_VERSION,
        **parameters,
    }
    return pipeline, augmentation_copies, classifier_parameters


def _temporal_feature_manifest(pipeline):
    """บันทึก schema และ preprocessing จริงให้ detector ตรวจความตรงกัน."""

    payload = dict(schema_metadata())
    payload["pipeline_config"] = asdict(pipeline.config)
    return payload


def temporal_pipeline_from_manifest(manifest):
    """คืน preprocessing ที่บันทึกไว้และตรวจว่าหน้ากล้องรองรับตรงกัน."""
    feature_schema = manifest.get("feature_schema", {})
    if feature_schema.get("schema_version") != FEATURE_SCHEMA_VERSION:
        raise ValueError("feature schema ของ TCN ไม่ตรงกับโปรแกรมรุ่นนี้")
    if manifest.get("feature_schema_version", FEATURE_SCHEMA_VERSION) != FEATURE_SCHEMA_VERSION:
        raise ValueError("feature schema สองตำแหน่งใน manifest ไม่ตรงกัน")
    if int(feature_schema.get("output_feature_count", -1)) != OUTPUT_FEATURE_COUNT:
        raise ValueError("จำนวน temporal features ไม่ตรงกับตัวตรวจจับ")
    if int(manifest.get("feature_count", OUTPUT_FEATURE_COUNT)) != OUTPUT_FEATURE_COUNT:
        raise ValueError("จำนวน features สองตำแหน่งใน manifest ไม่ตรงกัน")
    pipeline_values = dict(feature_schema.get("pipeline_config", {}))
    sequence_length = int(manifest.get("sequence_length", 30))
    if int(pipeline_values.get("target_length", sequence_length)) != sequence_length:
        raise ValueError("sequence length ของ pipeline ไม่ตรงกับ manifest")
    if pipeline_values.get("trim_motion", False):
        raise ValueError("artifact ใช้ motion trim แต่ตัวตรวจจับใช้ sliding window")
    pipeline_values["target_length"] = sequence_length
    augmentation = pipeline_values.pop("augmentation", {})
    pipeline_values["augmentation"] = AugmentationConfig(**augmentation)
    try:
        pipeline_config = FeaturePipelineConfig(**pipeline_values)
    except TypeError as error:
        raise ValueError(f"pipeline config ใน manifest ไม่ถูกต้อง: {error}") from error
    return TemporalFeaturePipeline(pipeline_config)


def _transform_temporal_sequences(raw_sequences, pipeline, *, training=False, seed=42):
    """แปลง sequence ทีละคลิปเพื่อไม่ให้ augmentation แตะ validation/test."""

    transformed = [
        pipeline.transform(
            sequence,
            training=training,
            seed=seed + index,
        )
        for index, sequence in enumerate(np.asarray(raw_sequences, dtype=np.float32))
    ]
    if not transformed:
        return np.empty(
            (0, pipeline.config.target_length, OUTPUT_FEATURE_COUNT),
            dtype=np.float32,
        )
    return np.asarray(transformed, dtype=np.float32)


def _temporal_training_samples(
    raw_sequences,
    labels,
    pipeline,
    augmentation_copies,
    *,
    seed,
):
    """รวมข้อมูลจริงหนึ่งชุดกับสำเนา augmentation โดยคืน label ตรงลำดับ."""

    labels = np.asarray(labels, dtype=str)
    chunks = [
        _transform_temporal_sequences(
            raw_sequences, pipeline, training=False, seed=seed
        )
    ]
    label_chunks = [labels]
    for copy_index in range(augmentation_copies):
        chunks.append(
            _transform_temporal_sequences(
                raw_sequences,
                pipeline,
                training=True,
                seed=seed + (copy_index + 1) * 1_000_003,
            )
        )
        label_chunks.append(labels)
    return np.concatenate(chunks), np.concatenate(label_chunks)


def _target_group_holdout(records, *, test_fraction=0.2, random_seed=42):
    """แบ่งคลิปคำใหม่เพียงคลาสเดียวตามกลุ่มจริงโดยไม่สร้าง metadata ปลอม."""

    groups = np.asarray(
        [f"{record.signer_id}::{record.session_id}" for record in records],
        dtype=str,
    )
    unique_groups = np.asarray(sorted(set(groups.tolist())), dtype=str)
    if len(unique_groups) < 2:
        raise HandVoxError(
            "คำใหม่ต้องมีข้อมูลอย่างน้อย 2 กลุ่มผู้ทำท่าและรอบถ่ายเพื่อวัดผล"
        )
    generator = np.random.default_rng(random_seed)
    generator.shuffle(unique_groups)
    test_group_count = max(1, int(round(len(unique_groups) * test_fraction)))
    test_group_count = min(test_group_count, len(unique_groups) - 1)
    test_groups = set(unique_groups[:test_group_count].tolist())
    test_mask = np.asarray([group in test_groups for group in groups], dtype=bool)
    return np.flatnonzero(~test_mask), np.flatnonzero(test_mask), groups


def _fit_temporal_classifier(
    classifier_parameters,
    train_x,
    train_y,
    *,
    validation_x=None,
    validation_y=None,
):
    """แปลง error จาก backend เป็นข้อความระดับ workflow ที่ GUI แสดงได้."""

    try:
        classifier = TemporalClassifier(**classifier_parameters)
        if validation_x is None:
            classifier.fit(train_x, train_y)
        else:
            classifier.fit(
                train_x,
                train_y,
                X_val=validation_x,
                y_val=validation_y,
            )
        return classifier
    except (TorchUnavailableError, RuntimeError, ValueError) as error:
        raise HandVoxError(f"เทรนโมเดล TCN ไม่สำเร็จ: {error}") from error


def _save_training_sequences(
    path,
    clips,
    labels,
    signer_ids=None,
    session_ids=None,
):
    """เก็บ raw sequence สำหรับเพิ่มคำถัดไป พร้อม mask บอก metadata ที่มีจริง."""

    labels = np.asarray(labels, dtype=str)
    if signer_ids is None or session_ids is None:
        signer_ids = np.full(len(labels), "", dtype=str)
        session_ids = np.full(len(labels), "", dtype=str)
    else:
        signer_ids = np.asarray(signer_ids, dtype=str)
        session_ids = np.asarray(session_ids, dtype=str)
    metadata_available = (np.char.strip(signer_ids) != "") & (
        np.char.strip(session_ids) != ""
    )
    np.savez_compressed(
        path,
        clips=np.asarray(clips, dtype=np.float32),
        labels=labels,
        signer_ids=signer_ids,
        session_ids=session_ids,
        group_metadata_available=metadata_available,
    )


# ── ขั้นที่ 4: เทรน วัดผล และสร้าง experiment ───────────────
def _train_temporal_and_evaluate(config, store, output_root):
    """ประเมิน TCN ตามกลยุทธ์ที่กำหนด แล้วฝึก final model เป็น ``.pt``."""

    from sklearn.preprocessing import LabelEncoder

    started_at = datetime.now().astimezone()
    started_timer = time.perf_counter()
    readiness = preflight(config, store)
    if not readiness.ready:
        raise HandVoxError(
            "ข้อมูลยังไม่พร้อมเทรน กรุณาเปิดรายงาน preflight และแก้รายการ error ก่อน"
        )
    pipeline, augmentation_copies, classifier_parameters = (
        _temporal_training_components(config)
    )
    feature_manifest = _temporal_feature_manifest(pipeline)
    flattened, labels, signers, sessions, records = _load_accepted_arrays(
        config, store
    )
    raw_sequences = flattened.reshape(
        len(flattened), config.collection.sequence_length, FEATURE_COUNT
    )
    class_names = sorted(config.all_classes)
    class_ids = list(class_names)
    session_groups = _session_group_ids(signers, sessions)
    fold_results = []
    all_true = []
    all_predictions = []
    fold_best_epochs = []

    if config.training.evaluation_strategy == "known_signers_session_holdout":
        holdout_folds, _ = _known_signers_session_holdout_folds(
            config, labels, signers, sessions
        )
        fold_specs = [
            (
                fold["name"],
                fold["train_indices"],
                fold["validation_indices"],
                fold["test_indices"],
            )
            for fold in holdout_folds
        ]
    else:
        fold_specs = []
        for fold_index, test_signer in enumerate(config.collection.signers):
            candidate_indices = np.flatnonzero(signers != test_signer)
            test_indices = np.flatnonzero(signers == test_signer)
            inner_train, inner_validation, _ = _grouped_session_holdout(
                labels[candidate_indices],
                signers[candidate_indices],
                sessions[candidate_indices],
                test_fraction=0.25,
                random_seed=config.training.random_seed + fold_index,
            )
            fold_specs.append(
                (
                    test_signer,
                    candidate_indices[inner_train],
                    candidate_indices[inner_validation],
                    test_indices,
                )
            )

    for fold_index, (
        test_signer,
        train_indices,
        validation_indices,
        test_indices,
    ) in enumerate(fold_specs):
        train_groups = sorted(set(session_groups[train_indices].tolist()))
        validation_groups = sorted(
            set(session_groups[validation_indices].tolist())
        )
        test_groups = sorted(set(session_groups[test_indices].tolist()))
        if (
            set(train_groups).intersection(validation_groups)
            or set(train_groups).intersection(test_groups)
            or set(validation_groups).intersection(test_groups)
        ):
            raise HandVoxError(
                "พบกลุ่มผู้ทำท่าและรอบถ่ายซ้ำระหว่าง train/validation/test"
            )

        train_x, train_y = _temporal_training_samples(
            raw_sequences[train_indices],
            labels[train_indices],
            pipeline,
            augmentation_copies,
            seed=config.training.random_seed + fold_index * 10_000,
        )
        validation_x = _transform_temporal_sequences(
            raw_sequences[validation_indices],
            pipeline,
            training=False,
            seed=config.training.random_seed,
        )
        test_x = _transform_temporal_sequences(
            raw_sequences[test_indices],
            pipeline,
            training=False,
            seed=config.training.random_seed,
        )
        classifier = _fit_temporal_classifier(
            classifier_parameters,
            train_x,
            train_y,
            validation_x=validation_x,
            validation_y=labels[validation_indices],
        )
        predictions = _predictions_with_recognition_policy(
            classifier.predict_proba(test_x), class_names, config
        )
        fold_metrics = _metric_payload(
            labels[test_indices], predictions, class_ids, class_names
        )
        fold_metrics.update(
            {
                "test_signer": test_signer,
                "train_signers": sorted(set(signers[train_indices].tolist())),
                "train_sessions": sorted(set(sessions[train_indices].tolist())),
                "validation_sessions": sorted(
                    set(sessions[validation_indices].tolist())
                ),
                "test_sessions": sorted(set(sessions[test_indices].tolist())),
                "train_session_groups": train_groups,
                "validation_session_groups": validation_groups,
                "test_session_groups": test_groups,
                "group_leakage_detected": False,
                "train_clips": len(train_indices),
                "augmented_train_samples": len(train_x),
                "validation_clips": len(validation_indices),
                "test_clips": len(test_indices),
                "training_device": classifier.device_used_,
                "device_name": classifier.device_selection_.device_name,
                "epochs_completed": classifier.n_epochs_,
                "best_epoch": classifier.best_epoch_,
            }
        )
        fold_results.append(fold_metrics)
        fold_best_epochs.append(classifier.best_epoch_)
        all_true.extend(labels[test_indices].tolist())
        all_predictions.extend(predictions.tolist())

    aggregate = _metric_payload(
        all_true, all_predictions, class_ids, class_names
    )
    passed, acceptance_checks, neutral_fpr = _acceptance_result(config, aggregate)
    aggregate.update(
        {
            "neutral_false_positive_rate": float(neutral_fpr),
            "acceptance_checks": acceptance_checks,
            "passed": passed,
        }
    )

    # ใช้จำนวน epoch ที่ validation เลือกได้ แล้วฝึก final model ด้วยข้อมูลจริง
    # ทั้งหมด จึงไม่ทิ้ง session ใดออกจาก artifact ที่นำไปใช้งานจริง
    final_epochs = max(1, int(round(float(np.median(fold_best_epochs)))))
    final_parameters = dict(classifier_parameters)
    final_parameters.update(
        {
            "max_epochs": final_epochs,
            "patience": final_epochs,
            "validation_fraction": 0.0,
        }
    )
    final_x, final_y = _temporal_training_samples(
        raw_sequences,
        labels,
        pipeline,
        augmentation_copies,
        seed=config.training.random_seed + 100_000,
    )
    final_classifier = _fit_temporal_classifier(
        final_parameters,
        final_x,
        final_y,
    )

    experiment_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    experiment_dir = Path(output_root) / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=False)
    fingerprint = _dataset_fingerprint(store, records)
    model_path = experiment_dir / "model.pt"
    final_classifier.save(
        model_path,
        metadata={
            "experiment_id": experiment_id,
            "dataset_fingerprint_sha256": fingerprint,
            "feature_schema": feature_manifest,
            "augmentation_copies": augmentation_copies,
            "evaluation_strategy": config.training.evaluation_strategy,
        },
    )
    model_metadata = final_classifier.artifact_metadata()
    encoder = LabelEncoder().fit(class_names)
    with (experiment_dir / "labels.pkl").open("wb") as file:
        pickle.dump(encoder, file)
    _save_training_sequences(
        experiment_dir / "training_sequences.npz",
        raw_sequences,
        labels,
        signers,
        sessions,
    )

    metrics_payload = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "created_at": started_at.isoformat(timespec="seconds"),
        "duration_seconds": round(time.perf_counter() - started_timer, 3),
        "model_backend": "temporal_tcn",
        "model_artifact": "model.pt",
        "feature_schema": feature_manifest,
        "model_metadata": model_metadata,
        "augmentation_copies": augmentation_copies,
        "final_epochs": final_epochs,
        "training_device": final_classifier.device_used_,
        "evaluation_strategy": config.training.evaluation_strategy,
        "evaluation_scope": (
            "known_signers_session_holdout"
            if config.training.evaluation_strategy == "known_signers_session_holdout"
            else "cross_person_holdout"
        ),
        "target_gesture": config.target_gesture,
        "dataset_fingerprint_sha256": fingerprint,
        "accepted_clips": len(records),
        "training_samples_after_augmentation": len(final_x),
        "signers": list(config.collection.signers),
        "sessions_present": sorted(set(sessions.tolist())),
        "session_groups_present": sorted(set(session_groups.tolist())),
        "evaluation_group_key": "signer_id+session_id",
        "classes": class_names,
        "aggregate": aggregate,
        "folds": fold_results,
        "environment": _version_info(),
    }
    (experiment_dir / "metrics.json").write_text(
        json.dumps(metrics_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    save_preflight_report(readiness, experiment_dir / "preflight.json")
    (experiment_dir / "training_config.snapshot.json").write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = _manifest(
        config,
        aggregate,
        experiment_id,
        model_backend="temporal_tcn",
        model_artifact="model.pt",
        feature_schema=feature_manifest,
        model_metadata=model_metadata,
    )
    (experiment_dir / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        experiment_dir / "summary.csv",
        [
            "experiment_id",
            "created_at",
            "duration_seconds",
            "model_backend",
            "training_device",
            "accepted_clips",
            "training_samples_after_augmentation",
            "accuracy",
            "macro_precision",
            "macro_recall",
            "macro_f1",
            "weighted_precision",
            "weighted_recall",
            "weighted_f1",
            "neutral_false_positive_rate",
            "unknown_false_activation_rate",
            "passed",
            "dataset_fingerprint_sha256",
        ],
        [
            {
                "experiment_id": experiment_id,
                "created_at": metrics_payload["created_at"],
                "duration_seconds": metrics_payload["duration_seconds"],
                "model_backend": "temporal_tcn",
                "training_device": metrics_payload["training_device"],
                "accepted_clips": len(records),
                "training_samples_after_augmentation": len(final_x),
                "accuracy": aggregate["accuracy"],
                "macro_precision": aggregate["macro_precision"],
                "macro_recall": aggregate["macro_recall"],
                "macro_f1": aggregate["macro_f1"],
                "weighted_precision": aggregate["weighted_precision"],
                "weighted_recall": aggregate["weighted_recall"],
                "weighted_f1": aggregate["weighted_f1"],
                "neutral_false_positive_rate": aggregate[
                    "neutral_false_positive_rate"
                ],
                "unknown_false_activation_rate": aggregate[
                    "unknown_false_activation_rate"
                ],
                "passed": aggregate["passed"],
                "dataset_fingerprint_sha256": fingerprint,
            }
        ],
    )
    _write_csv(
        experiment_dir / "per_class_metrics.csv",
        ["class_name", "precision", "recall", "f1", "support"],
        aggregate["per_class"],
    )
    fold_columns = [
        "test_signer",
        "train_signers",
        "train_sessions",
        "validation_sessions",
        "test_sessions",
        "train_session_groups",
        "validation_session_groups",
        "test_session_groups",
        "group_leakage_detected",
        "train_clips",
        "augmented_train_samples",
        "validation_clips",
        "test_clips",
        "training_device",
        "device_name",
        "epochs_completed",
        "best_epoch",
        "accuracy",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
    ]
    _write_csv(
        experiment_dir / "fold_summary.csv",
        fold_columns,
        [
            {
                key: ", ".join(str(value) for value in row[key])
                if isinstance(row[key], list)
                else row[key]
                for key in fold_columns
            }
            for row in fold_results
        ],
    )
    _write_csv(
        experiment_dir / "dataset_inventory.csv",
        [
            "gesture_name",
            "signer_id",
            "accepted",
            "pending",
            "rejected",
            "total",
            "sessions",
        ],
        readiness.inventory,
    )
    _write_confusion_csv(
        experiment_dir / "confusion_matrix.csv",
        class_names,
        aggregate["confusion_matrix"],
    )
    _write_plots(experiment_dir, class_names, aggregate)
    _write_markdown_report(experiment_dir, metrics_payload, config)
    _write_experiment_index(Path(output_root))
    return experiment_dir, metrics_payload


def train_and_evaluate(config=None, store=None, output_root=EXPERIMENTS_DIR):
    """วัดผลตาม config ฝึก final model และสร้างไฟล์รายงาน."""
    from sklearn.preprocessing import LabelEncoder
    from sklearn.svm import SVC

    started_at = datetime.now().astimezone()
    started_timer = time.perf_counter()
    config = config or load_training_config()
    store = store or DatasetV2Store()
    if config.training.algorithm == "TCN":
        return _train_temporal_and_evaluate(config, store, output_root)
    readiness = preflight(config, store)
    if not readiness.ready:
        raise HandVoxError(
            "ข้อมูลยังไม่พร้อมเทรน กรุณาเปิดรายงาน preflight และแก้รายการ error ก่อน"
        )

    features, labels, signers, sessions, records = _load_accepted_arrays(config, store)
    encoder = LabelEncoder()
    encoder.fit(list(config.all_classes))
    targets = encoder.transform(labels)
    class_names = list(encoder.classes_)
    class_ids = list(range(len(class_names)))
    fold_results = []
    all_true = []
    all_predictions = []
    session_groups = _session_group_ids(signers, sessions)

    parameters = dict(config.training.parameters)
    if config.training.evaluation_strategy == "known_signers_session_holdout":
        holdout_folds, _ = _known_signers_session_holdout_folds(
            config, labels, signers, sessions
        )
        fold_specs = [
            (
                fold["name"],
                np.sort(np.concatenate((fold["train_indices"], fold["validation_indices"]))),
                fold["test_indices"],
            )
            for fold in holdout_folds
        ]
    else:
        fold_specs = [
            (
                test_signer,
                np.flatnonzero(signers != test_signer),
                np.flatnonzero(signers == test_signer),
            )
            for test_signer in config.collection.signers
        ]

    for test_signer, train_indices, test_indices in fold_specs:
        train_groups = sorted(set(session_groups[train_indices].tolist()))
        test_groups = sorted(set(session_groups[test_indices].tolist()))
        if set(train_groups).intersection(test_groups):
            raise HandVoxError(
                "พบกลุ่มผู้ทำท่าและรอบถ่ายซ้ำระหว่าง train/test กรุณาตรวจ metadata"
            )
        classifier = SVC(random_state=config.training.random_seed, **parameters)
        classifier.fit(features[train_indices], targets[train_indices])
        if classifier.probability:
            probabilities = classifier.predict_proba(features[test_indices])
            prediction_names = _predictions_with_recognition_policy(
                probabilities, class_names, config
            )
            predictions = encoder.transform(prediction_names)
        else:
            predictions = classifier.predict(features[test_indices])
        fold_metrics = _metric_payload(
            targets[test_indices], predictions, class_ids, class_names
        )
        fold_metrics.update(
            {
                "test_signer": test_signer,
                "train_signers": sorted(set(signers[train_indices])),
                "train_sessions": sorted(set(sessions[train_indices])),
                "test_sessions": sorted(set(sessions[test_indices])),
                "train_session_groups": train_groups,
                "test_session_groups": test_groups,
                "group_leakage_detected": False,
                "train_clips": len(train_indices),
                "test_clips": len(test_indices),
            }
        )
        fold_results.append(fold_metrics)
        all_true.extend(targets[test_indices].tolist())
        all_predictions.extend(predictions.tolist())

    aggregate = _metric_payload(all_true, all_predictions, class_ids, class_names)
    passed, acceptance_checks, neutral_fpr = _acceptance_result(config, aggregate)
    aggregate["neutral_false_positive_rate"] = float(neutral_fpr)
    aggregate["acceptance_checks"] = acceptance_checks
    aggregate["passed"] = passed

    final_classifier = SVC(random_state=config.training.random_seed, **parameters)
    final_classifier.fit(features, targets)

    experiment_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    experiment_dir = Path(output_root) / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=False)
    fingerprint = _dataset_fingerprint(store, records)
    metrics_payload = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "created_at": started_at.isoformat(timespec="seconds"),
        "duration_seconds": round(time.perf_counter() - started_timer, 3),
        "model_backend": "svc",
        "model_artifact": "model.pkl",
        "evaluation_strategy": config.training.evaluation_strategy,
        "evaluation_scope": (
            "known_signers_session_holdout"
            if config.training.evaluation_strategy == "known_signers_session_holdout"
            else "cross_person_holdout"
        ),
        "target_gesture": config.target_gesture,
        "dataset_fingerprint_sha256": fingerprint,
        "accepted_clips": len(records),
        "signers": list(config.collection.signers),
        "sessions_present": sorted(set(sessions)),
        "session_groups_present": sorted(set(session_groups)),
        "evaluation_group_key": "signer_id+session_id",
        "classes": class_names,
        "aggregate": aggregate,
        "folds": fold_results,
        "environment": _version_info(),
    }
    (experiment_dir / "metrics.json").write_text(
        json.dumps(metrics_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    save_preflight_report(readiness, experiment_dir / "preflight.json")
    (experiment_dir / "training_config.snapshot.json").write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (experiment_dir / "model.pkl").open("wb") as file:
        pickle.dump(final_classifier, file)
    with (experiment_dir / "labels.pkl").open("wb") as file:
        pickle.dump(encoder, file)
    _save_training_sequences(
        experiment_dir / "training_sequences.npz",
        features.reshape(
            len(features), config.collection.sequence_length, FEATURE_COUNT
        ),
        labels,
        signers,
        sessions,
    )

    manifest = _manifest(
        config,
        aggregate,
        experiment_id,
        model_backend="svc",
        model_artifact="model.pkl",
    )
    (experiment_dir / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        experiment_dir / "summary.csv",
        [
            "experiment_id", "created_at", "duration_seconds", "accepted_clips",
            "accuracy", "macro_precision", "macro_recall", "macro_f1",
            "weighted_precision", "weighted_recall", "weighted_f1",
            "neutral_false_positive_rate", "unknown_false_activation_rate",
            "passed", "dataset_fingerprint_sha256",
        ],
        [
            {
                "experiment_id": experiment_id,
                "created_at": metrics_payload["created_at"],
                "duration_seconds": metrics_payload["duration_seconds"],
                "accepted_clips": metrics_payload["accepted_clips"],
                "accuracy": aggregate["accuracy"],
                "macro_precision": aggregate["macro_precision"],
                "macro_recall": aggregate["macro_recall"],
                "macro_f1": aggregate["macro_f1"],
                "weighted_precision": aggregate["weighted_precision"],
                "weighted_recall": aggregate["weighted_recall"],
                "weighted_f1": aggregate["weighted_f1"],
                "neutral_false_positive_rate": aggregate["neutral_false_positive_rate"],
                "unknown_false_activation_rate": aggregate[
                    "unknown_false_activation_rate"
                ],
                "passed": aggregate["passed"],
                "dataset_fingerprint_sha256": fingerprint,
            }
        ],
    )
    _write_csv(
        experiment_dir / "per_class_metrics.csv",
        ["class_name", "precision", "recall", "f1", "support"],
        aggregate["per_class"],
    )
    _write_csv(
        experiment_dir / "fold_summary.csv",
        [
            "test_signer", "train_signers", "train_sessions", "test_sessions",
            "train_session_groups", "test_session_groups", "group_leakage_detected",
            "train_clips", "test_clips",
            "accuracy", "macro_precision", "macro_recall", "macro_f1",
            "weighted_precision", "weighted_recall", "weighted_f1",
        ],
        [
            {
                key: ", ".join(row[key]) if isinstance(row[key], list) else row[key]
                for key in (
                    "test_signer", "train_signers", "train_sessions", "test_sessions",
                    "train_session_groups", "test_session_groups", "group_leakage_detected",
                    "train_clips", "test_clips",
                    "accuracy", "macro_precision", "macro_recall", "macro_f1",
                    "weighted_precision", "weighted_recall", "weighted_f1",
                )
            }
            for row in fold_results
        ],
    )
    _write_csv(
        experiment_dir / "dataset_inventory.csv",
        [
            "gesture_name", "signer_id", "accepted", "pending", "rejected",
            "total", "sessions",
        ],
        readiness.inventory,
    )
    _write_confusion_csv(
        experiment_dir / "confusion_matrix.csv",
        class_names,
        aggregate["confusion_matrix"],
    )
    _write_plots(experiment_dir, class_names, aggregate)
    _write_markdown_report(experiment_dir, metrics_payload, config)
    _write_experiment_index(Path(output_root))
    return experiment_dir, metrics_payload


def _train_temporal_quick_trial(config, store, output_root):
    """เพิ่มคำหนึ่งคำด้วย TCN โดยรักษาขอบเขตการวัดผลตาม metadata ที่มีจริง.

    หากฐานเดิมมี signer/session ครบ จะทำ grouped holdout ทั้งชุด แต่ฐานรุ่นเก่า
    ของ HandVox ไม่มี metadata ดังกล่าว จึงใช้ฐานเป็น training-only และกันคลิป
    คำใหม่ตามกลุ่มจริงเพื่อรายงาน recall เบื้องต้นเท่านั้น.
    """

    from sklearn.preprocessing import LabelEncoder

    readiness = quick_trial_readiness(config, store)
    if not readiness.ready:
        errors = [item.message for item in readiness.items if item.status == "error"]
        detail = "; ".join(errors) if errors else "ข้อมูลยังไม่ผ่านเงื่อนไข"
        raise HandVoxError(f"ยังเทรนทดลองด่วนไม่ได้: {detail}")
    started_at = datetime.now().astimezone()
    started_timer = time.perf_counter()
    pipeline, augmentation_copies, classifier_parameters = (
        _temporal_training_components(config)
    )
    feature_manifest = _temporal_feature_manifest(pipeline)
    target = config.target_gesture

    with np.load(LEGACY_DATA_FILE, allow_pickle=False) as data:
        base_clips = data["clips"].astype(np.float32)
        base_labels = data["labels"].astype(str)
        base_signers = (
            data["signer_ids"].astype(str)
            if "signer_ids" in data.files
            else np.full(len(base_labels), "", dtype=str)
        )
        base_sessions = (
            data["session_ids"].astype(str)
            if "session_ids" in data.files
            else np.full(len(base_labels), "", dtype=str)
        )
    keep = np.isin(
        base_labels,
        [name for name in config.visible_gestures if name != target],
    )
    base_clips = base_clips[keep]
    base_labels = base_labels[keep]
    base_signers = base_signers[keep]
    base_sessions = base_sessions[keep]
    base_metadata_complete = bool(
        len(base_signers) == len(base_labels)
        and len(base_sessions) == len(base_labels)
        and np.all(np.char.strip(base_signers) != "")
        and np.all(np.char.strip(base_sessions) != "")
    )

    target_records = sorted(
        (
            record
            for record in _training_records(config, store.records())
            if record.gesture_name == target and record.quality == "accepted"
        ),
        key=lambda record: record.clip_id,
    )
    target_clips = np.asarray(
        [
            np.load(
                store.resolve_data_path(record.sequence_file), allow_pickle=False
            )
            for record in target_records
        ],
        dtype=np.float32,
    )
    target_signers = np.asarray(
        [record.signer_id for record in target_records], dtype=str
    )
    target_sessions = np.asarray(
        [record.session_id for record in target_records], dtype=str
    )
    raw_sequences = np.concatenate((base_clips, target_clips), axis=0)
    labels = np.concatenate(
        (base_labels, np.asarray([target] * len(target_clips), dtype=str))
    )
    signer_ids = np.concatenate((base_signers, target_signers))
    session_ids = np.concatenate((base_sessions, target_sessions))
    base_count = len(base_clips)
    class_names = sorted(config.visible_gestures)
    class_ids = list(class_names)
    limitations = [
        "โหมดทดลองด่วนใช้ยืนยันการเพิ่มคำเบื้องต้น ไม่ใช่ผลมาตรฐานแทน LOSO"
    ]

    if base_metadata_complete:
        train_indices, test_indices, all_groups = _grouped_session_holdout(
            labels,
            signer_ids,
            session_ids,
            test_fraction=0.2,
            random_seed=config.training.random_seed,
        )
        evaluation_scope = "all_classes_grouped_signer_session_holdout"
        genuine_groups = all_groups
    else:
        target_train, target_test, target_groups = _target_group_holdout(
            target_records,
            test_fraction=0.2,
            random_seed=config.training.random_seed,
        )
        train_indices = np.concatenate(
            (
                np.arange(base_count, dtype=int),
                base_count + target_train,
            )
        )
        test_indices = base_count + target_test
        genuine_groups = np.concatenate(
            (np.full(base_count, "", dtype=str), target_groups)
        )
        evaluation_scope = "new_target_only_grouped_holdout"
        limitations.extend(
            [
                "คำฐานไม่มี signer/session จึงใช้เป็น training-only ทั้งหมด",
                "ชุดทดสอบมีเฉพาะคลิปคำใหม่จากกลุ่มที่โมเดลไม่เห็น",
                "Accuracy/Macro F1 รอบนี้ห้ามอ้างเป็นความแม่นยำรวมของทุกคำ",
                "ยังไม่สามารถวัดการถดถอยของคำเดิมได้อย่างเป็นอิสระ",
            ]
        )

    validation_indices = np.asarray([], dtype=int)
    inner_train_indices = np.asarray(train_indices, dtype=int)
    if base_metadata_complete:
        try:
            inner_train, inner_validation, _ = _grouped_session_holdout(
                labels[train_indices],
                signer_ids[train_indices],
                session_ids[train_indices],
                test_fraction=0.2,
                random_seed=config.training.random_seed + 1,
            )
            inner_train_indices = train_indices[inner_train]
            validation_indices = train_indices[inner_validation]
        except HandVoxError as error:
            limitations.append(
                "ไม่สามารถกัน grouped validation ภายในชุดฝึกได้: " + str(error)
            )

    train_x, train_y = _temporal_training_samples(
        raw_sequences[inner_train_indices],
        labels[inner_train_indices],
        pipeline,
        augmentation_copies,
        seed=config.training.random_seed,
    )
    test_x = _transform_temporal_sequences(
        raw_sequences[test_indices],
        pipeline,
        training=False,
        seed=config.training.random_seed,
    )
    trial_parameters = dict(classifier_parameters)
    if len(validation_indices):
        validation_x = _transform_temporal_sequences(
            raw_sequences[validation_indices],
            pipeline,
            training=False,
            seed=config.training.random_seed,
        )
        trial_classifier = _fit_temporal_classifier(
            trial_parameters,
            train_x,
            train_y,
            validation_x=validation_x,
            validation_y=labels[validation_indices],
        )
    else:
        # ไม่มี validation ที่แบ่งตามกลุ่มได้ จึง monitor training loss เท่านั้น
        # และบอกข้อจำกัดตรงไปตรงมา แทนสุ่มคลิปจาก session เดียวกันปะปนกัน
        trial_parameters["validation_fraction"] = 0.0
        limitations.append(
            "Early stopping รอบนี้ดู training loss เพราะไม่มี grouped validation ที่ซื่อสัตย์"
        )
        trial_classifier = _fit_temporal_classifier(
            trial_parameters,
            train_x,
            train_y,
        )

    predictions = trial_classifier.predict(test_x).astype(str)
    aggregate = _metric_payload(
        labels[test_indices], predictions, class_ids, class_names
    )
    recalls = {row["class_name"]: row["recall"] for row in aggregate["per_class"]}
    if base_metadata_complete:
        checks = {
            "accuracy": aggregate["accuracy"]
            >= config.acceptance.minimum_accuracy,
            "macro_f1": aggregate["macro_f1"]
            >= config.acceptance.minimum_macro_f1,
            "minimum_visible_recall": min(recalls.values(), default=0)
            >= config.acceptance.minimum_class_recall,
        }
    else:
        checks = {
            "new_target_holdout_accuracy": aggregate["accuracy"]
            >= config.acceptance.minimum_accuracy,
            "new_target_recall": recalls.get(target, 0.0)
            >= config.acceptance.minimum_class_recall,
        }
    aggregate.update(
        {
            "neutral_false_positive_rate": 0.0,
            "unknown_false_activation_rate": 0.0,
            "acceptance_checks": checks,
            "passed": all(checks.values()),
        }
    )

    final_epochs = max(1, trial_classifier.best_epoch_)
    final_parameters = dict(classifier_parameters)
    final_parameters.update(
        {
            "max_epochs": final_epochs,
            "patience": final_epochs,
            "validation_fraction": 0.0,
        }
    )
    final_x, final_y = _temporal_training_samples(
        raw_sequences,
        labels,
        pipeline,
        augmentation_copies,
        seed=config.training.random_seed + 100_000,
    )
    final_classifier = _fit_temporal_classifier(
        final_parameters,
        final_x,
        final_y,
    )

    experiment_id = "quick_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    experiment_dir = Path(output_root) / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(LEGACY_DATA_FILE.read_bytes())
    digest.update(_dataset_fingerprint(store, target_records).encode("ascii"))
    fingerprint = digest.hexdigest()
    final_classifier.save(
        experiment_dir / "model.pt",
        metadata={
            "experiment_id": experiment_id,
            "dataset_fingerprint_sha256": fingerprint,
            "feature_schema": feature_manifest,
            "augmentation_copies": augmentation_copies,
            "evaluation_scope": evaluation_scope,
            "research_grade": False,
        },
    )
    model_metadata = final_classifier.artifact_metadata()
    encoder = LabelEncoder().fit(class_names)
    with (experiment_dir / "labels.pkl").open("wb") as file:
        pickle.dump(encoder, file)
    _save_training_sequences(
        experiment_dir / "training_sequences.npz",
        raw_sequences,
        labels,
        signer_ids,
        session_ids,
    )

    genuine_train_groups = sorted(
        set(group for group in genuine_groups[inner_train_indices].tolist() if group)
    )
    genuine_validation_groups = sorted(
        set(group for group in genuine_groups[validation_indices].tolist() if group)
    )
    genuine_test_groups = sorted(
        set(group for group in genuine_groups[test_indices].tolist() if group)
    )
    fold = dict(aggregate)
    fold.update(
        {
            "test_signer": "grouped_session_holdout",
            "train_signers": sorted(
                set(value for value in signer_ids[inner_train_indices].tolist() if value)
            ),
            "train_sessions": sorted(
                set(value for value in session_ids[inner_train_indices].tolist() if value)
            ),
            "validation_sessions": sorted(
                set(value for value in session_ids[validation_indices].tolist() if value)
            ),
            "test_sessions": sorted(
                set(value for value in session_ids[test_indices].tolist() if value)
            ),
            "train_session_groups": genuine_train_groups,
            "validation_session_groups": genuine_validation_groups,
            "test_session_groups": genuine_test_groups,
            "group_leakage_detected": bool(
                set(genuine_train_groups).intersection(genuine_test_groups)
                or set(genuine_validation_groups).intersection(genuine_test_groups)
            ),
            "legacy_base_training_only": not base_metadata_complete,
            "train_clips": len(inner_train_indices),
            "augmented_train_samples": len(train_x),
            "validation_clips": len(validation_indices),
            "test_clips": len(test_indices),
            "training_device": trial_classifier.device_used_,
            "epochs_completed": trial_classifier.n_epochs_,
            "best_epoch": trial_classifier.best_epoch_,
        }
    )
    payload = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "created_at": started_at.isoformat(timespec="seconds"),
        "duration_seconds": round(time.perf_counter() - started_timer, 3),
        "mode": "quick_trial",
        "model_backend": "temporal_tcn",
        "model_artifact": "model.pt",
        "feature_schema": feature_manifest,
        "model_metadata": model_metadata,
        "training_device": final_classifier.device_used_,
        "evaluation_strategy": "grouped_signer_session_holdout",
        "configured_evaluation_strategy": config.training.evaluation_strategy,
        "evaluation_group_key": "signer_id+session_id",
        "evaluation_scope": evaluation_scope,
        "research_grade": False,
        "evaluation_limitations": limitations,
        "base_group_metadata_complete": base_metadata_complete,
        "target_gesture": target,
        "dataset_fingerprint_sha256": fingerprint,
        "accepted_clips": len(raw_sequences),
        "training_samples_after_augmentation": len(final_x),
        "base_clips": len(base_clips),
        "new_target_clips": len(target_clips),
        "signers": sorted(set(target_signers.tolist())),
        "sessions_present": sorted(set(target_sessions.tolist())),
        "session_groups_present": sorted(set(target_groups.tolist()))
        if not base_metadata_complete
        else sorted(set(genuine_groups.tolist())),
        "classes": class_names,
        "aggregate": aggregate,
        "folds": [fold],
        "environment": _version_info(),
    }
    (experiment_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    save_preflight_report(readiness, experiment_dir / "preflight.json")
    (experiment_dir / "training_config.snapshot.json").write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = _manifest(
        config,
        aggregate,
        experiment_id,
        model_backend="temporal_tcn",
        model_artifact="model.pt",
        feature_schema=feature_manifest,
        model_metadata=model_metadata,
    )
    manifest.update(
        {
            "mode": "quick_trial",
            "evaluation_scope": evaluation_scope,
            "research_grade": False,
        }
    )
    (experiment_dir / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        experiment_dir / "summary.csv",
        [
            "experiment_id",
            "created_at",
            "duration_seconds",
            "model_backend",
            "training_device",
            "evaluation_scope",
            "research_grade",
            "accepted_clips",
            "base_clips",
            "new_target_clips",
            "accuracy",
            "macro_f1",
            "passed",
            "dataset_fingerprint_sha256",
        ],
        [
            {
                "experiment_id": experiment_id,
                "created_at": payload["created_at"],
                "duration_seconds": payload["duration_seconds"],
                "model_backend": "temporal_tcn",
                "training_device": payload["training_device"],
                "evaluation_scope": evaluation_scope,
                "research_grade": False,
                "accepted_clips": len(raw_sequences),
                "base_clips": len(base_clips),
                "new_target_clips": len(target_clips),
                "accuracy": aggregate["accuracy"],
                "macro_f1": aggregate["macro_f1"],
                "passed": aggregate["passed"],
                "dataset_fingerprint_sha256": fingerprint,
            }
        ],
    )
    _write_csv(
        experiment_dir / "per_class_metrics.csv",
        ["class_name", "precision", "recall", "f1", "support"],
        aggregate["per_class"],
    )
    _write_confusion_csv(
        experiment_dir / "confusion_matrix.csv",
        class_names,
        aggregate["confusion_matrix"],
    )
    _write_plots(experiment_dir, class_names, aggregate)
    _write_markdown_report(experiment_dir, payload, config)
    _write_experiment_index(Path(output_root))
    return experiment_dir, payload


def train_quick_trial(config, store=None, output_root=EXPERIMENTS_DIR):
    """เทรนโมเดลทดลองจากข้อมูลฐานคำเดิมและคลิป accepted ของคำใหม่.

    ใช้ grouped holdout ตามผู้ทำท่าและรอบถ่ายเพื่อบันทึกค่าทดสอบเบื้องต้น
    โมเดลและชุดข้อมูลสะสมถูกเก็บใน experiment ก่อน และยังไม่เขียนทับ
    โมเดลหลักจนกว่าจะ activate
    """
    from sklearn.preprocessing import LabelEncoder
    from sklearn.svm import SVC

    if config.mode != "quick_trial":
        raise HandVoxError("train_quick_trial ต้องใช้ config โหมด quick_trial")
    store = store or DatasetV2Store()
    if config.training.algorithm == "TCN":
        return _train_temporal_quick_trial(config, store, output_root)
    readiness = quick_trial_readiness(config, store)
    if not readiness.ready:
        errors = [item.message for item in readiness.items if item.status == "error"]
        detail = "; ".join(errors) if errors else "ข้อมูลยังไม่ผ่านเงื่อนไข"
        raise HandVoxError(f"ยังเทรนทดลองด่วนไม่ได้: {detail}")

    started_at = datetime.now().astimezone()
    started_timer = time.perf_counter()
    target = config.target_gesture
    with np.load(LEGACY_DATA_FILE, allow_pickle=False) as data:
        base_clips = data["clips"].astype(np.float32)
        base_labels = data["labels"].astype(str)
        if not {"signer_ids", "session_ids"}.issubset(data.files):
            raise HandVoxError(
                "ข้อมูลฐานไม่มี signer_ids/session_ids จึงไม่สามารถประเมินแบบแยกรอบถ่ายได้ "
                "กรุณาใช้ Dataset V2 ที่มี metadata ครบ"
            )
        base_signers = data["signer_ids"].astype(str)
        base_sessions = data["session_ids"].astype(str)
        if len(base_signers) != len(base_labels) or len(base_sessions) != len(base_labels):
            raise HandVoxError(
                "จำนวน signer_ids/session_ids ในข้อมูลฐานไม่ตรงกับจำนวนคลิป"
            )
    keep = np.isin(base_labels, [name for name in config.visible_gestures if name != target])
    base_clips = base_clips[keep]
    base_labels = base_labels[keep]
    base_signers = base_signers[keep]
    base_sessions = base_sessions[keep]

    target_records = sorted(
        (
            record
            for record in _training_records(config, store.records())
            if record.gesture_name == target and record.quality == "accepted"
        ),
        key=lambda record: record.clip_id,
    )
    target_clips = np.asarray(
        [
            np.load(store.resolve_data_path(record.sequence_file), allow_pickle=False)
            for record in target_records
        ],
        dtype=np.float32,
    )
    clips = np.concatenate((base_clips, target_clips), axis=0)
    labels = np.concatenate(
        (base_labels, np.asarray([target] * len(target_clips), dtype=str)), axis=0
    )
    signer_ids = np.concatenate(
        (
            base_signers,
            np.asarray([record.signer_id for record in target_records], dtype=str),
        )
    )
    session_ids = np.concatenate(
        (
            base_sessions,
            np.asarray([record.session_id for record in target_records], dtype=str),
        )
    )
    features = clips.reshape(len(clips), -1)
    encoder = LabelEncoder()
    encoder.fit(list(config.visible_gestures))
    targets = encoder.transform(labels)
    class_names = list(encoder.classes_)
    class_ids = list(range(len(class_names)))
    train_indices, test_indices, session_groups = _grouped_session_holdout(
        labels,
        signer_ids,
        session_ids,
        test_fraction=0.2,
        random_seed=config.training.random_seed,
    )
    train_x, test_x = features[train_indices], features[test_indices]
    train_y, test_y = targets[train_indices], targets[test_indices]
    parameters = dict(config.training.parameters)
    trial_classifier = SVC(random_state=config.training.random_seed, **parameters)
    trial_classifier.fit(train_x, train_y)
    predictions = trial_classifier.predict(test_x)
    aggregate = _metric_payload(test_y, predictions, class_ids, class_names)
    recalls = [row["recall"] for row in aggregate["per_class"]]
    checks = {
        "accuracy": aggregate["accuracy"] >= config.acceptance.minimum_accuracy,
        "macro_f1": aggregate["macro_f1"] >= config.acceptance.minimum_macro_f1,
        "minimum_visible_recall": min(recalls, default=0)
        >= config.acceptance.minimum_class_recall,
    }
    aggregate.update(
        {
            "neutral_false_positive_rate": 0.0,
            "acceptance_checks": checks,
            "passed": all(checks.values()),
        }
    )
    final_classifier = SVC(random_state=config.training.random_seed, **parameters)
    final_classifier.fit(features, targets)

    experiment_id = "quick_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    experiment_dir = Path(output_root) / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(LEGACY_DATA_FILE.read_bytes())
    digest.update(_dataset_fingerprint(store, target_records).encode("ascii"))
    fold = dict(aggregate)
    fold.update(
        {
            "test_signer": "grouped_session_holdout",
            "train_signers": sorted(set(signer_ids[train_indices].tolist())),
            "train_sessions": sorted(set(session_ids[train_indices].tolist())),
            "test_sessions": sorted(set(session_ids[test_indices].tolist())),
            "train_session_groups": sorted(
                set(session_groups[train_indices].tolist())
            ),
            "test_session_groups": sorted(set(session_groups[test_indices].tolist())),
            "group_leakage_detected": False,
            "train_clips": len(train_y),
            "test_clips": len(test_y),
        }
    )
    payload = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "created_at": started_at.isoformat(timespec="seconds"),
        "duration_seconds": round(time.perf_counter() - started_timer, 3),
        "mode": "quick_trial",
        "model_backend": "svc",
        "model_artifact": "model.pkl",
        "evaluation_strategy": "grouped_signer_session_holdout",
        "configured_evaluation_strategy": config.training.evaluation_strategy,
        "evaluation_group_key": "signer_id+session_id",
        "target_gesture": target,
        "dataset_fingerprint_sha256": digest.hexdigest(),
        "accepted_clips": len(clips),
        "base_clips": len(base_clips),
        "new_target_clips": len(target_clips),
        "signers": sorted(set(signer_ids.tolist())),
        "sessions_present": sorted(set(session_ids.tolist())),
        "session_groups_present": sorted(set(session_groups.tolist())),
        "classes": class_names,
        "aggregate": aggregate,
        "folds": [fold],
        "environment": _version_info(),
    }
    (experiment_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    save_preflight_report(readiness, experiment_dir / "preflight.json")
    (experiment_dir / "training_config.snapshot.json").write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (experiment_dir / "model.pkl").open("wb") as file:
        pickle.dump(final_classifier, file)
    with (experiment_dir / "labels.pkl").open("wb") as file:
        pickle.dump(encoder, file)
    _save_training_sequences(
        experiment_dir / "training_sequences.npz",
        clips,
        labels,
        signer_ids,
        session_ids,
    )
    manifest = _manifest(
        config,
        aggregate,
        experiment_id,
        model_backend="svc",
        model_artifact="model.pkl",
    )
    manifest["mode"] = "quick_trial"
    (experiment_dir / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(
        experiment_dir / "summary.csv",
        [
            "experiment_id", "created_at", "duration_seconds", "accepted_clips",
            "base_clips", "new_target_clips", "accuracy", "macro_f1", "passed",
            "dataset_fingerprint_sha256",
        ],
        [{
            "experiment_id": experiment_id,
            "created_at": payload["created_at"],
            "duration_seconds": payload["duration_seconds"],
            "accepted_clips": payload["accepted_clips"],
            "base_clips": payload["base_clips"],
            "new_target_clips": payload["new_target_clips"],
            "accuracy": aggregate["accuracy"],
            "macro_f1": aggregate["macro_f1"],
            "passed": aggregate["passed"],
            "dataset_fingerprint_sha256": payload["dataset_fingerprint_sha256"],
        }],
    )
    _write_csv(
        experiment_dir / "per_class_metrics.csv",
        ["class_name", "precision", "recall", "f1", "support"],
        aggregate["per_class"],
    )
    _write_confusion_csv(
        experiment_dir / "confusion_matrix.csv", class_names, aggregate["confusion_matrix"]
    )
    _write_plots(experiment_dir, class_names, aggregate)
    _write_markdown_report(experiment_dir, payload, config)
    _write_experiment_index(Path(output_root))
    return experiment_dir, payload


# ── ขั้นที่ 5: รายงาน รายการทดลอง และการติดตั้ง ─────────────
def _write_markdown_report(experiment_dir, payload, config):
    """สร้างรายงาน Markdown ที่นำค่าไปอ้างอิงในเอกสารโครงงานได้."""
    aggregate = payload["aggregate"]
    result = "ผ่าน" if aggregate["passed"] else "ยังไม่ผ่าน"
    recognition_policy = _evaluated_recognition_policy(config)
    policy_description = (
        "- คะแนนหลังปฏิเสธคำไม่แน่ใจ: "
        f"**confidence ≥ {recognition_policy['minimum_confidence']:.2f}, "
        f"margin ≥ {recognition_policy['minimum_probability_margin']:.2f}**"
        if recognition_policy
        else "- คะแนนจากคำทำนายรายคลิปก่อนใช้ด่านความมั่นใจและการยืนยันคำในหน้ากล้อง"
    )
    lines = [
        f"# ผลการทดลอง HandVox — {payload['experiment_id']}",
        "",
        f"- โหมด: **{'ทดลองด่วน' if payload.get('mode') == 'quick_trial' else 'มาตรฐาน'}**",
        f"- คำที่เพิ่มในรอบนี้: **{payload.get('target_gesture') or 'แผนรวม'}**",
        f"- คลาสที่เทรนรวม: **{len(payload['classes'])} คลาส**",
        f"- โมเดล: **{payload.get('model_backend', 'svc')}**",
        f"- อุปกรณ์ที่ใช้เทรน final model: **{payload.get('training_device', 'CPU')}**",
        f"- ผลตามเกณฑ์: **{result}**",
        f"- Accuracy: **{aggregate['accuracy']:.4f}**",
        f"- Macro F1: **{aggregate['macro_f1']:.4f}**",
        policy_description,
        f"- Neutral false-positive rate: **{aggregate.get('neutral_false_positive_rate', 0.0):.4f}**",
        f"- Unknown false-activation rate: **{aggregate.get('unknown_false_activation_rate', 0.0):.4f}**",
        f"- จำนวนคลิป accepted: **{payload['accepted_clips']}**",
        f"- ระยะเวลาเทรนและสร้างรายงาน: **{payload['duration_seconds']:.3f} วินาที**",
        f"- Dataset SHA-256: `{payload['dataset_fingerprint_sha256']}`",
        "",
        "## ผลแยกตามท่า",
        "",
        "| ท่า | Precision | Recall | F1 | จำนวนทดสอบ |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in aggregate["per_class"]:
        lines.append(
            f"| {row['class_name']} | {row['precision']:.4f} | "
            f"{row['recall']:.4f} | {row['f1']:.4f} | {row['support']} |"
        )
    quick_mode = payload.get("mode") == "quick_trial"
    known_signers_holdout = (
        payload.get("evaluation_strategy") == "known_signers_session_holdout"
    )
    lines.extend(
        [
            "",
            "## ผลแยกตามชุดทดสอบ",
            "",
            "| ชุดทดสอบ | จำนวน Train | จำนวน Test | Accuracy | Macro F1 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for fold in payload["folds"]:
        test_label = (
            "session ที่กันไว้ของ person_01 และ person_02: "
            + ", ".join(fold["test_sessions"])
            if known_signers_holdout
            else fold["test_signer"]
        )
        lines.append(
            f"| {test_label} | {fold['train_clips']} | {fold['test_clips']} | "
            f"{fold['accuracy']:.4f} | {fold['macro_f1']:.4f} |"
        )
    lines.extend(["", "## ตรวจเกณฑ์", "", "| เกณฑ์ | ผล |", "| --- | --- |"])
    for name, passed in aggregate["acceptance_checks"].items():
        lines.append(f"| {name} | {'ผ่าน' if passed else 'ไม่ผ่าน'} |")
    limitations = payload.get("evaluation_limitations", [])
    if limitations:
        lines.extend(["", "## ข้อจำกัดเฉพาะรอบนี้", ""])
        lines.extend(f"- {item}" for item in limitations)
    lines.extend(
        [
            "",
            "## วิธีประเมิน",
            "",
            (
                "ใช้ grouped holdout โดยยึดผู้ทำท่าและรอบถ่ายเป็นหนึ่งกลุ่ม "
                "กลุ่มเดียวกันจึงไม่ปรากฏทั้ง train และ test "
                "ผลนี้ใช้คัดกรองเบื้องต้นก่อนเปิดกล้องทดลองจริง"
                if quick_mode
                else (
                    "ใช้ session holdout สำหรับผู้ใช้ที่เทรนไว้: โมเดลเรียนจาก "
                    "person_01 และ person_02 พร้อมกัน แล้วผลัดกันกันทุก session ของแต่ละคน "
                    "ไว้ทดสอบ จึงไม่มีคลิปหรือรอบถ่ายเดียวกันอยู่ทั้ง train และ test"
                    if known_signers_holdout
                    else "ใช้ Leave-One-Signer-Out จำนวน 2 fold: ฝึกจากสมาชิกหนึ่งคนและทดสอบกับอีกคน "
                    "จากนั้นสลับกัน คลิปจากผู้ทดสอบจึงไม่ปรากฏในชุดฝึกของ fold เดียวกัน"
                )
            ),
            "",
            "ไฟล์ `confusion_matrix.png`, `per_class_f1.png`, CSV และ JSON ในโฟลเดอร์นี้ "
            "สามารถนำไปใช้จัดทำเอกสารผลการทดลองได้",
            "",
            (
                "ข้อจำกัด: โหมดทดลองด่วนใช้ข้อมูลฐานเดิมร่วมกับคลิปคำใหม่จำนวนน้อย "
                "คะแนนนี้ไม่ใช่ผลทดสอบมาตรฐานสำหรับรายงานวิจัย ต้องทดสอบด้วยกล้องจริงและเก็บข้อมูลเพิ่มภายหลัง"
                if quick_mode
                else (
                    "ข้อจำกัด: ผลนี้ใช้ยืนยันการใช้งานสำหรับ person_01 และ person_02 เท่านั้น "
                    "ควรเก็บข้อมูลของผู้ใช้ใหม่แยกต่างหากเพื่อวัดความสามารถกับบุคคลภายนอกภายหลัง"
                    if known_signers_holdout
                    else "ข้อจำกัด: ผลนี้ประเมินจากสมาชิก 2 คน จึงใช้ยืนยันต้นแบบภายในกลุ่ม "
                    "และยังไม่ใช่หลักฐานว่าโมเดลใช้ได้กับบุคคลทั่วไป"
                )
            ),
            "",
            f"โมเดลในโฟลเดอร์นี้ยังไม่ถูกติดตั้งทับโมเดลหลักโดยอัตโนมัติ ({config.project_name})",
        ]
    )
    (experiment_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def list_experiments(root=EXPERIMENTS_DIR, target_gesture=None):
    """อ่าน experiment ที่สมบูรณ์และคืนรายการเรียงจากใหม่ไปเก่า."""
    root = Path(root)
    if not root.exists():
        return []
    experiments = []
    for directory in sorted(root.iterdir(), reverse=True):
        metrics_file = directory / "metrics.json"
        if not directory.is_dir() or not metrics_file.exists():
            continue
        try:
            payload = json.loads(metrics_file.read_text(encoding="utf-8"))
            aggregate = payload["aggregate"]
            experiment_target = str(payload.get("target_gesture", ""))
            if target_gesture is not None and experiment_target != target_gesture:
                continue
            experiments.append(
                {
                    "id": payload["experiment_id"],
                    "path": directory,
                    "created_at": payload["created_at"],
                    "accuracy": float(aggregate["accuracy"]),
                    "macro_f1": float(aggregate["macro_f1"]),
                    "passed": bool(aggregate["passed"]),
                    "target_gesture": experiment_target,
                    "mode": str(payload.get("mode", "standard")),
                    "evaluation_strategy": str(payload.get("evaluation_strategy", "")),
                    "evaluation_scope": str(payload.get("evaluation_scope", "")),
                }
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return sorted(experiments, key=lambda item: (item["created_at"], item["id"]), reverse=True)


def _write_experiment_index(root):
    """สร้าง CSV ดัชนีรวมเพื่อเปรียบเทียบผลทุกครั้งได้ในไฟล์เดียว."""
    rows = []
    for item in list_experiments(root):
        rows.append(
            {
                "experiment_id": item["id"],
                "created_at": item["created_at"],
                "accuracy": item["accuracy"],
                "macro_f1": item["macro_f1"],
                "passed": item["passed"],
                "target_gesture": item.get("target_gesture", ""),
                "mode": item.get("mode", "standard"),
                "report_path": str(item["path"] / "report.md"),
            }
        )
    _write_csv(
        Path(root) / "experiment_index.csv",
        [
            "experiment_id", "created_at", "target_gesture", "mode", "accuracy", "macro_f1", "passed",
            "report_path",
        ],
        rows,
    )


def _ensure_no_active_gesture_regression(new_custom, active_path=CUSTOM_GESTURES_FILE):
    """ปฏิเสธโมเดลเก่าที่จะทำให้คำซึ่งติดตั้งอยู่แล้วหายจากแอป."""
    current_active_names = {
        item.name for item in GestureCatalog(active_path=active_path).load_active()
    }
    new_active_names = {str(item.get("name", "")).strip() for item in new_custom}
    removed_names = sorted(current_active_names - new_active_names)
    if removed_names:
        raise HandVoxError(
            "ผลการทดลองนี้เก่ากว่าโมเดลปัจจุบันและจะทำให้คำหาย: "
            + ", ".join(removed_names)
            + " กรุณาเทรนคำเป้าหมายใหม่จากโมเดลล่าสุด"
        )


def activate_experiment(experiment_dir, allow_quick_trial=False, allow_unvalidated_trial=False):
    """ตรวจและติดตั้ง artifact SVC หรือ Temporal TCN แบบ staged/ย้อนคืนได้."""

    experiment_dir = Path(experiment_dir).resolve()
    try:
        experiment_dir.relative_to(EXPERIMENTS_DIR.resolve())
    except ValueError as error:
        raise HandVoxError("เลือกได้เฉพาะผลการทดลองภายในโฟลเดอร์ experiments") from error

    manifest_path = experiment_dir / "model_manifest.json"
    metrics_path = experiment_dir / "metrics.json"
    missing = [
        path.name for path in (manifest_path, metrics_path) if not path.exists()
    ]
    if missing:
        raise HandVoxError("ผลการทดลองขาดไฟล์: " + ", ".join(missing))
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HandVoxError(f"อ่าน manifest/metrics ไม่ได้: {error}") from error
    if metrics.get("mode") == "quick_trial" and not allow_quick_trial:
        raise HandVoxError(
            "ผลนี้เป็นโหมดทดลองด่วน ต้องยืนยันว่าจะติดตั้งเป็นโมเดลทดลองก่อน"
        )
    acceptance_passed = metrics.get("aggregate", {}).get("passed")
    experimental_override = acceptance_passed is False and allow_unvalidated_trial
    if acceptance_passed is not True and not experimental_override:
        raise HandVoxError("ผลการทดลองนี้ยังไม่ผ่านเกณฑ์ จึงไม่อนุญาตให้ติดตั้ง")

    backend = str(
        manifest.get("model_backend", metrics.get("model_backend", "svc"))
    ).strip()
    if backend not in {"svc", "temporal_tcn"}:
        raise HandVoxError(f"ไม่รองรับ model backend: {backend}")
    model_name = "model.pt" if backend == "temporal_tcn" else "model.pkl"
    model_source = experiment_dir / model_name
    labels_source = experiment_dir / "labels.pkl"
    required_paths = [model_source]
    if backend == "svc":
        required_paths.append(labels_source)
    missing = [path.name for path in required_paths if not path.exists()]
    if missing:
        raise HandVoxError("ผลการทดลองขาดไฟล์: " + ", ".join(missing))

    try:
        expected_classes = {
            item["name"] for item in manifest["visible_gestures"]
        }.union(manifest["internal_classes"])
        sequence_length = int(manifest.get("sequence_length", 30))
        if backend == "svc":
            with labels_source.open("rb") as file:
                labels = pickle.load(file)
            with model_source.open("rb") as file:
                model = pickle.load(file)
            if set(labels.classes_) != expected_classes:
                raise ValueError("labels ไม่ตรงกับ model manifest")
            if not getattr(model, "probability", False) or not callable(
                getattr(model, "predict_proba", None)
            ):
                raise ValueError("โมเดล SVC สำหรับติดตั้งต้องเทรนด้วย probability=true")
            if getattr(model, "n_features_in_", None) != (
                FEATURE_COUNT * sequence_length
            ):
                raise ValueError("จำนวน features ของ SVC ไม่ตรงกับตัวตรวจจับ")
        else:
            temporal_pipeline_from_manifest(manifest)
            model = TemporalClassifier.load(model_source, device="cpu")
            if set(model.classes_.tolist()) != expected_classes:
                raise ValueError("classes ใน TCN ไม่ตรงกับ model manifest")
            if model.input_size != OUTPUT_FEATURE_COUNT:
                raise ValueError("input size ของ TCN ไม่ตรงกับ feature pipeline")
            if model.sequence_length != sequence_length:
                raise ValueError("sequence length ของ TCN ไม่ตรงกับ manifest")
            if model.schema_version != FEATURE_SCHEMA_VERSION:
                raise ValueError("schema version ใน TCN artifact ไม่ตรงกับ manifest")
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        EOFError,
        pickle.UnpicklingError,
        TorchUnavailableError,
        RuntimeError,
    ) as error:
        raise HandVoxError(f"ตรวจไฟล์โมเดลก่อนติดตั้งไม่ผ่าน: {error}") from error

    new_custom = manifest["visible_gestures"]
    _ensure_no_active_gesture_regression(new_custom, CUSTOM_GESTURES_FILE)
    temporal_destination = TEMPORAL_MODEL_FILE
    # ช่วย test/deployment ที่เปลี่ยน MODEL_FILE ไปอีกโฟลเดอร์ แต่ไม่ได้ patch
    # TEMPORAL_MODEL_FILE โดยไม่เผลอแตะ artifact จริงใน workspace หลัก
    if temporal_destination.parent != MODEL_FILE.parent:
        temporal_destination = MODEL_FILE.parent / temporal_destination.name
    model_destination = (
        temporal_destination if backend == "temporal_tcn" else MODEL_FILE
    )
    temporary_custom = CUSTOM_GESTURES_FILE.with_suffix(".json.tmp")
    temporary_model = model_destination.with_suffix(model_destination.suffix + ".tmp")
    temporary_labels = LABEL_FILE.with_suffix(".pkl.tmp")
    temporary_manifest = MODEL_MANIFEST_FILE.with_suffix(".json.tmp")
    temporary_planned = PLANNED_GESTURES_FILE.with_suffix(".json.tmp")
    temporary_custom.write_text(
        json.dumps(new_custom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(model_source, temporary_model)
    if labels_source.exists():
        shutil.copy2(labels_source, temporary_labels)
    deployment_manifest = dict(manifest)
    deployment_manifest["deployment"] = {
        "status": "experimental_unvalidated" if experimental_override else (
            "quick_trial" if metrics.get("mode") == "quick_trial" else "validated"
        ),
        "acceptance_passed": acceptance_passed,
        "experimental_override_confirmed": bool(experimental_override),
        "activated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_experiment": str(experiment_dir),
    }
    deployment_manifest["evaluation"] = {
        **manifest.get("evaluation", {}), "passed": acceptance_passed
    }
    deployment_manifest.setdefault("training_signers", metrics.get("signers", []))
    deployment_manifest.setdefault("evaluation_strategy", metrics.get("evaluation_strategy", ""))
    deployment_manifest.setdefault("evaluation_scope", metrics.get("evaluation_scope", ""))
    temporary_manifest.write_text(
        json.dumps(deployment_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    visible_names = {item["name"] for item in new_custom}
    remaining_planned = [
        item
        for item in GestureCatalog().load_planned()
        if item.name not in visible_names
    ]
    temporary_planned.write_text(
        json.dumps(
            {"version": 1, "gestures": [asdict(item) for item in remaining_planned]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    managed_files = tuple(
        dict.fromkeys(
            (
                MODEL_FILE,
                temporal_destination,
                LABEL_FILE,
                MODEL_MANIFEST_FILE,
                CUSTOM_GESTURES_FILE,
                PLANNED_GESTURES_FILE,
                LEGACY_DATA_FILE,
            )
        )
    )
    existed_before = {source: source.exists() for source in managed_files}
    backup_dir = ROOT / "gesture_backups" / (
        "model_before_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    for source in managed_files:
        if source.exists():
            shutil.copy2(source, backup_dir / source.name)
    try:
        temporary_model.replace(model_destination)
        if temporary_labels.exists():
            temporary_labels.replace(LABEL_FILE)
        temporary_manifest.replace(MODEL_MANIFEST_FILE)
        temporary_custom.replace(CUSTOM_GESTURES_FILE)
        temporary_planned.replace(PLANNED_GESTURES_FILE)
        training_sequences = experiment_dir / "training_sequences.npz"
        if training_sequences.exists():
            # ข้อมูลสะสมนี้เป็นฐานสำหรับเพิ่มคำถัดไปโดยไม่ถ่ายคำเดิมซ้ำ
            temporary_sequences = LEGACY_DATA_FILE.with_suffix(".npz.tmp")
            shutil.copy2(training_sequences, temporary_sequences)
            temporary_sequences.replace(LEGACY_DATA_FILE)
    except OSError:
        for destination in managed_files:
            backup = backup_dir / destination.name
            if backup.exists():
                shutil.copy2(backup, destination)
            elif not existed_before[destination] and destination.exists():
                destination.unlink()
        raise
    return backup_dir
