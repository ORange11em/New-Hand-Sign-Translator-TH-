"""ตรวจความพร้อมสำหรับหน้า Dashboard แบบอ่านอย่างเดียวและไม่เปิดกล้อง."""

from dataclasses import dataclass
import json
import pickle
import sys

import numpy as np

from handvox.dataset_v2 import DatasetV2Store
from handvox.gesture_catalog import GestureCatalog
from handvox.paths import (
    LABEL_FILE,
    LEGACY_DATA_FILE,
    MODEL_FILE,
    MODEL_MANIFEST_FILE,
    TEMPORAL_MODEL_FILE,
)


@dataclass(frozen=True)
class DiagnosticItem:
    """ผลตรวจหนึ่งแถวที่หน้า Dashboard นำไปกำหนดข้อความและสีสถานะ."""

    name: str
    status: str
    message: str


def run_diagnostics():
    """ตรวจ Python โมเดล ข้อมูลเดิม คำศัพท์ และ Dataset V2 โดยไม่เปลี่ยนไฟล์."""
    results = []
    supported = sys.version_info[:2] in ((3, 10), (3, 11))
    results.append(
        DiagnosticItem(
            "Python",
            "ok" if supported else "warning",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )

    # โหลด PyTorch ก่อนเปิด pickle ของ scikit-learn บน Windows บางเครื่อง
    # เพื่อหลีกเลี่ยง runtime DLL ชนกันจน c10.dll เริ่มทำงานไม่ได้ (WinError 1114)
    try:
        from handvox.temporal_model import select_device

        device = select_device("auto")
        if device.selected.startswith("cuda"):
            results.append(
                DiagnosticItem("ตัวเร่งโมเดล", "ok", f"GPU - {device.device_name}")
            )
        elif device.selected == "cpu":
            results.append(
                DiagnosticItem(
                    "ตัวเร่งโมเดล",
                    "warning",
                    device.fallback_reason or "ใช้ CPU (ไม่พบ CUDA)",
                )
            )
        else:
            results.append(
                DiagnosticItem("ตัวเร่งโมเดล", "error", device.fallback_reason)
            )
    except Exception as error:
        results.append(DiagnosticItem("ตัวเร่งโมเดล", "error", str(error)))

    catalog = GestureCatalog()
    try:
        active = catalog.load_active()
        results.append(DiagnosticItem("ท่าที่ใช้งาน", "ok", f"{len(active)} ท่า"))
    except Exception as error:
        active = []
        results.append(DiagnosticItem("ท่าที่ใช้งาน", "error", str(error)))

    try:
        manifest = (
            json.loads(MODEL_MANIFEST_FILE.read_text(encoding="utf-8"))
            if MODEL_MANIFEST_FILE.exists()
            else {}
        )
    except (OSError, json.JSONDecodeError, TypeError) as error:
        manifest = {}
        results.append(DiagnosticItem("Manifest", "error", f"อ่านไม่ได้: {error}"))

    backend = str(
        manifest.get("model_backend", manifest.get("backend", "legacy_svc"))
    ).lower()
    active_names = {item.name for item in active}
    internal_names = set(manifest.get("internal_classes", []))
    expected_names = active_names.union(internal_names)
    if backend == "temporal_tcn":
        if not TEMPORAL_MODEL_FILE.exists():
            results.append(DiagnosticItem("โมเดล", "error", "ไม่พบ gesture_model.pt"))
        else:
            try:
                from handvox.temporal_model import TemporalClassifier

                temporal = TemporalClassifier.load(TEMPORAL_MODEL_FILE, device="cpu")
                model_names = {str(name) for name in temporal.classes_}
                matches = model_names == expected_names
                results.append(
                    DiagnosticItem(
                        "โมเดล",
                        "ok" if matches else "error",
                        f"TCN - {len(model_names)} คลาส"
                        if matches
                        else "รายชื่อท่าไม่ตรงกับ TCN",
                    )
                )
            except Exception as error:
                results.append(
                    DiagnosticItem("โมเดล", "error", f"เปิด TCN ไม่ได้: {error}")
                )
    elif not MODEL_FILE.exists() or not LABEL_FILE.exists():
        results.append(DiagnosticItem("โมเดล", "error", "ไม่พบโมเดล SVC หรือ labels"))
    else:
        try:
            with LABEL_FILE.open("rb") as file:
                labels = pickle.load(file)
            model_names = set(labels.classes_)
            matches = model_names == expected_names
            results.append(
                DiagnosticItem(
                    "โมเดล",
                    "ok" if matches else "error",
                    f"SVC - {len(model_names)} คลาส"
                    if matches
                    else "รายชื่อท่าไม่ตรงกับโมเดล",
                )
            )
        except Exception as error:
            results.append(DiagnosticItem("โมเดล", "error", f"อ่านไม่ได้: {error}"))

    if LEGACY_DATA_FILE.exists():
        try:
            with np.load(LEGACY_DATA_FILE, allow_pickle=False) as data:
                clips = data["clips"]
            results.append(DiagnosticItem("ข้อมูลเดิม", "ok", f"{len(clips)} คลิป"))
        except Exception as error:
            results.append(DiagnosticItem("ข้อมูลเดิม", "error", f"อ่านไม่ได้: {error}"))
    else:
        results.append(DiagnosticItem("ข้อมูลเดิม", "warning", "ยังไม่มีคลิป"))

    try:
        planned = catalog.load_planned()
        results.append(DiagnosticItem("ท่าที่วางแผน", "ok", f"{len(planned)} ท่า"))
    except Exception as error:
        results.append(DiagnosticItem("ท่าที่วางแผน", "error", str(error)))

    try:
        summary = DatasetV2Store().summary()
        status = "ok" if summary["clips"] else "warning"
        results.append(DiagnosticItem("Dataset V2", status, f"{summary['clips']} คลิป"))
    except Exception as error:
        results.append(DiagnosticItem("Dataset V2", "error", str(error)))
    return results
