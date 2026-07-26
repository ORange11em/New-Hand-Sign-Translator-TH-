
import argparse
import cv2, mediapipe as mp, csv, os, time, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from pathlib import Path
from body_features import extract_features, feature_columns, upper_body_bbox
from gesture_config import GESTURES

# ── ฟอนต์ไทย ──────────────────────────────────────────────
def load_font(size):
    for fp in ["C:/Windows/Fonts/THSarabunNew.ttf",
               "C:/Windows/Fonts/tahoma.ttf",
               "C:/Windows/Fonts/arial.ttf"]:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()

fL = load_font(56)   # ใหญ่
fM = load_font(34)   # กลาง
fS = load_font(22)   # เล็ก

def putThai(img, text, pos, font, color=(255,255,255)):
    pil  = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d    = ImageDraw.Draw(pil)
    d.text(pos, text, font=font, fill=(color[2],color[1],color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

def putThaiC(img, text, cx, y, font, color=(255,255,255)):
    pil  = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d    = ImageDraw.Draw(pil)
    bb   = d.textbbox((0,0), text, font=font)
    d.text((cx-(bb[2]-bb[0])//2, y), text, font=font,
           fill=(color[2],color[1],color[0]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

# ── MediaPipe ─────────────────────────────────────────────
mp_h = mp.solutions.holistic
detector = mp_h.Holistic(static_image_mode=False, model_complexity=1,
                         smooth_landmarks=True,
                         min_detection_confidence=0.7,
                         min_tracking_confidence=0.7)

SAMPLES = 300          # ตัวอย่างต่อท่า
CSV     = "gesture_data.csv"

# ── Normalize 1 มือ → 63 features ─────────────────────────
def ensure_upper_body_dataset():
    """Create the new schema and archive, rather than destroy, hand-only data."""
    expected_header = feature_columns() + ["label"]
    csv_path = Path(CSV)
    if csv_path.exists():
        with csv_path.open("r", newline="", encoding="utf-8") as file:
            current_header = next(csv.reader(file), [])
        if current_header == expected_header:
            return False

        backup_dir = Path("gesture_backups")
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"gesture_data_hand_only_{stamp}.csv"
        shutil.move(csv_path, backup_path)
        print(f"Legacy data archived: {backup_path}")

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerow(expected_header)
    return True

# ── สร้าง CSV ──────────────────────────────────────────────
dataset_reset = ensure_upper_body_dataset()

def count_ex(g):
    if not os.path.exists(CSV): return 0
    with open(CSV,"r",encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    return sum(1 for r in rows if r and r[-1]==g)

# ── กล้อง ──────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

parser = argparse.ArgumentParser(description="Collect HandVox gesture samples")
parser.add_argument("--gesture", help="Collect samples for this gesture only")
args = parser.parse_args()

if args.gesture and args.gesture not in GESTURES:
    parser.error(f"ไม่พบท่า '{args.gesture}' ในการตั้งค่า")

if dataset_reset:
    print("Upper-body mode is new: collecting every gesture again.")
    g_list = list(GESTURES.keys())
elif args.gesture:
    g_list = [args.gesture]
else:
    g_list = list(GESTURES.keys())
idx    = 0

while idx < len(g_list):
    g      = g_list[idx]
    howto  = GESTURES[g]
    ex     = count_ex(g)

    if ex >= SAMPLES:
        print(f"✅ {g} ครบแล้ว ({ex})")
        idx += 1
        continue

    remain = SAMPLES - ex
    cnt    = ex
    print(f"\n👐 [{g}] — {howto} | เหลือ {remain}")

    # ── รอ SPACE ──────────────────────────────────────────
    while True:
        ok,frm = cap.read()
        if not ok: break
        frm = cv2.flip(frm,1)
        H,W = frm.shape[:2]
        ov  = frm.copy()
        cv2.rectangle(ov,(0,0),(W,H),(0,0,0),-1)
        cv2.addWeighted(ov,.50,frm,.50,0,frm)

        frm = putThaiC(frm,"ท่าถัดไป",W//2,H//2-160,fM,(160,160,160))
        frm = putThaiC(frm,g,         W//2,H//2-100,fL,(0,255,160))
        frm = putThaiC(frm,howto,     W//2,H//2-20, fS,(200,200,100))
        frm = putThaiC(frm,f"เหลือ {remain} ตัวอย่าง",W//2,H//2+20,fS,(160,160,160))
        frm = putThaiC(frm,"กด SPACE เริ่ม  |  Q ออก",W//2,H//2+60,fS,(0,210,255))

        cv2.imshow("Data Collector",frm)
        k = cv2.waitKey(1)&0xFF
        if k==ord(' '): cd=time.time(); break
        if k==ord('q'): cap.release(); cv2.destroyAllWindows(); exit()

    # ── countdown ─────────────────────────────────────────
    while True:
        ok,frm = cap.read()
        if not ok: break
        frm = cv2.flip(frm,1)
        H,W = frm.shape[:2]
        rem = int(3-(time.time()-cd))
        if rem<=0: break
        ov=frm.copy(); cv2.rectangle(ov,(0,0),(W,H),(0,0,0),-1)
        cv2.addWeighted(ov,.5,frm,.5,0,frm)
        frm = putThaiC(frm,f"เตรียมพร้อม {rem}",W//2,H//2-40,fL,(0,220,255))
        frm = putThaiC(frm,g,W//2,H//2+30,fM,(0,255,160))
        cv2.imshow("Data Collector",frm)
        cv2.waitKey(1)

    # ── เก็บข้อมูล ─────────────────────────────────────────
    print(f"  📸 เก็บ [{g}]...")
    target = ex + remain

    while cnt < target:
        ok,frm = cap.read()
        if not ok: break
        frm = cv2.flip(frm,1)
        H,W = frm.shape[:2]
        rgb = cv2.cvtColor(frm,cv2.COLOR_BGR2RGB)
        res = detector.process(rgb)

        saved = False
        feats = extract_features(res)
        if feats is not None:
            with open(CSV,"a",newline="",encoding="utf-8") as f:
                csv.writer(f).writerow(feats+[g])
            cnt  += 1
            saved = True

            bbox = upper_body_bbox(res, W, H)
            if bbox:
                x1, y1, x2, y2 = bbox
                cv2.rectangle(frm,(x1,y1),(x2,y2),(0,255,100),2)

        pct  = int((cnt-ex)/remain*100) if remain>0 else 100
        bw   = W-40
        cv2.rectangle(frm,(20,H-40),(W-20,H-20),(40,40,40),-1)
        cv2.rectangle(frm,(20,H-40),(20+int(bw*pct/100),H-20),(0,220,100),-1)
        frm = putThai(frm,f"เก็บ: {g}  {cnt-ex}/{remain}  ({pct}%)",(20,8),fM,(0,255,160))
        if not saved:
            frm = putThai(frm,"ไม่เห็นมือ! ยกมือให้ชัดขึ้น",(20,55),fS,(0,100,255))

        cv2.imshow("Data Collector",frm)
        if cv2.waitKey(1)&0xFF==ord('q'):
            cap.release(); cv2.destroyAllWindows(); exit()

    print(f"  ✅ [{g}] ครบ!")
    idx += 1

cap.release(); cv2.destroyAllWindows()
print("\n✅ เก็บครบทุกท่า! → python train_model.py")
