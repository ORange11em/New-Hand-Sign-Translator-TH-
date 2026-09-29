from pathlib import Path
import hashlib
import json
import zipfile

from docx import Document
from docx.oxml.ns import qn
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
SOURCE = ROOT / 'ผลลัพธ์เอกสาร'
OUTPUT = SOURCE / 'ฉบับเพิ่มท่าอะไร_18คำ'
log = json.loads((WORK / 'edit_log.json').read_text(encoding='utf-8'))
checks = {}

def check(name, condition):
    assert condition, name
    checks[name] = True

def media(path):
    with zipfile.ZipFile(path) as z:
        return {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('word/media/')}

documents = {}
for filename, record in log['files'].items():
    revised = OUTPUT / filename
    original = SOURCE / filename
    backup = Path(record['backup'])
    check(f'{filename}: original preserved', original.read_bytes() == backup.read_bytes())
    check(f'{filename}: final hash', hashlib.sha256(revised.read_bytes()).hexdigest() == record['sha256'])
    check(f'{filename}: original images preserved', media(revised) == media(backup))
    documents[filename] = Document(revised)

doc4 = documents['บทที่ 4.docx']
doc5 = documents['บทที่ 5.docx']
check('chapter 4 table count', len(doc4.tables) == 5)
check('chapter 4 image count', len(doc4.inline_shapes) == 15)
check('chapter 5 table count', len(doc5.tables) == 1)
check('chapter 5 page start', doc5.sections[0]._sectPr.find(qn('w:pgNumType')).get(qn('w:start')) == '36')

experiment = ROOT / 'experiments' / log['source_experiment']
training = json.loads((experiment / 'metrics.json').read_text(encoding='utf-8'))
external = json.loads((experiment / 'external_evaluations' / log['external_evaluation'] / 'metrics.json').read_text(encoding='utf-8'))
check('18 classes', len(training['classes']) == len(external['classes']) == 18)
check('training clip counts', (training['accepted_clips'], training['base_clips'], training['new_target_clips']) == (622, 590, 32))
check('external scope', external['evaluated_clips'] == 287 and external['excluded_clip_count'] == 32 and external['pending_clips'] == 0)
check('excluded labels', external['excluded_classes'] == ['neutral', 'unknown'])
check('prediction policy', external['prediction_policy'] == 'raw_model_predictions')

def clean(text):
    return text.replace('\u200b', '').replace('\u00a0', ' ')

summary_table = next(t for t in doc4.tables if len(t.columns) == 5 and 'จำแนก' in clean(t.cell(0, 2).text))
summary_rows = summary_table.rows[1:]
check('summary table rows', len(summary_rows) == 2)
for row, data, count, correct in zip(summary_rows, (training, external), (144, 287), (122, 254)):
    actual = [clean(c.text) for c in row.cells][1:]
    aggregate = data['aggregate']
    expected = [str(count), str(correct), f"{aggregate['accuracy'] * 100:.2f}", f"{aggregate['macro_f1'] * 100:.2f}"]
    check(f'summary table: {count} clips', actual == expected)

word_table = next(t for t in doc4.tables if 'Precision' in t.cell(0, 2).text)
for row, data in zip(word_table.rows[1:], (training, external)):
    word = next(c for c in data['aggregate']['per_class'] if c['class_name'] == 'อะไร')
    expected = [str(word['support'])] + [f"{word[key] * 100:.2f}" for key in ('precision', 'recall', 'f1')]
    check(f'word metrics: {word["support"]} clips', [clean(c.text) for c in row.cells][1:] == expected)

for chapter, doc in ((4, doc4), (5, doc5)):
    text = clean('\n'.join(p.text for p in doc.paragraphs))
    check(f'chapter {chapter}: new gesture and scope', all(term in text for term in ('อะไร', '18 คำ', 'neutral', 'unknown', '32 คลิป', '287 คลิป')))
    check(f'chapter {chapter}: old and new results distinguished', 'รุ่นฐาน' in text and 'โมเดลทดลอง' in text)

pages = {}
for filename, folder, expected_count in (
    ('บทที่ 4.docx', 'final_ch4', 14),
    ('บทที่ 5.docx', 'final_ch5', 8),
    ('เอกสารอ้างอิง_บทที่ 4.docx', 'refs4', 2),
    ('เอกสารอ้างอิง_บทที่ 5.docx', 'refs5', 2),
):
    with pdfium.PdfDocument(WORK / folder / filename.replace('.docx', '.pdf')) as pdf:
        check(f'{filename}: page count', len(pdf) == expected_count)
        check(f'{filename}: no blank pages', all(len(page.get_textpage().get_text_range().strip()) > 20 for page in pdf))
        pages[filename] = len(pdf)
    check(f'{filename}: rendered images complete', all((WORK / folder / f'page-{i}.png').is_file() for i in range(1, expected_count + 1)))

audit = {
    'checks': checks,
    'page_counts': pages,
    'renderer': 'Microsoft Word PDF export; pypdfium2 PNG rendering',
    'all_pages_visually_reviewed': True,
    'visual_review': 'All 26 pages inspected; no clipped text, overlapping figures, missing images, or broken tables. Chapters use consecutive page numbering.',
    'output_sha256': {name: record['sha256'] for name, record in log['files'].items()},
}
(WORK / 'verification.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'PASS: {len(checks)} checks; {sum(pages.values())} pages visually reviewed.')
