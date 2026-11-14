# 0030: Prometheus metrics with the standard library

**Status:** accepted (2026-11-14)

## Context

Phase 9 asks for a Prometheus `/metrics` endpoint with query latency, retrieval counts and job durations, plus request-id logging. The request-id logging was already done (`core/logging.py`: every JSON log line has a `request_id`, and job logs are tagged `job-<id>`).

The official `prometheus_client` would be one more dependency. The user chose (2026-11-14) to write the text format with the standard library instead, since the app runs one process.

## Decision

- **`app/core/metrics.py`**, about 250 lines: a `Counter` and a `Histogram` with labels and a lock, plus `render()`, which writes [text format 0.0.4](https://prometheus.io/docs/instrumenting/exposition_formats/). The registry is module-level. One process (CLAUDE.md: 1 uvicorn worker, 1 job worker) means there's nothing to aggregate across processes. Values reset when the server restarts, which Prometheus handles for counters.
- **What it measures:**

  | Metric | Labels | Measured in |
  |---|---|---|
  | `rag_http_requests_total`, `rag_http_request_duration_seconds` | method, route, status | `MetricsMiddleware` (pure ASGI, so streamed answers aren't buffered) |
  | `rag_retrievals_total`, `rag_retrieval_duration_seconds`, `rag_retrieved_chunks` | mode | `retrieve_many`, so chat, the inspector and the evaluation all count |
  | `rag_answer_duration_seconds` | outcome: answered, not_found, error, disconnected | the chat stream, from the question to the end of the answer |
  | `rag_job_duration_seconds` | job_type, status: completed, failed, cancelled | the job worker, one observation per attempt |
  | `rag_jobs` (gauge) | status | read from the jobs table at scrape time |
  | `rag_info` (gauge) | version | |

- **Bounded labels.** The route label is the path template (`/api/documents/{document_id}/versions`), never the raw path. FastAPI 0.16x matches an included router's routes without its prefix, so the middleware puts the prefix back from the request path. Everything the UI's catch-all serves, and every unmatched path, is `other`. Scrapes of `/metrics` aren't counted.
- **Open like `/health`.** With a password set (decision 0026), `/metrics` still answers without a session, so Prometheus can scrape it. It holds counts and timings only, with no document names, questions or ids. `METRICS_ENABLED=false` removes the route.

## Not done

- No Grafana dashboard or Prometheus container in Compose. A reviewer can `curl localhost:8000/metrics`; scraping it is one job in any Prometheus config.
- No metrics for Ollama itself (tokens per second, model load time). Ollama doesn't expose them on its API, and the answer duration covers what the user waits for.
