import json
import logging
import sys

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, request_id_var
from app.main import create_app


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[dict] = []

    def emit(self, record):
        self.lines.append(json.loads(self.format(record)))


@pytest.fixture
def captured():
    handler = _ListHandler()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    yield handler.lines
    root.removeHandler(handler)
    root.setLevel(previous_level)


def test_json_formatter_includes_request_id_extras_and_exceptions():
    token = request_id_var.set("abc123")
    try:
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.getLogger("t").makeRecord(
                "t",
                logging.ERROR,
                __file__,
                1,
                "failed %s",
                ("x",),
                exc_info=sys.exc_info(),
                extra={"job_id": 7},
            )
        entry = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert entry["message"] == "failed x"
    assert entry["level"] == "ERROR"
    assert entry["request_id"] == "abc123"
    assert entry["job_id"] == 7
    assert "ValueError: boom" in entry["exc_info"]


def test_requests_get_an_id_header_and_one_log_line(runtime, captured):
    with TestClient(create_app(runtime, start_worker=False)) as client:
        generated = client.get("/api/jobs")
        echoed = client.get("/api/jobs", headers={"X-Request-ID": "trace-42"})

    request_id = generated.headers["x-request-id"]
    assert len(request_id) == 16
    assert echoed.headers["x-request-id"] == "trace-42"

    request_lines = [line for line in captured if line["message"] == "request"]
    assert {line["request_id"] for line in request_lines} >= {request_id, "trace-42"}
    line = next(line for line in request_lines if line["request_id"] == "trace-42")
    assert line["method"] == "GET" and line["path"] == "/api/jobs" and line["status"] == 200
    assert line["duration_ms"] >= 0


def test_worker_logs_are_tagged_with_the_job(runtime, captured):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as client:
        client.post("/api/documents", files=[("files", ("a.txt", b"alpha", "text/plain"))])
        app.state.worker.run_until_idle()

    job_lines = [line for line in captured if line["message"].startswith("job ")]
    assert job_lines
    assert all(line["request_id"] == f"job-{line['job_id']}" for line in job_lines)
