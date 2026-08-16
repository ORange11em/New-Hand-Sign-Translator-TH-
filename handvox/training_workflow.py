"""ตรวจความพร้อม เทรน วัดผล สร้างรายงาน และติดตั้งโมเดล V2 อย่างปลอดภัย.

ไฟล์นี้ไม่ติดตั้งโมเดลทันทีหลังเทรน แต่สร้าง experiment แยกแต่ละรอบก่อน
และยอมให้เปิดใช้งานเฉพาะผลที่ผ่านเกณฑ์ใน training_config.json
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


def _validate_sequence_files(config, store, records):
    """ตรวจว่า accepted clips มีไฟล์จริง shape ถูก และไม่มี NaN/Infinity."""
    invalid = []
    missing = []
    accepted = [record for record in records if record.quality == "accepted"]
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
                "พบผู้ทำท่านอกแผน: " + ", ".join(unexpected_signers),
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
        if row["accepted"] >= minimum and row["sessions"] < 2:
            items.append(
                ReadinessItem(
                    "error",
                    "session_missing",
                    f"{label}: ต้องมี accepted จากทั้ง 2 session",
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

    items.extend(_validate_sequence_files(config, store, records))
    error_count = sum(item.status == "error" for item in items)
    accepted_count = sum(
        record.quality == "accepted" and record.gesture_name in config.all_classes
        for record in records
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
            expected_shape = (config.collection.sequence_length, FEATURE_COUNT)
            if clips.ndim != 3 or tuple(clips.shape[1:]) != expected_shape:
                raise ValueError(f"shape ต้องเป็น (จำนวนคลิป, {expected_shape[0]}, {expected_shape[1]})")
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
        for record in store.records()
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
        for item in store.records()
        if item.quality == "accepted" and item.gesture_name in config.all_classes
    ]
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
    axis.set_title("HandVox Cross-person Confusion Matrix", fontproperties=font)
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
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "git_commit": git_commit,
    }


def _manifest(config, metrics, experiment_id):
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
    return {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "visible_gestures": visible,
        "internal_classes": list(config.internal_classes),
        "evaluation": {
            "accuracy": metrics["accuracy"],
            "macro_f1": metrics["macro_f1"],
            "passed": metrics["passed"],
        },
    }


def _acceptance_result(config, metrics):
    """เทียบผลวัดกับเกณฑ์รวม รายคลาส คำสำคัญ และ neutral."""
    recalls = {row["class_name"]: row["recall"] for row in metrics["per_class"]}
    visible_recalls = [recalls[name] for name in config.visible_gestures]
    critical_recalls = [recalls[name] for name in config.critical_gestures]
    metric_class_names = [row["class_name"] for row in metrics["per_class"]]
    neutral_index = metric_class_names.index("neutral")
    neutral_row = metrics["confusion_matrix"][neutral_index]
    neutral_total = sum(neutral_row)
    neutral_false_positive_rate = (
        (neutral_total - neutral_row[neutral_index]) / neutral_total
        if neutral_total
        else 1.0
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
    }
    return all(checks.values()), checks, neutral_false_positive_rate


# ── ขั้นที่ 4: เทรนแบบข้ามผู้ทำและสร้าง experiment ──────────
def train_and_evaluate(config=None, store=None, output_root=EXPERIMENTS_DIR):
    """ทำ Leave-One-Signer-Out สอง fold ฝึก final model และสร้างไฟล์รายงาน."""
    from sklearn.preprocessing import LabelEncoder
    from sklearn.svm import SVC

    started_at = datetime.now().astimezone()
    started_timer = time.perf_counter()
    config = config or load_training_config()
    store = store or DatasetV2Store()
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

    parameters = dict(config.training.parameters)
    for test_signer in config.collection.signers:
        train_mask = signers != test_signer
        test_mask = signers == test_signer
        classifier = SVC(random_state=config.training.random_seed, **parameters)
        classifier.fit(features[train_mask], targets[train_mask])
        predictions = classifier.predict(features[test_mask])
        fold_metrics = _metric_payload(
            targets[test_mask], predictions, class_ids, class_names
        )
        fold_metrics.update(
            {
                "test_signer": test_signer,
                "train_signers": sorted(set(signers[train_mask])),
                "train_clips": int(train_mask.sum()),
                "test_clips": int(test_mask.sum()),
            }
        )
        fold_results.append(fold_metrics)
        all_true.extend(targets[test_mask].tolist())
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
        "evaluation_strategy": config.training.evaluation_strategy,
        "target_gesture": config.target_gesture,
        "dataset_fingerprint_sha256": fingerprint,
        "accepted_clips": len(records),
        "signers": list(config.collection.signers),
        "sessions_present": sorted(set(sessions)),
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

    manifest = _manifest(config, aggregate, experiment_id)
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
            "neutral_false_positive_rate", "passed", "dataset_fingerprint_sha256",
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
            "test_signer", "train_signers", "train_clips", "test_clips",
            "accuracy", "macro_precision", "macro_recall", "macro_f1",
            "weighted_precision", "weighted_recall", "weighted_f1",
        ],
        [
            {
                key: ", ".join(row[key]) if isinstance(row[key], list) else row[key]
                for key in (
                    "test_signer", "train_signers", "train_clips", "test_clips",
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


def train_quick_trial(config, store=None, output_root=EXPERIMENTS_DIR):
    """เทรนโมเดลทดลองจากข้อมูลฐานคำเดิมและคลิป accepted ของคำใหม่.

    ใช้ stratified holdout เพื่อบันทึกค่าทดสอบเบื้องต้น โมเดลและชุดข้อมูลสะสม
    ถูกเก็บใน experiment ก่อน และยังไม่เขียนทับโมเดลหลักจนกว่าจะ activate
    """
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder
    from sklearn.svm import SVC

    if config.mode != "quick_trial":
        raise HandVoxError("train_quick_trial ต้องใช้ config โหมด quick_trial")
    store = store or DatasetV2Store()
    readiness = quick_trial_readiness(config, store)
    if not readiness.ready:
        raise HandVoxError("ข้อมูลคำใหม่ยังไม่ถึงขั้นต่ำสำหรับเทรนทดลองด่วน")

    started_at = datetime.now().astimezone()
    started_timer = time.perf_counter()
    target = config.target_gesture
    with np.load(LEGACY_DATA_FILE, allow_pickle=False) as data:
        base_clips = data["clips"].astype(np.float32)
        base_labels = data["labels"].astype(str)
    keep = np.isin(base_labels, [name for name in config.visible_gestures if name != target])
    base_clips = base_clips[keep]
    base_labels = base_labels[keep]

    target_records = sorted(
        (
            record
            for record in store.records()
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
    features = clips.reshape(len(clips), -1)
    encoder = LabelEncoder()
    encoder.fit(list(config.visible_gestures))
    targets = encoder.transform(labels)
    class_names = list(encoder.classes_)
    class_ids = list(range(len(class_names)))
    test_count = max(len(class_names), int(round(len(features) * 0.2)))
    train_x, test_x, train_y, test_y = train_test_split(
        features,
        targets,
        test_size=test_count,
        random_state=config.training.random_seed,
        stratify=targets,
    )
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
            "test_signer": "stratified_holdout",
            "train_signers": ["ข้อมูลฐานเดิม", "Dataset V2 คำใหม่"],
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
        "evaluation_strategy": config.training.evaluation_strategy,
        "target_gesture": target,
        "dataset_fingerprint_sha256": digest.hexdigest(),
        "accepted_clips": len(clips),
        "base_clips": len(base_clips),
        "new_target_clips": len(target_clips),
        "signers": sorted({record.signer_id for record in target_records}),
        "sessions_present": sorted({record.session_id for record in target_records}),
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
    np.savez_compressed(
        experiment_dir / "training_sequences.npz",
        clips=clips.astype(np.float32),
        labels=labels,
    )
    manifest = _manifest(config, aggregate, experiment_id)
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
    lines = [
        f"# ผลการทดลอง HandVox — {payload['experiment_id']}",
        "",
        f"- โหมด: **{'ทดลองด่วน' if payload.get('mode') == 'quick_trial' else 'มาตรฐาน'}**",
        f"- คำที่เพิ่มในรอบนี้: **{payload.get('target_gesture') or 'แผนรวม'}**",
        f"- คลาสที่เทรนรวม: **{len(payload['classes'])} คลาส**",
        f"- ผลตามเกณฑ์: **{result}**",
        f"- Accuracy: **{aggregate['accuracy']:.4f}**",
        f"- Macro F1: **{aggregate['macro_f1']:.4f}**",
        f"- Neutral false-positive rate: **{aggregate.get('neutral_false_positive_rate', 0.0):.4f}**",
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
    lines.extend(
        [
            "",
            "## ผลแยกตามผู้ทดสอบ",
            "",
            "| ผู้ที่ใช้ทดสอบ | จำนวน Train | จำนวน Test | Accuracy | Macro F1 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for fold in payload["folds"]:
        lines.append(
            f"| {fold['test_signer']} | {fold['train_clips']} | {fold['test_clips']} | "
            f"{fold['accuracy']:.4f} | {fold['macro_f1']:.4f} |"
        )
    lines.extend(["", "## ตรวจเกณฑ์", "", "| เกณฑ์ | ผล |", "| --- | --- |"])
    for name, passed in aggregate["acceptance_checks"].items():
        lines.append(f"| {name} | {'ผ่าน' if passed else 'ไม่ผ่าน'} |")
    lines.extend(
        [
            "",
            "## วิธีประเมิน",
            "",
            (
                "ใช้ stratified holdout แบ่งตัวอย่างทุกคำเป็น train/test โดยคงสัดส่วนคลาส "
                "ผลนี้ใช้คัดกรองเบื้องต้นก่อนเปิดกล้องทดลองจริง"
                if quick_mode
                else "ใช้ Leave-One-Signer-Out จำนวน 2 fold: ฝึกจากสมาชิกหนึ่งคนและทดสอบกับอีกคน "
                "จากนั้นสลับกัน คลิปจากผู้ทดสอบจึงไม่ปรากฏในชุดฝึกของ fold เดียวกัน"
            ),
            "",
            "ไฟล์ `confusion_matrix.png`, `per_class_f1.png`, CSV และ JSON ในโฟลเดอร์นี้ "
            "สามารถนำไปใช้จัดทำเอกสารผลการทดลองได้",
            "",
            (
                "ข้อจำกัด: โหมดทดลองด่วนใช้ข้อมูลฐานเดิมร่วมกับคลิปคำใหม่จำนวนน้อย "
                "คะแนนนี้ไม่ใช่ผลทดสอบมาตรฐานสำหรับรายงานวิจัย ต้องทดสอบด้วยกล้องจริงและเก็บข้อมูลเพิ่มภายหลัง"
                if quick_mode
                else "ข้อจำกัด: ผลนี้ประเมินจากสมาชิก 2 คน จึงใช้ยืนยันต้นแบบภายในกลุ่ม "
                "และยังไม่ใช่หลักฐานว่าโมเดลใช้ได้กับบุคคลทั่วไป"
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
                }
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return experiments


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


def activate_experiment(experiment_dir, allow_quick_trial=False):
    """ตรวจผล สำรองของเดิม แล้วติดตั้ง model/labels/manifest แบบ staged."""
    experiment_dir = Path(experiment_dir).resolve()
    try:
        experiment_dir.relative_to(EXPERIMENTS_DIR.resolve())
    except ValueError as error:
        raise HandVoxError("เลือกได้เฉพาะผลการทดลองภายในโฟลเดอร์ experiments") from error
    required = {
        "model": experiment_dir / "model.pkl",
        "labels": experiment_dir / "labels.pkl",
        "manifest": experiment_dir / "model_manifest.json",
        "metrics": experiment_dir / "metrics.json",
    }
    missing = [path.name for path in required.values() if not path.exists()]
    if missing:
        raise HandVoxError("ผลการทดลองขาดไฟล์: " + ", ".join(missing))
    metrics = json.loads(required["metrics"].read_text(encoding="utf-8"))
    if metrics.get("mode") == "quick_trial" and not allow_quick_trial:
        raise HandVoxError(
            "ผลนี้เป็นโหมดทดลองด่วน ต้องยืนยันว่าจะติดตั้งเป็นโมเดลทดลองก่อน"
        )
    if not metrics["aggregate"]["passed"]:
        raise HandVoxError("ผลการทดลองนี้ยังไม่ผ่านเกณฑ์ จึงไม่อนุญาตให้ติดตั้ง")
    manifest = json.loads(required["manifest"].read_text(encoding="utf-8"))
    try:
        with required["labels"].open("rb") as file:
            labels = pickle.load(file)
        with required["model"].open("rb") as file:
            model = pickle.load(file)
        expected_classes = {
            item["name"] for item in manifest["visible_gestures"]
        }.union(manifest["internal_classes"])
        if set(labels.classes_) != expected_classes:
            raise ValueError("labels ไม่ตรงกับ model manifest")
        if getattr(model, "n_features_in_", None) != FEATURE_COUNT * 30:
            raise ValueError("จำนวน features ของโมเดลไม่ตรงกับตัวตรวจจับ")
    except (
        OSError, KeyError, TypeError, ValueError, AttributeError, EOFError,
        pickle.UnpicklingError,
    ) as error:
        raise HandVoxError(f"ตรวจไฟล์โมเดลก่อนติดตั้งไม่ผ่าน: {error}") from error

    new_custom = manifest["visible_gestures"]
    _ensure_no_active_gesture_regression(new_custom, CUSTOM_GESTURES_FILE)
    temporary_custom = CUSTOM_GESTURES_FILE.with_suffix(".json.tmp")
    temporary_model = MODEL_FILE.with_suffix(".pkl.tmp")
    temporary_labels = LABEL_FILE.with_suffix(".pkl.tmp")
    temporary_manifest = MODEL_MANIFEST_FILE.with_suffix(".json.tmp")
    temporary_planned = PLANNED_GESTURES_FILE.with_suffix(".json.tmp")
    temporary_custom.write_text(
        json.dumps(new_custom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(required["model"], temporary_model)
    shutil.copy2(required["labels"], temporary_labels)
    shutil.copy2(required["manifest"], temporary_manifest)
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
    managed_files = (
        MODEL_FILE,
        LABEL_FILE,
        MODEL_MANIFEST_FILE,
        CUSTOM_GESTURES_FILE,
        PLANNED_GESTURES_FILE,
        LEGACY_DATA_FILE,
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
        temporary_model.replace(MODEL_FILE)
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
