"""Parser for Word (.docx) files."""

from pathlib import Path

import docx

from app.ingest.parsers.base import Block, ParsedDocument


def _heading_level(style_name: str) -> int:
    if style_name == "Title":
        return 1
    if style_name.startswith("Heading "):
        suffix = style_name.removeprefix("Heading ").strip()
        if suffix.isdigit():
            return int(suffix)
    return 0


def parse_docx(path: Path) -> ParsedDocument:
    document = docx.Document(str(path))
    blocks = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        blocks.append(Block(text=text, level=_heading_level(paragraph.style.name)))
    return ParsedDocument(blocks=blocks)
