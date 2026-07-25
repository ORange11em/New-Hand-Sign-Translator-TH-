# ============================================================
# STEP 2 : train_model.py  (SVM + Visualization)
# วิธีใช้ : python train_model.py
# ผลลัพธ์ : gesture_model.pkl, gesture_labels.pkl
#           training_results.png  ← ใช้ใส่รายงานได้เลย
# ============================================================
import pandas as pd, numpy as np, pickle, os
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split, cross_val_score, learning_curve
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
from gesture_config import GESTURE_NAMES

CSV   = "gesture_data.csv"
MODEL = "gesture_model.pkl"
LABEL = "gesture_labels.pkl"
OUT_IMG = "training_results.png"

# ── โหลดฟอนต์ไทย (ถ้ามี) ──────────────────────────────────
def get_thai_font():
    for fp in ["C:/Windows/Fonts/THSarabunNew.ttf",
               "C:/Windows/Fonts/tahoma.ttf"]:
        if os.path.exists(fp):
            return fm.FontProperties(fname=fp)
    return None

thai_font = get_thai_font()

print("="*55)
print("  HAND SIGN TRAINER  (SVM + Visualization)")
print("="*55)

if not os.path.exists(CSV):
    print("❌ ไม่พบ gesture_data.csv — รัน collect_data.py ก่อน!")
    exit()

df = pd.read_csv(CSV, encoding="utf-8")
data_gestures = set(df["label"].unique())
expected_gestures = set(GESTURE_NAMES)
if data_gestures != expected_gestures:
    print("❌ รายชื่อท่าใน gesture_data.csv ไม่ตรงกับ gesture_config.py")
    print(f"   ใน CSV: {sorted(data_gestures)}")
    print(f"   ที่กำหนด: {GESTURE_NAMES}")
    print("   ตรวจสอบข้อมูลให้ตรงกันก่อนเทรน")
    exit()
print(f"\n📊 ข้อมูลทั้งหมด: {len(df)} แถว")
print("\nตัวอย่างต่อท่า:")
for g, n in df["label"].value_counts().items():
    print(f"  {g:15s}: {n:4d}  {'█'*(n//15)}")

X      = df.drop("label", axis=1).values
le     = LabelEncoder()
y      = le.fit_transform(df["label"].values)
NAMES  = le.classes_

Xtr, Xt, ytr, yt = train_test_split(X, y, test_size=.2,
                                    random_state=42, stratify=y)

print(f"\n🔵 Train: {len(Xtr)}  Test: {len(Xt)}")
print("กำลัง train SVM...")

clf = SVC(kernel="rbf", C=10, gamma="scale", probability=True)
clf.fit(Xtr, ytr)

y_pred = clf.predict(Xt)
acc    = (y_pred == yt).mean()
print(f"\n🎯 Accuracy: {acc*100:.2f}%")
print(classification_report(yt, y_pred, target_names=NAMES))

cv = cross_val_score(clf, X, y, cv=5)
print(f"🔄 Cross-Val: {cv.mean()*100:.2f}% ± {cv.std()*100:.2f}%")

# ════════════════════════════════════════════════════════════
#  📊  สร้างกราฟ 3 ช่อง
# ════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(20, 6))
fig.patch.set_facecolor("#0d0d0d")

fp = thai_font  # shorthand

# ── 1) Confusion Matrix ─────────────────────────────────────
ax1 = fig.add_subplot(1, 3, 1)
cm  = confusion_matrix(yt, y_pred)
sns.heatmap(cm, annot=True, fmt="d", cmap="YlGn",
            xticklabels=NAMES, yticklabels=NAMES,
            linewidths=.5, linecolor="#333",
            cbar_kws={"shrink": .8}, ax=ax1)
ax1.set_facecolor("#111")
ax1.tick_params(colors="white", labelsize=9)
if thai_font:
    for lbl in ax1.get_xticklabels() + ax1.get_yticklabels():
        lbl.set_fontproperties(fp)
