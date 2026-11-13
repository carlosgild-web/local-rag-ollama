"""Evaluation service (Phase 7, decision 0019): golden sets, runs, comparison.

The one writer to the eval_* tables, as the versioning service is for
documents (invariant 1). Edits to a golden set and every run started are
audited (invariant 7).

A run measures the same path the console chat takes: the same hybrid
retrieval over the case's shelf (or all shelves), the profile's top-k,
system prompt, chat model and temperature. On top of that it can switch
retrieval to vectors only or keywords only, to compare them.
"""

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Chunk,
    Collection,
    Document,
    DocumentVersion,
    EvalCase,
    EvalResult,
    EvalRun,
    EvalSet,
    IngestJob,
    RagProfile,
    utcnow,
)
from app.eval import judge, metrics
from app.jobs import queue
from app.llm.base import EmbeddingClient, LLMClient
from app.retrieval.citation_repair import repair_citations
from app.retrieval.citations import citation_status
from app.retrieval.glossary import Term, expand_question, load_terms
from app.retrieval.prompt import NOT_FOUND_PHRASE, build_prompt
from app.retrieval.retrieve import RETRIEVAL_MODES, retrieve_many
from app.retrieval.vector_store import VectorStore
from app.versioning import profiles, service
from app.versioning.service import ConflictError, NotFoundError, ProgressCallback, record_audit

DEMO_SET_PATH = Path(__file__).resolve().parents[2] / "demo" / "eval" / "hilda-luna-golden.json"

CASE_FIELDS = (
    "question",
    "shelf",
    "expected_sources",
    "required_facts",
    "expect_not_found",
    "kind",
    "variant_group",
    "expected_answer_notes",
)


class InvalidEvalError(ValueError):
    pass


# --- Golden sets ------------------------------------------------------------


def list_sets(db: Session) -> list[EvalSet]:
    return list(db.execute(select(EvalSet).order_by(EvalSet.name)).scalars().all())


def get_set(db: Session, set_id: int) -> EvalSet:
    eval_set = db.get(EvalSet, set_id)
    if eval_set is None:
        raise NotFoundError(f"eval set {set_id} not found")
    return eval_set


def _check_name(db: Session, name: str, *, keep_id: int | None = None) -> str:
    name = name.strip()
    if not name:
        raise InvalidEvalError("a golden set needs a name")
    existing = db.execute(select(EvalSet).where(EvalSet.name == name)).scalar_one_or_none()
    if existing is not None and existing.id != keep_id:
        raise ConflictError(f"a golden set named {name!r} already exists")
    return name


def create_set(db: Session, name: str, description: str = "") -> EvalSet:
    eval_set = EvalSet(name=_check_name(db, name), description=description.strip())
    db.add(eval_set)
    db.flush()
    record_audit(db, "eval_set_create", "eval_set", eval_set.id, eval_set.name)
    db.commit()
    return eval_set


def update_set(
    db: Session, set_id: int, *, name: str | None = None, description: str | None = None
) -> EvalSet:
    eval_set = get_set(db, set_id)
    if name is not None:
        eval_set.name = _check_name(db, name, keep_id=set_id)
    if description is not None:
        eval_set.description = description.strip()
    record_audit(db, "eval_set_update", "eval_set", set_id, eval_set.name)
    db.commit()
    return eval_set


def delete_set(db: Session, set_id: int) -> None:
    """Removes the set, its cases and its runs. Refused while a run is going."""
    eval_set = get_set(db, set_id)
    runs = list(db.execute(select(EvalRun).where(EvalRun.eval_set_id == set_id)).scalars())
    if any(run_status(db, run) in {"pending", "running"} for run in runs):
        raise ConflictError("a run of this golden set is still going; cancel it first")
    for run in runs:
        db.delete(run)
    record_audit(
        db, "eval_set_delete", "eval_set", set_id, f"{eval_set.name} ({len(eval_set.cases)} cases)"
    )
    db.delete(eval_set)
    db.commit()


def _clean_case(fields: dict) -> dict:
    """Validates and tidies case fields; only the given ones are returned."""
    clean = {}
    for key, value in fields.items():
        if key not in CASE_FIELDS:
            raise InvalidEvalError(f"unknown case field {key!r}")
        if key == "question":
            value = (value or "").strip()
            if not value:
                raise InvalidEvalError("a case needs a question")
        elif key in {"shelf", "variant_group", "expected_answer_notes"}:
            value = (value or "").strip() or None
        elif key == "kind":
            value = (value or "").strip()
        elif key == "expected_sources":
            value = [s.strip() for s in value or [] if s and s.strip()]
        elif key == "required_facts":
            value = [[a.strip() for a in group if a and a.strip()] for group in value or []]
            value = [group for group in value if group]
        elif key == "expect_not_found":
            value = bool(value)
        clean[key] = value
    return clean


