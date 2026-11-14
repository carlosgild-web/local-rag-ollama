"""Prometheus metrics at `/metrics`, written with the standard library
(decision 0030).

The app runs one process, so a module-level registry is enough: counters
and histograms live in memory and reset when the server restarts, which
Prometheus handles. Labels are kept to small fixed sets (route templates,
job types, outcomes), never ids or raw paths, so the series count stays
bounded.

Instrumented:
- every HTTP request: count and duration, by method, route template and status
- every retrieval: count, duration and passages returned, by mode
- every chat answer: time to the end of the answer, by outcome
- every job: duration, by type and final status

`render()` adds two values read at scrape time: jobs by status (from the
`jobs` table) and the app version.
"""

import math
import re
import threading
import time
from collections.abc import Callable, Iterable, Sequence

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Seconds. Chat answers on a laptop CPU take 5-60 s, so the buckets reach far.
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)
JOB_BUCKETS = (0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)
COUNT_BUCKETS = (0, 1, 2, 3, 5, 8, 10, 20, 50)

LabelValues = tuple[str, ...]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(names: Sequence[str], values: Sequence[str], extra: str = "") -> str:
    parts = [f'{name}="{_escape(value)}"' for name, value in zip(names, values, strict=True)]
    if extra:
        parts.append(extra)
    return "{" + ",".join(parts) + "}" if parts else ""


