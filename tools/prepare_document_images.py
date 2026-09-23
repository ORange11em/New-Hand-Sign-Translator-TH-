"""Extract traceable, unretouched documentation stills from existing previews."""
from pathlib import Path
import sys, json, collections, shutil, html, math
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / '.venv/Lib/site-packages'))
import cv2
from PIL import Image, ImageDraw, ImageFont

OUT = ROOT / 'ผลลัพธ์เอกสาร/ชุดรูปประกอบเอกสาร_01_02_03'
FONT = 'C:/Windows/Fonts/tahoma.ttf'
CATEGORIES = {
    '01_การทักทายและมารยาท': ['สวัสดี', 'ขอโทษ', 'ไม่เป็นไร', 'ขอบคุณ'],
    '02_การตอบรับและความเข้าใจ': ['ใช่', 'ไม่ใช่', 'เข้าใจ', 'ไม่เข้าใจ'],
    '03_ความต้องการในชีวิตประจำวัน': ['ต้องการ', 'น้ำ', 'กิน', 'ห้องน้ำ'],
    '04_การขอความช่วยเหลือ': ['ช่วยด้วย', 'เจ็บ', 'หมอ'],
    '05_การหยุดและปฏิเสธ': ['หยุด', 'ไม่ต้อง'],
    '06_สถานะพื้นฐาน': ['neutral', 'unknown'],
}
ORDER = [g for gs in CATEGORIES.values() for g in gs]
CAT = {g:c for c,gs in CATEGORIES.items() for g in gs}
# Visual review: prefer a complete visible pose over a sharper transition frame.
REVIEWED = {('person_02','ขอโทษ'): ('ea809785',20), ('person_02','ไม่ใช่'): ('7171c',21)}

