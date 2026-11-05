"""Structure-aware chunker.

Packs parsed blocks into chunks of approximately `chunk_size_tokens`,
splitting on headings and paragraphs first, with trailing overlap carried
into the next chunk. Token counts are a cheap chars/4 approximation (see
docs/decisions/0001-token-estimate-heuristic.md) -- good enough for sizing
chunks, not meant to match any specific model's tokenizer.
"""

import re
from dataclasses import dataclass

from app.ingest.parsers.base import Block

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


@dataclass
class Chunk:
    text: str
    token_estimate: int
    page: int | None
    heading: str | None


def chunk_blocks(
    blocks: list[Block],
    *,
    chunk_size_tokens: int = 600,
    overlap_pct: float = 0.12,
) -> list[Chunk]:
    if not blocks:
        return []

    max_chars = chunk_size_tokens * CHARS_PER_TOKEN
    overlap_chars = round(max_chars * overlap_pct)

    raw_chunks = _pack_blocks(blocks, max_chars)
    return _apply_overlap(raw_chunks, overlap_chars)


@dataclass
class _RawChunk:
    text: str
    page: int | None
    heading: str | None


def _pack_blocks(blocks: list[Block], max_chars: int) -> list[_RawChunk]:
    raw_chunks: list[_RawChunk] = []
    current_parts: list[str] = []
    current_len = 0
    current_page: int | None = None
    current_heading: str | None = None

    def flush():
        nonlocal current_parts, current_len, current_page, current_heading
        if current_parts:
            raw_chunks.append(
                _RawChunk(
                    text="\n\n".join(current_parts), page=current_page, heading=current_heading
                )
            )
        current_parts = []
        current_len = 0
        current_page = None
        current_heading = None

    last_heading: str | None = None

    for block in blocks:
        if block.level > 0:
            last_heading = block.text

        for piece in _split_oversized(block.text, max_chars):
            piece_len = len(piece)
            is_heading = block.level > 0

            # Headings start a fresh chunk unless the current one is still empty.
            if is_heading and current_parts:
                flush()

            if current_parts and current_len + piece_len > max_chars:
                flush()

            if not current_parts:
                current_page = block.page
                current_heading = last_heading

            current_parts.append(piece)
            current_len += piece_len

    flush()
    return raw_chunks


def _split_oversized(text: str, max_chars: int) -> list[str]:
    """Split a single block into pieces no larger than max_chars, on sentence
    boundaries where possible."""
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)

    # A single sentence longer than max_chars: hard-split as a last resort.
    final_pieces = []
    for piece in pieces:
        if len(piece) <= max_chars:
            final_pieces.append(piece)
        else:
            final_pieces.extend(piece[i : i + max_chars] for i in range(0, len(piece), max_chars))
    return final_pieces


def _apply_overlap(raw_chunks: list[_RawChunk], overlap_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    previous_text = ""
    for raw in raw_chunks:
        if previous_text and overlap_chars > 0:
            tail = previous_text[-overlap_chars:]
            cut = tail.find(" ")
            if cut != -1:
                tail = tail[cut + 1 :]
            text = f"{tail} {raw.text}".strip()
        else:
            text = raw.text
        chunks.append(
            Chunk(
                text=text,
                token_estimate=estimate_tokens(text),
                page=raw.page,
                heading=raw.heading,
            )
        )
        previous_text = raw.text
    return chunks