def _number(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


class _Metric:
    kind = ""

    def __init__(self, name: str, help_text: str, labels: Sequence[str] = ()):
        self.name = name
        self.help = help_text
        self.label_names = tuple(labels)
        self._lock = threading.Lock()

    def _key(self, labels: dict[str, str]) -> LabelValues:
        if set(labels) != set(self.label_names):
            raise ValueError(f"{self.name} takes labels {self.label_names}, got {tuple(labels)}")
        return tuple(str(labels[name]) for name in self.label_names)

    def header(self) -> list[str]:
        return [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} {self.kind}"]


class Counter(_Metric):
    kind = "counter"

    def __init__(self, name: str, help_text: str, labels: Sequence[str] = ()):
        super().__init__(name, help_text, labels)
        self._values: dict[LabelValues, float] = {}

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        if amount < 0:
            raise ValueError("a counter only goes up")
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        with self._lock:
            return self._values.get(self._key(labels), 0.0)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()

    def lines(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
        return [f"{self.name}{_labels(self.label_names, k)} {_number(v)}" for k, v in items]


class Histogram(_Metric):
    kind = "histogram"

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Sequence[str] = (),
        *,
        buckets: Iterable[float] = LATENCY_BUCKETS,
    ):
        super().__init__(name, help_text, labels)
        self.buckets = tuple(sorted(buckets))
        # Per label set: count per bucket (not cumulative), then sum and count.
        self._values: dict[LabelValues, tuple[list[int], list[float]]] = {}

    def observe(self, value: float, **labels: str) -> None:
        key = self._key(labels)
        with self._lock:
            counts, totals = self._values.setdefault(key, ([0] * len(self.buckets), [0.0, 0.0]))
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    counts[i] += 1
                    break
            totals[0] += value
            totals[1] += 1

    def count(self, **labels: str) -> int:
        with self._lock:
            entry = self._values.get(self._key(labels))
            return int(entry[1][1]) if entry else 0

    def total(self, **labels: str) -> float:
        with self._lock:
            entry = self._values.get(self._key(labels))
            return entry[1][0] if entry else 0.0

    def reset(self) -> None:
        with self._lock:
            self._values.clear()

    def lines(self) -> list[str]:
        with self._lock:
            items = sorted((k, (list(c), list(t))) for k, (c, t) in self._values.items())
        out = []
        for key, (counts, (total, count)) in items:
            running = 0
            for bound, n in zip(self.buckets, counts, strict=True):
                running += n
                le = _labels(self.label_names, key, f'le="{_number(bound)}"')
                out.append(f"{self.name}_bucket{le} {running}")
            le = _labels(self.label_names, key, 'le="+Inf"')
            out.append(f"{self.name}_bucket{le} {_number(count)}")
            out.append(f"{self.name}_sum{_labels(self.label_names, key)} {_number(total)}")
            out.append(f"{self.name}_count{_labels(self.label_names, key)} {_number(count)}")
        return out


HTTP_REQUESTS = Counter(
    "rag_http_requests_total", "HTTP requests handled.", ("method", "route", "status")
)
HTTP_DURATION = Histogram(
    "rag_http_request_duration_seconds",
    "Time to handle an HTTP request; for a chat answer, until the stream ends.",
    ("method", "route"),
)
RETRIEVALS = Counter("rag_retrievals_total", "Searches of the indexes.", ("mode",))
RETRIEVAL_DURATION = Histogram(
    "rag_retrieval_duration_seconds",
    "Time to embed the question, search vectors and keywords, and fuse the lists.",
    ("mode",),
)
RETRIEVED_CHUNKS = Histogram(
    "rag_retrieved_chunks",
    "Passages a search returned.",
    ("mode",),
    buckets=COUNT_BUCKETS,
)
ANSWER_DURATION = Histogram(
    "rag_answer_duration_seconds",
    "Time from a chat question to the end of its answer, retrieval included.",
    ("outcome",),
)
JOB_DURATION = Histogram(
    "rag_job_duration_seconds",
    "Time a background job ran, by type and final status.",
    ("job_type", "status"),
    buckets=JOB_BUCKETS,
)

REGISTRY: tuple[Counter | Histogram, ...] = (
    HTTP_REQUESTS,
    HTTP_DURATION,
    RETRIEVALS,
    RETRIEVAL_DURATION,
    RETRIEVED_CHUNKS,
    ANSWER_DURATION,
    JOB_DURATION,
)


def reset() -> None:
    """Test helper: empties every metric."""
    for metric in REGISTRY:
        metric.reset()


def render(*, version: str, jobs_by_status: dict[str, int] | None = None) -> str:
    lines: list[str] = [
        "# HELP rag_info The running app.",
        "# TYPE rag_info gauge",
        f"rag_info{_labels(('version',), (version,))} 1",
    ]
    if jobs_by_status is not None:
        lines += [
            "# HELP rag_jobs Jobs in the queue table, by status.",
            "# TYPE rag_jobs gauge",
        ]
        lines += [
            f"rag_jobs{_labels(('status',), (status,))} {count}"
            for status, count in sorted(jobs_by_status.items())
        ]
    for metric in REGISTRY:
        lines += metric.header() + metric.lines()
    return "\n".join(lines) + "\n"


class MetricsMiddleware:
    """Pure ASGI, like RequestIdMiddleware, so SSE answers aren't buffered.
    The route label is the matched path template (`/api/documents/{document_id}`);
    anything no API route matched, such as the UI's own pages, is `other`."""

    def __init__(self, app, *, clock: Callable[[], float] = time.perf_counter):
        self.app = app
        self.clock = clock

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = self.clock()
        status_code = 500

        async def send_and_watch(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_watch)
        finally:
            route = _route_template(scope)
            if route != "/metrics":  # scrapes would drown the rest
                method = scope["method"]
                HTTP_REQUESTS.inc(method=method, route=route, status=str(status_code))
                HTTP_DURATION.observe(self.clock() - started, method=method, route=route)


_CONVERTER = re.compile(r"\{(\w+):\w+\}")


def _route_template(scope) -> str:
    path = getattr(scope.get("route"), "path", None)
    # The UI's catch-all route serves every page; keep it as one series.
    if not path or "{path" in path:
        return "other"
    # FastAPI 0.16x matches an included router's routes without its prefix, so
    # `route.path` is "/jobs" for /api/jobs. The prefix is what's left of the
    # request path once the route's own part, with its values filled in, is cut.
    params = scope.get("path_params") or {}
    plain = _CONVERTER.sub(lambda m: "{" + m.group(1) + "}", path)  # "{name:path}" -> "{name}"
    try:
        own_part = plain.format(**{name: str(value) for name, value in params.items()})
    except (KeyError, IndexError, ValueError):
        return path
    request_path = scope.get("path", "")
    if own_part and request_path.endswith(own_part):
        return request_path[: -len(own_part)] + path
    return path
