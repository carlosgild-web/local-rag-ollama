# ruff: noqa: E501  (tag descriptions and user-facing messages read better unwrapped)
"""Intake: analyze dropped files and suggest a shelf and tags for each one,
before anything is indexed (decision 0009).

Flow: stage the files -> an `analyze_intake` job parses each one, checks it
against the library (duplicate / new version), picks tags, and suggests an
existing shelf or a new one -> the user reviews and changes anything ->
confirm creates the approved shelves and queues the normal ingest jobs from
the staged files. Cancel (or 24 h) removes the staged files.

Suggestions are cheap and local: bge-m3 similarity on a ~2,000-character
excerpt, keyword rules for tags, and the chat model only to name a new
shelf (with a keyword fallback). New shelves are broad, one per audience
(staff vs business), decided from the department tag: excerpt similarity
alone could not separate them on the sample corpus. Thresholds were measured on the sample
corpus; see docs/decisions/0009-suggested-shelves-and-tags.md.
"""

import datetime as dt
import json
import re
import shutil
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Collection, Document, DocumentVersion, utcnow
from app.ingest import file_store
from app.ingest.parsers import SUPPORTED_EXTENSIONS
from app.ingest.uploads import safe_filename
from app.versioning import service

EXCERPT_CHARS = 2000
EMBED_BATCH = 16
# Matching an existing shelf: best score must reach this, and beat the next
# shelf by MARGIN to be "high" confidence (else "low": please check).
SHELF_MATCH_MIN = 0.60
SHELF_MARGIN = 0.03
DEPARTMENT_BONUS = 0.05  # same department tag as most of the shelf's documents
TAG_MARGIN = 0.02
NAMING_TIMEOUT_S = 60
BATCH_TTL = dt.timedelta(hours=24)
SHELF_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

DEPARTMENTS = {
    "hr": "Human resources for employees: hiring, onboarding, leave, holidays, pay, benefits, conduct, employee handbook.",
    "sales": "Sales and products: product catalog, prices, wholesale tiers, sales results, revenue, customers' orders.",
    "customer-support": "Customer service: questions customers ask, shipping, delivery, returns, refunds, damaged orders.",
    "procurement": "Buying from suppliers: supplier contracts, purchase terms, raw materials, vendor agreements.",
    "quality": "Quality control: inspections, defects, sampling, tolerances, rejecting batches.",
    "operations": "Workshop and production operations: equipment, safety rules, protective gear, production processes.",
    "management": "Management and planning: meeting notes, decisions, action items, forecasts, company results.",
}
# Few broad shelves: each department belongs to one audience, and files
# without a shelf are grouped by audience into suggested new shelves.
AUDIENCE = {
    "hr": "staff",
    "operations": "staff",
    "quality": "staff",
    "sales": "business",
    "customer-support": "business",
    "procurement": "business",
    "management": "business",
}
KINDS = {
    "policy": "A policy that states rules and what is allowed, with conditions and procedures.",
    "manual": "A manual or training guide that explains how to do work step by step.",
    "checklist": "A checklist of items or steps to tick off.",
    "announcement": "An announcement or memo telling staff about an event, dates or a change.",
    "catalog": "A product catalog listing items with descriptions and prices.",
    "price-list": "A price list or pricing sheet with prices, discounts and tiers.",
    "contract": "A contract or agreement between parties with terms, obligations and signatures.",
    "faq": "Frequently asked questions with questions and answers.",
    "meeting-notes": "Meeting notes with attendees, discussion points and action items.",
}
# Strong clues in the file name or the text decide the kind before any model.
KIND_KEYWORDS = [
    ("faq", re.compile(r"\bfaq\b|frequently asked|^\s*q:", re.I | re.M)),
    ("meeting-notes", re.compile(r"meeting[-_ ]notes|\battendees:|\baction items\b", re.I)),
    ("checklist", re.compile(r"checklist|^\s*\[ \]", re.I | re.M)),
    ("contract", re.compile(r"\bagreement\b|\bcontract\b", re.I)),
    ("price-list", re.compile(r"pricing|price[-_ ]list|price sheet", re.I)),
    ("catalog", re.compile(r"\bcatalog(ue)?\b", re.I)),
    ("announcement", re.compile(r"announcement|\bmemo\b", re.I)),
    ("manual", re.compile(r"\bmanual\b|\btraining\b|\bguide\b", re.I)),
    ("policy", re.compile(r"\bpolicy\b|\bhandbook\b", re.I)),
]
QUARTER = re.compile(r"\bQ([1-4])\s*(20\d\d)\b")
YEAR = re.compile(r"\b(20[2-3]\d)\b")


