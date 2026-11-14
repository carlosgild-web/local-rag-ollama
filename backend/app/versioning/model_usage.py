"""Which Ollama models the app depends on (the Models manager, PLAN.md Phase 6).

A model is in use when an active profile chats with it, an active shelf
embeds with it, or it is the embedding model new shelves get
(`EMBEDDING_MODEL`). Deleting a model in use would break answers or the
search, so the API refuses it.

Ollama tags every model (`bge-m3` is `bge-m3:latest`), while settings and
profiles often leave the tag out, so names are compared without ":latest".
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Collection, RagProfile


def same_model(name: str) -> str:
    """The comparable form of a model name: lower case, without ':latest'."""
    name = name.strip().lower()
    return name.removesuffix(":latest")


def model_uses(db: Session, settings: Settings) -> dict[str, list[str]]:
    """Plain descriptions of each use, keyed by `same_model(name)`."""
    uses: dict[str, list[str]] = {}

    def add(model: str, what: str) -> None:
        uses.setdefault(same_model(model), []).append(what)

    for profile in db.execute(
        select(RagProfile).where(RagProfile.is_active.is_(True)).order_by(RagProfile.name)
    ).scalars():
        add(profile.chat_model, f"chat model of profile {profile.name} v{profile.version}")
    for shelf in db.execute(
        select(Collection).where(Collection.is_active.is_(True)).order_by(Collection.name)
    ).scalars():
        add(shelf.embedding_model, f"embedding model of shelf {shelf.name}")
    add(settings.embedding_model, "embedding model for new shelves (EMBEDDING_MODEL)")
    return uses


def uses_of(db: Session, settings: Settings, name: str) -> list[str]:
    return model_uses(db, settings).get(same_model(name), [])