def _check_case(case: EvalCase) -> None:
    if case.expect_not_found and (case.required_facts or case.expected_sources):
        raise InvalidEvalError("a 'not found' case can't have required facts or expected sources")


def add_case(db: Session, set_id: int, **fields) -> EvalCase:
    get_set(db, set_id)
    fields = _clean_case(fields)
    if "question" not in fields:
        raise InvalidEvalError("a case needs a question")
    case = EvalCase(eval_set_id=set_id, **fields)
    _check_case(case)
    db.add(case)
    db.flush()
    record_audit(db, "eval_case_create", "eval_case", case.id, case.question[:200])
    db.commit()
    return case


def get_case(db: Session, case_id: int) -> EvalCase:
    case = db.get(EvalCase, case_id)
    if case is None:
        raise NotFoundError(f"eval case {case_id} not found")
    return case


def update_case(db: Session, case_id: int, **fields) -> EvalCase:
    case = get_case(db, case_id)
    for key, value in _clean_case(fields).items():
        setattr(case, key, value)
    _check_case(case)
    record_audit(db, "eval_case_update", "eval_case", case_id, case.question[:200])
    db.commit()
    return case


def delete_case(db: Session, case_id: int) -> None:
    """Old runs keep their copy of the case; only the link to it goes."""
    case = get_case(db, case_id)
    for result in db.execute(
        select(EvalResult).where(EvalResult.eval_case_id == case_id)
    ).scalars():
        result.eval_case_id = None
    record_audit(db, "eval_case_delete", "eval_case", case_id, case.question[:200])
    db.delete(case)
    db.commit()


# --- Import and export (the JSON file format of demo/eval/) -----------------

# File key -> case field. The file uses short keys so it's easy to write by hand.
_FILE_KEYS = {
    "question": "question",
    "shelf": "shelf",
    "sources": "expected_sources",
    "facts": "required_facts",
    "not_found": "expect_not_found",
    "kind": "kind",
    "group": "variant_group",
    "notes": "expected_answer_notes",
}


def import_set(db: Session, data: dict, *, name: str | None = None) -> EvalSet:
    """Creates a set from the file format: {"name", "description", "cases": [
    {"question", "shelf", "sources", "facts", "not_found", "kind", "group", "notes"}]}."""
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise InvalidEvalError("expected an object with a 'cases' list")
    set_name = _check_name(db, name or data.get("name") or "")
    eval_set = EvalSet(name=set_name, description=(data.get("description") or "").strip())
    db.add(eval_set)
    for number, item in enumerate(data["cases"], start=1):
        unknown = set(item) - set(_FILE_KEYS)
        if unknown:
            raise InvalidEvalError(f"case {number}: unknown keys {sorted(unknown)}")
        try:
            fields = _clean_case({_FILE_KEYS[k]: v for k, v in item.items()})
            if "question" not in fields:
                raise InvalidEvalError("a case needs a question")
            case = EvalCase(**fields)
            _check_case(case)
        except InvalidEvalError as exc:
            raise InvalidEvalError(f"case {number}: {exc}") from None
        eval_set.cases.append(case)
    db.flush()
    record_audit(
        db, "eval_set_import", "eval_set", eval_set.id, f"{set_name} ({len(eval_set.cases)} cases)"
    )
    db.commit()
    return eval_set


def export_set(db: Session, set_id: int) -> dict:
    eval_set = get_set(db, set_id)
    cases = []
    for case in eval_set.cases:
        item: dict = {"question": case.question}
        if case.shelf:
            item["shelf"] = case.shelf
        if case.kind:
            item["kind"] = case.kind
        if case.variant_group:
            item["group"] = case.variant_group
        if case.expect_not_found:
            item["not_found"] = True
        if case.expected_sources:
            item["sources"] = case.expected_sources
        if case.required_facts:
            item["facts"] = case.required_facts
        if case.expected_answer_notes:
            item["notes"] = case.expected_answer_notes
        cases.append(item)
    return {"name": eval_set.name, "description": eval_set.description, "cases": cases}


def demo_set_available() -> bool:
    return DEMO_SET_PATH.is_file()


