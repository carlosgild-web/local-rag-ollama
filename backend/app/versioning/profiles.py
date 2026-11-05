"""RAG profiles: versioned settings snapshots (PLAN.md section 5, "Settings
change -> new rag_profile version"). Every assistant message records the
profile version it used (invariant 5); every change is audited (invariant 7).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import RagProfile
from app.retrieval.prompt import NOT_FOUND_PHRASE, SYSTEM_INSTRUCTIONS
from app.versioning.service import NotFoundError, record_audit

DEFAULT_PROFILE_NAME = "default"
EDITABLE_FIELDS = (
    "chat_model",
    "embedding_model",
    "chunk_size_tokens",
    "chunk_overlap_pct",
    "retrieval_top_k",
    "temperature",
    "system_prompt",
)


class InvalidProfileError(ValueError):
    pass


def _defaults(settings: Settings) -> dict:
    return {
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "chunk_size_tokens": settings.chunk_size_tokens,
        "chunk_overlap_pct": settings.chunk_overlap_pct,
        "retrieval_top_k": settings.retrieval_top_k,
        "temperature": settings.llm_temperature,
        "system_prompt": SYSTEM_INSTRUCTIONS,
    }


def _latest(db: Session, name: str) -> RagProfile | None:
    return (
        db.execute(
            select(RagProfile).where(RagProfile.name == name).order_by(RagProfile.version.desc())
        )
        .scalars()
        .first()
    )


def get_profile(db: Session, profile_id: int) -> RagProfile:
    profile = db.get(RagProfile, profile_id)
    if profile is None:
        raise NotFoundError(f"profile {profile_id} not found")
    return profile


def get_active_profile(
    db: Session, settings: Settings, name: str = DEFAULT_PROFILE_NAME
) -> RagProfile:
    """The active version of `name`; the default profile is created from
    Settings on first use."""
    profile = db.execute(
        select(RagProfile).where(RagProfile.name == name, RagProfile.is_active.is_(True))
    ).scalar_one_or_none()
    if profile is not None:
        return profile
    if name != DEFAULT_PROFILE_NAME:
        raise NotFoundError(f"profile {name!r} not found")
    return create_profile_version(db, settings, name=name)


def list_active_profiles(db: Session) -> list[RagProfile]:
    return list(
        db.execute(
            select(RagProfile).where(RagProfile.is_active.is_(True)).order_by(RagProfile.name)
        )
        .scalars()
        .all()
    )


def list_versions(db: Session, profile_id: int) -> list[RagProfile]:
    profile = get_profile(db, profile_id)
    return list(
        db.execute(
            select(RagProfile)
            .where(RagProfile.name == profile.name)
            .order_by(RagProfile.version.desc())
        )
        .scalars()
        .all()
    )


def create_profile_version(
    db: Session, settings: Settings, *, name: str = DEFAULT_PROFILE_NAME, **changes
) -> RagProfile:
    """Creates the next version of `name`: the latest version (or Settings
    defaults) with `changes` applied. Earlier versions are kept, inactive."""
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise InvalidProfileError(f"unknown profile fields: {sorted(unknown)}")

    latest = _latest(db, name)
    base = {f: getattr(latest, f) for f in EDITABLE_FIELDS} if latest else _defaults(settings)
    values = {**base, **{k: v for k, v in changes.items() if v is not None}}
    _validate(values)

    if latest is not None:
        for old in db.execute(select(RagProfile).where(RagProfile.name == name)).scalars():
            old.is_active = False

    profile = RagProfile(
        name=name, version=(latest.version + 1) if latest else 1, is_active=True, **values
    )
    db.add(profile)
    db.flush()
    changed = sorted(k for k in values if latest is None or values[k] != base[k])
    record_audit(
        db,
        "settings_change",
        "rag_profile",
        profile.id,
        f"{name} v{profile.version}" + (f": {', '.join(changed)}" if latest else " created"),
    )
    db.commit()
    return profile


def _validate(values: dict) -> None:
    # Invariant 6: the prompt must keep the grounded-answer rule.
    if NOT_FOUND_PHRASE not in values["system_prompt"]:
        raise InvalidProfileError(
            f"system_prompt must tell the model to answer {NOT_FOUND_PHRASE!r} "
            "when the context lacks the answer"
        )
    if not 1 <= values["retrieval_top_k"] <= 50:
        raise InvalidProfileError("retrieval_top_k must be between 1 and 50")
    if not 0.0 <= values["temperature"] <= 2.0:
        raise InvalidProfileError("temperature must be between 0 and 2")
    if values["chunk_size_tokens"] < 50:
        raise InvalidProfileError("chunk_size_tokens must be at least 50")
    if not 0.0 <= values["chunk_overlap_pct"] < 0.5:
        raise InvalidProfileError("chunk_overlap_pct must be in [0, 0.5)")
