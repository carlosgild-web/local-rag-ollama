"""The glossary's service layer (decision 0021). Every change is audited as a
settings change would be (invariant 7): it changes how questions are asked."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GlossaryTerm
from app.retrieval.glossary import Term, load_terms
from app.versioning.service import ConflictError, NotFoundError, record_audit

DEMO_GLOSSARY_PATH = Path(__file__).resolve().parents[2] / "demo" / "glossary.json"


class InvalidGlossaryError(ValueError):
    pass


def list_terms(db: Session) -> list[GlossaryTerm]:
    return list(db.execute(select(GlossaryTerm).order_by(GlossaryTerm.term)).scalars().all())


def active_terms(db: Session) -> list[Term]:
    """What questions are expanded with right now."""
    return load_terms(db)


def add_term(db: Session, term: str, means: str) -> GlossaryTerm:
    term, means = " ".join(term.split()), " ".join(means.split())
    if not term or not means:
        raise InvalidGlossaryError("a glossary entry needs a word and what it means")
    if term.lower() == means.lower():
        raise InvalidGlossaryError("the meaning must differ from the word")
    existing = db.execute(select(GlossaryTerm).where(GlossaryTerm.term.ilike(term))).scalar()
    if existing is not None:
        raise ConflictError(f"{existing.term!r} is already in the glossary")
    row = GlossaryTerm(term=term, means=means)
    db.add(row)
    db.flush()
    record_audit(db, "glossary_add", "glossary", row.id, f"{term} -> {means}")
    db.commit()
    return row


def delete_term(db: Session, term_id: int) -> None:
    row = db.get(GlossaryTerm, term_id)
    if row is None:
        raise NotFoundError(f"glossary entry {term_id} not found")
    record_audit(db, "glossary_delete", "glossary", term_id, f"{row.term} -> {row.means}")
    db.delete(row)
    db.commit()


def demo_glossary_available() -> bool:
    return DEMO_GLOSSARY_PATH.is_file()


def load_demo_glossary(db: Session) -> list[GlossaryTerm]:
    """Adds the demo company's entries that aren't there yet."""
    if not demo_glossary_available():
        raise NotFoundError("the demo glossary isn't part of this install")
    have = {row.term.lower() for row in list_terms(db)}
    added = []
    for item in json.loads(DEMO_GLOSSARY_PATH.read_text(encoding="utf-8"))["terms"]:
        if item["term"].lower() not in have:
            added.append(add_term(db, item["term"], item["means"]))
    return added
