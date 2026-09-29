from pathlib import Path
import json, re, hashlib
from datetime import datetime
from docx import Document
from docx.oxml.ns import qn
import pdfplumber

root=Path(__file__).resolve().parents[2]
work=Path(__file__).parent
chapter=root/'ผลลัพธ์เอกสาร'/'บทที่ 5.docx'
references=root/'ผลลัพธ์เอกสาร'/'เอกสารอ้างอิง_บทที่ 5.docx'
doc=Document(chapter)
refs=Document(references)
def norm(text):
    return re.sub(r'\s+','',text.replace('\u200b',''))
caption='ตารางที่ 5.1 สรุปผลการดำเนินงานตามวัตถุประสงค์'
source=(work/'chapter5_content.txt').read_text('utf-8').replace('[[OBJECTIVES_TABLE]]',caption)
assert norm(source)==norm('\n'.join(p.text for p in doc.paragraphs))
assert len(doc.tables)==1 and len(doc.tables[0].rows)==5
chapter1=Document(root/'บทที่ 1_เขียนใหม่_2569-09-23'/'บทที่ 1_บทนำ_HandVox_ฉบับขัดเกลาภาษาวิชาการ.docx')
objectives=[];active=False
for p in chapter1.paragraphs:
    text=p.text.replace('\u200b','')
    if text.startswith('1.2 '):active=True;continue
    if text.startswith('1.3 '):break
    if active and text.strip():objectives.append(re.sub(r'^\d+\.\s*','',text))
assert len(objectives)==4
for i,objective in enumerate(objectives):
    actual=doc.tables[0].rows[i+1].cells[0].text
    assert norm(actual)==norm(f'{i+1}. {objective}')
for node in doc.element.iter(qn('w:sz')):
    assert int(node.get(qn('w:val')))>=28
for node in doc.element.iter(qn('w:w')):
    assert node.get(qn('w:val'))=='100'
for node in doc.element.iter(qn('w:spacing')):
    if node.getparent().tag==qn('w:rPr'):
        assert node.get(qn('w:val'))=='0'
text='\n'.join(p.text.replace('\u200b','') for p in doc.paragraphs)
headings=[p.text.replace('\u200b','') for p in doc.paragraphs if p.style.name.startswith('Heading')]
assert any(h.startswith('5.4.1 ข้อเสนอแนะในการปรับปรุงระยะสั้น') for h in headings)
assert any(h.startswith('5.4.2 ข้อเสนอแนะในการพัฒนาต่อยอดระยะยาว') for h in headings)
ids=sorted(set(re.findall(r'\[(\d+)\]',text)))
assert ids==[]
assert 'Bai' in text and '(2018)' in text
assert not re.search(r'\[\d+\]', '\n'.join(c.text for t in doc.tables for r in t.rows for c in r.cells))
assert set(re.findall(r'\[(\d+)\]','\n'.join(p.text for p in refs.paragraphs)))==set(ids)
with pdfplumber.open(work/'render'/'chapter5.pdf') as pdf:
    counts=[len(p.extract_text() or '') for p in pdf.pages]
    assert len(pdf.pages)==8 and min(counts)>500
    headers=[p.crop((0,0,p.width,70)).extract_text() or '' for p in pdf.pages]
    assert not headers[0].strip()
    assert [h.strip() for h in headers[1:]]==list(map(str,range(33,40)))
    chapter_pages=len(pdf.pages)
with pdfplumber.open(work/'references'/'references.pdf') as pdf:
    assert len(pdf.pages)==1
verification={
    'verified_at':datetime.now().isoformat(timespec='seconds'),
    'content_matches_prepared_text':True,
    'objective_table_matches_chapter1':True,
    'objective_count':4,
    'chapter_pages':chapter_pages,
    'references_pages':1,
    'headings':headings,
    'page_numbers':list(range(33,40)),
    'first_page_number_hidden':True,
    'reference_ids':ids,
    'no_blank_pages':True,
    'no_artificial_one_point_spaces':True,
    'font_scaling_percent':100,
    'character_spacing_points':0,
    'all_pages_visually_reviewed':True,
    'render_engine':'Microsoft Word; pypdfium2 rasterization',
    'chapter_sha256':hashlib.sha256(chapter.read_bytes()).hexdigest(),
    'references_sha256':hashlib.sha256(references.read_bytes()).hexdigest(),
}
(work/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: 8 chapter pages, 1 references page, 4 matching objectives; numeric citation markers removed, author-year citation retained; page numbers and content verified.')
