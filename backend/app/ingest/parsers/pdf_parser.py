"""Parser for PDF files, with an OCR fallback for low-text-yield pages."""

import re
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

from app.ingest.parsers.base import Block, ParsedDocument

OCR_RENDER_DPI = 300


def parse_pdf(
    path: Path,
    *,
    min_text_chars: int = 20,
    ocr_lang: str = "eng+spa",
    tesseract_cmd: str | None = None,
    tessdata_prefix: str | None = None,
) -> ParsedDocument:
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    blocks: list[Block] = []
    with pymupdf.open(str(path)) as document:
        for page_index, page in enumerate(document, start=1):
            text = page.get_text("text")
            needs_ocr = len(text.strip()) < min_text_chars
            if needs_ocr:
                text = _ocr_page(page, lang=ocr_lang, tessdata_prefix=tessdata_prefix)

            for paragraph in re.split(r"\n\s*\n", text):
                paragraph = paragraph.strip()
                if paragraph:
                    blocks.append(
                        Block(text=paragraph, level=0, page=page_index, needs_ocr=needs_ocr)
                    )

    return ParsedDocument(blocks=blocks)


def _ocr_page(page, *, lang: str, tessdata_prefix: str | None) -> str:
    pixmap = page.get_pixmap(dpi=OCR_RENDER_DPI)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    config = f"--tessdata-dir {tessdata_prefix}" if tessdata_prefix else ""
    return pytesseract.image_to_string(image, lang=lang, config=config)
