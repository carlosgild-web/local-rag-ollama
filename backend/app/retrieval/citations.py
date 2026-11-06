"""Checks the [n] citation markers of an answer (CLAUDE.md invariant 6).

The model is told to cite every sentence, but a small model sometimes
leaves citations out or cites a number that has no source. The app keeps
the answer and reports its citation status, so the UI can say when the
citations could not be verified.
"""

import re

from app.retrieval.prompt import NOT_FOUND_PHRASE

_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

OK = "ok"  # at least one citation, and every number points at a source
MISSING = "missing"  # no citation at all
INVALID = "invalid"  # some number has no source
NOT_APPLICABLE = "not_applicable"  # "not found" answers cite nothing


def cited_numbers(answer: str) -> list[int]:
    return [int(n) for group in _MARKER.findall(answer) for n in group.split(",")]


def citation_status(answer: str, source_count: int) -> str:
    text = answer.strip()
    if not text or NOT_FOUND_PHRASE in text.lower():
        return NOT_APPLICABLE
    numbers = cited_numbers(text)
    if not numbers:
        return MISSING
    if any(n < 1 or n > source_count for n in numbers):
        return INVALID
    return OK
