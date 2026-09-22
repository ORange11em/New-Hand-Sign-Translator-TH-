"""Restore the latest spaced HandVox chapters and standardize bilingual terms.

The current user-edited copies lost many Thai word/phrase spaces.  The project
builder still contains the same latest content with the intended spacing, page
layout, page numbering, figures, and tables.  Rebuilding from that source is
therefore safer than trying to infer every missing space from the damaged text.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.document import Document as _Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph

import build_handvox_chapters as builder


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "ผลลัพธ์เอกสาร"
REBUILD_DIR = ROOT / "tmp" / "chapter_spacing_rebuild"
PAGE_STARTS = {1: 1, 2: 6, 3: 37}


def iter_block_items(parent: _Document | _Cell):
    """Yield paragraphs and tables in their XML order, including table cells."""

    parent_element = parent.element.body if isinstance(parent, _Document) else parent._tc
    for child in parent_element.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            table = Table(child, parent)
            yield table
            for row in table.rows:
                for cell in row.cells:
                    yield from iter_block_items(cell)


def all_paragraphs(doc: _Document):
    for item in iter_block_items(doc):
        if isinstance(item, Paragraph):
            yield item
    for section in doc.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            yield from header.paragraphs
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            yield from footer.paragraphs


def set_page_number_start(document: _Document, start: int) -> None:
    """Keep chapter page numbers continuous while hiding the opening-page number."""

    section_properties = document.sections[0]._sectPr
    page_number_type = section_properties.find(qn("w:pgNumType"))
    if page_number_type is None:
        page_number_type = OxmlElement("w:pgNumType")
        section_properties.append(page_number_type)
    page_number_type.set(qn("w:start"), str(start))


def replace_text(doc: _Document, old: str, new: str, *, limit: int | None = None) -> int:
    """Replace text inside runs without flattening paragraph formatting."""

    changed = 0
    for paragraph in all_paragraphs(doc):
        for run in paragraph.runs:
            if old not in run.text:
                continue
            remaining = None if limit is None else max(limit - changed, 0)
            if remaining == 0:
                return changed
            occurrences = run.text.count(old)
            count = occurrences if remaining is None else min(occurrences, remaining)
            run.text = run.text.replace(old, new, count)
            changed += count
            if limit is not None and changed >= limit:
                return changed
    return changed


def set_thai_language_metadata(doc: _Document) -> None:
    """Tell Word to use Thai dictionary line breaking in all visible text."""

    for paragraph in all_paragraphs(doc):
        for run in paragraph.runs:
            properties = run._r.get_or_add_rPr()
            lang = properties.find(qn("w:lang"))
            if lang is None:
                lang = OxmlElement("w:lang")
                properties.append(lang)
            for attr in ("val", "eastAsia", "bidi"):
                lang.set(qn(f"w:{attr}"), "th-TH")

    for style in doc.styles:
        if not hasattr(style, "_element") or style._element.rPr is None:
            continue
        lang = style._element.rPr.find(qn("w:lang"))
        if lang is None:
            lang = OxmlElement("w:lang")
            style._element.rPr.append(lang)
        for attr in ("val", "eastAsia", "bidi"):
            lang.set(qn(f"w:{attr}"), "th-TH")


def apply_replacements(doc: _Document, replacements: list[tuple[str, str, int | None]]) -> None:
    missing: list[str] = []
    for old, new, limit in replacements:
        count = replace_text(doc, old, new, limit=limit)
        if count == 0:
            missing.append(old)
    if missing:
        raise RuntimeError("Target text was not found: " + " | ".join(missing))


CHAPTER_1_REPLACEMENTS = [
    (
        "เทคโนโลยีการมองเห็นด้วยคอมพิวเตอร์มาช่วย",
        "เทคโนโลยีการมองเห็นด้วยคอมพิวเตอร์ (Computer Vision) มาช่วย",
        1,
    ),
    (
        "และใช้ Support Vector Machine จำแนก",
        "และใช้เครื่องเวกเตอร์สนับสนุน (Support Vector Machine: SVM) จำแนก",
        1,
    ),
    (
        "ด้วย Accuracy, Precision, Recall, F1-score และ Confusion Matrix",
        "ด้วยค่าความถูกต้อง (Accuracy), ค่าความแม่นยำ (Precision), "
        "ค่าความระลึก (Recall), คะแนนเอฟวัน (F1-score) และเมทริกซ์ความสับสน "
        "(Confusion Matrix)",
        1,
    ),
    (
        "ข้อมูลแบบ stratified holdout 80:20",
        "ข้อมูลแบบกันไว้โดยคงสัดส่วนคลาส (stratified holdout) อัตรา 80:20",
        1,
    ),
    (
        "การประยุกต์ใช้ Computer Vision และ Machine Learning",
        "การประยุกต์ใช้การมองเห็นด้วยคอมพิวเตอร์ (Computer Vision) "
        "และการเรียนรู้ของเครื่อง (Machine Learning)",
        1,
    ),
    (
        "1.7.8 Support Vector Machine (SVM) และ RBF Kernel",
        "1.7.8 เครื่องเวกเตอร์สนับสนุน (Support Vector Machine: SVM) "
        "และเคอร์เนลอาร์บีเอฟ (RBF Kernel)",
        1,
    ),
    (
        "1.7.10 Text-to-Speech (TTS)",
        "1.7.10 การแปลงข้อความเป็นเสียงพูด (Text-to-Speech: TTS)",
        1,
    ),
    (
        "แบบจำลองที่สามารถเพิ่มคำศัพท์ได้ในภายหลัง",
        "แบบจำลองที่เพิ่มคำศัพท์ได้ภายหลัง",
        1,
    ),
]


CHAPTER_2_REPLACEMENTS = [
    (
        "2.2 การมองเห็นด้วยคอมพิวเตอร์",
        "2.2 การมองเห็นด้วยคอมพิวเตอร์ (Computer Vision)",
        None,
    ),
    (
        "2.5 Support Vector Machine",
        "2.5 เครื่องเวกเตอร์สนับสนุน (Support Vector Machine: SVM)",
        None,
    ),
    (
        "Sign Language Recognition ออกจาก Sign Language Translation",
        "การรู้จำภาษามือ (Sign Language Recognition) ออกจากการแปลภาษามือ "
        "(Sign Language Translation)",
        1,
    ),
    ("คลาสภายใน neutral", "คลาสภายในเป็นกลาง (neutral)", 1),
    (
        "ควรตรวจ Confusion Matrix เป็นพิเศษ",
        "ควรตรวจเมทริกซ์ความสับสน (Confusion Matrix) เป็นพิเศษ",
        1,
    ),
    (
        "ต้องมี Recall สูงกว่าคำทั่วไป",
        "ต้องมีค่าความระลึก (Recall) สูงกว่าคำทั่วไป",
        1,
    ),
    (
        "จุดสำคัญหรือ landmark เป็นพิกัด",
        "จุดสำคัญ (landmark) เป็นพิกัด",
        1,
    ),
    ("วิดีโอตัวอย่างหรือ metadata", "วิดีโอตัวอย่างหรือข้อมูลกำกับ (metadata)", 1),
    (
        "Support Vector Machine หรือ SVM เป็นวิธี",
        "เครื่องเวกเตอร์สนับสนุน (Support Vector Machine: SVM) เป็นวิธี",
        1,
    ),
    (
        "2.5.3 Kernel และ RBF",
        "2.5.3 เคอร์เนล (Kernel) และฟังก์ชันฐานรัศมี "
        "(Radial Basis Function: RBF)",
        1,
    ),
    (
        "RBF kernel ให้ความคล้าย",
        "เคอร์เนลฟังก์ชันฐานรัศมี (Radial Basis Function: RBF) ให้ความคล้าย",
        1,
    ),
    (
        "2.6.3 การแบ่งแบบ Stratified",
        "2.6.3 การแบ่งแบบคงสัดส่วนคลาส (Stratified)",
        1,
    ),
    (
        "การแบ่งแบบ stratified รักษาสัดส่วน",
        "การแบ่งแบบคงสัดส่วนคลาส (stratified) รักษาสัดส่วน",
        1,
    ),
    (
        "2.6.5 Leave-One-Signer-Out",
        "2.6.5 การเว้นผู้ทำท่าหนึ่งคนออก (Leave-One-Signer-Out)",
        1,
    ),
    (
        "Leave-One-Signer-Out สร้างจำนวน fold",
        "การเว้นผู้ทำท่าหนึ่งคนออก (Leave-One-Signer-Out) สร้างจำนวนรอบ "
        "(fold)",
        1,
    ),
    ("External test", "ชุดทดสอบภายนอก (External test)", 1),
    (
        "2.7.1 Confusion Matrix",
        "2.7.1 เมทริกซ์ความสับสน (Confusion Matrix)",
        1,
    ),
    (
        "Confusion Matrix จัดแถว",
        "เมทริกซ์ความสับสน (Confusion Matrix) จัดแถว",
        1,
    ),
    ("2.7.2 Accuracy", "2.7.2 ค่าความถูกต้อง (Accuracy)", 1),
    (
        "Accuracy คือจำนวนตัวอย่าง",
        "ค่าความถูกต้อง (Accuracy) คือจำนวนตัวอย่าง",
        1,
    ),
    (
        "2.7.3 Precision Recall และ F1-score",
        "2.7.3 ค่าความแม่นยำ (Precision) ค่าความระลึก (Recall) "
        "และคะแนนเอฟวัน (F1-score)",
        1,
    ),
    (
        "Precision ของคลาสหนึ่งวัด",
        "ค่าความแม่นยำ (Precision) ของคลาสหนึ่งวัด",
        1,
    ),
    ("Recall วัดว่าตัวอย่างจริง", "ค่าความระลึก (Recall) วัดว่าตัวอย่างจริง", 1),
    (
        "F1-score เป็นค่าเฉลี่ยฮาร์มอนิก",
        "คะแนนเอฟวัน (F1-score) เป็นค่าเฉลี่ยฮาร์มอนิก",
        1,
    ),
    (
        "2.7.4 ค่าเฉลี่ย Macro และ Weighted",
        "2.7.4 ค่าเฉลี่ยมหภาค (Macro average) และค่าเฉลี่ยถ่วงน้ำหนัก "
        "(Weighted average)",
        1,
    ),
    (
        "Macro average คำนวณ",
        "ค่าเฉลี่ยมหภาค (Macro average) คำนวณ",
        1,
    ),
    (
        "Weighted average ให้น้ำหนัก",
        "ค่าเฉลี่ยถ่วงน้ำหนัก (Weighted average) ให้น้ำหนัก",
        1,
    ),
    (
        "การรายงานแยก offline กับ real-time",
        "การรายงานแยกแบบออฟไลน์ (offline) กับแบบเวลาจริง (real-time)",
        1,
    ),
    (
        "true positive, false positive และ false negative",
        "ผลบวกจริง (true positive), ผลบวกลวง (false positive) "
        "และผลลบลวง (false negative)",
        1,
    ),
    (
        "สถานะ IDLE, CANDIDATE, CONFIRMED และ COOLDOWN",
        "สถานะว่าง (IDLE), สถานะรอยืนยัน (CANDIDATE), "
        "สถานะยืนยันแล้ว (CONFIRMED) และสถานะพักก่อนรับคำใหม่ (COOLDOWN)",
        1,
    ),
    (
        "สถานะ CANDIDATE หรือ CONFIRMED",
        "สถานะรอยืนยัน (CANDIDATE) หรือสถานะยืนยันแล้ว (CONFIRMED)",
        1,
    ),
    (
        "2.8.5 Text-to-Speech",
        "2.8.5 การแปลงข้อความเป็นเสียงพูด (Text-to-Speech: TTS)",
        1,
    ),
    (
        "Text-to-Speech เปลี่ยนข้อความไทย",
        "การแปลงข้อความเป็นเสียงพูด (Text-to-Speech: TTS) เปลี่ยนข้อความไทย",
        1,
    ),
    (
        "ความเสี่ยง overfitting",
        "ความเสี่ยงต่อการเรียนรู้จดจำข้อมูลฝึกมากเกินไป (overfitting)",
        1,
    ),
    (
        "สร้าง external test",
        "สร้างชุดทดสอบภายนอก (external test)",
        1,
    ),
    ("neutral class", "คลาสเป็นกลาง (neutral class)", 1),
]


CHAPTER_3_REPLACEMENTS = [
    (
        "ใช้ Accuracy, Precision, Recall, F1-score และ Confusion Matrix",
        "ใช้ค่าความถูกต้อง (Accuracy), ค่าความแม่นยำ (Precision), "
        "ค่าความระลึก (Recall), คะแนนเอฟวัน (F1-score) และเมทริกซ์ความสับสน "
        "(Confusion Matrix)",
        1,
    ),
    ("ต้องเก็บ metadata ของผู้ทำท่า", "ต้องเก็บข้อมูลกำกับ (metadata) ของผู้ทำท่า", 1),
    (
        "เพื่อส่งให้ SVM จำแนก",
        "เพื่อส่งให้เครื่องเวกเตอร์สนับสนุน (Support Vector Machine: SVM) จำแนก",
        1,
    ),
    (
        "สถานะ accepted หรือ rejected",
        "สถานะยอมรับ (accepted) หรือปฏิเสธ (rejected)",
        1,
    ),
    (
        "ใช้ LabelEncoder แปลงชื่อท่าเป็นรหัส",
        "ใช้ตัวเข้ารหัสป้ายกำกับ (LabelEncoder) แปลงชื่อท่าเป็นรหัส",
        1,
    ),
    (
        "แบบ stratified 80:20 และใช้ random seed 42",
        "แบบคงสัดส่วนคลาส (stratified) อัตรา 80:20 และใช้เมล็ดสุ่ม "
        "(random seed) 42",
        1,
    ),
    (
        "แบบจำลองใช้ SVC แบบ RBF",
        "แบบจำลองใช้เครื่องเวกเตอร์สนับสนุนชนิดจำแนก "
        "(Support Vector Classifier: SVC) ร่วมกับเคอร์เนลฟังก์ชันฐานรัศมี "
        "(Radial Basis Function: RBF)",
        1,
    ),
    (
        "probability เป็น true และ class_weight เป็น balanced",
        "ความน่าจะเป็น (probability) เป็น true และน้ำหนักคลาส "
        "(class_weight) เป็น balanced",
        1,
    ),
    (
        "ให้เหมือนกันทั้งขณะเก็บข้อมูล ฝึกแบบจำลอง และทำนายแบบเวลาจริง",
        "ให้เหมือนกัน ทั้งขณะเก็บข้อมูล ฝึกแบบจำลอง และทำนายแบบเวลาจริง",
        1,
    ),
]


def build_and_edit() -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REBUILD_DIR.mkdir(parents=True, exist_ok=True)
    builder.OUTPUT = REBUILD_DIR

    source_paths = [
        builder.build_chapter_1_structured(),
        builder.build_chapter_2_structured(),
        builder.build_chapter_3_structured(),
    ]
    replacements = [
        CHAPTER_1_REPLACEMENTS,
        CHAPTER_2_REPLACEMENTS,
        CHAPTER_3_REPLACEMENTS,
    ]

    outputs: list[Path] = []
    for chapter_number, source_path, chapter_replacements in zip(
        (1, 2, 3), source_paths, replacements
    ):
        document = Document(source_path)
        apply_replacements(document, chapter_replacements)
        set_thai_language_metadata(document)
        set_page_number_start(document, PAGE_STARTS[chapter_number])
        document.core_properties.title = f"HandVox บทที่ {chapter_number}"
        document.core_properties.subject = "โครงงาน HandVox"
        destination = OUTPUT_DIR / f"บทที่ {chapter_number}.docx"
        document.save(destination)
        outputs.append(destination)

    return outputs


if __name__ == "__main__":
    for output in build_and_edit():
        print(output)
