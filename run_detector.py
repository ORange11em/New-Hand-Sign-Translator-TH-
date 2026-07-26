# ============================================================
# STEP 3 : run_detector.py  (+ TTS เสียง + Sentence Builder)
# วิธีใช้ : python run_detector.py
#
# 🔊 พูดอัตโนมัติทันทีที่ยกมือแสดงท่าค้างไว้ 1.5 วิ
#
# คีย์ลัด:
#   SPACE      → เพิ่มคำปัจจุบันลงประโยค
#   BACKSPACE  → ลบคำล่าสุดออกจากประโยค
#   ENTER      → ล้างประโยคทั้งหมด
#   S          → อ่านประโยคออกเสียง (TTS)
#   ESC        → ออก
# ============================================================
import cv2, mediapipe as mp, numpy as np
import pickle, math, time, os, threading
from collections import deque, Counter
from PIL import Image, ImageDraw, ImageFont
from body_features import FEATURE_COUNT, extract_features, upper_body_bbox
from gesture_config import GESTURE_COLORS, GESTURE_NAMES

# ── TTS — gTTS + pygame (ภาษาไทย ต้องการอินเทอร์เน็ต) ──────
TTS_ENABLED = False
TTS_ENGINE  = "none"

try:
    from gtts import gTTS
    import pygame
    pygame.mixer.init()
    TTS_ENABLED = True
    TTS_ENGINE  = "gtts"
    print("✅ TTS พร้อมใช้งาน (gTTS)")
except ImportError:
    print("⚠️  ไม่พบ gTTS/pygame → pip install gTTS pygame")

