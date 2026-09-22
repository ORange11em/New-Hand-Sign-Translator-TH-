"""เปิดกล้อง ตรวจจับท่าจากโมเดล และสะสมคำเป็นประโยคแบบเรียลไทม์.

ลำดับหลักคือ อ่านภาพจากกล้อง -> ดึง landmark -> สะสมลำดับการเคลื่อนไหว
-> ให้โมเดลทำนาย -> ยืนยันผลด้วย state machine -> เพิ่มคำ/อ่านเสียง/บันทึกประโยค
หน้าต่างนี้รองรับทั้งปุ่มบนภาพและคีย์ลัด โดยไม่แก้ไขหรือเทรนโมเดล
"""

# ============================================================
# STEP 3 : run_detector.py  (+ TTS เสียง + Sentence Builder จากกล้อง)
# วิธีใช้ : python run_detector.py
#
# 📝 ค้างท่าที่ผ่านการยืนยัน 1.0 วิ → เพิ่มคำลงประโยคอัตโนมัติ
# 🔊 เปิด/ปิดการอ่านคำอัตโนมัติได้จากหน้าตั้งค่า
#
# คีย์ลัด:
#   SPACE      → เพิ่มคำปัจจุบันลงประโยค
#   BACKSPACE  → ลบคำล่าสุดออกจากประโยค
#   ENTER      → ล้างประโยคทั้งหมด
#   S          → อ่านประโยคออกเสียง (TTS)
#   B          → บันทึกประโยคลงประวัติ
#   ESC        → ออก
# ============================================================
import os
import json
import pickle
import time
from collections import deque

from handvox.temporal_model import TemporalClassifier

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from body_features import FEATURE_COUNT, extract_features, upper_body_bbox
from gesture_config import GESTURE_COLORS, GESTURE_NAMES
from gesture_state import DetectionPhase, GestureStateMachine
from handvox.camera_sentence import GestureHoldTimer
from handvox.feature_pipeline import (
    FEATURE_SCHEMA_VERSION,
    OUTPUT_FEATURE_COUNT,
)
from handvox.history import HistoryStore
from handvox.paths import (
    LABEL_FILE,
    MODEL_FILE,
    MODEL_MANIFEST_FILE,
    TEMPORAL_MODEL_FILE,
)
from handvox.sentence import SentenceBuilder
from handvox.settings import SettingsStore
from handvox.training_workflow import temporal_pipeline_from_manifest
from sequence_dataset import SEQUENCE_LENGTH as LEGACY_SEQUENCE_LENGTH
from tts_service import SpeechService


settings_store = SettingsStore()
settings = settings_store.load_or_default()
if settings_store.last_error:
    print(f"⚠️ settings.json ไม่ถูกต้อง จึงใช้ค่าเริ่มต้น: {settings_store.last_error}")

# ── ฟอนต์ไทย ──────────────────────────────────────────────
def load_font(size):
    """โหลดฟอนต์ภาษาไทยที่มีใน Windows หรือ fallback เป็นฟอนต์เริ่มต้น."""
    for fp in ["C:/Windows/Fonts/THSarabunNew.ttf",
               "C:/Windows/Fonts/tahoma.ttf",
               "C:/Windows/Fonts/arial.ttf"]:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()

fL = load_font(round(48 * settings.font_scale))
fM = load_font(round(30 * settings.font_scale))
fS = load_font(round(20 * settings.font_scale))
fXL = load_font(round(58 * settings.font_scale))

