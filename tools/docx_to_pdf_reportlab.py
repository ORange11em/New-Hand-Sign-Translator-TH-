"""Create readable, locally rendered PDFs from the HandVox chapter DOCX files.

This converter preserves document order, headings, Thai text, tables, inline
images, first-page numbering behavior, and the source chapter's start number.
It is intentionally limited to the formatting used by these project chapters.
"""

from __future__ import annotations

import argparse
import html
import re
import zipfile
from pathlib import Path

from docx import Document
from docx.document import Document as _Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import Image, LongTable, PageBreak, Paragraph as RLParagraph, SimpleDocTemplate, Spacer, TableStyle


THAI_FONT = Path(r"C:\Users\Ult_Orange\AppData\Local\Microsoft\Windows\Fonts\THSarabunNew.ttf")
BLIP_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def iter_blocks(parent: _Document):
    for child in parent.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def points(length, fallback: float) -> float:
    return float(length.pt) if length is not None else fallback


def start_page_number(docx_path: Path) -> int:
    with zipfile.ZipFile(docx_path) as package:
        xml = package.read("word/document.xml").decode("utf-8")
    match = re.search(r'w:pgNumType[^>]*w:start="(\d+)"', xml)
    return int(match.group(1)) if match else 1


def has_title_page(docx_path: Path) -> bool:
    with zipfile.ZipFile(docx_path) as package:
        return "w:titlePg" in package.read("word/document.xml").decode("utf-8")


def register_thai_font() -> None:
    if not THAI_FONT.exists():
        raise FileNotFoundError(f"ไม่พบฟอนต์ TH Sarabun New: {THAI_FONT}")
    pdfmetrics.registerFont(TTFont("THSarabunNew", str(THAI_FONT)))
    registerFontFamily(
        "THSarabunNew",
        normal="THSarabunNew",
        bold="THSarabunNew",
        italic="THSarabunNew",
        boldItalic="THSarabunNew",
    )


def run_markup(paragraph: Paragraph) -> str:
    parts: list[str] = []
    for run in paragraph.runs:
        text = html.escape(run.text).replace("\n", "<br/>").replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
        if not text:
            continue
        if run.bold:
            text = f"<b>{text}</b>"
        if run.italic:
            text = f"<i>{text}</i>"
        if run.underline:
            text = f"<u>{text}</u>"
        parts.append(text)
    return "".join(parts) or "&nbsp;"


def paragraph_style(paragraph: Paragraph, styles, body_size: float) -> ParagraphStyle:
    style_name = paragraph.style.name
    text = paragraph.text.strip()
    alignment = paragraph.alignment
    size = body_size
    bold = False
    space_before = 0
    space_after = 2
    first_indent = 0
    left_indent = 0
    if paragraph.paragraph_format.first_line_indent is not None:
        first_indent = points(paragraph.paragraph_format.first_line_indent, 0)
    if paragraph.paragraph_format.left_indent is not None:
        left_indent = points(paragraph.paragraph_format.left_indent, 0)

    if style_name == "Heading 1":
        size, bold, space_before, space_after, first_indent, left_indent = 16, True, 10, 3, 0, 0
    elif style_name == "Heading 2":
        size, bold, space_before, space_after, first_indent, left_indent = 16, True, 8, 2, 0, 0
    elif text.startswith("บทที่ ") or text in {"บทนำ", "ความรู้พื้นฐาน", "วิธีดำเนินการจัดทำโครงงาน"}:
        size, bold, space_before, space_after, first_indent, left_indent = 20, True, 0, 1, 0, 0
        alignment = TA_CENTER

    if alignment == 1:
        alignment = TA_CENTER
    elif alignment == 3:
        alignment = TA_JUSTIFY
    else:
        alignment = TA_LEFT
    return ParagraphStyle(
        name=f"p_{id(paragraph)}",
        parent=styles["Normal"],
        fontName="THSarabunNew",
        fontSize=size,
        leading=max(size * 1.08, 16),
        alignment=alignment,
        firstLineIndent=first_indent,
        leftIndent=left_indent,
        spaceBefore=space_before,
        spaceAfter=space_after,
        wordWrap="CJK",
        allowWidows=0,
        allowOrphans=0,
    )


def paragraph_has_page_break(paragraph: Paragraph) -> bool:
    return bool(paragraph._p.xpath('.//w:br[@w:type="page"]') or paragraph._p.xpath('.//w:pageBreakBefore'))


