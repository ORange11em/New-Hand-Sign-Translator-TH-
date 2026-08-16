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
CHAPTER_PAGE_STARTS = {1: 1, 2: 7, 3: 16, 4: 24, 5: 30}


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


def main():
    make_collection_figure(COLLECTION_FIGURE)
    make_confusion_figure(CONFUSION_FIGURE)
    paths = [
        build_chapter_1(),
        build_chapter_2(),
        build_chapter_3(),
        build_chapter_4(),
        build_chapter_5(),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
