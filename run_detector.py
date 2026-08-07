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
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from body_features import FEATURE_COUNT, extract_features, upper_body_bbox
from gesture_config import GESTURE_COLORS, GESTURE_NAMES
from gesture_state import DetectionPhase, GestureStateMachine
from handvox.camera_sentence import GestureHoldTimer
from handvox.history import HistoryStore
from handvox.paths import MODEL_MANIFEST_FILE
from handvox.sentence import SentenceBuilder
from handvox.settings import SettingsStore
from sequence_dataset import SEQUENCE_LENGTH
from tts_service import SpeechService


ROOT = Path(__file__).resolve().parent
settings_store = SettingsStore()
settings = settings_store.load_or_default()
if settings_store.last_error:
    print(f"⚠️ settings.json ไม่ถูกต้อง จึงใช้ค่าเริ่มต้น: {settings_store.last_error}")

# ── ฟอนต์ไทย ──────────────────────────────────────────────
def load_font(size):
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
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d   = ImageDraw.Draw(pil)
    d.text(pos, text, font=font, fill=(color[2],color[1],color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

def putThaiC(img, text, cx, y, font, color=(255,255,255)):
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d   = ImageDraw.Draw(pil)
    bb  = d.textbbox((0,0), text, font=font)
    d.text((cx-(bb[2]-bb[0])//2, y), text, font=font,
           fill=(color[2],color[1],color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

def text_size(text, font):
    pil = Image.new("RGB",(1,1))
    bb  = ImageDraw.Draw(pil).textbbox((0,0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

# ── โหลด Model ────────────────────────────────────────────
for filename in ["gesture_model.pkl", "gesture_labels.pkl"]:
    if not (ROOT / filename).exists():
        print(f"❌ ไม่พบ {filename} — รัน train_model.py ก่อน!")
        raise SystemExit(1)

with (ROOT / "gesture_model.pkl").open("rb") as file:
    model = pickle.load(file)
with (ROOT / "gesture_labels.pkl").open("rb") as file:
    le = pickle.load(file)
NAMES = list(le.classes_)
print(f"✅ โหลด model | ท่า: {NAMES}")
internal_labels = set()
if MODEL_MANIFEST_FILE.exists():
    try:
        manifest = json.loads(MODEL_MANIFEST_FILE.read_text(encoding="utf-8"))
        internal_labels = set(manifest.get("internal_classes", []))
    except (OSError, json.JSONDecodeError, TypeError):
        print("⚠️ อ่าน model_manifest.json ไม่ได้ จึงไม่ใช้คลาสภายใน")
if set(NAMES) != set(GESTURE_NAMES).union(internal_labels):
    print("❌ รายชื่อท่าในโมเดลไม่ตรงกับ gesture_config.py")
    print("   โปรดรัน python train_model.py เพื่อสร้างโมเดลใหม่")
    raise SystemExit(1)

# ── MediaPipe ─────────────────────────────────────────────
mp_h = mp.solutions.holistic
det = mp_h.Holistic(static_image_mode=False, model_complexity=1,
                    smooth_landmarks=True,
                    min_detection_confidence=0.7,
                    min_tracking_confidence=0.7)

def color(n): return GESTURE_COLORS.get(n, (0, 255, 160))

if getattr(model, "n_features_in_", FEATURE_COUNT * SEQUENCE_LENGTH) != FEATURE_COUNT * SEQUENCE_LENGTH:
    print("This is not a motion-clip model. Collect clips and train a new model first.")
    raise SystemExit(1)

def corner_box(img, x1,y1,x2,y2, c, t=3, L=30):
    for pts in [[(x1,y1+L),(x1,y1),(x1+L,y1)],
                [(x2-L,y1),(x2,y1),(x2,y1+L)],
                [(x1,y2-L),(x1,y2),(x1+L,y2)],
                [(x2-L,y2),(x2,y2),(x2,y2-L)]]:
        cv2.polylines(img,[np.array(pts)],False,c,t,cv2.LINE_AA)

# ── State ─────────────────────────────────────────────────
MIN_CONFIDENCE = settings.min_confidence
CONFIRM_FRAMES = settings.confirm_frames
RELEASE_SECONDS = settings.release_seconds

motion_frames = deque(maxlen=SEQUENCE_LENGTH)
recognizer = GestureStateMachine(
    min_confidence=MIN_CONFIDENCE,
    confirm_frames=CONFIRM_FRAMES,
    release_seconds=RELEASE_SECONDS,
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
    """Queue a camera-window button click for the main loop."""
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
    """Progress toward automatically adding the confirmed word."""
    bar_y = H - 32 - 146 - 16
    bar_w = int((W - 40) * min(hold_pct, 1.0))
    cv2.rectangle(frm, (20, bar_y), (W-20, bar_y+10), (25,25,25), -1)
    col = (0, 255, 80) if hold_pct >= 1.0 else (0, 200, 255)
    cv2.rectangle(frm, (20, bar_y), (20+bar_w, bar_y+10), col, -1)
    label = f"ค้างท่าไว้เพื่อ{action_label}..." if hold_pct < 1.0 else f"{action_label}แล้ว"
    frm = putThai(frm, f"{label}  {hold_pct*100:.0f}%",
                  (25, bar_y-22), fS, col)
    return frm

print("\n🎥 กล้องเปิดแล้ว | ESC ออก")
if settings.auto_add_words:
    print(f"📝 แสดงท่าค้างไว้ {HOLD_SEC:.1f} วิ → เพิ่มคำลงประโยคอัตโนมัติ")
else:
    print("📝 การเพิ่มคำอัตโนมัติปิดอยู่ — กด Space หรือปุ่ม 'เพิ่มคำ'")
print("   ใช้ปุ่มบนหน้ากล้องเพื่อลบ อ่าน บันทึก หรือล้างประโยค\n")


def save_sentence(source="detector-manual"):
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
    bbox  = None

    feats = extract_features(res)
    if feats is not None:
        bbox = upper_body_bbox(res, W, H)
        motion_frames.append(feats)
        if len(motion_frames) == SEQUENCE_LENGTH:
            sequence = np.array(motion_frames, dtype=np.float32).reshape(1, -1)
            proba = model.predict_proba(sequence)[0]
            ti    = np.argmax(proba)
            cur   = le.classes_[ti]
            cur_c = float(proba[ti])
            if cur in internal_labels:
                # neutral/คลาสภายในใช้ลด false activation แต่ไม่แสดงเป็นคำ
                cur = ""
                cur_c = 0.0

    decision = recognizer.update(
        cur, cur_c, landmarks_visible=feats is not None, now=now
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
        c  = color(confirmed) if confirmed else (90,90,90)
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
        elif detection_phase is DetectionPhase.CANDIDATE:
            frm = putThai(frm, "กำลังยืนยันผล...", (x1+6,max(y1-28,4)),
                          fS, (0,200,255))
        elif len(motion_frames) < SEQUENCE_LENGTH:
            frm = putThai(frm, "กำลังเก็บการเคลื่อนไหว...", (x1+6,max(y1-28,4)),
                          fS, (120,120,120))
        elif cur_c > 0:
            frm = putThai(frm, f"ยังไม่มั่นใจ {cur_c:.0%}",
                          (x1+6,max(y1-28,4)), fS, (0,140,255))
        else:
            frm = putThai(frm,"กำลังตรวจจับ...",(x1+6,max(y1-28,4)),fS,(120,120,120))

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
    if conf_val > 0:
        bf = int((W-40)*min(conf_val,1.0))
        cv2.rectangle(frm,(20,H-28),(W-20,H-14),(35,35,35),-1)
        bc = (0,220,100) if conf_val>.80 else (0,200,255) if conf_val>.60 else (60,60,200)
        cv2.rectangle(frm,(20,H-28),(20+bf,H-14),bc,-1)
        frm = putThai(frm, f"ความมั่นใจ: {conf_val:.0%}",
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
    badge_width, _ = text_size(badge_txt, fS)
    frm = putThai(frm, badge_txt, (max(12, W-badge_width-18), 60), fS, badge_col)

    cv2.imshow(WINDOW_TITLE, frm)

speech.close()
det.close()
cap.release()
cv2.destroyAllWindows()
print("👋 ปิดโปรแกรมแล้ว")
