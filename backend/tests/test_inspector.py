"""The retrieval inspector (decision 0024): parameters, score breakdown,
prompt, and that its defaults match what the chat sends."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.retrieval import retrieve as retrieve_module
from app.retrieval.fusion import fuse_rrf_scored
from app.retrieval.inspector import QuestionEmbeddingCache
from app.retrieval.qa import prepare_context
from app.retrieval.reranker import Reranker
from app.versioning import profiles, service

QUESTION = "How often is the kiln checked?"


class Reverse(Reranker):
    """Reverses the order and scores by position, so the change is visible."""

    def rerank(self, question, chunks):
        n = len(chunks)
        return [replace(c, score=float(n - i)) for i, c in enumerate(reversed(chunks))]


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def shelf(runtime):
    with runtime.session_factory() as db:
        shelf = service.create_collection(
            db, runtime.vector_store, name="kiln", embedding_model="fake"
        )
        for i in range(12):
            text = f"Kiln note {i}: the kiln is checked weekly by shift {i}."
            path = runtime.settings.uploads_dir / f"note{i}.txt"
            path.write_text(text, encoding="utf-8")
            service.ingest_document(
                db,
                collection=shelf,
                source_path=path,
                settings=runtime.settings,
                embedding_client=runtime.embedding_client_for("fake"),
                vector_store=runtime.vector_store,
            )
        return shelf.id


def _inspect(client, shelf, **params):
    response = client.post(
        "/api/retrieve/inspect", json={"question": QUESTION, "collection_id": shelf, **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Fusion ----------------------------------------------------------------------


def test_weighted_rrf_scales_each_list():
    plain = dict(fuse_rrf_scored([[1, 2], [2, 3]]))
    weighted = dict(fuse_rrf_scored([[1, 2], [2, 3]], weights=[2.0, 0.0]))
    assert weighted[1] == pytest.approx(2 * plain[1])
    assert weighted[3] == 0.0
    assert dict(fuse_rrf_scored([[1, 2], [2, 3]], weights=[1.0, 1.0])) == plain
    with pytest.raises(ValueError):
        fuse_rrf_scored([[1]], weights=[1.0, 1.0])


# --- Defaults match the chat ----------------------------------------------------


def test_defaults_send_the_chats_chunks_and_prompt(client, runtime, shelf):
    body = _inspect(client, shelf)
    with runtime.session_factory() as db:
        profile = profiles.get_active_profile(db, runtime.settings)
        context = prepare_context(
            db,
            QUESTION,
            collection=service.get_collection(db, shelf),
            settings=runtime.settings,
            embedding_client=runtime.embedding_client_for("fake"),
            vector_store=runtime.vector_store,
            top_k=profile.retrieval_top_k,
            system_instructions=profile.system_prompt,
        )
    sent = [c for c in body["chunks"] if c["sent"]]
    assert [c["chunk_id"] for c in sent] == [c.chunk_id for c in context.chunks]
    assert body["prompt"] == context.prompt
    assert body["parameters"] == {
        "mode": "hybrid",
        "top_k": profile.retrieval_top_k,
        "candidates": runtime.settings.retrieval_candidates,
        "vector_weight": 0.5,
        "min_cosine": 0.0,
        "rerank": False,
    }
    assert body["profile_name"] == "default" and body["reranker_available"] is False


def test_shows_the_candidates_below_the_top_k_line(client, shelf):
    body = _inspect(client, shelf, top_k=3)
    assert len(body["chunks"]) == 12  # every note is a candidate
    assert [c["sent"] for c in body["chunks"]] == [True] * 3 + [False] * 9
    assert [c["rank"] for c in body["chunks"]] == list(range(1, 13))
    assert body["prompt"].count("[3]") >= 1 and "[4]" not in body["prompt"]


def test_each_chunk_explains_its_score(client, shelf):
    body = _inspect(client, shelf)
    for chunk in body["chunks"]:
        assert chunk["fused_score"] == pytest.approx(chunk["score"])
        expected = 0.0
        if chunk["vector_rank"] is not None:
            assert -1.0 <= chunk["vector_score"] <= 1.0
            expected += 1 / (60 + chunk["vector_rank"])
        if chunk["keyword_rank"] is not None:
            assert chunk["keyword_score"] > 0  # BM25, higher is better
            expected += 1 / (60 + chunk["keyword_rank"])
        assert chunk["fused_score"] == pytest.approx(expected)


# --- Parameters -----------------------------------------------------------------


def test_modes_keep_one_side(client, shelf):
    vector = _inspect(client, shelf, mode="vector")["chunks"]
    keyword = _inspect(client, shelf, mode="keyword")["chunks"]
    assert all(c["keyword_rank"] is None and c["vector_rank"] for c in vector)
    assert all(c["vector_rank"] is None and c["keyword_rank"] for c in keyword)


def test_vector_weight_moves_the_ranking_toward_one_side(client, shelf):
    vector_only = _inspect(client, shelf, mode="vector")["chunks"]
    keyword_only = _inspect(client, shelf, mode="keyword")["chunks"]
    weight_1 = _inspect(client, shelf, vector_weight=1.0)["chunks"]
    weight_0 = _inspect(client, shelf, vector_weight=0.0)["chunks"]
    assert [c["chunk_id"] for c in weight_1] == [c["chunk_id"] for c in vector_only]
    assert [c["chunk_id"] for c in weight_0] == [c["chunk_id"] for c in keyword_only]
    # Still a hybrid search: the breakdown shows both sides.
    assert any(c["keyword_rank"] for c in weight_1)


def test_cosine_floor_drops_weak_vector_matches(client, shelf):
    everything = _inspect(client, shelf, mode="vector")["chunks"]
    # The fake embeddings give some negative similarities; the floor is 0..1.
    positive = sorted(c["vector_score"] for c in everything if c["vector_score"] > 0)
    floor = positive[len(positive) // 2]
    kept = _inspect(client, shelf, mode="vector", min_cosine=floor)["chunks"]
    assert 0 < len(kept) < len(everything)
    assert all(c["vector_score"] >= floor for c in kept)


def test_candidates_limits_each_side(client, shelf):
    body = _inspect(client, shelf, candidates=4, top_k=2)
    assert all(
        (c["vector_rank"] or 0) <= 4 and (c["keyword_rank"] or 0) <= 4 for c in body["chunks"]
    )
    assert len(body["chunks"]) <= 4
    assert body["parameters"]["candidates"] == 4


def test_glossary_expansion_is_shown(client, shelf):
    client.post("/api/glossary", json={"term": "kiln", "means": "oven"})
    body = _inspect(client, shelf)
    assert body["question"] == QUESTION
    assert body["expanded_question"] != QUESTION and "oven" in body["expanded_question"]
    assert body["expanded_question"] in body["prompt"]


def test_profile_top_k_and_instructions_are_used(client, shelf):
    client.post(
        "/api/profiles",
        json={"name": "default", "retrieval_top_k": 2, "system_prompt": _prompt_with("Be brief.")},
    )
    body = _inspect(client, shelf)
    assert body["parameters"]["top_k"] == 2 and body["profile_version"] == 1
    assert "Be brief." in body["prompt"]


def _prompt_with(extra: str) -> str:
    from app.retrieval.prompt import SYSTEM_INSTRUCTIONS

    return f"{SYSTEM_INSTRUCTIONS}\n{extra}"


def test_no_prompt_when_asked_or_nothing_found(client, runtime, shelf):
    assert _inspect(client, shelf, include_prompt=False)["prompt"] is None
    with runtime.session_factory() as db:
        empty = service.create_collection(
            db, runtime.vector_store, name="empty", embedding_model="fake"
        )
        empty_id = empty.id
    body = _inspect(client, empty_id)
    assert body["chunks"] == [] and body["prompt"] is None


def test_scopes_all_and_portal(client, shelf):
    assert _inspect(client, None, scope="all")["collection_ids"] == [shelf]
    portal = client.post("/api/retrieve/inspect", json={"question": QUESTION, "scope": "portal"})
    assert portal.status_code == 200


# --- Reranker -------------------------------------------------------------------


def test_rerank_needs_the_model(client, shelf):
    response = client.post(
        "/api/retrieve/inspect", json={"question": QUESTION, "collection_id": shelf, "rerank": True}
    )
    assert response.status_code == 409


def test_rerank_rescores_all_candidates_and_keeps_the_fused_score(
    client, runtime, shelf, monkeypatch
):
    from app.api.routes import retrieval as retrieval_routes

    monkeypatch.setattr(retrieval_routes, "model_ready", lambda _dir: True)
    runtime.reranker = Reverse()
    plain = _inspect(client, shelf, top_k=3)["chunks"]
    body = _inspect(client, shelf, top_k=3, rerank=True)
    reranked = body["chunks"]
    assert [c["chunk_id"] for c in reranked] == [c["chunk_id"] for c in reversed(plain)]
    assert [c["rerank_score"] for c in reranked] == [12.0 - i for i in range(12)]
    assert reranked[0]["fused_score"] == pytest.approx(plain[-1]["fused_score"])
    assert sum(c["sent"] for c in reranked) == 3
    assert body["parameters"]["rerank"] is True and body["timings"]["rerank_ms"] is not None


# --- Embedding cache ------------------------------------------------------------


def test_moving_a_slider_reuses_the_question_embedding(client, runtime, shelf):
    embedder = runtime.embedding_client_for("fake")
    first = _inspect(client, shelf)
    calls = embedder.call_count
    second = _inspect(client, shelf, top_k=2, vector_weight=0.8)
    assert embedder.call_count == calls
    assert second["timings"]["embedding_cached"] is True
    assert first["timings"]["embedding_cached"] is False


def test_question_cache_is_bounded():
    cache = QuestionEmbeddingCache(max_entries=2)
    cache.put("m", "a", [1.0])
    cache.put("m", "b", [2.0])
    assert cache.get("m", "a") == [1.0]  # now the most recent
    cache.put("m", "c", [3.0])
    assert cache.get("m", "b") is None
    assert cache.get("m", "a") == [1.0] and cache.get("m", "c") == [3.0]
    assert cache.get("other", "a") is None


def test_bad_parameters_are_422(client, shelf):
    for bad in ({"vector_weight": 1.5}, {"min_cosine": -0.1}, {"mode": "magic"}, {"top_k": 0}):
        response = client.post(
            "/api/retrieve/inspect", json={"question": QUESTION, "collection_id": shelf, **bad}
        )
        assert response.status_code == 422, bad


def test_retrieve_many_rejects_a_bad_weight(runtime, shelf):
    with runtime.session_factory() as db, pytest.raises(ValueError):
        retrieve_module.retrieve_many(
            db,
            QUESTION,
            collections=[service.get_collection(db, shelf)],
            settings=runtime.settings,
            embedding_client_for=runtime.embedding_client_for,
            vector_store=runtime.vector_store,
            vector_weight=2.0,
        )
