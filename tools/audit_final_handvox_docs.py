from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ผลลัพธ์เอกสาร"
EXPECTED_PLACEHOLDERS = {1: 0, 2: 2, 3: 2, 4: 2, 5: 0}
STALE_TERMS = ("4,500", "15 ป้ายกำกับ", "90 คลิป", "99.11", "90.78")


def document_text(document: Document) -> str:
    chunks = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            chunks.extend(cell.text for cell in row.cells)
    return "\n".join(chunks)


def main() -> None:
    failed = False
    for chapter in range(1, 6):
        path = OUTPUT / f"บทที่ {chapter}_ฉบับปรับปรุง_HandVox.docx"
        document = Document(path)
        text = document_text(document)
        placeholder_count = text.count("[เว้นพื้นที่สำหรับภาพประกอบ]")
        stale = [term for term in STALE_TERMS if term in text]
        section = document.sections[0]
        a4 = abs(section.page_width.mm - 210) < 1 and abs(section.page_height.mm - 297) < 1
        body_children = list(document.element.body)
        table_captions = []
        captions_below = True
        for index, child in enumerate(body_children):
            if child.tag != qn("w:p"):
                continue
            child_text = "".join(child.itertext()).strip()
            if not child_text.startswith("ตารางที่ "):
                continue
            table_captions.append(child_text)
            captions_below = captions_below and index > 0 and body_children[index - 1].tag == qn("w:tbl")
        ok = (
            placeholder_count == EXPECTED_PLACEHOLDERS[chapter]
            and not stale
            and a4
            and len(table_captions) == len(document.tables)
            and captions_below
        )
        failed = failed or not ok
        print(
            f"chapter={chapter} ok={ok} placeholders={placeholder_count} "
            f"tables={len(document.tables)} paragraphs={len(document.paragraphs)} "
            f"table_captions={len(table_captions)} captions_below={captions_below} "
            f"a4={a4} stale={stale}"
        )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