def load_demo_set(db: Session) -> EvalSet:
    """The golden set for the demo company. A 409 if it's already loaded."""
    if not demo_set_available():
        raise NotFoundError("the demo golden set isn't part of this install")
    return import_set(db, json.loads(DEMO_SET_PATH.read_text(encoding="utf-8")))


# --- Runs -------------------------------------------------------------------


def run_status(db: Session, run: EvalRun) -> str:
    """completed once results are in; before that, its job's status. A run
    without a job came from the CLI, which only runs while the app is stopped:
    seen from the app, an unfinished one was interrupted."""
    if run.finished_at is not None:
        return "completed"
    job = db.get(IngestJob, run.job_id) if run.job_id else None
    return job.status if job is not None else "cancelled"


def default_label(config: dict, profile: RagProfile) -> str:
    parts = [config["mode"], f"k={config['top_k']}", f"{profile.name} v{profile.version}"]
    if config["answers"]:
        parts.append(profile.chat_model)
    if config["judge"]:
        parts.append("judged")
    if config["answers"] and not config.get("repair_citations", True):
        parts.append("no citation repair")
    if not config.get("use_glossary", True):
        parts.append("no glossary")
    return ", ".join(parts)


def start_run(
    db: Session,
    settings: Settings,
    set_id: int,
    *,
    profile_id: int | None = None,
    mode: str = "hybrid",
    top_k: int | None = None,
    answers: bool = False,
    judge: bool = False,
    judge_model: str | None = None,
    repair: bool = True,
    glossary: bool = True,
    label: str = "",
    queue_job: bool = True,
) -> EvalRun:
    """Queues a run_eval job. One run at a time: a second request is a 409.
    The CLI passes queue_job=False and calls execute_run itself."""
    eval_set = get_set(db, set_id)
    if not eval_set.cases:
        raise InvalidEvalError("this golden set has no cases yet")
    if mode not in RETRIEVAL_MODES:
        raise InvalidEvalError(f"mode must be one of {', '.join(RETRIEVAL_MODES)}")
    if judge and not answers:
        raise InvalidEvalError("the faithfulness judge needs answers; turn answers on")
    if top_k is not None and not 1 <= top_k <= settings.retrieval_candidates:
        raise InvalidEvalError(f"top_k must be between 1 and {settings.retrieval_candidates}")
    unfinished = db.execute(select(EvalRun).where(EvalRun.finished_at.is_(None))).scalars()
    if any(run_status(db, run) in {"pending", "running"} for run in unfinished):
        raise ConflictError("an evaluation run is already going; wait for it or cancel it")

    profile = (
        profiles.get_profile(db, profile_id)
        if profile_id is not None
        else profiles.get_active_profile(db, settings)
    )
    config = {
        "mode": mode,
        "top_k": top_k or profile.retrieval_top_k,
        "answers": answers,
        "judge": judge,
        "judge_model": (judge_model or profile.chat_model) if judge else None,
        # Citation repair, as the chat does (decision 0020); off to measure without it.
        "repair_citations": repair,
        # The glossary as it was when the run started (decision 0021).
        "use_glossary": glossary,
        "glossary": [
            {"term": t.term, "means": t.means} for t in (load_terms(db) if glossary else [])
        ],
    }
    run = EvalRun(
        eval_set_id=set_id,
        rag_profile_id=profile.id,
        config=config,
        label=label.strip() or default_label(config, profile),
    )
    db.add(run)
    db.flush()
    record_audit(db, "eval_run", "eval_run", run.id, f"{eval_set.name}: {run.label}")
    db.commit()
    if queue_job:
        job = queue.enqueue(db, "run_eval", {"run_id": run.id})
        run.job_id = job.id
        db.commit()
    return run


def list_runs(db: Session, set_id: int | None = None) -> list[EvalRun]:
    query = select(EvalRun).order_by(EvalRun.id.desc())
    if set_id is not None:
        query = query.where(EvalRun.eval_set_id == set_id)
    return list(db.execute(query).scalars().all())


def get_run(db: Session, run_id: int) -> EvalRun:
    run = db.get(EvalRun, run_id)
    if run is None:
        raise NotFoundError(f"eval run {run_id} not found")
    return run


def delete_run(db: Session, run_id: int) -> None:
    run = get_run(db, run_id)
    if run_status(db, run) in {"pending", "running"}:
        raise ConflictError("this run is still going; cancel it first")
    record_audit(db, "eval_run_delete", "eval_run", run_id, run.label)
    db.delete(run)
    db.commit()


