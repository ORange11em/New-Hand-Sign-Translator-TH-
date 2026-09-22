"""สร้างเอกสารบทที่ 1–5 ของ HandVox ด้วยรูปแบบ Word ที่กำหนด.

ฟังก์ชันช่วงต้นควบคุมสไตล์ ตาราง เลขหน้า และรูป ส่วน build_chapter_1 ถึง
build_chapter_5 เติมเนื้อหาแต่ละบท และ main บันทึกไฟล์ทั้งหมดลงโฟลเดอร์ผลลัพธ์
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ผลลัพธ์เอกสาร"
ASSETS = ROOT / "qa" / "assets"
OUTPUT.mkdir(parents=True, exist_ok=True)
ASSETS.mkdir(parents=True, exist_ok=True)

LANDMARK_FIGURE = (
    ROOT
    / "figure_capture_tests"
    / "figure_2_1_landmarks"
    / "output"
    / "figure_2_1_landmarks_20260813_134243.png"
)
SEQUENCE_FIGURE = (
    ROOT
    / "figure_capture_tests"
    / "figure_2_2_sequence"
    / "output"
    / "figure_2_2_sequence_30_frames.png"
)
COLLECTION_FIGURE = ASSETS / "handvox_collect_screen.png"
CONFUSION_SOURCE = (
    ROOT
    / "experiments"
    / "quick_20260816_152804_809320"
    / "confusion_matrix.png"
)
CONFUSION_FIGURE = ASSETS / "handvox_confusion_matrix_stratified.png"

FONT_NAME = "TH Sarabun New"
# The font name embedded in the DOCX is authoritative.  Use the available
# Thai font only for generating the small illustrative placeholder bitmaps.
FONT_FILE = Path("C:/Windows/Fonts/angsana.ttc")
INK = "000000"
BLUE = "000000"
LIGHT_BLUE = "E7E6E6"
LIGHT_GRAY = "F2F2F2"
MID_GRAY = "A6A6A6"
_CURRENT_HEADING_LEVEL = 1
CHAPTER_PAGE_STARTS = {1: 1, 2: 6, 3: 14, 4: 22, 5: 29}


def set_run_font(run, size=16, bold=False, italic=False, color=INK):
    run.font.name = FONT_NAME
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{key}"), FONT_NAME)
    # Mark the run as Thai so Word applies Thai dictionary-based line breaking
    # instead of treating a long Thai phrase as one unbreakable word.
    lang = rpr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rpr.append(lang)
    for key in ("val", "eastAsia", "bidi"):
        lang.set(qn(f"w:{key}"), "th-TH")


def set_cell_shading(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = tcpr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcpr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=90, start=120, bottom=90, end=120):
    tc = cell._tc
    tcpr = tc.get_or_add_tcPr()
    mar = tcpr.first_child_found_in("w:tcMar")
    if mar is None:
        mar = OxmlElement("w:tcMar")
        tcpr.append(mar)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = mar.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_repeat_header(row):
    trpr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    trpr.append(header)


def set_row_cant_split(row):
    trpr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    cant_split.set(qn("w:val"), "true")
    trpr.append(cant_split)


def set_table_borders(table, color="B7B7B7", size="6"):
    tblpr = table._tbl.tblPr
    borders = tblpr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblpr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = borders.find(qn(f"w:{edge}"))
        if tag is None:
            tag = OxmlElement(f"w:{edge}")
            borders.append(tag)
        tag.set(qn("w:val"), "single")
        tag.set(qn("w:sz"), size)
        tag.set(qn("w:space"), "0")
        tag.set(qn("w:color"), color)


def set_fixed_table_geometry(table, widths_cm):
    table.autofit = False
    total_twips = sum(int(Cm(width).twips) for width in widths_cm)
    tblpr = table._tbl.tblPr
    tblw = tblpr.first_child_found_in("w:tblW")
    tblw.set(qn("w:w"), str(total_twips))
    tblw.set(qn("w:type"), "dxa")
    ind = tblpr.first_child_found_in("w:tblInd")
    if ind is None:
        ind = OxmlElement("w:tblInd")
        tblpr.append(ind)
    ind.set(qn("w:w"), "120")
    ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_cm:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(int(Cm(width).twips)))
        grid.append(col)
    for row in table.rows:
        for cell, width in zip(row.cells, widths_cm):
            cell.width = Cm(width)
            tcpr = cell._tc.get_or_add_tcPr()
            tcw = tcpr.first_child_found_in("w:tcW")
            tcw.set(qn("w:w"), str(int(Cm(width).twips)))
            tcw.set(qn("w:type"), "dxa")
            set_cell_margins(cell)


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "true")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for node in (begin, instr, separate, text, end):
        run._r.append(node)
    set_run_font(run, 14)


def configure_chapter_pagination(section, page_start):
    """Hide the chapter-opening number while still counting that page."""

    section.different_first_page_header_footer = True

    # Write both controls explicitly so the behavior survives reopening or
    # conversion: titlePg hides the first-page header and pgNumType keeps the
    # requested chapter-to-chapter sequence.
    title_page = section._sectPr.find(qn("w:titlePg"))
    if title_page is None:
        title_page = OxmlElement("w:titlePg")
        section._sectPr.append(title_page)
    title_page.set(qn("w:val"), "true")

    pg_num_type = section._sectPr.find(qn("w:pgNumType"))
    if pg_num_type is None:
        pg_num_type = OxmlElement("w:pgNumType")
        section._sectPr.append(pg_num_type)
    pg_num_type.set(qn("w:start"), str(page_start))


def configure_document(doc, page_start=1):
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.81)
    section.left_margin = Cm(3.81)
    section.right_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.header_distance = Cm(1.25)
    section.footer_distance = Cm(1.25)
    configure_chapter_pagination(section, page_start)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = Pt(16)
    normal._element.rPr.rFonts.set(qn("w:ascii"), FONT_NAME)
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), FONT_NAME)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
    normal._element.rPr.rFonts.set(qn("w:cs"), FONT_NAME)
    # Thai academic body paragraphs use a consistent 1.25 cm first-line
    # indent. Left alignment avoids Word stretching Thai glyphs and spaces.
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    normal.paragraph_format.first_line_indent = Cm(1.25)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.widow_control = True

    for style_name, size, color in (("Heading 1", 18, BLUE), ("Heading 2", 16, INK), ("Heading 3", 16, INK)):
        style = styles[style_name]
        style.font.name = FONT_NAME
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style._element.rPr.rFonts.set(qn("w:ascii"), FONT_NAME)
        style._element.rPr.rFonts.set(qn("w:hAnsi"), FONT_NAME)
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
        style._element.rPr.rFonts.set(qn("w:cs"), FONT_NAME)
        level = int(style_name[-1])
        style.paragraph_format.left_indent = Cm(1.25 * (level - 1))
        style.paragraph_format.right_indent = Cm(0)
        style.paragraph_format.first_line_indent = Cm(0)
        style.paragraph_format.space_before = Pt(10 if style_name == "Heading 1" else 6)
        style.paragraph_format.space_after = Pt(3)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True

    caption = styles["Caption"]
    caption.font.name = FONT_NAME
    caption.font.size = Pt(14)
    caption.font.italic = False
    caption.font.color.rgb = RGBColor.from_string(INK)
    caption._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
    caption.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.first_line_indent = Cm(0)
    caption.paragraph_format.space_before = Pt(3)
    caption.paragraph_format.space_after = Pt(6)
    # A caption is already kept with the table/image by the preceding object's
    # paragraph.  Keeping the caption with the following paragraph creates a
    # long pagination chain and can push the final table row to the next page.
    caption.paragraph_format.keep_with_next = False

    header = section.header
    header.is_linked_to_previous = False
    header_p = header.paragraphs[0]
    header_p.clear()
    add_page_number(header_p)

    first_header = section.first_page_header
    first_header.is_linked_to_previous = False
    first_header_p = first_header.paragraphs[0]
    first_header_p.clear()
    first_header_p.paragraph_format.first_line_indent = Cm(0)
    first_header_p.paragraph_format.space_before = Pt(0)
    first_header_p.paragraph_format.space_after = Pt(0)

    section.footer.is_linked_to_previous = False
    section.footer.paragraphs[0].clear()
    section.first_page_footer.is_linked_to_previous = False
    section.first_page_footer.paragraphs[0].clear()

    settings = doc.settings.element
    compat = settings.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat")
        settings.append(compat)
    update_fields = settings.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        settings.append(update_fields)
    update_fields.set(qn("w:val"), "true")


def add_chapter_title(doc, number, title):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.keep_with_next = True
    set_run_font(p.add_run(f"บทที่ {number}"), 20, bold=True)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.first_line_indent = Cm(0)
    p2.paragraph_format.space_after = Pt(12)
    p2.paragraph_format.keep_with_next = True
    set_run_font(p2.add_run(title), 20, bold=True)


def add_heading(doc, text, level=1):
    global _CURRENT_HEADING_LEVEL
    _CURRENT_HEADING_LEVEL = level
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.left_indent = Cm(1.25 * (level - 1))
    p.paragraph_format.right_indent = Cm(0)
    p.paragraph_format.first_line_indent = Cm(0)
    p.add_run(text)
    for run in p.runs:
        set_run_font(run, 18 if level == 1 else 16, bold=True, color=BLUE if level == 1 else INK)
    return p


def add_body(doc, text, indent=True, italic=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.left_indent = Cm(0)
    p.paragraph_format.right_indent = Cm(0)
    p.paragraph_format.first_line_indent = Cm(1.25 if indent else 0)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.keep_together = False
    set_run_font(p.add_run(text), 16, italic=italic)
    return p


def add_chapter_overview(doc, introduction, sections=None):
    """Add only the opening elements shown by the matching reference chapter."""
    intro = add_body(doc, introduction, indent=True)
    intro.alignment = WD_ALIGN_PARAGRAPH.LEFT
    intro.paragraph_format.space_before = Pt(20)
    intro.paragraph_format.space_after = Pt(6)

    for number, title in sections or []:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.left_indent = Cm(2.0)
        p.paragraph_format.first_line_indent = Cm(-0.75)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.keep_together = True
        set_run_font(p.add_run(f"{number} {title}"), 16)


def add_item(doc, number, text):
    marker_indent = 1.25
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.left_indent = Cm(marker_indent + 1.25)
    p.paragraph_format.first_line_indent = Cm(-1.25)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_together = True
    # Keep the number and its text in one run so Word cannot split them into
    # separate visual blocks (the defect shown in the user's screenshot).
    set_run_font(p.add_run(f"{number} {text}"), 16)
    return p


def _new_numbering_instance(doc, style_id="ListNumber"):
    """Create a real Word numbering instance that restarts at 1."""
    numbering = doc.part.numbering_part.element
    abstract_id = None
    for abstract in numbering.findall(qn("w:abstractNum")):
        for level in abstract.findall(qn("w:lvl")):
            paragraph_style = level.find(qn("w:pStyle"))
            if paragraph_style is not None and paragraph_style.get(qn("w:val")) == style_id:
                abstract_id = int(abstract.get(qn("w:abstractNumId")))
                break
        if abstract_id is not None:
            break
    if abstract_id is None:
        for abstract in numbering.findall(qn("w:abstractNum")):
            level = abstract.find(qn("w:lvl"))
            num_fmt = level.find(qn("w:numFmt")) if level is not None else None
            if num_fmt is not None and num_fmt.get(qn("w:val")) == "decimal":
                abstract_id = int(abstract.get(qn("w:abstractNumId")))
                break
    if abstract_id is None:
        raise RuntimeError("ไม่พบรูปแบบรายการลำดับเลขในแม่แบบ Word")

    num = numbering.add_num(abstract_id)
    num.add_lvlOverride(ilvl=0).add_startOverride(1)
    return int(num.get(qn("w:numId")))


def add_numbered_list(doc, items):
    """Add a numbered list using OOXML numbering rather than typed markers."""
    num_id = _new_numbering_instance(doc)
    paragraphs = []
    for text in items:
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.left_indent = Cm(2.0)
        p.paragraph_format.first_line_indent = Cm(-0.75)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.keep_together = True
        num_pr = p._p.get_or_add_pPr().get_or_add_numPr()
        num_pr.get_or_add_ilvl().val = 0
        num_pr.get_or_add_numId().val = num_id
        set_run_font(p.add_run(text), 16)
        paragraphs.append(p)
    return paragraphs


def add_subtopic(doc, label, text):
    """Add a compact bold lead-in under one of the required chapter headings."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.left_indent = Cm(0)
    p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    set_run_font(p.add_run(f"{label}: "), 16, bold=True)
    set_run_font(p.add_run(text), 16)
    return p


def add_note(doc, label, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.left_indent = Cm(0.2)
    p.paragraph_format.right_indent = Cm(0.2)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    ppr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "F2F2F2")
    ppr.append(shd)
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "8")
        node.set(qn("w:space"), "4")
        node.set(qn("w:color"), "000000")
        borders.append(node)
    ppr.append(borders)
    set_run_font(p.add_run(f"{label}: "), 15, bold=True, color=BLUE)
    set_run_font(p.add_run(text), 15)


def add_table(doc, headers, rows, widths_cm, caption=None, font_size=14):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    set_fixed_table_geometry(table, widths_cm)
    set_table_borders(table)
    hdr = table.rows[0]
    set_repeat_header(hdr)
    set_row_cant_split(hdr)
    for cell, text in zip(hdr.cells, headers):
        set_cell_shading(cell, LIGHT_BLUE)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.keep_with_next = True
        set_run_font(p.add_run(str(text)), font_size, bold=True, color=BLUE)
    for row_values in rows:
        row = table.add_row()
        set_row_cant_split(row)
        cells = row.cells
        for cell, text in zip(cells, row_values):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_after = Pt(0)
            if len(str(text)) <= 18:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            set_run_font(p.add_run(str(text)), font_size)
        set_fixed_table_geometry(table, widths_cm)
    if caption:
        for cell in table.rows[-1].cells:
            cell.paragraphs[-1].paragraph_format.keep_with_next = True
        p = doc.add_paragraph(style="Caption")
        p.paragraph_format.keep_together = True
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        set_run_font(p.add_run(caption), 14)
    return table


def add_project_schedule_table(doc):
    """Add the compact five-month project schedule used in chapter 1."""
    caption = doc.add_paragraph(style="Caption")
    caption.alignment = WD_ALIGN_PARAGRAPH.LEFT
    caption.paragraph_format.first_line_indent = Cm(0)
    caption.paragraph_format.space_before = Pt(0)
    caption.paragraph_format.space_after = Pt(2)
    caption.paragraph_format.keep_with_next = True
    set_run_font(caption.add_run("ตารางที่ 1.1 ระยะเวลาการดำเนินโครงงาน"), 14)

    headers = ["แนวทางการดำเนินโครงงาน", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค."]
    activities = [
        "1. ศึกษาและรวบรวมข้อมูลที่เกี่ยวข้อง",
        "2. วิเคราะห์ความต้องการและออกแบบระบบ",
        "3. พัฒนาระบบ เก็บข้อมูล และสกัดจุดสำคัญ",
        "4. ฝึกแบบจำลอง ทดสอบ และปรับปรุงระบบ",
        "5. ประเมินผล สรุปผล และจัดทำรายงาน",
    ]
    active_months = [
        {0, 1},
        {1, 2},
        {2, 3},
        {3, 4},
        {4},
    ]
    widths = [9.0, 1.13, 1.13, 1.13, 1.13, 1.13]
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    set_fixed_table_geometry(table, widths)
    set_table_borders(table, color="000000", size="8")

    header_row = table.rows[0]
    set_repeat_header(header_row)
    set_row_cant_split(header_row)
    for index, (cell, text) in enumerate(zip(header_row.cells, headers)):
        set_cell_shading(cell, LIGHT_BLUE)
        set_cell_margins(cell, top=30, start=55, bottom=30, end=55)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT if index == 0 else WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.0
        paragraph.paragraph_format.keep_with_next = True
        set_run_font(paragraph.add_run(text), 13, bold=True)

    for row_index, activity in enumerate(activities):
        row = table.add_row()
        set_row_cant_split(row)
        for column_index, cell in enumerate(row.cells):
            set_cell_margins(cell, top=25, start=55, bottom=25, end=55)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT if column_index == 0 else WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.paragraph_format.keep_with_next = row_index < len(activities) - 1
            if column_index == 0:
                set_run_font(paragraph.add_run(activity), 13)
            elif column_index - 1 in active_months[row_index]:
                set_cell_shading(cell, "2B2B2B")
        set_fixed_table_geometry(table, widths)
    return table


def add_compact_definition(doc, term, definition):
    """Add a concise thesis-style term definition without consuming a full page."""
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.left_indent = Cm(0)
    paragraph.paragraph_format.first_line_indent = Cm(1.25)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.keep_together = True
    set_run_font(paragraph.add_run(f"{term} หมายถึง "), 15, bold=True)
    set_run_font(paragraph.add_run(definition), 15)
    return paragraph


def add_code_block(doc, caption, code):
    """Add a compact, readable source-code excerpt using the project font."""
    label = doc.add_paragraph()
    label.paragraph_format.first_line_indent = Cm(0)
    label.paragraph_format.space_before = Pt(3)
    label.paragraph_format.space_after = Pt(2)
    label.paragraph_format.keep_with_next = True
    set_run_font(label.add_run(caption), 14, bold=True)

    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Cm(0.35)
    paragraph.paragraph_format.right_indent = Cm(0.35)
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.keep_together = True
    properties = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), "F2F2F2")
    properties.append(shading)
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:space"), "5")
        node.set(qn("w:color"), "B7B7B7")
        borders.append(node)
    properties.append(borders)

    lines = code.strip("\n").splitlines()
    for index, line in enumerate(lines):
        run = paragraph.add_run(line)
        set_run_font(run, 14)
        if index < len(lines) - 1:
            run.add_break()
    return paragraph


def add_reference(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.left_indent = Cm(1.25)
    p.paragraph_format.first_line_indent = Cm(-1.25)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.0
    set_run_font(p.add_run(text), 14)


def draw_arrow(draw, start, end, fill):
    draw.line([start, end], fill=fill, width=6)
    x2, y2 = end
    draw.polygon([(x2, y2), (x2 - 18, y2 - 11), (x2 - 18, y2 + 11)], fill=fill)


def make_flow_diagram(path):
    image = Image.new("RGB", (1800, 600), "white")
    draw = ImageDraw.Draw(image)
    font_title = ImageFont.truetype(str(FONT_FILE), 48)
    font_box = ImageFont.truetype(str(FONT_FILE), 38)
    font_small = ImageFont.truetype(str(FONT_FILE), 30)
    draw.text((900, 25), "สถาปัตยกรรมการทำงานของ HandVox", font=font_title, anchor="ma", fill="#000000")
    boxes = [
        ("เว็บแคม", "ภาพวิดีโอ"),
        ("MediaPipe Holistic", "15 จุดช่วงบน + มือ 2 ข้าง"),
        ("การปรับมาตรฐาน", "171 ค่า/เฟรม"),
        ("หน้าต่าง 30 เฟรม", "5,130 ค่า/คลิป"),
        ("SVM แบบ RBF", "ความน่าจะเป็นรายท่า"),
        ("ผลลัพธ์", "ข้อความ / ประโยค / เสียง"),
    ]
    start_x, y, width, height, gap = 35, 180, 255, 230, 40
    for idx, (title, subtitle) in enumerate(boxes):
        x1 = start_x + idx * (width + gap)
        x2 = x1 + width
        draw.rounded_rectangle((x1, y, x2, y + height), radius=18, fill="#F2F2F2", outline="#000000", width=4)
        draw.text(((x1 + x2) / 2, y + 72), title, font=font_box, anchor="mm", fill="#000000")
        draw.multiline_text(((x1 + x2) / 2, y + 150), subtitle, font=font_small, anchor="mm", align="center", fill="#000000", spacing=8)
        if idx < len(boxes) - 1:
            draw_arrow(draw, (x2 + 5, y + height / 2), (x2 + gap - 5, y + height / 2), "#4F81BD")
    draw.text((900, 535), "ใช้คุณลักษณะรูปทรงและการเคลื่อนไหวที่กำหนดไว้ล่วงหน้า ไม่ใช่การแปลภาษามือต่อเนื่องทั้งภาษา", font=font_small, anchor="mm", fill="#000000")
    image.save(path, quality=95)


def make_collection_figure(path):
    """Create a reproducible collection-screen illustration from a project capture."""
    if not LANDMARK_FIGURE.exists():
        raise FileNotFoundError(f"ไม่พบภาพต้นฉบับสำหรับหน้าจอเก็บข้อมูล: {LANDMARK_FIGURE}")

    image = Image.open(LANDMARK_FIGURE).convert("RGBA")
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, width, 132), fill=(17, 24, 39, 220))
    draw.rectangle((0, height - 74, width, height), fill=(17, 24, 39, 220))

    title_font = ImageFont.truetype(str(FONT_FILE), 44)
    status_font = ImageFont.truetype(str(FONT_FILE), 34)
    help_font = ImageFont.truetype(str(FONT_FILE), 29)
    draw.text((24, 15), "ท่า: สวัสดี", font=title_font, fill="#FFFFFF")
    draw.text((24, 68), "คลิปที่ 7/30", font=status_font, fill="#D1FAE5")
    draw.text(
        (width - 24, 32),
        "กำลังบันทึกเฟรม 18/30",
        font=status_font,
        fill="#86EFAC",
        anchor="ra",
    )
    draw.text(
        (width - 24, 84),
        "กรอบช่วงบนและจุดสำคัญต้องมองเห็นชัดเจน",
        font=help_font,
        fill="#E5E7EB",
        anchor="ra",
    )
    draw.text(
        (width / 2, height - 38),
        "Space เริ่ม/หยุด | S บันทึกภาพ | Q ออก | ภาพประกอบไม่เขียน Dataset จริง",
        font=help_font,
        fill="#FFFFFF",
        anchor="mm",
    )
    composed = Image.alpha_composite(image, overlay).convert("RGB")
    composed.save(path, quality=95)


def make_confusion_figure(path):
    """Correct the experiment label without altering the measured matrix."""
    if not CONFUSION_SOURCE.exists():
        raise FileNotFoundError(f"ไม่พบ confusion matrix: {CONFUSION_SOURCE}")
    image = Image.open(CONFUSION_SOURCE).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, _ = image.size
    draw.rectangle((0, 0, width, 92), fill="white")
    font = ImageFont.truetype(str(FONT_FILE), 44)
    draw.text(
        (width / 2, 42),
        "HandVox Confusion Matrix - stratified holdout 80:20",
        font=font,
        fill="#111111",
        anchor="mm",
    )
    image.save(path, quality=95)


def add_figure(doc, image_path, caption):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(str(image_path), width=Cm(14.4))
    shape._inline.docPr.set("descr", caption)
    shape._inline.docPr.set("title", caption)
    cap = doc.add_paragraph(style="Caption")
    set_run_font(cap.add_run(caption), 14)


def add_image_placeholder(doc, caption, description, height_lines=5):
    """Leave a visible, labeled space for a screenshot/diagram the user must supply."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_together = True
    p.paragraph_format.keep_with_next = True
    ppr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "F7F7F7")
    ppr.append(shd)
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "dashed")
        node.set(qn("w:sz"), "8")
        node.set(qn("w:space"), "6")
        node.set(qn("w:color"), "7F7F7F")
        borders.append(node)
    ppr.append(borders)
    spacer = "\n" * max(2, height_lines // 2)
    set_run_font(p.add_run(spacer), 14)
    set_run_font(p.add_run("[เว้นพื้นที่สำหรับภาพประกอบ]\n"), 15, bold=True, color=BLUE)
    set_run_font(p.add_run(f"ภาพที่ต้องการ: {description}"), 14, italic=True, color="000000")
    set_run_font(p.add_run(spacer), 14)
    cap = doc.add_paragraph(style="Caption")
    set_run_font(cap.add_run(caption), 14)
    return p


def build_chapter_1():
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[1])
    add_chapter_title(doc, 1, "บทนำ")

    add_heading(doc, "1.1 ที่มาและความสำคัญของปัญหา")
    add_body(doc, "การสื่อสารระหว่างผู้ใช้ภาษามือกับบุคคลที่ไม่เข้าใจภาษามือยังมีข้อจำกัดในหลายบริบท เช่น การติดต่อบริการ การเรียน การทำงาน และการสื่อสารในชีวิตประจำวัน เทคโนโลยีการมองเห็นด้วยคอมพิวเตอร์สามารถช่วยลดข้อจำกัดบางส่วนได้ โดยรับภาพจากกล้อง ตรวจหาตำแหน่งร่างกายและมือ แล้วจำแนกท่าที่ระบบเคยเรียนรู้ให้เป็นข้อความที่ผู้อื่นอ่านได้")
    add_body(doc, "อย่างไรก็ตาม ภาษามือเป็นภาษาธรรมชาติที่ประกอบด้วยรูปมือ ตำแหน่ง ทิศทาง การเคลื่อนไหว สีหน้า และโครงสร้างทางภาษา ระบบที่รู้จำเฉพาะท่าที่กำหนดไว้ล่วงหน้าจึงไม่ควรถูกอธิบายว่าเป็นเครื่องแปลภาษามืออย่างสมบูรณ์ โครงงานนี้จึงกำหนดขอบเขตเป็นระบบรู้จำท่าทางภาษามือไทยแบบแยกคำ (isolated gesture recognition) จากคลิปสั้นของการเคลื่อนไหว แล้วแสดงชื่อท่าเป็นข้อความและเสียงภาษาไทย")
    add_body(doc, "HandVox พัฒนาด้วยภาษา Python ใช้ OpenCV รับภาพจากเว็บแคม ใช้ MediaPipe Holistic ตรวจหาจุดสำคัญของช่วงบนและมือทั้งสองข้าง และใช้ Support Vector Machine (SVM) จำแนกลำดับข้อมูล 30 เฟรม ระบบยังรองรับการเพิ่มหรือลบท่าจากเมนู เก็บข้อมูลใหม่ ฝึกโมเดลซ้ำ สะสมคำเป็นประโยค และอ่านออกเสียง จึงเหมาะเป็นต้นแบบสำหรับศึกษากระบวนการสร้างระบบรู้จำท่าทางแบบครบวงจร")
    add_note(doc, "ขอบเขตการกล่าวอ้าง", "เอกสารฉบับนี้ใช้คำว่า “รู้จำท่าทางภาษามือแบบแยกคำ” แทนคำว่า “แปลภาษามือ” เมื่อกล่าวถึงความสามารถของโมเดล เพื่อให้สอดคล้องกับสิ่งที่ระบบปัจจุบันทำได้จริง")

    add_heading(doc, "1.2 วัตถุประสงค์ของโครงงาน")
    add_item(doc, "1.2.1", "เพื่อพัฒนาระบบ HandVox สำหรับรู้จำท่าทางภาษามือไทยที่กำหนดไว้ล่วงหน้าจากลำดับภาพเว็บแคมแบบเวลาจริง")
    add_item(doc, "1.2.2", "เพื่อพัฒนากระบวนการเก็บคลิป เพิ่มหรือลบท่า และฝึกแบบจำลองใหม่โดยผู้ใช้ไม่จำเป็นต้องแก้ไขซอร์สโค้ดโดยตรง")
    add_item(doc, "1.2.3", "เพื่อแสดงผลการรู้จำเป็นชื่อท่า ค่าความเชื่อมั่น ข้อความสะสมเป็นประโยค และเสียงพูดภาษาไทย")
    add_item(doc, "1.2.4", "เพื่อประเมินผลการจำแนกภายในชุดข้อมูลของโครงงาน และระบุข้อจำกัดที่ต้องตรวจสอบก่อนนำไปใช้กับผู้ใช้หรือสภาพแวดล้อมใหม่")

    add_heading(doc, "1.3 ขอบเขตการศึกษา")
    add_body(doc, "การศึกษานี้มุ่งพัฒนาต้นแบบ HandVox สำหรับรู้จำท่าทางภาษามือไทยแบบแยกคำจากภาพเคลื่อนไหวที่รับผ่านเว็บแคม โดยศึกษากระบวนการตั้งแต่การเก็บและเตรียมข้อมูล การสกัดจุดสำคัญของร่างกายและมือ การสร้างแบบจำลองจำแนกท่าทาง ตลอดจนการนำผลไปแสดงเป็นข้อความ ประโยค และเสียงภาษาไทย ทั้งนี้กำหนดขอบเขตด้านการทำงาน ข้อมูลและแบบจำลอง แพลตฟอร์ม และสิ่งที่อยู่นอกขอบเขตไว้ดังต่อไปนี้")
    add_heading(doc, "1.3.1 ขอบเขตด้านการทำงาน", 2)
    add_item(doc, "1)", "รับภาพจากเว็บแคมหนึ่งตัวและประมวลผลบุคคลหนึ่งคน โดยต้องเห็นช่วงไหล่และมืออย่างน้อยหนึ่งข้าง")
    add_item(doc, "2)", "รู้จำท่าทีละหนึ่งคำจากหน้าต่างข้อมูลล่าสุด 30 เฟรม และจำแนกเฉพาะท่าที่มีอยู่ในชุดข้อมูลของโครงงาน")
    add_item(doc, "3)", "แสดงชื่อท่าและค่าความเชื่อมั่น ใช้ผลย้อนหลัง 3 ครั้งเพื่อลดการสั่นของคำทำนาย และรับผลเมื่อความเชื่อมั่นไม่น้อยกว่า 0.40")
    add_item(doc, "4)", "เพิ่มคำลงในประโยค ลบคำ ล้างประโยค และอ่านออกเสียงด้วย gTTS เมื่อเชื่อมต่ออินเทอร์เน็ต")
    add_item(doc, "5)", "เพิ่มท่า ลบท่า สำรองข้อมูล และฝึกโมเดลใหม่ผ่านเมนูหรือไฟล์คำสั่งของระบบ")
    add_heading(doc, "1.3.2 ขอบเขตด้านข้อมูลและแบบจำลอง", 2)
    add_item(doc, "1)", "หนึ่งตัวอย่างเป็นคลิปลำดับ 30 เฟรม ส่วนจำนวนคลิปต่อท่าในชุดปัจจุบันอยู่ระหว่าง 10–30 คลิป และต้องเก็บเพิ่มแบบสมดุลก่อนประเมินมาตรฐาน")
    add_item(doc, "2)", "หนึ่งเฟรมใช้ 171 คุณลักษณะ ได้แก่ 15 จุดของช่วงบน มือซ้าย 21 จุด และมือขวา 21 จุด โดยแต่ละจุดมีพิกัด x, y และ z")
    add_item(doc, "3)", "หนึ่งคลิปถูกทำให้เป็นเวกเตอร์ 5,130 ค่า (30 × 171) เพื่อฝึก SVM แบบ RBF")
    add_item(doc, "4)", "ชุดข้อมูลที่ตรวจสอบ ณ วันที่ 16 สิงหาคม 2569 มี 16 ท่า รวม 350 คลิป ได้แก่ กิน ขอบคุณ ขอโทษ ช่วยด้วย ต้องการ น้ำ สวัสดี หมอ หยุด ห้องน้ำ เข้าใจ เจ็บ ใช่ ไม่เข้าใจ ไม่เป็นไร และไม่ใช่")
    add_heading(doc, "1.3.3 ขอบเขตด้านแพลตฟอร์ม", 2)
    add_item(doc, "1)", "ทำงานบนระบบปฏิบัติการ Windows 10 หรือ Windows 11")
    add_item(doc, "2)", "ใช้ Python 3.10 หรือ 3.11 และไลบรารีตามไฟล์ requirements.txt ของโครงงาน")
    add_item(doc, "3)", "ใช้กล้องเว็บแคมและลำโพง โดยอินเทอร์เน็ตจำเป็นสำหรับการติดตั้งครั้งแรกและการสร้างเสียงด้วย gTTS")
    add_heading(doc, "1.3.4 สิ่งที่อยู่นอกขอบเขต", 2)
    add_item(doc, "1)", "ไม่รองรับการรู้จำภาษามือต่อเนื่องหลายคำโดยอัตโนมัติ การวิเคราะห์ไวยากรณ์ หรือการแปลเป็นประโยคภาษาพูด")
    add_item(doc, "2)", "ไม่ได้ใช้จุดใบหน้าและการแสดงสีหน้าเป็นคุณลักษณะ แม้ MediaPipe Holistic จะตรวจหาได้")
    add_item(doc, "3)", "ยังไม่ผ่านการรับรองสำหรับการสื่อสารที่เกี่ยวข้องกับการแพทย์ กฎหมาย ความปลอดภัย หรือการใช้แทนล่ามภาษามือ")

    add_heading(doc, "1.4 วิธีดำเนินโครงงานโดยสรุป")
    steps = [
        ("1.4.1", "ศึกษาปัญหา หลักการรู้จำท่าทาง และข้อจำกัดของการกล่าวอ้างว่าเป็นการแปลภาษา"),
        ("1.4.2", "วิเคราะห์ความต้องการและออกแบบกระบวนการเก็บข้อมูล ฝึกแบบจำลอง และใช้งานแบบเวลาจริง"),
        ("1.4.3", "พัฒนาการสกัดคุณลักษณะจากช่วงบนและมือทั้งสองข้าง พร้อมปรับมาตรฐานด้วยจุดกึ่งกลางและระยะระหว่างไหล่"),
        ("1.4.4", "เก็บคลิปที่มีป้ายกำกับ แบ่งข้อมูลแบบ stratified และฝึก SVM แบบ RBF"),
        ("1.4.5", "ทดสอบฟังก์ชันการทำงาน ประเมินผลการจำแนก และวิเคราะห์ข้อจำกัดด้านข้อมูล ผู้ใช้ และสภาพแวดล้อม"),
        ("1.4.6", "จัดทำเอกสาร สรุปผล และเสนอแนวทางพัฒนาต่อ"),
    ]
    for no, text in steps:
        add_item(doc, no, text)

    add_heading(doc, "1.5 ประโยชน์ที่คาดว่าจะได้รับ")
    add_item(doc, "1.5.1", "ได้ต้นแบบระบบรู้จำท่าทางภาษามือแบบแยกคำที่สามารถทำงานกับกล้องทั่วไปและแสดงผลได้แบบเวลาจริง")
    add_item(doc, "1.5.2", "ได้กระบวนการสร้างชุดข้อมูลการเคลื่อนไหวและฝึกแบบจำลองที่ผู้ใช้สามารถเพิ่มคำศัพท์ได้เอง")
    add_item(doc, "1.5.3", "ได้กรณีศึกษาการประยุกต์ใช้ Computer Vision และ Machine Learning เพื่อสนับสนุนการสื่อสารอย่างมีขอบเขตและตรวจสอบได้")
    add_item(doc, "1.5.4", "ได้ข้อมูลข้อจำกัดและแนวทางพัฒนาสำหรับการทดสอบกับผู้ใช้หลายคน สภาพแวดล้อมหลายแบบ และคำศัพท์ที่มากขึ้น")

    add_heading(doc, "1.6 ทรัพยากรที่ใช้ในการพัฒนา")
    add_table(doc, ["ประเภท", "รายการ", "หน้าที่"], [
        ["ฮาร์ดแวร์", "คอมพิวเตอร์ที่รองรับ Python และเว็บแคม", "พัฒนา ฝึกแบบจำลอง และประมวลผลภาพ"],
        ["ฮาร์ดแวร์", "เว็บแคมความละเอียดที่รองรับ 1280 × 720 พิกเซล", "รับภาพช่วงบนและมือของผู้ใช้"],
        ["ซอฟต์แวร์", "Windows 10/11 และ Python 3.10/3.11", "สภาพแวดล้อมหลักของโปรแกรม"],
        ["ไลบรารี", "OpenCV 4.8.1 และ MediaPipe 0.10.9", "รับภาพ วาดส่วนติดต่อ และตรวจหาจุดสำคัญ"],
        ["ไลบรารี", "NumPy 1.26.4 และ scikit-learn 1.3.2", "จัดการข้อมูลและฝึก SVM"],
        ["ไลบรารี", "Pillow, gTTS และ pygame", "แสดงข้อความไทย สร้างเสียง และเล่นเสียง"],
    ], [2.6, 5.0, 7.05], caption="ตารางที่ 1.1 ทรัพยากรหลักของโครงงาน")

    add_heading(doc, "1.7 แผนการดำเนินงาน")
    add_table(doc, ["กิจกรรม", "ระยะที่ 1", "ระยะที่ 2", "ระยะที่ 3", "ระยะที่ 4", "ระยะที่ 5"], [
        ["ศึกษาปัญหาและงานที่เกี่ยวข้อง", "●", "", "", "", ""],
        ["วิเคราะห์และออกแบบระบบ", "●", "●", "", "", ""],
        ["พัฒนาและเก็บข้อมูล", "", "●", "●", "", ""],
        ["ฝึกแบบจำลองและทดสอบ", "", "", "●", "●", ""],
        ["ปรับปรุงและจัดทำเอกสาร", "", "", "", "●", "●"],
    ], [5.65, 1.8, 1.8, 1.8, 1.8, 1.8], caption="ตารางที่ 1.2 แผนการดำเนินงานเชิงระยะ (สามารถแทนระยะด้วยเดือนตามปฏิทินของสถานศึกษา)", font_size=13)

    add_heading(doc, "1.8 นิยามศัพท์เฉพาะ")
    definitions = [
        ("1.8.1", "ท่าทางภาษามือแบบแยกคำ (Isolated Sign/Gesture)", "ท่าหนึ่งคำที่เริ่มและสิ้นสุดภายในคลิปที่แยกจากท่าอื่นอย่างชัดเจน"),
        ("1.8.2", "จุดสำคัญ (Landmark)", "พิกัด x, y และ z ของตำแหน่งร่างกายหรือมือที่ MediaPipe ตรวจหาในแต่ละเฟรม"),
        ("1.8.3", "คลิปการเคลื่อนไหว (Motion Clip)", "ลำดับข้อมูล 30 เฟรมต่อเนื่องที่ใช้แทนการทำท่าหนึ่งครั้ง"),
        ("1.8.4", "การปรับมาตรฐาน (Normalization)", "การเลื่อนและปรับขนาดพิกัดให้สัมพันธ์กับจุดกึ่งกลางไหล่และระยะระหว่างไหล่ เพื่อลดผลจากตำแหน่งและระยะห่างจากกล้อง"),
        ("1.8.5", "เวกเตอร์คุณลักษณะ (Feature Vector)", "ชุดตัวเลขที่แทนจุดช่วงบนและมือ โดยมี 171 ค่าต่อเฟรมและ 5,130 ค่าต่อคลิป"),
        ("1.8.6", "Support Vector Machine (SVM)", "แบบจำลองการเรียนรู้แบบมีผู้สอนที่ใช้สร้างขอบเขตการตัดสินใจระหว่างคลาส"),
        ("1.8.7", "ค่าความเชื่อมั่น (Confidence)", "ค่าความน่าจะเป็นที่แบบจำลองรายงานประกอบคำทำนาย ซึ่งไม่เท่ากับความถูกต้องที่รับประกันในทุกสถานการณ์"),
        ("1.8.8", "Text-to-Speech (TTS)", "การแปลงข้อความผลลัพธ์เป็นเสียงพูดภาษาไทย"),
    ]
    for no, term, definition in definitions:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(1.25)
        p.paragraph_format.first_line_indent = Cm(-1.25)
        p.paragraph_format.keep_together = True
        set_run_font(p.add_run(f"{no} {term}: "), 16, bold=True)
        set_run_font(p.add_run(definition), 16)

    add_heading(doc, "1.9 โครงสร้างของรายงาน")
    add_body(doc, "รายงานโครงงานแบ่งเป็น 5 บท ได้แก่ บทที่ 1 บทนำ บทที่ 2 ความรู้พื้นฐานและงานที่เกี่ยวข้อง บทที่ 3 วิธีดำเนินการและการออกแบบระบบ บทที่ 4 ผลการพัฒนาและผลการประเมิน และบทที่ 5 สรุปผล อภิปรายผล ข้อจำกัด และข้อเสนอแนะ การแยกเนื้อหาเช่นนี้ช่วยให้วัตถุประสงค์ วิธีทดลอง ผลลัพธ์ และข้อสรุปสามารถตรวจสอบย้อนกลับถึงกันได้")

    path = OUTPUT / "บทที่ 1_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_2():
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[2])
    add_chapter_title(doc, 2, "ความรู้พื้นฐานและงานที่เกี่ยวข้อง")
    add_chapter_overview(
        doc,
        "บทนี้อธิบายแนวคิดที่จำเป็นต่อการพัฒนา HandVox ตั้งแต่ขอบเขตของการรู้จำภาษามือด้วยคอมพิวเตอร์ การตรวจหาจุดสำคัญ การแทนลำดับการเคลื่อนไหว การจำแนก และหลักการประเมินผล โดยมีหัวข้อดังนี้",
        [
            ("2.1", "ภาษามือ การรู้จำ และการแปล"),
            ("2.2", "การรู้จำแบบภาพนิ่ง แบบแยกคำ และแบบต่อเนื่อง"),
            ("2.3", "การมองเห็นด้วยคอมพิวเตอร์และจุดสำคัญ"),
            ("2.4", "MediaPipe Holistic ในโครงงาน"),
            ("2.5", "การปรับมาตรฐานเชิงตำแหน่งและขนาด"),
            ("2.6", "การแทนลำดับการเคลื่อนไหว"),
            ("2.7", "Support Vector Machine และ RBF Kernel"),
            ("2.8", "การแบ่งข้อมูลและการป้องกันการรั่วไหลของข้อมูล"),
            ("2.9", "ตัวชี้วัดการจำแนก"),
            ("2.10", "การประมวลผลแบบเวลาจริงและเสียงพูด"),
            ("2.11", "งานและแนวคิดที่เกี่ยวข้อง"),
            ("2.12", "ความน่าเชื่อถือ จริยธรรม และการเข้าถึง"),
            ("2.13", "บทสรุป"),
        ],
    )

    add_heading(doc, "2.1 ภาษามือ การรู้จำ และการแปล")
    add_body(doc, "ภาษามือเป็นภาษาธรรมชาติที่ใช้รูปมือ ตำแหน่ง ทิศทาง การเคลื่อนไหว การแสดงสีหน้า และโครงสร้างทางภาษา การทำให้คอมพิวเตอร์ระบุหน่วยท่าหรือคำจากวิดีโอเรียกว่า การรู้จำภาษามือ (Sign Language Recognition: SLR) ส่วนการแปลภาษามือ (Sign Language Translation: SLT) ต้องแปลงลำดับภาษามือให้เป็นประโยคของภาษาปลายทางโดยคำนึงถึงโครงสร้างและบริบท ดังนั้นระบบที่ส่งออกชื่อท่าจากคลิปสั้นจึงอยู่ในกลุ่มการรู้จำแบบแยกคำ ไม่ใช่ระบบแปลภาษามือต่อเนื่อง (Yu et al., 2022; Sarhan & Frintrop, 2023)")
    add_body(doc, "การกำหนดคำเรียกให้ตรงกับความสามารถเป็นหลักสำคัญของงานวิจัย เพราะช่วยป้องกันการนำผลไปใช้เกินขอบเขต HandVox จึงจำแนกเฉพาะท่าที่ผู้พัฒนาหรือผู้ใช้เก็บไว้ในชุดข้อมูล และต้องให้ผู้ใช้กดเพิ่มคำลงในประโยค ไม่ได้แบ่งคำหรือวิเคราะห์ไวยากรณ์โดยอัตโนมัติ")

    add_heading(doc, "2.2 การรู้จำแบบภาพนิ่ง แบบแยกคำ และแบบต่อเนื่อง")
    add_table(doc, ["รูปแบบ", "ข้อมูลนำเข้า", "ผลลัพธ์", "ขอบเขต"], [
        ["ภาพนิ่ง", "หนึ่งเฟรม", "คลาสของรูปมือ", "ไม่แทนลำดับการเคลื่อนไหว"],
        ["แบบแยกคำ", "คลิปของหนึ่งท่า", "หนึ่งคำหรือหนึ่งป้ายกำกับ", "เหมาะกับท่าที่มีจุดเริ่มและสิ้นสุดชัดเจน"],
        ["แบบต่อเนื่อง", "วิดีโอหลายท่าต่อกัน", "ลำดับคำหรือประโยค", "ต้องแบ่งหน่วยท่าและจัดการบริบท"],
    ], [2.6, 3.5, 3.4, 5.15], caption="ตารางที่ 2.1 การเปรียบเทียบระดับของการรู้จำ")
    add_body(doc, "HandVox เลือกการรู้จำแบบแยกคำจากคลิป 30 เฟรม เพื่อให้ระบบรับรู้การเคลื่อนไหวของแขนและมือที่ไม่สามารถอธิบายด้วยภาพนิ่งเพียงเฟรมเดียว อย่างไรก็ดี ความยาว 30 เฟรมเป็นจำนวนตัวอย่างตามลำดับ ไม่ใช่ระยะเวลาแน่นอน เพราะระยะเวลาจริงขึ้นกับอัตราเฟรมของกล้องและภาระการประมวลผล")

    add_heading(doc, "2.3 การมองเห็นด้วยคอมพิวเตอร์และจุดสำคัญ")
    add_body(doc, "การมองเห็นด้วยคอมพิวเตอร์เป็นกระบวนการรับภาพหรือวิดีโอและสกัดข้อมูลที่ใช้ตัดสินใจได้ OpenCV ทำหน้าที่เปิดกล้อง กลับภาพในแนวนอน วาดส่วนติดต่อ และแสดงผล ส่วน MediaPipe ทำหน้าที่ประมาณพิกัดจุดสำคัญ การใช้จุดสำคัญแทนภาพดิบช่วยลดมิติข้อมูลและทำให้ตีความได้ง่ายขึ้น แต่ยังขึ้นกับคุณภาพการตรวจหา การบังมือ แสง มุมกล้อง และความเร็วของการเคลื่อนไหว")
    add_body(doc, "งาน MediaPipe Hands เสนอการตรวจหาฝ่ามือร่วมกับแบบจำลองจุดสำคัญ 21 จุดต่อมือสำหรับการทำงานแบบเวลาจริงจากกล้อง RGB (Zhang et al., 2020) ส่วน MediaPipe Holistic รวมจุดท่าทางร่างกาย ใบหน้า และมือทั้งสองข้างไว้ในกระบวนการเดียว โดยคงความสอดคล้องของด้านซ้ายและขวาระหว่างเฟรม (Google AI Edge, n.d.)")

    add_heading(doc, "2.4 MediaPipe Holistic ในโครงงาน")
    add_body(doc, "โครงงานตั้งค่า MediaPipe Holistic ให้ประมวลผลวิดีโอต่อเนื่อง (static_image_mode=False) ใช้ model_complexity=1 เปิด smooth_landmarks และกำหนด min_detection_confidence กับ min_tracking_confidence เท่ากับ 0.70 แม้ Holistic จะสามารถส่งออกจุดจำนวนมาก แต่ HandVox เลือกเฉพาะ 15 จุดของช่วงบนและจุดมือ 21 จุดต่อข้างเพื่อควบคุมขนาดข้อมูล")
    add_table(doc, ["กลุ่มจุด", "จำนวนจุด", "พิกัดต่อจุด", "จำนวนคุณลักษณะ"], [
        ["ช่วงบน: ศีรษะ ไหล่ ศอก ข้อมือ และสะโพก", "15", "x, y, z", "45"],
        ["มือซ้าย", "21", "x, y, z", "63"],
        ["มือขวา", "21", "x, y, z", "63"],
        ["รวมต่อเฟรม", "57", "3", "171"],
    ], [6.2, 2.2, 2.4, 3.85], caption="ตารางที่ 2.2 คุณลักษณะที่ HandVox เลือกใช้")
    add_body(doc, "ระบบคืนค่า None เมื่อไม่พบโครงร่างท่าทางหรือไม่พบมือทั้งสองข้าง หากพบเพียงมือเดียว ระบบแทนคุณลักษณะของมือที่ไม่พบด้วยศูนย์จำนวน 63 ค่า วิธีนี้ทำให้ทุกเฟรมมีมิติเท่ากัน แต่ต้องระวังว่าศูนย์เป็นสัญลักษณ์ของข้อมูลที่หาย ไม่ใช่ตำแหน่งมือจริง")
    add_figure(
        doc,
        LANDMARK_FIGURE,
        "ภาพที่ 2.1 จุดสำคัญที่ HandVox เลือกใช้จาก MediaPipe Holistic",
    )

    add_heading(doc, "2.5 การปรับมาตรฐานเชิงตำแหน่งและขนาด")
    add_body(doc, "พิกัดจากภาพเปลี่ยนตามตำแหน่งผู้ใช้ ระยะห่าง และขนาดตัว HandVox จึงกำหนดจุดกึ่งกลางไหล่ซ้ายและขวาเป็นจุดอ้างอิง c และใช้ระยะยูคลิดระหว่างไหล่เป็นตัวปรับขนาด s สำหรับจุด p_i พิกัดที่ปรับแล้วคำนวณเป็น p′_i = (p_i − c) / max(s, 10⁻⁶) ทั้งแกน x, y และ z")
    add_body(doc, "การปรับดังกล่าวลดผลจากการเลื่อนตำแหน่งและการเปลี่ยนขนาดโดยรวม แต่ไม่ทำให้ข้อมูลไม่แปรผันต่อการหมุน มุมกล้อง หรือสัดส่วนร่างกายทั้งหมด จึงยังต้องเก็บข้อมูลจากระยะ มุม และความเร็วที่หลากหลาย")

    add_heading(doc, "2.6 การแทนลำดับการเคลื่อนไหว")
    add_body(doc, "หนึ่งคลิปประกอบด้วย 30 เฟรมและแต่ละเฟรมมี 171 คุณลักษณะ จึงแทนได้เป็นเมทริกซ์ขนาด 30 × 171 ก่อนฝึก ระบบเรียงค่าทุกเฟรมต่อกันเป็นเวกเตอร์ 5,130 ค่า การเรียงตามลำดับเวลาเก็บข้อมูลการเคลื่อนไหวไว้ทางอ้อม เพราะตำแหน่งของคุณลักษณะในเวกเตอร์สัมพันธ์กับลำดับเฟรม")
    add_body(doc, "ข้อดีของวิธีนี้คือใช้งานร่วมกับตัวจำแนกแบบดั้งเดิมได้ง่ายและฝึกได้รวดเร็วเมื่อข้อมูลมีขนาดเล็ก ข้อจำกัดคือทุกคลิปต้องมีจำนวนเฟรมเท่ากัน และแบบจำลองอาจไวต่อความเร็วหรือจังหวะที่ต่างจากข้อมูลฝึกมาก")
    add_figure(
        doc,
        SEQUENCE_FIGURE,
        "ภาพที่ 2.2 การแทนคลิปหนึ่งท่าเป็นลำดับ 30 เฟรม",
    )

    add_heading(doc, "2.7 Support Vector Machine และ RBF Kernel")
    add_body(doc, "Support Vector Machine เป็นวิธีการเรียนรู้แบบมีผู้สอนที่สร้างขอบเขตการตัดสินใจโดยอาศัยตัวอย่างที่อยู่ใกล้ขอบเขตของคลาส แนวคิดดั้งเดิมเสนอการแปลงข้อมูลไปยังปริภูมิที่มีมิติสูงเพื่อสร้างขอบเขตที่แยกข้อมูลได้ดี (Cortes & Vapnik, 1995) RBF kernel ช่วยสร้างขอบเขตไม่เชิงเส้นและเหมาะกับความสัมพันธ์ที่ซับซ้อนระหว่างตำแหน่งจุดหลายเฟรม")
    add_body(doc, "HandVox ใช้ SVC ของ scikit-learn โดยกำหนด kernel='rbf', C=10, gamma='scale', probability=True และ class_weight='balanced' ค่า C ควบคุมการแลกเปลี่ยนระหว่างขอบเขตที่กว้างกับข้อผิดพลาดบนข้อมูลฝึก ส่วน gamma กำหนดอิทธิพลของตัวอย่างต่อรูปร่างขอบเขต การถ่วงน้ำหนักคลาสช่วยลดผลจากจำนวนคลิปที่ไม่เท่ากัน และการเปิด probability ทำให้ระบบรายงานค่าประกอบการตัดสินใจ แต่ค่าดังกล่าวไม่ควรถูกตีความเป็นการรับประกันความถูกต้องในโลกจริง")

    add_heading(doc, "2.8 การแบ่งข้อมูลและการป้องกันการรั่วไหลของข้อมูล")
    add_body(doc, "การแบ่งชุดข้อมูลฝึกและทดสอบต้องทำก่อนประเมินผล โดยใช้ข้อมูลทดสอบเฉพาะสำหรับวัดความสามารถกับตัวอย่างที่โมเดลไม่ได้ใช้ฝึก HandVox ใช้การแบ่ง 80:20 แบบ stratified และ random_state=42 เพื่อรักษาสัดส่วนคลาสและทำซ้ำได้")
    add_body(doc, "อย่างไรก็ตาม คลิปที่เก็บต่อเนื่องจากผู้ทำท่าคนเดียว เซสชันเดียว และพื้นหลังเดียวอาจคล้ายกันมาก แม้จะอยู่คนละไฟล์คลิป หากสุ่มคลิประหว่างชุดฝึกและทดสอบ คะแนนอาจสะท้อนความสามารถในการจำลักษณะของเซสชันมากกว่าความสามารถกับผู้ใช้ใหม่ แนวทางที่เข้มงวดกว่าคือแบ่งตามผู้ให้ข้อมูลหรือรอบการเก็บ (grouped split) และมีชุดทดสอบภายนอกที่แยกจากกระบวนการพัฒนา")

    add_heading(doc, "2.9 ตัวชี้วัดการจำแนก")
    add_body(doc, "Accuracy คือสัดส่วนตัวอย่างที่ทำนายถูกทั้งหมด แต่เมื่อจำนวนตัวอย่างหรือความยากของแต่ละคลาสต่างกัน ควรรายงาน precision, recall และ F1-score รายคลาส รวมถึงค่าเฉลี่ยแบบ macro ซึ่งให้น้ำหนักทุกคลาสเท่ากัน Confusion matrix ช่วยแสดงว่าท่าใดถูกสับสนกับท่าใด (Sokolova & Lapalme, 2009)")
    add_table(doc, ["ตัวชี้วัด", "ความหมาย", "การใช้ในโครงงาน"], [
        ["Accuracy", "สัดส่วนการทำนายถูกทั้งหมด", "ภาพรวมของชุดทดสอบ"],
        ["Precision", "เมื่อระบบทำนายเป็นคลาสหนึ่ง มีสัดส่วนถูกเท่าใด", "ตรวจการทำนายเกิน"],
        ["Recall", "ตัวอย่างจริงของคลาสหนึ่งถูกพบเท่าใด", "ตรวจการพลาดคลาส"],
        ["F1-score", "ค่าเฉลี่ยฮาร์มอนิกของ precision และ recall", "เปรียบเทียบรายคลาส"],
        ["Confusion matrix", "จำนวนจริงและทำนายของทุกคู่คลาส", "ค้นหาคู่ท่าที่สับสน"],
    ], [3.0, 7.0, 4.65], caption="ตารางที่ 2.3 ตัวชี้วัดที่ควรรายงาน")

    add_heading(doc, "2.10 การประมวลผลแบบเวลาจริงและเสียงพูด")
    add_body(doc, "ขณะใช้งาน ระบบเก็บคุณลักษณะล่าสุดในคิว 30 เฟรม เมื่อคิวเต็มจึงคำนวณความน่าจะเป็นของทุกคลาส รับเฉพาะผลที่มีค่าอย่างน้อย 0.40 และใช้ผลย้อนหลัง 3 ครั้งเพื่อเลือกคลาสที่พบมากที่สุด หากไม่พบมือเกิน 0.4 วินาที ระบบล้างคิวและสถานะ การประมวลผลนี้ช่วยลดการสั่นของหน้าจอ แต่ไม่ได้แทนการประเมินความถูกต้องของโมเดล")
    add_body(doc, "ผลลัพธ์สามารถเพิ่มเป็นประโยคด้วยแป้นพิมพ์และส่งให้ gTTS สร้างเสียงภาษาไทย โดย pygame เล่นไฟล์เสียงที่สร้างชั่วคราว TTS เป็นช่องทางนำเสนอผล ไม่ได้มีส่วนในการรู้จำท่าทาง และต้องใช้อินเทอร์เน็ตในขณะสร้างเสียงตามการติดตั้งปัจจุบัน")

    add_heading(doc, "2.11 งานและแนวคิดที่เกี่ยวข้อง")
    add_table(doc, ["แหล่งอ้างอิง", "ประเด็นสำคัญ", "ความสัมพันธ์กับ HandVox"], [
        ["Cortes & Vapnik (1995)", "หลักการ Support Vector Networks", "ฐานของตัวจำแนก SVM"],
        ["Zhang et al. (2020)", "การติดตามโครงร่างมือ 21 จุดแบบเวลาจริง", "ฐานของคุณลักษณะมือ"],
        ["Yu et al. (2022)", "ทบทวนงานรู้จำระดับท่าทาง คำแยก และประโยคต่อเนื่อง", "ใช้กำหนดขอบเขตการกล่าวอ้าง"],
        ["Sarhan & Frintrop (2023)", "สำรวจการรู้จำภาษามือแบบแยกคำและชุดข้อมูล", "ใช้วิเคราะห์ข้อจำกัดด้านผู้ทำท่าและข้อมูล"],
        ["Chalotonpised et al. (2026)", "ชุดข้อมูลภาษามือไทยระดับคำจากหลายผู้ทำท่า", "ใช้เปรียบเทียบขนาดข้อมูลและการทดสอบแบบ signer-independent"],
        ["Google AI Edge (n.d.)", "MediaPipe Holistic สำหรับจุดร่างกาย ใบหน้า และมือ", "กระบวนการตรวจหาจุดของระบบ"],
    ], [4.0, 5.5, 5.15], caption="ตารางที่ 2.4 งานและแนวคิดที่เกี่ยวข้อง", font_size=13)
    add_body(doc, "งาน TSL-ONE-S รายงานชุดข้อมูลภาษามือไทยระดับคำ 4,152 วิดีโอ ครอบคลุม 184 คำ จากผู้ทำท่า 29 คน และประเมินแบบแยกผู้ทำท่า (signer-independent) (Chalotonpised et al., 2026) งานดังกล่าวชี้ให้เห็นความสำคัญของความหลากหลายด้านบุคคลและสภาพแวดล้อม ดังนั้นชุดข้อมูล 350 คลิปจาก 16 ท่าของ HandVox ควรถูกอธิบายว่าเป็นชุดข้อมูลต้นแบบภายในโครงงาน ไม่ใช่หลักฐานความสามารถทั่วไปของระบบ")

    add_heading(doc, "2.12 ความน่าเชื่อถือ จริยธรรม และการเข้าถึง")
    add_body(doc, "ข้อมูลท่าทางอาจเกี่ยวข้องกับอัตลักษณ์ การเคลื่อนไหว และสภาพแวดล้อมของผู้ให้ข้อมูล การเก็บข้อมูลจากบุคคลจึงควรแจ้งวัตถุประสงค์ ขอความยินยอม จำกัดการใช้ และเก็บเฉพาะข้อมูลที่จำเป็น โครงงานปัจจุบันจัดเก็บจุดสำคัญและป้ายกำกับในไฟล์ NPZ ไม่ได้บันทึกวิดีโอต้นฉบับเป็นชุดข้อมูล แต่ภาพจากกล้องยังถูกประมวลผลในหน่วยความจำระหว่างเก็บและใช้งาน")
    add_body(doc, "ระบบควรรายงานข้อจำกัดอย่างชัดเจน ไม่อ้างว่าสามารถแทนล่ามหรือรองรับภาษามือไทยทั้งหมด และควรประเมินกับผู้ใช้หลายคนก่อนใช้งานจริง การออกแบบส่วนติดต่อควรแสดงผลที่อ่านง่าย มีทางเลือกข้อความเมื่อเสียงใช้ไม่ได้ และให้ผู้ใช้แก้ไขหรือลบคำที่ระบบทำนายผิด")

    add_heading(doc, "2.13 บทสรุป")
    add_body(doc, "HandVox เป็นระบบรู้จำท่าทางภาษามือแบบแยกคำจากลำดับ 30 เฟรม โดยใช้ MediaPipe Holistic สกัด 171 คุณลักษณะต่อเฟรม ปรับมาตรฐานด้วยตำแหน่งและระยะไหล่ เรียงเป็นเวกเตอร์ 5,130 ค่า และจำแนกด้วย SVM แบบ RBF แนวทางนี้เหมาะกับต้นแบบข้อมูลขนาดเล็กและตรวจสอบกระบวนการได้ง่าย แต่ยังต้องควบคุมการรั่วไหลของข้อมูล ทดสอบกับผู้ทำท่าและสภาพแวดล้อมใหม่ และจำกัดการกล่าวอ้างให้ตรงกับการรู้จำแบบแยกคำ")

    add_heading(doc, "รายการอ้างอิงของบท", level=1)
    refs = [
        "Bradski, G. (2000). The OpenCV Library. Dr. Dobb’s Journal of Software Tools.",
        "Cortes, C., & Vapnik, V. (1995). Support-vector networks. Machine Learning, 20, 273–297. https://doi.org/10.1007/BF00994018",
        "Chalotonpised, J., Chen, W. H., Vijitkunsawat, W., & Lin, Y. C. (2026). TSL-ONE-S: A real-world Thai sign language dataset with deep learning benchmarks. IEEE Access, 14, 37845–37870. https://doi.org/10.1109/ACCESS.2026.3670970",
        "Google AI Edge. (n.d.). Holistic landmarks detection task guide. Retrieved August 1, 2026, from https://developers.google.com/edge/mediapipe/solutions/vision/holistic_landmarker",
        "Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., Blondel, M., Prettenhofer, P., Weiss, R., Dubourg, V., Vanderplas, J., Passos, A., Cournapeau, D., Brucher, M., Perrot, M., & Duchesnay, E. (2011). Scikit-learn: Machine learning in Python. Journal of Machine Learning Research, 12(85), 2825–2830.",
        "Sarhan, N., & Frintrop, S. (2023). Unraveling a decade: A comprehensive survey on isolated sign language recognition. Proceedings of the IEEE/CVF International Conference on Computer Vision Workshops, 3210–3219. https://openaccess.thecvf.com/content/ICCV2023W/AMFG/html/Sarhan_Unraveling_a_Decade_A_Comprehensive_Survey_on_Isolated_Sign_Language_ICCVW_2023_paper.html",
        "Sokolova, M., & Lapalme, G. (2009). A systematic analysis of performance measures for classification tasks. Information Processing & Management, 45(4), 427–437. https://doi.org/10.1016/j.ipm.2009.03.002",
        "Yu, M., Jia, J., Xue, C., Yan, G., Guo, Y., & Liu, Y. (2022). A review of sign language recognition research. Journal of Intelligent & Fuzzy Systems, 43(4), 3879–3898. https://doi.org/10.3233/JIFS-210050",
        "Zhang, F., Bazarevsky, V., Vakunov, A., Tkachenka, A., Sung, G., Chang, C.-L., & Grundmann, M. (2020). MediaPipe Hands: On-device real-time hand tracking. arXiv:2006.10214. https://doi.org/10.48550/arXiv.2006.10214",
    ]
    for ref in refs:
        add_reference(doc, ref)

    path = OUTPUT / "บทที่ 2_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_3():
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[3])
    add_chapter_title(doc, 3, "วิธีดำเนินการและการออกแบบระบบ")
    add_chapter_overview(
        doc,
        "บทนี้อธิบายวิธีพัฒนา HandVox ตามซอร์สโค้ด ชุดข้อมูล และไฟล์แบบจำลองของโครงการปัจจุบัน ตั้งแต่การวิเคราะห์ความต้องการจนถึงการทดสอบและควบคุมคุณภาพ",
    )

    add_heading(doc, "3.1 รูปแบบการดำเนินโครงงาน")
    add_body(doc, "โครงงานใช้รูปแบบการวิจัยและพัฒนาเชิงทดลอง ประกอบด้วยการกำหนดข้อกำหนด การออกแบบสถาปัตยกรรม การพัฒนาซอฟต์แวร์ การสร้างชุดข้อมูลที่มีป้ายกำกับ การฝึกและประเมินแบบจำลอง และการทดสอบการใช้งานแบบเวลาจริง การตัดสินใจทุกขั้นอ้างอิงจากไฟล์โปรแกรมเพื่อให้ตรวจสอบย้อนกลับได้")

    add_heading(doc, "3.2 การวิเคราะห์ความต้องการ")
    add_table(doc, ["รหัส", "ความต้องการ", "เกณฑ์ตรวจสอบ"], [
        ["FR-01", "รับภาพจากเว็บแคมและตรวจหาช่วงบนกับมือ", "เมื่อพบ pose และมืออย่างน้อยหนึ่งข้างจึงสร้างคุณลักษณะ"],
        ["FR-02", "เก็บคลิปท่าที่มีป้ายกำกับ", "หนึ่งคลิปมี 30 เฟรม พร้อมบันทึกท่า ผู้ทำท่า และเซสชันใน Dataset V2"],
        ["FR-03", "ฝึกตัวจำแนกหลายคลาส", "มีอย่างน้อย 2 ท่าและจำนวนคลิปขั้นต่ำครบ"],
        ["FR-04", "รู้จำแบบเวลาจริง", "แสดงชื่อท่าและค่าความเชื่อมั่นเมื่อผ่านเกณฑ์"],
        ["FR-05", "จัดการคำและเสียง", "เพิ่ม/ลบ/ล้างคำ และอ่านออกเสียงได้เมื่อ TTS พร้อม"],
        ["FR-06", "จัดการท่าที่ผู้ใช้เพิ่ม", "เพิ่ม ลบ สำรองข้อมูล และฝึกใหม่ได้จากเมนู"],
    ], [2.0, 6.3, 6.35], caption="ตารางที่ 3.1 ความต้องการเชิงหน้าที่", font_size=13)
    add_table(doc, ["รหัส", "ความต้องการที่ไม่ใช่เชิงหน้าที่", "แนวทาง"], [
        ["NFR-01", "ความสอดคล้องของข้อมูล", "ใช้ฟังก์ชัน extract_features เดียวกันระหว่างเก็บและทำนาย"],
        ["NFR-02", "การทำซ้ำ", "ใช้ random_state=42 และบันทึกเวอร์ชันไลบรารี"],
        ["NFR-03", "ความเป็นส่วนตัว", "บันทึกเฉพาะคุณลักษณะและป้ายกำกับ ไม่บันทึกวิดีโอเป็นชุดข้อมูล"],
        ["NFR-04", "ความทนทาน", "ล้างสถานะเมื่อไม่พบมือ และสำรองข้อมูลก่อนลบหรือรีเซ็ต"],
    ], [2.0, 6.0, 6.65], caption="ตารางที่ 3.2 ความต้องการที่ไม่ใช่เชิงหน้าที่", font_size=13)

    add_heading(doc, "3.3 สถาปัตยกรรมระบบ")
    add_figure(
        doc,
        ASSETS / "handvox_architecture.png",
        "ภาพที่ 3.1 สถาปัตยกรรมการประมวลผลของ HandVox",
    )
    add_body(doc, "สถาปัตยกรรมแบ่งเป็น 6 ส่วน ได้แก่ การรับภาพ การตรวจหาจุด การปรับมาตรฐาน การสะสมลำดับ 30 เฟรม การจำแนกด้วย SVM และการนำเสนอผล กระบวนการเก็บข้อมูลและกระบวนการใช้งานจริงเรียกใช้ body_features.extract_features ร่วมกัน จึงลดความเสี่ยงที่รูปแบบคุณลักษณะระหว่างฝึกและทำนายไม่ตรงกัน")
    add_table(doc, ["ไฟล์", "หน้าที่หลัก", "ข้อมูลเข้า/ออก"], [
        ["body_features.py", "สกัด 171 คุณลักษณะและกรอบช่วงบน", "MediaPipe results → feature vector"],
        ["sequence_dataset.py", "จัดเก็บและจัดการคลิป", "gesture_sequences.npz"],
        ["collect_data.py", "เปิดกล้องและเก็บคลิปตามป้ายกำกับ", "30 เฟรม → 1 คลิป"],
        ["train_model.py", "แบ่งข้อมูล ฝึก SVM และบันทึกโมเดล", "NPZ → model/labels PKL"],
        ["run_detector.py", "ทำนายแบบเวลาจริงและแสดงผล", "30 เฟรมล่าสุด → คำ/เสียง"],
        ["gesture_config.py", "โหลดชื่อ คำอธิบาย และสีของท่า", "custom_gestures.json"],
    ], [4.0, 6.0, 4.65], caption="ตารางที่ 3.3 องค์ประกอบซอฟต์แวร์", font_size=13)

    add_heading(doc, "3.4 การสร้างและจัดเก็บชุดข้อมูล")
    add_body(doc, "ผู้ใช้เพิ่มชื่อท่าและคำอธิบายผ่าน add_gesture.py จากนั้น collect_data.py เปิดกล้องที่ตั้งค่าความละเอียด 1280 × 720 พิกเซล กลับภาพแนวนอน และใช้ MediaPipe Holistic ประมวลผลเฟรม เมื่อผู้ใช้กด Space โปรแกรมนับถอยหลังและเก็บเฉพาะเฟรมที่ extract_features คืนค่าครบ จนครบ 30 เฟรมจึงบันทึกเป็นหนึ่งคลิป")
    add_body(doc, "sequence_dataset.py จัดเก็บชุดรวมใน gesture_sequences.npz เป็นอาร์เรย์ชนิด float32 รูปร่าง (จำนวนคลิป, 30, 171) และเก็บป้ายกำกับเป็นข้อความ ส่วน Dataset V2 จัดเก็บลำดับ .npy วิดีโอตัวอย่าง .mp4 และ metadata เช่น ผู้ทำท่า เซสชัน เวลา และสถานะคุณภาพ เพื่อรองรับการตรวจสอบย้อนหลัง หากพบข้อมูลโครงสร้างเก่า ระบบจะสำรองไว้ก่อนเปลี่ยนแปลง")
    add_note(doc, "ข้อควบคุมการเก็บข้อมูล", "ควรเริ่มและจบท่าภายในคลิปทุกครั้ง จัดให้เห็นไหล่และมืออย่างน้อยหนึ่งข้าง และเก็บความหลากหลายด้านผู้ทำท่า แสง ระยะ มุม และความเร็วโดยไม่เปลี่ยนความหมายของท่า")
    add_figure(
        doc,
        COLLECTION_FIGURE,
        "ภาพที่ 3.2 ตัวอย่างหน้าจอเก็บคลิปท่าทางของ HandVox",
    )

    add_heading(doc, "3.5 การสกัดและปรับมาตรฐานคุณลักษณะ")
    add_body(doc, "ระบบเลือกจุด pose หมายเลข 0, 2, 5, 7–16, 23 และ 24 รวม 15 จุด พร้อมมือซ้ายและขวาข้างละ 21 จุด แต่ละจุดมีพิกัด x, y และ z รวม 171 ค่า หากไม่พบ pose หรือไม่พบมือทั้งสองข้างจะไม่รับเฟรมนั้น หากพบเพียงมือเดียวจะเติมศูนย์แทนมือที่หาย")
    add_body(doc, "ให้ c เป็นจุดกึ่งกลางระหว่างไหล่ซ้ายและขวา และ s เป็นระยะยูคลิดระหว่างไหล่ ระบบคำนวณพิกัดมาตรฐานของทุกจุดด้วย p′_i = (p_i − c) / max(s, 10⁻⁶) จากนั้นเรียงคุณลักษณะตามลำดับ pose มือซ้าย และมือขวา การใช้จุดและลำดับเดียวกันในทุกไฟล์เป็นเงื่อนไขสำคัญของความถูกต้อง")

    add_heading(doc, "3.6 สถานะชุดข้อมูลปัจจุบัน")
    add_body(doc, "การตรวจสอบไฟล์ gesture_sequences.npz ณ วันที่ 16 สิงหาคม 2569 พบข้อมูล 350 คลิป รูปร่างอาร์เรย์ (350, 30, 171) ชนิด float32 และ 16 ป้ายกำกับ จำนวนต่อคลาสไม่เท่ากันตั้งแต่ 10–30 คลิป ดังตารางที่ 3.4 นอกจากนี้ Dataset V2 มี 230 คลิปที่สถานะ accepted จากผู้ทำท่า 2 รหัสและ 2 เซสชัน ส่วนข้อมูลฐานเดิม 120 คลิปยังไม่มี metadata ระดับผู้ทำท่าและเซสชัน")
    add_table(doc, ["กลุ่มป้ายกำกับ", "จำนวนต่อท่า", "รวมคลิป", "สถานะข้อมูล"], [
        ["ขอบคุณ, ขอโทษ, สวัสดี, ไม่เป็นไร", "30", "120", "ข้อมูลฐานเดิม; ไม่มี metadata รายคลิป"],
        ["กิน, ช่วยด้วย, ต้องการ, น้ำ, หมอ, หยุด, ห้องน้ำ, เข้าใจ, เจ็บ, ใช่, ไม่เข้าใจ", "20", "220", "Dataset V2; accepted"],
        ["ไม่ใช่", "10", "10", "Dataset V2; accepted"],
        ["รวม 16 ป้ายกำกับ", "10–30", "350", "30 เฟรม × 171 ค่าต่อคลิป"],
    ], [6.6, 2.3, 2.2, 3.55], caption="ตารางที่ 3.4 ผลการตรวจสอบชุดข้อมูลปัจจุบัน", font_size=13)
    add_body(doc, "จำนวนดังกล่าวเพียงพอสำหรับทดลองตัวจำแนกต้นแบบ แต่ยังไม่เพียงพอสำหรับสรุปความสามารถทั่วไป เพราะข้อมูลฐานเดิมขาด metadata และ Dataset V2 ยังมีผู้ทำท่าเพียง 2 รหัส จำนวนคลิปต่อคลาสไม่สมดุล และยังไม่มีชุดทดสอบภายนอก")

    add_heading(doc, "3.7 การฝึกแบบจำลอง")
    add_body(doc, "กระบวนการทดลองตรวจสอบรายชื่อป้ายกำกับและมิติข้อมูล ใช้ LabelEncoder แปลงชื่อท่าเป็นรหัสจำนวนเต็ม เรียงเมทริกซ์ 30 × 171 เป็นเวกเตอร์ 5,130 ค่า และแบ่งข้อมูลแบบ stratified holdout 80:20 เพื่อคัดกรองเบื้องต้น การตั้งค่าโครงการกำหนดเป้าหมายมาตรฐานไว้เป็น leave-one-signer-out เมื่อมีข้อมูลผู้ทำท่าครบสำหรับทุกคลาส")
    add_table(doc, ["รายการ", "ค่าที่ใช้", "ผลจากข้อมูลปัจจุบัน"], [
        ["จำนวนข้อมูล", "350 คลิป", "16 คลาส; 10–30 คลิปต่อคลาส"],
        ["การแบ่งข้อมูลรอบปัจจุบัน", "80:20 แบบ stratified", "ฝึก 280 คลิป; ทดสอบ 70 คลิป"],
        ["ตัวจำแนก", "SVC", "หลายคลาสผ่าน scikit-learn"],
        ["Kernel", "RBF", "ขอบเขตไม่เชิงเส้น"],
        ["C", "10", "ค่าคงที่ตามซอร์สโค้ด"],
        ["gamma", "scale", "คำนวณจากจำนวนคุณลักษณะและความแปรปรวน"],
        ["probability", "True", "ใช้ predict_proba ในเวลาจริง"],
        ["class_weight", "balanced", "ถ่วงน้ำหนักตามจำนวนตัวอย่างแต่ละคลาส"],
        ["ไฟล์ผลลัพธ์", "gesture_model.pkl, gesture_labels.pkl", "แบบจำลองและตัวเข้ารหัสป้ายกำกับ"],
    ], [4.2, 6.1, 4.35], caption="ตารางที่ 3.5 การตั้งค่าการฝึก", font_size=13)

    add_heading(doc, "3.8 การทำงานแบบเวลาจริง")
    add_item(doc, "1)", "โหลด gesture_model.pkl และ gesture_labels.pkl และตรวจว่ารายชื่อคลาสตรงกับ gesture_config.py")
    add_item(doc, "2)", "เปิด MediaPipe Holistic และเว็บแคม จากนั้นสกัดคุณลักษณะของทุกเฟรมที่ผ่านเงื่อนไข")
    add_item(doc, "3)", "สะสมคุณลักษณะล่าสุด 30 เฟรมใน motion_frames และเรียงเป็นเวกเตอร์ 5,130 ค่า")
    add_item(doc, "4)", "คำนวณ predict_proba เลือกคลาสที่มีค่าสูงสุด และรับผลเมื่อค่าความเชื่อมั่นไม่น้อยกว่า 0.40")
    add_item(doc, "5)", "เก็บผลย้อนหลัง 3 ครั้ง เลือกคลาสที่พบมากที่สุด และเฉลี่ยค่าความเชื่อมั่นของคลาสนั้น")
    add_item(doc, "6)", "ล้างคิวและสถานะเมื่อไม่พบมือนานกว่า 0.4 วินาที เพื่อลดการค้างของคำทำนายเดิม")
    add_item(doc, "7)", "แสดงกรอบ ชื่อท่า ค่าความเชื่อมั่น ประโยค และสถานะเสียงบนหน้าจอ")

    add_heading(doc, "3.9 ส่วนติดต่อผู้ใช้และการแปลงข้อความเป็นเสียง")
    add_table(doc, ["ปุ่ม", "การทำงาน", "ข้อควบคุม"], [
        ["Space", "เพิ่มคำที่ยืนยันแล้วลงในประโยค", "หน่วงอย่างน้อย 1 วินาทีระหว่างการเพิ่ม"],
        ["Backspace", "ลบคำล่าสุด", "ทำงานเมื่อประโยคไม่ว่าง"],
        ["Enter", "ล้างประโยค", "ลบรายการคำทั้งหมด"],
        ["S", "อ่านประโยค", "ทำงานเมื่อมีข้อความและ TTS พร้อม"],
        ["Esc", "ออกจากโปรแกรม", "คืนกล้องและปิดหน้าต่าง"],
    ], [2.5, 6.0, 6.15], caption="ตารางที่ 3.6 ปุ่มควบคุมขณะตรวจจับ", font_size=13)
    add_body(doc, "ระบบยังอ่านชื่อท่าอัตโนมัติเมื่อท่าเดียวกันถูกยืนยันต่อเนื่องครบ 1 วินาที และอนุญาตให้พูดซ้ำหลังผู้ใช้เอามือออกจนระบบรีเซ็ต การสร้างเสียงทำในเธรดแยกเพื่อไม่ให้วงรอบภาพหยุดรอจนเสียงเล่นจบ")

    add_heading(doc, "3.10 แผนการประเมินผล")
    add_heading(doc, "3.10.1 การประเมินภายในชุดข้อมูล", 2)
    add_item(doc, "1)", "รายงาน accuracy บนชุดทดสอบ 70 คลิป พร้อมจำนวนที่ทำนายถูกและผิด")
    add_item(doc, "2)", "รายงาน confusion matrix, precision, recall และ F1-score รายคลาส รวมทั้ง macro average")
    add_item(doc, "3)", "บันทึกเวอร์ชันข้อมูล รายชื่อคลาส random_state และเวลาที่ฝึก เพื่อทำซ้ำผลได้")
    add_note(doc, "สถานะผลประเมิน", "การทดลองด่วนล่าสุดใช้ stratified holdout 80:20 บนข้อมูล 350 คลิป ได้ Accuracy 94.29% และ Macro F1 93.75% ผลนี้ใช้คัดกรองเบื้องต้นเท่านั้น เพราะข้อมูลฐานเดิมขาด metadata และยังไม่ใช่การประเมินแบบแยกผู้ทำท่า")
    add_heading(doc, "3.10.2 การประเมินกับข้อมูลภายนอก", 2)
    add_body(doc, "ก่อนสรุปว่าระบบใช้ได้กับผู้ใช้ทั่วไป ควรสร้างชุดทดสอบที่แยกตามผู้ให้ข้อมูลและรอบการเก็บ โดยไม่ให้คลิปของบุคคลหรือเซสชันทดสอบอยู่ในชุดฝึก ควรทดสอบแสง ฉากหลัง ระยะ มุมกล้อง ความเร็ว มือข้างเดียวและสองข้าง และบันทึกเวลาแฝงตั้งแต่รับภาพจนแสดงผล")
    add_heading(doc, "3.10.3 การทดสอบเชิงหน้าที่", 2)
    add_table(doc, ["กรณีทดสอบ", "ผลที่คาดหวัง"], [
        ["ไม่พบ pose หรือมือ", "ไม่เพิ่มเฟรมและไม่ทำนาย"],
        ["คลิปของท่าไม่ครบ 30", "ไม่อนุญาตให้ฝึกและแจ้งรายชื่อท่าที่ยังไม่ครบ"],
        ["มีเพียง 1 คลาส", "ไม่ฝึกตัวจำแนกหลายคลาส"],
        ["โมเดลไม่ตรงกับรายการท่า", "หยุดและแจ้งให้ฝึกใหม่"],
        ["ความเชื่อมั่นต่ำกว่า 0.40", "ไม่ยืนยันชื่อท่า"],
        ["ไม่พบมือนานกว่า 0.4 วินาที", "ล้างคิว สถานะ และตัวจับเวลาพูด"],
        ["TTS ใช้งานไม่ได้", "ระบบรู้จำยังทำงานและแสดงข้อความได้"],
    ], [7.0, 7.65], caption="ตารางที่ 3.7 กรณีทดสอบเชิงหน้าที่", font_size=13)

    add_heading(doc, "3.11 การควบคุมคุณภาพและจริยธรรมข้อมูล")
    add_item(doc, "1)", "ใช้คำอธิบายท่าและป้ายกำกับที่ไม่ซ้ำ ตรวจการสะกดก่อนเก็บ และฝึกใหม่ทุกครั้งเมื่อเปลี่ยนรายการท่า")
    add_item(doc, "2)", "เก็บ metadata ของผู้ให้ข้อมูล เซสชัน สภาพแสง ระยะ และกล้องในรุ่นถัดไป เพื่อรองรับการแบ่งข้อมูลแบบกลุ่ม")
    add_item(doc, "3)", "ขอความยินยอมจากผู้ให้ข้อมูล ระบุวัตถุประสงค์ ระยะเวลาเก็บ และสิทธิในการถอนข้อมูล")
    add_item(doc, "4)", "ไม่ใช้ค่าความเชื่อมั่นแทนหลักฐานความถูกต้อง และไม่ใช้ระบบในบริบทสำคัญโดยไม่มีการยืนยันจากมนุษย์")
    add_item(doc, "5)", "รายงานจำนวนผู้ให้ข้อมูลและเงื่อนไขการทดสอบในบทที่ 4 เพื่อให้ผู้อ่านประเมินความสามารถทั่วไปของผลได้")

    # Keep the five quality-control items together in a compact academic list
    # so the chapter conclusion is not stranded on a nearly blank page.
    for paragraph in doc.paragraphs[-5:]:
        paragraph.paragraph_format.line_spacing = 1.0
        paragraph.paragraph_format.space_after = Pt(0)

    add_heading(doc, "3.12 บทสรุป")
    summary_paragraphs = [
        add_body(doc, "HandVox ใช้ MediaPipe Holistic สกัด 171 คุณลักษณะต่อเฟรม เก็บ 30 เฟรมเป็นเวกเตอร์ 5,130 ค่า และฝึก SVM แบบ RBF ข้อมูลปัจจุบันมี 350 คลิปจาก 16 ท่า การทดลองด่วนแบ่งฝึก 280 คลิปและทดสอบ 70 คลิป แต่ยังเป็น holdout ระดับคลิป จึงต้องประเมินแบบแยกผู้ทำท่าและสภาพแวดล้อมใหม่ก่อนสรุปการใช้งานจริง"),
    ]
    for paragraph in summary_paragraphs:
        paragraph.paragraph_format.line_spacing = 0.95
        paragraph.paragraph_format.space_after = Pt(0)
        for run in paragraph.runs:
            run.font.size = Pt(14)

    path = OUTPUT / "บทที่ 3_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_4():
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[4])
    add_chapter_title(doc, 4, "ผลการดำเนินงานและการประเมินผล")

    add_heading(doc, "4.1 ผลการจัดเตรียมและตรวจสอบข้อมูล")
    add_body(doc, "ไฟล์ gesture_sequences.npz เก็บข้อมูลเป็นอาร์เรย์สามมิติชนิด float32 รูปร่าง (350, 30, 171) หนึ่งคลิปแทนการทำท่าหนึ่งครั้งด้วยข้อมูล 30 เฟรม แต่ละเฟรมมี 171 คุณลักษณะ เมื่อนำมาเรียงสำหรับ SVM จึงมี 5,130 ค่าต่อคลิป ชุดข้อมูลมี 16 ป้ายกำกับและจำนวนตัวอย่างต่อคลาสอยู่ระหว่าง 10–30 คลิป")
    add_body(doc, "การตรวจสอบเชิงโครงสร้างไม่พบค่า NaN หรือ infinity และไม่พบคลิปซ้ำกันทุกค่าแบบตรงตัว สัดส่วนค่าศูนย์ประมาณ 12.93% ซึ่งรวมทั้งค่าที่เกิดจากการเติมศูนย์เมื่อไม่พบมือและค่าศูนย์จริงในข้อมูลที่ปรับมาตรฐานแล้ว Dataset V2 มี 230 คลิปสถานะ accepted จากผู้ทำท่า 2 รหัสและ 2 เซสชัน ส่วนข้อมูลฐานเดิม 120 คลิปไม่มี metadata ระดับผู้ทำท่าและเซสชัน")
    add_table(doc, ["รายการ", "ผลที่ตรวจสอบได้", "ความหมาย"], [
        ["รูปร่างชุดข้อมูล", "350 × 30 × 171", "350 คลิป; คลิปละ 30 เฟรม; เฟรมละ 171 ค่า"],
        ["ป้ายกำกับ", "16 ป้ายกำกับ", "4 คลาสเดิมและ 12 คลาสจาก Dataset V2"],
        ["จำนวนต่อป้ายกำกับ", "10–30 คลิป", "ข้อมูลยังไม่สมดุล; ใช้ class_weight=balanced"],
        ["ชนิดข้อมูล", "float32", "สอดคล้องกับขั้นตอนจัดเก็บและทำนาย"],
        ["ค่าที่ไม่เป็นจำนวนจำกัด", "ไม่พบ", "ทุกค่าผ่านการตรวจ finite"],
        ["คลิปซ้ำแบบตรงตัว", "0 คลิป", "คลิปทั้ง 350 รายการมีเวกเตอร์ต่างกัน"],
        ["สัดส่วนค่าศูนย์", "12.93%", "รวมศูนย์จากมือที่ไม่พบและค่าที่เป็นศูนย์จริง"],
        ["Dataset V2", "230 accepted", "12 ท่า; person_01/02; session_01/02"],
    ], [4.0, 4.2, 6.45], caption="ตารางที่ 4.1 ผลการตรวจสอบชุดข้อมูล HandVox", font_size=13)
    add_note(doc, "ขอบเขตหลักฐาน", "metadata มีเฉพาะ 230 คลิปใน Dataset V2 แต่ข้อมูลฐานเดิม 120 คลิปไม่มีรหัสผู้ทำท่าและเซสชัน การทดลองรวมทั้งสองแหล่งจึงยังแบ่งแบบ signer-independent อย่างน่าเชื่อถือไม่ได้")

    add_heading(doc, "4.2 การตั้งค่าการทดลองด่วน")
    add_body(doc, "การทดลองรหัส quick_20260816_152804_809320 ใช้ข้อมูล 350 คลิป แบ่งแบบ stratified holdout 80:20 เป็นชุดฝึก 280 คลิปและชุดทดสอบ 70 คลิป ใช้ SVC แบบ RBF กำหนด C=10, gamma='scale', probability=True และ class_weight='balanced' การทดลองนี้สร้างเพื่อคัดกรองโมเดลก่อนเปิดกล้องทดลองจริง ไม่ใช่ผลประเมินมาตรฐานสำหรับยืนยันการใช้งานทั่วไป")
    add_table(doc, ["รายการ", "ค่าที่ใช้หรือผลลัพธ์", "รายละเอียด"], [
        ["การแบ่งข้อมูล", "80:20 แบบ stratified", "ฝึก 280 คลิป; ทดสอบ 70 คลิป"],
        ["Random state", "42", "ทำซ้ำการแบ่งเดิมได้"],
        ["โมเดล", "SVC, RBF, C=10, gamma=scale", "probability=True; class_weight=balanced"],
        ["จำนวนคลาส", "16", "คลาสละ 2–6 ตัวอย่างในชุดทดสอบ"],
        ["ชนิดการทดลอง", "quick trial", "ใช้คัดกรองเบื้องต้นก่อนทดสอบกล้องจริง"],
        ["ลายนิ้วมือข้อมูล", "SHA-256: ab45c8…0624d", "ระบุชุดข้อมูลที่ใช้สร้างผลนี้"],
    ], [4.1, 4.4, 6.15], caption="ตารางที่ 4.2 การตั้งค่าการทดลองด่วน", font_size=13)

    add_heading(doc, "4.3 ผลการประเมินภาพรวม")
    add_body(doc, "แบบจำลองทำนายถูก 66 จาก 70 คลิปและผิด 4 คลิป คิดเป็น Accuracy 94.29% ค่า Macro precision, Macro recall และ Macro F1 เท่ากับ 93.75% ส่วนค่า weighted precision, recall และ F1 เท่ากับ 94.29% เกณฑ์ยอมรับที่กำหนดไว้สำหรับการทดลองด่วนผ่านทั้ง Accuracy, Macro F1 และค่าต่ำสุดของ recall ที่มองเห็นได้")
    add_table(doc, ["ตัวชี้วัด", "ผลลัพธ์", "การตีความภายในรอบทดลอง"], [
        ["ทำนายถูก / ผิด", "66 / 4 คลิป", "ชุดทดสอบรวม 70 คลิป"],
        ["Accuracy", "94.29%", "สูงกว่าเกณฑ์คัดกรอง 70%"],
        ["Macro precision", "93.75%", "ให้ทุกคลาสมีน้ำหนักเท่ากัน"],
        ["Macro recall", "93.75%", "สองคลาสมี recall ต่ำกว่าคลาสอื่น"],
        ["Macro F1", "93.75%", "สูงกว่าเกณฑ์คัดกรอง 70%"],
        ["Weighted F1", "94.29%", "ถ่วงตามจำนวนตัวอย่างในชุดทดสอบ"],
        ["ผลตามเกณฑ์", "ผ่าน", "ผ่านเกณฑ์สำหรับ quick trial เท่านั้น"],
    ], [4.0, 3.3, 7.35], caption="ตารางที่ 4.3 ผลการประเมินภาพรวม", font_size=13)

    add_heading(doc, "4.4 ผลรายป้ายกำกับและความสับสน")
    add_body(doc, "จำนวน 14 จาก 16 คลาส ได้แก่ กิน ขอบคุณ ขอโทษ ช่วยด้วย ต้องการ น้ำ สวัสดี หมอ หยุด ห้องน้ำ เจ็บ ใช่ ไม่เป็นไร และไม่ใช่ มี precision, recall และ F1 เท่ากับ 1.000 ส่วน “เข้าใจ” และ “ไม่เข้าใจ” มีค่าเท่ากับ 0.500 โดยตัวอย่างจริงของแต่ละคลาส 2 จาก 4 คลิปถูกทำนายสลับกัน จึงควรเก็บข้อมูลเพิ่มและทบทวนความแตกต่างของท่า")
    add_table(doc, ["ป้ายกำกับ", "Support", "Precision", "Recall", "F1"], [
        ["14 คลาสที่ระบุในย่อหน้าก่อนตาราง", "2–6 ต่อคลาส", "1.000", "1.000", "1.000"],
        ["เข้าใจ", "4", "0.500", "0.500", "0.500"],
        ["ไม่เข้าใจ", "4", "0.500", "0.500", "0.500"],
        ["Macro average", "70", "0.9375", "0.9375", "0.9375"],
    ], [7.3, 2.3, 1.75, 1.75, 1.55], caption="ตารางที่ 4.4 ผลการจำแนกรายป้ายกำกับ", font_size=12)
    add_figure(doc, CONFUSION_FIGURE, "ภาพที่ 4.1 Confusion matrix ของการทดลอง HandVox 16 ท่า")
    add_note(doc, "การตีความ", "ผลนี้มาจากการสุ่มระดับคลิปในชุดข้อมูลรวมเดียวกัน จึงแสดงความสามารถในการแยกตัวอย่างภายในชุดปัจจุบัน แต่ยังไม่พิสูจน์ความแม่นยำกับผู้ทำท่า เซสชัน กล้อง หรือสภาพแวดล้อมใหม่")

    add_heading(doc, "4.5 ผลการพัฒนาระบบใช้งานแบบเวลาจริง")
    add_body(doc, "การตรวจซอร์สโค้ดยืนยันว่ากระบวนการเก็บข้อมูลและใช้งานจริงเรียกใช้ extract_features เดียวกัน โหลดโมเดลกับตัวเข้ารหัสป้ายกำกับ ตรวจจำนวนคุณลักษณะ 5,130 ค่า และตรวจว่ารายชื่อคลาสตรงกับ gesture_config.py ก่อนเริ่มทำนาย ขั้นตอนเหล่านี้ลดความเสี่ยงจากความไม่สอดคล้องระหว่างข้อมูลฝึกกับข้อมูลใช้งาน")
    add_table(doc, ["ความสามารถ", "ผลการพัฒนาที่ตรวจจากซอร์ส", "หลักฐาน/เงื่อนไข"], [
        ["ทำนายจากการเคลื่อนไหว", "สะสม 30 เฟรมล่าสุดแล้วใช้ predict_proba", "run_detector.py"],
        ["เกณฑ์ความเชื่อมั่น", "ยืนยันเมื่อค่าสูงสุดไม่น้อยกว่า 0.40", "ยังต้องปรับจากข้อมูลภายนอก"],
        ["ลดการสั่นของคำ", "ลงคะแนนจากผลล่าสุด 3 ครั้งและเฉลี่ยความเชื่อมั่น", "ช่วยให้หน้าจอนิ่งขึ้น"],
        ["รีเซ็ตสถานะ", "ล้างคิวเมื่อไม่พบมือนานกว่า 0.4 วินาที", "ป้องกันคำเดิมค้าง"],
        ["อ่านเสียงอัตโนมัติ", "ค้างท่า 1 วินาทีแล้วเรียก gTTS ในเธรดแยก", "ต้องมีอินเทอร์เน็ตและเสียงพร้อม"],
        ["สร้างประโยค", "เพิ่ม ลบ ล้าง และอ่านคำที่สะสม", "Space, Backspace, Enter, S"],
        ["เพิ่ม/ลบท่า", "จัดการรายการ เก็บคลิป สำรอง และฝึกใหม่", "เมนูและไฟล์ BAT"],
    ], [3.4, 6.5, 4.75], caption="ตารางที่ 4.6 ผลการพัฒนาความสามารถของระบบ", font_size=13)
    add_figure(
        doc,
        ROOT / "qa" / "gui_dashboard_current.png",
        "ภาพที่ 4.2 หน้าจอภาพรวมและสถานะความพร้อมของระบบ HandVox",
    )
    add_body(doc, "ผลด้านส่วนติดต่อข้างต้นเป็นหลักฐานจากโค้ดและไฟล์กำหนดค่า ยังไม่มีบันทึกการทดสอบภาคสนาม เช่น FPS เฉลี่ย เวลาแฝง อัตราความผิดพลาดต่อเนื่อง ความสำเร็จของ TTS หรือความพึงพอใจของผู้ใช้ จึงไม่นำค่าดังกล่าวมารายงานโดยคาดเดา")

    add_heading(doc, "4.6 ข้อจำกัดในการตีความผล")
    add_item(doc, "1)", "ข้อมูลฐานเดิม 120 คลิปไม่มีตัวระบุผู้ทำท่าและเซสชัน จึงตรวจการรั่วไหลเชิงบุคคลหรือเซสชันไม่ได้")
    add_item(doc, "2)", "Dataset V2 มีเพียง 2 รหัสผู้ทำท่าและ 2 เซสชัน และยังไม่ครอบคลุมทุกคลาสเดิมในรูปแบบ metadata เดียวกัน")
    add_item(doc, "3)", "จำนวนคลิปต่อคลาสไม่เท่ากันตั้งแต่ 10–30 คลิป และชุดทดสอบบางคลาสมีเพียง 2 ตัวอย่าง")
    add_item(doc, "4)", "ตัวชี้วัดมาจาก stratified holdout ภายในชุดเดียว ไม่มีชุดทดสอบภายนอกหรือผล leave-one-signer-out ที่ครอบคลุมทั้ง 16 ท่า")
    add_item(doc, "5)", "ยังไม่วัดเวลาแฝง FPS ความทนทานต่อแสง ฉากหลัง ระยะ มุมกล้อง การบังมือ หรือความเร็วการทำท่าที่ต่างจากชุดฝึก")
    add_item(doc, "6)", "ยังไม่มีการประเมินร่วมกับผู้ใช้ภาษามือหรือผู้เชี่ยวชาญ และคำอธิบายป้ายกำกับหลายรายการยังรอตรวจสอบรูปแบบภาษามือไทย")

    add_heading(doc, "4.7 สรุปผลการดำเนินงาน")
    add_body(doc, "HandVox รุ่นปัจจุบันใช้ข้อมูล 350 คลิปจาก 16 ท่า คลิปละ 30 เฟรมและ 171 คุณลักษณะต่อเฟรม การทดลองด่วนด้วย SVC แบบ RBF ทำนายถูก 66 จาก 70 คลิป ให้ Accuracy 94.29% และ Macro F1 93.75% ความผิดพลาดทั้งหมดในรอบนี้เกิดจากการสับสนระหว่าง “เข้าใจ” กับ “ไม่เข้าใจ”")
    add_body(doc, "อย่างไรก็ตาม คะแนนดังกล่าวยังไม่เป็นหลักฐานของการใช้งานทั่วไป เพราะการประเมินสุ่มในระดับคลิปและข้อมูลบางส่วนไม่มี metadata ผู้ทำท่าหรือเซสชัน บทที่ 5 จึงอภิปรายผลภายใต้ข้อจำกัดนี้และเสนอแนวทางเก็บข้อมูล ทดสอบ และปรับปรุงระบบต่อไป")

    path = OUTPUT / "บทที่ 4_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_5():
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[5])
    add_chapter_title(doc, 5, "สรุปผล อภิปรายผล และข้อเสนอแนะ")

    add_heading(doc, "5.1 สรุปผลการพัฒนา")
    add_body(doc, "โครงงานได้พัฒนา HandVox ซึ่งรับภาพเว็บแคม ใช้ MediaPipe Holistic สกัดจุดช่วงบน 15 จุดและมือข้างละ 21 จุด รวม 171 คุณลักษณะต่อเฟรม ปรับมาตรฐานด้วยจุดกึ่งกลางและระยะระหว่างไหล่ สะสม 30 เฟรมเป็นเวกเตอร์ 5,130 ค่า และใช้ SVC แบบ RBF จำแนกท่าที่กำหนดไว้ล่วงหน้า")
    add_body(doc, "ระบบรองรับวงจรตั้งแต่เพิ่มชื่อท่า เก็บคลิป ตรวจความพร้อมของข้อมูล ฝึกแบบจำลอง บันทึกโมเดล ใช้งานแบบเวลาจริง แสดงค่าความเชื่อมั่น สะสมคำเป็นประโยค อ่านเสียงภาษาไทย และลบท่าพร้อมสำรองข้อมูล ชุดข้อมูลปัจจุบันมี 16 ท่า รวม 350 คลิป โดยแต่ละท่ามี 10–30 คลิป")
    add_body(doc, "การทดลองด่วนแบบ stratified holdout 80:20 ทำนายถูก 66 จาก 70 คลิป ให้ Accuracy 94.29% และ Macro F1 93.75% คลาส “เข้าใจ” กับ “ไม่เข้าใจ” มี F1 เท่ากับ 0.500 และถูกทำนายสลับกัน อย่างไรก็ตาม ตัวเลขนี้สะท้อนเฉพาะการแบ่งระดับคลิปภายในชุดข้อมูลเดียวกันและยังไม่ใช่ผล signer-independent")
    add_table(doc, ["ด้าน", "ผลการพัฒนาที่ตรวจสอบได้"], [
        ["ข้อมูล", "350 คลิป × 30 เฟรม × 171 คุณลักษณะ; 16 ป้ายกำกับ"],
        ["แบบจำลอง", "SVC แบบ RBF, C=10, gamma=scale, probability=True, class_weight=balanced"],
        ["การประเมิน", "Holdout 66/70 ถูก; Accuracy 94.29%; Macro F1 93.75%"],
        ["ระบบเวลาจริง", "หน้าต่าง 30 เฟรม เกณฑ์ 0.40 และ smoothing 3 ผลล่าสุด"],
        ["การนำเสนอ", "ชื่อท่า ความเชื่อมั่น ประโยค และเสียงภาษาไทย"],
        ["การจัดการ", "เพิ่ม/ลบท่า เก็บคลิป ฝึกใหม่ และสำรองข้อมูล"],
    ], [3.8, 10.85], caption="ตารางที่ 5.1 สรุปผลการพัฒนา HandVox")

    add_heading(doc, "5.2 ผลสำเร็จตามวัตถุประสงค์")
    add_table(doc, ["วัตถุประสงค์", "ผลที่ได้", "สถานะและหลักฐาน"], [
        ["รู้จำท่าจากลำดับภาพแบบเวลาจริง", "พัฒนาท่อประมวลผล 30 เฟรมและ SVM", "บรรลุในระดับต้นแบบ; run_detector.py"],
        ["เพิ่ม/ลบท่าและฝึกใหม่โดยไม่แก้โค้ด", "มีเมนู ไฟล์ BAT และ custom_gestures.json", "บรรลุตามฟังก์ชันที่พัฒนา"],
        ["แสดงข้อความ ประโยค และเสียงไทย", "มีชื่อท่า ความเชื่อมั่น ตัวแก้ไขประโยค และ TTS", "บรรลุตามซอร์ส; TTS ต้องทดสอบเครือข่ายจริง"],
        ["ประเมินผลและระบุข้อจำกัด", "มี holdout รายคลาสและ confusion matrix", "บรรลุสำหรับ quick trial; signer-independent ยังไม่เสร็จ"],
    ], [5.8, 5.0, 3.85], caption="ตารางที่ 5.2 ผลสำเร็จเทียบกับวัตถุประสงค์", font_size=13)

    add_heading(doc, "5.3 อภิปรายผล")
    add_heading(doc, "5.3.1 ความหมายของผลการประเมิน", 2)
    add_body(doc, "Accuracy 94.29% และ Macro F1 93.75% แสดงว่าคุณลักษณะลำดับ 5,130 ค่าและ SVM แยกตัวอย่างส่วนใหญ่ในชุดข้อมูลปัจจุบันได้ แต่ผลรายคลาสชี้จุดอ่อนชัดเจนที่คู่ “เข้าใจ” กับ “ไม่เข้าใจ” ซึ่งมี precision, recall และ F1 เท่ากับ 0.500 จึงควรทบทวนความแตกต่างของท่าและเก็บตัวอย่างที่หลากหลายขึ้น")
    add_body(doc, "แม้คะแนนรวมผ่านเกณฑ์คัดกรอง แต่ยังไม่ควรสรุปว่าระบบทำงานกับผู้ใช้ทั่วไป เพราะคลิปจากคนหรือเซสชันเดียวกันอาจถูกสุ่มไปอยู่ทั้งชุดฝึกและชุดทดสอบ อีกทั้งข้อมูลฐานเดิมไม่มี metadata ที่ใช้ตรวจสอบการรั่วไหลได้")

    add_heading(doc, "5.3.2 ผลของการใช้ข้อมูลลำดับการเคลื่อนไหว", 2)
    add_body(doc, "การเปลี่ยนจากภาพนิ่งหนึ่งเฟรมเป็นลำดับ 30 เฟรมทำให้ข้อมูลคงลำดับการเคลื่อนไหวของแขนและมือไว้ และการใช้จุดช่วงบนร่วมกับมือสองข้างช่วยอธิบายตำแหน่งสัมพันธ์กับร่างกายได้มากขึ้นกว่าคุณลักษณะมือข้างเดียว อย่างไรก็ดี การเรียงทุกเฟรมเป็นเวกเตอร์ยาวทำให้โมเดลไวต่อจังหวะและกำหนดให้ทุกคลิปยาวเท่ากัน")

    add_heading(doc, "5.3.3 การใช้งานแบบเวลาจริง", 2)
    add_body(doc, "เกณฑ์ความเชื่อมั่น 0.40 การรวมผลล่าสุด 3 ครั้ง และการรีเซ็ตเมื่อไม่พบมือ 0.4 วินาทีเป็นกลไกจัดการผลหลังการทำนาย ช่วยให้ข้อความบนหน้าจอมีเสถียรภาพและลดคำเดิมค้าง แต่ยังไม่มีการทดลองเปรียบเทียบค่าพารามิเตอร์เหล่านี้กับอัตราความผิดพลาดหรือเวลาแฝง")
    add_body(doc, "การสะสมคำและเสียงไทยช่วยให้ผู้ใช้ส่งผลลัพธ์ต่อไปยังผู้ฟังได้ แต่ไม่ใช่การวิเคราะห์ไวยากรณ์ภาษามือ ประโยคเกิดจากการเลือกคำทีละคำของผู้ใช้ และ gTTS ต้องใช้อินเทอร์เน็ตขณะสร้างเสียงตามสถาปัตยกรรมปัจจุบัน")

    add_heading(doc, "5.4 ข้อจำกัดของโครงงาน")
    add_table(doc, ["ประเด็น", "ข้อจำกัด", "ผลต่อข้อสรุป"], [
        ["ขอบเขตภาษา", "รู้จำ 16 ท่าแบบแยกคำ", "ไม่เท่ากับการแปลภาษามือไทยต่อเนื่อง"],
        ["ผู้ทำท่า", "Dataset V2 มี 2 รหัส; ข้อมูลฐานเดิมไม่มีรหัส", "ยังประเมินแยกผู้ทำท่าครบทุกคลาสไม่ได้"],
        ["เซสชัน", "Dataset V2 มี 2 เซสชัน; ข้อมูลเดิมไม่ระบุ", "ยังตรวจการรั่วไหลทั้งชุดไม่ได้"],
        ["การประเมิน", "สุ่มแบ่งระดับคลิปจากชุดเดียวกัน", "คะแนนอาจสูงกว่าการใช้งานกับข้อมูลใหม่"],
        ["ข้อมูล", "350 คลิป; 10–30 คลิปต่อคลาส; ไม่มีชุดทดสอบภายนอก", "ยังสรุปความสามารถทั่วไปไม่ได้"],
        ["ความเร็ว", "ไม่มีบันทึก FPS และเวลาแฝง", "ยังสรุปสมรรถนะเวลาจริงเชิงปริมาณไม่ได้"],
        ["เสียง", "gTTS พึ่งอินเทอร์เน็ต", "เสียงอาจไม่พร้อมในพื้นที่เครือข่ายไม่เสถียร"],
        ["ผู้ใช้", "ยังไม่มี user study กับกลุ่มเป้าหมาย", "ยังไม่ทราบความสะดวกและความเหมาะสมจริง"],
    ], [3.0, 6.2, 5.45], caption="ตารางที่ 5.3 ข้อจำกัดของโครงงาน", font_size=13)

    add_heading(doc, "5.5 ข้อเสนอแนะ")
    add_heading(doc, "5.5.1 ข้อเสนอแนะเพื่อปรับปรุงระบบ", 2)
    add_item(doc, "1)", "ตรวจและกำหนดพจนานุกรมป้ายกำกับร่วมกับผู้ใช้ภาษามือหรือผู้เชี่ยวชาญ แก้คำอธิบายที่สะกดผิด และกำหนดวิธีเริ่ม–จบท่าให้เหมือนกันก่อนเก็บข้อมูลเพิ่ม")
    add_item(doc, "2)", "เพิ่ม metadata ได้แก่ รหัสผู้ให้ข้อมูล รหัสเซสชัน แสง ฉากหลัง ระยะ มุม กล้อง และความเร็ว เพื่อรองรับการตรวจสอบและแบ่งข้อมูลแบบกลุ่ม")
    add_item(doc, "3)", "แยกชุดฝึก ชุดตรวจสอบ และชุดทดสอบภายนอกตามผู้ให้ข้อมูลหรือเซสชัน ห้ามให้ข้อมูลของกลุ่มทดสอบปรากฏในกระบวนการปรับโมเดล")
    add_item(doc, "4)", "วัด FPS เวลาแฝง อัตราการปฏิเสธคำ อัตราคำผิด และความสำเร็จของ TTS ในสภาพแวดล้อมหลายแบบ พร้อมบันทึกเวอร์ชันข้อมูลและซอฟต์แวร์")
    add_item(doc, "5)", "ปรับเกณฑ์ความเชื่อมั่นจากชุดตรวจสอบ เพิ่มสถานะไม่ทราบ/ปฏิเสธเมื่อไม่มีคลาสเหมาะสม และประเมินการสอบเทียบค่าความน่าจะเป็น")
    add_item(doc, "6)", "เพิ่มทางเลือกเสียงภาษาไทยแบบออฟไลน์และตัวเลือกปิดการพูดอัตโนมัติ เพื่อรองรับพื้นที่เครือข่ายจำกัดและความต้องการที่ต่างกัน")

    add_heading(doc, "5.5.2 ข้อเสนอแนะสำหรับงานวิจัยต่อยอด", 2)
    add_item(doc, "1)", "ขยายจำนวนคำและผู้ทำท่าอย่างเป็นระบบ โดยวางแผนตัวอย่างต่อกลุ่มก่อนเก็บข้อมูล ไม่เพิ่มเฉพาะคลิปจากสถานการณ์เดิม")
    add_item(doc, "2)", "เปรียบเทียบ SVM กับแบบจำลองลำดับ เช่น HMM, LSTM, Temporal Convolutional Network หรือ Transformer เมื่อมีข้อมูลมากพอและใช้ชุดทดสอบเดียวกันอย่างยุติธรรม")
    add_item(doc, "3)", "ศึกษาการแบ่งช่วงท่าอัตโนมัติและการรู้จำหลายคำต่อเนื่อง โดยแยกโจทย์การแบ่งหน่วยท่า การรู้จำ และการจัดลำดับภาษาปลายทาง")
    add_item(doc, "4)", "ศึกษาว่า สีหน้าและท่าทางที่ไม่ใช้มือมีบทบาทต่อความหมายของคำอย่างไร พร้อมประเมินผลกระทบด้านความเป็นส่วนตัว")
    add_item(doc, "5)", "ออกแบบและทดสอบร่วมกับชุมชนผู้ใช้ภาษามือ ผู้เชี่ยวชาญด้านภาษา และผู้เชี่ยวชาญด้านการเข้าถึง เพื่อให้โจทย์ คำศัพท์ และเกณฑ์ความสำเร็จสอดคล้องกับการใช้งานจริง")

    add_heading(doc, "5.5.3 ชุดคำศัพท์ที่เสนอให้เพิ่มในอนาคต 9 ท่า", 2)
    add_body(doc, "หลังจากเพิ่มคำศัพท์รุ่นปัจจุบันจนมี 16 ท่าแล้ว ไฟล์ planned_gestures.json ยังระบุคำที่วางแผนไว้อีก 9 ท่า ดังตารางที่ 5.4 รายการนี้เป็นชื่อคำสำหรับวางแผนชุดข้อมูล ไม่ใช่ข้อกำหนดรูปแบบการทำท่า โดยต้องตรวจสอบรูปแบบภาษามือไทย ความหมายตามบริบท และความเหมาะสมร่วมกับผู้ใช้ภาษามือหรือผู้เชี่ยวชาญก่อนบันทึกข้อมูลจริง")
    future_table = add_table(doc, ["ลำดับ", "คำศัพท์ที่เสนอ", "วัตถุประสงค์การใช้งาน"], [
        ["1", "ไม่ต้อง", "ใช้ปฏิเสธความต้องการหรือบริการ"],
        ["2", "มา", "ใช้สื่อสารการเคลื่อนเข้าหาผู้พูดหรือจุดหมาย"],
        ["3", "ได้", "ใช้ตอบรับความเป็นไปได้หรือความสามารถตามบริบท"],
        ["4", "ไป", "ใช้สื่อสารการเคลื่อนออกจากจุดหรือไปยังสถานที่"],
        ["5", "ไม่ได้", "ใช้ปฏิเสธความเป็นไปได้หรือความสามารถตามบริบท"],
        ["6", "ที่ไหน", "ใช้สร้างคำถามเกี่ยวกับสถานที่"],
        ["7", "นอน", "ใช้สื่อสารกิจวัตรหรือความต้องการพักผ่อน"],
        ["8", "ป่วย", "ใช้แจ้งอาการไม่สบาย"],
        ["9", "ยา", "ใช้สื่อสารเรื่องยาและการรักษา"],
    ], [1.4, 3.2, 10.05], caption="ตารางที่ 5.4 ชุดคำศัพท์ที่เสนอให้เพิ่มในอนาคต 9 ท่า", font_size=13)
    for row in future_table.rows:
        for cell in row.cells:
            set_cell_margins(cell, top=40, start=120, bottom=40, end=120)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.line_spacing = 1.0
    add_body(doc, "แผนเก็บข้อมูลควรกำหนดจำนวนคลิปต่อท่าให้เท่ากัน เก็บจากผู้ทำท่าหลายคนและหลายเซสชัน พร้อมบันทึกรหัสผู้ให้ข้อมูล สภาพแสง ฉากหลัง ระยะ มุมกล้อง และความเร็วในการทำท่า จากนั้นแบ่งชุดฝึก ชุดตรวจสอบ และชุดทดสอบโดยไม่ให้ข้อมูลของผู้ทำท่าหรือเซสชันเดียวกันรั่วไหลข้ามชุด")

    add_heading(doc, "5.6 สรุปภาพรวม")
    add_body(doc, "HandVox แสดงให้เห็นความเป็นไปได้ของการใช้ MediaPipe Holistic ร่วมกับ SVM เพื่อรู้จำท่าทางแบบแยกคำจากคลิปสั้น ระบบเชื่อมขั้นตอนเก็บข้อมูล ฝึกแบบจำลอง ทำนาย แสดงข้อความ สร้างประโยค และอ่านเสียงไว้ในต้นแบบเดียว รุ่นปัจจุบันมี 16 ท่า 350 คลิป และผ่านเกณฑ์คัดกรองภายในด้วย Accuracy 94.29% และ Macro F1 93.75%")
    add_body(doc, "คุณค่าของผลลัพธ์จึงอยู่ที่การพิสูจน์กระบวนการและเป็นฐานสำหรับทดลองต่อ มากกว่าการรับรองความแม่นยำในโลกจริง ขั้นตอนสำคัญถัดไปคือเก็บข้อมูลหลายผู้ทำท่าและหลายเซสชัน จัดทำ metadata ประเมินแบบแยกกลุ่มและภายนอก วัดเวลาแฝง และทดสอบกับผู้ใช้เป้าหมายภายใต้การขอความยินยอมและการคุ้มครองข้อมูลที่เหมาะสม")

    path = OUTPUT / "บทที่ 5_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_1_structured():
    """บทที่ 1 ตามหัวข้อ 1.1–1.7 และรูปแบบตัวอย่างของผู้ใช้."""
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[1])
    add_chapter_title(doc, 1, "บทนำ")

    add_heading(doc, "1.1 ที่มาและความสำคัญของปัญหา")
    add_body(doc, "การสื่อสารระหว่างผู้ใช้ภาษามือกับบุคคลที่ไม่เข้าใจภาษามือยังมีข้อจำกัดในหลายสถานการณ์ เช่น การติดต่อขอรับบริการ การเรียน การทำงาน และการสื่อสารในชีวิตประจำวัน หากไม่มีล่ามหรือผู้ช่วย ผู้ใช้ภาษามืออาจต้องใช้การเขียนหรือการพิมพ์ข้อความแทน ซึ่งไม่สะดวกในทุกบริบท จึงเกิดแนวคิดนำเทคโนโลยีการมองเห็นด้วยคอมพิวเตอร์มาช่วยตรวจจับท่าทางและแสดงผลให้ผู้อื่นเข้าใจได้ง่ายขึ้น")
    add_body(doc, "ปัญหาดังกล่าวไม่ได้เกิดจากความสามารถของผู้ใช้ภาษามือ แต่เกิดจากสภาพแวดล้อมและบริการส่วนใหญ่ยังออกแบบโดยยึดภาษาพูดเป็นหลัก เมื่อผู้ให้บริการไม่เข้าใจภาษามือ การสื่อสารเรื่องง่ายอาจใช้เวลานาน เกิดความคลาดเคลื่อน หรือทำให้ผู้ใช้ต้องพึ่งพาบุคคลอื่น การมีเครื่องมือช่วยแสดงผลท่าที่ระบบรู้จักเป็นข้อความจึงสามารถใช้เป็นช่องทางเสริมในสถานการณ์ที่ไม่มีล่ามได้")
    add_body(doc, "การพัฒนาระบบรู้จำท่าทางจากวิดีโอมีความท้าทายมากกว่าการจำแนกภาพนิ่ง เนื่องจากความหมายของท่าหลายคำขึ้นอยู่กับทิศทางและลำดับการเคลื่อนไหว นอกจากนี้ รูปร่างมือ ตำแหน่งแขน ระยะจากกล้อง แสง ฉากหลัง และความเร็วของผู้ทำท่าล้วนส่งผลต่อข้อมูลที่ตรวจจับได้ ระบบจึงต้องรักษาลำดับเวลาและลดความแปรผันที่ไม่เกี่ยวข้องก่อนนำข้อมูลไปฝึกแบบจำลอง")
    add_body(doc, "โครงงาน HandVox พัฒนาขึ้นเป็นต้นแบบระบบรู้จำท่าทางภาษามือไทยแบบแยกคำจากภาพเว็บแคม ระบบใช้ MediaPipe Holistic ตรวจหาจุดสำคัญของช่วงบนและมือทั้งสองข้าง เก็บข้อมูลการเคลื่อนไหวต่อเนื่อง 30 เฟรม และใช้ Support Vector Machine จำแนกท่าที่มีอยู่ในชุดข้อมูล จากนั้นแสดงชื่อท่า ค่าความเชื่อมั่น ข้อความสะสมเป็นประโยค และเสียงพูดภาษาไทย")
    add_body(doc, "เหตุผลที่เลือกใช้ข้อมูลจุดสำคัญแทนภาพสีทั้งภาพ คือข้อมูลมีขนาดเล็กกว่า ลดอิทธิพลจากรายละเอียดของเสื้อผ้าและพื้นหลัง และสามารถอธิบายตำแหน่งสัมพันธ์ของข้อศอก ข้อมือ และนิ้วมือได้ชัดเจน ส่วน SVM แบบ RBF เหมาะกับการทดลองที่มีจำนวนตัวอย่างไม่มากและข้อมูลมีขอบเขตระหว่างคลาสไม่เป็นเส้นตรง จึงใช้เป็นแบบจำลองหลักของต้นแบบรุ่นนี้")
    add_body(doc, "HandVox ไม่ได้มุ่งทำเฉพาะตัวจำแนกท่าทาง แต่เชื่อมกระบวนการตั้งแต่การกำหนดรายการท่า การเก็บคลิป การตรวจคุณภาพข้อมูล การฝึกแบบจำลอง การทำนายแบบเวลาจริง ไปจนถึงการนำผลไปสะสมเป็นประโยคและอ่านออกเสียง การรวมทุกขั้นตอนไว้ในระบบเดียวช่วยให้ผู้พัฒนาตรวจสอบความสอดคล้องของข้อมูลและปรับปรุงคำศัพท์ได้โดยไม่ต้องสร้างกระบวนการใหม่ทุกครั้ง")
    add_body(doc, "แรงบันดาลใจของโครงงานคือการสร้างเครื่องมือที่ช่วยลดช่องว่างในการสื่อสารและเป็นพื้นที่ทดลองกระบวนการสร้างระบบรู้จำท่าทางตั้งแต่การเก็บข้อมูลจนถึงการใช้งานจริง อย่างไรก็ตาม ระบบรุ่นปัจจุบันรู้จำเฉพาะท่าที่กำหนดไว้ล่วงหน้าและยังไม่ใช่การแปลภาษามือต่อเนื่องอย่างสมบูรณ์ การกำหนดขอบเขตให้ชัดเจนจึงช่วยให้ประเมินผลและนำระบบไปพัฒนาต่อได้อย่างเหมาะสม")
    add_body(doc, "ผลของโครงงานจึงควรถูกมองเป็นต้นแบบเชิงวิศวกรรมและฐานข้อมูลสำหรับการศึกษาต่อ ไม่ใช่ผลิตภัณฑ์ที่รับรองความถูกต้องในทุกสถานการณ์ การรายงานทั้งผลสำเร็จและข้อจำกัดอย่างตรงไปตรงมามีความสำคัญ เพราะช่วยกำหนดว่าต้องเพิ่มข้อมูล ทดสอบกับผู้ใช้ และปรับระบบส่วนใดก่อนนำไปใช้ในสภาพแวดล้อมจริง")

    add_heading(doc, "1.2 วัตถุประสงค์ของโครงงาน")
    add_numbered_list(doc, [
        "เพื่อพัฒนาระบบ HandVox สำหรับรู้จำท่าทางภาษามือไทยแบบแยกคำจากลำดับภาพเว็บแคมแบบเวลาจริง",
        "เพื่อพัฒนากระบวนการเพิ่มท่า เก็บคลิป ลบท่า และฝึกแบบจำลองใหม่โดยผู้ใช้ไม่จำเป็นต้องแก้ไขซอร์สโค้ดโดยตรง",
        "เพื่อแสดงผลการรู้จำเป็นชื่อท่า ค่าความเชื่อมั่น ข้อความสะสมเป็นประโยค และเสียงพูดภาษาไทย",
        "เพื่อประเมินการจำแนกภายในชุดข้อมูลด้วย Accuracy, Precision, Recall, F1-score และ Confusion Matrix พร้อมระบุข้อจำกัด",
        "เพื่อตรวจสอบความสอดคล้องของขั้นตอนเก็บข้อมูล ฝึก และทำนาย รวมถึงกรณีข้อมูลหรืออุปกรณ์ไม่พร้อม",
        "เพื่อสรุปผลการพัฒนา ปัญหา และแนวทางเพิ่มผู้ทำท่า คำศัพท์ และการประเมินภายนอกในรุ่นถัดไป",
    ])

    add_heading(doc, "1.3 ขอบเขตของการจัดสร้างโครงงาน")
    add_body(doc, "โครงงานครอบคลุมการพัฒนาต้นแบบบนคอมพิวเตอร์ระบบ Windows โดยใช้เว็บแคมหนึ่งตัวสำหรับรับภาพบุคคลหนึ่งคน ตั้งแต่การเก็บข้อมูล การสกัดคุณลักษณะ การฝึกแบบจำลอง การทำนาย และการนำเสนอผล มีขอบเขตดังต่อไปนี้")
    add_numbered_list(doc, [
        "ระบบรับภาพช่วงบนและมืออย่างน้อยหนึ่งข้าง และรู้จำท่าทีละหนึ่งคำจากข้อมูลล่าสุด 30 เฟรม",
        "หนึ่งเฟรมใช้จุดสำคัญ 57 จุด รวม 171 คุณลักษณะ และหนึ่งคลิปถูกแปลงเป็นเวกเตอร์ 5,130 ค่าเพื่อฝึก SVM แบบ RBF",
        "ชุดข้อมูลที่ใช้ในโครงงานมี 16 ท่า รวม 350 คลิป โดยจำแนกเฉพาะท่าที่มีอยู่ในชุดข้อมูลเท่านั้น",
        "ระบบแสดงชื่อท่าและค่าความเชื่อมั่น ใช้ผลย้อนหลัง 3 ครั้งเพื่อลดการสั่น และรับผลเมื่อค่าความเชื่อมั่นไม่น้อยกว่า 0.40",
        "ผู้ใช้สามารถเพิ่มคำลงในประโยค ลบคำ ล้างประโยค และอ่านออกเสียงภาษาไทย รวมถึงเพิ่มหรือลบท่าและฝึกแบบจำลองใหม่ได้",
        "โครงงานไม่ครอบคลุมการรู้จำภาษามือต่อเนื่องหลายคำ การวิเคราะห์ไวยากรณ์ การใช้สีหน้าเป็นคุณลักษณะ หรือการใช้แทนล่ามในบริบทสำคัญ",
    ])
    add_subtopic(doc, "ขอบเขตด้านผู้ใช้และสภาพแวดล้อม", "ระบบออกแบบให้บุคคลหนึ่งคนอยู่หน้ากล้องในระยะที่มองเห็นศีรษะ ไหล่ แขน และมือได้ชัดเจน ใช้ฉากหลังทั่วไปและแสงที่เพียงพอสำหรับการตรวจจับจุดสำคัญ การทดลองยังไม่ครอบคลุมพื้นที่กลางแจ้ง แสงน้อย การบังมือมาก หรือการมีหลายคนในภาพเดียวกัน")
    add_subtopic(doc, "ขอบเขตด้านข้อมูล", "ตัวอย่างหนึ่งรายการแทนการทำท่าหนึ่งครั้งด้วยข้อมูล 30 เฟรม แต่ละเฟรมประกอบด้วย 15 จุดของช่วงบนและมือข้างละ 21 จุด รวม 171 คุณลักษณะ ชุดข้อมูลปัจจุบันมี 16 ป้ายกำกับและ 350 คลิป โดยจำนวนตัวอย่างต่อคลาสยังไม่เท่ากัน")
    add_subtopic(doc, "ขอบเขตด้านซอฟต์แวร์", "ระบบทำงานบน Windows 10 หรือ Windows 11 ใช้ Python 3.10 หรือ 3.11 ร่วมกับ OpenCV, MediaPipe, NumPy, scikit-learn, Pillow, gTTS และ pygame ใช้ไฟล์ข้อมูลกับไฟล์แบบจำลองภายในโครงการ และต้องเชื่อมต่ออินเทอร์เน็ตเมื่อสร้างเสียงด้วย gTTS")
    add_subtopic(doc, "ขอบเขตด้านการประเมิน", "การประเมินเชิงปริมาณใช้การแบ่งข้อมูลแบบ stratified holdout 80:20 เพื่อคัดกรองต้นแบบ รายงานผลรวม ผลรายคลาส และคู่ท่าที่สับสน ส่วนการทดสอบกับผู้ใช้ใหม่ การแบ่งแบบแยกผู้ทำท่า การวัดเวลาแฝง และการศึกษาความพึงพอใจยังเป็นงานที่ต้องดำเนินการต่อ")
    add_subtopic(doc, "ข้อจำกัดของการกล่าวอ้าง", "คำว่ารู้จำในรายงานหมายถึงการเลือกป้ายกำกับจากรายการที่ระบบเคยเรียนรู้ ไม่ได้หมายถึงการแปลโครงสร้างภาษามือไทยทั้งหมด ระบบจึงไม่ควรใช้แทนล่ามหรือใช้ตัดสินใจในบริบทด้านการแพทย์ กฎหมาย และความปลอดภัยโดยไม่มีมนุษย์ตรวจสอบ")

    add_heading(doc, "1.4 ประโยชน์ที่คาดว่าจะได้รับ")
    add_body(doc, "ผู้ใช้และผู้พัฒนาจะได้ต้นแบบระบบรู้จำท่าทางภาษามือแบบแยกคำที่ทำงานกับกล้องทั่วไปและแสดงผลได้แบบเวลาจริง พร้อมกระบวนการสร้างชุดข้อมูลการเคลื่อนไหวและฝึกแบบจำลองที่สามารถเพิ่มคำศัพท์ได้ในภายหลัง สถานศึกษาหรือผู้สนใจยังสามารถใช้โครงงานเป็นกรณีศึกษาการประยุกต์ใช้ Computer Vision และ Machine Learning เพื่อสนับสนุนการสื่อสาร รวมถึงเป็นฐานสำหรับการเก็บข้อมูลจากผู้ใช้หลายคนและการประเมินภายนอกในอนาคต")

    add_heading(doc, "1.5 ทรัพยากรที่ใช้ในการจัดทำโครงงาน")
    add_body(doc, "ทรัพยากรที่ใช้ประกอบด้วยคอมพิวเตอร์ระบบ Windows เว็บแคม และลำโพงหรือหูฟัง ร่วมกับ Python 3.10 หรือ 3.11 และไลบรารี OpenCV, MediaPipe Holistic, NumPy, scikit-learn, Pillow, gTTS และ pygame รวมถึงชุดข้อมูลลำดับท่าทางกับไฟล์แบบจำลองของ HandVox")

    add_heading(doc, "1.6 ระยะเวลาการดำเนินงาน")
    add_project_schedule_table(doc)

    add_heading(doc, "1.7 นิยามศัพท์เฉพาะ")
    add_compact_definition(doc, "1.7.1 HandVox", "ระบบรู้จำท่าทางภาษามือไทยแบบแยกคำจากเว็บแคมและแสดงผลเป็นข้อความกับเสียงพูด")
    add_compact_definition(doc, "1.7.2 การรู้จำภาษามือแบบแยกคำ", "การจำแนกคลิปหนึ่งท่าเป็นหนึ่งป้ายกำกับ โดยไม่รวมการแบ่งคำและแปลภาษามือต่อเนื่อง")
    add_compact_definition(doc, "1.7.3 OpenCV", "ไลบรารีสำหรับรับภาพจากเว็บแคม ประมวลผลภาพ และแสดงส่วนติดต่อของระบบ")
    add_compact_definition(doc, "1.7.4 MediaPipe Holistic", "เครื่องมือที่ตรวจหาจุดสำคัญของร่างกาย ใบหน้า และมือจากภาพหรือวิดีโอ")
    add_compact_definition(doc, "1.7.5 จุดสำคัญ (Landmark)", "พิกัดข้อต่อของช่วงบนและมือที่ใช้เป็นคุณลักษณะแทนข้อมูลภาพดิบ")
    add_compact_definition(doc, "1.7.6 ลำดับภาพ 30 เฟรม", "ข้อมูลการเคลื่อนไหวของหนึ่งท่าที่เรียงต่อกันเพื่อรักษาทิศทางและจังหวะของท่า")
    add_compact_definition(doc, "1.7.7 เวกเตอร์คุณลักษณะ (Feature Vector)", "ชุดตัวเลขจากพิกัดจุดสำคัญที่จัดรูปแบบเป็นข้อมูลนำเข้าของแบบจำลอง")
    add_compact_definition(doc, "1.7.8 Support Vector Machine (SVM) และ RBF Kernel", "แบบจำลองและฟังก์ชันสำหรับสร้างขอบเขตจำแนกข้อมูลท่าทางที่ไม่เป็นเส้นตรง")
    add_compact_definition(doc, "1.7.9 ค่าความเชื่อมั่น (Confidence Score)", "ค่าประกอบการตัดสินใจก่อนรับผลทำนายเข้าสู่ระบบ")
    add_compact_definition(doc, "1.7.10 Text-to-Speech (TTS)", "เทคโนโลยีแปลงชื่อท่าหรือข้อความสะสมให้เป็นเสียงพูดภาษาไทย")

    # The supplied chapter-one form specifies 16 pt bold section headings and
    # 16 pt regular body text.  A single-spaced body keeps the ten required
    # definitions with the schedule instead of creating a nearly empty sixth
    # page, while the space before each heading supplies the requested blank
    # line between sections.
    for paragraph in doc.paragraphs[2:]:
        paragraph.paragraph_format.line_spacing = 1.0
        if paragraph.style.name == "Heading 1":
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                set_run_font(run, 16, bold=True, color=INK)

    path = OUTPUT / "บทที่ 1_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_2_compact_legacy():
    """บทที่ 2 ตามแบบความรู้พื้นฐาน พร้อมหัวข้อหลัก 2.1–2.9 ครบถ้วน."""
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[2])
    add_chapter_title(doc, 2, "ความรู้พื้นฐาน")
    add_chapter_overview(
        doc,
        "ในการจัดสร้างโครงงาน HandVox จำเป็นต้องศึกษาความรู้พื้นฐาน แนวคิด ทฤษฎี และงานวิจัยที่เกี่ยวข้อง ดังนี้",
        [
            ("2.1", "ภาษามือและการรู้จำ"),
            ("2.2", "การมองเห็นด้วยคอมพิวเตอร์"),
            ("2.3", "จุดสำคัญที่ใช้ใน HandVox"),
            ("2.4", "การปรับมาตรฐานและการแทนลำดับ"),
            ("2.5", "Support Vector Machine"),
            ("2.6", "การแบ่งข้อมูลและการป้องกันการรั่วไหล"),
            ("2.7", "การประเมินผล"),
            ("2.8", "การทำงานแบบเวลาจริงและเสียงพูด"),
            ("2.9", "งานวิจัยที่เกี่ยวข้อง"),
        ],
    )

    add_body(doc, "เนื้อหาในบทนี้สืบค้นจาก Google Scholar โดยใช้คำค้นที่เกี่ยวข้องกับ sign language recognition, Thai sign language, MediaPipe, hand landmarks, Support Vector Machine และ real-time sign language translation แล้วตรวจสอบชื่อผู้แต่ง ปีเผยแพร่ วิธีดำเนินการ และผลการทดลองกับหน้าต้นฉบับของวารสารหรือการประชุมวิชาการก่อนนำมาเรียบเรียง")
    add_heading(doc, "2.1 ภาษามือและการรู้จำ")
    add_body(doc, "ภาษามือเป็นภาษาธรรมชาติที่ประกอบด้วยรูปมือ ตำแหน่ง ทิศทาง การเคลื่อนไหว สีหน้า และโครงสร้างทางภาษา การรู้จำแบบแยกคำรับคลิปของท่าหนึ่งคำและส่งออกหนึ่งป้ายกำกับ ส่วนการรู้จำแบบต่อเนื่องต้องแบ่งหน่วยท่าจากวิดีโอหลายคำและจัดการบริบท HandVox เลือกขอบเขตแบบแยกคำเพื่อให้พัฒนาและประเมินต้นแบบได้ชัดเจน")
    add_body(doc, "Camgoz และคณะ (2018) อธิบายว่าการรู้จำภาษามือไม่ควรถูกมองเป็นเพียงการจำแนกท่าทาง เพราะภาษามือมีลำดับคำและโครงสร้างไวยากรณ์ที่แตกต่างจากภาษาพูด งานดังกล่าวแยกปัญหา Sign Language Recognition ซึ่งมุ่งระบุหน่วยท่า ออกจาก Sign Language Translation ซึ่งมุ่งสร้างประโยคภาษาพูดที่มีความหมายสอดคล้องกัน แนวคิดนี้ใช้กำหนดให้ HandVox รุ่นปัจจุบันเป็นระบบรู้จำแบบแยกคำ ไม่อ้างว่าเป็นระบบแปลภาษามืออย่างสมบูรณ์")
    add_body(doc, "การจำแนกรูปมือจากภาพนิ่งเหมาะกับคำที่รูปมือในช่วงใดช่วงหนึ่งมีข้อมูลเพียงพอ แต่ท่าจำนวนมากมีความหมายต่างกันจากทิศทาง การเคลื่อนเข้า–ออก การหมุนข้อมือ หรือการเปลี่ยนตำแหน่งสัมพันธ์กับร่างกาย หากใช้ภาพเพียงเฟรมเดียว ระบบอาจมองไม่เห็นลำดับดังกล่าว การใช้คลิปจึงช่วยให้แบบจำลองได้รับข้อมูลก่อน ระหว่าง และหลังการเคลื่อนไหว")
    add_body(doc, "สำหรับการรู้จำแบบแยกคำ ผู้เก็บข้อมูลต้องกำหนดจุดเริ่มและจุดสิ้นสุดของท่าให้ใกล้เคียงกันในทุกตัวอย่าง ถ้าบางคลิปเริ่มช้า บางคลิปจบเร็ว หรือมีช่วงอยู่นิ่งยาวเกินไป แบบจำลองอาจเรียนรู้จังหวะที่ไม่เกี่ยวข้องกับความหมาย HandVox จึงกำหนดจำนวนเฟรมคงที่และใช้คำแนะนำการเก็บข้อมูลแบบเดียวกันทุกคลาส")
    add_table(doc, ["รูปแบบ", "ข้อมูลนำเข้า", "ผลลัพธ์", "ขอบเขต"], [
        ["ภาพนิ่ง", "หนึ่งเฟรม", "คลาสของรูปมือ", "ไม่แทนลำดับการเคลื่อนไหว"],
        ["แบบแยกคำ", "คลิปของหนึ่งท่า", "หนึ่งคำหรือป้ายกำกับ", "เหมาะกับท่าที่มีจุดเริ่มและสิ้นสุดชัดเจน"],
        ["แบบต่อเนื่อง", "วิดีโอหลายท่าต่อกัน", "ลำดับคำหรือประโยค", "ต้องแบ่งหน่วยท่าและจัดการบริบท"],
    ], [2.6, 3.5, 3.4, 5.15], caption="ตารางที่ 2.1 การเปรียบเทียบรูปแบบการรู้จำ")
    add_body(doc, "การเลือกแบบแยกคำทำให้ขอบเขตของปัญหาชัดเจนและเหมาะกับชุดข้อมูลขนาดเล็ก ผู้ใช้ต้องทำท่าหนึ่งคำภายในหน้าต่างเก็บข้อมูล และระบบคืนผลหนึ่งป้ายกำกับต่อครั้ง ข้อดีคือสามารถตรวจผลรายคำได้ตรงไปตรงมา ส่วนข้อจำกัดคือยังไม่สามารถแบ่งคำจากการเคลื่อนไหวต่อเนื่องหรือเรียงผลเป็นประโยคภาษาพูดโดยอัตโนมัติ")

    add_heading(doc, "2.2 การมองเห็นด้วยคอมพิวเตอร์")
    add_body(doc, "OpenCV ทำหน้าที่รับภาพจากกล้อง วาดส่วนติดต่อ และแสดงผล ส่วน MediaPipe Holistic ประมาณตำแหน่งจุดสำคัญของร่างกายและมือ การใช้พิกัดจุดสำคัญแทนภาพดิบช่วยลดมิติข้อมูลและทำให้ระบบเน้นโครงสร้างการเคลื่อนไหว แต่ผลยังขึ้นกับแสง มุมกล้อง การบังมือ และความเร็วของผู้ใช้")
    add_body(doc, "Lugaresi และคณะ (2019) เสนอ MediaPipe เป็นกรอบงานสำหรับสร้าง perception pipeline แบบข้ามแพลตฟอร์ม โดยเชื่อมส่วนรับสื่อ แบบจำลอง และการแปลงข้อมูลเป็นกราฟการประมวลผล ช่วยให้พัฒนาต้นแบบและวัดประสิทธิภาพบนอุปกรณ์เป้าหมายได้ ส่วน Zhang และคณะ (2020) พัฒนา MediaPipe Hands ซึ่งใช้ palm detector ร่วมกับ hand landmark model เพื่อประมาณโครงมือ 21 จุดจากภาพกล้องเดียวและทำงานแบบเวลาจริงบนอุปกรณ์เคลื่อนที่ แนวคิดทั้งสองเป็นฐานของการใช้ MediaPipe Holistic ใน HandVox")
    add_body(doc, "กระบวนการตรวจจับจุดสำคัญมีสองช่วงหลัก คือการตรวจว่าร่างกายหรือมืออยู่บริเวณใดในภาพ และการประมาณพิกัดของจุดข้อต่อภายในบริเวณนั้น เมื่อประมวลผลวิดีโอต่อเนื่อง ระบบสามารถติดตามตำแหน่งจากเฟรมก่อนหน้าเพื่อลดภาระการตรวจใหม่ทุกครั้ง แต่หากมือเคลื่อนเร็ว หลุดกรอบ หรือถูกบัง พิกัดอาจหายหรือกระโดดจนส่งผลต่อเวกเตอร์คุณลักษณะ")
    add_body(doc, "HandVox เปิดใช้งานการประมวลผลแบบวิดีโอต่อเนื่อง ใช้ model complexity ระดับกลาง เปิดการทำให้จุดต่อเนื่องราบรื่น และกำหนดค่าความเชื่อมั่นขั้นต่ำของการตรวจจับกับการติดตามเท่ากับ 0.70 การตั้งค่านี้เป็นจุดสมดุลเบื้องต้นระหว่างความเสถียรกับความเร็ว และควรทดสอบใหม่เมื่อเปลี่ยนกล้องหรือสภาพแวดล้อม")
    add_heading(doc, "2.3 จุดสำคัญที่ใช้ใน HandVox")
    add_body(doc, "ระบบเลือกจุดช่วงบน 15 จุด และมือซ้ายกับมือขวาข้างละ 21 จุด แต่ละจุดมีพิกัด x, y และ z จึงมีข้อมูลรวม 171 ค่าในหนึ่งเฟรม หากพบมือเพียงข้างเดียว ระบบเติมศูนย์ให้ข้อมูลมืออีกข้างเพื่อรักษาขนาดข้อมูลให้เท่ากัน")
    add_body(doc, "จุดช่วงบนช่วยอธิบายตำแหน่งของมือเมื่อเทียบกับศีรษะ ไหล่ ศอก และลำตัว ขณะที่จุดมืออธิบายรูปนิ้วและทิศทางฝ่ามือ การใช้ทั้งสองกลุ่มร่วมกันเหมาะกับท่าที่รูปมือคล้ายกันแต่เกิดคนละตำแหน่ง หากไม่พบโครงร่างของช่วงบนหรือไม่พบมือทั้งสองข้าง ระบบจะไม่รับเฟรมนั้น เพราะข้อมูลไม่เพียงพอสำหรับสร้างตัวอย่างที่สอดคล้องกับชุดฝึก")
    add_body(doc, "การเติมศูนย์เมื่อพบมือเพียงข้างเดียวทำให้ทุกเฟรมมีจำนวนคุณลักษณะเท่ากัน แต่ศูนย์ในกรณีนี้หมายถึงข้อมูลที่ไม่ตรวจพบ ไม่ใช่ตำแหน่งจริงของมือ ดังนั้นสัดส่วนเฟรมที่มือหายไม่ควรมากเกินไป และควรตรวจคุณภาพคลิปก่อนรวมเข้าในชุดข้อมูล มิฉะนั้นแบบจำลองอาจเรียนรู้รูปแบบของข้อมูลหายแทนรูปแบบของท่าทาง")

    add_heading(doc, "2.4 การปรับมาตรฐานและการแทนลำดับ")
    add_body(doc, "ระบบใช้จุดกึ่งกลางระหว่างไหล่เป็นจุดอ้างอิงและใช้ระยะระหว่างไหล่เป็นตัวปรับขนาด เพื่อลดผลจากตำแหน่งและระยะห่างจากกล้อง หนึ่งคลิปมี 30 เฟรม เฟรมละ 171 ค่า ก่อนฝึกจะเรียงเป็นเวกเตอร์ 5,130 ค่า โดยลำดับของตำแหน่งในเวกเตอร์ยังคงข้อมูลการเคลื่อนไหวตามเวลา")
    add_body(doc, "ให้ c เป็นจุดกึ่งกลางระหว่างไหล่ซ้ายกับไหล่ขวา และให้ s เป็นระยะยูคลิดระหว่างไหล่ พิกัดของจุดแต่ละจุดถูกเลื่อนด้วย c และหารด้วย s ก่อนจัดเก็บ วิธีนี้ลดผลจากการยืนค่อนไปทางซ้ายหรือขวาและการอยู่ใกล้หรือไกลกล้อง อย่างไรก็ตาม การปรับดังกล่าวยังไม่ทำให้ข้อมูลไม่แปรผันต่อการหมุนตัว มุมกล้อง หรือสัดส่วนร่างกายทั้งหมด")
    add_body(doc, "การเรียงข้อมูล 30 เฟรมต่อกันเป็นเวกเตอร์ทำให้ SVM สามารถใช้ข้อมูลเวลาได้โดยไม่ต้องมีโครงสร้างแบบจำลองลำดับเฉพาะ ตำแหน่งลำดับที่ 1–171 แทนเฟรมแรก และตำแหน่งช่วงท้ายแทนเฟรมที่ 30 ดังนั้นท่าที่เคลื่อนไหวในทิศทางตรงข้ามจะให้ลำดับค่าแตกต่างกัน แม้บางเฟรมจะมีรูปมือคล้ายกัน")
    add_body(doc, "ข้อจำกัดของการกำหนด 30 เฟรมคือผู้ทำท่าต้องปรับจังหวะให้พอดีกับหน้าต่างข้อมูล หากทำท่าเร็วมากจะมีช่วงอยู่นิ่งเหลือมาก แต่หากทำช้ามากท่าอาจไม่จบภายในคลิป แบบจำลองจึงอาจไวต่อความเร็ว การเก็บข้อมูลควรมีหลายจังหวะและในอนาคตอาจใช้การปรับแนวเวลา หรือแบบจำลองที่รองรับความยาวลำดับไม่เท่ากัน")

    add_heading(doc, "2.5 Support Vector Machine")
    add_body(doc, "Cortes และ Vapnik (1995) เสนอ Support-Vector Networks สำหรับสร้างขอบเขตการตัดสินใจที่มีระยะห่างจากตัวอย่างสำคัญมากที่สุด และใช้การแปลงข้อมูลไปยังปริภูมิมิติสูงเพื่อรองรับข้อมูลที่ไม่สามารถแยกด้วยเส้นตรง แนวคิดดังกล่าวพัฒนาต่อมาเป็น SVM ที่ใช้ kernel ได้ HandVox ใช้ RBF kernel เพื่อรองรับความสัมพันธ์ที่ไม่เป็นเส้นตรง กำหนด C=10, gamma=scale, probability=True และ class_weight=balanced")
    add_body(doc, "ค่า C ควบคุมการแลกเปลี่ยนระหว่างการยอมให้มีข้อผิดพลาดบนข้อมูลฝึกกับการสร้างขอบเขตที่ยืดหยุ่น ค่า gamma กำหนดระยะอิทธิพลของตัวอย่างต่อรูปร่างขอบเขต ส่วน class_weight=balanced เพิ่มน้ำหนักให้คลาสที่มีตัวอย่างน้อยกว่า การตั้งค่าปัจจุบันยึดตามการทดลองของโครงการและควรปรับด้วยชุดตรวจสอบที่แยกจากชุดทดสอบเมื่อมีข้อมูลมากขึ้น")
    add_body(doc, "การเปิด probability ทำให้โปรแกรมใช้ predict_proba เพื่อรายงานค่าประกอบการตัดสินใจแบบเวลาจริง แต่ค่าความน่าจะเป็นดังกล่าวขึ้นกับการสอบเทียบของแบบจำลองและลักษณะข้อมูล ไม่ควรตีความว่าเป็นความถูกต้องที่รับประกันในทุกสภาพแวดล้อม เกณฑ์ 0.40 จึงเป็นค่าตั้งต้นที่ต้องตรวจสอบกับข้อมูลภายนอก")
    add_heading(doc, "2.6 การแบ่งข้อมูลและการป้องกันการรั่วไหล")
    add_body(doc, "การแบ่งแบบ stratified ช่วยรักษาสัดส่วนของแต่ละคลาสระหว่างชุดฝึกกับชุดทดสอบ แต่ถ้าคลิปจากผู้ทำท่าหรือเซสชันเดียวกันกระจายอยู่ทั้งสองชุด คะแนนอาจสะท้อนความคล้ายของผู้ทำท่าและฉากหลังมากกว่าความสามารถกับผู้ใช้ใหม่ แนวทางที่เข้มงวดกว่าคือแบ่งตามรหัสผู้ให้ข้อมูลหรือเซสชัน และเก็บชุดทดสอบภายนอกที่ไม่ใช้ระหว่างการพัฒนา")
    add_heading(doc, "2.7 การประเมินผล")
    add_body(doc, "Accuracy ใช้สรุปสัดส่วนการทำนายถูกทั้งหมด ส่วน Precision, Recall และ F1-score ช่วยพิจารณาผลรายคลาส ค่า Macro F1 ให้น้ำหนักทุกคลาสเท่ากัน และ Confusion Matrix แสดงคู่ท่าที่ระบบทำนายสับสน การแบ่งข้อมูลควรแยกผู้ทำท่าหรือเซสชันเพื่อป้องกันข้อมูลที่คล้ายกันรั่วไหลระหว่างชุดฝึกและชุดทดสอบ")
    add_heading(doc, "2.8 การทำงานแบบเวลาจริงและเสียงพูด")
    add_body(doc, "ระบบสะสมคุณลักษณะล่าสุด 30 เฟรม รับผลที่มีค่าความเชื่อมั่นอย่างน้อย 0.40 และลงคะแนนจากผลล่าสุด 3 ครั้งเพื่อให้ข้อความนิ่งขึ้น ผลที่ยืนยันแล้วสามารถเพิ่มลงในประโยคและอ่านออกเสียงภาษาไทยผ่านระบบ Text-to-Speech")
    add_body(doc, "กลไกรวมผลย้อนหลังช่วยลดการเปลี่ยนป้ายกำกับไปมาระหว่างเฟรม แต่ทำให้เกิดความหน่วงเพิ่มขึ้นเล็กน้อย หากไม่พบมือนานกว่า 0.4 วินาที ระบบจะล้างคิวและสถานะเดิมเพื่อป้องกันผลเก่าค้างบนหน้าจอ การตั้งค่าทั้งสามส่วน ได้แก่ ขนาดหน้าต่าง เกณฑ์ความเชื่อมั่น และจำนวนผลย้อนหลัง มีผลต่อความไวกับความเสถียรของระบบ")
    add_body(doc, "ส่วน Text-to-Speech ทำหน้าที่เปลี่ยนชื่อท่าหรือข้อความสะสมเป็นเสียงภาษาไทย ช่วยส่งผลลัพธ์ไปยังคู่สนทนาโดยไม่ต้องอ่านหน้าจอ การสร้างเสียงทำงานแยกจากวงรอบกล้องเพื่อลดการหยุดค้าง แต่ gTTS ต้องใช้อินเทอร์เน็ต จึงควรมีทางเลือกเสียงแบบออฟไลน์ในรุ่นที่ต้องใช้งานในพื้นที่เครือข่ายไม่เสถียร")

    add_heading(doc, "2.9 งานวิจัยที่เกี่ยวข้อง")
    add_body(doc, "การคัดเลือกงานวิจัยพิจารณาความใกล้เคียงกับ HandVox ใน 4 ด้าน ได้แก่ การรู้จำภาษามือไทย การใช้ภาพหรือจุดสำคัญของร่างกาย การจำแนกท่าจากลำดับเวลา และการทำงานแบบเวลาจริง งานที่นำมาอ้างอิงมีทั้งงานภาษาไทยซึ่งสะท้อนข้อจำกัดด้านข้อมูลในประเทศ และงานต่างประเทศที่แสดงแนวทางเมื่อจำนวนคำกับผู้ทำท่าเพิ่มขึ้น")

    add_heading(doc, "2.9.1 การรู้จำนิ้วสะกดภาษาไทยด้วย SVM", 2)
    add_body(doc, "Pariwat และ Seresangtakul (2017) ศึกษาการรู้จำนิ้วสะกดภาษาไทยจากคุณลักษณะภาพแบบ global และ local แล้วเปรียบเทียบ SVM หลาย kernel ข้อมูลที่รายงานในงานทบทวนภายหลังมี 15 ท่า 75 ภาพ จากผู้ทำท่า 5 คน ผลเฉลี่ยของ RBF kernel เท่ากับ 91.2% สูงกว่า linear, polynomial และ sigmoid งานนี้สนับสนุนการเลือก RBF สำหรับข้อมูลท่าทางที่ขอบเขตคลาสไม่เป็นเส้นตรง แต่เป็นภาพนิ่งและชุดข้อมูลขนาดเล็ก จึงไม่ยืนยันผลของ HandVox ที่ใช้ลำดับ 30 เฟรมโดยตรง")
    add_heading(doc, "2.9.2 การรู้จำนิ้วสะกดภาษาไทยด้วย CNN และการปฏิเสธท่าที่ไม่รู้จัก", 2)
    add_body(doc, "Nakjai และ Katanyukul (2019) พัฒนากระบวนการสองขั้นตอน คือค้นหาและตัดบริเวณมือ ก่อนจำแนกภาพด้วย CNN หรือ HOG งานใช้ท่านิ้วสะกดภาษาไทย 25 ท่า 125 ภาพ จากผู้ทำท่า 11 คน และรายงาน mean Average Precision 91.26 งานยังเสนอ confidence ratio เพื่อช่วยแยกท่าที่ถูกต้องออกจากท่าช่วงเปลี่ยนหรือท่าที่ไม่อยู่ในชุดคำ แนวคิดดังกล่าวชี้ว่า HandVox ควรมีสถานะ “ไม่ทราบ” แทนการบังคับเลือกหนึ่งใน 16 คลาสทุกครั้ง")
    add_heading(doc, "2.9.3 ชุดข้อมูลวิดีโอเลขภาษามือไทย", 2)
    add_body(doc, "Vijitkunsawat, Racharak, Nguyen และ Minh (2023) สร้างชุดข้อมูลวิดีโอเลขภาษามือไทย 9 ท่า มีประมาณ 63 วิดีโอต่อท่า รวม 567 วิดีโอจากผู้ทำท่า 21 คน แล้วเปรียบเทียบ CNN-Mode, CNN-LSTM, VGG-Mode และ VGG-LSTM ทั้งภาพเต็มกับภาพที่ตัดเฉพาะมือ ผลพบว่า VGG-LSTM ร่วมกับการประมวลผลล่วงหน้าให้ผลดีที่สุดทั้งชุดทดสอบภายในและภายนอก งานนี้แสดงความสำคัญของจำนวนผู้ทำท่า การเก็บข้อมูลเป็นวิดีโอ และการรายงานผลกับผู้ทำท่าที่ต่างจากชุดพัฒนา")
    add_heading(doc, "2.9.4 ระบบตรวจจับภาษามือไทยด้วย MediaPipe และ LSTM", 2)
    add_body(doc, "Damrongekarun, Pisitpipattana, Waijanya และ Promrit (2023) ใช้ MediaPipe ดึงจุดสำคัญของมือ ใบหน้า และท่าทางจากวิดีโอ แล้วใช้ LSTM วิเคราะห์ลำดับ แบ่งข้อมูลฝึกและทดสอบ 80:20 ได้ค่า Accuracy 0.83 และนำผลไปแสดงบนแอป Flutter ผ่าน Flask API งานนี้มีโครงสร้างใกล้ HandVox ในด้านการใช้พิกัดจุดสำคัญและการส่งผลเป็นข้อความไทย แต่เลือกแบบจำลองลำดับเชิงลึกแทน SVM")
    add_heading(doc, "2.9.5 การแปลภาษามือไทยเป็นข้อความแบบเวลาจริง", 2)
    add_body(doc, "Jintanachaiwat และคณะ (2024) ใช้ MediaPipe Holistic เก็บจุดมือ ร่างกาย และใบหน้าเป็นลำดับ 30 เฟรม เฟรมละ 1,662 ค่า แล้วเปรียบเทียบ RNN, Bi-RNN, LSTM, Bi-LSTM และ FNN-LSTM สำหรับคำภาษาไทยที่ใช้ในการประชุม ผลของ LSTM บนชุดทดสอบเท่ากับ 100% แต่ลดเหลือ 86% เมื่อทดสอบแบบเวลาจริง ผู้วิจัยระบุว่าการเก็บข้อมูลจากผู้ทำท่าเพียงคนเดียวเสี่ยงต่อ overfitting ผลดังกล่าวยืนยันว่าคะแนนจากชุดทดสอบภายในอาจสูงกว่าการใช้งานจริงและควรเก็บข้อมูลหลายบุคคล")
    add_heading(doc, "2.9.6 ชุดข้อมูลภาษามือระดับคำขนาดใหญ่", 2)
    add_body(doc, "Li, Rodriguez, Yu และ Li (2020) เสนอ WLASL ซึ่งมีภาษามืออเมริกันระดับคำมากกว่า 2,000 คำและผู้ทำท่ามากกว่า 100 คน พร้อมเปรียบเทียบวิธีที่ใช้ภาพลักษณะโดยรวมกับวิธีที่ใช้โครงร่าง และเสนอ Pose-TGCN เพื่อเรียนรู้ความสัมพันธ์เชิงพื้นที่กับเวลา งานนี้แสดงว่าความหลากหลายของผู้ทำท่าและขนาดคำศัพท์ทำให้ปัญหายากขึ้นมาก การเพิ่มคลาสใน HandVox จึงต้องเพิ่มข้อมูลและทดสอบวิธีลำดับที่ซับซ้อนกว่า SVM ควบคู่กัน")
    add_heading(doc, "2.9.7 การรู้จำและการแปลภาษามือต่อเนื่อง", 2)
    add_body(doc, "Camgoz, Hadfield, Koller, Ney และ Bowden (2018) เสนอปัญหา Neural Sign Language Translation และชุดข้อมูล RWTH-PHOENIX-Weather 2014T ซึ่งมีมากกว่า 67,000 หน่วยท่าจากคำศัพท์ภาษามือมากกว่า 1,000 หน่วย งานใช้แนวคิด Neural Machine Translation เพื่อเชื่อมวิดีโอกับประโยคภาษาพูด ผลงานนี้มีขอบเขตกว้างกว่า HandVox เพราะต้องแบ่งท่าต่อเนื่องและจัดการไวยากรณ์ แต่เป็นแนวทางระยะยาวสำหรับการพัฒนาจากการสะสมคำไปสู่การแปลประโยค")

    add_table(doc, ["ผู้วิจัยและปี", "ข้อมูลและวิธี", "ผลสำคัญ", "สิ่งที่ HandVox นำมาใช้"], [
        ["Pariwat และ Seresangtakul (2017)\nKST 2017, หน้า 116–120", "15 ท่า; 75 ภาพ; 5 คน; คุณลักษณะ global/local และ SVM", "RBF เฉลี่ย 91.2%", "เลือก RBF และระบุข้อจำกัดของข้อมูลขนาดเล็ก"],
        ["Nakjai และ Katanyukul (2019)\nDOI: 10.1007/s11265-018-1375-6", "25 ท่า; 125 ภาพ; 11 คน; CNN เทียบ HOG", "mAP 91.26 และเสนอ confidence ratio", "เสนอให้เพิ่มสถานะไม่ทราบและตรวจท่าช่วงเปลี่ยน"],
        ["Vijitkunsawat และคณะ (2023)\nDOI: 10.5220/0011643700003411", "9 ท่าเลข; 567 วิดีโอ; 21 คน; CNN/LSTM และ VGG/LSTM", "VGG-LSTM หลังตัดบริเวณมือให้ผลดีที่สุด", "เก็บวิดีโอหลายคนและแยกทดสอบภายนอก"],
        ["Damrongekarun และคณะ (2023)\nDOI: 10.14456/kkuscij.2023.19", "MediaPipe landmarks, LSTM, แบ่ง 80:20 และแอป Flutter", "Accuracy 0.83", "ใช้พิกัดจุดสำคัญและแสดงผลเป็นข้อความไทย"],
        ["Jintanachaiwat และคณะ (2024)\nDOI: 10.1007/s44163-024-00113-8", "MediaPipe Holistic; 30 เฟรม; เปรียบเทียบ RNN และ LSTM", "LSTM ชุดทดสอบ 100%; เวลาจริง 86%", "แยกผลภายในออกจากเวลาจริงและระวังข้อมูลคนเดียว"],
        ["Li และคณะ (2020)\nWACV 2020, หน้า 1459–1469", "WLASL มากกว่า 2,000 คำ; มากกว่า 100 คน; appearance/pose/Pose-TGCN", "แสดงความท้าทายเมื่อคำและผู้ทำท่าเพิ่ม", "วางแผนขยายข้อมูลและเปรียบเทียบโมเดลลำดับ"],
        ["Camgoz และคณะ (2018)\nDOI: 10.1109/CVPR.2018.00812", "วิดีโอต่อเนื่อง มากกว่า 67,000 หน่วยท่า และ Neural Translation", "แปลภาษามือโดยคำนึงถึงลำดับและไวยากรณ์", "กำหนดขอบเขตปัจจุบันเป็นแยกคำและวางแนวทางอนาคต"],
    ], [3.7, 4.65, 3.15, 3.15], caption="ตารางที่ 2.2 การเปรียบเทียบงานวิจัยที่เกี่ยวข้องกับ HandVox", font_size=10)
    add_body(doc, "สรุปได้ว่าคุณภาพระบบขึ้นกับตัวจำแนก คุณภาพข้อมูล จำนวนผู้ทำท่า และวิธีแบ่งชุดทดสอบ HandVox จึงควรเพิ่มผู้ทำท่า สร้างชุดทดสอบภายนอก เพิ่มสถานะไม่ทราบ และเปรียบเทียบ SVM กับ LSTM ภายใต้ข้อมูลชุดเดียวกัน")

    # Apply the supplied chapter-two form: 20 pt title and 16 pt black
    # headings/body with one blank line before each numbered heading.
    for paragraph in doc.paragraphs[2:]:
        if paragraph.style.name not in {"Caption"}:
            paragraph.paragraph_format.line_spacing = 1.0
        if paragraph.style.name in {"Heading 1", "Heading 2"}:
            paragraph.paragraph_format.left_indent = Cm(0)
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                set_run_font(run, 16, bold=True, color=INK)

    path = OUTPUT / "บทที่ 2_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_2_structured():
    """สร้างบทที่ 2 ฉบับขยาย โดยเชื่อมทฤษฎีกับการทำงานจริงของ HandVox."""
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[2])
    add_chapter_title(doc, 2, "ความรู้พื้นฐาน")
    add_chapter_overview(
        doc,
        "ในการจัดสร้างโครงงาน HandVox จำเป็นต้องศึกษาความรู้พื้นฐาน แนวคิด ทฤษฎี เทคโนโลยี และงานวิจัยที่เกี่ยวข้อง เพื่อกำหนดขอบเขต ออกแบบข้อมูล เลือกแบบจำลอง และประเมินผลระบบอย่างเหมาะสม โดยแบ่งเนื้อหาออกเป็นหัวข้อดังนี้",
        [
            ("2.1", "ภาษามือและการรู้จำ"),
            ("2.2", "การมองเห็นด้วยคอมพิวเตอร์"),
            ("2.3", "จุดสำคัญที่ใช้ใน HandVox"),
            ("2.4", "การปรับมาตรฐานและการแทนลำดับ"),
            ("2.5", "Support Vector Machine"),
            ("2.6", "การแบ่งข้อมูลและการป้องกันการรั่วไหล"),
            ("2.7", "การประเมินผล"),
            ("2.8", "การทำงานแบบเวลาจริงและเสียงพูด"),
            ("2.9", "งานวิจัยที่เกี่ยวข้อง"),
        ],
    )

    def subsection(number, title, paragraphs):
        add_heading(doc, f"{number} {title}", 2)
        for paragraph in paragraphs:
            add_body(doc, paragraph)

    add_body(doc, "การทบทวนเอกสารดำเนินการโดยสืบค้นผ่าน Google Scholar ด้วยคำค้นภาษาไทยและภาษาอังกฤษ เช่น Thai sign language recognition, Thai finger spelling, isolated sign language recognition, MediaPipe Holistic, hand landmarks, Support Vector Machine, signer-independent evaluation และ real-time sign language translation จากนั้นตรวจสอบชื่อผู้แต่ง ปีเผยแพร่ วิธีทดลอง ชุดข้อมูล และผลที่รายงานกับหน้าต้นฉบับของวารสาร การประชุมวิชาการ หรือคลังบทความของผู้เผยแพร่ก่อนนำมาเรียบเรียง")
    add_body(doc, "เนื้อหาในบทนี้แยกความรู้พื้นฐานออกจากผลการดำเนินงานของโครงงาน โดยส่วนทฤษฎีอธิบายหลักการที่ใช้ในการออกแบบ ส่วนที่กล่าวถึงค่าตั้งของ HandVox อ้างอิงจากซอร์สโค้ดและไฟล์กำหนดค่าของระบบรุ่นปัจจุบัน การแยกสองส่วนนี้ช่วยป้องกันการนำผลคาดหมายไปเขียนเสมือนเป็นผลทดลองจริง และทำให้สามารถตรวจสอบย้อนกลับได้ว่าหลักการใดเชื่อมกับองค์ประกอบใดของระบบ")

    # 2.1 ภาษามือและการรู้จำ
    add_heading(doc, "2.1 ภาษามือและการรู้จำ")
    add_body(doc, "ภาษามือเป็นภาษาธรรมชาติในช่องทางการมองเห็นและการเคลื่อนไหว ผู้ใช้สร้างความหมายด้วยมือ แขน ใบหน้า ศีรษะ และลำตัวพร้อมกัน จึงมีลักษณะต่างจากท่าทางสั่งงานทั่วไปซึ่งมักกำหนดสัญลักษณ์จำนวนจำกัดและไม่จำเป็นต้องมีโครงสร้างทางภาษา การพัฒนาระบบรู้จำภาษามือจึงต้องกำหนดให้ชัดว่าระบบกำลังจำแนกท่าที่กำหนดไว้ รู้จำลำดับหน่วยภาษา หรือแปลเป็นประโยคภาษาพูด")

    subsection("2.1.1", "ภาษามือกับท่าทางทั่วไป", [
        "ท่าทางทั่วไปอาจเป็นสัญญาณที่ผู้ออกแบบระบบกำหนดขึ้น เช่น ยกมือเพื่อเริ่มหรือชูนิ้วเพื่อเลือกคำสั่ง แต่ภาษามือมีรูปแบบการใช้ที่เกิดขึ้นในชุมชนผู้ใช้ มีคำศัพท์ หลักการสร้างความหมาย และความแตกต่างระหว่างภาษา ภาษามือไทยจึงไม่ควรถูกแทนด้วยชุดท่าของภาษามือประเทศอื่นโดยตรง แม้บางรูปมืออาจมีลักษณะคล้ายกัน",
        "ระบบคอมพิวเตอร์มองเห็นเพียงข้อมูลภาพหรือพิกัด จึงยังไม่เข้าใจความหมายทางภาษาด้วยตัวเอง ผู้พัฒนาต้องกำหนดป้ายกำกับตัวอย่างให้สอดคล้องกับคำที่ต้องการรู้จำ และต้องอาศัยผู้รู้ภาษามือตรวจความถูกต้องของรูปมือ ทิศทาง จุดเริ่ม จุดสิ้นสุด และบริบทของแต่ละท่า หากป้ายกำกับผิด แบบจำลองจะเรียนรู้ความสัมพันธ์ที่ผิดแม้กระบวนการฝึกจะทำงานสมบูรณ์",
        "สำหรับ HandVox คำว่า การรู้จำ หมายถึงการรับคลิปสั้นของหนึ่งท่าจากเว็บแคมแล้วเลือกป้ายกำกับจากรายการที่ระบบรองรับ ไม่ได้หมายถึงการตีความภาษามือไทยทุกคำหรือการแปลประโยคต่อเนื่อง ข้อจำกัดนี้เป็นส่วนสำคัญของการรายงานผล เพราะความถูกต้องภายในชุดคำ 16 คำไม่สามารถขยายความเป็นความสามารถของระบบแปลภาษามือเต็มรูปแบบได้",
    ])

    subsection("2.1.2", "องค์ประกอบที่สร้างความหมาย", [
        "องค์ประกอบแบบใช้มือประกอบด้วยรูปมือ ตำแหน่งของมือ ทิศทางฝ่ามือ การวางแนวของนิ้ว การเคลื่อนที่ และความสัมพันธ์ระหว่างมือสองข้าง รูปมือที่เหมือนกันอาจให้ความหมายต่างกันเมื่ออยู่คนละตำแหน่งหรือเคลื่อนคนละทิศทาง ดังนั้นการเลือกเฉพาะภาพมือที่ตัดออกจากร่างกายอาจทำให้สูญเสียบริบทสำคัญ",
        "องค์ประกอบที่ไม่ใช้มือประกอบด้วยสีหน้า การเคลื่อนไหวศีรษะ การจ้องมอง ปาก ไหล่ และลำตัว องค์ประกอบเหล่านี้อาจทำหน้าที่เปลี่ยนน้ำเสียงทางภาษา แสดงคำถาม ปฏิเสธ หรือเสริมข้อมูลที่มือไม่ได้สื่อเพียงลำพัง Camgoz และคณะ (2020) ย้ำว่าภาษามือใช้หลายช่องทางพร้อมกัน จึงเป็นปัญหาเชิงพื้นที่และเวลาที่ซับซ้อนกว่าการจำแนกรูปมือ",
        "HandVox รุ่นปัจจุบันใช้จุดสำคัญช่วงบนและมือสองข้าง แต่ไม่ใช้จุดใบหน้ารายละเอียดสูง การตัดสินใจนี้ช่วยลดจำนวนคุณลักษณะและภาระการประมวลผล เหมาะกับต้นแบบคำระดับพื้นฐาน อย่างไรก็ตาม คำที่ต่างกันด้วยสีหน้าหรือรูปปากอาจไม่สามารถแยกได้ดี จึงต้องเลือกชุดคำให้สอดคล้องกับข้อมูลที่ระบบเก็บจริง",
        "ความสัมพันธ์เชิงเวลามีความสำคัญกับท่าที่เคลื่อนไหว เช่น การเคลื่อนเข้าใกล้ลำตัว การหมุนข้อมือ หรือการยกมือขึ้น หากนำทุกเฟรมมาเฉลี่ยเป็นค่าเดียว ระบบอาจสูญเสียทิศทางและลำดับ HandVox จึงเก็บข้อมูลเป็นลำดับ 30 เฟรมและรักษาตำแหน่งของแต่ละเฟรมไว้ในเวกเตอร์สำหรับการจำแนก",
    ])

    subsection("2.1.3", "ระดับของงานรู้จำภาษามือ", [
        "การรู้จำจากภาพนิ่งรับข้อมูลหนึ่งเฟรมและเหมาะกับรูปมือที่มีเอกลักษณ์ชัดเจน ข้อดีคือเก็บข้อมูลง่ายและใช้ทรัพยากรน้อย แต่ไม่สามารถอธิบายท่าที่ความหมายขึ้นกับการเคลื่อนไหวหรือการเปลี่ยนรูปมือหลายช่วง",
        "การรู้จำแบบแยกคำรับคลิปที่มีท่าหนึ่งคำและทราบขอบเขตเริ่มต้นกับสิ้นสุดโดยประมาณ งานลักษณะนี้ยังต้องวิเคราะห์เวลา แต่ไม่ต้องค้นหาว่าคำเริ่มและจบตรงจุดใดในวิดีโอยาว จึงเหมาะกับการสร้างต้นแบบและการประเมินรายคลาส",
        "การรู้จำแบบต่อเนื่องรับวิดีโอหลายคำที่เชื่อมกัน ต้องจัดการช่วงเปลี่ยนระหว่างท่า การกลืนท่าจากคำก่อนหน้าและถัดไป และความยาวของแต่ละคำที่ไม่เท่ากัน ส่วนการแปลภาษามือต้องทำขั้นต่อไป คือเปลี่ยนลำดับหน่วยท่าเป็นประโยคภาษาพูดที่มีลำดับคำและไวยากรณ์ต่างกัน Camgoz และคณะ (2018) จึงแยก Sign Language Recognition ออกจาก Sign Language Translation อย่างชัดเจน",
    ])
    add_table(doc, ["ระดับงาน", "ข้อมูลนำเข้า", "ผลลัพธ์", "ประเด็นสำคัญ"], [
        ["ภาพนิ่ง", "ภาพหนึ่งเฟรม", "คลาสของรูปมือ", "ไม่เก็บลำดับการเคลื่อนไหว"],
        ["แยกคำ", "คลิปหนึ่งท่า", "หนึ่งคำหรือหนึ่งป้ายกำกับ", "ต้องกำหนดช่วงเริ่มและสิ้นสุดให้สม่ำเสมอ"],
        ["ต่อเนื่อง", "วิดีโอหลายท่า", "ลำดับหน่วยท่า", "ต้องแบ่งคำและจัดการช่วงเปลี่ยน"],
        ["การแปล", "วิดีโอภาษามือ", "ประโยคภาษาพูด", "ต้องเรียนรู้ความหมาย ลำดับคำ และไวยากรณ์"],
    ], [2.4, 3.1, 3.65, 5.5], caption="ตารางที่ 2.1 ระดับของงานรู้จำและแปลภาษามือ", font_size=13)

    subsection("2.1.4", "การรู้จำแบบแยกคำของ HandVox", [
        "HandVox กำหนดหนึ่งตัวอย่างเป็นคลิป 30 เฟรมของหนึ่งคำ ผู้ใช้เริ่มจากท่าเตรียม แสดงการเคลื่อนไหวหลัก และจบภายในหน้าต่างข้อมูลเดียวกัน วิธีนี้ทำให้จำนวนคุณลักษณะของทุกตัวอย่างเท่ากันและสามารถใช้ SVM ซึ่งต้องรับเวกเตอร์ขนาดคงที่ได้",
        "ชุดคำที่มองเห็นต่อผู้ใช้มี 16 คำ ได้แก่ สวัสดี ขอโทษ ไม่เป็นไร ขอบคุณ ใช่ ไม่ใช่ ช่วยด้วย ห้องน้ำ น้ำ กิน เจ็บ หมอ เข้าใจ ไม่เข้าใจ ต้องการ และหยุด นอกจากนี้ระบบการฝึกรุ่นใหม่กำหนดคลาสภายใน neutral เพื่อช่วยเรียนรู้กรณีที่ไม่ควรปล่อยคำออกไป คลาสภายในจะใช้ระหว่างการจำแนกแต่ไม่แสดงเป็นคำในประโยค",
        "การเลือกคำควรคำนึงถึงความต่างทางสายตา ความสำคัญต่อสถานการณ์ และความสามารถในการเก็บตัวอย่าง คำที่มีการเคลื่อนไหวคล้ายกันมากต้องมีจำนวนตัวอย่างมากขึ้นและควรตรวจ Confusion Matrix เป็นพิเศษ ส่วนคำ ช่วยด้วย ถูกกำหนดเป็นคำสำคัญซึ่งต้องมี Recall สูงกว่าคำทั่วไปตามเกณฑ์รับรองของโครงการ",
    ])

    subsection("2.1.5", "ความแปรผันและความท้าทาย", [
        "ผู้ทำท่าต่างคนมีขนาดมือ สัดส่วนร่างกาย ความถนัด ความเร็ว และรูปแบบการเคลื่อนไหวไม่เหมือนกัน แม้เป็นคำเดียวกัน ตำแหน่งพิกัดดิบจึงอาจแตกต่างอย่างมาก หากเก็บข้อมูลจากคนเพียงคนเดียว แบบจำลองอาจจดจำลักษณะของบุคคลนั้นมากกว่ารูปแบบของคำ",
        "สภาพการถ่ายภาพเพิ่มความแปรผันจากแสง ฉากหลัง เสื้อผ้า ระยะกล้อง มุมกล้อง ความละเอียด และการบังมือ จุดสำคัญอาจหายหรือกระโดดเมื่อมือเคลื่อนเร็ว อยู่ชิดขอบภาพ หรือซ้อนกับใบหน้าและลำตัว การประเมินในสภาพควบคุมจึงควรแยกจากการทดสอบใช้งานจริง",
        "อีกปัญหาคือท่าช่วงเปลี่ยนระหว่างคำและท่าที่ไม่อยู่ในชุดฝึก ตัวจำแนกแบบปิดจะพยายามเลือกหนึ่งคลาสเสมอ แม้ข้อมูลนำเข้าไม่ใช่คำที่รู้จัก ระบบใช้งานจริงจึงต้องมีเกณฑ์ความเชื่อมั่น คลาส neutral กลไกยืนยันหลายเฟรม และสถานะรอให้ผู้ใช้ปล่อยท่า เพื่อลดการสร้างคำผิดจากช่วงที่ผู้ใช้กำลังเปลี่ยนมือ",
    ])

    # 2.2 การมองเห็นด้วยคอมพิวเตอร์
    add_heading(doc, "2.2 การมองเห็นด้วยคอมพิวเตอร์")
    add_body(doc, "การมองเห็นด้วยคอมพิวเตอร์เป็นกระบวนการทำให้คอมพิวเตอร์รับและแปลงข้อมูลภาพเป็นตัวแทนที่ใช้ตัดสินใจได้ สำหรับ HandVox กระบวนการเริ่มจากเว็บแคม ส่งภาพให้ OpenCV จัดการเฟรม แปลงลำดับสี และส่งเข้า MediaPipe เพื่อประมาณจุดสำคัญ จากนั้นระบบจึงแปลงพิกัดเป็นคุณลักษณะสำหรับแบบจำลอง")

    subsection("2.2.1", "ภาพดิจิทัล วิดีโอ และระบบพิกัด", [
        "ภาพดิจิทัลประกอบด้วยพิกเซลเรียงเป็นตาราง แต่ละพิกเซลเก็บค่าความเข้มของช่องสี วิดีโอคือภาพหลายเฟรมที่เรียงตามเวลา อัตราเฟรมกำหนดความถี่ในการสังเกตการเคลื่อนไหว หากอัตราเฟรมต่ำเกินไป การเคลื่อนไหวเร็วอาจขาดช่วง แต่หากสูงมาก ภาระประมวลผลและจำนวนข้อมูลจะเพิ่มขึ้น",
        "OpenCV อ่านภาพในลำดับสี BGR ขณะที่ MediaPipe รับ RGB โปรแกรมจึงต้องแปลงลำดับสีก่อนประมวลผล หากข้ามขั้นตอนนี้ ค่าช่องสีจะสลับและลดคุณภาพการตรวจจับ แม้ภาพบนหน้าจอยังอาจดูใกล้เคียงในบางกรณี",
        "พิกัดภาพ x และ y มักถูกทำให้เป็นสัดส่วนกับความกว้างและความสูงของเฟรม ส่วนค่า z ของ MediaPipe แทนความลึกเชิงสัมพัทธ์ ไม่ใช่ระยะจริงจากกล้องโดยตรง การใช้พิกัดเหล่านี้ต้องคำนึงว่าความละเอียดภาพ อัตราส่วนภาพ และตำแหน่งผู้ใช้ส่งผลต่อค่าที่ได้",
    ])

    subsection("2.2.2", "บทบาทของ OpenCV", [
        "OpenCV ทำหน้าที่เปิดอุปกรณ์กล้อง อ่านเฟรม กลับภาพในแนวนอน แปลงสี วาดกรอบ แสดงข้อความ และรับคีย์หรือการคลิกจากผู้ใช้ การกลับภาพช่วยให้หน้าจอทำงานเหมือนกระจกซึ่งใช้งานง่าย แต่ต้องใช้แนวทางเดียวกันทั้งตอนเก็บข้อมูลและตรวจจับเพื่อไม่ให้ทิศซ้ายขวาของตัวอย่างต่างกัน",
        "HandVox ขอภาพจากกล้องที่ขนาด 1280 x 720 พิกเซล แต่ความละเอียดจริงขึ้นกับอุปกรณ์และไดรเวอร์ ค่าความละเอียดที่สูงขึ้นช่วยให้เห็นรายละเอียดมือ แต่เพิ่มเวลาถ่ายโอนและประมวลผล ดังนั้นการตั้งค่าควรทดสอบร่วมกับอัตราเฟรมและความหน่วงบนเครื่องเป้าหมาย",
        "ส่วนติดต่อบนภาพกล้องมีหน้าที่มากกว่าการตกแต่ง เพราะช่วยให้ผู้ใช้เห็นว่าระบบตรวจพบร่างกายหรือมือหรือไม่ แสดงคำที่กำลังพิจารณา สถานะยืนยัน ค่าความเชื่อมั่น ประโยคปัจจุบัน และปุ่มควบคุม การให้ข้อมูลย้อนกลับทันทีช่วยให้ผู้ใช้ปรับตำแหน่งและจังหวะการทำท่าได้",
    ])

    subsection("2.2.3", "การตรวจจับและการติดตาม", [
        "การตรวจจับค้นหาว่าวัตถุหรือส่วนร่างกายอยู่บริเวณใดในภาพ ส่วนการติดตามใช้ข้อมูลจากเฟรมก่อนหน้าเพื่อประมาณตำแหน่งในเฟรมถัดไป การติดตามช่วยลดการตรวจใหม่ทุกเฟรมและทำให้พิกัดต่อเนื่องขึ้น แต่หากวัตถุหลุดกรอบหรือถูกบัง ระบบอาจต้องกลับไปตรวจจับใหม่",
        "HandVox ใช้ MediaPipe Holistic ในโหมดวิดีโอต่อเนื่อง กำหนด model_complexity เท่ากับ 1 เปิด smooth_landmarks และกำหนดค่าความเชื่อมั่นขั้นต่ำของการตรวจจับกับการติดตามเท่ากับ 0.70 ค่าดังกล่าวเป็นการประนีประนอมระหว่างคุณภาพ ความเร็ว และความต่อเนื่องของจุดสำคัญ",
        "การทำให้จุดราบรื่นช่วยลดการสั่นจากความคลาดเคลื่อนรายเฟรม แต่มีโอกาสเพิ่มความหน่วงและทำให้การเปลี่ยนเร็วถูกกรองบางส่วน จึงต้องประเมินร่วมกับขนาดหน้าต่าง 30 เฟรมและกลไกยืนยันผล ไม่ควรพิจารณาค่าตั้งของตัวติดตามแยกจากพฤติกรรมทั้งระบบ",
    ])

    subsection("2.2.4", "ภาพดิบกับจุดสำคัญ", [
        "การเรียนรู้จากภาพดิบเก็บข้อมูลพื้นผิว สี รูปร่างมือ ใบหน้า เสื้อผ้า และฉากหลังไว้ครบ แบบจำลองเชิงลึกสามารถเรียนรู้คุณลักษณะจากข้อมูลจำนวนมาก แต่ต้องใช้ทรัพยากรสูงและมีความเสี่ยงเรียนรู้สิ่งรบกวน เช่น สีเสื้อหรือสถานที่ถ่ายภาพ",
        "การใช้จุดสำคัญลดภาพให้เหลือโครงสร้างพิกัดของข้อต่อ ทำให้ข้อมูลมีขนาดเล็กและลดอิทธิพลของพื้นหลัง เหมาะกับโครงการที่มีข้อมูลจำกัดและต้องทำงานบนคอมพิวเตอร์ทั่วไป อย่างไรก็ตาม ความผิดพลาดของตัวประมาณจุดสำคัญจะถูกส่งต่อไปยังตัวจำแนก และรายละเอียดที่ไม่มีในพิกัดจะไม่สามารถกู้คืนได้",
        "แนวทางผสมสามารถใช้ทั้งภาพเฉพาะมือ จุดสำคัญ และลำดับเวลาเพื่อให้แต่ละแหล่งข้อมูลชดเชยข้อจำกัดกัน งาน SAM-SLR ของ Jiang และคณะ (2021) แสดงแนวคิดการรวมข้อมูลภาพ ความลึก และโครงกระดูก แต่ขอบเขตดังกล่าวต้องใช้ข้อมูลและพลังประมวลผลมากกว่า HandVox รุ่นต้นแบบ",
    ])
    add_table(doc, ["ตัวแทนข้อมูล", "ข้อดี", "ข้อจำกัด", "ความเหมาะสมกับ HandVox"], [
        ["ภาพเต็ม", "เก็บบริบทและองค์ประกอบครบ", "มิติสูงและไวต่อฉากหลัง", "เหมาะเมื่อมีข้อมูลและทรัพยากรมาก"],
        ["ภาพเฉพาะมือ", "เน้นรูปมือและรายละเอียดนิ้ว", "สูญเสียตำแหน่งเทียบร่างกาย", "ใช้เสริมคำที่ต่างกันด้วยรูปมือ"],
        ["จุดมือ", "ข้อมูลเล็กและลดผลจากพื้นหลัง", "ไม่เห็นสี พื้นผิว และสีหน้า", "เหมาะกับคำที่รูปมือเด่น"],
        ["จุดมือและช่วงบน", "เห็นรูปมือ ตำแหน่ง และท่าทาง", "ขึ้นกับคุณภาพ landmark", "เป็นตัวแทนหลักของระบบปัจจุบัน"],
        ["หลายรูปแบบร่วมกัน", "ข้อมูลแต่ละชนิดชดเชยกัน", "ซับซ้อนและใช้ทรัพยากรสูง", "เป็นแนวทางพัฒนาต่อยอด"],
    ], [2.8, 3.7, 3.7, 4.45], caption="ตารางที่ 2.2 การเปรียบเทียบตัวแทนข้อมูลภาพสำหรับการรู้จำ", font_size=12)

    subsection("2.2.5", "ปัจจัยของสภาพแวดล้อม", [
        "แสงน้อยทำให้เกิดสัญญาณรบกวนและขอบมือไม่ชัด แสงจากด้านหลังอาจทำให้มือมืดกว่าฉาก ส่วนแสงที่เปลี่ยนระหว่างคลิปทำให้คุณภาพการตรวจจับไม่คงที่ ควรเก็บข้อมูลหลายสภาพแสงแต่ยังต้องรักษาให้มือและช่วงบนมองเห็นได้",
        "มุมกล้องเปลี่ยนรูปร่างที่ฉายลงบนภาพและทำให้พิกัด z มีความคลาดเคลื่อน การฝึกเฉพาะกล้องตรงระดับเดียวอาจให้ผลดีในห้องทดลองแต่ลดลงเมื่อวางกล้องสูงหรือต่ำกว่าเดิม การกำหนดตำแหน่งใช้งานที่แนะนำและการเก็บตัวอย่างหลายมุมจึงเป็นคนละมาตรการที่ควรทำร่วมกัน",
        "การบังเกิดได้เมื่อมือซ้อนกัน มือผ่านใบหน้า หรือหลุดนอกกรอบ ถ้าพบมือเพียงข้างเดียว HandVox เติมศูนย์ให้มือที่หายเพื่อรักษามิติข้อมูล แต่หากจุดหายต่อเนื่องเป็นเวลานาน ตัวอย่างจะมีข้อมูลไม่พอและควรถูกปฏิเสธในขั้นตรวจคุณภาพ",
    ])

    # 2.3 จุดสำคัญ
    add_heading(doc, "2.3 จุดสำคัญที่ใช้ใน HandVox")
    add_body(doc, "จุดสำคัญหรือ landmark เป็นพิกัดตัวแทนตำแหน่งข้อต่อและส่วนของร่างกาย การเลือกจุดต้องครอบคลุมข้อมูลที่จำเป็นต่อการแยกคำโดยไม่เพิ่มมิติที่ไม่จำเป็น HandVox ใช้จุดช่วงบน 15 จุดและจุดมือข้างละ 21 จุด แต่ละจุดมีค่า x, y และ z รวม 171 ค่าในหนึ่งเฟรม")

    subsection("2.3.1", "กรอบงาน MediaPipe", [
        "Lugaresi และคณะ (2019) เสนอ MediaPipe เป็นกรอบงานสำหรับประกอบ perception pipeline จากส่วนรับสื่อ แบบจำลอง และตัวแปลงข้อมูลในรูปกราฟ ช่วยให้พัฒนาต้นแบบ วัดทรัพยากร และนำการประมวลผลไปใช้ข้ามแพลตฟอร์มได้",
        "แนวคิดแบบ pipeline เหมาะกับ HandVox เพราะสามารถแยกขั้นรับภาพ การตรวจจุดสำคัญ การสกัดคุณลักษณะ การสะสมลำดับ และการจำแนกออกจากกัน เมื่อเกิดปัญหาจึงตรวจได้ว่าความผิดพลาดเริ่มจากกล้อง จุดสำคัญ หรือแบบจำลอง",
        "MediaPipe ไม่ได้ทำหน้าที่จำแนกคำภาษามือให้ HandVox โดยตรง แต่ให้พิกัดที่ใช้เป็นข้อมูลนำเข้าของแบบจำลอง SVM ความถูกต้องของระบบสุดท้ายจึงขึ้นกับทั้งตัวตรวจจุดสำคัญและตัวจำแนก ไม่ควรรายงานผลของส่วนใดส่วนหนึ่งแทนประสิทธิภาพทั้งระบบ",
    ])

    subsection("2.3.2", "จุดมือ 21 จุด", [
        "Zhang และคณะ (2020) อธิบาย MediaPipe Hands ว่าใช้ palm detector เพื่อค้นหาบริเวณมือ แล้วใช้ hand landmark model ประมาณโครงมือจากภาพ RGB กล้องเดียว กระบวนการสองขั้นช่วยให้โมเดล landmark ทำงานกับบริเวณที่จัดแนวแล้วและรองรับการติดตามแบบเวลาจริงบนอุปกรณ์",
        "จุดมือ 21 จุดครอบคลุมข้อมือ โคนนิ้ว ข้อนิ้ว และปลายนิ้วทั้งห้า การเปรียบเทียบตำแหน่งระหว่างจุดช่วยอธิบายการงอ เหยียด กาง และทิศทางของนิ้วได้ดีกว่ากรอบสี่เหลี่ยมรอบมือเพียงอย่างเดียว",
        "พิกัดมือยังมีข้อจำกัดเมื่อมือหันด้านข้าง นิ้วซ้อนกัน หรือส่วนหนึ่งอยู่นอกภาพ การทำให้มองเห็นมือชัดและเก็บหลายตัวอย่างจึงยังจำเป็น แม้ตัวตรวจจุดสำคัญจะผ่านการฝึกมาก่อนแล้วก็ตาม",
    ])

    subsection("2.3.3", "จุดช่วงบน 15 จุด", [
        "HandVox เลือกจุดหมายเลข 0, 2, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 23 และ 24 จากโครงร่างของ MediaPipe จุดเหล่านี้ครอบคลุมศีรษะบางส่วน ไหล่ ศอก ข้อมือ และสะโพก ซึ่งเพียงพอสำหรับอธิบายตำแหน่งมือเทียบช่วงบนในคำพื้นฐาน",
        "ไหล่ซ้ายและไหล่ขวาใช้สร้างจุดกึ่งกลางและระยะอ้างอิงในการปรับมาตรฐาน ศอกกับข้อมือช่วยอธิบายแนวแขน ส่วนจุดศีรษะและสะโพกช่วยให้เห็นตำแหน่งโดยรวม การใช้เฉพาะ 15 จุดลดจำนวนคุณลักษณะจากการเก็บโครงร่างทั้งตัว",
        "การตัดจุดขาส่วนล่างออกเหมาะกับกรอบกล้องที่เน้นช่วงบนและคำที่แสดงด้วยมือ แต่ระบบจะไม่เหมาะกับภาษามือหรือท่าทางที่ใช้การเคลื่อนไหวส่วนล่างอย่างมีความหมาย การเลือกจุดจึงเป็นการกำหนดขอบเขตของสิ่งที่แบบจำลองสามารถเรียนรู้ได้",
    ])

    subsection("2.3.4", "การสร้างเวกเตอร์ 171 ค่า", [
        "จุดช่วงบน 15 จุดสร้างข้อมูล 45 ค่า เพราะแต่ละจุดมี 3 แกน มือซ้าย 21 จุดสร้าง 63 ค่า และมือขวาอีก 63 ค่า ผลรวมเท่ากับ 45 + 63 + 63 หรือ 171 ค่าในหนึ่งเฟรม ลำดับคอลัมน์ถูกกำหนดคงที่เป็น pose ก่อน ตามด้วย left_hand และ right_hand",
        "การใช้ลำดับเดียวกันเป็นเงื่อนไขสำคัญ เพราะตัวเลขตำแหน่งหนึ่งไม่มีความหมายในตัวเอง หากขณะฝึกตำแหน่งที่ 46 หมายถึงข้อมือซ้าย แต่ขณะทำนายกลับหมายถึงข้อมือขวา แบบจำลองจะได้รับความหมายคนละแบบแม้จำนวนคุณลักษณะยังเท่ากัน",
        "ไฟล์ body_features.py ถูกใช้ร่วมกันทั้งขั้นเก็บข้อมูลและตรวจจับ เพื่อลดความเสี่ยงที่สูตรปรับมาตรฐาน จำนวนจุด หรือการเติมค่ามือที่หายจะแตกต่างกัน การรวมตรรกะสำคัญไว้ที่เดียวเป็นหลักการควบคุมความสอดคล้องของข้อมูลที่มีผลโดยตรงต่อความถูกต้อง",
    ])
    add_table(doc, ["กลุ่มจุด", "จำนวนจุด", "ค่าต่อจุด", "จำนวนคุณลักษณะ", "หน้าที่"], [
        ["ช่วงบน", "15", "x, y, z", "45", "ตำแหน่งศีรษะ ไหล่ แขน และลำตัว"],
        ["มือซ้าย", "21", "x, y, z", "63", "รูปมือและการเคลื่อนไหวมือซ้าย"],
        ["มือขวา", "21", "x, y, z", "63", "รูปมือและการเคลื่อนไหวมือขวา"],
        ["รวมต่อเฟรม", "57", "3", "171", "ตัวแทนช่วงบนและมือทั้งสองข้าง"],
        ["รวม 30 เฟรม", "-", "-", "5,130", "เวกเตอร์หนึ่งคลิปสำหรับ SVM"],
    ], [2.7, 2.2, 2.6, 2.7, 4.45], caption="ตารางที่ 2.3 จำนวนจุดและมิติคุณลักษณะของ HandVox", font_size=12)

    subsection("2.3.5", "ข้อมูลหายและการระบุข้างของมือ", [
        "หากไม่พบโครงร่างช่วงบน หรือไม่พบมือทั้งสองข้าง ฟังก์ชันสกัดคุณลักษณะจะคืนค่า None และเฟรมนั้นไม่ถูกเพิ่มในลำดับ เพราะไม่มีจุดอ้างอิงหรือไม่มีข้อมูลมือเพียงพอสำหรับการจำแนก",
        "หากพบมือเพียงข้างเดียว ระบบเติมศูนย์ 63 ค่าให้มือที่หาย การเติมศูนย์ช่วยรักษาขนาดเวกเตอร์ แต่ศูนย์หมายถึง ไม่ตรวจพบ ไม่ใช่ตำแหน่งจริงของมือ ดังนั้นจำนวนเฟรมที่เติมศูนย์ควรถูกใช้เป็นตัวชี้วัดคุณภาพคลิปด้วย",
        "การกลับภาพแบบกระจกและการตีความ left_hand กับ right_hand ต้องสอดคล้องกันทุกขั้น หากกระบวนการใดกลับภาพต่างจากอีกกระบวนการ ระบบอาจสลับมือซ้ายและขวา ควรมีการทดสอบแบบหน่วยที่ยืนยันลำดับคอลัมน์และตัวอย่างที่ใช้มือข้างเดียวโดยเฉพาะ",
    ])

    subsection("2.3.6", "ข้อดีด้านขนาดข้อมูลและความเป็นส่วนตัว", [
        "ลำดับจุดสำคัญมีขนาดเล็กกว่าวิดีโอดิบมาก จึงจัดเก็บ โหลด และฝึกได้รวดเร็วขึ้น อีกทั้งลดรายละเอียดใบหน้า เสื้อผ้า และฉากหลังที่ไม่จำเป็นต่อแบบจำลอง เหมาะกับการทดลองหลายรอบและการตรวจเวอร์ชันชุดข้อมูล",
        "อย่างไรก็ตาม พิกัดการเคลื่อนไหวยังเป็นข้อมูลเกี่ยวกับบุคคลและอาจเปิดเผยรูปแบบการเคลื่อนไหวหรือสัดส่วนบางอย่างได้ จึงยังต้องควบคุมสิทธิ์การเข้าถึง ขอความยินยอม และกำหนดระยะเวลาจัดเก็บ ไม่ควรสรุปว่าการตัดภาพออกทำให้ข้อมูลไม่มีความเสี่ยงด้านความเป็นส่วนตัวทั้งหมด",
    ])

    # 2.4 การปรับมาตรฐานและลำดับ
    add_heading(doc, "2.4 การปรับมาตรฐานและการแทนลำดับ")
    add_body(doc, "พิกัดที่ได้จากกล้องแปรผันตามตำแหน่งและระยะของผู้ใช้ HandVox จึงปรับพิกัดให้อ้างอิงร่างกายก่อนเก็บ แล้วนำ 30 เฟรมมาเรียงเป็นเวกเตอร์ขนาดคงที่ วิธีนี้ลดความแปรผันบางส่วนและทำให้แบบจำลอง SVM รับข้อมูลเวลาได้โดยไม่ต้องใช้โครงข่ายลำดับโดยตรง")

    subsection("2.4.1", "การเลื่อนจุดอ้างอิง", [
        "ระบบคำนวณจุดกึ่งกลางระหว่างไหล่ซ้ายกับไหล่ขวาในสามแกน แล้วนำพิกัดของทุกจุดลบด้วยจุดกึ่งกลางดังกล่าว ผลลัพธ์คือพิกัดสัมพันธ์กับลำตัวแทนพิกัดสัมพันธ์กับมุมภาพ",
        "การเลื่อนจุดอ้างอิงช่วยลดผลจากการยืนค่อนไปทางซ้ายหรือขวาและการขยับขึ้นลงเล็กน้อย ตัวอย่างของคำเดียวกันจึงอยู่ในระบบพิกัดใกล้เคียงกันมากขึ้น แต่ไม่แก้ผลของการหมุนตัวหรือการเปลี่ยนมุมกล้องทั้งหมด",
        "การเลือกกึ่งกลางไหล่เหมาะกับงานช่วงบนเพราะตรวจพบได้ค่อนข้างสม่ำเสมอและอยู่ใกล้ศูนย์กลางการเคลื่อนไหวของแขน หากไหล่ถูกบังหรือประมาณผิด ความคลาดเคลื่อนจะกระทบทุกจุดในเฟรมนั้นพร้อมกัน",
    ])

    subsection("2.4.2", "การปรับขนาดด้วยระยะไหล่", [
        "หลังเลื่อนจุด ระบบหารค่าพิกัดด้วยระยะยูคลิดระหว่างไหล่ซ้ายกับไหล่ขวา ระยะดังกล่าวทำหน้าที่เป็นสเกลโดยประมาณของผู้ใช้ในภาพ ช่วยลดผลจากการยืนใกล้หรือไกลกล้องและความแตกต่างของขนาดร่างกาย",
        "โค้ดกำหนดค่าต่ำสุดของสเกลเป็น 1e-6 เพื่อป้องกันการหารด้วยศูนย์ หากตัวตรวจจุดสำคัญให้ตำแหน่งไหล่เกือบตรงกัน การหารด้วยค่าที่เล็กมากอาจสร้างค่าคุณลักษณะสูงผิดปกติ จึงควรตรวจค่าผิดปกติและคุณภาพ landmark ในขั้นเตรียมข้อมูล",
        "การปรับด้วยระยะไหล่ไม่ทำให้ข้อมูลคงที่ต่อมุมมองสามมิติอย่างสมบูรณ์ เพราะระยะที่ฉายบนภาพเปลี่ยนเมื่อผู้ใช้หันตัว และค่า z เป็นความลึกเชิงสัมพัทธ์ ดังนั้นยังควรเก็บข้อมูลหลายมุมที่อยู่ในขอบเขตใช้งานจริง",
    ])

    subsection("2.4.3", "หน้าต่างเวลา 30 เฟรม", [
        "หนึ่งคลิปของ HandVox มี 30 เฟรม จำนวนดังกล่าวสร้างจุดสมดุลระหว่างการเห็นการเคลื่อนไหวทั้งท่าและขนาดข้อมูล หากกล้องทำงานใกล้ 30 เฟรมต่อวินาที หน้าต่างจะครอบคลุมเวลาประมาณหนึ่งวินาที แต่เวลาจริงอาจต่างตามอัตราเฟรมของเครื่อง",
        "ผู้เก็บข้อมูลต้องทำท่าให้จบภายในหน้าต่างเดียวกัน หากทำเร็วมาก ลำดับจะมีช่วงอยู่นิ่งจำนวนมาก หากทำช้าเกินไป ส่วนท้ายของท่าอาจหลุดนอกคลิป ความต่างของจังหวะทำให้ตำแหน่งเหตุการณ์สำคัญอยู่คนละเฟรมและลดความคล้ายของตัวอย่างในคลาสเดียวกัน",
        "การเก็บตัวอย่างหลายจังหวะช่วยให้แบบจำลองเห็นความแปรผัน แต่ต้องไม่กว้างจนขอบเขตของคลาสไม่ชัด ในอนาคตสามารถทดลอง resampling, Dynamic Time Warping หรือแบบจำลองลำดับที่รองรับความยาวไม่เท่ากันเพื่อจัดแนวเวลาให้ดีขึ้น",
    ])

    subsection("2.4.4", "การเรียงลำดับเป็นเวกเตอร์", [
        "เมื่อได้คุณลักษณะ 171 ค่าต่อเฟรม ระบบเรียงเฟรมที่ 1 ถึง 30 ต่อกันเป็นเวกเตอร์ 5,130 ค่า ตำแหน่ง 1-171 แทนเฟรมแรก ตำแหน่ง 172-342 แทนเฟรมที่สอง และดำเนินต่อไปจนถึงเฟรมที่ 30",
        "แม้ SVM จะไม่มีกลไกหน่วยความจำแบบ RNN แต่การวางข้อมูลแต่ละเวลาไว้คนละตำแหน่งทำให้แบบจำลองเห็นรูปแบบของลำดับ ท่าที่เคลื่อนจากซ้ายไปขวาจึงให้เวกเตอร์ต่างจากท่าที่เคลื่อนย้อนกลับ แม้จะมีชุดพิกัดคล้ายกันเมื่อไม่สนลำดับ",
        "ข้อแลกเปลี่ยนคือมิติข้อมูลสูงเมื่อเทียบกับจำนวนคลิป หากมีตัวอย่างน้อย แบบจำลองอาจเรียนรู้รายละเอียดเฉพาะของคลิป การปรับมาตรฐาน การเลือกจุด และการประเมินข้ามผู้ทำจึงมีความสำคัญมากกว่าการพิจารณาความถูกต้องบนชุดฝึก",
    ])
    add_table(doc, ["ขั้นตอน", "ข้อมูลเข้า", "การแปลง", "ข้อมูลออก"], [
        ["ตรวจจุดสำคัญ", "ภาพ RGB", "ประมาณ pose และ hands", "พิกัดจุดของหนึ่งเฟรม"],
        ["เลือกจุด", "จุดทั้งหมด", "เลือกช่วงบน 15 และมือ 42 จุด", "57 จุด"],
        ["เลื่อนพิกัด", "57 จุด", "ลบด้วยกึ่งกลางไหล่", "พิกัดสัมพันธ์กับลำตัว"],
        ["ปรับขนาด", "พิกัดสัมพันธ์", "หารด้วยระยะไหล่", "พิกัดมาตรฐาน 171 ค่า"],
        ["สะสมเวลา", "171 ค่าต่อเฟรม", "เก็บตามลำดับ 30 เฟรม", "เมทริกซ์ 30 x 171"],
        ["แผ่เวกเตอร์", "เมทริกซ์ 30 x 171", "เรียงตามเวลา", "เวกเตอร์ 5,130 ค่า"],
    ], [2.65, 3.4, 4.55, 4.05], caption="ตารางที่ 2.4 ขั้นตอนการแปลงภาพเป็นเวกเตอร์ของหนึ่งคลิป", font_size=12)

    subsection("2.4.5", "ความเร็ว จังหวะ และการจัดแนวเวลา", [
        "ความเร็วของผู้ทำท่าเป็นแหล่งความแปรผันที่ระบบปรับด้วยตำแหน่งและขนาดไม่ได้ หากเหตุการณ์สำคัญเกิดเฟรมที่ 10 ในตัวอย่างหนึ่งแต่เกิดเฟรมที่ 20 ในอีกตัวอย่าง ระยะในเวกเตอร์อาจสูงแม้ความหมายเหมือนกัน",
        "แนวทางพื้นฐานคือให้คำแนะนำการเก็บข้อมูล ใช้ตัวนับก่อนเริ่ม และเก็บหลายรอบในจังหวะธรรมชาติ แนวทางขั้นสูงคือปรับจำนวนเฟรมด้วย interpolation จัดแนวลำดับด้วย Dynamic Time Warping หรือใช้ LSTM, GRU, Temporal Convolution และ Transformer",
        "HandVox เลือกเวกเตอร์คงที่เพื่อให้ระบบง่ายและตรวจสอบได้ การพัฒนาต่อควรเปรียบเทียบวิธีใหม่บนชุดข้อมูลและวิธีแบ่งเดียวกัน เพื่อให้ทราบว่าผลดีขึ้นจากแบบจำลองจริง ไม่ใช่จากการเปลี่ยนเงื่อนไขทดลอง",
    ])

    subsection("2.4.6", "การตรวจคุณภาพคุณลักษณะ", [
        "ก่อนฝึกควรตรวจมิติข้อมูล ค่า NaN ค่าอนันต์ ค่าผิดปกติ จำนวนเฟรมที่มือหาย และการกระจายของแต่ละแกน หากพบคลิปผิดปกติควรย้อนดูวิดีโอตัวอย่างหรือ metadata แทนการลบทิ้งโดยไม่บันทึกเหตุผล",
        "การทำภาพตัวอย่างของเส้นทางจุดหรือสถิติต่อเฟรมช่วยตรวจว่าลำดับไม่กลับด้าน มือไม่สลับ และจุดกึ่งกลางไหล่ทำงานตามคาด การตรวจคุณภาพก่อนฝึกช่วยลดเวลาที่สูญเสียไปกับการปรับแบบจำลองเพื่อแก้ปัญหาซึ่งเกิดจากข้อมูล",
    ])

    # 2.5 SVM
    add_heading(doc, "2.5 Support Vector Machine")
    add_body(doc, "Support Vector Machine หรือ SVM เป็นวิธีการเรียนรู้แบบมีผู้สอนสำหรับจำแนกข้อมูล โดยค้นหาขอบเขตการตัดสินใจที่แยกคลาสและมีระยะขอบกว้าง Cortes และ Vapnik (1995) เสนอ Support-Vector Networks สำหรับข้อมูลที่ไม่สามารถแยกได้สมบูรณ์และใช้การแปลงไปยังปริภูมิคุณลักษณะเพื่อสร้างขอบเขตไม่เชิงเส้น")

    subsection("2.5.1", "ไฮเปอร์เพลนและระยะขอบ", [
        "ในกรณีสองคลาส SVM สร้างไฮเปอร์เพลนเพื่อแบ่งตัวอย่างออกเป็นสองด้าน ตัวอย่างที่อยู่ใกล้ขอบเขตและมีผลต่อคำตอบเรียกว่า support vectors ระยะระหว่างขอบเขตกับตัวอย่างสำคัญทั้งสองด้านเรียกว่า margin",
        "แนวคิดระยะขอบกว้างมุ่งสร้างขอบเขตที่ไม่เพียงแยกข้อมูลฝึก แต่ยังมีพื้นที่เผื่อสำหรับตัวอย่างใหม่ ความสามารถในการทั่วไปจึงขึ้นกับความซับซ้อนของขอบเขต คุณภาพข้อมูล และความเหมาะสมของพารามิเตอร์ ไม่ได้ขึ้นกับการจำแนกชุดฝึกถูกทั้งหมดเพียงอย่างเดียว",
        "ข้อมูลของ HandVox มี 5,130 มิติต่อคลิป แต่จำนวนคลิปต่อคลาสจำกัด SVM เหมาะกับสถานการณ์ที่ตัวแทนคุณลักษณะถูกกำหนดไว้แล้วและชุดข้อมูลยังไม่ใหญ่พอสำหรับโครงข่ายเชิงลึกขนาดมาก อย่างไรก็ตาม มิติสูงยังเพิ่มความเสี่ยง overfitting จึงต้องทดสอบกับผู้ทำที่ไม่อยู่ในชุดฝึก",
    ])

    subsection("2.5.2", "Soft Margin และค่า C", [
        "ข้อมูลจริงมีสัญญาณรบกวนและคลาสอาจซ้อนกัน Soft Margin ยอมให้ตัวอย่างบางส่วนอยู่ผิดด้านของขอบเขตโดยมีค่าปรับ ค่า C ควบคุมการแลกเปลี่ยนระหว่างการลดข้อผิดพลาดบนชุดฝึกกับการรักษาขอบเขตให้เรียบ",
        "ค่า C สูงให้โทษกับตัวอย่างที่จำแนกผิดมาก ขอบเขตจึงพยายามตามข้อมูลฝึกและอาจไวต่อค่าผิดปกติ ค่า C ต่ำยอมให้ผิดมากขึ้นเพื่อสร้างขอบเขตที่เรียบกว่า ไม่มีค่าเดียวที่ดีที่สุดสำหรับทุกข้อมูล จึงควรเลือกด้วย validation ที่ไม่ปะปนกับชุดทดสอบ",
        "HandVox กำหนด C เท่ากับ 10.0 เป็นค่าตั้งต้น ค่านี้ต้องรายงานควบคู่กับ kernel, gamma, class_weight และวิธีแบ่งข้อมูล เพราะผลของ C ไม่สามารถตีความแยกจากค่าที่ควบคุมรูปร่างขอบเขตและสัดส่วนคลาส",
    ])

    subsection("2.5.3", "Kernel และ RBF", [
        "Kernel คำนวณความคล้ายของตัวอย่างเสมือนแปลงข้อมูลไปยังปริภูมิที่ซับซ้อนกว่าโดยไม่ต้องสร้างพิกัดใหม่ทั้งหมด Linear kernel เหมาะเมื่อคลาสแยกได้ด้วยความสัมพันธ์เชิงเส้น ส่วน Polynomial และ RBF รองรับขอบเขตไม่เชิงเส้น",
        "RBF kernel ให้ความคล้ายลดลงตามระยะระหว่างตัวอย่าง ค่า gamma ควบคุมขอบเขตอิทธิพลของแต่ละตัวอย่าง gamma สูงทำให้ขอบเขตละเอียดและเสี่ยงตามสัญญาณรบกวน gamma ต่ำทำให้ขอบเขตกว้างและอาจแยกคลาสที่ซับซ้อนไม่พอ",
        "HandVox ใช้ gamma=scale ซึ่งคำนวณจากจำนวนคุณลักษณะและความแปรปรวนของข้อมูลโดยอัตโนมัติ ค่าเริ่มต้นนี้สะดวกแต่ไม่แทนการค้นหาพารามิเตอร์ ควรเปรียบเทียบกับค่าหลายระดับภายในแต่ละ fold ของผู้ทำท่า",
    ])
    add_table(doc, ["Kernel", "ลักษณะขอบเขต", "ข้อดี", "ข้อควรระวัง"], [
        ["Linear", "เชิงเส้น", "เร็วและตีความง่าย", "อาจไม่พอกับท่าที่สัมพันธ์ซับซ้อน"],
        ["Polynomial", "โค้งตามดีกรี", "แทนปฏิสัมพันธ์หลายระดับ", "ไวต่อ degree, gamma และ coef0"],
        ["RBF", "ไม่เชิงเส้นเฉพาะบริเวณ", "ยืดหยุ่นและใช้แพร่หลาย", "ต้องควบคุม C และ gamma"],
        ["Sigmoid", "คล้ายฟังก์ชันกระตุ้น", "ใช้กับข้อมูลบางชนิด", "ไม่เหมาะกับทุกค่าพารามิเตอร์"],
    ], [2.6, 3.6, 3.75, 4.7], caption="ตารางที่ 2.5 การเปรียบเทียบ Kernel ของ SVM", font_size=12)

    subsection("2.5.4", "การจำแนกหลายคลาส", [
        "SVM พื้นฐานอธิบายในกรณีสองคลาส แต่ HandVox มีหลายคำ ไลบรารี SVC จึงสร้างปัญหาย่อยระหว่างคู่คลาสและรวมผลเพื่อเลือกคำสุดท้าย จำนวนคู่เพิ่มตามจำนวนคลาส ทำให้เวลาฝึกและความซับซ้อนเพิ่มเมื่อขยายคำศัพท์",
        "คู่คำที่สับสนมากควรถูกตรวจรายคู่ใน Confusion Matrix เพราะคะแนนรวมอาจซ่อนปัญหาเฉพาะคลาส การเพิ่มตัวอย่างที่เน้นความแตกต่างของคู่นั้นหรือเพิ่มคุณลักษณะที่เกี่ยวข้องมีโอกาสแก้ปัญหาได้ตรงกว่าการเปลี่ยนแบบจำลองทั้งหมด",
    ])

    subsection("2.5.5", "พารามิเตอร์ของ HandVox", [
        "ไฟล์ training_config.json ระบุ algorithm เป็น SVC ใช้ kernel=rbf, C=10.0, gamma=scale, probability=true, class_weight=balanced และ random_seed=42 การบันทึกค่ากำหนดพร้อมผลทดลองทำให้สามารถสร้างการทดลองซ้ำและเปรียบเทียบรุ่นได้",
        "class_weight=balanced ปรับน้ำหนักผกผันกับจำนวนตัวอย่างของแต่ละคลาส ช่วยลดการเอนเอียงไปยังคลาสที่มีข้อมูลมาก แต่ไม่แก้ปัญหาคุณภาพต่ำหรือความหลากหลายน้อย หากคลาสหนึ่งมีตัวอย่างซ้ำจากคนเดียว น้ำหนักที่สูงขึ้นอาจเพิ่มการเรียนรู้รูปแบบเฉพาะคนนั้น",
        "การปรับพารามิเตอร์ควรทำเฉพาะบนชุดฝึกและ validation ภายใน ไม่ควรดูคะแนนชุดทดสอบแล้วเลือกค่าที่ดีที่สุด เพราะชุดทดสอบจะกลายเป็นส่วนหนึ่งของการพัฒนาและคะแนนสุดท้ายมีอคติ",
    ])

    subsection("2.5.6", "ค่าความน่าจะเป็นและการสอบเทียบ", [
        "SVM ให้คะแนนระยะจากขอบเขตการตัดสินใจ ไม่ได้ให้ความน่าจะเป็นโดยธรรมชาติ เมื่อเปิด probability ไลบรารีจะใช้กระบวนการสอบเทียบเพื่อแปลงคะแนนเป็นค่าความน่าจะเป็น Lin, Lin และ Weng (2007) อธิบายการปรับปรุงวิธี probabilistic outputs ของ SVM เพื่อลดปัญหาเชิงตัวเลข",
        "ค่าจาก predict_proba ใช้จัดอันดับและกำหนดเกณฑ์ปฏิเสธผลได้ แต่ไม่ควรตีความว่า 0.80 หมายถึงถูก 80 เปอร์เซ็นต์ในทุกสภาพแวดล้อม การสอบเทียบอาจเปลี่ยนเมื่อผู้ใช้ กล้อง หรือสัดส่วนคลาสต่างจากข้อมูลฝึก",
        "HandVox ใช้ค่าความเชื่อมั่นขั้นต่ำ 0.65 ในสถานะตรวจจับ ค่านี้ควรเลือกจาก validation โดยพิจารณาทั้ง Recall ของคำสำคัญและอัตราการสร้างคำผิดจาก neutral หากเพิ่มเกณฑ์สูง ระบบอาจปลอดภัยขึ้นแต่พลาดคำจริงมากขึ้น",
    ])

    subsection("2.5.7", "SVM กับแบบจำลองลำดับเชิงลึก", [
        "SVM มีข้อดีด้านความง่าย ความเร็ว และทำงานได้กับชุดข้อมูลขนาดเล็กเมื่อมีคุณลักษณะที่ดี ส่วน LSTM, GRU, Temporal Convolution และ Transformer สามารถเรียนรู้ความสัมพันธ์ตามเวลาได้ยืดหยุ่นกว่า แต่ต้องใช้ข้อมูล การปรับพารามิเตอร์ และทรัพยากรมากขึ้น",
        "การเปรียบเทียบที่ยุติธรรมต้องใช้ตัวอย่าง ชุดแบ่ง และตัวชี้วัดเดียวกัน หากวิธีหนึ่งใช้ผู้ทำท่าซ้ำระหว่างฝึกกับทดสอบ ขณะที่อีกวิธีทดสอบกับผู้ทำใหม่ คะแนนไม่สามารถสรุปว่าแบบจำลองใดดีกว่าได้",
        "สำหรับโครงงานระดับต้นแบบ การใช้ SVM เป็น baseline ที่ตรวจสอบง่ายมีคุณค่า เมื่อจำนวนผู้ทำและคลิปเพิ่มขึ้น จึงค่อยเปรียบเทียบกับ LSTM หรือโมเดลกราฟบนจุดสำคัญ เพื่อวัดว่าความซับซ้อนที่เพิ่มให้ประโยชน์จริงเพียงใด",
    ])

    # 2.6 ข้อมูลและ leakage
    add_heading(doc, "2.6 การแบ่งข้อมูลและการป้องกันการรั่วไหล")
    add_body(doc, "คุณภาพการประเมินขึ้นกับวิธีสร้างและแบ่งชุดข้อมูลอย่างมาก ระบบอาจได้คะแนนสูงโดยไม่สามารถใช้กับบุคคลใหม่ หากคลิปจากผู้ทำหรือเซสชันเดียวกันกระจายอยู่ทั้งชุดฝึกและชุดทดสอบ HandVox รุ่นใหม่จึงเก็บ signer_id, session_id และประเมินแบบ Leave-One-Signer-Out")

    subsection("2.6.1", "การออกแบบชุดข้อมูล", [
        "การออกแบบเริ่มจากนิยามคลาส วิธีทำท่า ขอบเขตเฟรม สภาพแวดล้อม และจำนวนตัวอย่างต่อกลุ่ม คำอธิบายต้องชัดพอให้ผู้เก็บต่างคนสร้างตัวอย่างสอดคล้องกัน แต่ไม่ควรบังคับจังหวะจนขาดความเป็นธรรมชาติ",
        "ค่ากำหนดปัจจุบันมีผู้ทำ person_01 และ person_02 เซสชัน session_01 และ session_02 ตั้งเป้า 10 คลิปต่อผู้ทำต่อคลาส และต้องมีคลิป accepted อย่างน้อย 8 คลิปต่อผู้ทำต่อคลาสก่อนฝึกเต็มรูปแบบ โครงสร้างนี้บังคับให้ตรวจความครบถ้วนแยกตามบุคคล ไม่ใช่นับเพียงยอดรวม",
        "การมีเพียงสองผู้ทำยังจำกัดการทั่วไป แม้ Leave-One-Signer-Out จะแยกคนได้ถูกต้อง ผลแต่ละ fold พึ่งผู้ทดสอบเพียงหนึ่งคน การเพิ่มจำนวนผู้ทำที่ต่างวัย รูปร่างมือ ความถนัด และประสบการณ์ใช้ภาษามือจะทำให้การประเมินน่าเชื่อถือขึ้น",
    ])

    subsection("2.6.2", "การตรวจรับและการปฏิเสธคลิป", [
        "Dataset V2 แยกสถานะคลิปเป็น accepted, pending และ rejected ช่วยให้เก็บตัวอย่างก่อนแล้วตรวจคุณภาพภายหลัง คลิปที่จุดสำคัญหายมาก ทำท่าไม่ครบ ป้ายกำกับผิด หรือมีความผิดปกติควรถูกปฏิเสธพร้อมบันทึกเหตุผล",
        "การตรวจรับต้องใช้เกณฑ์เดียวกันทุกคลาส หากตรวจคำหนึ่งเข้มกว่าคำอื่น ความต่างของคุณภาพจะกลายเป็นสัญญาณที่แบบจำลองเรียนรู้ การสุ่มตรวจซ้ำโดยผู้ตรวจอีกคนช่วยประเมินความสอดคล้องของป้ายกำกับ",
        "การเก็บวิดีโอตัวอย่างไว้ช่วยตรวจย้อนกลับ แต่เพิ่มขนาดและความเสี่ยงด้านความเป็นส่วนตัว ไฟล์กำหนดค่าเปิด save_preview_video จึงควรกำหนดผู้เข้าถึง ระยะเวลาจัดเก็บ และวิธีลบเมื่อไม่จำเป็น",
    ])

    subsection("2.6.3", "การแบ่งแบบ Stratified", [
        "การแบ่งแบบ stratified รักษาสัดส่วนของแต่ละคลาสให้ใกล้เคียงกันระหว่างชุดฝึกกับชุดทดสอบ เหมาะสำหรับการทดสอบเบื้องต้นเมื่อแต่ละคลาสมีตัวอย่างน้อยและต้องการให้ทุกคลาสปรากฏในทั้งสองชุด",
        "ข้อจำกัดคือ stratified ที่พิจารณาเฉพาะป้ายกำกับไม่รู้ว่าคลิปใดมาจากผู้ทำหรือเซสชันเดียวกัน ตัวอย่างที่ใกล้เคียงกันมากอาจอยู่คนละชุด ทำให้คะแนนสูงจากการจดจำบุคคล ฉาก และรูปแบบการเก็บข้อมูล",
        "HandVox ใช้ stratified holdout เฉพาะโหมด quick trial เพื่อประเมินคำใหม่อย่างรวดเร็ว ผลดังกล่าวควรถูกระบุว่าเป็นผลเบื้องต้นและไม่ใช้แทนการรับรองแบบข้ามผู้ทำของการฝึกเต็มรูปแบบ",
    ])

    subsection("2.6.4", "การรั่วไหลของข้อมูล", [
        "Data leakage เกิดเมื่อข้อมูลที่ไม่ควรมีในขั้นฝึกหรือเลือกแบบจำลองส่งผลต่อโมเดล เช่น ใช้ชุดทดสอบเลือกพารามิเตอร์ ปรับมาตรฐานด้วยสถิติรวมทุกชุด หรือปล่อยคลิปจากเซสชันเดียวกันอยู่ทั้งฝึกและทดสอบ",
        "ในข้อมูลวิดีโอ การตัดคลิปยาวหนึ่งไฟล์เป็นหลายหน้าต่างแล้วสุ่มแบ่งหน้าต่างมีความเสี่ยงสูง เพราะเฟรมติดกันแทบเหมือนกัน หากหน้าต่างเหล่านั้นอยู่คนละชุด คะแนนจะวัดความคล้ายของวิดีโอต้นทางมากกว่าความสามารถกับตัวอย่างใหม่",
        "มาตรการป้องกันคือกำหนดกลุ่มก่อนแบ่ง เก็บขั้นตอน preprocessing ไว้ใน pipeline ที่ fit เฉพาะชุดฝึก แยก validation จาก test และบันทึก fingerprint ของชุดข้อมูลที่ใช้ในแต่ละ experiment เพื่อให้รู้ว่าผลใดมาจากข้อมูลรุ่นใด",
    ])
    add_table(doc, ["วิธีแบ่ง", "สิ่งที่ควบคุม", "ข้อดี", "ข้อจำกัด/การใช้"], [
        ["สุ่มทั่วไป", "จำนวนรวม", "ง่ายและเร็ว", "เสี่ยงสัดส่วนคลาสและกลุ่มไม่สมดุล"],
        ["Stratified", "สัดส่วนคลาส", "ทุกคลาสอยู่ในแต่ละชุด", "ไม่ป้องกันผู้ทำหรือเซสชันซ้ำ"],
        ["Group by session", "เซสชัน", "ลดคลิปใกล้เคียงข้ามชุด", "ยังอาจมีผู้ทำคนเดิม"],
        ["Group by signer", "ผู้ทำท่า", "วัดการใช้กับบุคคลใหม่", "ต้องมีผู้ทำหลายคน"],
        ["Leave-One-Signer-Out", "สลับผู้ทำเป็นชุดทดสอบ", "ใช้ข้อมูลทุกคนและรายงานราย fold", "ใช้เวลาฝึกหลายรอบ"],
        ["External test", "แหล่งข้อมูลภายนอก", "ใกล้การใช้งานจริงที่สุด", "ต้องเก็บข้อมูลที่ไม่แตะระหว่างพัฒนา"],
    ], [3.0, 3.1, 3.8, 4.75], caption="ตารางที่ 2.6 การเปรียบเทียบวิธีแบ่งข้อมูล", font_size=12)

    subsection("2.6.5", "Leave-One-Signer-Out", [
        "Leave-One-Signer-Out สร้างจำนวน fold เท่ากับจำนวนผู้ทำ แต่ละ fold ฝึกด้วยข้อมูลของทุกคนยกเว้นหนึ่งคนและใช้คนนั้นเป็นชุดทดสอบ ผลรวมจึงสะท้อนการทั่วไปไปยังผู้ทำที่ไม่เคยเห็นมากกว่าการสุ่มคลิป",
        "HandVox ปัจจุบันมีสองผู้ทำจึงเกิดสอง fold ในแต่ละรอบ แบบจำลองแรกฝึก person_01 และทดสอบ person_02 ส่วนอีกแบบจำลองสลับกัน จากนั้นรวมคำทำนายของทุก fold เพื่อคำนวณตัวชี้วัด aggregate ก่อนฝึก final model ด้วยข้อมูล accepted ทั้งหมดสำหรับใช้งาน",
        "ควรรายงานทั้งผลรวมและผลราย fold หากคนหนึ่งได้คะแนนสูงแต่อีกคนต่ำ ค่าเฉลี่ยเพียงค่าเดียวอาจซ่อนความไม่เท่าเทียม การเพิ่มผู้ทำช่วยให้เห็นการกระจายและสร้างช่วงความเชื่อมั่นได้ดีขึ้น",
    ])

    subsection("2.6.6", "ความไม่สมดุลของคลาส", [
        "คลาสไม่สมดุลทำให้ Accuracy สูงแม้โมเดลละเลยคลาสที่มีน้อย HandVox ตั้งเป้าจำนวนต่อผู้ทำต่อคลาสเท่ากันและใช้ class_weight=balanced เป็นมาตรการเสริม แต่ยังต้องตรวจ support และ Recall รายคลาส",
        "คลาส neutral มีบทบาทต่างจากคำจริง เพราะครอบคลุมท่าที่ไม่ควรปล่อยคำและอาจมีความหลากหลายสูง การเก็บ neutral ควรรวมท่าเตรียม ช่วงเปลี่ยน และท่าที่ไม่อยู่ในรายการ โดยไม่ใช้ตัวอย่างที่คลุมเครือจนทับคำจริง",
    ])

    subsection("2.6.7", "การเพิ่มข้อมูล", [
        "การเพิ่มข้อมูลพิกัดสามารถทำด้วยการรบกวนขนาดเล็ก การเปลี่ยนสเกล การเลื่อนเวลา หรือการตัดบางเฟรม แต่การแปลงต้องรักษาความหมายของคำและไม่สร้างท่าที่เป็นไปไม่ได้ การกลับซ้ายขวาไม่ควรใช้โดยอัตโนมัติ เพราะอาจเปลี่ยนมือถนัดหรือความหมาย",
        "ข้อมูลสังเคราะห์ไม่แทนการเก็บจากผู้ใช้หลายคน ควรใช้เพื่อเพิ่มความทนต่อความแปรผันที่ทราบ และต้องใช้เฉพาะชุดฝึก ไม่ควรสร้างตัวอย่างจากคลิปทดสอบแล้วนำกลับไปฝึก",
    ])

    subsection("2.6.8", "เวอร์ชันและความสามารถในการทำซ้ำ", [
        "ระบบบันทึก training_config snapshot, dataset fingerprint, เวอร์ชันสภาพแวดล้อม, metrics, confusion matrix และ model manifest ในโฟลเดอร์ experiment การเก็บหลักฐานเหล่านี้ทำให้ตรวจย้อนกลับได้ว่าโมเดลใดใช้ข้อมูลและค่ากำหนดชุดใด",
        "การบันทึก random_seed ช่วยให้ขั้นตอนสุ่มซ้ำได้ใกล้เคียงเดิม แต่ไม่รับประกันผลเหมือนกันทุกแพลตฟอร์ม การทำซ้ำที่ดีต้องรวมเวอร์ชันไลบรารี ซอร์สโค้ด และกฎคัดเลือกข้อมูล ไม่ใช่บันทึกเพียง seed",
    ])

    # 2.7 Evaluation
    add_heading(doc, "2.7 การประเมินผล")
    add_body(doc, "การประเมินต้องตอบทั้งความถูกต้องของการจำแนก ความสมดุลระหว่างคลาส ความปลอดภัยของคำสำคัญ และพฤติกรรมแบบเวลาจริง Sokolova และ Lapalme (2009) ชี้ว่าตัวชี้วัดแต่ละชนิดตอบคุณสมบัติของ Confusion Matrix ต่างกัน จึงไม่ควรใช้ Accuracy เพียงค่าเดียว")

    subsection("2.7.1", "Confusion Matrix", [
        "Confusion Matrix จัดแถวเป็นคลาสจริงและคอลัมน์เป็นคลาสที่ทำนาย ค่าบนแนวทแยงคือคำที่ทำนายถูก ส่วนค่านอกแนวทแยงแสดงคู่คำที่สับสน รูปแบบของความผิดพลาดช่วยชี้ว่าควรเพิ่มข้อมูลหรือคุณลักษณะใด",
        "การอ่านต้องพิจารณาจำนวนตัวอย่างต่อแถว หากคลาสหนึ่งมี support น้อย จำนวนผิดเพียงเล็กน้อยอาจเปลี่ยน Recall มาก ควรแสดงทั้งจำนวนจริงและอัตราที่ทำให้เป็นสัดส่วนเมื่อเปรียบเทียบคลาส",
    ])

    subsection("2.7.2", "Accuracy", [
        "Accuracy คือจำนวนตัวอย่างที่ทำนายถูกหารด้วยจำนวนตัวอย่างทั้งหมด เหมาะสำหรับสรุปภาพรวมเมื่อคลาสมีจำนวนใกล้เคียงกันและต้นทุนของความผิดพลาดเท่ากัน",
        "ใน HandVox ความผิดพลาดบางชนิดสำคัญกว่า เช่น พลาดคำ ช่วยด้วย หรือสร้างคำจาก neutral ดังนั้น Accuracy ที่ผ่านเกณฑ์ยังไม่เพียงพอ ต้องตรวจ Recall ของคำสำคัญและอัตรา false positive ของ neutral เพิ่มเติม",
    ])

    subsection("2.7.3", "Precision Recall และ F1-score", [
        "Precision ของคลาสหนึ่งวัดว่าสิ่งที่ระบบทำนายเป็นคลาสนั้นถูกจริงกี่ส่วน ค่า Precision ต่ำหมายถึงระบบเรียกชื่อคลาสนั้นเกินไปและสร้าง false positive มาก",
        "Recall วัดว่าตัวอย่างจริงของคลาสถูกตรวจพบกี่ส่วน ค่า Recall ต่ำหมายถึงระบบพลาดคำจริง สำหรับคำสำคัญที่การพลาดมีผลสูง ควรกำหนดเกณฑ์ Recall เฉพาะแม้ Precision กับ Recall จะมีการแลกเปลี่ยนกัน",
        "F1-score เป็นค่าเฉลี่ยฮาร์มอนิกของ Precision และ Recall จึงต่ำเมื่อค่าใดค่าหนึ่งต่ำมาก เหมาะสำหรับสรุปสมดุลของการตรวจพบและการหลีกเลี่ยงผลบวกผิด แต่ยังควรเปิดดูสองค่าต้นทางเพื่อเข้าใจสาเหตุ",
    ])
    add_table(doc, ["ตัวชี้วัด", "ความหมาย", "สูตรย่อ", "การใช้ใน HandVox"], [
        ["Accuracy", "สัดส่วนที่ทำนายถูกทั้งหมด", "ถูกทั้งหมด / ตัวอย่างทั้งหมด", "เกณฑ์ภาพรวม"],
        ["Precision", "ความถูกต้องของผลที่ทำนายเป็นคลาส", "TP / (TP + FP)", "ตรวจคำที่ระบบปล่อยเกิน"],
        ["Recall", "สัดส่วนคำจริงที่ตรวจพบ", "TP / (TP + FN)", "เน้นคำสำคัญและคลาสที่พลาด"],
        ["F1-score", "สมดุล Precision กับ Recall", "2PR / (P + R)", "สรุปผลรายคลาสและ Macro F1"],
        ["Neutral FPR", "neutral ที่ถูกปล่อยเป็นคำ", "neutral ผิด / neutral ทั้งหมด", "ควบคุม false activation"],
    ], [2.5, 4.4, 3.4, 4.35], caption="ตารางที่ 2.7 ตัวชี้วัดสำหรับการประเมิน HandVox", font_size=12)

    subsection("2.7.4", "ค่าเฉลี่ย Macro และ Weighted", [
        "Macro average คำนวณตัวชี้วัดแยกแต่ละคลาสแล้วเฉลี่ยโดยให้น้ำหนักเท่ากัน จึงสะท้อนว่าระบบทำงานกับคลาสเล็กได้ดีเพียงใด HandVox ใช้ Macro F1 เป็นเกณฑ์หลักร่วมกับ Accuracy",
        "Weighted average ให้น้ำหนักตาม support ของแต่ละคลาส เหมาะกับสรุปผลตามการกระจายข้อมูลจริง แต่คลาสใหญ่มีอิทธิพลมากกว่า การรายงาน Macro และ Weighted ร่วมกันช่วยเปิดเผยว่าคะแนนรวมดีเพราะคลาสใหญ่หรือดีสม่ำเสมอทุกคลาส",
    ])

    subsection("2.7.5", "เกณฑ์ยอมรับของโครงงาน", [
        "training_config.json กำหนด Accuracy ขั้นต่ำ 0.70, Macro F1 ขั้นต่ำ 0.70 และ Recall ต่ำสุดของคำทั่วไป 0.50 เกณฑ์เหล่านี้ใช้เป็นประตูคุณภาพเบื้องต้น ไม่ใช่การรับรองว่าระบบพร้อมใช้ในสถานการณ์เสี่ยงสูง",
        "คำ ช่วยด้วย ถูกกำหนดเป็น critical gesture และต้องมี Recall อย่างน้อย 0.75 ส่วน neutral false positive rate ต้องไม่เกิน 0.20 การมีเกณฑ์เฉพาะสะท้อนต้นทุนความผิดพลาดที่ต่างกันระหว่างคำ",
        "หากการทดลองไม่ผ่าน ระบบยังบันทึกผลและสาเหตุของเกณฑ์ที่ไม่ผ่านเพื่อให้แก้ไขได้ แต่ไม่ควรเปิดใช้โมเดลนั้นเป็นรุ่นหลักโดยอัตโนมัติ ควรตรวจข้อมูลรายคลาส คู่คำสับสน และผลรายผู้ทำก่อนตัดสินใจเก็บข้อมูลเพิ่มหรือปรับแบบจำลอง",
    ])

    subsection("2.7.6", "การประเมินแบบเวลาจริง", [
        "คะแนนบนคลิปที่ตัดไว้ไม่รวมความผิดพลาดจากการเริ่มจับช้า การเลื่อนหน้าต่าง ช่วงเปลี่ยน การไม่พบมือ และการยืนยันผล การทดสอบหน้ากล้องจึงต้องวัดความถูกต้องแบบเหตุการณ์ร่วมกับจำนวนครั้งที่ปล่อยคำซ้ำหรือปล่อยคำโดยไม่มีท่าจริง",
        "ตัวชี้วัดระบบประกอบด้วยอัตราเฟรม ความหน่วงจากเริ่มทำท่าถึงแสดงผล เวลาจากยืนยันถึงเสียงเริ่ม จำนวนเฟรมที่ landmark หาย และการใช้หน่วยประมวลผล ความเร็วที่สูงแต่ผลสั่นไม่ใช่ประสบการณ์ที่ดี ขณะที่ผลนิ่งมากแต่หน่วงหลายวินาทีก็ลดความเป็นธรรมชาติของการสนทนา",
        "การทดสอบควรใช้สถานการณ์ที่ใกล้จริง เช่น เปลี่ยนระยะกล้อง แสง และผู้ใช้ พร้อมกำหนดสคริปต์คำเพื่อเปรียบเทียบรุ่นอย่างยุติธรรม การรายงานแยก offline กับ real-time ป้องกันการนำคะแนนในสภาพง่ายไปอ้างแทนประสิทธิภาพใช้งาน",
    ])

    subsection("2.7.7", "การวิเคราะห์ข้อผิดพลาดและความไม่แน่นอน", [
        "หลังได้ผลควรสุ่มตรวจ true positive, false positive และ false negative ของทุกคลาส พร้อมดูเส้นทาง landmark เพื่อแยกว่าปัญหาเกิดจากป้ายกำกับ จุดสำคัญ หน้าต่างเวลา หรือขอบเขตของแบบจำลอง",
        "คะแนนจากตัวอย่างจำนวนจำกัดมีความไม่แน่นอน ควรรายงานจำนวนผู้ทำ จำนวนคลิป และ support ควบคู่กับร้อยละ เมื่อเพิ่มผู้ทำสามารถใช้การกระจายราย fold หรือช่วงความเชื่อมั่นเพื่อหลีกเลี่ยงการตีความความต่างเล็กน้อยเกินจริง",
        "การประเมินความเท่าเทียมควรเปรียบเทียบผลตามผู้ทำ ความถนัด สภาพแสง และอุปกรณ์ หากกลุ่มใดได้ผลต่ำ ควรเพิ่มข้อมูลและปรับการออกแบบ ไม่ควรแก้ด้วยการตัดกลุ่มนั้นออกจากชุดทดสอบ",
    ])

    # 2.8 Real-time and TTS
    add_heading(doc, "2.8 การทำงานแบบเวลาจริงและเสียงพูด")
    add_body(doc, "ระบบใช้งานจริงต้องแปลงผลจำแนกรายเฟรมให้เป็นคำที่นิ่ง ป้องกันคำซ้ำ สะสมเป็นประโยค และอ่านออกเสียงโดยไม่ทำให้วงรอบกล้องหยุด HandVox จึงใช้หน้าต่างเลื่อน เครื่องสถานะยืนยันผล ตัวจับเวลาค้างท่า ตัวสร้างประโยค และบริการเสียงแบบคิว")

    subsection("2.8.1", "หน้าต่างเลื่อน", [
        "โปรแกรมเก็บคุณลักษณะล่าสุดใน deque ขนาด 30 เฟรม เมื่อครบแล้วทุกเฟรมใหม่จะผลักเฟรมเก่าสุดออกและสร้างเวกเตอร์ใหม่ วิธีนี้ให้ผลต่อเนื่องโดยไม่ต้องรอเก็บคลิปใหม่ทั้งชุดทุกครั้ง",
        "หน้าต่างที่ซ้อนกันมีข้อมูลเหมือนกัน 29 จาก 30 เฟรม ผลทำนายจึงมีความสัมพันธ์สูง การนับทุกผลเป็นหลักฐานอิสระอาจทำให้ความมั่นใจเกินจริง เครื่องสถานะของ HandVox จึงใช้ผลต่อเนื่องเพื่อยืนยันความนิ่ง แต่การประเมินยังต้องนับตามเหตุการณ์หรือคลิป",
        "เมื่อผู้ใช้ปล่อยท่าและระบบตรวจสถานะ released โปรแกรมล้าง motion_frames เพื่อป้องกันเฟรมจากคำเก่าปะปนกับการยกมือรอบใหม่ การล้างที่จุดเปลี่ยนช่วยลดท่าผสมซึ่งไม่มีในชุดฝึก",
    ])

    subsection("2.8.2", "เกณฑ์ความเชื่อมั่นและเครื่องสถานะ", [
        "GestureStateMachine มีสถานะ IDLE, CANDIDATE, CONFIRMED และ COOLDOWN ผลจะถูกพิจารณาเมื่อเห็น landmark มีชื่อคลาส และ confidence ไม่น้อยกว่า 0.65 หากคำเดิมผ่านเงื่อนไขต่อเนื่อง 4 เฟรมจึงเปลี่ยนเป็น CONFIRMED",
        "ถ้าคำเปลี่ยนระหว่าง CANDIDATE ระบบเริ่มนับใหม่ ช่วยลดการยืนยันจากผลชั่วคราว เมื่อยืนยันแล้ว confidence ถูกปรับแบบถัวเฉลี่ยกับผลใหม่เพื่อให้แสดงค่าเสถียรขึ้น",
        "เมื่อผลไม่ผ่าน ระบบซ่อนชื่อเก่าทันที แต่ยังรอ 0.35 วินาทีก่อน reset เพื่อทนต่อ landmark หายชั่วคราว หากเกินเวลาจึงส่ง released และกลับ IDLE การแยกการซ่อนผลออกจากการรีเซ็ตช่วยไม่ให้คำค้างบนหน้าจอพร้อมรักษาความต่อเนื่องระยะสั้น",
        "ค่าทั้งสามคือ confidence 0.65, confirm_frames 4 และ release_seconds 0.35 ปรับได้ใน settings แต่ต้องทดสอบร่วมกัน เกณฑ์สูงและจำนวนเฟรมมากลด false activation แต่เพิ่มความหน่วงและอาจพลาดผู้ใช้ที่ทำท่าเร็ว",
    ])
    add_table(doc, ["ค่าตั้ง", "ค่าเริ่มต้น", "หน้าที่", "ผลเมื่อเพิ่มค่า"], [
        ["min_confidence", "0.65", "ปฏิเสธผลไม่มั่นใจ", "ผลผิดลดลงแต่ Recall อาจลด"],
        ["confirm_frames", "4", "ยืนยันคำซ้ำต่อเนื่อง", "นิ่งขึ้นแต่หน่วงขึ้น"],
        ["release_seconds", "0.35 วินาที", "รอก่อนถือว่าปล่อยท่า", "ทนการหายชั่วคราวแต่รีเซ็ตช้า"],
        ["speak_hold_seconds", "1.0 วินาที", "ค้างท่าก่อนเพิ่มคำ/พูด", "ลดการยิงเร็วแต่สนทนาช้าลง"],
        ["sequence_length", "30 เฟรม", "ขนาดหน้าต่างการเคลื่อนไหว", "เห็นท่ายาวขึ้นแต่เพิ่มมิติและหน่วง"],
    ], [3.2, 2.55, 4.15, 4.75], caption="ตารางที่ 2.8 ค่าตั้งสำคัญของการตรวจจับแบบเวลาจริง", font_size=12)

    subsection("2.8.3", "การป้องกันคำซ้ำและ Cooldown", [
        "หลังเพิ่มหรืออ่านคำ ระบบเรียก mark_emitted เพื่อเข้าสู่ COOLDOWN คำเดิมจะไม่ถูกปล่อยซ้ำจนกว่าผู้ใช้ปล่อยท่าหรือเปลี่ยนเป็นคำใหม่ ช่วยป้องกันหน้าต่างเลื่อนสร้างคำเดิมหลายครั้งจากการค้างมือ",
        "ตัวสร้างประโยคยังมีตัวเลือก prevent_duplicate_words เพื่อไม่เพิ่มคำเดียวกันติดกัน และมี cooldown สำหรับการกดเพิ่มด้วยตนเอง มาตรการหลายชั้นเหมาะกับส่วนติดต่อที่ผู้ใช้สามารถสั่งทั้งอัตโนมัติและด้วยปุ่ม",
        "การป้องกันซ้ำต้องไม่ปิดกั้นกรณีที่ผู้ใช้ต้องการพูดคำเดิมสองครั้ง วิธีออกแบบที่เหมาะคือให้ผู้ใช้ปล่อยท่าชัดเจนระหว่างคำหรือมีปุ่มเพิ่มด้วยตนเอง พร้อมแสดงสถานะว่าระบบกำลังรอการปล่อยท่า",
    ])

    subsection("2.8.4", "การสร้างประโยคและประวัติ", [
        "คำที่ยืนยันสามารถเพิ่มลง SentenceBuilder ลบคำล่าสุด ล้าง อ่าน หรือบันทึกได้ ส่วนติดต่อแสดงจำนวนคำและข้อความปัจจุบัน ช่วยให้ผู้ใช้ตรวจและแก้ก่อนส่งเสียง ลดผลเสียจากการจำแนกผิดหนึ่งคำ",
        "ประวัติประโยคบันทึกแหล่งที่มา เช่น detector-manual หรือ detector-tts และจำกัดจำนวนรายการเริ่มต้น 100 รายการ ข้อมูลประวัติช่วยทบทวนการใช้งาน แต่ต้องให้ผู้ใช้ควบคุมการลบและระวังข้อความส่วนบุคคล",
        "ระบบรองรับการเพิ่มคำอัตโนมัติเมื่อค้างท่าครบหนึ่งวินาทีและการเพิ่มด้วย Space หรือปุ่มบนจอ การมีทางเลือกช่วยรองรับผู้ใช้ต่างรูปแบบ แต่ควรประเมินความเข้าใจของปุ่ม ขนาดตัวอักษร และเวลาตอบสนองกับผู้ใช้จริง",
    ])

    subsection("2.8.5", "Text-to-Speech", [
        "Text-to-Speech เปลี่ยนข้อความไทยเป็นเสียงเพื่อให้คู่สนทนาที่ไม่รู้ภาษามือรับสารได้ HandVox ลองใช้ gTTS สร้างไฟล์เสียงภาษาไทยและเล่นด้วย pygame ก่อน หากบริการออนไลน์ไม่พร้อมจะถอยไปใช้ pyttsx3 แบบออฟไลน์เมื่อมีเสียงที่รองรับ",
        "การสร้างเสียงทำงานใน worker thread และรับข้อความผ่านคิวขนาดจำกัด วงรอบกล้องจึงไม่ต้องรอจนเสียงเล่นจบ เสียงหลายคำถูกเล่นตามลำดับและไม่ทับกัน หากคิวเต็มระบบข้ามข้อความใหม่พร้อมแจ้งเตือนแทนการทำให้หน้าจอค้าง",
        "gTTS ต้องเชื่อมต่อเครือข่ายและสร้างไฟล์ MP3 ชั่วคราว โปรแกรมใช้ชื่อสุ่ม เล่นเสร็จแล้วลบไฟล์ การใช้งานในสถานที่เครือข่ายไม่แน่นอนควรทดสอบเสียงออฟไลน์และตรวจว่ามี voice ภาษาไทยในระบบปฏิบัติการ",
        "คุณภาพเสียงไม่ใช่เพียงความดัง ต้องพิจารณาการออกเสียงคำเฉพาะ ความเร็ว เวลารอก่อนเสียงเริ่ม และความถูกต้องของข้อความต้นทาง ระบบควรให้ผู้ใช้ตรวจประโยคและหยุดหรือล้างคิวได้เมื่อคำผิด",
    ])

    subsection("2.8.6", "การออกแบบสำหรับผู้ใช้", [
        "ส่วนติดต่อควรแสดงกรอบบริเวณที่ตรวจพบ คำปัจจุบัน confidence สถานะ CANDIDATE หรือ CONFIRMED และแถบค้างท่า เพื่อให้ผู้ใช้เข้าใจว่าเหตุใดระบบยังไม่เพิ่มคำ การซ่อนความซับซ้อนทั้งหมดอาจทำให้ผู้ใช้คิดว่าระบบไม่ทำงานเมื่อจริง ๆ กำลังรอยืนยัน",
        "ข้อความต้องอ่านง่ายบนฉากหลังที่เปลี่ยน จึงควรใช้แถบพื้นหลัง สีที่มีความต่าง และขนาดตัวอักษรปรับได้ ปุ่มสำคัญต้องมีทั้งข้อความไทยและคีย์ลัด และไม่วางทับบริเวณมือที่ใช้ทำท่า",
        "การออกแบบควรร่วมกับผู้ใช้หูหนวกหรือผู้ใช้ภาษามือตั้งแต่การเลือกคำ รูปแบบการทำท่า ไปจนถึงการทดสอบ ไม่ควรสรุปความต้องการแทนผู้ใช้จากมุมมองผู้พัฒนาเพียงฝ่ายเดียว",
    ])

    subsection("2.8.7", "ความเป็นส่วนตัวและการนำไปใช้", [
        "ระบบกล้องควรประมวลผลในเครื่องให้มากที่สุดและไม่บันทึกวิดีโอโดยอัตโนมัติในโหมดใช้งาน หากต้องบันทึกเพื่อปรับปรุงโมเดลต้องขอความยินยอม ระบุวัตถุประสงค์ และให้ผู้ใช้ถอนข้อมูลได้",
        "HandVox เป็นเครื่องมือช่วยสื่อสาร ไม่ควรใช้แทนล่ามในสถานการณ์ทางการแพทย์ กฎหมาย หรือเหตุฉุกเฉินโดยไม่มีการตรวจสอบ ความผิดพลาดของคำอาจเปลี่ยนความหมาย จึงต้องแสดงข้อจำกัดและมีช่องทางสื่อสารสำรอง",
    ])

    # 2.9 Related research
    add_heading(doc, "2.9 งานวิจัยที่เกี่ยวข้อง")
    add_body(doc, "งานวิจัยที่คัดเลือกครอบคลุมภาษามือไทย การรู้จำจากภาพและจุดสำคัญ ชุดข้อมูลหลายผู้ทำ การจำแนกแบบแยกคำ และการแปลต่อเนื่อง การเปรียบเทียบไม่ได้มุ่งจัดอันดับจากค่าความถูกต้องเพียงอย่างเดียว เพราะแต่ละงานใช้จำนวนคำ ผู้ทำ อุปกรณ์ และวิธีแบ่งข้อมูลต่างกัน แต่พิจารณาว่าแต่ละงานให้บทเรียนใดต่อการออกแบบ HandVox")

    subsection("2.9.1", "การรู้จำนิ้วสะกดภาษาไทยด้วย SVM", [
        "Pariwat และ Seresangtakul (2017) ศึกษา Thai finger-spelling sign language recognition using global and local features with SVM และเปรียบเทียบ kernel หลายชนิด งานทบทวนภายหลังรายงานว่า RBF ให้ค่าเฉลี่ย 91.20 เปอร์เซ็นต์กับข้อมูล 15 ท่า 75 ภาพจากผู้ทำ 5 คน",
        "งานนี้สนับสนุนว่า RBF สามารถสร้างขอบเขตไม่เชิงเส้นให้คุณลักษณะท่ามือ แต่ข้อมูลเป็นภาพนิ่งและมีขนาดเล็ก ผลจึงไม่ยืนยันความสามารถกับลำดับ 30 เฟรมหรือผู้ใช้ใหม่โดยตรง HandVox นำ SVM-RBF มาเป็น baseline แต่เพิ่มจุดช่วงบน ลำดับเวลา และการประเมินแยกผู้ทำ",
    ])

    subsection("2.9.2", "CNN และการปฏิเสธท่าที่ไม่รู้จัก", [
        "Nakjai และ Katanyukul (2019) พัฒนาระบบรู้จำนิ้วสะกดภาษาไทยแบบสองขั้น เริ่มจากค้นหาและตัดบริเวณมือ แล้วใช้ CNN หรือ HOG จำแนก 25 ท่าจาก 125 ภาพของผู้ทำ 11 คน งานรายงาน mean Average Precision 91.26 และเสนอ confidence ratio เพื่อแยกผลถูกออกจากท่าที่ไม่อยู่ในชุดและช่วงเปลี่ยน",
        "บทเรียนสำคัญต่อ HandVox คือระบบใช้งานต้องมีความสามารถปฏิเสธผล ไม่ใช่บังคับเลือกคลาสทุกครั้ง กลไก neutral, min_confidence และการยืนยันหลายเฟรมตอบปัญหาเดียวกันในระดับระบบ แม้วิธีคำนวณต่างจาก confidence ratio ของงานดังกล่าว",
    ])

    subsection("2.9.3", "นิ้วสะกดหลายจังหวะในฉากซับซ้อน", [
        "Pariwat และ Seresangtakul (2021) เสนอระบบ Multi-Stroke Thai Finger-Spelling โดยใช้ semantic segmentation แยกมือจากฉากหลัง ใช้ optical flow แยกช่วงการเคลื่อนไหว และ CNN เรียนรู้คุณลักษณะ งานนี้แสดงว่าตัวอักษรบางตัวไม่ได้จบในรูปมือเดียวแต่ประกอบด้วยหลาย stroke",
        "แนวคิดการแยก stroke ชี้ว่าหน้าต่างคงที่ของ HandVox อาจยังไม่เหมาะกับคำที่มีหลายช่วงชัดเจน การขยายคำศัพท์ควรตรวจโครงสร้างภายในท่าและพิจารณาการแบ่งช่วงหรือแบบจำลองลำดับแทนการเพิ่มคลาสเข้าสู่เวกเตอร์เดิมทันที",
    ])

    subsection("2.9.4", "ชุดข้อมูลวิดีโอเลขภาษามือไทย", [
        "Vijitkunsawat, Racharak, Nguyen และ Minh (2023) สร้างชุดข้อมูลวิดีโอเลขภาษามือไทย 9 ท่า รวม 567 วิดีโอจากผู้ทำ 21 คน และเปรียบเทียบ CNN-Mode, CNN-LSTM, VGG-Mode และ VGG-LSTM กับทั้งภาพเต็มและภาพที่ตัดเฉพาะมือ",
        "งานรายงานว่า VGG-LSTM ร่วมกับการประมวลผลล่วงหน้าให้ผลดีที่สุดทั้งชุดทดสอบภายในและภายนอก จุดเด่นคือจำนวนผู้ทำมากกว่างานไทยขนาดเล็กหลายงานและมีการทดสอบภายนอก HandVox จึงควรเพิ่มผู้ทำและรักษาชุดทดสอบที่ไม่ใช้ระหว่างพัฒนา",
    ])

    subsection("2.9.5", "MediaPipe และ LSTM สำหรับคำภาษาไทย", [
        "Damrongekarun, Pisitpipattana, Waijanya และ Promrit (2023) ใช้ MediaPipe ดึงจุดมือ ใบหน้า และท่าทางจากวิดีโอ แล้วใช้ LSTM วิเคราะห์ลำดับ แบ่งข้อมูลฝึกและทดสอบ 80:20 รายงาน Accuracy 0.83 และแสดงผลภาษาไทยผ่านแอป Flutter ที่เชื่อม Flask API",
        "โครงสร้างใกล้ HandVox ในด้านการใช้ landmark และการนำผลไปยังส่วนติดต่อ แต่แบบจำลองและสถาปัตยกรรมต่างกัน งานนี้สนับสนุนการใช้พิกัดเป็นตัวแทนข้อมูลและแสดงแนวทางแยกบริการประมวลผลจากแอปผู้ใช้",
    ])

    subsection("2.9.6", "การแปลภาษามือไทยแบบเวลาจริง", [
        "Jintanachaiwat และคณะ (2024) ใช้ MediaPipe Holistic เก็บจุดมือ ร่างกาย และใบหน้าเป็นลำดับ 30 เฟรม เฟรมละ 1,662 ค่า แล้วเปรียบเทียบ RNN, Bi-RNN, LSTM, Bi-LSTM และ FNN-LSTM สำหรับคำที่ใช้ในการประชุม",
        "LSTM ได้ 100 เปอร์เซ็นต์บนชุดทดสอบแต่ลดเหลือ 86 เปอร์เซ็นต์เมื่อทดสอบแบบเวลาจริง ผู้วิจัยระบุข้อจำกัดจากข้อมูลผู้ทำเพียงคนเดียว ความต่างนี้เป็นหลักฐานว่าคะแนน offline ไม่ควรถูกใช้แทนผลหน้ากล้อง และสนับสนุนการประเมินข้ามผู้ทำของ HandVox",
    ])

    subsection("2.9.7", "โปรแกรมแปลภาษามือด้วยจุดมือ", [
        "งาน Smart Application for Thai and English Sign Language Translation (2023) ใช้ MediaPipe ตรวจ 21 จุดต่อมือ รองรับสองมือรวม 42 จุด และจำแนก 68 สัญลักษณ์ ผู้ทดลอง 3 คนทำสัญลักษณ์ละ 5 ครั้ง โดยกำหนดระยะเว็บแคมประมาณ 50 เซนติเมตร งานรายงานผลรวม 95.39 เปอร์เซ็นต์",
        "ผู้วิจัยพบว่าภาษามือไทยบางสัญลักษณ์มีสองระดับของท่าทำให้ผิดพลาดมากกว่าภาษาอังกฤษ ข้อสังเกตนี้สอดคล้องกับความจำเป็นต้องเก็บลำดับและตำแหน่งเทียบร่างกาย HandVox จึงใช้จุดช่วงบนร่วมกับมือ แทนจุดมือเพียงอย่างเดียว",
    ])

    subsection("2.9.8", "WLASL และคำศัพท์ขนาดใหญ่", [
        "Li, Rodriguez, Yu และ Li (2020) เสนอ WLASL ชุดข้อมูลภาษามืออเมริกันระดับคำมากกว่า 2,000 คำจากผู้ทำมากกว่า 100 คน และเปรียบเทียบวิธี appearance กับ pose รวมทั้ง Pose-TGCN ที่เรียนรู้ความสัมพันธ์ของโครงร่างตามเวลา",
        "ผลบนคำศัพท์ขนาดใหญ่แสดงว่าปัญหายากขึ้นมากเมื่อจำนวนคำและความหลากหลายของผู้ทำเพิ่มขึ้น บทเรียนคือการขยาย HandVox จาก 16 คำต้องเพิ่มข้อมูลและทบทวนแบบจำลอง ไม่ควรคาดว่าค่าตั้งเดิมจะขยายได้โดยไม่ลดประสิทธิภาพ",
    ])

    subsection("2.9.9", "AUTSL และการประเมินผู้ทำใหม่", [
        "Sincan และ Keles (2020) สร้าง AUTSL จำนวน 226 ท่า 38,336 วิดีโอจากผู้ทำ 43 คน มี RGB, depth และ skeleton พร้อมฉากและสภาพแสงหลากหลาย ชุด benchmark แยกผู้ทำ 6 คนออกจากชุดฝึกและ validation",
        "งานรายงานว่าความถูกต้องของ baseline สูงถึง 95.95 เปอร์เซ็นต์เมื่อสุ่มแบ่ง แต่เหลือ 62.02 เปอร์เซ็นต์บน user-independent benchmark ช่องว่างนี้แสดงผลของวิธีแบ่งข้อมูลอย่างชัดเจนและสนับสนุน Leave-One-Signer-Out ใน HandVox",
    ])

    subsection("2.9.10", "การรู้จำและแปลภาษามือต่อเนื่อง", [
        "Camgoz, Hadfield, Koller, Ney และ Bowden (2018) เสนอ Neural Sign Language Translation และชุดข้อมูล PHOENIX14T ซึ่งมีมากกว่า 67,000 หน่วยท่าจากคำศัพท์ภาษามือมากกว่า 1,000 หน่วย งานเชื่อมวิดีโอกับประโยคภาษาพูดและแยกการรู้จำหน่วยท่าออกจากการแปล",
        "ต่อมา Camgoz และคณะ (2020) เสนอ Sign Language Transformers ที่เรียนรู้การรู้จำต่อเนื่องและการแปลร่วมกันด้วย CTC และ Transformer งานทั้งสองมีขอบเขตกว้างกว่า HandVox แต่เป็นแนวทางระยะยาวหากต้องพัฒนาจากการสะสมคำแยกคำไปสู่ประโยคที่คำนึงถึงไวยากรณ์",
    ])

    subsection("2.9.11", "การรู้จำจากโครงกระดูกหลายรูปแบบ", [
        "Jiang และคณะ (2021) เสนอ Skeleton Aware Multi-modal Sign Language Recognition ซึ่งใช้ SL-GCN เรียนรู้พลวัตของโครงกระดูกทั้งตัวและรวมข้อมูลหลายรูปแบบ งานได้อันดับสูงในการแข่งขัน isolated sign language recognition บน AUTSL",
        "แนวคิดกราฟสอดคล้องกับธรรมชาติของ landmark ที่จุดเชื่อมกันเป็นโครงสร้าง ไม่ใช่เพียงรายการตัวเลข การพัฒนาต่อสามารถสร้างกราฟมือและช่วงบนเพื่อเรียนรู้ความสัมพันธ์เชิงพื้นที่กับเวลา แต่ต้องเปรียบเทียบกับ SVM บนข้อมูลเดียวกันและระวัง overfitting เมื่อข้อมูลยังน้อย",
    ])

    subsection("2.9.12", "การสังเคราะห์ช่องว่างของงานวิจัย", [
        "งานไทยจำนวนหนึ่งรายงานผลสูงในชุดข้อมูลขนาดเล็กหรือการสุ่มแบ่ง ขณะที่งานชุดข้อมูลขนาดใหญ่แสดงว่าคะแนนลดลงชัดเจนเมื่อทดสอบกับผู้ทำใหม่ ความแตกต่างไม่ได้หมายความว่างานหนึ่งด้อยกว่า แต่อธิบายว่าความยากของโจทย์และวิธีประเมินมีผลต่อค่าที่รายงาน",
        "HandVox เติมช่องว่างในระดับต้นแบบด้วยการใช้ landmark ช่วงบนและมือ ลำดับ 30 เฟรม SVM-RBF คลาส neutral เครื่องสถานะเวลาจริง และการประเมิน Leave-One-Signer-Out พร้อมเกณฑ์รายคลาส จุดแข็งคือกระบวนการตรวจสอบย้อนกลับได้และใช้ทรัพยากรทั่วไป",
        "ข้อจำกัดยังอยู่ที่จำนวนผู้ทำเพียงสองคน คำศัพท์ 16 คำ หน้าต่างคงที่ และการไม่ใช้รายละเอียดใบหน้า งานต่อยอดที่มีความสำคัญที่สุดคือเพิ่มผู้ทำและเซสชัน สร้าง external test เพิ่ม neutral ที่หลากหลาย และเปรียบเทียบ SVM กับ LSTM หรือกราฟบนชุดแบ่งเดียวกัน",
    ])

    add_table(doc, ["งานวิจัย", "ข้อมูล/วิธี", "ผลหรือข้อค้นพบ", "บทเรียนสำหรับ HandVox"], [
        ["Pariwat และ Seresangtakul (2017)", "15 ท่า 75 ภาพ 5 คน; global/local features และ SVM", "RBF เฉลี่ย 91.20%", "ใช้ RBF เป็น baseline แต่ต้องเพิ่มลำดับและผู้ทำ"],
        ["Nakjai และ Katanyukul (2019)\nDOI 10.1007/s11265-018-1375-6", "25 ท่า 125 ภาพ 11 คน; CNN/HOG", "mAP 91.26; confidence ratio", "ต้องปฏิเสธท่าที่ไม่รู้จักและช่วงเปลี่ยน"],
        ["Pariwat และ Seresangtakul (2021)\nDOI 10.3390/sym13020262", "multi-stroke; segmentation, optical flow, CNN", "จัดการหลาย stroke และฉากซับซ้อน", "ท่าหลายช่วงอาจต้องแบ่งหรือใช้โมเดลลำดับ"],
        ["Vijitkunsawat และคณะ (2023)", "9 ท่า 567 วิดีโอ 21 คน; CNN/LSTM และ VGG/LSTM", "VGG-LSTM หลังตัดมือให้ผลดีที่สุด", "เพิ่มผู้ทำและทดสอบภายนอก"],
        ["Damrongekarun และคณะ (2023)\nDOI 10.14456/kkuscij.2023.19", "MediaPipe landmarks, LSTM, 80:20", "Accuracy 0.83; Flutter/Flask", "ใช้ landmark และแยกส่วนบริการกับหน้าจอ"],
        ["Jintanachaiwat และคณะ (2024)\nDOI 10.1007/s44163-024-00113-8", "MediaPipe Holistic 30 เฟรม; RNN/LSTM", "test 100%; real-time 86%", "รายงาน offline แยกจากเวลาจริง"],
        ["Smart Application (2023)\nDOI 10.14456/jait.2023.13", "42 จุดมือ 68 สัญลักษณ์ 3 คน", "รวม 95.39%; ท่าไทยสองระดับยากกว่า", "ใช้ช่วงบนและลำดับเสริมจุดมือ"],
        ["Li และคณะ (2020) WLASL", ">2,000 คำ >100 คน; appearance/pose/Pose-TGCN", "คำศัพท์ใหญ่มีความท้าทายสูง", "การเพิ่มคลาสต้องเพิ่มข้อมูลและโมเดล"],
        ["Sincan และ Keles (2020) AUTSL\nDOI 10.1109/ACCESS.2020.3028072", "226 ท่า 38,336 วิดีโอ 43 คน", "random 95.95%; user-independent 62.02%", "วิธีแบ่งผู้ทำมีผลต่อคะแนนมาก"],
        ["Camgoz และคณะ (2018) PHOENIX14T", ">67,000 หน่วยท่า; Neural Translation", "เชื่อมวิดีโอกับประโยคภาษาพูด", "แยกการรู้จำออกจากการแปล"],
        ["Camgoz และคณะ (2020)", "CTC และ Transformer แบบร่วม", "รู้จำต่อเนื่องและแปล end-to-end", "แนวทางอนาคตสำหรับประโยคต่อเนื่อง"],
        ["Jiang และคณะ (2021) SAM-SLR", "SL-GCN และข้อมูลหลายรูปแบบ", "ใช้โครงกระดูกทั้งตัวและเวลา", "landmark สามารถแทนเป็นกราฟได้"],
    ], [3.4, 4.25, 3.4, 3.6], caption="ตารางที่ 2.9 การเปรียบเทียบงานวิจัยที่เกี่ยวข้องกับ HandVox", font_size=10)

    add_body(doc, "จากแนวคิดและงานวิจัยทั้งหมด สรุปได้ว่าการสร้างระบบรู้จำภาษามือที่น่าเชื่อถือไม่ได้ขึ้นกับตัวจำแนกเพียงส่วนเดียว แต่เป็นผลร่วมของการกำหนดขอบเขตภาษา คุณภาพป้ายกำกับ ความหลากหลายของผู้ทำ คุณภาพ landmark การแทนลำดับ วิธีแบ่งข้อมูล ตัวชี้วัด และกลไกควบคุมผลแบบเวลาจริง")
    add_body(doc, "HandVox เลือกสถาปัตยกรรมที่เหมาะกับต้นแบบ ได้แก่ เว็บแคม OpenCV, MediaPipe Holistic, คุณลักษณะ 171 ค่าต่อเฟรม, ลำดับ 30 เฟรม, SVM-RBF, Leave-One-Signer-Out, neutral class และ Text-to-Speech การพัฒนาบทต่อไปจึงต้องรักษาความสอดคล้องขององค์ประกอบเหล่านี้ตั้งแต่การเก็บข้อมูลจนถึงการทดสอบหน้ากล้อง")
    add_heading(doc, "2.9.13 ข้อสังเคราะห์เพื่อการออกแบบ HandVox", 2)
    add_body(doc, "ผลการทบทวนชี้ให้เห็นว่าแบบจำลองที่มีคะแนนสูงจากการแบ่งข้อมูลแบบสุ่มอาจยังไม่พร้อมใช้กับผู้ทำคนใหม่ ดังนั้นค่า Accuracy จึงต้องอ่านควบคู่กับ Macro F1, Recall รายคลาส, Confusion Matrix และผล Leave-One-Signer-Out การรายงานให้ครบช่วยให้เห็นทั้งความสามารถทั่วไปของระบบและจุดที่ยังต้องปรับปรุงอย่างตรงไปตรงมา")
    add_body(doc, "ในระดับการออกแบบ ระบบควรแยกความรับผิดชอบของแต่ละส่วนให้ชัดเจน ได้แก่ ส่วนกล้องและการแปลงสี ส่วนตรวจ landmark ส่วนสร้างเวกเตอร์คุณลักษณะ ส่วนจำแนกคำ และส่วนแสดงข้อความหรือเสียง การแยกส่วนเช่นนี้ทำให้ย้อนตรวจได้ว่าความผิดพลาดเกิดจากกล้อง จุดสำคัญ ลำดับเฟรม หรือแบบจำลอง ไม่ควรสรุปว่าเป็นข้อผิดพลาดของ SVM เพียงอย่างเดียว")
    add_body(doc, "สำหรับข้อมูลฝึก การกำหนดคลิป accepted, pending และ rejected เป็นหลักฐานของคุณภาพข้อมูล ไม่ใช่ขั้นตอนที่ควรถูกข้าม คลิปที่ landmark หาย มือถูกบัง ป้ายกำกับไม่ตรง หรือเริ่มท่าไม่ตรงจังหวะต้องมีเหตุผลกำกับ การเก็บ metadata ของผู้ทำ เซสชัน และสภาพแวดล้อมจึงช่วยให้คัดแยกข้อมูล ป้องกันการรั่วไหล และทำการทดลองซ้ำได้")
    add_body(doc, "สำหรับการใช้งานจริง ค่าความมั่นใจและกลไกยืนยันผลมีความสำคัญไม่แพ้ความแม่นยำออฟไลน์ HandVox จึงใช้ min_confidence, confirm_frames, release_seconds และ cooldown เพื่อไม่ปล่อยคำซ้ำหรือคำที่เกิดจากท่าผ่าน ระบบควรแสดงสถานะที่ผู้ใช้เข้าใจได้ พร้อมเปิดทางให้แก้ไขหรือพูดซ้ำเมื่อผลยังไม่แน่นอน")
    add_body(doc, "ผลจากงานวิจัยยังเสนอทิศทางต่อยอดอย่างเป็นขั้นตอน หากเพิ่มคำศัพท์ เพิ่มผู้ทำ หรือเพิ่มการเคลื่อนไหวที่ซับซ้อน ควรเพิ่มข้อมูลและทดสอบภายนอกก่อนพิจารณา LSTM, Transformer หรือแบบจำลองกราฟจาก landmark การเปลี่ยนแบบจำลองโดยไม่เพิ่มคุณภาพและความหลากหลายของข้อมูลอาจทำให้ต้นแบบซับซ้อนขึ้น แต่ไม่ได้ทำให้เชื่อถือได้มากขึ้น")
    add_body(doc, "ขอบเขตของ HandVox รุ่นนี้จึงเป็นการรู้จำคำแบบแยกคำจากชุดคำที่กำหนดไว้ เพื่อช่วยสื่อสารเบื้องต้น ไม่ใช่ระบบแปลภาษามือแทนมนุษย์ในทุกบริบท")

    # Apply the supplied chapter-two form: 20 pt title and 16 pt black
    # headings/body with one blank line before each numbered heading.
    for paragraph in doc.paragraphs[2:]:
        if paragraph.style.name not in {"Caption"}:
            paragraph.paragraph_format.line_spacing = 1.0
        if paragraph.style.name in {"Heading 1", "Heading 2"}:
            paragraph.paragraph_format.left_indent = Cm(0)
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                set_run_font(run, 16, bold=True, color=INK)

    path = OUTPUT / "บทที่ 2_HandVox_ฉบับขยาย_ทฤษฎีและงานวิจัย_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_3_structured():
    """บทที่ 3 ตามรูปแบบ 3.1 วิเคราะห์ 3.2 ออกแบบ และ 3.3 ดำเนินการสร้าง."""
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[3])
    add_chapter_title(doc, 3, "วิธีดำเนินการจัดทำโครงงาน")

    add_heading(doc, "3.1 การวิเคราะห์ปัญหา")
    add_body(doc, "จากการศึกษาปัญหาพบว่า การสื่อสารระหว่างผู้ใช้ภาษามือกับบุคคลทั่วไปยังต้องพึ่งล่าม การเขียน หรือการพิมพ์ข้อความในหลายสถานการณ์ วิธีดังกล่าวอาจใช้เวลานานและไม่สะดวกเมื่อผู้ใช้ต้องสื่อสารอย่างต่อเนื่อง โครงงานจึงกำหนดปัญหาหลักเป็นการสร้างต้นแบบที่รับท่าทางจากเว็บแคม จำแนกคำที่ระบบรู้จัก และนำเสนอผลเป็นข้อความกับเสียงภาษาไทยโดยใช้อุปกรณ์ที่หาได้ทั่วไป")
    add_body(doc, "การวิเคราะห์ข้อมูลนำเข้าพบว่า ภาษามือหนึ่งคำไม่ได้ขึ้นกับรูปมือเพียงเฟรมเดียว แต่เกี่ยวข้องกับตำแหน่งช่วงบน ทิศทาง และลำดับการเคลื่อนไหว ระบบจึงต้องเก็บข้อมูลหลายเฟรมต่อเนื่องและรักษาลำดับของจุดสำคัญให้เหมือนกันทั้งขณะเก็บข้อมูล ฝึกแบบจำลอง และทำนายแบบเวลาจริง หากลำดับคุณลักษณะไม่ตรงกัน แบบจำลองจะตีความค่าคนละความหมายและให้ผลผิดพลาดได้")
    add_body(doc, "ข้อจำกัดที่ต้องคำนึงถึง ได้แก่ ความแตกต่างของรูปร่างมือ ระยะจากกล้อง มุมกล้อง แสง ฉากหลัง ความเร็วในการทำท่า การบังมือ และจำนวนข้อมูลต่อคำ นอกจากนี้ ระบบรุ่นนี้เป็นการรู้จำแบบแยกคำจากรายการที่กำหนดไว้ ไม่ได้แปลภาษามือแบบต่อเนื่องหรือวิเคราะห์ไวยากรณ์ จึงต้องกำหนดความสามารถและขอบเขตการใช้งานให้ชัดเจนก่อนออกแบบ")

    add_heading(doc, "3.1.1 ความต้องการของระบบ", 2)
    add_numbered_list(doc, [
        "รับภาพจากเว็บแคมและตรวจจับช่วงบนกับมืออย่างน้อยหนึ่งข้างได้ต่อเนื่อง",
        "เก็บข้อมูลหนึ่งท่าเป็นลำดับ 30 เฟรม และจัดรูปแบบข้อมูลทุกคลิปให้มีมิติเท่ากัน",
        "เพิ่มหรือลบท่า เก็บคลิป ตรวจข้อมูล และฝึกแบบจำลองใหม่ได้โดยไม่แก้ซอร์สโค้ดหลัก",
        "จำแนกเฉพาะท่าที่อยู่ในชุดข้อมูล พร้อมแสดงชื่อท่าและค่าความเชื่อมั่น",
        "สะสมคำเป็นประโยค ลบหรือล้างข้อความ และอ่านออกเสียงภาษาไทยได้",
        "จัดการกรณีกล้อง ข้อมูล แบบจำลอง หรือระบบเสียงไม่พร้อมโดยไม่ทำให้โปรแกรมค้าง",
    ])

    add_heading(doc, "3.1.2 เกณฑ์และข้อจำกัดในการพัฒนา", 2)
    add_body(doc, "ระบบต้องสร้างเวกเตอร์ 171 ค่าต่อเฟรมจากจุดช่วงบน 15 จุดและมือข้างละ 21 จุด แล้วเรียงข้อมูล 30 เฟรมเป็น 5,130 ค่าต่อคลิป แบบจำลองต้องบันทึกคู่กับตัวเข้ารหัสชื่อคลาส และก่อนทำนายต้องตรวจว่าจำนวนคุณลักษณะกับรายชื่อคลาสตรงกับการตั้งค่าปัจจุบัน")
    add_body(doc, "การประเมินภายในใช้ Accuracy, Precision, Recall, F1-score และ Confusion Matrix แต่คะแนนดังกล่าวยังไม่ยืนยันการใช้งานกับบุคคลทั่วไป หากข้อมูลฝึกและทดสอบมาจากผู้ทำท่าหรือสภาพแวดล้อมใกล้เคียงกัน ดังนั้นระบบต้องเก็บ metadata ของผู้ทำท่าและเซสชันไว้สำหรับการแบ่งข้อมูลแบบแยกกลุ่มในระยะต่อไป")

    add_heading(doc, "3.2 การออกแบบการจัดสร้างโครงงาน")
    add_body(doc, "การออกแบบ HandVox แบ่งระบบเป็นองค์ประกอบย่อยที่เชื่อมต่อกัน ได้แก่ การรับภาพ การตรวจหาจุดสำคัญ การปรับมาตรฐานพิกัด การสะสมลำดับเฟรม การจัดการชุดข้อมูล การฝึกแบบจำลอง การทำนาย และการนำเสนอผล การแบ่งหน้าที่ช่วยให้ตรวจสอบความผิดพลาดและเปลี่ยนส่วนประกอบได้โดยไม่กระทบทั้งระบบ")

    add_heading(doc, "3.2.1 การออกแบบสถาปัตยกรรมระบบ", 2)
    add_body(doc, "เว็บแคมส่งภาพเข้าสู่ OpenCV แล้วแปลงสีเพื่อให้ MediaPipe Holistic ตรวจหาจุดสำคัญ ฟังก์ชัน body_features.py เลือกเฉพาะจุดที่ใช้ ปรับพิกัดด้วยจุดกึ่งกลางและระยะระหว่างไหล่ และคืนเวกเตอร์ 171 ค่า เมื่อสะสมครบ 30 เฟรม ระบบเรียงเป็นเวกเตอร์ 5,130 ค่าเพื่อส่งให้ SVM จำแนก ผลลัพธ์ผ่านการตรวจค่าความเชื่อมั่นและการรวมผลย้อนหลัง ก่อนแสดงชื่อท่า ประโยค และเสียงพูด")
    add_body(doc, "เส้นทางเก็บข้อมูลกับเส้นทางทำนายใช้ฟังก์ชันสกัดคุณลักษณะเดียวกัน เพื่อให้จำนวน ลำดับ และการเติมศูนย์เมื่อไม่พบมือข้างหนึ่งเหมือนกัน ภาพจากกล้องใช้ระหว่างประมวลผล ส่วนข้อมูลหลักที่บันทึกเป็นพิกัดจุดสำคัญและ metadata ซึ่งช่วยลดขนาดไฟล์และลดรายละเอียดภาพที่ไม่จำเป็น")
    add_figure(doc, ASSETS / "handvox_architecture.png", "ภาพที่ 3.1 สถาปัตยกรรมการประมวลผลของ HandVox")

    add_heading(doc, "3.2.2 วัสดุ อุปกรณ์ และซอฟต์แวร์", 2)
    add_table(doc, ["ประเภท", "รายการ", "หน้าที่"], [
        ["ฮาร์ดแวร์", "คอมพิวเตอร์ Windows 10 หรือ 11", "พัฒนา เก็บข้อมูล และฝึกแบบจำลอง"],
        ["ฮาร์ดแวร์", "เว็บแคม 1280 × 720 พิกเซล", "รับภาพช่วงบนและมือของผู้ใช้"],
        ["ฮาร์ดแวร์", "ลำโพงหรือหูฟัง", "ตรวจสอบเสียงภาษาไทย"],
        ["ซอฟต์แวร์", "Python 3.10 หรือ 3.11 และ OpenCV", "ควบคุมกล้องและส่วนติดต่อ"],
        ["ไลบรารี", "MediaPipe Holistic", "ตรวจจุดสำคัญของร่างกายและมือ"],
        ["ไลบรารี", "NumPy และ scikit-learn", "จัดรูปข้อมูลและฝึก SVM"],
        ["ไลบรารี", "Pillow, gTTS และ pygame", "แสดงภาษาไทย สร้างและเล่นเสียง"],
        ["ข้อมูล", "NPZ, Dataset V2 และไฟล์ PKL", "เก็บลำดับท่า metadata และแบบจำลอง"],
    ], [2.55, 5.25, 6.85], caption="ตารางที่ 3.1 วัสดุ อุปกรณ์ และซอฟต์แวร์ที่ใช้", font_size=13)
    add_body(doc, "OpenCV ทำหน้าที่ติดต่อกล้องและวาดหน้าจอ MediaPipe สกัดจุดสำคัญ NumPy จัดการอาร์เรย์ scikit-learn ฝึกและเรียกใช้ SVC ส่วน Pillow, gTTS และ pygame รองรับอักษรไทย การสร้างเสียง และการเล่นเสียง หากบริการสร้างเสียงไม่พร้อม ระบบรู้จำและแสดงข้อความต้องยังทำงานต่อได้")

    add_heading(doc, "3.2.3 การออกแบบข้อมูลและส่วนติดต่อ", 2)
    add_body(doc, "ชุดข้อมูลออกแบบให้หนึ่งรายการแทนการทำท่าหนึ่งครั้งด้วยอาร์เรย์ขนาด 30 × 171 และป้ายกำกับหนึ่งชื่อ Dataset V2 เพิ่มรหัสผู้ทำท่า รหัสเซสชัน เวลาเก็บ และสถานะคุณภาพ เพื่อให้ตรวจย้อนหลังและแบ่งชุดทดสอบตามบุคคลได้ ไฟล์กำหนดค่ารวบรวมชื่อท่า คำอธิบาย สี และค่าตั้งสำคัญเพื่อป้องกันการกระจายค่าคงที่ไว้หลายไฟล์")
    add_body(doc, "ส่วนติดต่อขณะเก็บข้อมูลต้องแสดงชื่อท่า จำนวนคลิป ความคืบหน้าของ 30 เฟรม และสถานะว่าพบจุดสำคัญหรือไม่ ส่วนหน้าทำนายต้องแสดงกรอบผู้ใช้ ชื่อท่า ค่าความเชื่อมั่น ประโยค ปุ่มควบคุม และสถานะเสียง โดยจัดให้ผลหลักอ่านได้ชัดเจนและไม่บดบังมือของผู้ใช้")

    add_heading(doc, "3.3 การดำเนินการสร้าง (ตัวอย่างโค้ดบางส่วน)")
    add_body(doc, "การดำเนินงานเริ่มจากกำหนดรายการท่าและโครงสร้างข้อมูล แล้วพัฒนาแต่ละองค์ประกอบตามลำดับเพื่อให้สามารถทดสอบแยกส่วนได้ กระบวนการหลักมีดังต่อไปนี้")
    add_numbered_list(doc, [
        "กำหนดขอบเขต รายการท่า ค่าตั้ง และโครงสร้างไฟล์ของโครงการ",
        "พัฒนาฟังก์ชันตรวจจุดสำคัญและสร้างคุณลักษณะ 171 ค่าต่อเฟรม",
        "พัฒนาหน้าจอเก็บคลิปและบันทึกหนึ่งท่าให้ครบ 30 เฟรม",
        "ตรวจรูปร่างข้อมูล ป้ายกำกับ จำนวนคลิป และ metadata ก่อนฝึก",
        "แปลงคลิปเป็นเวกเตอร์ 5,130 ค่า แบ่งข้อมูล และฝึก SVM แบบ RBF",
        "บันทึกแบบจำลอง ตัวเข้ารหัสชื่อคลาส และข้อมูลการทดลอง",
        "พัฒนาการทำนายแบบเวลาจริง การสะสมประโยค และเสียงภาษาไทย",
        "ทดสอบกรณีปกติ กรณีผิดพลาด และบันทึกข้อจำกัดเพื่อปรับปรุง",
    ])

    add_heading(doc, "3.3.1 การเก็บและจัดเตรียมข้อมูล", 2)
    add_body(doc, "ก่อนเก็บข้อมูล ผู้จัดทำตรวจชื่อท่าไม่ให้ซ้ำและกำหนดคำอธิบายการเคลื่อนไหวให้ชัดเจน กล้องถูกจัดให้อยู่ในระดับที่มองเห็นศีรษะ ไหล่ ศอก ข้อมือ และนิ้วมือ ผู้ทำท่าเริ่มและจบการเคลื่อนไหวภายในหน้าต่าง 30 เฟรม โปรแกรมรับเฉพาะเฟรมที่พบช่วงบนและมืออย่างน้อยหนึ่งข้าง")
    add_body(doc, "แต่ละคำถูกเก็บหลายครั้งโดยเปลี่ยนจังหวะ ระยะ และตำแหน่งเล็กน้อยโดยไม่เปลี่ยนความหมาย เพื่อให้แบบจำลองเห็นความแปรผันตามธรรมชาติ Dataset V2 แยกข้อมูลตามผู้ทำท่าและเซสชัน พร้อมบันทึกสถานะ accepted หรือ rejected ทำให้สามารถตรวจคุณภาพและป้องกันคลิปที่ไม่สมบูรณ์เข้าสู่ชุดฝึก")
    add_figure(doc, COLLECTION_FIGURE, "ภาพที่ 3.2 ตัวอย่างหน้าจอเก็บคลิปท่าทางของ HandVox")

    add_heading(doc, "3.3.2 การสกัดและปรับมาตรฐานคุณลักษณะ", 2)
    add_body(doc, "ระบบใช้จุดช่วงบน 15 จุดและจุดมือข้างละ 21 จุด รวม 57 จุด จุดละพิกัด x, y และ z จึงได้ 171 ค่าต่อเฟรม จุดกึ่งกลางไหล่ใช้เป็นต้นกำเนิด และระยะระหว่างไหล่ใช้เป็นตัวปรับขนาด หากพบมือเพียงข้างเดียวจะเติมศูนย์ 63 ค่าให้มือที่หาย แต่ถ้าไม่พบช่วงบนหรือไม่พบมือทั้งสองข้างจะไม่รับเฟรมนั้น")
    add_code_block(doc, "ตัวอย่างโค้ดที่ 3.1 การสร้างเวกเตอร์คุณลักษณะ", """def extract_features(results):
    pose = results.pose_landmarks
    left_hand = results.left_hand_landmarks
    right_hand = results.right_hand_landmarks
    if pose is None or (left_hand is None and right_hand is None):
        return None
    center, scale = _normalizer(pose)
    pose_points = [pose.landmark[index] for index in POSE_IDS]
    return (_encode(pose_points, center, scale, len(POSE_IDS))
            + _encode(left_hand.landmark if left_hand else None,
                      center, scale, HAND_POINTS)
            + _encode(right_hand.landmark if right_hand else None,
                      center, scale, HAND_POINTS))""")
    add_body(doc, "ฟังก์ชันในไฟล์จริงใช้ลำดับจุดคงที่และคืนค่า None เมื่อข้อมูลไม่เพียงพอ ทั้ง collect_data.py และ run_detector.py เรียกใช้ฟังก์ชันเดียวกัน จึงลดความเสี่ยงที่ข้อมูลฝึกกับข้อมูลทำนายมีความหมายไม่ตรงกัน")

    add_heading(doc, "3.3.3 การฝึกแบบจำลอง", 2)
    add_body(doc, "ก่อนฝึก โปรแกรมตรวจขนาดอาร์เรย์ จำนวนป้ายกำกับ และความครบถ้วนของคลิป จากนั้นใช้ LabelEncoder แปลงชื่อท่าเป็นรหัสและเรียงข้อมูล 30 × 171 เป็นเวกเตอร์ 5,130 ค่า การทดลองคัดกรองแบ่งข้อมูลแบบ stratified 80:20 และใช้ random seed 42 ส่วนแผนประเมินมาตรฐานของ Dataset V2 กำหนดให้แยกผู้ทำท่าระหว่างฝึกกับทดสอบ")
    add_body(doc, "แบบจำลองใช้ SVC แบบ RBF กำหนด C เท่ากับ 10, gamma เป็น scale, probability เป็น true และ class_weight เป็น balanced ค่า probability ทำให้ระบบนำค่าประกอบการตัดสินใจไปใช้ในเวลาจริง ส่วน class_weight ช่วยลดผลจากจำนวนตัวอย่างแต่ละคลาสที่ไม่เท่ากัน เมื่อฝึกเสร็จจะบันทึกแบบจำลองและตัวเข้ารหัสชื่อคลาสเพื่อโหลดใช้ร่วมกัน")
    add_code_block(doc, "ตัวอย่างโค้ดที่ 3.2 การกำหนดและฝึก SVC", """parameters = {
    "kernel": "rbf", "C": 10.0, "gamma": "scale",
    "probability": True, "class_weight": "balanced",
}
classifier = SVC(random_state=42, **parameters)
classifier.fit(train_x, train_y)
prediction = classifier.predict(test_x)""")

    add_heading(doc, "3.3.4 การทำนายแบบเวลาจริง", 2)
    add_body(doc, "โปรแกรมโหลดแบบจำลองกับตัวเข้ารหัส ตรวจจำนวนคุณลักษณะและรายชื่อคลาส แล้วเปิดเว็บแคม เมื่อได้เฟรมที่ผ่านเงื่อนไขจะเพิ่มเวกเตอร์ลงในคิวล่าสุด 30 เฟรม เมื่อคิวเต็มจึงเรียงข้อมูลและเรียก predict_proba เพื่อหาคลาสที่มีค่าสูงสุด")
    add_body(doc, "ผลทำนายต้องผ่านเกณฑ์ความเชื่อมั่นและการยืนยันหลายเฟรมก่อนแสดงเป็นคำ ระบบใช้ผลย้อนหลังเพื่อลดการสั่น และล้างคิวเมื่อผู้ใช้ปล่อยมือนานเกินช่วงที่กำหนด เพื่อไม่ให้เฟรมจากท่าเก่าปะปนกับท่าครั้งใหม่ คำที่ยืนยันแล้วสามารถเพิ่มลงในประโยค ลบ ล้าง หรืออ่านออกเสียงภาษาไทยได้")
    add_code_block(doc, "ตัวอย่างโค้ดที่ 3.3 การทำนายจากลำดับ 30 เฟรม", """motion_frames.append(features)
if len(motion_frames) == SEQUENCE_LENGTH:
    sequence = np.asarray(motion_frames, dtype=np.float32)
    sequence = sequence.reshape(1, -1)
    probability = model.predict_proba(sequence)[0]
    index = int(np.argmax(probability))
    label = label_encoder.classes_[index]
    confidence = float(probability[index])""")
    add_table(doc, ["ปุ่ม", "การทำงาน", "เงื่อนไข"], [
        ["Space", "เพิ่มคำล่าสุดลงในประโยค", "ต้องมีผลที่ยืนยันแล้ว"],
        ["Backspace", "ลบคำล่าสุด", "ประโยคต้องไม่ว่าง"],
        ["Enter", "ล้างประโยค", "เริ่มข้อความใหม่"],
        ["S", "อ่านประโยคเป็นเสียงไทย", "มีข้อความและระบบเสียงพร้อม"],
        ["Esc", "ออกจากโปรแกรม", "คืนกล้องและปิดหน้าต่าง"],
    ], [2.6, 6.3, 5.75], caption="ตารางที่ 3.2 การควบคุมระบบขณะใช้งาน", font_size=13)

    add_heading(doc, "3.3.5 การทดสอบและควบคุมคุณภาพ", 2)
    add_body(doc, "การทดสอบครอบคลุมทั้งเส้นทางปกติและเหตุการณ์ผิดพลาด ตั้งแต่ความพร้อมของกล้อง ความครบถ้วนของข้อมูล ความสอดคล้องระหว่างโมเดลกับรายการท่า การตอบสนองเมื่อค่าความเชื่อมั่นต่ำ ไปจนถึงการทำงานต่อเมื่อระบบเสียงไม่พร้อม แต่ละกรณีกำหนดผลที่คาดหวังไว้เพื่อให้ตรวจซ้ำได้")
    add_table(doc, ["กรณีทดสอบ", "ผลที่คาดหวัง"], [
        ["ไม่พบช่วงบนหรือมือ", "ไม่เพิ่มเฟรมและไม่ทำนาย"],
        ["คลิปไม่ครบ 30 เฟรม", "ไม่บันทึกเป็นตัวอย่างสมบูรณ์"],
        ["มีป้ายกำกับไม่พอ", "หยุดฝึกและแจ้งให้เพิ่มข้อมูล"],
        ["โมเดลไม่ตรงกับรายการท่า", "หยุดทำนายและแจ้งให้ฝึกใหม่"],
        ["ค่าความเชื่อมั่นต่ำ", "ไม่ยืนยันชื่อท่า"],
        ["ผู้ใช้ปล่อยมือนานเกินกำหนด", "ล้างคิวและสถานะเดิม"],
        ["ระบบเสียงใช้งานไม่ได้", "ยังแสดงข้อความและทำนายต่อได้"],
    ], [7.0, 7.65], caption="ตารางที่ 3.3 กรณีทดสอบการทำงานของระบบ", font_size=13)
    add_body(doc, "หลังการทดสอบ ระบบบันทึกเวอร์ชันชุดข้อมูล รายชื่อคลาส ค่าตั้งแบบจำลอง จำนวนตัวอย่าง และผลประเมินไว้ร่วมกัน เมื่อเปลี่ยนข้อมูลหรือซอฟต์แวร์จะสร้างรอบทดลองใหม่แทนการเขียนทับผลเดิม และสำรองข้อมูลก่อนลบท่าหรือรีเซ็ตชุดข้อมูล เพื่อให้สามารถตรวจย้อนกลับและทำซ้ำการทดลองได้")

    add_heading(doc, "3.3.6 การบันทึกเวอร์ชันและการส่งมอบระบบ", 2)
    add_body(doc, "ไฟล์ที่ใช้ส่งมอบประกอบด้วยซอร์สโค้ด รายการไลบรารี ไฟล์กำหนดค่า คู่มือเก็บข้อมูล ชุดข้อมูลที่ได้รับอนุญาตให้ใช้ แบบจำลอง ตัวเข้ารหัสชื่อคลาส และรายงานผลการทดลอง แต่ละรอบระบุวันที่ เวอร์ชัน รายชื่อท่า จำนวนคลิป และค่าตั้งที่ใช้ เพื่อป้องกันการนำโมเดลคนละรุ่นไปใช้กับรายการคำหรือโครงสร้างข้อมูลที่ไม่ตรงกัน")
    add_body(doc, "ก่อนส่งมอบ ผู้จัดทำทดสอบการเปิดโปรแกรมบนเครื่องเป้าหมาย ตรวจสิทธิ์เข้าถึงกล้อง ความพร้อมของแบบอักษรและเสียง เส้นทางไฟล์ และการคืนทรัพยากรเมื่อปิดโปรแกรม พร้อมจัดทำขั้นตอนสำรองและกู้คืนข้อมูล หากผู้ใช้เพิ่มหรือลบท่า ต้องเก็บข้อมูลให้ครบ ฝึกใหม่ และตรวจรายชื่อคลาสก่อนนำแบบจำลองรุ่นใหม่มาใช้งาน")

    # Apply the supplied chapter-three form: 20 pt chapter title and 16 pt
    # black headings/body with one clear blank line before each heading.
    for paragraph in doc.paragraphs[2:]:
        if paragraph.style.name not in {"Caption"}:
            paragraph.paragraph_format.line_spacing = 1.0
        if paragraph.style.name in {"Heading 1", "Heading 2"}:
            paragraph.paragraph_format.left_indent = Cm(0)
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                set_run_font(run, 16, bold=True, color=INK)

    path = OUTPUT / "บทที่ 3_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_4_structured():
    """บทที่ 4 แสดงผลการทดลองและการประเมินตามแบบฟอร์ม."""
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[4])
    add_chapter_title(doc, 4, "ผลการดำเนินงาน")

    add_heading(doc, "ผลการวิเคราะห์และทดลอง")
    add_body(doc, "ชุดข้อมูล HandVox มี 350 คลิป แต่ละคลิปประกอบด้วยข้อมูล 30 เฟรมและแต่ละเฟรมมี 171 คุณลักษณะ รวมเป็นเวกเตอร์ 5,130 ค่าต่อคลิป ชุดข้อมูลมี 16 ป้ายกำกับ จำนวนตัวอย่างต่อป้ายกำกับอยู่ระหว่าง 10–30 คลิป การตรวจสอบไม่พบค่า NaN หรือ infinity และไม่พบคลิปที่ซ้ำกันทุกค่าแบบตรงตัว")
    add_body(doc, "ข้อมูลถูกจัดเก็บเป็นอาร์เรย์ชนิด float32 รูปร่าง 350 × 30 × 171 การตรวจสอบมิติยืนยันว่าทุกคลิปมีจำนวนเฟรมและจำนวนคุณลักษณะเท่ากัน จึงสามารถเรียงเป็นเมทริกซ์สองมิติสำหรับ SVM ได้โดยไม่ต้องเติมความยาวเพิ่มเติม สัดส่วนค่าศูนย์ประมาณ 12.93% ซึ่งรวมทั้งค่าที่เกิดจากมือที่ตรวจไม่พบและค่าที่เป็นศูนย์จริงหลังปรับมาตรฐาน")
    add_body(doc, "ชุดข้อมูลประกอบด้วยข้อมูลฐานเดิม 120 คลิปจาก 4 ท่า และ Dataset V2 จำนวน 230 คลิปจาก 12 ท่า ข้อมูล Dataset V2 มีรหัสผู้ทำท่า 2 รหัสและเซสชัน 2 รอบ พร้อมสถานะ accepted ส่วนข้อมูลฐานเดิมไม่มี metadata ระดับบุคคลและเซสชัน ความแตกต่างนี้เป็นข้อจำกัดสำคัญเมื่อต้องการแบ่งข้อมูลแบบแยกผู้ทำท่า")
    add_table(doc, ["รายการ", "ผลที่ตรวจสอบได้", "ความหมาย"], [
        ["รูปร่างชุดข้อมูล", "350 × 30 × 171", "350 คลิป; คลิปละ 30 เฟรม; เฟรมละ 171 ค่า"],
        ["จำนวนป้ายกำกับ", "16 ป้ายกำกับ", "ท่าที่ระบบสามารถจำแนกได้ในรุ่นปัจจุบัน"],
        ["จำนวนต่อป้ายกำกับ", "10–30 คลิป", "ข้อมูลยังไม่สมดุล"],
        ["ชนิดข้อมูล", "float32", "สอดคล้องกับขั้นตอนฝึกและทำนาย"],
        ["ค่าที่ไม่เป็นจำนวนจำกัด", "ไม่พบ", "ทุกค่าผ่านการตรวจสอบ"],
        ["คลิปซ้ำแบบตรงตัว", "0 คลิป", "คลิปทั้ง 350 รายการมีเวกเตอร์ต่างกัน"],
    ], [4.0, 4.2, 6.45], caption="ตารางที่ 4.1 ผลการตรวจสอบชุดข้อมูล HandVox", font_size=13)
    add_table(doc, ["กลุ่มป้ายกำกับ", "จำนวนต่อท่า", "จำนวนคลิป", "สถานะข้อมูล"], [
        ["ขอบคุณ ขอโทษ สวัสดี และไม่เป็นไร", "30", "120", "ข้อมูลฐานเดิม ไม่มี metadata รายคลิป"],
        ["กิน ช่วยด้วย ต้องการ น้ำ หมอ หยุด ห้องน้ำ เข้าใจ เจ็บ ใช่ และไม่เข้าใจ", "20", "220", "Dataset V2 มีรหัสผู้ทำท่าและเซสชัน"],
        ["ไม่ใช่", "10", "10", "Dataset V2 มีรหัสผู้ทำท่าและเซสชัน"],
        ["รวม 16 ท่า", "10–30", "350", "ใช้ร่วมกันในการทดลองรอบปัจจุบัน"],
    ], [5.8, 2.4, 2.4, 4.05], caption="ตารางที่ 4.2 การกระจายจำนวนคลิปในชุดข้อมูล", font_size=13)
    add_body(doc, "จำนวนตัวอย่างที่ไม่เท่ากันทำให้คลาสที่มี 30 คลิปมีอิทธิพลต่อการฝึกมากกว่าคลาสที่มี 10 คลิป โครงการจึงเปิด class_weight=balanced เพื่อถ่วงน้ำหนัก แต่การถ่วงน้ำหนักไม่สามารถทดแทนความหลากหลายของข้อมูลได้ โดยเฉพาะคลาสที่มีผู้ทำท่าหรือเซสชันจำนวนน้อย จึงยังต้องเก็บข้อมูลเพิ่มอย่างสมดุล")

    add_body(doc, "การทดลองแบ่งข้อมูลแบบ stratified holdout 80:20 โดยใช้ชุดฝึก 280 คลิปและชุดทดสอบ 70 คลิป กำหนด random state เท่ากับ 42 และใช้ SVC แบบ RBF ที่มี C=10, gamma=scale, probability=True และ class_weight=balanced การทดลองนี้ใช้สำหรับประเมินต้นแบบภายในชุดข้อมูลปัจจุบัน")
    add_table(doc, ["รายการ", "ค่าที่ใช้", "รายละเอียด"], [
        ["การแบ่งข้อมูล", "80:20 แบบ stratified", "ฝึก 280 คลิป; ทดสอบ 70 คลิป"],
        ["Random state", "42", "ทำซ้ำการแบ่งเดิมได้"],
        ["แบบจำลอง", "SVC แบบ RBF", "C=10 และ gamma=scale"],
        ["การรายงานความเชื่อมั่น", "probability=True", "ใช้ประกอบการทำนายแบบเวลาจริง"],
        ["การถ่วงคลาส", "class_weight=balanced", "ลดผลจากจำนวนคลิปที่ไม่เท่ากัน"],
    ], [4.1, 4.4, 6.15], caption="ตารางที่ 4.3 การตั้งค่าการทดลอง", font_size=13)
    add_body(doc, "การแบ่งแบบ stratified ทำให้ทุกคลาสมีตัวอย่างอยู่ในชุดฝึกและชุดทดสอบตามสัดส่วนเดิม โดยคลาสหนึ่งมีตัวอย่างในชุดทดสอบประมาณ 2–6 คลิป การกำหนด random state ช่วยให้ทำซ้ำการแบ่งรอบนี้ได้ แต่ไม่ได้ทำให้ผลเป็นอิสระจากผู้ทำท่า หากคลิปที่คล้ายกันจากเซสชันเดียวกันอยู่คนละชุด คะแนนยังอาจสูงกว่าการทดสอบกับข้อมูลใหม่")
    add_body(doc, "แบบจำลองไม่ได้ปรับพารามิเตอร์จากชุดทดสอบในรอบนี้ การตั้งค่า C และ gamma ใช้ค่าที่กำหนดในซอร์สโค้ด การทดลองจึงมีลักษณะเป็น quick trial สำหรับตรวจว่ากระบวนการและคุณลักษณะสามารถแยกคลาสเบื้องต้นได้หรือไม่ ก่อนวางแผนสร้างชุดตรวจสอบและเปรียบเทียบพารามิเตอร์อย่างเป็นระบบ")

    add_body(doc, "แบบจำลองทำนายถูก 66 จาก 70 คลิปและผิด 4 คลิป คิดเป็น Accuracy 94.29% ค่า Macro Precision, Macro Recall และ Macro F1 เท่ากับ 93.75% โดย 14 จาก 16 คลาสได้ผลสมบูรณ์ในรอบทดลอง ส่วนท่า “เข้าใจ” และ “ไม่เข้าใจ” มี F1 เท่ากับ 0.500 และถูกทำนายสลับกัน")
    add_table(doc, ["ตัวชี้วัด", "ผลลัพธ์", "การตีความ"], [
        ["ทำนายถูก / ผิด", "66 / 4 คลิป", "ชุดทดสอบรวม 70 คลิป"],
        ["Accuracy", "94.29%", "ผลรวมของการทำนายทุกคลาส"],
        ["Macro Precision", "93.75%", "ให้น้ำหนักทุกคลาสเท่ากัน"],
        ["Macro Recall", "93.75%", "สองคลาสมีค่าต่ำกว่าคลาสอื่น"],
        ["Macro F1", "93.75%", "ผลเฉลี่ยรายคลาส"],
    ], [4.0, 3.3, 7.35], caption="ตารางที่ 4.4 ผลการประเมินภาพรวม", font_size=13)
    add_body(doc, "Accuracy และ Weighted F1 มีค่า 94.29% เท่ากัน เพราะแบบจำลองทำนายถูกในคลาสส่วนใหญ่และข้อผิดพลาดเกิดในคลาสที่มีจำนวนตัวอย่างไม่มาก ค่า Macro F1 ต่ำกว่าเล็กน้อยที่ 93.75% เนื่องจากให้น้ำหนักทุกคลาสเท่ากัน จึงสะท้อนผลของคลาสเข้าใจและไม่เข้าใจที่มี F1 เพียง 0.500 ชัดกว่าค่าที่ถ่วงตามจำนวนตัวอย่าง")
    add_table(doc, ["กลุ่มผลลัพธ์", "Support", "Precision", "Recall", "F1-score"], [
        ["14 คลาสที่ทำนายถูกทั้งหมด", "2–6 ต่อคลาส", "1.000", "1.000", "1.000"],
        ["เข้าใจ", "4", "0.500", "0.500", "0.500"],
        ["ไม่เข้าใจ", "4", "0.500", "0.500", "0.500"],
        ["Macro average", "70", "0.9375", "0.9375", "0.9375"],
        ["Weighted average", "70", "0.9429", "0.9429", "0.9429"],
    ], [5.8, 2.4, 2.2, 2.0, 2.25], caption="ตารางที่ 4.5 ผลการจำแนกตามกลุ่มคลาส", font_size=12)
    add_body(doc, "ความผิดพลาดทั้ง 4 คลิปเกิดจากคู่ท่าเข้าใจและไม่เข้าใจ โดยตัวอย่างจริงของแต่ละคลาส 2 จาก 4 คลิปถูกทำนายสลับกัน รูปแบบนี้แสดงว่าคุณลักษณะหรือข้อมูลฝึกยังไม่แยกจุดต่างของสองท่าได้ชัดเจน ควรตรวจลำดับการเคลื่อนไหวของมือ ช่วงเริ่ม–จบ และคำอธิบายป้ายกำกับ พร้อมเก็บตัวอย่างจากหลายคนเพิ่มเติม")
    add_figure(doc, CONFUSION_FIGURE, "ภาพที่ 4.1 Confusion Matrix ของการทดลอง HandVox 16 ท่า")
    add_body(doc, "Confusion Matrix แสดงแนวทแยงเข้มสำหรับ 14 คลาส แปลว่าตัวอย่างในชุดทดสอบรอบนี้ถูกจัดเข้าคลาสจริงทั้งหมด ส่วนตำแหน่งนอกแนวทแยงระหว่างเข้าใจกับไม่เข้าใจแสดงการสับสนแบบสองทิศทาง การวิเคราะห์ตำแหน่งเหล่านี้มีประโยชน์กว่าการดูคะแนนรวมเพียงค่าเดียว เพราะระบุได้ว่าควรปรับข้อมูลของคู่ท่าใด")

    add_heading(doc, "การประเมินผล")
    add_body(doc, "ผลการตรวจสอบการทำงานของโปรแกรมพบว่ากระบวนการเก็บข้อมูลและการใช้งานจริงใช้ฟังก์ชันสกัดคุณลักษณะรูปแบบเดียวกัน ระบบตรวจจำนวนคุณลักษณะและรายชื่อคลาสก่อนเริ่มทำนาย สะสมข้อมูลล่าสุด 30 เฟรม รับผลที่ผ่านเกณฑ์ความเชื่อมั่น และแสดงผลต่อผู้ใช้แบบเวลาจริง")
    add_subtopic(doc, "ความครบถ้วนของฟังก์ชัน", "ระบบสามารถเปิดกล้อง ตรวจจุดสำคัญ สะสมลำดับ เรียกแบบจำลอง แสดงชื่อท่าและค่าความเชื่อมั่น รวมผลย้อนหลัง และรีเซ็ตเมื่อไม่พบมือ นอกจากนี้ยังรองรับการสร้างประโยค อ่านเสียง เพิ่มหรือลบท่า เก็บคลิป สำรองข้อมูล และฝึกแบบจำลองใหม่")
    add_subtopic(doc, "ความสอดคล้องของข้อมูลกับโมเดล", "ก่อนเริ่มทำนาย โปรแกรมตรวจว่าจำนวนคุณลักษณะของโมเดลเท่ากับ 5,130 ค่าและรายชื่อคลาสตรงกับไฟล์กำหนดค่า หากไม่ตรงจะหยุดและแจ้งให้ฝึกใหม่ การตรวจนี้ช่วยป้องกันการนำโมเดลเก่าไปใช้กับรายการท่าที่เปลี่ยนแล้ว")
    add_table(doc, ["ความสามารถ", "ผลที่ตรวจสอบได้", "เงื่อนไข"], [
        ["ทำนายจากการเคลื่อนไหว", "สะสม 30 เฟรมแล้วใช้ predict_proba", "ต้องตรวจพบช่วงบนและมือ"],
        ["ยืนยันชื่อท่า", "รับผลเมื่อค่าความเชื่อมั่นไม่น้อยกว่า 0.40", "ยังต้องปรับจากข้อมูลภายนอก"],
        ["ลดการสั่นของผล", "ลงคะแนนจากผลล่าสุด 3 ครั้ง", "ช่วยให้ข้อความบนหน้าจอนิ่งขึ้น"],
        ["สร้างประโยค", "เพิ่ม ลบ ล้าง และอ่านคำที่สะสม", "ควบคุมผ่านแป้นพิมพ์"],
        ["อ่านเสียงภาษาไทย", "สร้างและเล่นเสียงด้วย gTTS", "ต้องเชื่อมต่ออินเทอร์เน็ต"],
        ["จัดการท่า", "เพิ่ม ลบ เก็บคลิป สำรอง และฝึกใหม่", "ทำงานผ่านเมนูของโครงการ"],
    ], [3.4, 6.5, 4.75], caption="ตารางที่ 4.6 ผลการประเมินการทำงานของระบบ", font_size=13)
    add_body(doc, "ในด้านการตอบสนอง ระบบต้องรอสะสมข้อมูลครบ 30 เฟรมก่อนทำนายและต้องผ่านการรวมผลย้อนหลัง 3 ครั้ง จึงมีความหน่วงโดยธรรมชาติ แม้กลไกนี้ช่วยให้ผลนิ่งขึ้น แต่โครงการยังไม่ได้บันทึก FPS และเวลาแฝงตั้งแต่รับภาพจนแสดงผล จึงยังไม่สามารถสรุปสมรรถนะเวลาจริงเป็นตัวเลขได้")
    add_body(doc, "ในด้านความทนทาน ระบบจัดการกรณีไม่พบมือด้วยการหยุดเพิ่มเฟรมและล้างสถานะเมื่อหายไปนานกว่า 0.4 วินาที แต่ยังไม่มีผลทดสอบเชิงระบบภายใต้แสงน้อย ฉากหลังซับซ้อน ระยะหลายระดับ มุมกล้องต่างกัน หรือการบังมือ การตรวจซอร์สยืนยันกลไกที่พัฒนาได้ แต่ไม่ทดแทนการทดลองภาคสนาม")
    add_figure(doc, ROOT / "qa" / "gui_dashboard_current.png", "ภาพที่ 4.2 หน้าจอการทำงานของ HandVox")
    add_body(doc, "หน้าจอภาพรวมแสดงจำนวนท่าที่โมเดลรู้จัก จำนวนคำที่วางแผน สถานะข้อมูล และความพร้อมของส่วนประกอบ ช่วยให้ผู้ใช้ตรวจสภาพระบบก่อนเริ่มงาน ส่วนหน้าจอตรวจจับแสดงภาพกล้อง จุดสำคัญ ชื่อท่า ค่าความเชื่อมั่น และข้อความสะสม การจัดข้อมูลเหล่านี้ไว้ในตำแหน่งมองเห็นง่ายช่วยลดความสับสนระหว่างการเก็บข้อมูลกับการใช้งานจริง")
    add_body(doc, "ผลการทดลองแสดงว่า HandVox สามารถเชื่อมขั้นตอนเก็บข้อมูล ฝึกแบบจำลอง และทำนายแบบเวลาจริงได้ตามวัตถุประสงค์ของต้นแบบ อย่างไรก็ตาม คะแนนที่รายงานมาจากการสุ่มแบ่งคลิปภายในชุดข้อมูลเดียวกัน ข้อมูลฐานเดิมบางส่วนไม่มีรหัสผู้ทำท่าและเซสชัน และยังไม่มีชุดทดสอบภายนอก จึงไม่ควรใช้คะแนนนี้ยืนยันความแม่นยำกับผู้ใช้ทั่วไป")
    add_body(doc, "การประเมินรุ่นถัดไปควรเก็บข้อมูลจากผู้ทำท่าหลายคนและหลายเซสชัน แยกชุดทดสอบตามบุคคล วัดเวลาแฝงและอัตราเฟรม ทดสอบแสง ฉากหลัง ระยะ และมุมกล้อง รวมทั้งประเมินความสะดวกในการใช้งานร่วมกับกลุ่มเป้าหมายจริง")
    add_table(doc, ["ด้านที่ต้องประเมินต่อ", "ข้อมูลที่ต้องเก็บ", "เกณฑ์หรือผลที่ต้องรายงาน"], [
        ["ความสามารถทั่วไป", "ผู้ทำท่าและเซสชันที่ไม่อยู่ในชุดฝึก", "Accuracy และ Macro F1 บนชุดภายนอก"],
        ["สมรรถนะเวลาจริง", "FPS และเวลาแฝงต่อการทำนาย", "ค่าเฉลี่ย ค่าต่ำสุด และช่วงการกระจาย"],
        ["ความทนทาน", "แสง ฉากหลัง ระยะ มุม และการบังมือ", "อัตราคำผิดและอัตราปฏิเสธในแต่ละสภาพ"],
        ["ระบบเสียง", "เวลาสร้างเสียงและอัตราความสำเร็จ", "ผลเมื่อเครือข่ายปกติและไม่เสถียร"],
        ["ประสบการณ์ผู้ใช้", "ภารกิจและแบบประเมินจากกลุ่มเป้าหมาย", "ความสำเร็จ เวลา และข้อเสนอแนะ"],
    ], [4.0, 6.2, 4.45], caption="ตารางที่ 4.7 แผนการประเมินสำหรับการใช้งานจริง", font_size=13)

    path = OUTPUT / "บทที่ 4_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def build_chapter_5_structured():
    """บทที่ 5 สรุปผล ปัญหา และข้อเสนอแนะตามแบบฟอร์ม."""
    doc = Document()
    configure_document(doc, page_start=CHAPTER_PAGE_STARTS[5])
    add_chapter_title(doc, 5, "สรุปผลและข้อเสนอแนะ")

    add_heading(doc, "สรุปผล")
    add_body(doc, "โครงงาน HandVox สามารถพัฒนาต้นแบบระบบรู้จำท่าทางภาษามือไทยแบบแยกคำจากลำดับภาพเว็บแคมได้ ระบบใช้ MediaPipe Holistic สกัด 171 คุณลักษณะต่อเฟรม เก็บ 30 เฟรมเป็นเวกเตอร์ 5,130 ค่า และใช้ SVM แบบ RBF จำแนกท่าจากชุดข้อมูล 16 ท่า รวม 350 คลิป")
    add_body(doc, "ระบบบรรลุวัตถุประสงค์ด้านการทำนายแบบเวลาจริง การเพิ่มหรือลบท่าและฝึกแบบจำลองใหม่ การแสดงชื่อท่าและค่าความเชื่อมั่น การสะสมคำเป็นประโยค และการอ่านเสียงภาษาไทย การทดลองภายในชุดข้อมูลทำนายถูก 66 จาก 70 คลิป ให้ Accuracy 94.29% และ Macro F1 93.75% แต่ยังต้องประเมินกับผู้ทำท่าและสภาพแวดล้อมใหม่ก่อนนำไปใช้งานจริง")
    add_subtopic(doc, "ผลด้านการจัดเตรียมข้อมูล", "โครงการกำหนดโครงสร้างข้อมูลให้แต่ละตัวอย่างมีความยาว 30 เฟรมเท่ากัน และใช้ชุดคุณลักษณะเดียวกันทั้งขณะเก็บข้อมูล ฝึกแบบจำลอง และทำนายจริง การจัดรูปแบบที่สอดคล้องกันช่วยลดข้อผิดพลาดจากมิติข้อมูลไม่ตรงกัน และทำให้สามารถตรวจสอบคลิปที่มีค่าผิดปกติหรือจำนวนเฟรมไม่ครบก่อนนำเข้าสู่กระบวนการฝึก")
    add_body(doc, "ชุดข้อมูลที่ใช้ประกอบด้วยข้อมูลฐานเดิม 120 คลิปและ Dataset V2 จำนวน 230 คลิป รวม 350 คลิป ครอบคลุม 16 ป้ายกำกับ แม้จำนวนดังกล่าวเพียงพอสำหรับพิสูจน์แนวคิดของระบบ แต่จำนวนต่อป้ายกำกับ 10–30 คลิปยังไม่สมดุล และข้อมูลฐานเดิมไม่มี metadata ระดับผู้ทำท่ากับเซสชัน จึงยังไม่ครอบคลุมความแตกต่างของบุคคลและสภาพแวดล้อม")
    add_subtopic(doc, "ผลด้านแบบจำลอง", "การใช้ SVM แบบ RBF เหมาะกับต้นแบบที่มีข้อมูลไม่มากและคุณลักษณะเป็นเวกเตอร์คงที่ ผลการทดลองแบบ stratified holdout แสดงว่าแบบจำลองสามารถแยกท่าส่วนใหญ่ได้ดี โดย 14 จาก 16 คลาสทำนายถูกทั้งหมดในชุดทดสอบรอบนี้ ส่วนข้อผิดพลาด 4 คลิปกระจุกอยู่ที่คู่ท่าเข้าใจและไม่เข้าใจ")
    add_body(doc, "คะแนน Accuracy 94.29% และ Macro F1 93.75% แสดงว่ากระบวนการสกัดคุณลักษณะและจำแนกท่ามีศักยภาพในขอบเขตข้อมูลปัจจุบัน อย่างไรก็ตาม คะแนนดังกล่าวเป็นผลจากการแบ่งคลิปภายในชุดข้อมูลเดียวกัน ไม่ใช่การทดสอบกับผู้ทำท่ารายใหม่ทั้งหมด จึงควรตีความเป็นผลของต้นแบบและใช้เป็นค่าฐานสำหรับการพัฒนา ไม่ใช่ข้อยืนยันความแม่นยำในการใช้งานทั่วไป")
    add_subtopic(doc, "ผลด้านการทำงานของระบบ", "HandVox เชื่อมการรับภาพ การตรวจจุดสำคัญ การสะสมลำดับ 30 เฟรม การทำนาย การรวมผลย้อนหลัง และการแสดงข้อความเข้าด้วยกัน ผู้ใช้สามารถเพิ่มคำลงในประโยค ลบคำ ล้างข้อความ และสั่งอ่านเสียงภาษาไทยได้ นอกจากนี้ยังมีเมนูเพิ่มหรือลบท่า เก็บคลิป สำรองข้อมูล และฝึกโมเดลใหม่ ช่วยให้โครงการนำไปสาธิตและปรับปรุงชุดคำได้โดยไม่ต้องแก้กระบวนการหลักทุกครั้ง")
    add_body(doc, "ระบบมีการตรวจจำนวนคุณลักษณะและรายชื่อคลาสของแบบจำลองก่อนเริ่มใช้งาน รวมทั้งล้างลำดับเมื่อไม่พบมือนานเกินค่าที่กำหนด กลไกเหล่านี้ช่วยลดข้อผิดพลาดจากโมเดลกับข้อมูลคนละรุ่นและลดการนำเฟรมจากคนละท่ามาปะปนกัน แต่ยังต้องทดสอบเวลาแฝง อัตราเฟรม และความทนทานในสภาพจริงเพิ่มเติม")
    add_subtopic(doc, "การบรรลุวัตถุประสงค์", "เมื่อเปรียบเทียบกับวัตถุประสงค์ในบทที่ 1 ระบบบรรลุการสร้างต้นแบบ การจัดการชุดท่า การแสดงผลและเสียง ตลอดจนการประเมินด้วยตัวชี้วัดมาตรฐาน ส่วนวัตถุประสงค์ด้านการรองรับผู้ใช้หลายบุคคลและสภาพแวดล้อมหลากหลายบรรลุเฉพาะระดับออกแบบแนวทาง เนื่องจากข้อมูลและผลทดสอบภายนอกยังไม่เพียงพอ")
    add_table(doc, ["วัตถุประสงค์", "ผลที่ได้", "สถานะ"], [
        ["รู้จำท่าจากลำดับภาพแบบเวลาจริง", "พัฒนากระบวนการ 30 เฟรมและ SVM", "บรรลุในระดับต้นแบบ"],
        ["เพิ่ม ลบท่า และฝึกใหม่", "มีเมนูจัดการรายการท่าและชุดข้อมูล", "บรรลุ"],
        ["แสดงข้อความ ประโยค และเสียงไทย", "แสดงชื่อท่า สะสมคำ และอ่านเสียง", "บรรลุ โดยเสียงต้องใช้อินเทอร์เน็ต"],
        ["ประเมินผลและระบุข้อจำกัด", "มีตัวชี้วัดรายคลาสและ Confusion Matrix", "บรรลุสำหรับการทดลองภายใน"],
        ["รองรับการพัฒนาชุดคำในอนาคต", "เพิ่ม ลบ เก็บข้อมูล และฝึกใหม่ได้", "บรรลุในโครงสร้างต้นแบบ"],
        ["ทดสอบกับผู้ใช้และสภาพแวดล้อมใหม่", "มีแผนการประเมินแต่ยังไม่มีผลภาคสนาม", "ต้องดำเนินการต่อ"],
    ], [5.4, 5.45, 3.8], caption="ตารางที่ 5.1 ผลสำเร็จเทียบกับวัตถุประสงค์", font_size=12)
    add_body(doc, "โดยสรุป HandVox แสดงให้เห็นว่าข้อมูลจุดสำคัญของร่างกายและมือสามารถใช้สร้างระบบรู้จำท่าทางแบบแยกคำบนคอมพิวเตอร์ทั่วไปได้ กระบวนการปัจจุบันเหมาะสำหรับการทดลองและการสาธิตในสภาพควบคุม ขณะที่การนำไปใช้สื่อสารจริงจำเป็นต้องขยายข้อมูล ปรับวิธีประเมิน และออกแบบความปลอดภัยของผลทำนายให้รัดกุมขึ้น")

    add_heading(doc, "ปัญหาและอุปสรรค")
    add_numbered_list(doc, [
        "ชุดข้อมูลมีเพียง 350 คลิปจาก 16 ท่า และจำนวนคลิปต่อคลาสไม่เท่ากันตั้งแต่ 10–30 คลิป ทำให้ยังไม่ครอบคลุมความหลากหลายของการใช้งานจริง",
        "ข้อมูลฐานเดิม 120 คลิปไม่มีรหัสผู้ทำท่าและเซสชัน จึงไม่สามารถตรวจสอบการรั่วไหลของข้อมูลหรือประเมินแบบแยกบุคคลได้ครบทุกคลาส",
        "ผลการทดลองมาจากการสุ่มแบ่งคลิปในชุดเดียวกันและยังไม่มีชุดทดสอบภายนอก คะแนนจึงอาจสูงกว่าผลเมื่อใช้กับบุคคลหรือสภาพแวดล้อมใหม่",
        "ท่า “เข้าใจ” และ “ไม่เข้าใจ” มีลักษณะที่ระบบสับสนกัน โดยทั้งสองคลาสมี F1 เท่ากับ 0.500 ในรอบทดลอง",
        "การตรวจจับจุดสำคัญได้รับผลกระทบจากแสง การบังมือ ระยะ มุมกล้อง และความเร็วในการทำท่า ขณะที่ระบบยังกำหนดให้ทุกคลิปมี 30 เฟรมเท่ากัน",
        "การกำหนดลำดับคงที่ 30 เฟรมทำให้ผู้ใช้ต้องทำท่าในช่วงเวลาที่ระบบคาดไว้ หากช้าหรือเร็วเกินไป ส่วนสำคัญของการเคลื่อนไหวอาจอยู่ไม่ครบในหน้าต่างข้อมูล",
        "ค่าเกณฑ์ความเชื่อมั่น 0.40 และการลงคะแนนจากผลล่าสุด 3 ครั้งยังเป็นค่าที่กำหนดเชิงวิศวกรรม ไม่ได้ปรับจากชุดตรวจสอบเฉพาะ จึงอาจรับผลที่ไม่แน่นอนหรือทำให้เกิดความหน่วงมากเกินไปในบางกรณี",
        "ระบบเสียงภาษาไทยใช้ gTTS ซึ่งต้องพึ่งพาอินเทอร์เน็ต เมื่อเครือข่ายไม่พร้อมระบบอาจไม่สามารถสร้างเสียงได้ แม้ส่วนการรู้จำท่ายังทำงานอยู่",
        "ยังไม่มีการวัด FPS เวลาแฝง อัตราการปฏิเสธคำ หรือการทดสอบความพึงพอใจกับกลุ่มเป้าหมายจริง จึงประเมินความเร็ว ความสะดวก และความเหมาะสมในชีวิตประจำวันไม่ได้ครบถ้วน",
        "รายการคำและรูปแบบท่ายังไม่ได้ผ่านการตรวจทานอย่างเป็นทางการจากผู้ใช้ภาษามือไทยหรือผู้เชี่ยวชาญทุกคำ จึงอาจมีความแตกต่างด้านรูปแบบการทำท่าและความหมายตามบริบท",
    ])
    add_body(doc, "ปัญหาข้างต้นแบ่งได้เป็นสามกลุ่ม ได้แก่ ข้อจำกัดด้านข้อมูล ข้อจำกัดด้านแบบจำลองและการประมวลผล และข้อจำกัดด้านการใช้งานจริง กลุ่มข้อมูลมีผลโดยตรงต่อความสามารถทั่วไปของระบบ ส่วนกลุ่มแบบจำลองมีผลต่อความถูกต้องและความหน่วง ขณะที่กลุ่มการใช้งานเกี่ยวข้องกับความเข้าใจของผู้ใช้ ความพร้อมของเครือข่าย และความเหมาะสมของคำศัพท์")
    add_body(doc, "อุปสรรคสำคัญที่สุดในระยะปัจจุบันคือการมีข้อมูลจากบุคคลและเซสชันจำกัด เพราะไม่สามารถแก้ได้ด้วยการปรับพารามิเตอร์เพียงอย่างเดียว การเพิ่มข้อมูลที่มีคุณภาพและ metadata ครบถ้วนจะช่วยทั้งการฝึกแบบจำลอง การแบ่งชุดทดสอบ และการวิเคราะห์สาเหตุของข้อผิดพลาดในระยะยาว")

    add_heading(doc, "ข้อเสนอแนะ")
    add_numbered_list(doc, [
        "เพิ่มจำนวนคำ ผู้ทำท่า และรอบการเก็บข้อมูลให้สมดุล พร้อมตรวจรูปแบบและความหมายของท่าร่วมกับผู้ใช้ภาษามือหรือผู้เชี่ยวชาญ",
        "บันทึกรหัสผู้ให้ข้อมูล รหัสเซสชัน แสง ฉากหลัง ระยะ มุมกล้อง และความเร็วของการทำท่า เพื่อรองรับการตรวจสอบย้อนหลัง",
        "แบ่งชุดฝึก ชุดตรวจสอบ และชุดทดสอบตามผู้ให้ข้อมูลหรือเซสชัน และจัดทำชุดทดสอบภายนอกที่ไม่ผ่านกระบวนการปรับโมเดล",
        "เก็บตัวอย่างของท่า “เข้าใจ” และ “ไม่เข้าใจ” เพิ่มขึ้น พร้อมทบทวนจุดต่างของการเคลื่อนไหวที่ทำให้ระบบจำแนกได้ชัดเจน",
        "วัด FPS เวลาแฝง อัตราการปฏิเสธคำ และความสำเร็จของระบบเสียงในสภาพแวดล้อมหลายแบบ รวมทั้งทดสอบกับผู้ใช้เป้าหมายจริง",
        "เพิ่มระบบเสียงภาษาไทยแบบออฟไลน์และสถานะไม่ทราบเมื่อไม่มีคลาสที่เหมาะสม เพื่อลดการทำนายที่ไม่มั่นใจ",
        "เมื่อมีข้อมูลมากเพียงพอ ควรเปรียบเทียบ SVM กับแบบจำลองลำดับ เช่น LSTM หรือ Transformer และศึกษาการรู้จำหลายคำต่อเนื่องในอนาคต",
        "ปรับความยาวลำดับหรือใช้วิธีจัดแนวเวลาที่รองรับความเร็วในการทำท่าต่างกัน พร้อมทดลองช่วงหน้าต่างและการรวมผลหลายค่าอย่างเป็นระบบ",
        "กำหนดกระบวนการขอความยินยอม การไม่เก็บภาพดิบโดยไม่จำเป็น การกำหนดสิทธิ์เข้าถึง และการสำรองชุดข้อมูล เพื่อคุ้มครองข้อมูลของผู้เข้าร่วม",
        "จัดทำคู่มือการเก็บข้อมูล คู่มือผู้ใช้ และบันทึกเวอร์ชันของรายการท่า ชุดข้อมูล แบบจำลอง และค่าตั้ง เพื่อให้ผู้อื่นทำซ้ำและตรวจสอบผลได้",
    ])
    add_subtopic(doc, "แนวทางระยะเร่งด่วน", "ควรเพิ่มข้อมูลให้คลาสที่มีตัวอย่างน้อย โดยเริ่มจากท่าไม่ใช่ เข้าใจ และไม่เข้าใจ ตรวจชื่อป้ายกำกับและรูปแบบการทำท่ากับผู้เชี่ยวชาญ บันทึก metadata ทุกคลิป และสร้างชุดทดสอบที่แยกผู้ทำท่าจากชุดฝึกอย่างชัดเจน")
    add_subtopic(doc, "แนวทางระยะกลาง", "เมื่อมีข้อมูลสมดุลมากขึ้น ควรปรับ C, gamma, เกณฑ์ความเชื่อมั่น และจำนวนผลย้อนหลังจากชุดตรวจสอบ เปรียบเทียบตัวเลือกตาม Macro F1 เวลาแฝง และอัตราการปฏิเสธ พร้อมเพิ่มเสียงแบบออฟไลน์และหน้าจอแจ้งสถานะเมื่อระบบไม่มั่นใจ")
    add_subtopic(doc, "แนวทางระยะยาว", "ควรขยายไปสู่การรู้จำท่าต่อเนื่อง การแบ่งช่วงคำอัตโนมัติ และแบบจำลองที่เรียนรู้ลำดับเวลาได้โดยตรง เช่น LSTM หรือ Transformer รวมทั้งทดสอบกับผู้ใช้หลากหลายกลุ่มในสถานการณ์จริง โดยให้ผู้ใช้ภาษามือมีส่วนร่วมตั้งแต่การกำหนดคำศัพท์จนถึงการประเมินผล")
    add_table(doc, ["ช่วงดำเนินการ", "งานสำคัญ", "ผลที่คาดหวัง"], [
        ["ระยะเร่งด่วน", "เพิ่มข้อมูลแบบสมดุล แก้คู่ท่าสับสน และบันทึก metadata", "ชุดข้อมูลพร้อมแบ่งทดสอบตามบุคคลและวิเคราะห์ข้อผิดพลาด"],
        ["ระยะสั้น", "สร้างชุดทดสอบภายนอกและปรับพารามิเตอร์จากชุดตรวจสอบ", "คะแนนที่สะท้อนข้อมูลใหม่และค่าตั้งที่มีหลักฐานรองรับ"],
        ["ระยะกลาง", "วัด FPS เวลาแฝง ความทนทาน และทดสอบผู้ใช้", "ทราบสมรรถนะและปัญหาการใช้งานจริง"],
        ["ระยะกลาง", "เพิ่มเสียงออฟไลน์และสถานะไม่ทราบ", "ลดการพึ่งพาอินเทอร์เน็ตและลดคำทำนายผิดที่ไม่มั่นใจ"],
        ["ระยะยาว", "เปรียบเทียบแบบจำลองลำดับและพัฒนาการรู้จำต่อเนื่อง", "รองรับประโยคที่เป็นธรรมชาติมากขึ้น"],
    ], [3.2, 7.2, 5.1], caption="ตารางที่ 5.2 แผนพัฒนา HandVox ในระยะต่อไป", font_size=13)
    add_body(doc, "การพัฒนาในระยะต่อไปควรกำหนดเกณฑ์ผ่านล่วงหน้า เช่น Macro F1 บนผู้ทำท่าที่ไม่อยู่ในชุดฝึก เวลาแฝงเฉลี่ย อัตราการปฏิเสธ และอัตราความสำเร็จของภารกิจผู้ใช้ การมีเกณฑ์ที่วัดได้จะช่วยให้ตัดสินใจได้ว่าการเพิ่มข้อมูลหรือเปลี่ยนแบบจำลองให้ประโยชน์จริงเพียงใด")
    add_body(doc, "หากดำเนินการตามลำดับดังกล่าว HandVox จะพัฒนาจากต้นแบบในสภาพควบคุมไปสู่ระบบที่มีหลักฐานรองรับทั้งด้านความถูกต้อง ความเร็ว ความทนทาน และประสบการณ์ผู้ใช้ได้มากขึ้น โดยยังคงเป้าหมายสำคัญคือช่วยให้การสื่อสารด้วยท่าทางเข้าถึงได้ง่ายและเหมาะสมกับบริบทภาษาไทย")

    path = OUTPUT / "บทที่ 5_ฉบับปรับปรุง_HandVox_THSarabun.docx"
    doc.save(path)
    return path


def main():
    make_collection_figure(COLLECTION_FIGURE)
    make_confusion_figure(CONFUSION_FIGURE)
    paths = [
        build_chapter_1_structured(),
        build_chapter_2_structured(),
        build_chapter_3_structured(),
        build_chapter_4_structured(),
        build_chapter_5_structured(),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