# --- Data -------------------------------------------------------------------


@dataclass
class IntakeFile:
    key: str
    name: str  # what the document will be called (the file name)
    path: str  # relative path as picked, e.g. "HR/policy.docx"
    stored: str  # staged copy, relative to the batch folder
    size: int
    sha256: str = ""
    status: str = "pending"  # new | new_version | duplicate | name_in_trash | unsupported | empty | too_large | unreadable
    message: str = ""
    include: bool = True
    shelf: str | None = None  # "existing:<collection id>" or "new:<group key>"
    confidence: str = "high"  # high | low ("please check")
    reason: str = ""
    tags: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)  # other good shelves


@dataclass
class SuggestedShelf:
    ref: str  # "existing:<id>" or "new:<key>"
    name: str
    description: str = ""
    existing: bool = False
    named_by: str = ""  # "model" | "keywords" | "existing"


def _batch_dir(settings: Settings, batch_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", batch_id):
        raise service.NotFoundError(f"intake batch {batch_id!r} not found")
    return settings.uploads_dir / "intake" / batch_id


def _manifest_path(settings: Settings, batch_id: str) -> Path:
    return _batch_dir(settings, batch_id) / "manifest.json"


def load_batch(settings: Settings, batch_id: str) -> dict:
    path = _manifest_path(settings, batch_id)
    if not path.exists():
        raise service.NotFoundError(f"intake batch {batch_id!r} not found (it may have expired)")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_batch(settings: Settings, batch_id: str, manifest: dict) -> None:
    path = _manifest_path(settings, batch_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    tmp.replace(path)


# --- Staging ------------------------------------------------------------------


def stage_batch(settings: Settings, uploads: list[tuple[str, str, object]]) -> tuple[str, int]:
    """Copies uploaded files (name, relative path, binary stream) into a new
    batch folder. Returns the batch id and the number of files."""
    batch_id = uuid.uuid4().hex
    folder = _batch_dir(settings, batch_id) / "files"
    folder.mkdir(parents=True)
    files = []
    max_bytes = settings.max_upload_mb * 1024 * 1024
    for index, (filename, rel_path, stream) in enumerate(uploads):
        name = safe_filename(filename)
        stored = f"files/{index:04d}-{name}"
        written = 0
        with (folder.parent / stored).open("wb") as out:
            while chunk := stream.read(1024 * 1024):
                written += len(chunk)
                if written <= max_bytes:
                    out.write(chunk)
        rel = (rel_path or name).replace("\\", "/").lstrip("/")
        files.append(
            asdict(IntakeFile(key=f"f{index}", name=name, path=rel, stored=stored, size=written))
        )
    _save_batch(
        settings,
        batch_id,
        {
            "batch_id": batch_id,
            "created_at": utcnow().isoformat(),
            "state": "staged",
            "files": files,
            "shelves": [],
        },
    )
    return batch_id, len(files)


def cancel_batch(settings: Settings, batch_id: str) -> None:
    shutil.rmtree(_batch_dir(settings, batch_id), ignore_errors=True)


def purge_stale_batches(settings: Settings, now: dt.datetime | None = None) -> int:
    root = settings.uploads_dir / "intake"
    if not root.exists():
        return 0
    now = now or utcnow()
    removed = 0
    for folder in root.iterdir():
        manifest = folder / "manifest.json"
        try:
            created = dt.datetime.fromisoformat(
                json.loads(manifest.read_text(encoding="utf-8"))["created_at"]
            )
        except (OSError, ValueError, KeyError):
            created = dt.datetime.fromtimestamp(folder.stat().st_mtime, dt.UTC)
        if created.tzinfo is None:
            created = created.replace(tzinfo=dt.UTC)
        if now - created > BATCH_TTL:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed


# --- Analysis -------------------------------------------------------------------


def _unit(vector) -> np.ndarray:
    v = np.asarray(vector, dtype=float)
    norm = np.linalg.norm(v)
    return v / norm if norm else v


class _Vocabulary:
    """Department and kind descriptions, embedded once per analysis."""

    def __init__(self, embed):
        self.dept_names = list(DEPARTMENTS)
        self.kind_names = list(KINDS)
        vectors = [_unit(v) for v in embed(list(DEPARTMENTS.values()) + list(KINDS.values()))]
        self.dept_vecs = np.array(vectors[: len(DEPARTMENTS)])
        self.kind_vecs = np.array(vectors[len(DEPARTMENTS) :])


def _best(names: list[str], vecs: np.ndarray, v: np.ndarray) -> str | None:
    sims = vecs @ v
    order = np.argsort(-sims)
    if len(order) > 1 and sims[order[0]] - sims[order[1]] < TAG_MARGIN:
        return None
    return names[order[0]]


def suggest_tags(
    name: str, path: str, text: str, vector: np.ndarray, vocab: _Vocabulary, known_tags: set[str]
) -> list[str]:
    """Folder, department, kind and validity tags; at most 5."""
    tags: list[str] = []
    parts = path.split("/")
    if len(parts) > 2:  # the first folder below the one picked ("Picked/HR/x.docx")
        tags.append(_slug(parts[1]))
    department = _best(vocab.dept_names, vocab.dept_vecs, vector)
    if department:
        tags.append(department)
    head = f"{name}\n{text[:EXCERPT_CHARS]}"
    kind = next(
        (k for k, pattern in KIND_KEYWORDS if pattern.search(name) or pattern.search(head)), None
    )
    kind = kind or _best(vocab.kind_names, vocab.kind_vecs, vector)
    if kind:
        tags.append(kind)
    quarter = QUARTER.search(head)
    if quarter:
        tags.append(f"q{quarter.group(1)}-{quarter.group(2)}")
    years = Counter(YEAR.findall(head))
    if years:
        tags.append(years.most_common(1)[0][0])
    # Prefer a spelling the library already uses (e.g. "HR" vs "hr").
    by_lower = {t.lower(): t for t in known_tags}
    out: list[str] = []
    for tag in tags:
        tag = by_lower.get(tag.lower(), tag)
        if tag and tag.lower() not in {t.lower() for t in out}:
            out.append(tag)
    return out[:5]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:30]


def _audience(tags: list[str], vector: np.ndarray, vocab: _Vocabulary) -> str:
    """'staff' or 'business': from the department tag, else from the
    closest department even when it was too close to call as a tag (hr vs
    operations are both staff)."""
    department = next((t for t in tags if t in AUDIENCE), None)
    if department is None:
        department = vocab.dept_names[int(np.argmax(vocab.dept_vecs @ vector))]
    return AUDIENCE[department]


def _ask_model(runtime, prompt: str) -> str | None:
    """The chat model's answer, or None if it fails or takes longer than
    NAMING_TIMEOUT_S (e.g. low memory). The slow call is abandoned, not
    awaited: its thread finishes on its own."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        llm = runtime.llm_client_for(runtime.settings.chat_model)
        return pool.submit(llm.generate, prompt, temperature=0.1, num_ctx=4096).result(
            timeout=NAMING_TIMEOUT_S
        )
    except FutureTimeout:
        return None
    except Exception:  # noqa: BLE001 - no model, Ollama down...: keyword names instead
        return None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _name_groups(
    runtime, groups: list[tuple[list[tuple[str, str]], list[str]]], taken: set[str]
) -> list[tuple[str, str, str]]:
    """(name, description, named_by) for each group of (file name, opening
    text) pairs and their tags. One chat-model call names all of them; a
    group the answer doesn't cover gets a keyword name from its tags."""
    blocks = []
    for number, (names_and_heads, _) in enumerate(groups, start=1):
        listing = "\n".join(f"  - {name}: {head[:160]!r}" for name, head in names_and_heads[:8])
        blocks.append(f"Shelf {number}:\n{listing}")
    prompt = (
        "You organise one company's documents into shelves (collections). For each shelf "
        "below, suggest a short name and a one-sentence description of what it holds.\n"
        "Each name is 1 to 3 lowercase English words joined with hyphens (letters and digits "
        "only), and every name is different.\n"
        'Reply with JSON only: {"shelves": [{"name": "employees-hr", "description": "..."}, ...]} '
        f"with exactly {len(groups)} entries, in order.\n\n" + "\n\n".join(blocks) + "\n"
    )
    answers: list = []
    answer = _ask_model(runtime, prompt)
    if answer:
        try:
            data = json.loads(re.search(r"\{.*\}", answer, re.S).group(0))
            answers = data.get("shelves", []) if isinstance(data, dict) else []
        except (AttributeError, ValueError):
            answers = []
    out = []
    for index, (_, tags) in enumerate(groups):
        entry = answers[index] if index < len(answers) and isinstance(answers[index], dict) else {}
        name = _slug(str(entry.get("name", "")))[:40]
        if SHELF_NAME.match(name):
            description = str(entry.get("description", "")).strip()[:200]
            out.append((_unique(name, taken), description, "model"))
            continue
        counts = Counter(t for t in tags if t in DEPARTMENTS)
        top = [t for t, _ in counts.most_common(2)] or ["documents"]
        description = "Documents about " + " and ".join(t.replace("-", " ") for t in top) + "."
        out.append((_unique("-".join(top), taken), description, "keywords"))
    return out


def _unique(name: str, taken: set[str]) -> str:
    candidate, n = name, 2
    while candidate in taken:
        candidate = f"{name}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def analyze_batch(db: Session, runtime, batch_id: str, progress=None) -> dict:
    """Fills in status, tags and a shelf suggestion for every staged file."""
    settings = runtime.settings
    manifest = load_batch(settings, batch_id)
    folder = _batch_dir(settings, batch_id)
    files = [IntakeFile(**f) for f in manifest["files"]]
    embedder = runtime.embedding_client_for(settings.embedding_model)
    vocab = _Vocabulary(embedder.embed)
    known_tags = {
        t for (tags,) in db.execute(select(Document.tags)) for t in (tags or "").split(",") if t
    }
    shelves = list(db.execute(select(Collection).where(Collection.is_active)).scalars())

    texts: dict[str, str] = {}
    vectors: dict[str, np.ndarray] = {}
    max_bytes = settings.max_upload_mb * 1024 * 1024
    for i, item in enumerate(files):  # check and parse; embed afterwards in batches
        if progress:
            progress(0.3 * i / max(len(files), 1))
        stored = folder / item.stored
        item.sha256 = file_store.hash_file(stored)
        check = service.check_uploads(
            db,
            None,
            [service.UploadCandidate(item.name, item.sha256, item.size)],
            max_bytes=max_bytes,
            supported_extensions=SUPPORTED_EXTENSIONS,
        )[0]
        item.status, item.message = check.status, check.message
        if check.status in ("unsupported", "empty", "too_large", "duplicate"):
            item.include = False
            continue
        try:
            text = service._parse(stored, settings).full_text  # noqa: SLF001 - same parser ingestion uses
        except Exception as exc:  # noqa: BLE001 - shown to the user, file left out
            item.status, item.message, item.include = (
                "unreadable",
                f"Couldn't read it: {exc}",
                False,
            )
            continue
        if not text.strip():
            item.status, item.message, item.include = (
                "empty",
                "No text could be read from it.",
                False,
            )
            continue
        texts[item.key] = text

    keys = list(texts)
    for start in range(0, len(keys), EMBED_BATCH):
        batch = keys[start : start + EMBED_BATCH]
        for key, vector in zip(
            batch, embedder.embed([texts[k][:EXCERPT_CHARS] for k in batch]), strict=True
        ):
            vectors[key] = _unit(vector)
        if progress:
            progress(0.3 + 0.4 * (start + len(batch)) / len(keys))
    for item in files:
        if item.key in vectors:
            item.tags = suggest_tags(
                item.name, item.path, texts[item.key], vectors[item.key], vocab, known_tags
            )

    suggested: list[SuggestedShelf] = [
        SuggestedShelf(ref=f"existing:{c.id}", name=c.name, existing=True, named_by="existing")
        for c in shelves
    ]
    unassigned = _match_existing(db, runtime, files, vectors, texts, shelves, embedder)
    if progress:
        progress(0.8)

    # Group the rest by audience into suggested new shelves; a subfolder's
    # files stay together, on its majority audience.
    by_key = {f.key: f for f in files}
    audience = {k: _audience(by_key[k].tags, vectors[k], vocab) for k in unassigned}
    folders: dict[str, list[str]] = {}
    for key in unassigned:
        parts = by_key[key].path.split("/")
        if len(parts) > 2:
            folders.setdefault(parts[1], []).append(key)
    for keys_in_folder in folders.values():
        majority = Counter(audience[k] for k in keys_in_folder).most_common(1)[0][0]
        for k in keys_in_folder:
            audience[k] = majority
    groups: dict[str, list[IntakeFile]] = {}
    for key in unassigned:
        groups.setdefault(audience[key], []).append(by_key[key])
    taken = {c.name for c in db.execute(select(Collection)).scalars()}
    ordered = [members for _, members in sorted(groups.items())]
    names = _name_groups(
        runtime,
        [
            ([(m.name, texts[m.key][:300]) for m in members], [t for m in members for t in m.tags])
            for members in ordered
        ],
        taken,
    )
    for group_no, (members, (name, description, named_by)) in enumerate(
        zip(ordered, names, strict=True), start=1
    ):
        ref = f"new:g{group_no}"
        suggested.append(
            SuggestedShelf(ref=ref, name=name, description=description, named_by=named_by)
        )
        for m in members:
            m.shelf = ref
            others = [x.name for x in members if x.key != m.key][:2]
            m.reason = (
                "Grouped with " + ", ".join(others) if others else "No existing shelf matches it"
            )

    manifest["files"] = [asdict(f) for f in files]
    manifest["shelves"] = [asdict(s) for s in suggested]
    manifest["state"] = "ready"
    _save_batch(settings, batch_id, manifest)
    return {"batch_id": batch_id, "files": len(files), "new_shelves": len(suggested) - len(shelves)}


def _match_existing(db, runtime, files, vectors, texts, shelves, default_embedder) -> list[str]:
    """Assigns files to existing shelves where they fit; returns the keys of
    files that fit none (to be grouped into new shelves)."""
    unassigned: list[str] = []
    if not shelves:
        return [f.key for f in files if f.include and f.key in vectors]

    # Same name on a shelf: that's where it belongs (it becomes a new version).
    names = {}
    for c in shelves:
        for doc in db.execute(
            select(Document).where(Document.collection_id == c.id, Document.trashed_at.is_(None))
        ).scalars():
            names.setdefault(doc.filename.lower(), (c, doc))

    fingerprints = {c.id: _shelf_fingerprints(db, runtime, c) for c in shelves}
    shelf_departments = {c.id: _majority_department(db, c) for c in shelves}
    embedders = {runtime.settings.embedding_model: default_embedder}

    for item in files:
        if not item.include or item.key not in vectors:
            continue
        if item.name.lower() in names:
            shelf, doc = names[item.name.lower()]
            item.shelf = f"existing:{shelf.id}"
            versions = len(
                list(
                    db.execute(
                        select(DocumentVersion.id).where(DocumentVersion.document_id == doc.id)
                    )
                )
            )
            item.status = "new_version"
            item.message = (
                f"A different version is already on shelf '{shelf.name}'. This becomes "
                f"v{versions + 1} and the active version; the old one is kept."
            )
            item.reason = f"Same name as a document on '{shelf.name}'"
            continue
        department = next((t for t in item.tags if t in DEPARTMENTS), None)
        scored = []
        for c in shelves:
            prints = fingerprints[c.id]
            if not prints:
                continue
            if c.embedding_model not in embedders:
                embedders[c.embedding_model] = runtime.embedding_client_for(c.embedding_model)
            vector = vectors[item.key]
            if c.embedding_model != runtime.settings.embedding_model:
                vector = _unit(
                    embedders[c.embedding_model].embed([texts[item.key][:EXCERPT_CHARS]])[0]
                )
            sims = sorted(((float(vector @ v), title) for title, v in prints), reverse=True)
            score = float(np.mean([s for s, _ in sims[:2]]))
            if department and shelf_departments[c.id] == department:
                score += DEPARTMENT_BONUS
            scored.append((score, c, sims[0][1]))
        if not scored:
            unassigned.append(item.key)
            continue
        scored.sort(key=lambda s: s[0], reverse=True)
        best_score, best, similar_to = scored[0]
        if best_score < SHELF_MATCH_MIN:
            unassigned.append(item.key)
            continue
        item.shelf = f"existing:{best.id}"
        item.reason = f"Similar to '{similar_to}' on '{best.name}'"
        if len(scored) > 1 and best_score - scored[1][0] < SHELF_MARGIN:
            item.confidence = "low"
            item.alternatives = [f"existing:{scored[1][1].id}"]
            item.reason += f" — but it also fits '{scored[1][1].name}'; please check"
    return unassigned


def _shelf_fingerprints(db, runtime, collection: Collection) -> list[tuple[str, np.ndarray]]:
    """One vector per active document: its first passage, which covers the
    same opening text an intake excerpt does."""
    active = {
        version_id: filename
        for version_id, filename in db.execute(
            select(Document.active_version_id, Document.filename).where(
                Document.collection_id == collection.id, Document.trashed_at.is_(None)
            )
        )
        if version_id
    }
    out = []
    for metadata, vector in runtime.vector_store.get_vectors(
        collection.chroma_collection, {"chunk_index": 0}
    ):
        filename = active.get(int(metadata.get("version_id", 0)))
        if filename:
            out.append((filename, _unit(vector)))
    return out


def _majority_department(db, collection: Collection) -> str | None:
    counts = Counter(
        t
        for (tags,) in db.execute(
            select(Document.tags).where(
                Document.collection_id == collection.id, Document.trashed_at.is_(None)
            )
        )
        for t in (tags or "").split(",")
        if t in DEPARTMENTS
    )
    return counts.most_common(1)[0][0] if counts else None


# --- Confirm ----------------------------------------------------------------------


@dataclass
class ConfirmedFile:
    key: str
    include: bool
    shelf: str  # "existing:<id>" or "new:<key>"
    tags: list[str]


def confirm_batch(
    db: Session,
    runtime,
    batch_id: str,
    new_shelves: dict[str, str],
    decisions: list[ConfirmedFile],
    enqueue,
) -> tuple[list[int], list[dict]]:
    """Creates the approved new shelves, then queues one ingest job per
    included file from its staged copy. Returns (job ids, created shelves)."""
    settings = runtime.settings
    manifest = load_batch(settings, batch_id)
    if manifest.get("state") != "ready":
        raise service.ConflictError("this batch hasn't been analyzed yet, or was already processed")
    files = {f["key"]: f for f in manifest["files"]}
    chosen = [d for d in decisions if d.include and d.key in files]
    used_refs = {d.shelf for d in chosen}

    for ref in used_refs:
        if re.fullmatch(r"existing:\d+", ref):
            shelf = service.get_collection(db, int(ref.split(":", 1)[1]))
            if not shelf.is_active:
                raise service.ConflictError(f"shelf '{shelf.name}' is a retired copy")
        elif ref.startswith("new:"):
            name = new_shelves.get(ref, "").strip().lower()
            if not SHELF_NAME.match(name):
                raise service.ConflictError(
                    f"'{name}' isn't a valid shelf name: use lowercase letters, digits, - and _"
                )
        else:
            raise service.ConflictError(f"unknown shelf {ref!r}")
    new_names = [new_shelves[r].strip().lower() for r in used_refs if r.startswith("new:")]
    if len(new_names) != len(set(new_names)):
        raise service.ConflictError("two new shelves have the same name: give each its own")
    for name in new_names:  # check all before creating any
        if service.get_active_collection(db, name) is not None:
            raise service.ConflictError(f"a shelf called '{name}' already exists: pick it instead")

    created: dict[str, Collection] = {}
    for ref in sorted(r for r in used_refs if r.startswith("new:")):
        created[ref] = service.create_collection(
            db,
            runtime.vector_store,
            name=new_shelves[ref].strip().lower(),
            embedding_model=settings.embedding_model,
            chunk_size_tokens=settings.chunk_size_tokens,
            chunk_overlap_pct=settings.chunk_overlap_pct,
        )

    folder = _batch_dir(settings, batch_id)
    job_ids = []
    for decision in chosen:
        item = files[decision.key]
        collection_id = (
            created[decision.shelf].id
            if decision.shelf in created
            else int(decision.shelf.split(":", 1)[1])
        )
        staging = settings.uploads_dir / uuid.uuid4().hex
        staging.mkdir(parents=True)
        target = staging / item["name"]
        shutil.move(str(folder / item["stored"]), target)
        tags = ",".join(t.strip() for t in decision.tags if t.strip() and "," not in t) or None
        job = enqueue(
            "ingest",
            {
                "staged_path": str(target),
                "filename": item["name"],
                "collection_id": collection_id,
                "tags": tags,
            },
        )
        job_ids.append(job.id)

    service.audit_event(
        db,
        "intake_confirm",
        "intake",
        None,
        f"{len(job_ids)} file(s) queued; new shelves: {', '.join(c.name for c in created.values()) or 'none'}",
    )
    cancel_batch(settings, batch_id)
    return job_ids, [{"ref": ref, "id": c.id, "name": c.name} for ref, c in created.items()]
