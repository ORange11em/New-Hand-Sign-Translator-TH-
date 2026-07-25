
import cv2, mediapipe as mp, csv, os, time, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
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
mp_h  = mp.solutions.hands
detector = mp_h.Hands(static_image_mode=False, max_num_hands=1,
                      min_detection_confidence=0.85,
                      min_tracking_confidence=0.85, model_complexity=1)

SAMPLES = 300          # ตัวอย่างต่อท่า
CSV     = "gesture_data.csv"

# ── Normalize 1 มือ → 63 features ─────────────────────────
def norm(lm):
    wx,wy,wz = lm[0].x, lm[0].y, lm[0].z
    sc = math.sqrt((lm[9].x-wx)**2+(lm[9].y-wy)**2+(lm[9].z-wz)**2)+1e-6
    return [v for p in lm for v in ((p.x-wx)/sc,(p.y-wy)/sc,(p.z-wz)/sc)]

# ── สร้าง CSV ──────────────────────────────────────────────
if not os.path.exists(CSV):
    with open(CSV,"w",newline="",encoding="utf-8") as f:
        h = [f"lm{i}_{a}" for i in range(21) for a in "xyz"] + ["label"]
        csv.writer(f).writerow(h)
    print(f"สร้าง {CSV} แล้ว")

def count_ex(g):
    if not os.path.exists(CSV): return 0
    with open(CSV,"r",encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    return sum(1 for r in rows if r and r[-1]==g)

# ── กล้อง ──────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

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
        if res.multi_hand_landmarks:
            lm    = res.multi_hand_landmarks[0].landmark
            feats = norm(lm)
            with open(CSV,"a",newline="",encoding="utf-8") as f:
                csv.writer(f).writerow(feats+[g])
            cnt  += 1
            saved = True

            xs=[p.x for p in lm]; ys=[p.y for p in lm]
            x1=int(max(0,min(xs)-.05)*W); y1=int(max(0,min(ys)-.05)*H)
            x2=int(min(1,max(xs)+.05)*W); y2=int(min(1,max(ys)+.05)*H)
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