def save(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(path)

def read_frames(path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok: break
        frames.append(frame)
    cap.release()
    return frames, fps

def score(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h,w = gray.shape
    return float(cv2.Laplacian(gray[h//5:9*h//10,w//5:4*w//5], cv2.CV_64F).var())

def sheet(items, title, destination, cols=4):
    cw,ch = 336,238
    canvas = Image.new('RGB', (cols*cw+32, math.ceil(len(items)/cols)*ch+86), 'white')
    draw = ImageDraw.Draw(canvas)
    draw.text((16,16), title, font=ImageFont.truetype(FONT,26), fill='#172033')
    for i,(label,path) in enumerate(items):
        x,y = 16+(i%cols)*cw,70+(i//cols)*ch
        im=Image.open(path); im.thumbnail((320,180)); canvas.paste(im,(x,y))
        draw.text((x,y+184),label,font=ImageFont.truetype(FONT,18),fill='#172033')
    destination.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(destination)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    groups=collections.defaultdict(list)
    for dataset in ['dataset_v2','dataset_external_v2']:
        rows=[json.loads(line) for line in (ROOT/dataset/'metadata.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        superseded={r['supersedes_clip_id'] for r in rows if r.get('supersedes_clip_id') and r.get('quality')!='rejected'}
        for r in rows:
            if r['signer_id'] not in ['person_01','person_02','person_03']: continue
            if r['quality']=='rejected' or r['clip_id'] in superseded: continue
            if not r.get('preview_file') or not (ROOT/dataset/r['preview_file']).exists(): continue
            groups[r['signer_id'],r['gesture_name']].append(dict(r,dataset=dataset))
    manifest=[]
    for person in ['person_01','person_02','person_03']:
        for gesture in ORDER:
            candidates=groups[person,gesture]
            accepted=[r for r in candidates if r['quality']=='accepted']
            candidates=accepted or candidates
            reviewed=REVIEWED.get((person,gesture))
            if reviewed:
                candidates=[r for r in candidates if r['clip_id'].startswith(reviewed[0])]
            best=None
            for r in candidates:
                frames,fps=read_frames(ROOT/r['dataset']/r['preview_file'])
                if len(frames)<3: continue
                # Avoid the boundaries and compare sharpness in the central body region.
                mids=list(range(max(1,int(len(frames)*.3)),max(2,int(len(frames)*.75))))
                fi=max(mids,key=lambda i:score(frames[i]))
                if reviewed: fi=reviewed[1]
                candidate=(score(frames[fi]),r,frames,fps,fi)
                if best is None or candidate[0]>best[0]: best=candidate
            if best is None: raise RuntimeError(f'Missing usable preview: {person}/{gesture}')
            sharp,r,frames,fps,fi=best
            number=ORDER.index(gesture)+1
            basename=f'{number:02d}_{gesture}_{person}'
            folder=OUT/'01_รูปท่าแยกตามบุคคล'/person/f'{number:02d}_{gesture}'
            main_path=folder/f'{basename}_ภาพหลัก.png'
            save(frames[fi],main_path)
            indices=[round((len(frames)-1)*f) for f in (.15,.5,.85)]
            phase_paths=[]
            for k,idx in enumerate(indices,1):
                path=folder/f'{basename}_ช่วง{k:02d}.png'; save(frames[idx],path); phase_paths.append(path)
            w,h=frames[0].shape[1],frames[0].shape[0]
            strip=Image.new('RGB',(w*3,h+84),'white'); d=ImageDraw.Draw(strip)
            for k,path in enumerate(phase_paths):
                strip.paste(Image.open(path),(k*w,0))
                d.text((k*w+16,h+10),f'ช่วง {k+1:02d} · เฟรม {indices[k]+1}',font=ImageFont.truetype(FONT,22),fill='#172033')
            d.text((16,h+47),f'{gesture} | {person} | คลิป {r["clip_id"][:8]}',font=ImageFont.truetype(FONT,20),fill='#172033')
            strip_path=folder/f'{basename}_ภาพลำดับ.png'; strip.save(strip_path)
            category_folder=OUT/'02_รูปท่าแยกตามหมวด'/CAT[gesture]/gesture
            category_folder.mkdir(parents=True,exist_ok=True)
            for path in [main_path,strip_path]: shutil.copy2(path,category_folder/path.name)
            record={**r,'category':CAT[gesture],'image':str(main_path.relative_to(OUT)).replace('\\','/'),'sequence_image':str(strip_path.relative_to(OUT)).replace('\\','/'),'main_frame_index_zero_based':fi,'phase_frame_indices_zero_based':indices,'main_time_seconds':round(fi/fps,4) if fps else None,'fps':fps,'decoded_frames':len(frames),'width':w,'height':h,'sharpness_score':round(sharp,2),'source_video':f'{r["dataset"]}/{r["preview_file"]}'}
            manifest.append(record)
            if reviewed: record['visual_review']='เลือกคลิป/เฟรมที่เห็นท่าชัดหลังตรวจภาพจริง'
            print(f'{person}: {gesture} [{r["quality"]}]',flush=True)
    (OUT/'รายการภาพและแหล่งที่มา.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    for person in ['person_01','person_02','person_03']:
        sheet([(f'{ORDER.index(r["gesture_name"])+1:02d} {r["gesture_name"]}',OUT/r['image']) for r in manifest if r['signer_id']==person],f'HandVox · {person} · ภาพท่าทั้งหมด',OUT/'04_ภาพรวมสำหรับเลือกใช้'/f'{person}_รวมทุกท่า.png')
    cards=[]
    for r in manifest:
        caption=f'ท่า{r["gesture_name"]} โดยผู้ทำท่า {r["signer_id"][-2:]}'
        cards.append(f'<article data-search="{r["signer_id"]} {r["gesture_name"]} {r["category"]}"><a href="{r["image"]}"><img loading="lazy" src="{r["image"]}" alt="{caption}"></a><h3>{caption}</h3><p>{r["category"][3:]} · {r["width"]}×{r["height"]} px</p><a href="{r["image"]}">ภาพเดี่ยว PNG</a> · <a href="{r["sequence_image"]}">ภาพลำดับ 3 ช่วง</a></article>')
    page='''<!doctype html><html lang="th"><meta charset="utf-8"><title>รูปประกอบเอกสาร HandVox</title><style>body{font:16px Tahoma,sans-serif;background:#f3f5f8;color:#172033;margin:32px}header{max-width:1000px}input{padding:12px;font:inherit;width:350px;max-width:85%;margin:12px 0 24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}article{background:white;padding:16px;border-radius:10px}img{width:100%}h3{font-size:18px}a{color:#165ec0}p{line-height:1.8}article[hidden]{display:none}</style><header><h1>รูปประกอบเอกสาร HandVox</h1><p>ผู้ทำท่า 01–03 · 17 ท่าคำศัพท์ + neutral และ unknown · ภาพจากคลิปจริง ขนาดต้นฉบับ<br>ภาพนี้เป็นตัวอย่างจากข้อมูลที่ถ่ายไว้ ชื่อท่าอ้างอิงป้ายกำกับใน Dataset ไม่ใช่การรับรองความถูกต้องของภาษามือ</p><p><a href="03_รูปโปรแกรม/">เปิดโฟลเดอร์รูปโปรแกรม</a> · <a href="04_ภาพรวมสำหรับเลือกใช้/">เปิดภาพรวมแต่ละคน</a></p><input id="q" placeholder="ค้นหาชื่อท่า หมวด หรือ person_01"></header><main>'''+''.join(cards)+'''</main><script>document.querySelector('#q').oninput=e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('article').forEach(x=>x.hidden=!x.dataset.search.toLowerCase().includes(q))}</script></html>'''
    (OUT/'เปิดดูรูปทั้งหมด.html').write_text(page,encoding='utf-8')
    (OUT/'อ่านก่อนใช้.txt').write_text('''ชุดรูปประกอบเอกสาร HandVox — ผู้ทำท่า 01, 02, 03

01_รูปท่าแยกตามบุคคล: แต่ละคนมีครบ 19 หมวด (17 ท่าคำศัพท์ และ neutral/unknown)
แต่ละหมวดมีภาพหลัก PNG, ภาพช่วง 01/02/03 และภาพลำดับ 3 ช่วง
02_รูปท่าแยกตามหมวด: สำเนาภาพหลักและภาพลำดับ จัดตามความหมายของท่า 6 หมวด
03_รูปโปรแกรม: ภาพหน้าจอจริงของโปรแกรม แยกจากภาพท่าทาง
04_ภาพรวมสำหรับเลือกใช้: ภาพรวม 19 หมวดของแต่ละคน
เปิดดูรูปทั้งหมด.html: ดับเบิลคลิกเพื่อค้นหาและเลือกภาพ
รายการภาพและแหล่งที่มา.json: คลิปต้นทาง เฟรม เวลา สถานะการตรวจคุณภาพ และขนาดภาพ

หลักการคัดภาพ: ใช้คลิปที่มีไฟล์วิดีโอ ไม่ใช้คลิป rejected หรือคลิปที่ถูกถ่ายทดแทนแล้ว
เลือก accepted ก่อน pending และเปรียบเทียบความคมชัดบริเวณกลางตัวในช่วงกลางคลิป
ภาพลำดับใช้ตำแหน่งประมาณ 15%, 50%, 85% ของคลิปเดียวกัน เพื่อเห็นการเคลื่อนไหว
ช่วง 01/02/03 เป็นลำดับภาพภายในคลิป ไม่ใช่รหัสบุคคล
รูปเดี่ยวคงพิกเซลต้นฉบับ ไม่แต่งท่าทาง ไม่สร้างภาพบุคคลใหม่ ไม่ขยายความละเอียดเทียม
ป้ายชื่อท่าอ้างอิงข้อมูลที่บันทึกไว้ ภาพไม่ใช่การรับรองความถูกต้องตามมาตรฐานภาษามือ
หมวด neutral และ unknown เป็นข้อมูลพื้นฐาน/ท่าที่ไม่รู้จัก ให้แยกจาก 17 คำศัพท์ในรายงาน
ภาพในหมวด 02 เป็นสำเนาเพื่อความสะดวก ไม่ใช่ตัวอย่างเพิ่ม
''',encoding='utf-8-sig')
    print(f'COMPLETE: {len(manifest)} person/gesture combinations -> {OUT}',flush=True)

if __name__=='__main__': main()