ax1.set_xlabel("Predicted", color="#aaa", fontsize=10)
ax1.set_ylabel("Actual",    color="#aaa", fontsize=10)
ax1.set_title("Confusion Matrix", color="white", fontsize=13, pad=10)
ax1.xaxis.label.set_color("#aaa"); ax1.yaxis.label.set_color("#aaa")
plt.setp(ax1.get_xticklabels(), rotation=35, ha="right")
plt.setp(ax1.get_yticklabels(), rotation=0)

# ── 2) Per-class Accuracy Bar ──────────────────────────────
ax2 = fig.add_subplot(1, 3, 2)
per_acc = cm.diagonal() / cm.sum(axis=1) * 100
colors  = plt.cm.RdYlGn(per_acc / 100)
bars    = ax2.barh(NAMES, per_acc, color=colors, edgecolor="#555", height=.65)
ax2.set_facecolor("#111")
ax2.set_xlim(0, 110)
ax2.set_xlabel("Accuracy (%)", color="#aaa", fontsize=10)
ax2.set_title("Per-class Accuracy", color="white", fontsize=13, pad=10)
ax2.tick_params(colors="white", labelsize=9)
if thai_font:
    for lbl in ax2.get_yticklabels():
        lbl.set_fontproperties(fp)
for bar, val in zip(bars, per_acc):
    ax2.text(val + 1.5, bar.get_y() + bar.get_height()/2,
             f"{val:.1f}%", va="center", color="white", fontsize=9)
ax2.axvline(90, color="#ff6", linestyle="--", lw=1, alpha=.5, label="90%")
ax2.legend(facecolor="#222", labelcolor="white", fontsize=8)
ax2.spines[:].set_color("#444")

# ── 3) Learning Curve ──────────────────────────────────────
ax3 = fig.add_subplot(1, 3, 3)
train_sz, train_sc, val_sc = learning_curve(
    clf, X, y, cv=5,
    train_sizes=np.linspace(.1, 1.0, 8),
    scoring="accuracy", n_jobs=-1
)
tmean = train_sc.mean(axis=1) * 100
tstd  = train_sc.std(axis=1)  * 100
vmean = val_sc.mean(axis=1)   * 100
vstd  = val_sc.std(axis=1)    * 100

ax3.set_facecolor("#111")
ax3.plot(train_sz, tmean, "o-", color="#00e5ff", lw=2,  label="Train Score")
ax3.fill_between(train_sz, tmean-tstd, tmean+tstd, alpha=.2, color="#00e5ff")
ax3.plot(train_sz, vmean, "s-", color="#76ff03", lw=2,  label="CV Score")
ax3.fill_between(train_sz, vmean-vstd, vmean+vstd, alpha=.2, color="#76ff03")
ax3.set_xlabel("Training Samples", color="#aaa", fontsize=10)
ax3.set_ylabel("Accuracy (%)",     color="#aaa", fontsize=10)
ax3.set_title("Learning Curve",    color="white", fontsize=13, pad=10)
ax3.set_ylim(50, 105)
ax3.tick_params(colors="white")
ax3.legend(facecolor="#222", labelcolor="white", fontsize=9)
ax3.spines[:].set_color("#444")
ax3.grid(alpha=.2, color="#555")

# ── Footer text ───────────────────────────────────────────
fig.text(.5, .97,
         f"Overall Accuracy: {acc*100:.2f}%   |   "
         f"Cross-Val: {cv.mean()*100:.2f}% ± {cv.std()*100:.2f}%   |   "
         f"Gestures: {len(NAMES)}   |   Samples: {len(df)}",
         ha="center", color="#ccc", fontsize=11,
         fontweight="bold",
         bbox=dict(facecolor="#1a1a1a", edgecolor="#444",
                   boxstyle="round,pad=.4"))

plt.tight_layout(rect=[0, 0, 1, .95])
plt.savefig(OUT_IMG, dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"\n📈 บันทึกกราฟ → {OUT_IMG}")

with open(MODEL, "wb") as f: pickle.dump(clf, f)
with open(LABEL, "wb") as f: pickle.dump(le,  f)
print(f"✅ บันทึก {MODEL} และ {LABEL}")
print("ขั้นตอนถัดไป: python run_detector.py")
