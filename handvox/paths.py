"""รวมตำแหน่งไฟล์สำคัญไว้จุดเดียว เพื่อไม่ให้แต่ละโมดูลสร้าง path ต่างกัน."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = ROOT / "settings.json"
HISTORY_FILE = ROOT / "conversation_history.json"
PLANNED_GESTURES_FILE = ROOT / "planned_gestures.json"
CUSTOM_GESTURES_FILE = ROOT / "custom_gestures.json"
MODEL_FILE = ROOT / "gesture_model.pkl"
TEMPORAL_MODEL_FILE = ROOT / "gesture_model.pt"
LABEL_FILE = ROOT / "gesture_labels.pkl"
LEGACY_DATA_FILE = ROOT / "gesture_sequences.npz"
DATASET_V2_DIR = ROOT / "dataset_v2"
TRAINING_CONFIG_FILE = ROOT / "training_config.json"
EXPERIMENTS_DIR = ROOT / "experiments"
MODEL_MANIFEST_FILE = ROOT / "model_manifest.json"
LOG_FILE = ROOT / "handvox.log"
