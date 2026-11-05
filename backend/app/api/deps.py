"""FastAPI dependencies: the shared Runtime and a per-request DB session."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_db(runtime: Annotated[Runtime, Depends(get_runtime)]) -> Iterator[Session]:
    db = runtime.session_factory()
    try:
        yield db
    finally:
        db.close()


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
DbDep = Annotated[Session, Depends(get_db)]
