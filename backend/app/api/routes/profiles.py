"""RAG profiles (PLAN.md section 8). Every save is a new version; answers
record which version produced them."""

from fastapi import APIRouter, status

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import ProfileIn, ProfileOut
from app.versioning import profiles

router = APIRouter(tags=["profiles"])


@router.get("/profiles", response_model=list[ProfileOut])
def list_profiles(db: DbDep, runtime: RuntimeDep):
    """The active version of each profile (the default one is created on first use)."""
    profiles.get_active_profile(db, runtime.settings)
    return profiles.list_active_profiles(db)


@router.post("/profiles", status_code=status.HTTP_201_CREATED, response_model=ProfileOut)
def save_profile(db: DbDep, runtime: RuntimeDep, body: ProfileIn):
    """Creates the next version of `name` from its latest version plus the
    fields given. Omitted fields are carried over."""
    changes = body.model_dump(exclude={"name"}, exclude_none=True)
    return profiles.create_profile_version(db, runtime.settings, name=body.name, **changes)


@router.get("/profiles/{profile_id}/versions", response_model=list[ProfileOut])
def list_profile_versions(db: DbDep, profile_id: int):
    return profiles.list_versions(db, profile_id)
