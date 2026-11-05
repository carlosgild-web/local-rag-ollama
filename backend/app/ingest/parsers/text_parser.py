"""Parsers for plain text and Markdown files."""

import re

from app.ingest.parsers.base import Block, ParsedDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


def parse_txt(text: str) -> ParsedDocument:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return ParsedDocument(blocks=[Block(text=p, level=0) for p in paragraphs])


def parse_markdown(text: str) -> ParsedDocument:
    blocks: list[Block] = []
    paragraph_lines: list[str] = []

    def flush_paragraph():
        if paragraph_lines:
            blocks.append(Block(text=" ".join(paragraph_lines).strip(), level=0))
            paragraph_lines.clear()

    for line in text.splitlines():
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            blocks.append(Block(text=heading_match.group(2).strip(), level=level))
        elif line.strip() == "":
            flush_paragraph()
        else:
            paragraph_lines.append(line.strip())
    flush_paragraph()

    return ParsedDocument(blocks=blocks)
