"""อ่าน Dataset/โมเดลเดิมและสร้างสรุปผลที่ทำซ้ำได้ โดยไม่แก้ไฟล์ต้นฉบับ."""

from __future__ import annotations

import json
import pickle
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with np.load(ROOT / "gesture_sequences.npz", allow_pickle=False) as data:
        clips = data["clips"].astype(np.float32)
        labels = data["labels"].astype(str)

    with (ROOT / "gesture_model.pkl").open("rb") as file:
        stored_model = pickle.load(file)
    with (ROOT / "gesture_labels.pkl").open("rb") as file:
        stored_encoder = pickle.load(file)

    encoder = LabelEncoder()
    target = encoder.fit_transform(labels)
    features = clips.reshape(len(clips), -1)
    train_x, test_x, train_y, test_y = train_test_split(
        features,
        target,
        test_size=0.2,
        random_state=42,
        stratify=target,
    )

    prediction = stored_model.predict(test_x)
    report = classification_report(
        test_y,
        prediction,
        labels=np.arange(len(encoder.classes_)),
        target_names=encoder.classes_,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(
        test_y,
        prediction,
        labels=np.arange(len(encoder.classes_)),
    )

    fresh_model = SVC(kernel="rbf", C=10, gamma="scale", probability=True)
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(fresh_model, features, target, cv=folds, scoring="accuracy")

    byte_rows = np.ascontiguousarray(features).view(
        np.dtype((np.void, features.dtype.itemsize * features.shape[1]))
    ).ravel()
    unique_rows = len(np.unique(byte_rows))

    per_class = {}
    for name in encoder.classes_:
        metrics = report[name]
        per_class[name] = {
            "clips": int(np.sum(labels == name)),
            "test_support": int(metrics["support"]),
            "precision": float(metrics["precision"]),
            "recall": float(metrics["recall"]),
            "f1_score": float(metrics["f1-score"]),
        }

    summary = {
        "dataset": {
            "shape": list(clips.shape),
            "dtype": str(clips.dtype),
            "classes": encoder.classes_.tolist(),
            "counts": dict(sorted(Counter(labels).items())),
            "finite": bool(np.isfinite(clips).all()),
            "unique_clips": unique_rows,
            "exact_duplicate_clips": int(len(clips) - unique_rows),
            "zero_fraction": float(np.mean(clips == 0)),
        },
        "stored_artifacts": {
            "encoder_classes": stored_encoder.classes_.tolist(),
            "model_feature_count": int(stored_model.n_features_in_),
            "model_class_count": int(len(stored_model.classes_)),
        },
        "holdout": {
            "split": "80:20 stratified, random_state=42",
            "train_clips": int(len(train_x)),
            "test_clips": int(len(test_x)),
            "correct": int(np.sum(prediction == test_y)),
            "incorrect": int(np.sum(prediction != test_y)),
            "accuracy": float(np.mean(prediction == test_y)),
            "macro_precision": float(report["macro avg"]["precision"]),
            "macro_recall": float(report["macro avg"]["recall"]),
            "macro_f1": float(report["macro avg"]["f1-score"]),
            "per_class": per_class,
            "confusion_matrix_labels": encoder.classes_.tolist(),
            "confusion_matrix": matrix.tolist(),
        },
        "cross_validation": {
            "method": "StratifiedKFold(n_splits=5, shuffle=True, random_state=42)",
            "scores": cv_scores.tolist(),
            "mean_accuracy": float(cv_scores.mean()),
            "sample_std": float(cv_scores.std(ddof=1)),
        },
        "interpretation_limit": (
            "All metrics use random clip-level splits of the same dataset; they do not "
            "establish signer-independent or session-independent performance."
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
