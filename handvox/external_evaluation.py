"""วัดโมเดลที่บันทึกไว้กับผู้ทำท่าใหม่ และเก็บรายงานแต่ละรอบแยกจากผลเทรน."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import pickle
from types import SimpleNamespace
from uuid import uuid4

import numpy as np

from body_features import FEATURE_COUNT
from handvox.errors import DataFileError, HandVoxError
from handvox.feature_pipeline import (
    AugmentationConfig,
    FEATURE_SCHEMA_VERSION,
    FeaturePipelineConfig,
    OUTPUT_FEATURE_COUNT,
    TemporalFeaturePipeline,
)
from handvox.paths import DATASET_V2_DIR
from handvox.temporal_model import TemporalClassifier
from handvox.training_workflow import (
    _metric_payload,
    _predictions_with_recognition_policy,
    _write_confusion_csv,
    _write_csv,
)


def _read_json(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("ต้องเป็น JSON object")
        return payload
    except (OSError, ValueError) as error:
        raise DataFileError(f"อ่าน {Path(path).name} ไม่ได้: {error}") from error


def _sequence_hash(sequence):
    values = np.ascontiguousarray(sequence, dtype="<f4")
    return hashlib.sha256(values.tobytes()).hexdigest()


def _training_provenance(experiment_dir):
    experiment_dir = Path(experiment_dir)
    signers = set()
    for filename in ("training_config.snapshot.json", "metrics.json"):
        payload = _read_json(experiment_dir / filename)
        values = (
            payload.get("collection", {}).get("signers", [])
            if filename == "training_config.snapshot.json"
            else payload.get("signers", [])
        )
        if not isinstance(values, list) or any(not str(value).strip() for value in values):
            raise DataFileError(f"รายชื่อผู้เทรนใน {filename} ไม่ถูกต้อง")
        signers.update(str(value).strip() for value in values)
    try:
        with np.load(experiment_dir / "training_sequences.npz", allow_pickle=False) as archive:
            clips = archive["clips"].astype(np.float32)
            signer_ids = np.char.strip(archive["signer_ids"].astype(str))
            labels = archive["labels"].astype(str)
            session_ids = np.char.strip(archive["session_ids"].astype(str))
            if (
                clips.ndim != 3
                or clips.shape[2] != FEATURE_COUNT
                or not len(clips)
                or not np.isfinite(clips).all()
                or any(values.shape != (len(clips),) for values in (signer_ids, labels, session_ids))
                or np.any(signer_ids == "")
                or np.any(session_ids == "")
            ):
                raise ValueError("sequence หรือข้อมูลผู้ทำท่า/session ไม่ครบ")
            if "group_metadata_available" in archive and not np.all(archive["group_metadata_available"]):
                raise ValueError("มีข้อมูลเทรนที่ไม่ทราบผู้ทำท่า")
            signers.update(signer_ids.tolist())
            hashes = {_sequence_hash(sequence) for sequence in clips}
    except (OSError, ValueError, KeyError) as error:
        raise DataFileError(
            "ยืนยันข้อมูลผู้เทรนและคลิปเดิมไม่ได้จาก training_sequences.npz: " + str(error)
        ) from error
    if not signers:
        raise DataFileError("ไม่พบรายชื่อผู้ทำท่าที่ใช้เทรนโมเดลนี้")
    return tuple(sorted(signers)), hashes


def get_training_signers(experiment_dir):
    """คืนรายชื่อผู้เทรนจาก snapshot, metrics และ metadata ของคลิปที่บันทึกไว้."""
    return _training_provenance(experiment_dir)[0]


def get_experiment_classes(experiment_dir):
    manifest = _read_json(Path(experiment_dir) / "model_manifest.json")
    try:
        names = tuple(item["name"] for item in manifest["visible_gestures"]) + tuple(
            manifest["internal_classes"]
        )
        if not names or any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("รายชื่อคลาสว่างหรือไม่ถูกต้อง")
        if len(names) != len(set(names)):
            raise ValueError("รายชื่อคลาสซ้ำ")
        return names
    except (KeyError, TypeError, ValueError) as error:
        raise DataFileError(f"คลาสใน manifest ไม่ถูกต้อง: {error}") from error


def get_experiment_sequence_length(experiment_dir):
    manifest = _read_json(Path(experiment_dir) / "model_manifest.json")
    length = manifest.get("sequence_length")
    if not isinstance(length, int) or isinstance(length, bool) or length < 1:
        raise DataFileError("จำนวนเฟรมใน manifest ไม่ถูกต้อง")
    return length


def _model_path(experiment_dir, filename):
    target = (experiment_dir / str(filename)).resolve()
    if not target.is_relative_to(experiment_dir.resolve()) or not target.is_file():
        raise DataFileError(f"ไม่พบไฟล์โมเดลภายใน experiment: {filename}")
    return target


def _saved_policy(manifest):
    values = manifest.get("recognition_policy")
    if values is None:
        return None
    try:
        confidence = float(values.get("minimum_confidence", 0.0))
        margin = float(values.get("minimum_probability_margin", 0.0))
        if not 0 <= confidence <= 1 or not 0 <= margin <= 1:
            raise ValueError("ค่าต้องอยู่ระหว่าง 0 และ 1")
    except (AttributeError, TypeError, ValueError) as error:
        raise DataFileError(f"recognition_policy ที่บันทึกไว้ไม่ถูกต้อง: {error}") from error
    return SimpleNamespace(
        visible_gestures=tuple(item["name"] for item in manifest["visible_gestures"]),
        acceptance=SimpleNamespace(
            minimum_prediction_confidence=confidence,
            minimum_probability_margin=margin,
        ),
    )


def _load_predictor(experiment_dir, manifest, sequence_length):
    backend = manifest.get("model_backend", "svc")
    artifact = manifest.get("model_artifact", manifest.get("model_file"))
    artifact = artifact or ("model.pt" if backend == "temporal_tcn" else "model.pkl")
    model_path = _model_path(experiment_dir, artifact)
    try:
        if backend == "temporal_tcn":
            schema = manifest["feature_schema"]
            if (
                manifest["feature_schema_version"] != FEATURE_SCHEMA_VERSION
                or schema["schema_version"] != FEATURE_SCHEMA_VERSION
                or int(manifest["feature_count"]) != OUTPUT_FEATURE_COUNT
            ):
                raise ValueError("feature schema ของ TCN ไม่ตรงกับ pipeline ที่รองรับ")
            parameters = dict(schema["pipeline_config"])
            parameters["augmentation"] = AugmentationConfig(**parameters.get("augmentation", {}))
            pipeline = TemporalFeaturePipeline(FeaturePipelineConfig(**parameters))
            if pipeline.config.target_length != sequence_length:
                raise ValueError("จำนวนเฟรมใน pipeline ไม่ตรงกับ manifest")
            model = TemporalClassifier.load(model_path, device="cpu")
            if (
                model.sequence_length != sequence_length
                or model.input_size != OUTPUT_FEATURE_COUNT
                or model.schema_version != FEATURE_SCHEMA_VERSION
            ):
                raise ValueError("รูปแบบข้อมูลของ TCN ไม่ตรงกับ manifest")
            names = np.asarray(model.classes_, dtype=str)
            encoder = None
        elif backend == "svc":
            if (
                manifest.get("feature_schema_version", "handvox.raw_landmarks.v1")
                != "handvox.raw_landmarks.v1"
                or int(manifest.get("feature_count", FEATURE_COUNT)) != FEATURE_COUNT
            ):
                raise ValueError("feature schema ของ SVC ต้องเป็น raw landmarks")
            with model_path.open("rb") as model_file:
                model = pickle.load(model_file)
            with _model_path(experiment_dir, "labels.pkl").open("rb") as labels_file:
                encoder = pickle.load(labels_file)
            names = np.asarray(encoder.inverse_transform(model.classes_), dtype=str)
            if int(model.n_features_in_) != sequence_length * FEATURE_COUNT:
                raise ValueError("จำนวน feature ของ SVC ไม่ตรงกับ manifest")
            pipeline = None
        else:
            raise ValueError(f"ไม่รองรับโมเดล {backend}")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, pickle.UnpicklingError) as error:
        raise DataFileError(f"โหลดโมเดลเพื่อวัดผลไม่สำเร็จ: {error}") from error
    expected = {item["name"] for item in manifest["visible_gestures"]}.union(manifest["internal_classes"])
    if len(names) != len(expected) or set(names.tolist()) != expected:
        raise DataFileError("คลาสของโมเดลไม่ตรงกับ manifest")
    return model, encoder, pipeline, names, model_path


def _external_metrics(actual, predicted, class_names):
    metrics = _metric_payload(actual, predicted, class_names, class_names)
    for field in ("precision", "recall", "f1"):
        metrics[f"macro_{field}"] = float(np.mean([row[field] for row in metrics["per_class"]]))
    return metrics


def evaluate_external(experiment_dir, store, output_root=None, *, include_pending=False):
    """วัดเฉพาะคลิป accepted ของผู้ทำท่าใหม่โดยไม่เทรนหรือติดตั้งโมเดล.

    แต่ละรอบสร้างโฟลเดอร์รายงานใหม่เสมอ ผลไม่มีค่า ``passed`` และไม่แก้
    metrics.json หรือสิทธิ์ติดตั้งของ experiment เดิม. include_pending ใช้วัด
    เบื้องต้นเท่านั้น โดยรักษาสถานะคุณภาพและแยกประเภทจากรายงานที่ผ่านตรวจ.
    """
    experiment_dir = Path(experiment_dir).resolve()
    if store.root.resolve().is_relative_to(DATASET_V2_DIR.resolve()):
        raise DataFileError("ข้อมูลวัดผู้ใช้ใหม่ต้องเก็บในโฟลเดอร์แยกจาก dataset_v2")
    manifest = _read_json(experiment_dir / "model_manifest.json")
    try:
        sequence_length = int(manifest["sequence_length"])
        visible_names = [item["name"] for item in manifest["visible_gestures"]]
        expected_names = visible_names + list(manifest["internal_classes"])
        if sequence_length < 1 or not expected_names or len(expected_names) != len(set(expected_names)):
            raise ValueError("จำนวนเฟรมหรือรายชื่อคลาสไม่ถูกต้อง")
    except (KeyError, TypeError, ValueError) as error:
        raise DataFileError(f"manifest สำหรับวัดผลไม่ถูกต้อง: {error}") from error
    training_signers, training_hashes = _training_provenance(experiment_dir)
    eligible_quality = {"accepted", "pending"} if include_pending else {"accepted"}
    records = sorted(
        (record for record in store.records() if record.quality in eligible_quality),
        key=lambda record: record.clip_id,
    )
    if not records:
        qualities = "accepted หรือ pending" if include_pending else "accepted"
        raise DataFileError(f"ยังไม่มีคลิป {qualities} ของผู้ทำท่าใหม่สำหรับวัดผล")
    accepted_count = sum(record.quality == "accepted" for record in records)
    pending_count = sum(record.quality == "pending" for record in records)
    if len({record.clip_id for record in records}) != len(records):
        raise DataFileError("พบ clip_id ซ้ำในชุดวัดผล")
    training_signer_keys = {signer.casefold() for signer in training_signers}
    overlapping = sorted({
        record.signer_id.strip() for record in records
        if record.signer_id.strip().casefold() in training_signer_keys
    })
    if overlapping:
        raise DataFileError("ชุดวัดผู้ใช้ใหม่มีผู้ที่ใช้เทรนแล้ว: " + ", ".join(overlapping))
    unknown_labels = sorted({record.gesture_name for record in records}.difference(expected_names))
    if unknown_labels:
        raise DataFileError("คลาสในชุดวัดผลไม่มีในโมเดล: " + ", ".join(unknown_labels))
    sequences = []
    sequence_hashes = []
    for record in records:
        try:
            if not record.sequence_file:
                raise ValueError("ไม่มี sequence_file")
            sequence = np.load(store.resolve_data_path(record.sequence_file), allow_pickle=False)
            if sequence.shape != (sequence_length, FEATURE_COUNT) or not np.isfinite(sequence).all():
                raise ValueError(f"ต้องเป็น ({sequence_length}, {FEATURE_COUNT}) และไม่มี NaN/Infinity")
            sequence = sequence.astype(np.float32)
            if not np.isfinite(sequence).all():
                raise ValueError("ข้อมูลเกินขอบเขต float32")
        except (OSError, ValueError, TypeError) as error:
            raise DataFileError(f"คลิป {record.clip_id} ใช้วัดผลไม่ได้: {error}") from error
        fingerprint = _sequence_hash(sequence)
        if fingerprint in training_hashes:
            raise DataFileError(f"คลิป {record.clip_id} มี sequence ซ้ำกับข้อมูลเทรน")
        if fingerprint in sequence_hashes:
            raise DataFileError(f"คลิป {record.clip_id} มี sequence ซ้ำในชุดวัดผล")
        sequences.append(sequence)
        sequence_hashes.append(fingerprint)
    model, encoder, pipeline, class_names, model_path = _load_predictor(
        experiment_dir, manifest, sequence_length
    )
    policy = _saved_policy(manifest)
    try:
        features = (
            np.asarray([pipeline.transform(sequence, training=False) for sequence in sequences], dtype=np.float32)
            if pipeline is not None
            else np.asarray(sequences, dtype=np.float32).reshape(len(sequences), -1)
        )
        if policy is None:
            raw_predictions = model.predict(features)
            predictions = np.asarray(
                encoder.inverse_transform(raw_predictions) if encoder is not None else raw_predictions,
                dtype=str,
            )
        else:
            probabilities = np.asarray(model.predict_proba(features), dtype=np.float64)
            if (
                probabilities.shape != (len(records), len(class_names))
                or not np.isfinite(probabilities).all()
                or np.any(probabilities < 0)
                or np.any(probabilities > 1)
                or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-5)
            ):
                raise ValueError("probability ของโมเดลไม่ถูกต้อง")
            predictions = _predictions_with_recognition_policy(probabilities, class_names, policy)
        if predictions.shape != (len(records),) or not set(predictions).issubset(class_names):
            raise ValueError("คำทำนายไม่ตรงกับจำนวนคลิปหรือคลาสในโมเดล")
    except (ValueError, TypeError, AttributeError, RuntimeError) as error:
        raise HandVoxError(f"ประเมินผู้ทำท่าใหม่ไม่สำเร็จ: {error}") from error
    actual = np.asarray([record.gesture_name for record in records], dtype=str)
    signers = np.asarray([record.signer_id.strip() for record in records], dtype=str)
    sessions = np.asarray([record.session_id for record in records], dtype=str)
    created_at = datetime.now().astimezone()
    evaluation_id = created_at.strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid4().hex[:8]
    aggregate = _external_metrics(actual, predictions, class_names.tolist())
    rows = [
        {
            **asdict(record),
            "sequence_sha256": sequence_hashes[index],
            "prediction": str(predictions[index]),
            "correct": bool(record.gesture_name == predictions[index]),
        }
        for index, record in enumerate(records)
    ]
    missing_classes = sorted(set(class_names).difference(actual))
    payload = {
        "schema_version": 1,
        "evaluation_id": evaluation_id,
        "experiment_id": manifest.get("experiment_id", experiment_dir.name),
        "created_at": created_at.isoformat(timespec="seconds"),
        "evaluation_scope": "external_new_signers_provisional" if pending_count else "external_new_signers",
        "evaluation_status": "provisional_pending_review" if pending_count else "quality_reviewed",
        "include_pending": include_pending,
        "affects_installation": False,
        "prediction_policy": "saved_recognition_policy" if policy is not None else "raw_model_predictions",
        "recognition_policy": manifest.get("recognition_policy"),
        "macro_average_scope": "all_model_classes",
        "source_experiment": str(experiment_dir),
        "model_backend": manifest.get("model_backend", "svc"),
        "model_artifact_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "training_sequences_sha256": hashlib.sha256((experiment_dir / "training_sequences.npz").read_bytes()).hexdigest(),
        "dataset_root": str(store.root.resolve()),
        "dataset_fingerprint_sha256": hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "training_signers": list(training_signers),
        "signers": sorted(set(signers.tolist())),
        "evaluated_clips": len(records),
        "accepted_clips": accepted_count,
        "pending_clips": pending_count,
        "classes": class_names.tolist(),
        "missing_classes": missing_classes,
        "coverage_complete": not missing_classes,
        "aggregate": aggregate,
        "per_signer": {
            signer: _external_metrics(actual[signers == signer], predictions[signers == signer], class_names.tolist())
            for signer in sorted(set(signers.tolist()))
        },
        "per_session": {
            session: {
                "evaluated_clips": int(np.sum(sessions == session)),
                **_external_metrics(actual[sessions == session], predictions[sessions == session], class_names.tolist()),
            }
            for session in sorted(set(sessions.tolist()))
        },
        "clips": rows,
    }
    report_root = Path(output_root) if output_root is not None else experiment_dir / "external_evaluations"
    report_dir = report_root / evaluation_id
    report_dir.mkdir(parents=True, exist_ok=False)
    (report_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (report_dir / "model_manifest.snapshot.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(report_dir / "predictions.csv", list(rows[0]), rows)
    _write_csv(report_dir / "per_class_metrics.csv", list(aggregate["per_class"][0]), aggregate["per_class"])
    _write_confusion_csv(report_dir / "confusion_matrix.csv", class_names.tolist(), aggregate["confusion_matrix"])
    lines = [
        "# ผลวัดโมเดลกับผู้ทำท่าใหม่" + (" (เบื้องต้น — ยังมีคลิปรอตรวจคุณภาพ)" if pending_count else ""),
        "",
        f"- โมเดล: {payload['experiment_id']}",
        f"- ผู้ทำท่าที่ใช้เทรน: {', '.join(training_signers)}",
        f"- ผู้ทำท่าที่ใช้วัดผล: {', '.join(payload['signers'])}",
        f"- คลิปที่ประเมิน: {len(records)}",
        f"- คลิป accepted: {accepted_count}",
        f"- คลิป pending: {pending_count}",
        f"- Accuracy: {aggregate['accuracy']:.2%}",
        f"- Macro F1: {aggregate['macro_f1']:.2%}",
        "- Macro F1 เฉลี่ยทุกคลาสของโมเดล โดยคลาสที่ไม่มีข้อมูลหรือทายไม่ได้มีค่า 0",
        f"- วิธีทำนาย: {payload['prediction_policy']}",
        "- รายงานนี้ใช้โมเดลที่บันทึกไว้โดยไม่มีการเทรนเพิ่ม และไม่เปลี่ยนผลอนุมัติติดตั้ง",
        "- เป็นการวัดระดับคลิป ยังไม่ใช่การทดสอบบทสนทนาต่อเนื่องจากกล้อง",
    ]
    if pending_count:
        lines.append("- ผลนี้ยังไม่ใช่ผลที่ผ่านการตรวจคุณภาพครบทุกคลิป และไม่มีการเปลี่ยน pending เป็น accepted")
    if missing_classes:
        lines.append("- ข้อมูลยังไม่ครบทุกคลาส ขาด: " + ", ".join(missing_classes))
    (report_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_dir, payload