def index_snapshot(db: Session, collections: list[Collection]) -> list[dict]:
    """What each shelf held when the run started. The fingerprint changes when
    any document's active version changes (an upload, edit, rollback, delete),
    so two runs with equal fingerprints searched the same index."""
    snapshot = []
    for collection in collections:
        versions = db.execute(
            select(Document.id, Document.active_version_id)
            .where(
                Document.collection_id == collection.id,
                Document.trashed_at.is_(None),
                Document.active_version_id.is_not(None),
            )
            .order_by(Document.id)
        ).all()
        chunks = db.execute(
            select(func.count())
            .select_from(Chunk)
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Chunk.collection_id == collection.id,
                Chunk.retired_at.is_(None),
                Document.active_version_id == Chunk.version_id,
                Document.trashed_at.is_(None),
            )
        ).scalar_one()
        digest = hashlib.sha256(
            json.dumps([collection.id, *[list(v) for v in versions]]).encode()
        ).hexdigest()
        snapshot.append(
            {
                "shelf": collection.name,
                "collection_id": collection.id,
                "embedding_model": collection.embedding_model,
                "chunk_size_tokens": collection.chunk_size_tokens,
                "documents": len(versions),
                "chunks": chunks,
                "fingerprint": digest[:12],
            }
        )
    return snapshot


def _shelves_for(db: Session, cases: list[EvalCase]) -> list[Collection]:
    if any(case.shelf is None for case in cases):
        return service.active_collections(db)
    names = sorted({case.shelf for case in cases if case.shelf})
    return [c for name in names if (c := service.get_active_collection(db, name)) is not None]


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def execute_run(
    db: Session,
    run_id: int,
    *,
    settings: Settings,
    embedding_client_for: Callable[[str], EmbeddingClient],
    vector_store: VectorStore,
    llm_client_for: Callable[[str], LLMClient],
    progress: ProgressCallback | None = None,
) -> dict:
    """Runs every case and stores the results and totals. Starts over if a
    previous attempt was interrupted (a restart or a retry of the job)."""
    run = get_run(db, run_id)
    profile = profiles.get_profile(db, run.rag_profile_id) if run.rag_profile_id else None
    if profile is None:
        raise NotFoundError(f"eval run {run_id} has no profile")
    config = run.config
    cases = list(get_set(db, run.eval_set_id).cases)

    run.results.clear()
    run.metrics = None
    run.hit_rate_at_5 = run.mrr = None
    run.index_snapshot = index_snapshot(db, _shelves_for(db, cases))
    db.commit()

    terms = [Term(**t) for t in config.get("glossary", [])]
    llm = llm_client_for(profile.chat_model) if config["answers"] else None
    judge_llm = llm_client_for(config["judge_model"]) if config.get("judge") else None
    if progress is not None:
        progress(0.0)
    for number, case in enumerate(cases, start=1):
        run.results.append(
            _run_case(
                db,
                case,
                config=config,
                profile=profile,
                settings=settings,
                embedding_client_for=embedding_client_for,
                vector_store=vector_store,
                llm=llm,
                judge_llm=judge_llm,
                terms=terms,
            )
        )
        db.commit()
        if progress is not None:
            progress(number / len(cases))  # raises JobCancelled on a cancel

    totals = metrics.summarize(run.results, with_answers=config["answers"])
    run.metrics = totals
    run.hit_rate_at_5 = totals["hit_rate_at_5"]
    run.mrr = totals["mrr"]
    run.finished_at = utcnow()
    db.commit()
    return {
        "run_id": run.id,
        "cases": totals["cases"],
        "hit_rate_at_5": totals["hit_rate_at_5"],
        "mrr": totals["mrr"],
        "pass_rate": totals["pass_rate"],
    }


