"""Shared parser output types.

A parsed document is a flat, ordered list of blocks. `level` 0 means a plain
paragraph; 1+ means a heading of that depth. The chunker uses `level` to
avoid splitting across heading boundaries.
"""

from dataclasses import dataclass


@dataclass
class Block:
    text: str
    level: int = 0
    page: int | None = None
    needs_ocr: bool = False


@dataclass
class ParsedDocument:
    blocks: list[Block]

    @property
    def full_text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)
