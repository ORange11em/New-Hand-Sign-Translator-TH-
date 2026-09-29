"""Create report-ready confusion matrices from the saved 18-word experiment."""
from pathlib import Path
import csv
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / 'experiments/quick_20260928_063139_251134'
EXTERNAL = EXPERIMENT / 'external_evaluations/20260928_075546_882114_dc18826b'
OUTPUT = ROOT / 'ผลลัพธ์เอกสาร/ฉบับเพิ่มท่าอะไร_18คำ/รูปประกอบ'
OUTPUT.mkdir(parents=True, exist_ok=True)
FONT = font_manager.FontProperties(fname='C:/Windows/Fonts/tahoma.ttf')
BOLD = font_manager.FontProperties(fname='C:/Windows/Fonts/tahomabd.ttf')

reports = [
    (EXPERIMENT, 'confusion_matrix_18words_existing_signers.png',
     'ผู้ทำท่าเดิม — แยกรอบบันทึกไว้ทดสอบ', 144, 122,
     'โมเดลทดลอง 18 คำ ไม่รวมคลาส neutral และ unknown'),
    (EXTERNAL, 'confusion_matrix_18words_new_signer.png',
     'ผู้ทำท่าใหม่ — person_03', 287, 254,
     'ประเมินเฉพาะ 18 คำ • ข้าม neutral 16 คลิป และ unknown 16 คลิป รวม 32 คลิป'),
]

audit = []
for folder, filename, subtitle, count, correct, note in reports:
    metrics_path = folder / 'metrics.json'
    data = json.loads(metrics_path.read_text(encoding='utf-8'))
    labels = data['classes']
    matrix = np.asarray(data['aggregate']['confusion_matrix'], dtype=int)
    with (folder / 'confusion_matrix.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    assert rows[0][1:] == labels
    assert [row[0] for row in rows[1:]] == labels
    assert np.array_equal(matrix, np.asarray([row[1:] for row in rows[1:]], dtype=int))
    assert matrix.shape == (18, 18) and matrix.sum() == count and np.trace(matrix) == correct
    assert 'อะไร' in labels and 'neutral' not in labels and 'unknown' not in labels
    assert np.isclose(correct / count, data['aggregate']['accuracy'])

    fig, ax = plt.subplots(figsize=(15, 13), dpi=100)
    fig.patch.set_facecolor('white')
    fig.subplots_adjust(left=0.115, right=0.975, top=0.87, bottom=0.15)
    ax.imshow(matrix, cmap='Blues', vmin=0, vmax=matrix.max(), interpolation='nearest', aspect='auto')
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha='right', rotation_mode='anchor', fontproperties=FONT, fontsize=11)
    ax.set_yticks(range(len(labels)), labels, fontproperties=FONT, fontsize=11)
    ax.tick_params(axis='both', length=0, pad=8)
    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        if tick.get_text() == 'อะไร':
            tick.set_fontproperties(BOLD)
            tick.set_fontsize(11)
    ax.set_xlabel('ค่าที่โมเดลทำนาย', fontproperties=FONT, fontsize=13, labelpad=13)
    ax.set_ylabel('ค่าจริง', fontproperties=FONT, fontsize=13, labelpad=13)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for (row, col), value in np.ndenumerate(matrix):
        ax.text(col, row, str(value), ha='center', va='center', fontsize=10,
                color='white' if value > matrix.max() * 0.55 else '#253447')

    fig.text(0.54, 0.963, 'HandVox Confusion Matrix — 18 คำ (เพิ่มท่า “อะไร”)',
             ha='center', fontproperties=BOLD, fontsize=19, color='#182c40')
    fig.text(0.54, 0.928, subtitle, ha='center', fontproperties=FONT, fontsize=14)
    fig.text(0.54, 0.898,
             f"{count:,} คลิป | จำแนกถูก {correct:,} คลิป | Accuracy {correct / count * 100:.2f}% | Macro F1 {data['aggregate']['macro_f1'] * 100:.2f}%",
             ha='center', fontproperties=FONT, fontsize=12, color='#405065')
    fig.text(0.54, 0.047, note, ha='center', fontproperties=FONT, fontsize=11, color='#405065')
    fig.text(0.54, 0.023, 'ผลทดลอง 28 กันยายน 2569 • ตัวเลขในช่องคือจำนวนคลิป • ใช้คำทำนายโดยตรงของโมเดล',
             ha='center', fontproperties=FONT, fontsize=10, color='#526274')
    output_path = OUTPUT / filename
    fig.savefig(output_path, dpi=300, facecolor='white', metadata={
        'Title': f'HandVox 18-word confusion matrix: {subtitle}',
        'Description': f'Source: {metrics_path.relative_to(ROOT)}; rows=actual; columns=predicted; entries=clip counts.',
    })
    plt.close(fig)
    audit.append({
        'output': str(output_path), 'source': str(metrics_path),
        'source_sha256': hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
        'matrix_matches_csv': True, 'classes': len(labels),
        'clips': int(matrix.sum()), 'correct': int(np.trace(matrix)),
        'resolution': [4500, 3900], 'dpi': 300,
    })

(Path(__file__).resolve().parent / 'confusion_figures_audit.json').write_text(
    json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print('Created 2 PNG figures at 300 DPI; both matrices match source CSV and JSON.')