def _run_case(
    db: Session,
    case: EvalCase,
    *,
    config: dict,
    profile: RagProfile,
    settings: Settings,
    embedding_client_for: Callable[[str], EmbeddingClient],
    vector_store: VectorStore,
    llm: LLMClient | None,
    judge_llm: LLMClient | None,
    terms: list[Term],
) -> EvalResult:
    result = EvalResult(
        eval_case_id=case.id,
        question=case.question,
        shelf=case.shelf,
        kind=case.kind,
        variant_group=case.variant_group,
        expect_not_found=case.expect_not_found,
        expected_sources=list(case.expected_sources),
        required_facts=[list(g) for g in case.required_facts],
        retrieved=[],
    )
    if case.shelf is None:
        collections = service.active_collections(db)
    else:
        shelf = service.get_active_collection(db, case.shelf)
        collections = [shelf] if shelf is not None else []
    if not collections:
        result.error = f"no shelf named {case.shelf!r}" if case.shelf else "no shelves"
        result.passed = False
        return result

    question = expand_question(case.question, terms)
    start = time.perf_counter()
    # All candidates, so the rank of the right file is known even past top-k.
    chunks = retrieve_many(
        db,
        question,
        collections=collections,
        settings=settings,
        embedding_client_for=embedding_client_for,
        vector_store=vector_store,
        top_k=settings.retrieval_candidates,
        mode=config["mode"],
    )
    result.retrieval_ms = _ms(start)
    result.retrieved = [
        {"chunk_id": c.chunk_id, "filename": c.filename, "score": round(c.score, 6)} for c in chunks
    ]
    result.first_relevant_rank = metrics.first_relevant_rank(
        [c.filename for c in chunks], case.expected_sources
    )

    if llm is not None:
        sent = chunks[: config["top_k"]]
        start = time.perf_counter()
        if sent:
            answer = llm.generate(
                build_prompt(question, sent, profile.system_prompt),
                temperature=profile.temperature,
                num_ctx=settings.ollama_num_ctx,
            )
            if config.get("repair_citations", True):
                answer = repair_citations(answer, [c.text for c in sent]).text
        else:
            answer = NOT_FOUND_PHRASE  # what the chat says with nothing retrieved
        result.answer_ms = _ms(start)
        result.answer = answer
        result.not_found = metrics.is_not_found(answer)
        result.missing_facts = metrics.missing_facts(answer, case.required_facts)
        result.citation_status = citation_status(answer, len(sent))
        result.cited_sources = metrics.cited_filenames(answer, [c.filename for c in sent])
        if judge_llm is not None and sent and not result.not_found:
            reply = judge_llm.generate(
                judge.judge_prompt(sent, answer), temperature=0.0, num_ctx=settings.ollama_num_ctx
            )
            result.faithfulness, result.judge_note = judge.parse_verdict(reply)

    result.passed = metrics.case_passed(result, with_answers=llm is not None)
    return result


# --- Comparison -------------------------------------------------------------


def _brief(result: EvalResult) -> dict:
    return {
        "result_id": result.id,
        "first_relevant_rank": result.first_relevant_rank,
        "top_source": result.retrieved[0]["filename"] if result.retrieved else None,
        "answer": result.answer,
        "not_found": result.not_found,
        "missing_facts": result.missing_facts,
        "cited_sources": result.cited_sources,
        "faithfulness": result.faithfulness,
        "passed": result.passed,
        "error": result.error,
    }


def _change(a: EvalResult | None, b: EvalResult | None) -> str:
    """How case results moved from run a to run b."""
    if a is None or b is None:
        return "only_a" if b is None else "only_b"
    if a.passed is not None and b.passed is not None and a.passed != b.passed:
        return "fixed" if b.passed else "broken"
    rank_a, rank_b = a.first_relevant_rank, b.first_relevant_rank
    if rank_a != rank_b:
        if rank_b is not None and (rank_a is None or rank_b < rank_a):
            return "better"
        return "worse"
    return "same"


def compare_runs(db: Session, a_id: int, b_id: int) -> dict:
    """Two runs side by side, case by case. Cases are matched by golden-set
    case, or by question and shelf for cases deleted since."""
    run_a, run_b = get_run(db, a_id), get_run(db, b_id)

    def key(result: EvalResult):
        return result.eval_case_id or (result.question, result.shelf)

    b_by_key = {key(r): r for r in run_b.results}
    rows = []
    seen = set()
    for a in run_a.results:
        b = b_by_key.get(key(a))
        seen.add(key(a))
        rows.append(_row(a, b))
    rows += [_row(None, b) for b in run_b.results if key(b) not in seen]

    fingerprints_a = {s["shelf"]: s["fingerprint"] for s in run_a.index_snapshot}
    fingerprints_b = {s["shelf"]: s["fingerprint"] for s in run_b.index_snapshot}
    return {
        "a": run_a,
        "b": run_b,
        "same_index": fingerprints_a == fingerprints_b,
        "cases": rows,
    }


def _row(a: EvalResult | None, b: EvalResult | None) -> dict:
    either = a or b
    return {
        "case_id": either.eval_case_id,
        "question": either.question,
        "shelf": either.shelf,
        "kind": either.kind,
        "variant_group": either.variant_group,
        "expect_not_found": either.expect_not_found,
        "a": _brief(a) if a else None,
        "b": _brief(b) if b else None,
        "change": _change(a, b),
    }
