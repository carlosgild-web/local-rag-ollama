"""Parser for Word (.docx) files.

Reads paragraphs and tables in document order. Each table row becomes one
block with its cells joined by " | ", so a key/value row such as
"Agreement number | XA-2026-014" stays together in one chunk.
"""

from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingest.parsers.base import Block, ParsedDocument


def _heading_level(style_name: str | None) -> int:
    if not style_name:
        return 0
    if style_name == "Title":
        return 1
    if style_name.startswith("Heading "):
        suffix = style_name.removeprefix("Heading ").strip()
        if suffix.isdigit():
            return int(suffix)
    return 0


def _paragraph_block(paragraph: Paragraph) -> Block | None:
    text = paragraph.text.strip()
    if not text:
        return None
    # Files without a default paragraph style give style None: plain text.
    style = paragraph.style
    return Block(text=text, level=_heading_level(style.name if style else None))


def _table_blocks(table: Table) -> list[Block]:
    blocks = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            text = " ".join(cell.text.split())
            # Merged cells repeat the same cell object; keep the text once.
            if text and (not cells or cells[-1] != text):
                cells.append(text)
        if cells:
            blocks.append(Block(text=" | ".join(cells)))
    return blocks


def _iter_body(document: DocxDocument):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def parse_docx(path: Path) -> ParsedDocument:
    document = docx.Document(str(path))
    blocks: list[Block] = []
    for item in _iter_body(document):
        if isinstance(item, Table):
            blocks.extend(_table_blocks(item))
        elif (block := _paragraph_block(item)) is not None:
            blocks.append(block)
    return ParsedDocument(blocks=blocks)
