from app.retrieval.prompt import NOT_FOUND_PHRASE, build_prompt, format_context, format_sources
from app.retrieval.retrieve import RetrievedChunk

CHUNKS = [
    RetrievedChunk(
        chunk_id=1,
        text="Espresso forces hot water through finely ground coffee.",
        page=None,
        heading=None,
        filename="coffee-brewing-methods.txt",
        document_id=1,
    ),
    RetrievedChunk(
        chunk_id=2,
        text="Aperture determines how much light a telescope gathers.",
        page=3,
        heading="Choosing a Telescope",
        filename="intro-to-astronomy-telescopes.txt",
        document_id=2,
    ),
]


def test_format_context_numbers_and_labels_sources():
    context = format_context(CHUNKS)
    assert "[1] coffee-brewing-methods.txt" in context
    assert "[2] intro-to-astronomy-telescopes.txt (page 3)" in context
    assert "Espresso forces hot water" in context


def test_format_sources_prefers_page_then_heading():
    sources = format_sources(CHUNKS)
    lines = sources.splitlines()
    assert lines[0] == "[1] coffee-brewing-methods.txt"
    assert lines[1] == "[2] intro-to-astronomy-telescopes.txt (page 3)"


def test_build_prompt_includes_not_found_rule_and_question():
    prompt = build_prompt("How does espresso work?", CHUNKS)
    assert NOT_FOUND_PHRASE in prompt
    assert "How does espresso work?" in prompt
    assert "[1] coffee-brewing-methods.txt" in prompt


def test_heading_only_chunk_uses_heading_not_page():
    heading_only = RetrievedChunk(
        chunk_id=3,
        text="Some text.",
        page=None,
        heading="Intro",
        filename="doc.md",
        document_id=3,
    )
    sources = format_sources([heading_only])
    assert sources == "[1] doc.md (Intro)"
