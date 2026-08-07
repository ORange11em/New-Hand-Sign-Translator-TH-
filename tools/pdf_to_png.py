"""Render every PDF page to a numbered PNG using PyMuPDF."""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(args.pdf)
    for page_number, page in enumerate(document, start=1):
        pixmap = page.get_pixmap(dpi=args.dpi, alpha=False)
        output = args.output_dir / f"page-{page_number}.png"
        pixmap.save(output)
        print(output)


if __name__ == "__main__":
    main()