def table_widths(table: Table, available: float) -> list[float]:
    grid = table._tbl.tblGrid.gridCol_lst
    raw = [int(c.w) for c in grid] if grid else []
    col_count = len(table.columns)
    if not raw or len(raw) != col_count or sum(raw) == 0:
        return [available / col_count] * col_count
    total = float(sum(raw))
    return [available * w / total for w in raw]


def table_flowable(table: Table, styles, available: float) -> LongTable:
    data = []
    table_style = ParagraphStyle(
        "cell",
        parent=styles["Normal"],
        fontName="THSarabunNew",
        fontSize=11.5,
        leading=13,
        wordWrap="CJK",
        alignment=TA_CENTER,
    )
    for row_index, row in enumerate(table.rows):
        cells = []
        for cell in row.cells:
            text = "<br/>".join(run_markup(p) for p in cell.paragraphs)
            cell_style = ParagraphStyle(
                f"cell{row_index}_{len(cells)}",
                parent=table_style,
                fontName="THSarabunNew",
                alignment=TA_CENTER if row_index == 0 else TA_LEFT,
            )
            cells.append(RLParagraph(text, cell_style))
        data.append(cells)
    result = LongTable(data, colWidths=table_widths(table, available), repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "THSarabunNew"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "THSarabunNew"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9A9A9A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return result


def images_for_paragraph(paragraph: Paragraph, assets: Path, max_width: float):
    flows = []
    for index, blip in enumerate(paragraph._p.iter(BLIP_NS)):
        rel_id = blip.get(REL_NS)
        if not rel_id or rel_id not in paragraph.part.related_parts:
            continue
        image_part = paragraph.part.related_parts[rel_id]
        suffix = Path(image_part.partname).suffix or ".png"
        asset = assets / f"{paragraph._p.getparent().index(paragraph._p)}_{index}{suffix}"
        asset.write_bytes(image_part.blob)
        try:
            reader = ImageReader(str(asset))
            width, height = reader.getSize()
            scaled_width = min(max_width * 0.9, width * 72 / 96)
            scaled_height = scaled_width * height / width
            if scaled_height > 330:
                scaled_height = 330
                scaled_width = scaled_height * width / height
            flows.append(Image(str(asset), width=scaled_width, height=scaled_height, hAlign="CENTER"))
            flows.append(Spacer(1, 6))
        except Exception:
            continue
    return flows


def convert(source: Path, target: Path, asset_root: Path) -> None:
    doc = Document(source)
    section = doc.sections[0]
    page_width = points(section.page_width, A4[0])
    page_height = points(section.page_height, A4[1])
    left = points(section.left_margin, 3.81 * cm)
    right = points(section.right_margin, 2.54 * cm)
    top = points(section.top_margin, 3.81 * cm)
    bottom = points(section.bottom_margin, 2.54 * cm)
    available = page_width - left - right
    styles = getSampleStyleSheet()
    story = []
    assets = asset_root / source.stem
    assets.mkdir(parents=True, exist_ok=True)

    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            if paragraph_has_page_break(block):
                story.append(PageBreak())
            if block.text.strip() or list(block._p.iter(BLIP_NS)):
                story.append(RLParagraph(run_markup(block), paragraph_style(block, styles, 16)))
            story.extend(images_for_paragraph(block, assets, available))
        else:
            story.append(Spacer(1, 4))
            story.append(table_flowable(block, styles, available))
            story.append(Spacer(1, 4))

    start = start_page_number(source)
    hide_first = has_title_page(source)

    def page_number(canvas, _doc):
        current = canvas.getPageNumber()
        if hide_first and current == 1:
            return
        label = str(start + current - 1)
        canvas.saveState()
        canvas.setFont("THSarabunNew", 12)
        canvas.drawRightString(page_width - right, page_height - top + 18, label)
        canvas.restoreState()

    builder = SimpleDocTemplate(
        str(target), pagesize=(page_width, page_height),
        leftMargin=left, rightMargin=right, topMargin=top, bottomMargin=bottom,
        title=source.stem,
        author="HandVox",
    )
    builder.build(story, onFirstPage=page_number, onLaterPages=page_number)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    register_thai_font()
    args.target.parent.mkdir(parents=True, exist_ok=True)
    convert(args.source, args.target, args.assets)
    print(args.target)


if __name__ == "__main__":
    main()