def speak(text):
    if not TTS_ENABLED or not text.strip():
        return
    def _run():
        try:
            import tempfile, uuid
            tts = gTTS(text=text, lang="th")
            tmp = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.mp3")
            tts.save(tmp)
            pygame.mixer.music.load(tmp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            pygame.mixer.music.unload()
            os.remove(tmp)
        except Exception as e:
            print(f"TTS error: {e}")
    threading.Thread(target=_run, daemon=True).start()

# ── ฟอนต์ไทย ──────────────────────────────────────────────
def load_font(size):
    for fp in ["C:/Windows/Fonts/THSarabunNew.ttf",
               "C:/Windows/Fonts/tahoma.ttf",
               "C:/Windows/Fonts/arial.ttf"]:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()

fL = load_font(48)
fM = load_font(30)
fS = load_font(20)
fXL = load_font(58)

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
for f in ["gesture_model.pkl","gesture_labels.pkl"]:
    if not os.path.exists(f):
        print(f"❌ ไม่พบ {f} — รัน train_model.py ก่อน!"); exit()

with open("gesture_model.pkl","rb") as f: model = pickle.load(f)
with open("gesture_labels.pkl","rb") as f: le   = pickle.load(f)
NAMES = list(le.classes_)
print(f"✅ โหลด model | ท่า: {NAMES}")
if set(NAMES) != set(GESTURE_NAMES):
    print("❌ รายชื่อท่าในโมเดลไม่ตรงกับ gesture_config.py")
    print("   โปรดรัน python train_model.py เพื่อสร้างโมเดลใหม่")
    exit()

# ── MediaPipe ─────────────────────────────────────────────
mp_h = mp.solutions.holistic
det = mp_h.Holistic(static_image_mode=False, model_complexity=1,
                    smooth_landmarks=True,
                    min_detection_confidence=0.7,
                    min_tracking_confidence=0.7)

def color(n): return GESTURE_COLORS.get(n, (0, 255, 160))

if getattr(model, "n_features_in_", FEATURE_COUNT) != FEATURE_COUNT:
    print("This is a hand-only model. Collect upper-body samples and train a new model first.")
    exit()

def corner_box(img, x1,y1,x2,y2, c, t=3, L=30):
    for pts in [[(x1,y1+L),(x1,y1),(x1+L,y1)],
                [(x2-L,y1),(x2,y1),(x2,y1+L)],
                [(x1,y2-L),(x1,y2),(x1+L,y2)],
                [(x2-L,y2),(x2,y2),(x2,y2-L)]]:
        cv2.polylines(img,[np.array(pts)],False,c,t,cv2.LINE_AA)

# ── State ─────────────────────────────────────────────────
smooth    = deque(maxlen=3)
confirmed = ""
conf_val  = 0.0
no_hand   = None
RESET     = 0.4
THRESH    = 0.40

# ── Auto-speak state ───────────────────────────────────────
# ยกมือค้างไว้ SPEAK_HOLD_SEC วิ → พูดอัตโนมัติ
# เอามือออกแล้วยกขึ้นใหม่ → พูดได้ใหม่เลย
SPEAK_HOLD_SEC  = 1.0      # วินาทีที่ต้องค้างไว้ก่อนพูด
last_spoken     = ""       # ท่าล่าสุดที่พูดไปแล้ว
pending_gesture = ""       # ท่าที่กำลังรอจับเวลา
gesture_start   = 0.0      # เวลาที่เริ่มเห็นท่านี้

# ── Sentence Builder ───────────────────────────────────────
sentence     = []
add_cooldown = 0.0
COOLDOWN_SEC = 1.0

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
prev = time.time()

# ── helper: Sentence Bar ───────────────────────────────────
def draw_sentence_bar(frm, W, H, sentence):
    BAR_H = 80
    bar_y = H - BAR_H - 32
    ov = frm.copy()
    cv2.rectangle(ov, (0, bar_y), (W, bar_y+BAR_H), (15,15,15), -1)
    cv2.addWeighted(ov, .85, frm, .15, 0, frm)
    cv2.line(frm, (0, bar_y), (W, bar_y), (60,60,60), 1)
    frm = putThai(frm, "📝 ประโยค:", (12, bar_y+6), fS, (130,130,130))
    sx = 130
    for word in sentence:
        c = color(word)
        tw, th = text_size(word, fM)
        pad = 6
        cv2.rectangle(frm, (sx-pad, bar_y+12), (sx+tw+pad, bar_y+12+th+4),
                      tuple(int(v*0.35) for v in c), -1)
        cv2.rectangle(frm, (sx-pad, bar_y+12), (sx+tw+pad, bar_y+12+th+4), c, 1)
        frm = putThai(frm, word, (sx, bar_y+14), fM, c)
        sx += tw + pad*2 + 10
        if sx > W - 200:
            sx = 130
            bar_y += 40
    frm = putThai(frm, "SPACE =เพิ่มคำ  BS =ลบ  ENTER =ล้าง  S =อ่านเสียง",
                  (12, bar_y+BAR_H-20), fS, (70,70,70))
    frm = putThai(frm, f"{len(sentence)} คำ", (W-70, bar_y+6), fS, (80,80,80))
    return frm

# ── helper: Hold Progress Bar ──────────────────────────────
def draw_hold_bar(frm, W, H, hold_pct):
    """progress bar สีฟ้า แสดงความคืบหน้าของการค้างท่า"""
    bar_y = H - 32 - 80 - 16
    bar_w = int((W - 40) * min(hold_pct, 1.0))
    cv2.rectangle(frm, (20, bar_y), (W-20, bar_y+10), (25,25,25), -1)
    col = (0, 255, 80) if hold_pct >= 1.0 else (0, 200, 255)
    cv2.rectangle(frm, (20, bar_y), (20+bar_w, bar_y+10), col, -1)
    label = "🔊 ค้างไว้เพื่อพูด..." if hold_pct < 1.0 else "🔊 กำลังพูด..."
    frm = putThai(frm, f"{label}  {hold_pct*100:.0f}%",
                  (25, bar_y-22), fS, col)
    return frm

print("\n🎥 กล้องเปิดแล้ว | ESC ออก")
print("🔊 ยกมือแสดงท่าค้างไว้ 1.0 วิ → พูดอัตโนมัติ\n")

while True:
    ok, frm = cap.read()
    if not ok: break
    frm = cv2.flip(frm, 1)
    H, W = frm.shape[:2]
    res  = det.process(cv2.cvtColor(frm, cv2.COLOR_BGR2RGB))
    now  = time.time()

    cur   = ""
    cur_c = 0.0
    bbox  = None

    feats = extract_features(res)
    if feats is not None:
        no_hand = None
        bbox = upper_body_bbox(res, W, H)
        proba = model.predict_proba(np.array(feats).reshape(1, -1))[0]
        ti    = np.argmax(proba)
        tc    = proba[ti]
        if tc >= THRESH:
            cur   = le.classes_[ti]
            cur_c = float(tc)
    else:
        if no_hand is None:
            no_hand = now
        elif now - no_hand > RESET:
            smooth.clear()
            confirmed = ""; conf_val = 0.0
            # รีเซ็ต hold timer เมื่อเอามือออก
            # last_spoken รีเซ็ตด้วย → ยกมือขึ้นใหม่พูดได้ทันที
            pending_gesture = ""
            gesture_start   = 0.0
            last_spoken     = ""

    if cur:
        smooth.append((cur, cur_c))
        labels = [x[0] for x in smooth]
        top    = Counter(labels).most_common(1)[0][0]
        confs  = [x[1] for x in smooth if x[0]==top]
        confirmed = top
        conf_val  = sum(confs)/len(confs)

    # ── Auto-speak: จับเวลาค้างท่า ──────────────────────────
    # ถ้าท่าเปลี่ยน → reset จับเวลาใหม่
    if confirmed != pending_gesture:
        pending_gesture = confirmed
        gesture_start   = now

    hold_pct = 0.0
    if confirmed and confirmed != last_spoken:
        hold_pct = (now - gesture_start) / SPEAK_HOLD_SEC
        if hold_pct >= 1.0:
            speak(confirmed)
            last_spoken = confirmed
            print(f"🔊 พูด: {confirmed}")

    # ── keyboard ────────────────────────────────────────────
    k = cv2.waitKey(1) & 0xFF

    if k == ord(' '):       # SPACE → เพิ่มคำลงประโยค
        if confirmed and (now - add_cooldown) > COOLDOWN_SEC:
            sentence.append(confirmed)
            add_cooldown = now
            print(f"📝 เพิ่ม: {confirmed}  |  ประโยค: {' '.join(sentence)}")

    elif k == 8:            # BACKSPACE → ลบคำล่าสุด
        if sentence:
            print(f"🗑️  ลบ: {sentence.pop()}")

    elif k == 13:           # ENTER → ล้างประโยค
        sentence.clear()
        print("🔄 ล้างประโยคแล้ว")

    elif k == ord('s'):     # S → อ่านประโยคทั้งหมด
        if sentence:
            full = " ".join(sentence)
            print(f"🔊 อ่าน: {full}")
            speak(full)
        else:
            print("⚠️  ประโยคว่างอยู่")

    elif k == 27:           # ESC → ออก
        break

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
        else:
            frm = putThai(frm,"กำลังตรวจจับ...",(x1+6,max(y1-28,4)),fS,(120,120,120))

    # Hold progress bar
    if confirmed and confirmed != last_spoken and hold_pct > 0:
        frm = draw_hold_bar(frm, W, H, hold_pct)

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
    if TTS_ENABLED:
        badge_txt = f"🔊 Auto TTS ({TTS_ENGINE})"
        badge_col = (0,200,80)
    else:
        badge_txt = "🔇 TTS OFF"
        badge_col = (80,80,80)
    frm = putThai(frm, badge_txt, (W-200, 60), fS, badge_col)

    cv2.putText(frm,"ESC=quit",(12,H-5),
                cv2.FONT_HERSHEY_SIMPLEX,.38,(60,60,60),1)
    cv2.imshow("Hand Sign Translator — TH", frm)

cap.release(); cv2.destroyAllWindows()
print("👋 ปิดโปรแกรมแล้ว")
