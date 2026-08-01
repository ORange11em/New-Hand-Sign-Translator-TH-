"""Train HandVox on short motion clips using a flattened sequence SVM."""

import pickle
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC

from gesture_config import GESTURE_NAMES
from sequence_dataset import CLIPS_PER_GESTURE, DATA_FILE, SEQUENCE_LENGTH, load_dataset


ROOT = Path(__file__).resolve().parent
MODEL_FILE = ROOT / "gesture_model.pkl"
LABEL_FILE = ROOT / "gesture_labels.pkl"


def main():
    clips, labels = load_dataset()
    if not len(clips):
        print("ยังไม่มีคลิปข้อมูล เปิด Add_New_Gesture.bat เพื่อเพิ่มท่าแรก")
        return 1

    known = set(labels)
    expected = set(GESTURE_NAMES)
    if known != expected:
        print("รายชื่อท่าในคลิปไม่ตรงกับการตั้งค่า")
        return 1
    if len(known) < 2:
        print("ต้องมีอย่างน้อย 2 ท่าจึงจะฝึกโมเดลจำแนกท่าได้")
        return 1

    counts = {name: int(np.sum(labels == name)) for name in sorted(known)}
    incomplete = [name for name, count in counts.items() if count < CLIPS_PER_GESTURE]
    if incomplete:
        print("คลิปข้อมูลยังไม่ครบ 30 คลิปต่อท่า:", ", ".join(incomplete))
        return 1

    encoder = LabelEncoder()
    target = encoder.fit_transform(labels)
    features = clips.reshape(len(clips), -1)
    train_x, test_x, train_y, test_y = train_test_split(
        features, target, test_size=0.2, random_state=42, stratify=target
    )
    classifier = SVC(kernel="rbf", C=10, gamma="scale", probability=True)
    classifier.fit(train_x, train_y)
    accuracy = float((classifier.predict(test_x) == test_y).mean())

    with MODEL_FILE.open("wb") as file:
        pickle.dump(classifier, file)
    with LABEL_FILE.open("wb") as file:
        pickle.dump(encoder, file)

    print("ฝึกโมเดลคลิปการเคลื่อนไหวเสร็จแล้ว")
    print("จำนวนคลิป:", len(clips), "| ความยาวคลิป:", SEQUENCE_LENGTH, "เฟรม")
    print("ตัวอย่างต่อท่า:", counts)
    print(f"ความแม่นยำทดสอบ: {accuracy * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
