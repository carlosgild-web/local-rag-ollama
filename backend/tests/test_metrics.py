"""Prometheus metrics (decision 0030): the text format, and that requests,
retrievals, answers and jobs are counted."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.core import auth, metrics
from app.main import create_app

CORPUS = Path(__file__).parent / "corpus"


@pytest.fixture(autouse=True)
def clean_metrics():
    metrics.reset()
    yield
    metrics.reset()


@pytest.fixture
def app(runtime):
    return create_app(runtime, start_worker=False)


def _sample(text: str, name: str, **labels: str) -> float | None:
    """The value of one series in a scrape, or None if it isn't there."""
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        series, value = line.rsplit(" ", 1)
        series_name, _, label_part = series.partition("{")
        if series_name != name:
            continue
        found = dict(re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', label_part))
        if found == labels:
            return float(value)
    return None


def test_counter_and_histogram_write_the_prometheus_text_format():
    counter = metrics.Counter("t_total", "Things.", ("kind",))
    counter.inc(kind='a"b')
    counter.inc(2, kind='a"b')
    histogram = metrics.Histogram("t_seconds", "Time.", ("kind",), buckets=(0.1, 1))
    for value in (0.05, 0.5, 5):
        histogram.observe(value, kind="x")

    assert counter.header() == ["# HELP t_total Things.", "# TYPE t_total counter"]
    assert counter.lines() == ['t_total{kind="a\\"b"} 3']
    assert histogram.lines() == [
        't_seconds_bucket{kind="x",le="0.1"} 1',
        't_seconds_bucket{kind="x",le="1"} 2',
        't_seconds_bucket{kind="x",le="+Inf"} 3',
        't_seconds_sum{kind="x"} 5.55',
        't_seconds_count{kind="x"} 3',
    ]


def test_metrics_refuse_wrong_labels_and_negative_counts():
    counter = metrics.Counter("t_total", "Things.", ("kind",))
    with pytest.raises(ValueError):
        counter.inc(other="x")
    with pytest.raises(ValueError):
        counter.inc(-1, kind="x")


def test_scrape_has_version_and_jobs_and_is_not_counted_itself(app):
    with TestClient(app) as client:
        client.post("/api/documents", files=[("files", ("a.txt", b"alpha", "text/plain"))])
        response = client.get("/metrics")
        again = client.get("/metrics").text

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert _sample(response.text, "rag_info", version=__version__) == 1
    assert _sample(response.text, "rag_jobs", status="pending") == 1
    assert "# TYPE rag_http_request_duration_seconds histogram" in response.text
    assert 'route="/metrics"' not in again


def test_requests_are_labelled_by_route_template_not_raw_path(app):
    with TestClient(app) as client:
        client.get("/api/documents/123456/versions")
        client.get("/api/documents/654321/versions")
        client.get("/api/jobs")
        client.delete("/api/models/some/model:tag")
        text = client.get("/metrics").text

    template = "/api/documents/{document_id}/versions"
    assert _sample(text, "rag_http_requests_total", method="GET", route=template, status="404") == 2
    assert _sample(text, "rag_http_requests_total", method="GET", route="/api/jobs", status="200")
    assert "123456" not in text
    assert 'route="/api/models/{name:path}"' in text
    count = _sample(text, "rag_http_request_duration_seconds_count", method="GET", route=template)
    assert count == 2


def test_ui_pages_count_as_one_route(runtime, tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    runtime.settings.static_dir = static
    with TestClient(create_app(runtime, start_worker=False)) as client:
        client.get("/documents")
        client.get("/settings/profiles")
        text = client.get("/metrics").text
    assert _sample(text, "rag_http_requests_total", method="GET", route="other", status="200") == 2


def test_chat_records_retrieval_and_answer_time(app, runtime):
    runtime.fake_llm._responses.append("Espresso is brewed under pressure [1].")
    with TestClient(app) as client:
        coffee = (CORPUS / "coffee-brewing-methods.txt").read_bytes()
        client.post("/api/documents", files=[("files", ("coffee.txt", coffee, "text/plain"))])
        app.state.worker.run_until_idle()
        client.post("/api/chat", json={"question": "How is espresso brewed?"}).read()
        text = client.get("/metrics").text

    assert _sample(text, "rag_retrievals_total", mode="hybrid") == 1
    assert _sample(text, "rag_retrieved_chunks_count", mode="hybrid") == 1
    assert _sample(text, "rag_retrieved_chunks_sum", mode="hybrid") > 0
    assert _sample(text, "rag_answer_duration_seconds_count", outcome="answered") == 1
    ingest = {"job_type": "ingest", "status": "completed"}
    assert _sample(text, "rag_job_duration_seconds_count", **ingest) == 1


def test_a_question_with_nothing_to_search_is_a_not_found_answer(app):
    with TestClient(app) as client:
        client.post("/api/collections", json={"name": "empty"})
        client.post("/api/chat", json={"question": "Anything?"}).read()
        text = client.get("/metrics").text
    assert _sample(text, "rag_answer_duration_seconds_count", outcome="not_found") == 1


def test_failed_jobs_are_timed_as_failed(app, runtime):
    from app.db.models import IngestJob

    with runtime.session_factory() as db:
        db.add(IngestJob(job_type="no-such-job", payload="{}"))
        db.commit()
    with TestClient(app):
        app.state.worker.run_until_idle()
    assert metrics.JOB_DURATION.count(job_type="no-such-job", status="failed") >= 1


def test_metrics_stay_open_with_a_password_and_can_be_turned_off(runtime):
    auth.set_password(runtime.settings, "correct horse battery")
    with TestClient(create_app(runtime, start_worker=False)) as client:
        assert client.get("/api/documents").status_code == 401
        assert client.get("/metrics").status_code == 200

    runtime.settings.metrics_enabled = False
    with TestClient(create_app(runtime, start_worker=False)) as client:
        # No route: the UI's catch-all (if built) answers instead.
        assert "rag_info" not in client.get("/metrics").text
