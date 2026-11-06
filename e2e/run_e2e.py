"""End-to-end test of the running app against the sample corpus.

Drives the real HTTP API (the same calls the web UI makes) with a real
Ollama, checks every answer against facts from e2e/scenario.json, and
writes a Markdown report plus raw JSON. Needs a running server on an empty
database; it never touches the app's files directly.

    backend/.venv/Scripts/python.exe e2e/run_e2e.py --run-dir backend/data/e2e-runs/run1
    ... --phases persistence_prepare        (then restart or kill the server)
    ... --phases persistence_verify report

Checks are "must" (app mechanics: ingestion, versioning, rollback, trash,
jobs, persistence; any failure exits non-zero) or "quality" (what the model
answers; reported as a pass rate). Every request carries an X-Request-ID,
so failures can be matched to server log lines (--server-log).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

E2E_DIR = Path(__file__).resolve().parent
CORPUS = E2E_DIR / "corpus"
NOT_FOUND = "not found in the documents"
CHAT_TIMEOUT = 420.0
JOB_TIMEOUT = 900.0

sys.path.insert(0, str(E2E_DIR))
import variants

PHASES = [
    "preflight",
    "collections",
    "ingest",
    "questions",
    "grounding",
    "versions",
    "new_documents",
    "edge_cases",
    "report",
]
EXTRA_PHASES = ["persistence_prepare", "persistence_verify", "ui"]  # "ui": recorded from the browser pass


# --- results ------------------------------------------------------------------


@dataclass
class Result:
    id: str
    phase: str
    title: str
    level: str  # "must" | "quality" | "info"
    passed: bool | None
    detail: str = ""
    question: str | None = None
    collection: str | None = None
    answer: str | None = None
    sources: list[str] = field(default_factory=list)
    seconds: float | None = None
    request_id: str | None = None
    cause: str | None = None  # for failed answers: retrieval miss / answer miss / app error
    expected: str | None = None


class Run:
    def __init__(self, base_url: str, run_dir: Path, server_log: Path | None):
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0)
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.server_log = server_log
        self.results_path = run_dir / "results.json"
        self.state_path = run_dir / "state.json"
        self.calls_path = run_dir / "calls.jsonl"
        self.results: list[dict] = (
            json.loads(self.results_path.read_text(encoding="utf-8")) if self.results_path.exists() else []
        )
        self.state: dict = (
            json.loads(self.state_path.read_text(encoding="utf-8"))
            if self.state_path.exists()
            else {"messages": {}, "documents": {}}
        )
        self._seq = 0
        self.phase = "?"
        self.resume = False
        self._tag = time.strftime("%H%M%S")

    # persistence of results between invocations
    def add(self, result: Result) -> Result:
        self.results = [r for r in self.results if r["id"] != result.id]
        self.results.append(asdict(result))
        self.results_path.write_text(json.dumps(self.results, indent=2, ensure_ascii=False), "utf-8")
        mark = {True: "PASS", False: "FAIL", None: "INFO"}[result.passed]
        print(f"  [{mark}] {result.id}: {result.title}  {result.detail[:120]}", flush=True)
        return result

    def save_state(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), "utf-8")

    # HTTP with request ids and a call log
    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        self._seq += 1
        request_id = f"e2e-{self._tag}-{self.phase}-{self._seq}"
        headers = {**kwargs.pop("headers", {}), "X-Request-ID": request_id}
        started = time.perf_counter()
        error = None
        try:
            response = self.client.request(method, path, headers=headers, **kwargs)
            status = response.status_code
        except httpx.HTTPError as exc:
            error, status, response = f"{type(exc).__name__}: {exc}", None, None
        self._log_call(request_id, method, path, status, started, error)
        if response is None:
            raise RuntimeError(f"{method} {path} failed: {error}")
        return response

    def _log_call(self, request_id, method, path, status, started, error) -> None:
        entry = {
            "request_id": request_id,
            "phase": self.phase,
            "method": method,
            "path": path,
            "status": status,
            "ms": round((time.perf_counter() - started) * 1000),
            "error": error,
        }
        with self.calls_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def json(self, method: str, path: str, **kwargs):
        response = self.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:300]}")
        return None if response.status_code == 204 else response.json()

    # --- app helpers -----------------------------------------------------------

    def collection_id(self, name: str) -> int:
        for c in self.json("GET", "/api/collections"):
            if c["name"] == name and c["is_active"]:
                return c["id"]
        raise RuntimeError(f"no active collection named {name!r}")

    def upload(self, paths: list[Path], collection: str, tags: str | None = None) -> list[int]:
        files = [("files", (p.name, p.read_bytes())) for p in paths]
        data = {"collection_id": str(self.collection_id(collection))}
        if tags:
            data["tags"] = tags
        body = self.json("POST", "/api/documents", files=files, data=data)
        return [j["job_id"] for j in body["jobs"]]

    def job(self, job_id: int) -> dict:
        for j in self.json("GET", "/api/jobs", params={"limit": 500}):
            if j["id"] == job_id:
                return j
        raise RuntimeError(f"job {job_id} not found")

    def wait_job(self, job_id: int, timeout: float = JOB_TIMEOUT) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            j = self.job(job_id)
            if j["status"] in ("completed", "failed", "cancelled"):
                return j
            time.sleep(2)
        return self.job(job_id)

    def documents(self, **params) -> list[dict]:
        return self.json("GET", "/api/documents", params={"limit": 500, **params})

    def document(self, filename: str, trashed: bool = False) -> dict | None:
        return next((d for d in self.documents(trashed=trashed) if d["filename"] == filename), None)

    def chat(self, question: str, collection: str | int, session_id: int | None = None) -> dict:
        cid = collection if isinstance(collection, int) else self.collection_id(collection)
        self._seq += 1
        request_id = f"e2e-{self._tag}-{self.phase}-{self._seq}"
        out = {"answer": "", "sources": [], "error": None, "done": None, "request_id": request_id}
        started = time.perf_counter()
        status = None
        try:
            with self.client.stream(
                "POST",
                "/api/chat",
                json={"question": question, "collection_id": cid, "session_id": session_id},
                headers={"X-Request-ID": request_id},
                timeout=CHAT_TIMEOUT,
            ) as response:
                status = response.status_code
                if status >= 400:
                    response.read()
                    out["error"] = f"HTTP {status}: {response.text[:300]}"
                else:
                    for event, data in _sse_events(response.iter_lines()):
                        if event == "session":
                            out["session_id"] = data["session_id"]
                        elif event == "sources":
                            out["sources"] = data
                        elif event == "token":
                            out["answer"] += data["text"]
                        elif event == "done":
                            out["done"] = data
                        elif event == "error":
                            out["error"] = data["detail"]
        except httpx.HTTPError as exc:
            out["error"] = f"{type(exc).__name__}: {exc}"
        out["seconds"] = round(time.perf_counter() - started, 1)
        self._log_call(request_id, "POST", "/api/chat", status, started, out["error"])
        return out

    def retrieve_texts(self, question: str, collection: str) -> list[dict]:
        body = self.json(
            "POST",
            "/api/retrieve",
            json={"question": question, "collection_id": self.collection_id(collection)},
        )
        return body["chunks"]


def _sse_events(lines):
    event, data = "message", []
    for line in lines:
        if line == "":
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield event, json.loads("\n".join(data))


# --- answer checks ------------------------------------------------------------


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text.lower())
    text = text.replace("\u00a0", " ").replace("**", "")
    return re.sub(r"\s+", " ", text)


def missing_groups(answer: str, expect: list[list[str]]) -> list[list[str]]:
    norm = normalize(answer)
    return [g for g in expect if not any(normalize(alt) in norm for alt in g)]


def is_not_found(answer: str) -> bool:
    return NOT_FOUND in normalize(answer)


def cited_files(sources: list[dict]) -> list[str]:
    return [s.get("filename") or "?" for s in sources]


def describe_expect(expect: list[list[str]]) -> str:
    return " AND ".join(" / ".join(g) for g in expect)


def ask_and_check(
    run: Run,
    *,
    id: str,
    title: str,
    question: str,
    collection: str,
    expect: list[list[str]] | None = None,
    source: str | None = None,
    not_found: bool = False,
    forbid: list[str] | None = None,
    session_id: int | None = None,
    level: str = "quality",
) -> tuple[Result, dict]:
    out = run.chat(question, collection, session_id)
    answer = out["answer"]
    files = cited_files(out["sources"])
    problems = []
    cause = None

    if out["error"]:
        problems.append(f"stream error: {out['error']}")
        cause = "app error"
    elif not_found:
        if not is_not_found(answer):
            problems.append("expected 'not found in the documents'")
    else:
        missing = missing_groups(answer, expect or [])
        if missing:
            problems.append(f"missing: {describe_expect(missing)}")
        if source and Path(source).name not in [Path(f).name for f in files]:
            problems.append(f"{source} not among sources")
        if is_not_found(answer):
            problems.append("answered 'not found'")
        if not re.search(r"\[\d+", answer):
            problems.append("no [n] citation")
    for word in forbid or []:
        if word in normalize(answer):
            problems.append(f"contains forbidden {word!r}")

    if problems and cause is None and expect and not not_found:
        chunks = run.retrieve_texts(question, collection)
        found = [g for g in expect if any(normalize(a) in normalize(c["text"]) for c in chunks for a in g)]
        cause = "answer miss" if len(found) == len(expect) else "retrieval miss"

    result = run.add(
        Result(
            id=id,
            phase=run.phase,
            title=title,
            level="must" if out["error"] else level,
            passed=not problems,
            detail="; ".join(problems) or "ok",
            question=question,
            collection=collection,
            answer=answer.strip() or out["error"],
            sources=files,
            seconds=out["seconds"],
            request_id=out["request_id"],
            cause=cause,
            expected=("not found in the documents" if not_found else describe_expect(expect or [])),
        )
    )
    return result, out


def must(run: Run, id: str, title: str, ok: bool, detail: str = "") -> bool:
    run.add(Result(id=id, phase=run.phase, title=title, level="must", passed=bool(ok), detail=detail))
    return bool(ok)


def info(run: Run, id: str, title: str, detail: str) -> None:
    run.add(Result(id=id, phase=run.phase, title=title, level="info", passed=None, detail=detail))


def scenario() -> dict:
    return json.loads((E2E_DIR / "scenario.json").read_text(encoding="utf-8"))


# --- phases -------------------------------------------------------------------


def phase_preflight(run: Run, s: dict) -> None:
    health = run.request("GET", "/health").json()
    must(run, "pre-01", "Health is ok", health["status"] == "ok", json.dumps(health))
    docs = run.documents() + run.documents(trashed=True)
    must(run, "pre-02", "Database starts empty", not docs, f"{len(docs)} documents present")


def phase_collections(run: Run, s: dict) -> None:
    for name in s["collections"]:
        response = run.request("POST", "/api/collections", json={"name": name})
        must(
            run, f"col-{name}", f"Create collection {name}", response.status_code == 201, f"HTTP {response.status_code}"
        )
    duplicate = run.request("POST", "/api/collections", json={"name": "hr"})
    must(
        run,
        "col-dup",
        "Duplicate collection name is refused (409)",
        duplicate.status_code == 409,
        f"HTTP {duplicate.status_code}",
    )


def phase_ingest(run: Run, s: dict) -> None:
    for name, files in s["collections"].items():
        paths = [CORPUS / f for f in files]
        started = time.perf_counter()
        job_ids = run.upload(paths, name, tags=f"e2e,{name}")
        jobs = [run.wait_job(j) for j in job_ids]
        seconds = round(time.perf_counter() - started, 1)
        for path, job in zip(paths, jobs, strict=True):
            result = job.get("result") or {}
            ok = job["status"] == "completed" and result.get("status") == "ingested"
            must(
                run,
                f"ing-{path.name}",
                f"Ingest {path.name} into {name}",
                ok,
                f"{job['status']}, {result.get('chunk_count')} chunks"
                + (f", error: {job['error']}" if job["error"] else ""),
            )
            if ok:
                run.state["documents"][path.name] = result["document_id"]
        info(run, f"ing-time-{name}", f"Ingest time for {name}", f"{len(paths)} files in {seconds}s")
    run.save_state()

    chunks = run.retrieve_texts("supplier agreement number", "suppliers-quality")
    must(
        run,
        "ing-docx-table",
        "Word table text is indexed (agreement number)",
        any("XA-2026-014" in c["text"] for c in chunks),
    )
    pdf_pages = [c["page"] for c in run.retrieve_texts("holiday closure", "hr") if c["filename"].endswith(".pdf")]
    must(
        run, "ing-pdf-pages", "PDF chunks keep page numbers", bool(pdf_pages) and all(pdf_pages), f"pages: {pdf_pages}"
    )
    hr = run.documents(collection_id=run.collection_id("hr"))
    must(run, "ing-tags", "Upload tags are stored", all("e2e" in d["tags"] for d in hr), f"{[d['tags'] for d in hr]}")


def phase_questions(run: Run, s: dict) -> None:
    for q in s["questions"]:
        if run.resume and any(r["id"] == q["id"] for r in run.results):
            continue  # answered in an earlier, interrupted invocation
        _, out = ask_and_check(
            run,
            id=q["id"],
            title=f"[{q['kind']}] {q['source']}",
            question=q["question"],
            collection=q["collection"],
            expect=q["expect"],
            source=q["source"],
        )
        if out.get("done"):
            run.state["messages"][q["id"]] = {
                "session_id": out.get("session_id"),
                "message_id": out["done"]["message_id"],
                "sources": out["sources"],
            }
            run.save_state()  # per question, so an interrupted run can resume
        if q.get("note"):
            info(run, f"{q['id']}-note", f"Note for {q['id']}", q["note"])
    run.save_state()


def phase_grounding(run: Run, s: dict) -> None:
    for g in s["grounding"]:
        if run.resume and any(r["id"] == g["id"] for r in run.results):
            continue
        ask_and_check(
            run,
            id=g["id"],
            title=f"[{g['kind']}] must answer 'not found'",
            question=g["question"],
            collection=g["collection"],
            not_found=True,
        )


def phase_versions(run: Run, s: dict) -> None:
    built = variants.build(run.run_dir / "work")
    run.state["variants"] = built
    run.save_state()

    jobs_before = len(run.json("GET", "/api/jobs", params={"limit": 500}))
    for edit in s["edits"]:
        name = Path(edit["file"]).name
        before = run.document(name)
        [job_id] = run.upload([Path(built["edited"][edit["file"]])], edit["collection"])
        job = run.wait_job(job_id)
        after = run.document(name)
        result = job.get("result") or {}
        must(
            run,
            f"ver-{name}",
            f"Re-upload of edited {name} becomes version 2",
            job["status"] == "completed"
            and result.get("status") == "ingested"
            and after is not None
            and before is not None
            and after["id"] == before["id"]
            and after["version_count"] == 2
            and after["active_version_number"] == 2,
            f"job {job['status']} {result}, versions {after and after['version_count']}, "
            f"active v{after and after['active_version_number']}",
        )
        ask = edit["ask"]
        ask_and_check(
            run,
            id=ask["id"],
            title=f"Answer uses the edited {name}",
            question=ask["question"],
            collection=edit["collection"],
            expect=ask["expect"],
            source=name,
            forbid=[ask["old"]],
        )
        if ask.get("note"):
            info(run, f"{ask['id']}-note", f"Note for {ask['id']}", ask["note"])
    jobs_after_uploads = len(run.json("GET", "/api/jobs", params={"limit": 500}))

    # Old answers keep exactly the sources they were given.
    saved = run.state["messages"].get("sq-01")
    if saved:
        session = run.json("GET", f"/api/sessions/{saved['session_id']}")
        message = next(m for m in session["messages"] if m["id"] == saved["message_id"])
        then = [(x["chunk_id"], x["rank"]) for x in saved["sources"]]
        now = [(x["chunk_id"], x["rank"]) for x in message["sources"]]
        must(
            run,
            "ver-history",
            "Old answer keeps its original sources after a new version",
            then == now and "xa-2026-014" in normalize(message["content"]),
            f"then {then}, now {now}",
        )

    # Rollback one document: pointer flips, no job, no re-embedding.
    edit = next(e for e in s["edits"] if "rollback" in e)
    name = Path(edit["file"]).name
    doc = run.document(name)
    versions = run.json("GET", f"/api/documents/{doc['id']}/versions")
    v1 = next(v for v in versions if v["version_number"] == 1)
    started = time.perf_counter()
    rolled = run.json("POST", f"/api/documents/{doc['id']}/rollback", json={"version_id": v1["id"]})
    seconds = round(time.perf_counter() - started, 2)
    jobs_after_rollback = len(run.json("GET", "/api/jobs", params={"limit": 500}))
    doc = run.document(name)
    must(
        run,
        "rb-pointer",
        f"Rollback of {name} to v1 flips the active version",
        doc["active_version_number"] == 1 and rolled["is_active"] and rolled["chunk_count"] > 0,
        f"active v{doc['active_version_number']}, v1 chunks {rolled['chunk_count']}, {seconds}s",
    )
    must(
        run,
        "rb-no-job",
        "Rollback queues no job (nothing re-embedded)",
        jobs_after_rollback == jobs_after_uploads,
        f"jobs {jobs_after_uploads} -> {jobs_after_rollback}",
    )
    diff = run.json(
        "GET",
        f"/api/documents/{doc['id']}/diff",
        params={"a": v1["id"], "b": next(v["id"] for v in versions if v["version_number"] == 2)},
    )
    must(
        run,
        "rb-diff",
        "Diff between versions shows the edit",
        any("45 days" in line for line in diff["diff"]),
        f"{len(diff['diff'])} diff lines",
    )
    rb = edit["rollback"]
    ask_and_check(
        run,
        id=rb["id"],
        title=f"After rollback the answer uses v1 of {name}",
        question=edit["ask"]["question"],
        collection=edit["collection"],
        expect=rb["expect"],
        source=name,
        forbid=["45 days"],
    )
    info(run, "ver-jobs", "Jobs created by the edit uploads", f"{jobs_after_uploads - jobs_before}")


def phase_new_documents(run: Run, s: dict) -> None:
    built = run.state.get("variants") or variants.build(run.run_dir / "work")
    new = {d["file"]: d for d in s["new_documents"]}

    # Two uploads back to back: the second waits behind the first, so it
    # can be cancelled while pending, then retried.
    [first] = run.upload(
        [Path(built["new"]["11-travel-expense-policy.md"])], new["11-travel-expense-policy.md"]["collection"]
    )
    [second] = run.upload(
        [Path(built["new"]["12-politica-de-garantia.md"])], new["12-politica-de-garantia.md"]["collection"]
    )
    cancelled = run.json("POST", f"/api/jobs/{second}/cancel")
    run.wait_job(first)
    second_job = run.wait_job(second, timeout=30)
    must(
        run,
        "job-cancel",
        "A pending job can be cancelled",
        second_job["status"] == "cancelled",
        f"after cancel: {cancelled['status']} (cancel_requested={cancelled['cancel_requested']}), final {second_job['status']}",
    )
    run.json("POST", f"/api/jobs/{second}/retry")
    retried = run.wait_job(second)
    must(
        run,
        "job-retry",
        "A cancelled job can be retried to completion",
        retried["status"] == "completed",
        f"{retried['status']} {retried.get('error') or ''}",
    )

    [third] = run.upload([Path(built["new"]["13-foundry-notes.txt"])], new["13-foundry-notes.txt"]["collection"])
    third_job = run.wait_job(third)
    must(
        run,
        "new-13",
        "Ingest 13-foundry-notes.txt",
        third_job["status"] == "completed",
        f"{third_job['status']} {third_job.get('error') or ''}",
    )
    must(run, "new-11", "Ingest 11-travel-expense-policy.md", run.job(first)["status"] == "completed")

    for doc in s["new_documents"]:
        for ask in doc["asks"]:
            ask_and_check(
                run,
                id=ask["id"],
                title=("[prompt injection] " if doc.get("injection") else "") + f"New document {doc['file']}",
                question=ask["question"],
                collection=doc["collection"],
                expect=ask.get("expect"),
                source=None if ask.get("not_found") else doc["file"],
                not_found=ask.get("not_found", False),
                forbid=ask.get("forbid"),
            )


def phase_edge_cases(run: Run, s: dict) -> None:
    # Same file again: skipped as a duplicate, no new version.
    [job_id] = run.upload([CORPUS / "01-product-catalog.pdf"], "sales-customers")
    job = run.wait_job(job_id)
    doc = run.document("01-product-catalog.pdf")
    must(
        run,
        "edge-dup",
        "Unchanged re-upload is skipped as a duplicate",
        (job.get("result") or {}).get("status") == "skipped_duplicate" and doc["version_count"] == 1,
        f"{job['status']} {job.get('result')}",
    )

    # Same file to another shelf: currently skipped without a message (known gap).
    [job_id] = run.upload([CORPUS / "CustomerSupport/08-customer-faq.txt"], "hr")
    job = run.wait_job(job_id)
    doc = run.document("08-customer-faq.txt")
    info(
        run,
        "edge-cross-shelf",
        "Upload of a file already on another shelf",
        f"job {job['status']}, result {job.get('result')}, document stays in collection "
        f"{doc['collection_id']} (sales-customers is {run.collection_id('sales-customers')}). "
        "Known gap: the user is not told the file was skipped.",
    )

    # Bad uploads are refused clearly.
    response = run.request(
        "POST",
        "/api/documents",
        files=[("files", ("photo.png", b"\x89PNG\r\n"))],
        data={"collection_id": str(run.collection_id("hr"))},
    )
    must(
        run,
        "edge-415",
        "Unsupported file type is refused with 415",
        response.status_code == 415,
        f"HTTP {response.status_code}: {response.text[:200]}",
    )
    response = run.request(
        "POST",
        "/api/documents",
        files=[("files", ("empty-note.txt", b""))],
        data={"collection_id": str(run.collection_id("hr"))},
    )
    if response.status_code == 202:
        job = run.wait_job(response.json()["jobs"][0]["job_id"])
        info(
            run,
            "edge-empty",
            "Empty .txt upload",
            f"job {job['status']}, result {job.get('result')}, error {job.get('error')}",
        )
    else:
        info(run, "edge-empty", "Empty .txt upload", f"HTTP {response.status_code}: {response.text[:200]}")
    health = run.request("GET", "/health").json()
    must(run, "edge-health", "Server healthy after bad uploads", health["status"] == "ok")

    # Trash: the document stops answering and is listed in the trash.
    qc = run.document("03-quality-control-manual.pdf")
    run.request("DELETE", f"/api/documents/{qc['id']}")
    trashed = run.document("03-quality-control-manual.pdf", trashed=True)
    must(run, "edge-trash-list", "Deleted document is listed in the trash", trashed is not None)
    _, out = ask_and_check(
        run,
        id="edge-trash-answer",
        title="Trashed document is no longer used for answers",
        question="How long are Quality Register records retained?",
        collection="suppliers-quality",
        not_found=True,
        level="quality",
    )
    must(
        run,
        "edge-trash-sources",
        "Trashed document is never cited",
        "03-quality-control-manual.pdf" not in cited_files(out["sources"]),
        f"sources: {cited_files(out['sources'])}",
    )

    # Reindex a cited document and a whole collection (bug fixed on 2026-11-06).
    sup = run.document("02-supplier-agreement.docx")
    job = run.wait_job(run.json("POST", f"/api/documents/{sup['id']}/reindex")["job_id"])
    must(
        run,
        "edge-reindex-doc",
        "Reindex a document that answers cite",
        job["status"] == "completed",
        f"{job['status']} {job.get('error') or ''}",
    )
    queued = run.json("POST", f"/api/collections/{run.collection_id('hr')}/reindex")
    job = run.wait_job(queued["job_id"])
    must(
        run,
        "edge-reindex-col",
        "Reindex a whole collection in place",
        job["status"] == "completed" and queued["mode"] == "in_place",
        f"{queued['mode']}, {job['status']} {job.get('error') or ''}",
    )
    ask_and_check(
        run,
        id="edge-after-reindex",
        title="Answers still work after reindex",
        question="When does the company close for the year-end holiday?",
        collection="hr",
        expect=[["december 19"]],
        source="05-holiday-announcement.pdf",
    )

    # Blue/green rebuild with smaller chunks.
    old_id = run.collection_id("sales-customers")
    queued = run.json("POST", f"/api/collections/{old_id}/reindex", json={"chunk_size_tokens": 300})
    job = run.wait_job(queued["job_id"])
    collections = run.json("GET", "/api/collections", params={"include_inactive": True})
    new = next((c for c in collections if c["name"] == "sales-customers" and c["is_active"]), None)
    old = next(c for c in collections if c["id"] == old_id)
    must(
        run,
        "edge-rebuild",
        "Changing chunk size rebuilds and swaps the collection",
        queued["mode"] == "blue_green"
        and job["status"] == "completed"
        and new is not None
        and new["id"] != old_id
        and new["chunk_size_tokens"] == 300
        and not old["is_active"],
        f"{queued['mode']}, job {job['status']}, new {new and new['id']} "
        f"({new and new['chunk_size_tokens']} tokens), old active={old['is_active']}",
    )
    ask_and_check(
        run,
        id="edge-after-rebuild",
        title="Answers work on the rebuilt collection",
        question="Which charm sold best in Q3 and how many units were sold?",
        collection="sales-customers",
        expect=[["crescent moon"], ["4,120", "4120"]],
        source="07-q3-2026-sales-meeting-notes.txt",
    )
    out = run.chat("What is the boutique price of the Amber Hollow Starter Set?", old_id)
    info(
        run,
        "edge-old-generation",
        "Asking a retired collection generation directly",
        f"error={out['error']}, answer={out['answer'][:160]!r}, sources={cited_files(out['sources'])}",
    )

    # Follow-up question in the same session (known limitation: no chat memory).
    _, first = ask_and_check(
        run,
        id="edge-followup-1",
        title="Follow-up setup question",
        question="What is the retail price of the Desert Sand Faceted bead?",
        collection="sales-customers",
        expect=[["1.00", "$1"]],
        source="01-product-catalog.pdf",
    )
    second = run.chat("And what is its wholesale price?", "sales-customers", first.get("session_id"))
    info(
        run,
        "edge-followup-2",
        "Follow-up 'And what is its wholesale price?' in the same session",
        f"answer={second['answer'][:200]!r}. Expected limitation: each question is answered on its own.",
    )

    # Feedback and audit.
    saved = run.state["messages"].get("hr-01")
    if saved:
        run.json("POST", f"/api/messages/{saved['message_id']}/feedback", json={"thumbs_up": True})
        session = run.json("GET", f"/api/sessions/{saved['session_id']}")
        message = next(m for m in session["messages"] if m["id"] == saved["message_id"])
        must(
            run,
            "edge-feedback",
            "Thumbs-up feedback is saved",
            (message.get("feedback") or {}).get("thumbs_up") is True,
        )
    actions = {a["action"] for a in run.json("GET", "/api/audit", params={"limit": 1000})}
    wanted = {"collection_create", "upload", "delete", "rollback", "reindex", "job_cancel", "job_retry"}
    must(
        run,
        "edge-audit",
        "Audit log records every kind of change",
        wanted <= actions,
        f"missing: {sorted(wanted - actions)}",
    )


def phase_persistence_prepare(run: Run, s: dict) -> None:
    snapshot = {
        "documents": sorted(d["filename"] for d in run.documents()),
        "trashed": sorted(d["filename"] for d in run.documents(trashed=True)),
        "sessions": len(run.json("GET", "/api/sessions", params={"limit": 200})),
    }
    path = run.run_dir / "work" / "14-restart-check.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "HILDA & LUNA BEADWORKS\nRESTART CHECK NOTE\n[Sample data]\nThe restart check code word is LAPISLAZULI.\n" * 40,
        encoding="utf-8",
    )
    [job_id] = run.upload([path], "hr")
    run.state["persistence"] = {"snapshot": snapshot, "job_id": job_id}
    run.save_state()
    info(
        run,
        "per-prepare",
        "Snapshot taken; restart-check upload queued",
        f"job {job_id}. Now kill the server and start it again.",
    )


def phase_persistence_verify(run: Run, s: dict) -> None:
    p = run.state["persistence"]
    snapshot = p["snapshot"]
    job = run.wait_job(p["job_id"])
    must(
        run,
        "per-job",
        "Job interrupted by the restart is recovered and completes",
        job["status"] == "completed",
        f"{job['status']} {job.get('error') or ''}",
    )
    documents = sorted(d["filename"] for d in run.documents())
    expected = sorted(snapshot["documents"] + ["14-restart-check.txt"])
    must(run, "per-docs", "Documents survive the restart", documents == expected, f"{len(documents)} documents")
    must(
        run,
        "per-trash",
        "Trash survives the restart",
        sorted(d["filename"] for d in run.documents(trashed=True)) == snapshot["trashed"],
    )
    sessions = len(run.json("GET", "/api/sessions", params={"limit": 200}))
    must(
        run,
        "per-sessions",
        "Chat history survives the restart",
        sessions == snapshot["sessions"],
        f"{sessions} sessions",
    )
    ask_and_check(
        run,
        id="per-answer",
        title="Answers work after the restart",
        question="What is the restart check code word?",
        collection="hr",
        expect=[["lapislazuli"]],
        source="14-restart-check.txt",
    )


# --- report -------------------------------------------------------------------


def _log_lines(server_log: Path | None, request_id: str | None) -> list[str]:
    if not server_log or not request_id or not server_log.exists():
        return []
    lines = []
    for line in server_log.read_text(encoding="utf-8", errors="replace").splitlines():
        if f'"request_id": "{request_id}"' in line and '"level": "INFO"' not in line:
            try:
                entry = json.loads(line)
                lines.append(
                    f"{entry.get('level')} {entry.get('logger')}: {entry.get('message')}"
                    + (f"\n{entry['exc_info'][-800:]}" if entry.get("exc_info") else "")
                )
            except ValueError:
                lines.append(line[:500])
    return lines


def citation_verdict(result: dict, source: str) -> str:
    """'correct' if a cited [n] is the expected document, else why not."""
    numbers = {int(n) for n in re.findall(r"\[(\d+)", result.get("answer") or "")}
    if not numbers:
        return "missing"
    sources = result.get("sources") or []
    cited = {Path(sources[n - 1]).name for n in numbers if 0 < n <= len(sources)}
    if Path(source).name in cited:
        return "correct"
    return "points elsewhere" if cited else "invalid number"


def _cell(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def phase_report(run: Run, s: dict) -> None:
    results = run.results
    order = {p: i for i, p in enumerate(PHASES + EXTRA_PHASES)}
    results.sort(key=lambda r: (order.get(r["phase"], 99), r["id"]))
    must_r = [r for r in results if r["level"] == "must"]
    qual = [r for r in results if r["level"] == "quality"]
    timed = [r["seconds"] for r in results if r["seconds"]]

    out = ["# End-to-end test report", ""]
    out.append(f"Run: `{run.run_dir.name}`, generated {time.strftime('%Y-%m-%d %H:%M')} local time.  ")
    out.append("Corpus: `e2e/corpus/` (fictional Hilda & Luna Beadworks sample data), scenario: `e2e/scenario.json`.")
    out += ["", "## Summary", "", "| Checks | Passed | Failed |", "|---|---|---|"]
    out.append(
        f"| Must pass (app mechanics) | {sum(r['passed'] for r in must_r)} | {sum(not r['passed'] for r in must_r)} |"
    )
    out.append(f"| Answer quality | {sum(r['passed'] for r in qual)} | {sum(not r['passed'] for r in qual)} |")
    if timed:
        out.append(
            f"\nAnswer time: median {sorted(timed)[len(timed) // 2]}s, max {max(timed)}s over {len(timed)} answers."
        )
    by_cause: dict[str, int] = {}
    for r in qual + must_r:
        if r["passed"] is False and r.get("cause"):
            by_cause[r["cause"]] = by_cause.get(r["cause"], 0) + 1
    if by_cause:
        out.append(
            "\nFailed answers by cause: "
            + ", ".join(f"{k}: {v}" for k, v in by_cause.items())
            + ". *Retrieval miss* means the fact was not in the passages found; "
            "*answer miss* means it was found but the model did not state it."
        )

    # Do the [n] markers point at the document that holds the answer?
    expected_source = {q["id"]: q["source"] for q in s["questions"]}
    for edit in s["edits"]:
        expected_source[edit["ask"]["id"]] = Path(edit["file"]).name
        if "rollback" in edit:
            expected_source[edit["rollback"]["id"]] = Path(edit["file"]).name
    citation = {r["id"]: citation_verdict(r, expected_source[r["id"]]) for r in results if r["id"] in expected_source}
    if citation:
        counts: dict[str, int] = {}
        for verdict in citation.values():
            counts[verdict] = counts.get(verdict, 0) + 1
        out.append(
            f"\nCitations ({len(citation)} answers that should cite a known document): "
            + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            + ". Invariant 6 makes citations mandatory."
        )

    for phase in PHASES + EXTRA_PHASES:
        rows = [r for r in results if r["phase"] == phase]
        if not rows:
            continue
        out += ["", f"## {phase.replace('_', ' ').title()}", ""]
        mech = [r for r in rows if r["question"] is None]
        asks = [r for r in rows if r["question"] is not None]
        if mech:
            out += ["| | Check | Detail |", "|---|---|---|"]
            for r in mech:
                mark = {True: "✅", False: "❌", None: "ℹ️"}[r["passed"]]
                out.append(f"| {mark} | {_cell(r['title'])} | {_cell(r['detail'])} |")
            out.append("")
        for r in asks:
            mark = "✅" if r["passed"] else "❌"
            out.append(f"**{mark} {r['id']}** · {r['title']} · shelf `{r['collection']}` · {r['seconds']}s")
            out.append(f"> **Q:** {r['question']}  ")
            out.append(f"> **A:** {_cell(r['answer'])}  ")
            out.append(
                f"> **Expected:** {_cell(r['expected'])} · **Sources:** {_cell(', '.join(r['sources']) or 'none')}"
            )
            if r["id"] in citation:
                out.append(f"> **Citation:** {citation[r['id']]}  ")
            if not r["passed"]:
                out.append(
                    f"> **Problem:** {_cell(r['detail'])}" + (f" · **Cause:** {r['cause']}" if r.get("cause") else "")
                )
            out.append("")

    errors = [r for r in results if r["passed"] is False and r.get("request_id")]
    calls = (
        [json.loads(x) for x in run.calls_path.read_text(encoding="utf-8").splitlines()]
        if run.calls_path.exists()
        else []
    )
    http_errors = [c for c in calls if c["error"] or (c["status"] or 0) >= 500]
    out += ["", "## Errors and server log excerpts", ""]
    if not errors and not http_errors:
        out.append("No request failed and no server errors were logged.")
    for c in http_errors:
        out.append(f"- `{c['request_id']}` {c['method']} {c['path']} → {c['status']} {c['error'] or ''}")
        for line in _log_lines(run.server_log, c["request_id"]):
            out.append(f"  ```\n  {line}\n  ```")
    for r in errors:
        lines = _log_lines(run.server_log, r["request_id"])
        if lines:
            out.append(f"- {r['id']} (`{r['request_id']}`):")
            out += [f"  ```\n  {line}\n  ```" for line in lines]

    out += [
        "",
        "## Known limitations (recorded, not failures)",
        "",
        "- A file already on another shelf is skipped as a duplicate without telling the user.",
        "- There is no restore-from-trash endpoint yet (Phase 5).",
        "- Each question is answered on its own; the chat does not use earlier turns.",
        (
            "- Answers come from `qwen2.5:3b` on a 7.2 GB RAM laptop (decision 0004); "
            "a 7B/8B model would answer more precisely and faster on better hardware."
        ),
    ]
    report = run.run_dir / "report.md"
    report.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nReport: {report}")


# --- main ---------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--server-log", type=Path, default=None)
    parser.add_argument("--resume", action="store_true", help="skip questions already answered in this run dir")
    parser.add_argument(
        "--phases", nargs="*", default=PHASES, help=f"phases to run, in order: {', '.join(PHASES + EXTRA_PHASES)}"
    )
    args = parser.parse_args()

    run = Run(args.base_url, args.run_dir, args.server_log)
    run.resume = args.resume
    s = scenario()
    for name in args.phases:
        run.phase = name
        print(f"\n== {name}", flush=True)
        try:
            globals()[f"phase_{name}"](run, s)
        except Exception as exc:  # noqa: BLE001 - record and stop: later phases need earlier ones
            must(run, f"{name}-crash", f"Phase {name} stopped with an exception", False, f"{type(exc).__name__}: {exc}")
            if name != "report":
                phase_report(run, s)
            return 2
    failed = [r for r in run.results if r["level"] == "must" and r["passed"] is False]
    print(f"\nMust-pass failures: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
