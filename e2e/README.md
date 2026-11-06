# End-to-end test

This tests the running app with a real Ollama and the sample corpus in `corpus/`, which is fictional
"Hilda & Luna Beadworks" data. It works through the same HTTP API the web UI uses.

It checks:
- ingestion: PDF, Word including tables, text and Markdown
- answers, against facts in `scenario.json`
- citations
- grounding: off-topic and missing facts must give "not found in the documents"
- shelf isolation
- versions, rollback and diff
- trash
- jobs: cancel and retry
- reindex and blue/green rebuild
- prompt injection
- persistence across a restart

The unit tests in `backend/tests/` use fakes. This test covers what they can't: real files, the real
model and real memory limits. It is not run in CI.

## Run it

```bash
# 1. Start the server on an EMPTY data directory, logging to a file
cd backend
DATA_DIR=./data-e2e .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 > e2e-server.log 2>&1 &

# 2. Run the main phases (about 1–3 hours on a CPU-only laptop)
cd ..
backend/.venv/Scripts/python.exe e2e/run_e2e.py --run-dir backend/data-e2e/e2e-runs/run1 \
    --server-log backend/e2e-server.log

# 3. Optional restart check: queue an upload, kill and restart the server, verify
backend/.venv/Scripts/python.exe e2e/run_e2e.py --run-dir ... --phases persistence_prepare
#    (stop the server now, start it again)
backend/.venv/Scripts/python.exe e2e/run_e2e.py --run-dir ... --phases persistence_verify report
```

The report goes to `<run-dir>/report.md`. The exit code is non-zero if any **must** check fails: an
app mechanic such as ingestion, versions, rollback, trash, jobs or persistence. **Quality** checks
cover what the model answers. They are reported as a pass rate, and each failure is classified:
- **retrieval miss:** the fact was not in the passages found
- **answer miss:** the fact was found but not stated
- **app error**

## Files

| File | What it is |
|---|---|
| `corpus/` | 11 sample documents, in the folder layout they were delivered in |
| `scenario.json` | Collections, questions with expected facts, grounding tests, edits, new documents |
| `variants.py` | Builds edited copies (new versions) and new documents; the corpus is never modified |
| `run_e2e.py` | The runner and report writer |