def putThai(img, text, pos, font, color=(255,255,255)):
    """วาดข้อความไทยที่พิกัดซ้ายบนบนภาพ BGR."""
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d   = ImageDraw.Draw(pil)
    d.text(pos, text, font=font, fill=(color[2],color[1],color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

def putThaiC(img, text, cx, y, font, color=(255,255,255)):
    """วาดข้อความไทยโดยจัดกึ่งกลางรอบพิกัด cx."""
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d   = ImageDraw.Draw(pil)
    bb  = d.textbbox((0,0), text, font=font)
    d.text((cx-(bb[2]-bb[0])//2, y), text, font=font,
           fill=(color[2],color[1],color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

def text_size(text, font):
    """วัดความกว้าง/สูงของข้อความเพื่อจัดตำแหน่งองค์ประกอบ UI."""
    pil = Image.new("RGB",(1,1))
    bb  = ImageDraw.Draw(pil).textbbox((0,0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

# ── โหลด manifest และ Model ──────────────────────────────
manifest = {}
if MODEL_MANIFEST_FILE.exists():
    try:
        manifest = json.loads(MODEL_MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        print("⚠️ อ่าน model_manifest.json ไม่ได้ จึงลองใช้โมเดล SVC เดิม")
        manifest = {}

internal_labels = {str(name) for name in manifest.get("internal_classes", [])}
experimental_deployment = manifest.get("deployment", {}).get("status") == "experimental_unvalidated"
if experimental_deployment:
    print("คำเตือน: โมเดลทดลอง ผลยังไม่ผ่านเกณฑ์ โปรดตรวจคำก่อนใช้")
saved_recognition_policy = manifest.get("recognition_policy", {})
if not isinstance(saved_recognition_policy, dict):
    saved_recognition_policy = {}
try:
    model_min_confidence = float(saved_recognition_policy.get("minimum_confidence", 0.0))
    model_min_margin = float(
        saved_recognition_policy.get("minimum_probability_margin", 0.0)
    )
except (TypeError, ValueError):
    model_min_confidence = 0.0
    model_min_margin = 0.0
model_min_confidence = min(1.0, max(0.0, model_min_confidence))
model_min_margin = min(1.0, max(0.0, model_min_margin))
requested_backend = str(
    manifest.get("model_backend", manifest.get("backend", "legacy_svc"))
).strip().lower()
model_backend = ""
model = None
temporal_pipeline = None
MODEL_SEQUENCE_LENGTH = LEGACY_SEQUENCE_LENGTH
model_device = "cpu"
model_device_name = "CPU"
model_device_fallback = ""
temporal_load_error = ""

if requested_backend == "temporal_tcn":
    try:
        if not TEMPORAL_MODEL_FILE.exists():
            raise FileNotFoundError(f"ไม่พบ {TEMPORAL_MODEL_FILE.name}")
        manifest_schema = str(
            manifest.get("feature_schema_version", FEATURE_SCHEMA_VERSION)
        )
        if manifest_schema != FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"feature schema ใน manifest เป็น {manifest_schema} "
                f"แต่ตัวตรวจจับรองรับ {FEATURE_SCHEMA_VERSION}"
            )
        manifest_feature_count = int(
            manifest.get("feature_count", OUTPUT_FEATURE_COUNT)
        )
        if manifest_feature_count != OUTPUT_FEATURE_COUNT:
            raise ValueError(
                f"feature count ใน manifest เป็น {manifest_feature_count} "
                f"แต่ตัวตรวจจับสร้าง {OUTPUT_FEATURE_COUNT}"
            )

        preferred_device = "auto" if settings.prefer_gpu else "cpu"
        model = TemporalClassifier.load(
            TEMPORAL_MODEL_FILE, device=preferred_device
        )
        if int(model.input_size) != OUTPUT_FEATURE_COUNT:
            raise ValueError(
                f"โมเดล TCN ต้องการ {model.input_size} features "
                f"แต่ pipeline สร้าง {OUTPUT_FEATURE_COUNT}"
            )
        if str(model.schema_version) != FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"artifact ใช้ feature schema {model.schema_version} "
                f"แต่ตัวตรวจจับรองรับ {FEATURE_SCHEMA_VERSION}"
            )
        MODEL_SEQUENCE_LENGTH = int(model.sequence_length)
        manifest_length = int(
            manifest.get("sequence_length", MODEL_SEQUENCE_LENGTH)
        )
        if manifest_length != MODEL_SEQUENCE_LENGTH:
            raise ValueError("sequence length ใน manifest ไม่ตรงกับ artifact")
        temporal_pipeline = temporal_pipeline_from_manifest(manifest)
        NAMES = [str(name) for name in model.classes_]
        expected_temporal_classes = set(GESTURE_NAMES).union(internal_labels)
        if set(NAMES) != expected_temporal_classes:
            raise ValueError(
                "รายชื่อคลาสใน TCN ไม่ตรงกับคำที่ใช้งานและคลาสภายใน"
            )
        model_backend = "temporal_tcn"
        model_device = str(model.device_used_)
        selection = model.device_selection_
        model_device_name = selection.device_name or model_device.upper()
        model_device_fallback = selection.fallback_reason
    except (OSError, RuntimeError, TypeError, ValueError, AttributeError) as error:
        temporal_load_error = str(error)
        model = None
        temporal_pipeline = None
        print(f"⚠️ เปิดโมเดล TCN ไม่ได้: {error}")
        print("   กำลังลองใช้โมเดล SVC เดิมแทน")

if model is None:
    missing_legacy = [
        path.name for path in (MODEL_FILE, LABEL_FILE) if not path.exists()
    ]
    if missing_legacy:
        print("❌ ไม่พบโมเดลที่พร้อมใช้งาน: " + ", ".join(missing_legacy))
        if temporal_load_error:
            print(f"   TCN ใช้ไม่ได้เพราะ: {temporal_load_error}")
        print("   กรุณาเทรนและติดตั้งโมเดลจากหน้าเตรียมเทรนก่อน")
        raise SystemExit(1)
    try:
        with MODEL_FILE.open("rb") as file:
            model = pickle.load(file)
        with LABEL_FILE.open("rb") as file:
            le = pickle.load(file)
        NAMES = [str(name) for name in le.classes_]
    except (OSError, EOFError, AttributeError, pickle.UnpicklingError) as error:
        print(f"❌ โหลดโมเดล SVC เดิมไม่ได้: {error}")
        raise SystemExit(1) from error
    expected_legacy_features = FEATURE_COUNT * LEGACY_SEQUENCE_LENGTH
    if getattr(model, "n_features_in_", expected_legacy_features) != expected_legacy_features:
        print("❌ โมเดล SVC ไม่ใช่ motion-clip model ที่ตัวตรวจจับรองรับ")
        raise SystemExit(1)
    if not getattr(model, "probability", False) or not callable(
        getattr(model, "predict_proba", None)
    ):
        print("❌ โมเดล SVC ต้องเทรนด้วย probability=true ก่อนใช้งานหน้ากล้อง")
        raise SystemExit(1)
    model_backend = "legacy_svc"
    MODEL_SEQUENCE_LENGTH = LEGACY_SEQUENCE_LENGTH
    model_device = "cpu"
    model_device_name = "CPU"
    if requested_backend == "temporal_tcn":
        # manifest เป็นของ TCN ที่เปิดไม่ได้ จึงอนุมานคลาสภายในจาก SVC สำรอง
        # แทนการบังคับใช้ internal_classes ของ artifact คนละไฟล์
        internal_labels = set(NAMES).difference(GESTURE_NAMES)
        model_min_confidence = 0.0
        model_min_margin = 0.0

if set(NAMES) != set(GESTURE_NAMES).union(internal_labels):
    print("❌ รายชื่อท่าในโมเดลไม่ตรงกับ gesture_config.py")
    print("   โปรดรัน python train_model.py เพื่อสร้างโมเดลใหม่")
    raise SystemExit(1)
print(f"✅ โหลด {model_backend} | ท่า: {NAMES}")
if model_device_fallback:
    print(f"⚠️ {model_device_fallback}")
print(f"⚙️ อุปกรณ์ประมวลผลโมเดล: {model_device_name} ({model_device})")
if model_backend == "temporal_tcn" and model_device.startswith("cuda"):
    device_badge_text = "GPU · TCN"
    device_badge_color = (45, 190, 80)
elif model_backend == "temporal_tcn":
    device_badge_text = "CPU · TCN"
    if settings.prefer_gpu:
        device_badge_text += " · GPU ไม่พร้อม"
    device_badge_color = (0, 155, 230)
else:
    device_badge_text = (
        "CPU · SVC สำรอง" if temporal_load_error else "CPU · SVC เดิม"
    )
    device_badge_color = (110, 110, 110)

# ── MediaPipe ─────────────────────────────────────────────
mp_h = mp.solutions.holistic
det = mp_h.Holistic(static_image_mode=False, model_complexity=1,
                    smooth_landmarks=True,
                    min_detection_confidence=0.7,
                    min_tracking_confidence=0.7)

def color(n):
    """คืนสีประจำท่า หรือใช้สีเขียวเริ่มต้นเมื่อไม่มีการกำหนด."""
    return GESTURE_COLORS.get(n, (0, 255, 160))

def corner_box(img, x1,y1,x2,y2, c, t=3, L=30):
    """วาดเฉพาะมุมกรอบ เพื่อไม่ให้เส้นทับภาพผู้ใช้มากเกินไป."""
    for pts in [[(x1,y1+L),(x1,y1),(x1+L,y1)],
                [(x2-L,y1),(x2,y1),(x2,y1+L)],
                [(x1,y2-L),(x1,y2),(x1+L,y2)],
                [(x2-L,y2),(x2,y2),(x2,y2-L)]]:
        cv2.polylines(img,[np.array(pts)],False,c,t,cv2.LINE_AA)

# ── State ─────────────────────────────────────────────────
MIN_CONFIDENCE = max(settings.min_confidence, model_min_confidence)
MIN_PROBABILITY_MARGIN = max(settings.min_probability_margin, model_min_margin)
CONFIRM_FRAMES = settings.confirm_frames
RELEASE_SECONDS = settings.release_seconds

motion_frames = deque(maxlen=MODEL_SEQUENCE_LENGTH)
recognizer = GestureStateMachine(
    min_confidence=MIN_CONFIDENCE,
    confirm_frames=CONFIRM_FRAMES,
    release_seconds=RELEASE_SECONDS,
    min_probability_margin=MIN_PROBABILITY_MARGIN,
    neutral_release_frames=settings.neutral_release_frames,
)
confirmed = ""
conf_val = 0.0

# ── Auto-add state ─────────────────────────────────────────
# ค้างท่าที่ผ่านการยืนยันครบ HOLD_SEC วิ แล้วเพิ่มเพียงหนึ่งครั้ง
# หลังเพิ่มจะเข้า cooldown จนกว่าจะปล่อยมือหรือเปลี่ยนท่า
HOLD_SEC = settings.speak_hold_seconds
hold_timer = GestureHoldTimer(HOLD_SEC)

speech = SpeechService(volume=settings.tts_volume)
if speech.available:
    print(f"✅ TTS พร้อมใช้งาน ({speech.engine_name})")
else:
    print("⚠️  TTS ใช้งานไม่ได้")

# ── Sentence Builder ───────────────────────────────────────
sentence = SentenceBuilder(
    prevent_duplicates=settings.prevent_duplicate_words
)
history = HistoryStore()
add_cooldown = 0.0
COOLDOWN_SEC = 1.0
WINDOW_TITLE = "Hand Sign Translator — TH"
sentence_action_regions = {}
sentence_actions = deque()

cap = cv2.VideoCapture(settings.camera_index)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
if not cap.isOpened():
    speech.close()
    det.close()
    print("❌ เปิดกล้องไม่ได้")
    raise SystemExit(1)
prev = time.monotonic()


def queue_sentence_action(event, x, y, _flags, _param):
    """แปลงตำแหน่งคลิกบนหน้ากล้องเป็น action ให้ลูปหลักทำต่อ."""
    if event != cv2.EVENT_LBUTTONUP:
        return
    for action, (x1, y1, x2, y2) in sentence_action_regions.items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            sentence_actions.append(action)
            break


cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
cv2.setMouseCallback(WINDOW_TITLE, queue_sentence_action)

# ── helper: Sentence Bar ───────────────────────────────────
def draw_sentence_bar(frm, W, H, sentence):
    """วาดประโยค ปุ่มควบคุม และชื่อคีย์ลัดที่ด้านล่างของภาพ."""
    BAR_H = 146
    bar_y = H - BAR_H - 32
    ov = frm.copy()
    cv2.rectangle(ov, (0, bar_y), (W, bar_y+BAR_H), (15,15,15), -1)
    cv2.addWeighted(ov, .85, frm, .15, 0, frm)
    cv2.line(frm, (0, bar_y), (W, bar_y), (60,60,60), 1)
    frm = putThai(frm, "ประโยคปัจจุบัน", (16, bar_y+7), fS, (150,150,150))
    frm = putThai(frm, f"{len(sentence)} คำ", (W-74, bar_y+7), fS, (150,150,150))

    sentence_text = sentence.text or "ยังไม่มีคำ — แสดงท่าค้างไว้เพื่อเริ่มสร้างประโยค"
    while text_size(sentence_text, fM)[0] > W - 34 and len(sentence_text) > 4:
        sentence_text = "…" + sentence_text[2:]
    sentence_color = (245,245,245) if sentence.text else (125,125,125)
    frm = putThai(frm, sentence_text, (16, bar_y+34), fM, sentence_color)

    actions = (
        ("add", "เพิ่มคำ", "SPACE", (235,99,37)),
        ("remove", "ลบคำล่าสุด", "BACKSPACE", (75,75,75)),
        ("speak", "อ่านประโยค", "S", (61,128,21)),
        ("save", "บันทึก", "B", (61,128,21)),
        ("clear", "ล้าง", "ENTER", (28,28,185)),
    )
    gap = 8
    margin = 14
    button_y1 = bar_y + 83
    button_y2 = bar_y + 136
    button_w = max(70, (W - margin*2 - gap*(len(actions)-1)) // len(actions))
    sentence_action_regions.clear()
    for index, (action, label, shortcut, fill) in enumerate(actions):
        x1 = margin + index * (button_w + gap)
        x2 = W - margin if index == len(actions)-1 else x1 + button_w
        sentence_action_regions[action] = (x1, button_y1, x2, button_y2)
        cv2.rectangle(frm, (x1, button_y1), (x2, button_y2), fill, -1)
        cv2.rectangle(frm, (x1, button_y1), (x2, button_y2), (125,125,125), 1)
        label_w, _ = text_size(label, fS)
        frm = putThai(frm, label, (x1 + max(6, (x2-x1-label_w)//2), button_y1+3), fS)
        shortcut_scale = 0.34
        shortcut_size = cv2.getTextSize(
            shortcut, cv2.FONT_HERSHEY_SIMPLEX, shortcut_scale, 1
        )[0]
        shortcut_x = x1 + max(5, (x2-x1-shortcut_size[0])//2)
        cv2.putText(
            frm,
            shortcut,
            (shortcut_x, button_y2-7),
            cv2.FONT_HERSHEY_SIMPLEX,
            shortcut_scale,
            (225,225,225),
            1,
            cv2.LINE_AA,
        )
    return frm

# ── helper: Hold Progress Bar ──────────────────────────────
def draw_hold_bar(frm, W, H, hold_pct, action_label):
    """วาดความคืบหน้าการค้างท่าก่อนเพิ่มหรืออ่านคำอัตโนมัติ."""
    bar_y = H - 32 - 146 - 16
    bar_w = int((W - 40) * min(hold_pct, 1.0))
    cv2.rectangle(frm, (20, bar_y), (W-20, bar_y+10), (25,25,25), -1)
    col = (0, 255, 80) if hold_pct >= 1.0 else (0, 200, 255)
    cv2.rectangle(frm, (20, bar_y), (20+bar_w, bar_y+10), col, -1)
    label = f"ค้างท่าไว้เพื่อ{action_label}..." if hold_pct < 1.0 else f"{action_label}แล้ว"
    frm = putThai(frm, f"{label}  {hold_pct*100:.0f}%",
                  (25, bar_y-22), fS, col)
    return frm


def draw_detection_status(frm, x1, y1, x2, text, status_color, progress=None):
    """วาดข้อความสถานะสั้น ๆ และ progress การยืนยันเหนือกรอบผู้ใช้."""
    width = frm.shape[1]
    panel_x1 = max(8, x1)
    panel_x2 = min(width - 8, max(panel_x1 + 250, x2))
    panel_y1 = max(58, y1 - (54 if progress is not None else 38))
    panel_y2 = panel_y1 + (48 if progress is not None else 34)
    overlay = frm.copy()
    cv2.rectangle(
        overlay, (panel_x1, panel_y1), (panel_x2, panel_y2), (18, 18, 18), -1
    )
    cv2.addWeighted(overlay, 0.82, frm, 0.18, 0, frm)
    cv2.rectangle(
        frm, (panel_x1, panel_y1), (panel_x2, panel_y2), status_color, 1
    )

    available_width = panel_x2 - panel_x1 - 16
    display_text = text
    while text_size(display_text, fS)[0] > available_width and len(display_text) > 4:
        display_text = display_text[:-2] + "…"
    frm = putThai(
        frm, display_text, (panel_x1 + 8, panel_y1 + 3), fS, status_color
    )
    if progress is not None:
        progress = min(1.0, max(0.0, float(progress)))
        track_x1 = panel_x1 + 8
        track_x2 = panel_x2 - 8
        track_y1 = panel_y2 - 10
        cv2.rectangle(frm, (track_x1, track_y1), (track_x2, track_y1 + 5), (55, 55, 55), -1)
        fill_x = track_x1 + round((track_x2 - track_x1) * progress)
        cv2.rectangle(frm, (track_x1, track_y1), (fill_x, track_y1 + 5), status_color, -1)
    return frm


def draw_badge(frm, text, x, y, badge_color):
    """วาด badge มีพื้นหลังให้อ่านได้แม้ฉากกล้องสว่าง."""
    text_width, text_height = text_size(text, fS)
    x2 = x + text_width + 16
    y2 = y + max(28, text_height + 8)
    overlay = frm.copy()
    cv2.rectangle(overlay, (x, y), (x2, y2), (18, 18, 18), -1)
    cv2.addWeighted(overlay, 0.82, frm, 0.18, 0, frm)
    cv2.rectangle(frm, (x, y), (x2, y2), badge_color, 1)
    return putThai(frm, text, (x + 8, y + 2), fS, badge_color)

print("\n🎥 กล้องเปิดแล้ว | ESC ออก")
if settings.auto_add_words:
    print(f"📝 แสดงท่าค้างไว้ {HOLD_SEC:.1f} วิ → เพิ่มคำลงประโยคอัตโนมัติ")
else:
    print("📝 การเพิ่มคำอัตโนมัติปิดอยู่ — กด Space หรือปุ่ม 'เพิ่มคำ'")
print("   ใช้ปุ่มบนหน้ากล้องเพื่อลบ อ่าน บันทึก หรือล้างประโยค\n")


def save_sentence(source="detector-manual"):
    """บันทึกประโยคปัจจุบันลงประวัติพร้อมระบุแหล่งที่มา."""
    if not sentence:
        print("⚠️ ประโยคว่างอยู่")
        return False
    try:
        history.add(sentence.text, source=source, limit=settings.history_limit)
        print(f"💾 บันทึกประโยค: {sentence.text}")
        return True
    except Exception as error:
        print(f"⚠️ บันทึกประวัติไม่ได้: {error}")
        return False


def speak_sentence():
    """ส่งประโยคเข้าคิวเสียง และบันทึกประวัติเมื่อเปิดการตั้งค่าไว้."""
    if not sentence:
        print("⚠️ ประโยคว่างอยู่")
        return False
    full = sentence.text
    print(f"🔊 อ่าน: {full}")
    if not speech.speak(full):
        print("⚠️ ยังส่งข้อความเข้าคิวเสียงไม่ได้")
        return False
    if settings.save_spoken_sentences:
        save_sentence(source="detector-tts")
    return True


def add_confirmed_word(label, now):
    """เพิ่มคำยืนยันด้วยตนเองแล้วเข้าสู่ cooldown เพื่อกันคลิกซ้ำ."""
    global add_cooldown, detection_phase
    if not label or not recognizer.speech_armed:
        print("⚠️ ยังไม่มีคำใหม่ที่ยืนยันแล้ว หรือยังไม่ได้ปล่อยท่าก่อนหน้า")
        return False
    if now - add_cooldown <= COOLDOWN_SEC:
        return False
    added = sentence.add(label)
    add_cooldown = now
    recognizer.mark_emitted(label)
    detection_phase = recognizer.phase
    hold_timer.reset()
    if added:
        print(f"📝 เพิ่ม: {label}  |  ประโยค: {sentence.text}")
    else:
        print("⚠️ ไม่เพิ่มคำเดิมซ้ำติดกัน")
    return added


def perform_sentence_action(action, label, now):
    """รวมการทำงาน add/remove/clear/speak/save ของปุ่มและคีย์บอร์ด."""
    if action == "add":
        add_confirmed_word(label, now)
    elif action == "remove":
        removed = sentence.remove_last()
        if removed:
            print(f"🗑️ ลบ: {removed}  |  ประโยค: {sentence.text or '-'}")
    elif action == "clear":
        sentence.clear()
        print("🔄 ล้างประโยคแล้ว")
    elif action == "speak":
        speak_sentence()
    elif action == "save":
        save_sentence()

while True:
    ok, frm = cap.read()
    if not ok: break
    frm = cv2.flip(frm, 1)
    H, W = frm.shape[:2]
    res  = det.process(cv2.cvtColor(frm, cv2.COLOR_BGR2RGB))
    now  = time.monotonic()

    cur   = ""
    cur_c = 0.0
    raw_label = ""
    probability_margin = 0.0
    neutral_detected = False
    unknown_detected = False
    rejected_by_recognition_policy = False
    prediction_ready = False
    bbox  = None

    feats = extract_features(res)
    if feats is not None:
        bbox = upper_body_bbox(res, W, H)
        motion_frames.append(feats)
        if len(motion_frames) == MODEL_SEQUENCE_LENGTH:
            raw_sequence = np.asarray(motion_frames, dtype=np.float32)
            if model_backend == "temporal_tcn":
                # inference ห้าม augmentation และต้องใช้ schema เดียวกับตอนเทรน
                sequence = temporal_pipeline.transform(
                    raw_sequence, training=False
                )[None, :, :]
            else:
                sequence = raw_sequence.reshape(1, -1)
            proba = model.predict_proba(sequence)[0]
            ti = int(np.argmax(proba))
            raw_label = NAMES[ti]
            cur_c = float(proba[ti])
            second_best = (
                float(np.partition(proba, -2)[-2]) if len(proba) > 1 else 0.0
            )
            probability_margin = max(0.0, cur_c - second_best)
            prediction_ready = True
            neutral_detected = raw_label == "neutral"
            rejected_by_recognition_policy = (
                raw_label not in internal_labels
                and (
                    cur_c < MIN_CONFIDENCE
                    or probability_margin < MIN_PROBABILITY_MARGIN
                )
            )
            unknown_detected = (
                raw_label == "unknown"
                or raw_label in internal_labels and not neutral_detected
                or rejected_by_recognition_policy
            )
            # คลาสภายในช่วยปฏิเสธ false activation แต่ห้ามเข้า SentenceBuilder
            cur = "" if raw_label in internal_labels or rejected_by_recognition_policy else raw_label

    decision = recognizer.update(
        cur,
        cur_c,
        landmarks_visible=feats is not None,
        now=now,
        probability_margin=probability_margin,
        neutral_detected=neutral_detected,
        unknown_detected=unknown_detected,
    )
    confirmed = decision.label
    conf_val = decision.confidence
    detection_phase = decision.phase
    if decision.released:
        # อย่าให้เฟรมจากท่าเก่าปะปนกับการยกมือรอบใหม่
        motion_frames.clear()

    # ── Auto-add: จับเวลาค้างท่า ────────────────────────────
    # ใช้ผลที่ผ่าน threshold และยืนยันครบหลายเฟรมเท่านั้น
    hold_enabled = settings.auto_add_words or (settings.auto_tts and speech.available)
    if hold_enabled:
        capture = hold_timer.update(confirmed, recognizer.speech_armed, now)
    else:
        capture = hold_timer.update("", False, now)

    hold_pct = capture.progress
    if capture.ready_label:
        emitted_label = capture.ready_label
        if settings.auto_add_words:
            if sentence.add(emitted_label):
                print(f"📝 เพิ่มอัตโนมัติ: {emitted_label}  |  ประโยค: {sentence.text}")
            else:
                print("⚠️ ไม่เพิ่มคำเดิมซ้ำติดกัน")
        if settings.auto_tts and speech.available:
            if speech.speak(emitted_label):
                print(f"🔊 พูด: {emitted_label}")
            else:
                print("⚠️ ยังส่งคำเข้าคิวเสียงไม่ได้")
        recognizer.mark_emitted(emitted_label)
        detection_phase = recognizer.phase
        hold_pct = 1.0

    # ── keyboard + ปุ่มบนหน้ากล้อง ─────────────────────────
    k = cv2.waitKey(1) & 0xFF
    if k == 27:             # ESC → ออก
        break
    key_actions = {
        ord(' '): "add",
        8: "remove",
        13: "clear",
        ord('s'): "speak",
        ord('S'): "speak",
        ord('b'): "save",
        ord('B'): "save",
    }
    action = sentence_actions.popleft() if sentence_actions else key_actions.get(k)
    if action:
        perform_sentence_action(action, confirmed, now)

    # ── วาด UI ──────────────────────────────────────────────

    # Header
    ov = frm.copy()
    cv2.rectangle(ov,(0,0),(W,52),(8,8,8),-1)
    cv2.addWeighted(ov,.65,frm,.35,0,frm)
    fps = 1/max(now-prev,.001); prev = now
    frm = putThai(frm, "ระบบแปลภาษามือเรียลไทม์-TH  (HandVox)",
                  (18,8), fM, (230,230,230))
    cv2.putText(frm, f"FPS:{fps:.0f}", (W-80,34),
                cv2.FONT_HERSHEY_SIMPLEX, .6, (120,120,120), 1)
    esc_text = "ESC · ปิดกล้อง" if W >= 900 else "ESC"
    esc_width, _ = text_size(esc_text, fS)
    frm = putThai(frm, esc_text, (max(12, W-esc_width-100), 13), fS, (155,155,155))

    # Bounding box + label
    if bbox:
        x1,y1,x2,y2 = bbox
        cx = (x1+x2)//2
        active_display_label = confirmed or decision.candidate_label
        c = color(active_display_label) if active_display_label else (90,90,90)
        ov = frm.copy()
        cv2.rectangle(ov,(x1,y1),(x2,y2),c,-1)
        cv2.addWeighted(ov,.09,frm,.91,0,frm)
        cv2.rectangle(frm,(x1,y1),(x2,y2),c,1)
        corner_box(frm,x1,y1,x2,y2,c,t=3)
        if confirmed:
            label = f"{confirmed}  {conf_val:.0%}"
            tw,th = text_size(label, fL)
            bx1=max(0,cx-tw//2-12); bx2=min(W,cx+tw//2+12)
            by1=max(0,y1-th-18);    by2=y1
            cv2.rectangle(frm,(bx1,by1),(bx2,by2),c,-1)
            frm = putThaiC(frm, label, cx, by1+4, fL, (0,0,0))
        elif decision.released and decision.reason == "neutral_released":
            frm = draw_detection_status(
                frm, x1, y1, x2, "พร้อมทำคำเดิมอีกครั้ง", (60, 210, 110)
            )
        elif detection_phase is DetectionPhase.COOLDOWN:
            if decision.reason == "neutral":
                frm = draw_detection_status(
                    frm,
                    x1,
                    y1,
                    x2,
                    f"พักมือเพื่อพร้อมรับคำเดิม {decision.neutral_progress:.0%}",
                    (60, 210, 110),
                    decision.neutral_progress,
                )
            else:
                frm = draw_detection_status(
                    frm,
                    x1,
                    y1,
                    x2,
                    "วางมือในท่าพัก (neutral) ก่อนทำคำเดิมซ้ำ",
                    (0, 190, 235),
                )
        elif (
            detection_phase is DetectionPhase.CANDIDATE
            and bool(decision.candidate_label)
        ):
            candidate = decision.candidate_label or cur
            frm = draw_detection_status(
                frm,
                x1,
                y1,
                x2,
                f"กำลังยืนยัน “{candidate}” {decision.confirm_progress:.0%}",
                (0, 205, 255),
                decision.confirm_progress,
            )
        elif len(motion_frames) < MODEL_SEQUENCE_LENGTH:
            warmup = len(motion_frames) / MODEL_SEQUENCE_LENGTH
            frm = draw_detection_status(
                frm,
                x1,
                y1,
                x2,
                f"กำลังอ่านการเคลื่อนไหว {warmup:.0%}",
                (145, 145, 145),
                warmup,
            )
        elif neutral_detected:
            frm = draw_detection_status(
                frm,
                x1,
                y1,
                x2,
                "ท่าพัก (neutral) · พร้อมรับคำถัดไป",
                (60, 210, 110),
            )
        elif unknown_detected or decision.reason == "unknown":
            frm = draw_detection_status(
                frm,
                x1,
                y1,
                x2,
                f"ไม่แน่ใจ · ท่านี้ยังไม่อยู่ในคำที่รู้จัก {cur_c:.0%}",
                (0, 135, 255),
            )
        elif decision.reason == "low_margin":
            frm = draw_detection_status(
                frm,
                x1,
                y1,
                x2,
                f"ไม่แน่ใจ · ผลสองคำใกล้กัน {cur_c:.0%}",
                (0, 135, 255),
            )
        elif decision.reason == "low_confidence" or prediction_ready:
            frm = draw_detection_status(
                frm,
                x1,
                y1,
                x2,
                f"ไม่แน่ใจ · ลองทำท่าให้ชัดขึ้น {cur_c:.0%}",
                (0, 135, 255),
            )
        else:
            frm = draw_detection_status(
                frm, x1, y1, x2, "กำลังตรวจจับ...", (145, 145, 145)
            )

    # Hold progress bar
    if recognizer.speech_armed and confirmed and hold_pct > 0:
        if settings.auto_add_words and settings.auto_tts and speech.available:
            hold_action = "เพิ่มคำและอ่าน"
        elif settings.auto_add_words:
            hold_action = "เพิ่มคำ"
        else:
            hold_action = "อ่านคำ"
        frm = draw_hold_bar(frm, W, H, hold_pct, hold_action)

    # Confidence bar
    display_confidence = conf_val if conf_val > 0 else (
        cur_c if prediction_ready and not neutral_detected else 0.0
    )
    if display_confidence > 0:
        bf = int((W-40)*min(display_confidence,1.0))
        cv2.rectangle(frm,(20,H-28),(W-20,H-14),(35,35,35),-1)
        bc = (0,220,100) if display_confidence>.80 else (0,200,255) if display_confidence>.60 else (60,60,200)
        cv2.rectangle(frm,(20,H-28),(20+bf,H-14),bc,-1)
        confidence_text = f"ความมั่นใจ: {display_confidence:.0%}"
        if prediction_ready:
            confidence_text += f" · ระยะห่าง: {probability_margin:.0%}"
        frm = putThai(frm, confidence_text,
                      (25,H-50), fS, (150,150,150))

    # Sentence bar
    frm = draw_sentence_bar(frm, W, H, sentence)

    # badge
    if settings.auto_add_words and settings.auto_tts and speech.available:
        badge_txt = f"📝 สร้างประโยคอัตโนมัติ  |  🔊 {speech.engine_name}"
        badge_col = (0,200,80)
    elif settings.auto_add_words:
        badge_txt = "📝 สร้างประโยคอัตโนมัติ"
        badge_col = (0,200,80)
    elif settings.auto_tts and speech.available:
        badge_txt = f"🔊 Auto TTS ({speech.engine_name})"
        badge_col = (0,180,220)
    elif speech.available:
        badge_txt = f"🔊 TTS พร้อม ({speech.engine_name})"
        badge_col = (0,180,220)
    else:
        badge_txt = "🔇 TTS OFF"
        badge_col = (80,80,80)
    frm = draw_badge(frm, device_badge_text, 14, 60, device_badge_color)
    badge_width, _ = text_size(badge_txt, fS)
    frm = draw_badge(
        frm, badge_txt, max(14, W-badge_width-30), 60, badge_col
    )
    if experimental_deployment:
        frm = draw_badge(frm, "โมเดลทดลอง: ยังไม่ผ่านเกณฑ์ โปรดตรวจคำก่อนใช้", 14, 100, (0, 165, 255))

    cv2.imshow(WINDOW_TITLE, frm)

speech.close()
det.close()
cap.release()
cv2.destroyAllWindows()
print("👋 ปิดโปรแกรมแล้ว")
