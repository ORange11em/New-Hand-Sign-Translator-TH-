r"""Evaluate recorded person_03 clips against the unchanged installed 01+02 model.

Pending clips are included explicitly as provisional, never silently accepted.
Run from the project with: .venv\Scripts\python.exe tools/evaluate_person_03.py
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from handvox.dataset_v2 import DatasetV2Store
from handvox.external_collection import ADDITIONAL_TEST_SESSIONS
from handvox.external_evaluation import (
    _external_metrics,
    evaluate_external,
    get_training_signers,
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(rows, classes):
    actual = np.asarray([row["gesture_name"] for row in rows], dtype=str)
    predicted = np.asarray([row["prediction"] for row in rows], dtype=str)
    return {
        "clips": len(rows),
        "correct": sum(row["correct"] for row in rows),
        "quality_counts": dict(Counter(row["quality"] for row in rows)),
        **_external_metrics(actual, predicted, classes),
    }


def main():
    manifest_path = ROOT / "model_manifest.json"
    active = json.loads(manifest_path.read_text(encoding="utf-8"))
    experiment = (ROOT / "experiments" / active["experiment_id"]).resolve()
    if not experiment.is_relative_to((ROOT / "experiments").resolve()):
        raise ValueError("Invalid installed experiment path")
    saved = json.loads((experiment / "model_manifest.json").read_text(encoding="utf-8"))
    for field in (
        "model_backend", "model_artifact", "model_file", "sequence_length",
        "feature_count", "feature_schema_version", "feature_schema",
        "visible_gestures", "internal_classes", "recognition_policy",
    ):
        if active.get(field) != saved.get(field):
            raise ValueError(f"Installed and saved manifests differ: {field}")
    installed_model = ROOT / "gesture_model.pt"
    saved_model = (experiment / saved["model_artifact"]).resolve()
    if not saved_model.is_relative_to(experiment):
        raise ValueError("Invalid model artifact path")
    if sha256(installed_model) != sha256(saved_model):
        raise ValueError("Installed model is not the saved experiment model")
    if set(get_training_signers(experiment)) != {"person_01", "person_02"}:
        raise ValueError("This report requires a model trained only on 01+02")
    store = DatasetV2Store(ROOT / "dataset_external_v2")
    if {row.signer_id for row in store.records()} != {"person_03"}:
        raise ValueError("This report requires only person_03 in the external dataset")
    protected = [
        manifest_path, installed_model, saved_model,
        experiment / "model_manifest.json", experiment / "training_sequences.npz",
        experiment / "training_config.snapshot.json", experiment / "metrics.json",
        ROOT / "training_config.json", ROOT / "dataset_v2" / "metadata.jsonl",
        store.manifest,
    ]
    before = {str(path.relative_to(ROOT)): sha256(path) for path in protected}
    directory, payload = evaluate_external(experiment, store, include_pending=True)
    after = {str(path.relative_to(ROOT)): sha256(path) for path in protected}
    if before != after:
        raise RuntimeError("Protected model or dataset files changed during evaluation")
    rows = payload["clips"]
    cohorts = {"all": summarize(rows, payload["classes"])}
    for name, session_ids in (
        ("new_sessions_05_07", set(ADDITIONAL_TEST_SESSIONS)),
        ("original_sessions_01_04", {f"session_{number:02d}" for number in range(1, 5)}),
    ):
        selected = [row for row in rows if row["session_id"] in session_ids]
        if selected:
            cohorts[name] = summarize(selected, payload["classes"])
    confusions = Counter(
        (row["gesture_name"], row["prediction"]) for row in rows if not row["correct"]
    )
    summary = {
        "evaluation_id": payload["evaluation_id"],
        "experiment_id": payload["experiment_id"],
        "evaluation_status": payload["evaluation_status"],
        "model_matches_installed": True,
        "protected_files_unchanged": True,
        "protected_sha256": before,
        "cohorts": cohorts,
        "per_session": payload["per_session"],
        "confusions": [
            {"actual": actual, "predicted": predicted, "count": count}
            for (actual, predicted), count in confusions.most_common()
        ],
    }
    (directory / "collection_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# ผลวัด person_03 กับโมเดลที่โปรแกรมติดตั้งอยู่", "",
        f"โมเดล `{payload['experiment_id']}` ฝึกจาก person_01 + person_02 เท่านั้น "
        "ตรวจว่าไฟล์โมเดลและนโยบายทำนายตรงกับโปรแกรมก่อนวัดผลแล้ว "
        "ไม่มีการเทรน ปรับ threshold เปลี่ยนโมเดล หรือแก้สถานะคุณภาพคลิป", "",
        f"สถานะ: **{payload['evaluation_status']}** — accepted {payload['accepted_clips']} คลิป "
        f"และ pending {payload['pending_clips']} คลิป", "",
        "## คะแนนหลัก (19 คลาส รวม neutral และ unknown)", "",
        "| ชุดข้อมูล | ถูก / ทั้งหมด | Accuracy | Macro F1 |",
        "|---|---:|---:|---:|",
    ]
    labels = {"all": "ทั้งหมด", "new_sessions_05_07": "อัดเพิ่ม session 05–07",
              "original_sessions_01_04": "เดิม session 01–04"}
    for name, metrics in cohorts.items():
        lines.append(f"| {labels[name]} | {metrics['correct']} / {metrics['clips']} | "
                     f"{metrics['accuracy']:.2%} | {metrics['macro_f1']:.2%} |")
    lines += ["", "## แยกตาม session", "",
              "| Session | คลิป | Accuracy | Macro F1 |", "|---|---:|---:|---:|"]
    for session, metrics in payload["per_session"].items():
        lines.append(f"| {session} | {metrics['evaluated_clips']} | "
                     f"{metrics['accuracy']:.2%} | {metrics['macro_f1']:.2%} |")
    lines += ["", "## รายคลาส — ทั้งหมด", "",
              "| ท่า/คลาส | จำนวนคลิป | Precision | Recall | F1 |", "|---|---:|---:|---:|---:|"]
    for row in sorted(cohorts["all"]["per_class"], key=lambda row: row["recall"]):
        lines.append(f"| {row['class_name']} | {row['support']} | {row['precision']:.2%} | "
                     f"{row['recall']:.2%} | {row['f1']:.2%} |")
    lines += ["", "## คู่ที่ทายผิด (ทั้งหมด)", "",
              "| ท่าจริง | คำทำนาย | จำนวน |", "|---|---|---:|"]
    for (actual, predicted), count in confusions.most_common():
        lines.append(f"| {actual} | {predicted} | {count} |")
    lines += [
        "", "## ขอบเขตและข้อควรระวัง", "",
        "- เป็นการวัดระดับคลิป โดยใช้ saved recognition policy รวมเกณฑ์ confidence/margin "
        "ยังไม่รวมการยืนยันท่าหลายเฟรม การกันคำซ้ำ และบทสนทนาต่อเนื่องจากกล้อง",
        "- pending ยังไม่ผ่านการตรวจความถูกต้องของท่า/ป้ายกำกับ จึงเป็นผลเบื้องต้น "
        "การตรวจขนาดข้อมูล ค่าว่าง และข้อมูลซ้ำไม่ใช่การตรวจคุณภาพท่าจากวิดีโอ",
        "- ไม่ควรลบคลิปเพียงเพราะโมเดลทายผิด ตรวจคุณภาพตามเกณฑ์เดียวกันโดยไม่อิงคำทำนาย "
        "และบันทึกเหตุผลหากคลิปใช้ไม่ได้",
        "- ผลนี้อธิบายคน 03 คนเดียว แม้หลาย session ก็ไม่เท่ากับหลายคน "
        "และยังสรุปไม่ได้ว่าโมเดลทำได้เท่านี้กับคนใหม่ทุกคนหรือไม่มี overfitting",
        "- คะแนนเดิมและคะแนนรอบใหม่เป็นคนละคลิป/สภาพการอัด ไม่ใช่หลักฐานว่าโมเดลดีขึ้นหรือแย่ลง "
        "เพราะใช้โมเดลเดิมทุกชุด",
        "- ไม่ใช้คะแนนนี้ปรับโมเดลแล้วอ้างว่าเป็น final test ที่ไม่เคยใช้ตัดสินใจ",
        "- ตรวจ SHA-256 ยืนยันว่าโมเดล manifest ข้อมูลเทรน และ metadata ชุดทดสอบไม่เปลี่ยนระหว่างวัด",
        "", "ดูผลรายคลิปใน [predictions.csv](predictions.csv) และข้อมูลตรวจสอบใน "
        "[collection_summary.json](collection_summary.json)",
    ]
    (directory / "collection_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(directory / "collection_summary.md"),
        "status": payload["evaluation_status"],
        "cohorts": {name: {key: value for key, value in metrics.items()
                            if key not in {"per_class", "confusion_matrix", "classification_report"}}
                    for name, metrics in cohorts.items()},
        "per_class": cohorts["all"]["per_class"],
        "confusions": summary["confusions"],
        "protected_files_unchanged": before == after,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
