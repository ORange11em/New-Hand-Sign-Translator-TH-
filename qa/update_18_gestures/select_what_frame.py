"""Make a contact sheet from accepted video previews of the gesture 'อะไร'."""
from pathlib import Path
import json

import cv2
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / 'dataset_v2'
WORK = Path(__file__).resolve().parent
records = [json.loads(line) for line in (DATASET / 'metadata.jsonl').read_text(encoding='utf-8').splitlines()]
records = [r for r in records if r['gesture_name'] == 'อะไร' and r['quality'] == 'accepted' and r.get('preview_file')]
records = [r for signer in ('person_01', 'person_02') for r in records if r['signer_id'] == signer][:4]
assert len(records) == 4
font = ImageFont.truetype('C:/Windows/Fonts/tahoma.ttf', 20)
frames = []
for record in sorted(records, key=lambda r: r['clip_id']):
    cap = cv2.VideoCapture(str(DATASET / record['preview_file']))
    assert cap.isOpened()
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    assert count >= 24
    for at in [4, 11, 18, 25]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, at)
        ok, frame = cap.read()
        assert ok
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail((400, 300))
        frames.append((record, at, img.copy()))
    cap.release()

w, h = 430, 340
sheet = Image.new('RGB', (w * 4, h * 4), 'white')
draw = ImageDraw.Draw(sheet)
for i, (record, at, img) in enumerate(frames):
    x, y = (i % 4) * w, (i // 4) * h
    sheet.paste(img, (x + (w - img.width) // 2, y + 8))
    draw.text((x + 15, y + 310), f"{record['clip_id'][:8]} | frame {at}", fill='#253447', font=font)
sheet.save(WORK / 'what_contact_sheet.png')
print('Contact sheet saved; all 4 clips accepted, 16 frames inspected.')
