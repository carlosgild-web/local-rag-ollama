"""Evaluation (Phase 7, decision 0019): scoring, golden sets, runs, comparison.

Runs use the fake runtime: fake embeddings (so vector ranks are arbitrary),
real FTS5 (so keyword ranks are real) and a fake LLM with canned replies.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AuditLog
from app.eval import judge, metrics
from app.eval import service as eval_service
from app.eval.metrics import CaseScore
from app.ingest.parsers import parse_file
from app.main import create_app
from app.retrieval.prompt import NOT_FOUND_PHRASE

# --- Scoring -------------------------------------------------------------------


def test_normalize_treats_dashes_accents_and_bold_alike():
    assert metrics.normalize("Approval takes **3–5** business  days") == (
        "approval takes 3-5 business days"
    )
    assert metrics.normalize("¿Cuántas semanas?") == "¿cuantas semanas?"


def test_missing_facts_needs_one_alternative_of_each_group():
    facts = [["6:00", "6 pm"], ["main floor"]]
    assert metrics.missing_facts("At 6 PM on the Main Floor [1].", facts) == []
    assert metrics.missing_facts("At 6 pm [1].", facts) == [["main floor"]]


def test_first_relevant_rank_and_cited_files():
    files = ["faq.txt", "policy.docx", "faq.txt"]
    assert metrics.first_relevant_rank(files, ["policy.docx"]) == 2
    assert metrics.first_relevant_rank(files, ["other.pdf"]) is None
    # [9] has no source and is left out; each file is listed once.
    assert metrics.cited_filenames("A [1]. B [3][9]. C [2, 1].", files) == [
        "faq.txt",
        "policy.docx",
    ]
    assert metrics.citations_on_target(["faq.txt"], ["faq.txt", "x.md"])
    assert not metrics.citations_on_target([], ["faq.txt"])
    assert not metrics.citations_on_target(["faq.txt", "policy.docx"], ["faq.txt"])


def test_case_passes_on_retrieval_alone_without_answers():
    hit = CaseScore(False, ["a.txt"], [], first_relevant_rank=5)
    miss = CaseScore(False, ["a.txt"], [], first_relevant_rank=6)
    trap = CaseScore(True, [], [])
    assert metrics.case_passed(hit, with_answers=False) is True
    assert metrics.case_passed(miss, with_answers=False) is False
    assert metrics.case_passed(trap, with_answers=False) is None


def test_case_passes_with_answers_only_when_facts_and_citations_are_right():
    good = CaseScore(
        False, ["a.txt"], [["16"]], not_found=False, missing_facts=[], cited_sources=["a.txt"]
    )
    wrong_file = CaseScore(
        False, ["a.txt"], [["16"]], not_found=False, missing_facts=[], cited_sources=["b.txt"]
    )
    said_not_found = CaseScore(False, ["a.txt"], [["16"]], not_found=True, missing_facts=[["16"]])
    trap_ok = CaseScore(True, [], [], not_found=True)
    trap_answered = CaseScore(True, [], [], not_found=False)
    assert metrics.case_passed(good, with_answers=True) is True
    assert metrics.case_passed(wrong_file, with_answers=True) is False
    assert metrics.case_passed(said_not_found, with_answers=True) is False
    assert metrics.case_passed(trap_ok, with_answers=True) is True
    assert metrics.case_passed(trap_answered, with_answers=True) is False


def test_summarize_reports_unmeasured_rates_as_none():
    cases = [
        CaseScore(False, ["a.txt"], [], first_relevant_rank=1, passed=True, variant_group="g"),
        CaseScore(False, ["a.txt"], [], first_relevant_rank=4, passed=True, variant_group="g"),
        CaseScore(False, ["a.txt"], [], first_relevant_rank=None, passed=False),
        CaseScore(True, [], []),
    ]
    totals = metrics.summarize(cases, with_answers=False)
    assert totals["answerable"] == 3 and totals["traps"] == 1
    assert totals["hit_rate_at_5"] == pytest.approx(2 / 3)
    assert totals["hit_rate_at_1"] == pytest.approx(1 / 3)
    assert totals["mrr"] == pytest.approx((1 + 0.25 + 0) / 3)
    assert totals["variant_rate"] == 1.0
    assert "trap_rate" not in totals  # answers weren't generated

    empty = metrics.summarize([], with_answers=True)
    assert empty["hit_rate_at_5"] is None and empty["trap_rate"] is None


def test_judge_verdicts():
    assert judge.parse_verdict("YES. Every fact is in source 1.")[0] == 1.0
    assert judge.parse_verdict("Partly - the email isn't in the sources.")[0] == 0.5
    assert judge.parse_verdict("no")[0] == 0.0
    assert judge.parse_verdict("I cannot tell.")[0] is None


# --- The demo golden set ----------------------------------------------------------


def test_demo_golden_set_facts_are_in_their_sources():
    """Every required fact must be in one of the case's expected files, or the
    golden set measures nothing (and a corpus edit would silently break it)."""
    data = json.loads(eval_service.DEMO_SET_PATH.read_text(encoding="utf-8"))
    demo_root = eval_service.DEMO_SET_PATH.parents[1] / "hilda-luna"
    texts = {
        path.name: metrics.normalize(parse_file(path).full_text)
        for path in demo_root.rglob("*")
        if path.is_file()
    }
    shelves = {path.name for path in demo_root.iterdir() if path.is_dir()}
    assert len(data["cases"]) >= 40
    for case in data["cases"]:
        assert case.get("shelf") is None or case["shelf"] in shelves, case["question"]
        for source in case.get("sources", []):
            assert source in texts, (case["question"], source)
        for group in case.get("facts", []):
            assert any(
                metrics.normalize(alt) in texts[source]
                for alt in group
                for source in case["sources"]
            ), (case["question"], group)


def test_demo_golden_set_loads_and_exports_the_same(db_session):
    eval_set = eval_service.load_demo_set(db_session)
    data = json.loads(eval_service.DEMO_SET_PATH.read_text(encoding="utf-8"))
    assert len(eval_set.cases) == len(data["cases"])
    exported = eval_service.export_set(db_session, eval_set.id)
    assert exported["cases"] == [
        {k: v for k, v in case.items() if v not in (None, [], False, "")} for case in data["cases"]
    ]
    with pytest.raises(eval_service.ConflictError):
        eval_service.load_demo_set(db_session)


# --- API: golden sets ----------------------------------------------------------------


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _shelf(client, name):
    response = client.post("/api/collections", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload(client, collection_id, filename, text):
    response = client.post(
        "/api/documents",
        files=[("files", (filename, text.encode(), "text/plain"))],
        data={"collection_id": str(collection_id)},
    )
    assert response.status_code == 202, response.text
    client.drain()


@pytest.fixture
def library(client):
    """Two shelves with three short documents."""
    hr = _shelf(client, "hr")
    support = _shelf(client, "support")
    _upload(client, hr, "pto.txt", "Employees get sixteen PTO days in years three to five.")
    _upload(client, hr, "party.txt", "The holiday party starts at six on the main floor.")
    _upload(client, support, "faq.txt", "Custom bead colors need a minimum order of two kilograms.")
    return {"hr": hr, "support": support}


def _new_set(client, cases):
    response = client.post("/api/eval/sets/import", json={"name": "small", "cases": cases})
    assert response.status_code == 201, response.text
    return response.json()


CASES = [
    {"question": "How many PTO days in years three to five?", "shelf": "hr",
     "sources": ["pto.txt"], "facts": [["sixteen", "16"]]},
    {"question": "When does the holiday party start?", "shelf": "hr",
     "sources": ["party.txt"], "facts": [["six", "6"]]},
    {"question": "Minimum order for custom bead colors?", "shelf": "support",
     "sources": ["faq.txt"], "facts": [["two kilograms", "2 kg"]]},
    {"question": "What dental insurance do employees get?", "shelf": "hr", "not_found": True},
]  # fmt: skip


def test_golden_set_editing_is_validated_and_audited(client, runtime):
    created = client.post("/api/eval/sets", json={"name": "mine", "description": "d"})
    assert created.status_code == 201
    set_id = created.json()["id"]
    assert client.post("/api/eval/sets", json={"name": "mine"}).status_code == 409

    case = client.post(
        f"/api/eval/sets/{set_id}/cases",
        json={"question": " PTO? ", "shelf": "hr", "required_facts": [["16", " "], []]},
    )
    assert case.status_code == 201
    assert case.json()["question"] == "PTO?"
    assert case.json()["required_facts"] == [["16"]]  # blanks dropped

    trap_with_facts = client.patch(
        f"/api/eval/cases/{case.json()['id']}", json={"expect_not_found": True}
    )
    assert trap_with_facts.status_code == 422

    patched = client.patch(
        f"/api/eval/cases/{case.json()['id']}", json={"variant_group": "pto", "kind": "table"}
    )
    assert patched.json()["variant_group"] == "pto"
    assert patched.json()["required_facts"] == [["16"]]  # untouched fields stay

    detail = client.get(f"/api/eval/sets/{set_id}").json()
    assert detail["case_count"] == 1 and detail["cases"][0]["kind"] == "table"

    exported = client.get(f"/api/eval/sets/{set_id}/export")
    assert exported.headers["content-disposition"].endswith('mine.json"')
    assert exported.json()["cases"] == [
        {"question": "PTO?", "shelf": "hr", "kind": "table", "group": "pto", "facts": [["16"]]}
    ]

    assert client.delete(f"/api/eval/cases/{case.json()['id']}").status_code == 204
    assert client.delete(f"/api/eval/sets/{set_id}").status_code == 204
    with runtime.session_factory() as db:
        actions = [a.action for a in db.execute(select(AuditLog)).scalars()]
    for action in (
        "eval_set_create",
        "eval_case_create",
        "eval_case_update",
        "eval_case_delete",
        "eval_set_delete",
    ):
        assert action in actions


def test_import_names_the_bad_case(client):
    response = client.post(
        "/api/eval/sets/import",
        json={"name": "bad", "cases": [{"question": "ok"}, {"question": "x", "answer": "y"}]},
    )
    assert response.status_code == 422
    assert "case 2" in response.json()["detail"]
    assert client.get("/api/eval/sets").json() == []  # nothing half-imported


def test_demo_set_endpoint(client):
    status = client.get("/api/eval/demo").json()
    assert status == {"available": True, "loaded_set_id": None}
    loaded = client.post("/api/eval/demo")
    assert loaded.status_code == 201
    assert client.get("/api/eval/demo").json()["loaded_set_id"] == loaded.json()["id"]
    assert client.post("/api/eval/demo").status_code == 409


# --- API: runs -----------------------------------------------------------------------


def _run(client, body):
    response = client.post("/api/eval/runs", json=body)
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending"
    client.drain()
    return client.get(f"/api/eval/runs/{response.json()['id']}").json()


def test_retrieval_run_scores_hits_and_records_the_index(client, library):
    eval_set = _new_set(client, CASES)
    run = _run(client, {"eval_set_id": eval_set["id"], "mode": "keyword"})

    assert run["status"] == "completed" and run["progress"] == 1.0
    assert run["config"]["mode"] == "keyword" and run["config"]["answers"] is False
    assert run["label"].startswith("keyword, k=5, default v1")
    totals = run["metrics"]
    assert totals["cases"] == 4 and totals["answerable"] == 3 and totals["traps"] == 1
    assert totals["hit_rate_at_5"] == 1.0  # keyword search finds every document
    assert totals["mrr"] == 1.0
    assert "answered_rate" not in totals

    by_question = {r["question"]: r for r in run["results"]}
    pto = by_question[CASES[0]["question"]]
    assert pto["first_relevant_rank"] == 1 and pto["passed"] is True
    assert pto["retrieved"][0]["filename"] == "pto.txt"
    assert pto["answer"] is None
    assert by_question[CASES[3]["question"]]["passed"] is None  # traps need answers

    shelves = {s["shelf"]: s for s in run["index_snapshot"]}
    assert set(shelves) == {"hr", "support"}
    assert shelves["hr"]["documents"] == 2 and shelves["hr"]["chunks"] >= 2


def test_answer_run_scores_facts_citations_traps_and_faithfulness(client, runtime, library):
    eval_set = _new_set(client, CASES)
    runtime.fake_llm._responses.extend(
        [
            "Employees get sixteen PTO days [1].",  # facts and citation right
            "YES. It's in source 1.",  # judge
            "It starts at six [2].",  # source 2 isn't party.txt
            "NO. Source 2 is about PTO.",
            NOT_FOUND_PHRASE,  # a real answer missed
            "Employees get full dental cover [1].",  # a trap answered anyway
            "PARTLY.",
        ]
    )
    run = _run(
        client, {"eval_set_id": eval_set["id"], "mode": "keyword", "answers": True, "judge": True}
    )
    assert run["status"] == "completed"
    results = [r for r in run["results"]]
    pto, party, faq, dental = results
    assert pto["passed"] is True and pto["faithfulness"] == 1.0
    assert pto["cited_sources"] == ["pto.txt"] and pto["citation_status"] == "ok"
    assert party["missing_facts"] == [] and party["passed"] is False  # wrong file cited
    assert faq["not_found"] is True and faq["faithfulness"] is None  # not judged
    assert dental["passed"] is False and dental["not_found"] is False

    totals = run["metrics"]
    assert totals["answered_rate"] == pytest.approx(2 / 3)
    assert totals["facts_rate"] == pytest.approx(2 / 3)
    assert totals["trap_rate"] == 0.0
    assert totals["citation_rate"] == pytest.approx(1 / 2)
    assert totals["faithfulness"] == pytest.approx((1 + 0 + 0.5) / 3)
    assert totals["pass_rate"] == pytest.approx(1 / 4)

    prompt = runtime.fake_llm.calls[0]
    assert "How many PTO days" in prompt and "Cite the sources" in prompt  # the chat prompt


def test_run_rules(client, library):
    eval_set = _new_set(client, CASES)
    judge_only = client.post("/api/eval/runs", json={"eval_set_id": eval_set["id"], "judge": True})
    assert judge_only.status_code == 422
    too_many = client.post("/api/eval/runs", json={"eval_set_id": eval_set["id"], "top_k": 99})
    assert too_many.status_code == 422
    assert client.post("/api/eval/runs", json={"eval_set_id": 999}).status_code == 404

    first = client.post("/api/eval/runs", json={"eval_set_id": eval_set["id"]}).json()
    second = client.post("/api/eval/runs", json={"eval_set_id": eval_set["id"]})
    assert second.status_code == 409  # one run at a time
    assert client.delete(f"/api/eval/runs/{first['id']}").status_code == 409
    assert client.delete(f"/api/eval/sets/{eval_set['id']}").status_code == 409

    assert client.post(f"/api/jobs/{first['job_id']}/cancel").status_code == 200
    assert client.get(f"/api/eval/runs/{first['id']}").json()["status"] == "cancelled"
    assert client.delete(f"/api/eval/runs/{first['id']}").status_code == 204


def test_an_interrupted_cli_run_does_not_block_new_runs(client, runtime, library):
    eval_set = _new_set(client, CASES)
    with runtime.session_factory() as db:
        cli_run = eval_service.start_run(db, runtime.settings, eval_set["id"], queue_job=False)
        cli_run_id = cli_run.id  # never executed: as if the CLI was stopped mid-run
    assert client.get(f"/api/eval/runs/{cli_run_id}").json()["status"] == "cancelled"
    assert _run(client, {"eval_set_id": eval_set["id"]})["status"] == "completed"
    assert client.delete(f"/api/eval/runs/{cli_run_id}").status_code == 204


def test_a_case_on_a_missing_shelf_is_an_error_not_a_crash(client, library):
    eval_set = _new_set(client, [{"question": "Anything?", "shelf": "nope", "sources": ["x.txt"]}])
    run = _run(client, {"eval_set_id": eval_set["id"]})
    assert run["status"] == "completed"
    assert run["results"][0]["error"] == "no shelf named 'nope'"
    assert run["metrics"]["errors"] == 1 and run["metrics"]["hit_rate_at_5"] is None


def test_all_shelves_case_searches_every_shelf(client, library):
    eval_set = _new_set(
        client, [{"question": "custom bead colors minimum order", "sources": ["faq.txt"]}]
    )
    run = _run(client, {"eval_set_id": eval_set["id"], "mode": "keyword"})
    assert run["results"][0]["first_relevant_rank"] == 1


def test_compare_runs_case_by_case_and_notices_index_changes(client, library):
    eval_set = _new_set(client, CASES)
    keyword = _run(client, {"eval_set_id": eval_set["id"], "mode": "keyword"})
    again = _run(client, {"eval_set_id": eval_set["id"], "mode": "keyword"})

    same = client.get(f"/api/eval/compare?a={keyword['id']}&b={again['id']}").json()
    assert same["same_index"] is True
    assert {row["change"] for row in same["cases"]} == {"same"}

    _upload(client, library["hr"], "pto.txt", "Employees get twenty PTO days after six years.")
    edited = _run(client, {"eval_set_id": eval_set["id"], "mode": "keyword"})
    changed = client.get(f"/api/eval/compare?a={keyword['id']}&b={edited['id']}").json()
    assert changed["same_index"] is False  # a new version of pto.txt is active

    runs = client.get(f"/api/eval/runs?eval_set_id={eval_set['id']}").json()
    assert [r["id"] for r in runs] == [edited["id"], again["id"], keyword["id"]]


def test_editing_a_case_later_leaves_old_results_alone(client, library):
    eval_set = _new_set(client, CASES[:1])
    run = _run(client, {"eval_set_id": eval_set["id"], "mode": "keyword"})
    case_id = client.get(f"/api/eval/sets/{eval_set['id']}").json()["cases"][0]["id"]
    client.patch(f"/api/eval/cases/{case_id}", json={"question": "Something else?"})
    assert client.delete(f"/api/eval/cases/{case_id}").status_code == 204
    result = client.get(f"/api/eval/runs/{run['id']}").json()["results"][0]
    assert result["question"] == CASES[0]["question"] and result["eval_case_id"] is None


# --- Retrieval modes ------------------------------------------------------------------


def test_vector_mode_skips_keywords_and_keyword_mode_skips_vectors(runtime, monkeypatch):
    from app.retrieval import retrieve as retrieve_module

    calls = []
    real_fts, real_vec = retrieve_module._fts_candidate_ids, retrieve_module._vector_candidate_ids
    monkeypatch.setattr(
        retrieve_module,
        "_fts_candidate_ids",
        lambda *a, **k: calls.append("fts") or real_fts(*a, **k),
    )
    monkeypatch.setattr(
        retrieve_module,
        "_vector_candidate_ids",
        lambda *a, **k: calls.append("vector") or real_vec(*a, **k),
    )
    with runtime.session_factory() as db:
        shelf = eval_service.service.create_collection(
            db, runtime.vector_store, name="s", embedding_model="fake"
        )
        for mode, expected in (("hybrid", ["vector", "fts"]), ("vector", ["vector"]),
                               ("keyword", ["fts"])):  # fmt: skip
            calls.clear()
            retrieve_module.retrieve_many(
                db,
                "anything",
                collections=[shelf],
                settings=runtime.settings,
                embedding_client_for=runtime.embedding_client_for,
                vector_store=runtime.vector_store,
                mode=mode,
            )
            assert calls == expected, mode
        with pytest.raises(ValueError):
            retrieve_module.retrieve_many(
                db,
                "x",
                collections=[shelf],
                settings=runtime.settings,
                embedding_client_for=runtime.embedding_client_for,
                vector_store=runtime.vector_store,
                mode="magic",
            )
