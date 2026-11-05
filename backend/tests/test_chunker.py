from app.ingest.chunker import Chunk, chunk_blocks, estimate_tokens
from app.ingest.parsers.base import Block


def test_estimate_tokens_is_chars_over_four():
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_empty_blocks_yield_no_chunks():
    assert chunk_blocks([]) == []


def test_small_document_is_a_single_chunk():
    blocks = [Block(text="Title", level=1), Block(text="A short paragraph.", level=0)]
    chunks = chunk_blocks(blocks, chunk_size_tokens=600, overlap_pct=0.12)
    assert len(chunks) == 1
    assert "Title" in chunks[0].text
    assert "A short paragraph." in chunks[0].text


def test_heading_always_starts_a_new_chunk():
    # Each paragraph (250 chars) fits comfortably within a 280-char budget on
    # its own, so the only thing that can force a second chunk is the rule
    # that a heading always flushes a non-empty current chunk.
    paragraph = "word " * 50
    blocks = [
        Block(text="Heading One", level=1),
        Block(text=paragraph, level=0),
        Block(text="Heading Two", level=1),
        Block(text=paragraph, level=0),
    ]
    chunks = chunk_blocks(blocks, chunk_size_tokens=70, overlap_pct=0.0)
    assert len(chunks) == 2
    assert chunks[0].heading == "Heading One"
    assert chunks[1].heading == "Heading Two"
    assert "Heading Two" in chunks[1].text


def test_overlap_carries_tail_of_previous_chunk():
    # Each paragraph (120 chars) fits alone under a 200-char budget, but not
    # combined, so they land in separate chunks and overlap kicks in.
    paragraph_a = "alpha " * 20
    paragraph_b = "bravo " * 20
    blocks = [Block(text=paragraph_a, level=0), Block(text=paragraph_b, level=0)]
    chunks = chunk_blocks(blocks, chunk_size_tokens=50, overlap_pct=0.12)
    assert len(chunks) == 2
    assert "alpha" in chunks[1].text
    assert "bravo" in chunks[1].text
    assert len(chunks[1].text) > len(paragraph_b)


def test_oversized_single_paragraph_is_split_on_sentence_boundaries():
    sentence = "This is one sentence. "
    huge_paragraph = sentence * 100  # way over any reasonable chunk size
    blocks = [Block(text=huge_paragraph.strip(), level=0)]
    chunks = chunk_blocks(blocks, chunk_size_tokens=60, overlap_pct=0.0)
    assert len(chunks) > 1
    for chunk in chunks:
        assert isinstance(chunk, Chunk)
        assert chunk.token_estimate <= 70  # some slack for overlap-free sizing


def test_page_number_is_preserved_per_chunk():
    blocks = [
        Block(text="Page one text.", level=0, page=1),
        Block(text="Page two text.", level=0, page=2),
    ]
    chunks = chunk_blocks(blocks, chunk_size_tokens=5, overlap_pct=0.0)
    pages = {c.page for c in chunks}
    assert pages == {1, 2}
