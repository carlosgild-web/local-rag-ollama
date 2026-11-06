"""Citation checks (CLAUDE.md invariant 6). Cases are taken from answers in
the 2026-11-06 end-to-end test (docs/test-reports/2026-11-06-e2e.md)."""

import pytest

from app.retrieval.citations import (
    INVALID,
    MISSING,
    NOT_APPLICABLE,
    OK,
    citation_status,
    cited_numbers,
)
from app.retrieval.prompt import NOT_FOUND_PHRASE, build_prompt, citation_reminder
from app.retrieval.retrieve import RetrievedChunk


@pytest.mark.parametrize(
    ("answer", "sources", "expected"),
    [
        ("The RSVP deadline is December 8, 2026. [1]", 5, OK),
        ("Safety glasses are required [1][3].", 5, OK),
        ("Both apply [1, 2].", 2, OK),
        # e2e hr-01: right answer, no citation
        ("The company closes from December 22, 2026 through January 2, 2027.", 5, MISSING),
        # e2e sc-10: only 5 sources were given
        ("The payment terms for the Strategic Partner tier are Net 45. [6]", 5, INVALID),
        ("Use [0] for nothing.", 3, INVALID),
        (NOT_FOUND_PHRASE, 5, NOT_APPLICABLE),
        ("Not found in the documents.", 0, NOT_APPLICABLE),
        ("", 5, NOT_APPLICABLE),
    ],
)
def test_citation_status(answer, sources, expected):
    assert citation_status(answer, sources) == expected


def test_cited_numbers_reads_single_grouped_and_repeated_markers():
    assert cited_numbers("a [2] b [1][3] c [4, 5]") == [2, 1, 3, 4, 5]
    assert cited_numbers("a markdown [link](http://x) and no citation") == []


def _chunk(i: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=i, text=f"fact {i}", page=None, heading=None, filename=f"f{i}.txt", document_id=i
    )


def test_prompt_ends_with_a_numbered_citation_reminder_before_answer():
    chunks = [_chunk(1), _chunk(2), _chunk(3)]
    prompt = build_prompt("Which fact?", chunks)
    assert prompt.endswith(f"{citation_reminder(3)}\n\nAnswer:")
    assert "Only use the source numbers shown in the context ([1] to [3])" in prompt
    assert NOT_FOUND_PHRASE in citation_reminder(3)
    assert "([1])" in citation_reminder(1)
