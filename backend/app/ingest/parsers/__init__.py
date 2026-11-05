"""Dispatches a file to the right parser by extension."""

from pathlib import Path

from app.ingest.parsers.base import Block, ParsedDocument
from app.ingest.parsers.docx_parser import parse_docx
from app.ingest.parsers.pdf_parser import parse_pdf
from app.ingest.parsers.text_parser import parse_markdown, parse_txt

SUPPORTED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf"}


class UnsupportedFileTypeError(Exception):
    pass


def parse_file(
    path: Path,
    *,
    ocr_lang: str = "eng+spa",
    ocr_min_text_chars: int = 20,
    tesseract_cmd: str | None = None,
    tessdata_prefix: str | None = None,
) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return parse_txt(path.read_text(encoding="utf-8"))
    if suffix == ".md":
        return parse_markdown(path.read_text(encoding="utf-8"))
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".pdf":
        return parse_pdf(
            path,
            min_text_chars=ocr_min_text_chars,
            ocr_lang=ocr_lang,
            tesseract_cmd=tesseract_cmd,
            tessdata_prefix=tessdata_prefix,
        )
    raise UnsupportedFileTypeError(f"No parser registered for extension '{suffix}'")


__all__ = [
    "Block",
    "ParsedDocument",
    "SUPPORTED_EXTENSIONS",
    "UnsupportedFileTypeError",
    "parse_file",
]
