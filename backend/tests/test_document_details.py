"""The document details panel's API: last updated, version text, compare,
restore, chat history search and the feedback summary."""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _upload(client, collection_id, filename, content):
    response = client.post(
        "/api/documents",
        files=[("files", (filename, content.encode(), "text/plain"))],
        data={"collection_id": str(collection_id)},
    )
    assert response.status_code == 202, response.text
    client.drain()


@pytest.fixture
def faq(client):
    """customer-faq.txt with two versions: the support email changes in v2."""
    shelf = client.post("/api/collections", json={"name": "support"}).json()
    _upload(
        client,
        shelf["id"],
        "customer-faq.txt",
        "Questions? Email help@example.com.\nShipping takes 3 days.",
    )
    first = client.get("/api/documents").json()[0]
    time.sleep(0.02)
    _upload(
        client,
        shelf["id"],
        "customer-faq.txt",
        "Questions? Email care@example.com.\nShipping takes 3 days.",
    )
    return first


def test_a_new_version_moves_updated_at_but_not_created_at(client, faq):
    doc = client.get("/api/documents").json()[0]
    assert doc["version_count"] == 2
    assert doc["created_at"] == faq["created_at"]
    assert doc["updated_at"] > faq["updated_at"]


def test_each_version_text_can_be_read(client, faq):
    versions = client.get(f"/api/documents/{faq['id']}/versions").json()
    texts = {
        v["version_number"]: client.get(
            f"/api/documents/{faq['id']}/versions/{v['id']}/text"
        ).json()
        for v in versions
    }
    assert "help@example.com" in texts[1]["text"]
    assert "care@example.com" in texts[2]["text"]


def test_version_text_of_another_document_is_a_404(client, faq):
    versions = client.get(f"/api/documents/{faq['id']}/versions").json()
    assert client.get(f"/api/documents/9999/versions/{versions[0]['id']}/text").status_code == 404


def test_compare_shows_the_changed_line(client, faq):
    v2, v1 = client.get(f"/api/documents/{faq['id']}/versions").json()
    diff = client.get(
        f"/api/documents/{faq['id']}/diff", params={"a": v1["id"], "b": v2["id"]}
    ).json()["diff"]
    assert "-Questions? Email help@example.com." in diff
    assert "+Questions? Email care@example.com." in diff
    assert not any(line.startswith(("-", "+")) and "Shipping" in line for line in diff)


def test_restoring_an_earlier_version_updates_the_date(client, faq):
    before = client.get("/api/documents").json()[0]
    v2, v1 = client.get(f"/api/documents/{faq['id']}/versions").json()
    time.sleep(0.02)
    restored = client.post(
        f"/api/documents/{faq['id']}/rollback", json={"version_id": v1["id"]}
    ).json()
    assert restored["is_active"] and restored["version_number"] == 1
    after = client.get("/api/documents").json()[0]
    assert after["active_version_number"] == 1
    assert after["updated_at"] > before["updated_at"]


def test_chat_history_can_be_searched(client, runtime):
    from app.versioning import history

    with runtime.session_factory() as db:
        a = history.create_session(db, "Shipping times")
        history.add_message(db, a.id, "user", "How long does shipping take?")
        b = history.create_session(db, "Holidays")
        history.add_message(db, b.id, "user", "When do we close for the holidays?")

    def titles(q):
        return [s["title"] for s in client.get("/api/sessions", params={"q": q}).json()]

    assert titles("shipping") == ["Shipping times"]
    assert titles("close for the") == ["Holidays"]
    assert sorted(titles("")) == ["Holidays", "Shipping times"]


def test_feedback_summary_counts_and_lists_not_helpful_answers(client, runtime):
    from app.versioning import history

    with runtime.session_factory() as db:
        s = history.create_session(db, "Prices", channel="intranet")
        history.add_message(db, s.id, "user", "What does a bee charm cost?")
        bad = history.add_message(db, s.id, "assistant", "It costs $9.")
        history.add_message(db, s.id, "user", "And the moon charm?")
        good = history.add_message(db, s.id, "assistant", "$1.85 each.")
        bad_id, good_id = bad.id, good.id

    client.post(f"/api/messages/{good_id}/feedback", json={"thumbs_up": True})
    client.post(
        f"/api/messages/{bad_id}/feedback", json={"thumbs_up": False, "comment": "Wrong price"}
    )

    summary = client.get("/api/feedback/summary").json()
    assert (summary["helpful"], summary["not_helpful"]) == (1, 1)
    [item] = summary["recent_not_helpful"]
    assert item["question"] == "What does a bee charm cost?"
    assert item["answer"] == "It costs $9."
    assert item["comment"] == "Wrong price"
    assert item["channel"] == "intranet"
