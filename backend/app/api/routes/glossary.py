"""The glossary (decision 0021): words people use and the words the documents use."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbDep
from app.api.schemas import GlossaryIn, GlossaryOut, GlossaryPreviewOut
from app.retrieval.glossary import expand_with_glossary
from app.versioning import glossary

router = APIRouter(prefix="/glossary", tags=["glossary"])


@router.get("", response_model=list[GlossaryOut])
def list_terms(db: DbDep):
    return glossary.list_terms(db)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=GlossaryOut)
def add_term(db: DbDep, body: GlossaryIn):
    return glossary.add_term(db, body.term, body.means)


@router.delete("/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_term(db: DbDep, term_id: int):
    glossary.delete_term(db, term_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/demo", response_model=list[GlossaryOut])
def load_demo_terms(db: DbDep):
    """Adds the demo company's entries that aren't there yet."""
    return glossary.load_demo_glossary(db)


@router.get("/preview", response_model=GlossaryPreviewOut)
def preview(db: DbDep, question: Annotated[str, Query(min_length=1, max_length=2000)]):
    """How a question reads after the glossary, as the search and the model see it."""
    return GlossaryPreviewOut(question=question, expanded=expand_with_glossary(db, question))
