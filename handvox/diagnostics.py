"""ตรวจความพร้อมสำหรับหน้า Dashboard แบบอ่านอย่างเดียวและไม่เปิดกล้อง."""

from dataclasses import dataclass
import json
import pickle
import sys

import numpy as np

from handvox.dataset_v2 import DatasetV2Store
from handvox.gesture_catalog import GestureCatalog
from handvox.paths import LABEL_FILE, LEGACY_DATA_FILE, MODEL_FILE, MODEL_MANIFEST_FILE


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

    catalog = GestureCatalog()
    try:
        active = catalog.load_active()
        results.append(DiagnosticItem("ท่าที่ใช้งาน", "ok", f"{len(active)} ท่า"))
    except Exception as error:
        active = []
        results.append(DiagnosticItem("ท่าที่ใช้งาน", "error", str(error)))

    if not MODEL_FILE.exists() or not LABEL_FILE.exists():
        results.append(
            DiagnosticItem("โมเดล", "error", "ไม่พบไฟล์โมเดลหรือ labels")
        )
    else:
        try:
            with LABEL_FILE.open("rb") as file:
                labels = pickle.load(file)
            model_names = set(labels.classes_)
            active_names = {item.name for item in active}
            internal_names = set()
            if MODEL_MANIFEST_FILE.exists():
                manifest = json.loads(MODEL_MANIFEST_FILE.read_text(encoding="utf-8"))
                internal_names = set(manifest.get("internal_classes", []))
            matches = model_names == active_names.union(internal_names)
            results.append(
                DiagnosticItem(
                    "โมเดล",
                    "ok" if matches else "error",
                    f"{len(model_names)} คลาส"
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
