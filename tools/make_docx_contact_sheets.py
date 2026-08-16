"""รวมภาพหน้ารายงานเป็น contact sheet สำหรับตรวจรูปแบบทุกหน้า."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--per-sheet", type=int, default=4)
    args = parser.parse_args()

    pages = sorted(
        args.input_dir.glob("page-*.png"),
        key=lambda path: int(path.stem.split("-")[-1]),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
    thumb_w, thumb_h = 470, 665
    cell_w, cell_h = 500, 710

    for sheet_no, start in enumerate(range(0, len(pages), args.per_sheet), start=1):
        sheet = Image.new("RGB", (cell_w * 2, cell_h * 2), "#d9d9d9")
        draw = ImageDraw.Draw(sheet)
        for offset, page_path in enumerate(pages[start : start + args.per_sheet]):
            with Image.open(page_path) as page:
                page = page.convert("RGB")
                page.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                col, row = offset % 2, offset // 2
                x = col * cell_w + (cell_w - page.width) // 2
                y = row * cell_h + 32
                sheet.paste(page, (x, y))
                page_number = int(page_path.stem.split("-")[-1])
                draw.text((col * cell_w + 12, row * cell_h + 5), f"Page {page_number}", fill="black", font=font)
        output = args.output_dir / f"sheet-{sheet_no:02d}.png"
        sheet.save(output, optimize=True)
        print(output)


if __name__ == "__main__":
    main()
