"""Citation repair (decision 0020): only the [n] markers change, and only on clear evidence.

The passages mirror the Phase 7 baseline failures on the demo company."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.retrieval.citation_repair import repair_citations
from app.retrieval.prompt import NOT_FOUND_PHRASE

CATALOG = "Opal Mist Swirl GB-1014 12mm retail $1.60 per bead. Desert Sand $0.70."
PRICING = "GB-1014 Opal Mist Swirl boutique $0.80-$0.88, large $0.64-$0.72."
SHIPPING = "Retail orders under $50 ship for $18 international. Breakage claims under 20 pieces."
QC_MANUAL = "One in 20 outbound orders is spot checked at random before it ships."
HOLIDAY = "This year the profit-sharing bonus is paid with the December 18 paycheck."
HANDBOOK = "Profit-sharing bonus: full-time staff, paid annually each February."


def test_a_number_only_another_passage_has_moves_the_citation():
    answer = "The retail price of the Opal Mist Swirl bead is $1.60 [1]."
    fixed = repair_citations(answer, [PRICING, CATALOG])
    assert fixed.text == "The retail price of the Opal Mist Swirl bead is $1.60 [2]."
    assert fixed.changes == [("[1]", "[2]")]


def test_a_claim_spans_the_sentences_before_its_marker():
    answer = "The retail price is $1.60. This information can be found in [1] under GB-1014."
    assert "[2]" in repair_citations(answer, [PRICING, CATALOG]).text


def test_a_citation_that_already_has_the_numbers_stays():
    answer = "The bonus is paid with the December 18 paycheck [1]."
    fixed = repair_citations(answer, [HOLIDAY, HANDBOOK])
    assert fixed.text == answer and not fixed.changed


def test_a_wrong_document_loses_to_the_one_that_has_the_figures():
    answer = "This year the bonus comes with the December 18 paycheck [2][3]."
    fixed = repair_citations(answer, [SHIPPING, HANDBOOK, CATALOG, HOLIDAY])
    assert fixed.text.endswith("paycheck [4].")


def test_more_shared_words_win_when_the_numbers_tie():
    answer = "Outbound orders are spot checked randomly, 1 in 20 outbound orders [1]."
    assert repair_citations(answer, [SHIPPING, QC_MANUAL]).text.endswith("orders [2].")


def test_an_out_of_range_number_is_replaced():
    answer = "Records are kept for 24 months. [7]"
    fixed = repair_citations(
        answer, ["Quality Register records are retained for 24 months.", PRICING]
    )
    assert fixed.text == "Records are kept for 24 months. [1]"


def test_a_section_title_used_as_a_citation_becomes_a_number():
    answer = (
        "Give 2 weeks' written notice for a voluntary resignation. [4. Separation of Employment]"
    )
    passages = [HANDBOOK, "Voluntary resignation: 2 weeks' written notice is requested."]
    assert repair_citations(answer, passages).text.endswith("resignation. [2]")


def test_a_weak_extra_marker_in_a_run_is_dropped():
    answer = "A batch of 501 to 1,200 pieces uses a sample of 50 pieces [1][2]."
    passages = ["Batch 501-1,200 pieces: sample size 50 pieces.", "Strategic Partner tier."]
    assert repair_citations(answer, passages).text.endswith("pieces [1].")


def test_uncited_last_sentence_gets_the_clearly_supporting_passage():
    answer = "The bonus is paid with the December 18 paycheck."
    assert repair_citations(answer, [HANDBOOK, HOLIDAY]).text == (
        "The bonus is paid with the December 18 paycheck [2]."
    )


def test_the_rest_of_a_cited_sentence_gets_nothing_added():
    answer = "- [2] states that heat-resistant gloves are required."
    passages = ["Heat-resistant gloves required.", "Heat-resistant gloves required at casting."]
    assert repair_citations(answer, passages).text == answer


def test_unclear_cases_are_left_alone():
    # No anchors at all, a tie, and an answer that is "not found".
    assert (
        repair_citations("See the sources [1].", [CATALOG, PRICING]).text == "See the sources [1]."
    )
    tie = "Opal Mist Swirl [2]."
    assert repair_citations(tie, [CATALOG, PRICING]).text == tie
    assert repair_citations(NOT_FOUND_PHRASE, [CATALOG]).text == NOT_FOUND_PHRASE
    assert repair_citations("Anything [1].", []).text == "Anything [1]."


def test_words_never_change():
    answer = "The retail price is **$1.60** [1]. Wholesale starts at $0.64 [2]."
    fixed = repair_citations(answer, [PRICING, CATALOG])
    strip = lambda text: "".join(c for c in text if c not in "[]0123456789")  # noqa: E731
    assert strip(fixed.text) == strip(answer)


# --- In the chat and in evaluation runs -------------------------------------------


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _two_documents(client):
    shelf = client.post("/api/collections", json={"name": "ops"}).json()["id"]
    for name, text in (("pricing.txt", PRICING), ("catalog.txt", CATALOG)):
        client.post(
            "/api/documents",
            files=[("files", (name, text.encode(), "text/plain"))],
            data={"collection_id": str(shelf)},
        )
        client.drain()
    return shelf


def _number_of(sources, filename):
    return next(s["rank"] for s in sources if s["filename"] == filename)


def test_chat_saves_the_answer_with_repaired_citations(client, runtime):
    shelf = _two_documents(client)
    question = "What is the retail price of Opal Mist Swirl GB-1014?"
    sources = client.post(
        "/api/retrieve", json={"question": question, "collection_id": shelf}
    ).json()
    pricing = _number_of(sources["chunks"], "pricing.txt")
    catalog = _number_of(sources["chunks"], "catalog.txt")
    runtime.fake_llm._responses.append(f"The retail price is $1.60 [{pricing}].")

    client.post("/api/chat", json={"question": question, "collection_id": shelf})
    session = client.get("/api/sessions").json()[0]
    answer = client.get(f"/api/sessions/{session['id']}").json()["messages"][-1]["content"]
    assert answer == f"The retail price is $1.60 [{catalog}]."


def test_an_eval_run_can_keep_the_models_citations(client, runtime):
    shelf = _two_documents(client)
    question = "What is the retail price of Opal Mist Swirl GB-1014?"
    sources = client.post(
        "/api/retrieve", json={"question": question, "collection_id": shelf}
    ).json()
    pricing = _number_of(sources["chunks"], "pricing.txt")
    eval_set = client.post(
        "/api/eval/sets/import",
        json={"name": "s", "cases": [{"question": question, "shelf": "ops",
                                       "sources": ["catalog.txt"], "facts": [["1.60"]]}]},
    ).json()  # fmt: skip

    passed = {}
    for repair in (True, False):
        runtime.fake_llm._responses.append(f"The retail price is $1.60 [{pricing}].")
        run = client.post(
            "/api/eval/runs",
            json={"eval_set_id": eval_set["id"], "answers": True, "repair_citations": repair},
        ).json()
        client.drain()
        detail = client.get(f"/api/eval/runs/{run['id']}").json()
        assert detail["config"]["repair_citations"] is repair
        passed[repair] = detail["results"][0]["passed"]
    assert passed == {True: True, False: False}
    assert "no citation repair" in client.get("/api/eval/runs").json()[0]["label"]
