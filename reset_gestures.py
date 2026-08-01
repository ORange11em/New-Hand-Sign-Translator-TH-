"""Archive all active gestures and start an empty upper-body dataset."""

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from sequence_dataset import DATA_FILE, empty_dataset, save_dataset


ROOT = Path(__file__).resolve().parent
ACTIVE_FILES = (
    "gesture_data.csv",
    "gesture_sequences.npz",
    "gesture_model.pkl",
    "gesture_labels.pkl",
    "training_results.png",
    "custom_gestures.json",
)


def main():
    parser = argparse.ArgumentParser(description="Reset all active HandVox gestures")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        print("Run with --confirm to reset active gestures.")
        return 1

    backup_dir = ROOT / "gesture_backups" / (
        "reset_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    for filename in ACTIVE_FILES:
        source = ROOT / filename
        if source.exists():
            shutil.move(source, backup_dir / filename)

    clips, labels = empty_dataset()
    save_dataset(clips, labels)
    (ROOT / "custom_gestures.json").write_text("[]\n", encoding="utf-8")

    print("All active gestures have been reset.")
    print(f"Backup: {backup_dir}")
    print("Open Add_New_Gesture.bat to add the first gesture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
