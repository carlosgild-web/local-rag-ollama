"""RAG profiles (PLAN.md section 8). Every save is a new version; answers
record which version produced them. Restoring an old version saves its
values as the next version, so history is never rewritten."""

from fastapi import APIRouter, Query, status

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import (
    ProfileCompareOut,
    ProfileFieldChange,
    ProfileIn,
    ProfileOut,
    ProfileVersionOut,
)
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


@router.get("/profiles/compare", response_model=ProfileCompareOut)
def compare_profile_versions(db: DbDep, a: int = Query(...), b: int = Query(...)):
    """Two versions of one profile: the fields that differ and a line diff of the prompt."""
    result = profiles.compare_versions(db, a, b)
    return ProfileCompareOut(
        a=ProfileOut.model_validate(result.a),
        b=ProfileOut.model_validate(result.b),
        changes=[ProfileFieldChange(field=c.field, a=c.a, b=c.b) for c in result.changes],
        prompt_diff=result.prompt_diff,
    )


@router.get("/profiles/{profile_id}/versions", response_model=list[ProfileVersionOut])
def list_profile_versions(db: DbDep, profile_id: int):
    """Every version of the profile, newest first, with how often each was used."""
    versions = profiles.list_versions(db, profile_id)
    usage = profiles.usage_counts(db, [v.id for v in versions])
    return [
        ProfileVersionOut(
            **ProfileOut.model_validate(v).model_dump(),
            answer_count=usage[v.id][0],
            eval_run_count=usage[v.id][1],
        )
        for v in versions
    ]


@router.post(
    "/profiles/{profile_id}/restore",
    status_code=status.HTTP_201_CREATED,
    response_model=ProfileOut,
)
def restore_profile_version(db: DbDep, runtime: RuntimeDep, profile_id: int):
    """Saves that version's values as the next version (audited)."""
    return profiles.restore_version(db, runtime.settings, profile_id)
