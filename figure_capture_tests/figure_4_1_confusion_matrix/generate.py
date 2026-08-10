"""Generate figure 4.1 from the current 4-class dataset without saving a model."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATASET = ROOT / "gesture_sequences.npz"
OUTPUT = HERE / "output"


def configure_thai_font() -> str:
    candidates = (
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts/THSarabunNew.ttf",
        Path("C:/Windows/Fonts/THSarabunNew.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
    )
    for path in candidates:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            family = font_manager.FontProperties(fname=str(path)).get_name()
            plt.rcParams["font.family"] = family
            plt.rcParams["font.size"] = 16
            return family
    return "sans-serif"


def main() -> int:
    if not DATASET.exists():
        raise FileNotFoundError(f"ไม่พบ Dataset: {DATASET}")
    with np.load(DATASET, allow_pickle=False) as data:
        clips = data["clips"].astype(np.float32)
        labels = data["labels"].astype(str)
    classes, counts = np.unique(labels, return_counts=True)
    if len(classes) != 4:
        raise ValueError(f"รายงานปัจจุบันต้องมี 4 คลาส แต่ Dataset มี {len(classes)} คลาส")
    if np.any(counts < 30):
        raise ValueError(f"แต่ละคลาสต้องมีอย่างน้อย 30 คลิป: {dict(zip(classes, counts))}")

    encoder = LabelEncoder()
    target = encoder.fit_transform(labels)
    features = clips.reshape(len(clips), -1)
    train_x, test_x, train_y, test_y = train_test_split(
        features, target, test_size=0.2, random_state=42, stratify=target
    )
    model = SVC(kernel="rbf", C=10, gamma="scale", probability=True)
    model.fit(train_x, train_y)
    prediction = model.predict(test_x)
    matrix = confusion_matrix(test_y, prediction, labels=np.arange(len(classes)))
    accuracy = accuracy_score(test_y, prediction)

    configure_thai_font()
    figure, axis = plt.subplots(figsize=(9.5, 7.5), dpi=160)
    display = ConfusionMatrixDisplay(matrix, display_labels=encoder.classes_)
    display.plot(ax=axis, cmap="Blues", colorbar=False, values_format="d")
    axis.set_title(f"Confusion Matrix ของ HandVox (Accuracy {accuracy * 100:.2f}%)",
                   fontsize=22, pad=18)
    axis.set_xlabel("ค่าที่แบบจำลองทำนาย", fontsize=18)
    axis.set_ylabel("ค่าจริง", fontsize=18)
    figure.tight_layout()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image_path = OUTPUT / "figure_4_1_confusion_matrix_4_classes.png"
    figure.savefig(image_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    report = {
        "dataset": str(DATASET),
        "shape": list(clips.shape),
        "classes": encoder.classes_.tolist(),
        "counts": {name: int(count) for name, count in zip(classes, counts)},
        "split": "80:20 stratified, random_state=42",
        "test_samples": int(len(test_y)),
        "accuracy": float(accuracy),
        "confusion_matrix": matrix.tolist(),
        "model_written": False,
    }
    json_path = OUTPUT / "figure_4_1_metrics.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(image_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

