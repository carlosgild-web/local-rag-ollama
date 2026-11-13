"""Glossary expansion (decision 0021): "vacation" -> "vacation (PTO, paid time off)".

The 3B chat model answered "How many vacation days do I have?" with "not
found" although the PTO table was the top passage: it didn't connect the
two words. The glossary writes the documents' words into the question, right
after the word the person used, so both the search and the model see them:

    How many vacation (PTO, paid time off) days do I have?

Matching ignores case and accents, works on whole words, and accepts a
plural ending ("vacations", "urgentes"). A term whose meaning is already in
the question is skipped.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GlossaryTerm
from app.retrieval.textnorm import normalize

_TOKEN = re.compile(r"\w+")
_PLURAL_ENDINGS = ("", "s", "es")


@dataclass(frozen=True)
class Term:
    term: str
    means: str


def _tokens(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), normalize(m.group())) for m in _TOKEN.finditer(text)]


def _same_word(word: str, wanted: str) -> bool:
    return any(word == wanted + ending for ending in _PLURAL_ENDINGS)


def expand_question(question: str, terms: Iterable[Term]) -> str:
    """The question with each glossary term followed by its meaning in brackets."""
    tokens = _tokens(question)
    question_norm = normalize(question)
    inserts: dict[int, list[str]] = {}  # character position -> meanings to add there
    used: set[int] = set()  # token positions already matched by a longer term
    # Longer terms first, so "time off" wins over "time".
    for item in sorted(terms, key=lambda t: -len(t.term.split())):
        wanted = normalize(item.term).split()
        if not wanted or normalize(item.means) in question_norm:
            continue
        for i in range(len(tokens) - len(wanted) + 1):
            window = tokens[i : i + len(wanted)]
            if any(i + k in used for k in range(len(wanted))):
                continue
            if all(w == tok[2] for w, tok in zip(wanted[:-1], window, strict=False)) and (
                _same_word(window[-1][2], wanted[-1])
            ):
                inserts.setdefault(window[-1][1], []).append(item.means)
                used.update(range(i, i + len(wanted)))
                break  # once per term
    if not inserts:
        return question
    out, last = [], 0
    for position in sorted(inserts):
        out.append(question[last:position])
        out.append(f" ({'; '.join(inserts[position])})")
        last = position
    out.append(question[last:])
    return "".join(out)


def terms_from_rows(rows: Sequence) -> list[Term]:
    return [Term(term=r.term, means=r.means) for r in rows]


def load_terms(db: Session) -> list[Term]:
    """The glossary as it is now (read-only; changes go through versioning/glossary.py)."""
    return terms_from_rows(db.execute(select(GlossaryTerm).order_by(GlossaryTerm.term)).scalars())


def expand_with_glossary(db: Session, question: str) -> str:
    return expand_question(question, load_terms(db))
