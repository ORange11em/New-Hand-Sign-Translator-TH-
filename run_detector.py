"""เปิดกล้อง ตรวจจับท่าจากโมเดล และสะสมคำเป็นประโยคแบบเรียลไทม์.

ลำดับหลักคือ อ่านภาพจากกล้อง -> ดึง landmark -> สะสมลำดับการเคลื่อนไหว
-> ให้โมเดลทำนาย -> ยืนยันผลด้วย state machine -> เพิ่มคำ/อ่านเสียง/บันทึกประโยค
หน้าต่างนี้แยกภาพกล้องออกจากปุ่มและผลแปล โดยไม่แก้ไขหรือเทรนโมเดล
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
import json
import pickle
import time
from collections import deque

from handvox.temporal_model import TemporalClassifier

import cv2
import mediapipe as mp
import numpy as np

from body_features import FEATURE_COUNT, extract_features, upper_body_bbox
from gesture_config import GESTURE_NAMES
from gesture_state import DetectionPhase, GestureStateMachine
from handvox.camera_sentence import GestureHoldTimer
from handvox.detector_performance import DetectorPerformance, timing_lines
from handvox.detector_sequence import expire_missing_motion
from handvox.detector_view import DetectorView, DetectorViewState, detection_presentation
from handvox.feature_pipeline import (
    FEATURE_SCHEMA_VERSION,
    OUTPUT_FEATURE_COUNT,
)
from handvox.history import HistoryStore
from handvox.paths import (
    ROOT,
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
elif model_backend == "temporal_tcn":
    device_badge_text = "CPU · TCN"
    if settings.prefer_gpu:
        device_badge_text += " · GPU ไม่พร้อม"
else:
    device_badge_text = (
        "CPU · SVC สำรอง" if temporal_load_error else "CPU · SVC เดิม"
    )

# ── MediaPipe ─────────────────────────────────────────────
mp_h = mp.solutions.holistic
det = mp_h.Holistic(static_image_mode=False, model_complexity=1,
                    smooth_landmarks=True,
                    min_detection_confidence=0.7,
                    min_tracking_confidence=0.7)

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
WINDOW_TITLE = "HandVox - Live"
view = DetectorView(settings.font_scale)
performance = DetectorPerformance()
frame_times = deque(maxlen=MODEL_SEQUENCE_LENGTH)
show_details = False
performance_snapshot = performance.snapshot()
last_performance_update = 0.0
action_feedback = ""
feedback_until = 0.0
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


def queue_sentence_action(event, x, y, _flags, _param):
    """แปลงตำแหน่งคลิกบนหน้ากล้องเป็น action ให้ลูปหลักทำต่อ."""
    if event != cv2.EVENT_LBUTTONUP:
        return
    for action, (x1, y1, x2, y2) in sentence_action_regions.items():
        if x1 <= x < x2 and y1 <= y < y2:
            sentence_actions.append(action)
            break


cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_TITLE, *view.size)
cv2.setMouseCallback(WINDOW_TITLE, queue_sentence_action)

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
    """Apply an action and show its result without replacing the detected word."""
    global action_feedback, feedback_until
    if action == "add":
        success = add_confirmed_word(label, now)
        action_feedback = "เพิ่มคำแล้ว" if success else "รอคำที่ยืนยันก่อน"
    elif action == "remove":
        removed = sentence.remove_last()
        action_feedback = "ลบคำล่าสุดแล้ว" if removed else "ประโยคยังว่างอยู่"
    elif action == "clear":
        sentence.clear()
        action_feedback = "ล้างประโยคแล้ว"
    elif action == "speak":
        action_feedback = "ส่งประโยคไปอ่านแล้ว" if speak_sentence() else "ยังอ่านประโยคไม่ได้"
    elif action == "save":
        action_feedback = "บันทึกประโยคแล้ว" if save_sentence() else "ยังบันทึกไม่ได้"
    feedback_until = now + 2.0


try:
    while True:
        try:
            window_visible = cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE)
        except cv2.error:
            break
        if window_visible < 1:
            break
        frame_started = time.perf_counter()
        durations = {}
        ok, frm = cap.read()
        if not ok: break
        frm = cv2.flip(frm, 1)
        H, W = frm.shape[:2]
        durations["camera"] = time.perf_counter() - frame_started
        landmarks_started = time.perf_counter()
        res = det.process(cv2.cvtColor(frm, cv2.COLOR_BGR2RGB))
        durations["landmarks"] = time.perf_counter() - landmarks_started
        state_started = time.perf_counter()
        durations["inference"] = 0.0
        now = time.monotonic()

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
        if feats is None:
            expire_missing_motion(
                motion_frames, frame_times, now=now, release_seconds=RELEASE_SECONDS,
            )
        if feats is not None:
            bbox = upper_body_bbox(res, W, H)
            motion_frames.append(feats)
            frame_times.append(now)
            if len(motion_frames) == MODEL_SEQUENCE_LENGTH:
                inference_started = time.perf_counter()
                raw_sequence = np.asarray(motion_frames, dtype=np.float32)
                if model_backend == "temporal_tcn":
                    # inference ห้าม augmentation และต้องใช้ schema เดียวกับตอนเทรน
                    sequence = temporal_pipeline.transform(
                        raw_sequence, training=False
                    )[None, :, :]
                else:
                    sequence = raw_sequence.reshape(1, -1)
                proba = model.predict_proba(sequence)[0]
                durations["inference"] = time.perf_counter() - inference_started
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
            frame_times.clear()

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
        if k in (ord("d"), ord("D")) or action == "details":
            show_details = not show_details
        elif action == "close":
            break
        elif action:
            perform_sentence_action(action, confirmed, now)

        durations["state"] = time.perf_counter() - state_started - durations["inference"]
        render_started = time.perf_counter()
        if now - last_performance_update >= 0.5:
            performance_snapshot = performance.snapshot()
            last_performance_update = now
        if settings.auto_add_words and settings.auto_tts and speech.available:
            hold_action = "เพิ่มคำและอ่าน"
        elif settings.auto_add_words:
            hold_action = "เพิ่มคำ"
        else:
            hold_action = "อ่านคำ"
        presentation = detection_presentation(
            decision, visible=feats is not None, frame_count=len(motion_frames),
            sequence_length=MODEL_SEQUENCE_LENGTH, neutral=neutral_detected,
            unknown=unknown_detected, policy_rejected=rejected_by_recognition_policy,
            hold_progress=round(hold_pct, 2) if recognizer.speech_armed else 0.0,
            hold_action=hold_action,
        )
        display_confidence = conf_val if conf_val > 0 else (
            cur_c if prediction_ready and not neutral_detected else 0.0
        )
        sequence_seconds = frame_times[-1] - frame_times[0] if len(frame_times) > 1 else None
        if settings.auto_tts and speech.available:
            speech_status = "อ่านคำอัตโนมัติ"
        elif speech.available:
            speech_status = "อ่านประโยคด้วยปุ่ม"
        else:
            speech_status = "เสียงไม่พร้อม"
        view_state = DetectorViewState(
            detection=presentation, sentence=sentence.text, word_count=len(sentence),
            confidence=round(display_confidence, 2), fps=round(performance_snapshot["fps"], 1),
            device=device_badge_text, experimental=experimental_deployment,
            auto_add=settings.auto_add_words, speech_status=speech_status,
            features_visible=feats is not None,
            can_add=bool(confirmed and recognizer.speech_armed and now - add_cooldown > COOLDOWN_SEC),
            can_speak=speech.available, details=show_details,
            timing=timing_lines(performance_snapshot, sequence_seconds) if show_details else (),
            feedback=action_feedback if now < feedback_until else "",
        )
        display_frame = view.render(frm, view_state, bbox)
        sentence_action_regions.clear()
        sentence_action_regions.update(view.action_regions(view_state))
        durations["render"] = time.perf_counter() - render_started
        display_started = time.perf_counter()
        cv2.imshow(WINDOW_TITLE, display_frame)
        durations["display"] = time.perf_counter() - display_started
        durations["total"] = time.perf_counter() - frame_started
        performance.record(durations, predicted=prediction_ready, features_visible=feats is not None)
finally:
    speech.close()
    det.close()
    cap.release()
    cv2.destroyAllWindows()
    try:
        performance.save(
            ROOT / "detector_performance_latest.json",
            metadata={
                "model_backend": model_backend,
                "model_device": model_device,
                "model_sequence_length": MODEL_SEQUENCE_LENGTH,
                "minimum_confidence": MIN_CONFIDENCE,
                "minimum_probability_margin": MIN_PROBABILITY_MARGIN,
                "missing_motion_reset_seconds": RELEASE_SECONDS,
            },
        )
    except OSError as error:
        print(f"บันทึกเวลาประมวลผลไม่ได้: {error}")
    print("ปิดกล้องแล้ว")
