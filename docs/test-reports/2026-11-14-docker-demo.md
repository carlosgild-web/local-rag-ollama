# Docker demo mode, from a fresh clone (2026-11-14)

The Phase 9 "Done when" check: can a reviewer who only has Docker run the demo in 5 commands or fewer ([decision 0031](../decisions/0031-docker-demo-mode.md))?

**Machine:** the development laptop. Windows 11, 7.2 GB RAM, 8 CPU threads, no GPU. Docker Desktop 29.5.3, whose VM got 3.4 GiB. VS Code and other apps stayed open, with about 1.6 GB free before Docker started. The test used its own Compose project (`-p ragdemo-test`) and new volumes, and `APP_PORT=8020` because port 8000 was in use.

## Steps and results

| Step | Command or action | Result |
|---|---|---|
| 1 | `git clone https://github.com/carlosgild-web/local-rag-ollama.git` | OK |
| 2 | `cd local-rag-ollama` | OK |
| 3 | `docker compose -f compose.yaml -f compose.demo.yaml up -d` | OK in **23.5 min** (images, then `bge-m3` and `qwen2.5:3b` at about 2.5 MB/s); `/health` all OK |
| 4 | **Load the demo company** (`POST /api/demo/seed`, as the dashboard button does) | 11 of 11 files indexed in **13.5 min** |
| 5 | Ask Luna (portal chat): "When does the company close for the holidays?" | **Failed twice**: Ollama couldn't load the model within the app's 300 s timeout |
| 6 | The same, with `OLLAMA_MAX_LOADED_MODELS=1` added | **Right answer** ("December 22, 2026 through January 2"), from `05-holiday-announcement.pdf`, but about **10 minutes** to stream |

## Why the questions failed

- Inside Docker's VM (3.5 GB), `qwen2.5:3b` alone takes 2.2 GB and `bge-m3` 1.2 GB. With both loaded, the model server was killed for lack of memory (`llama-server process has terminated: signal: killed`). No container restarted, and the app reported "Can't reach Ollama".
- Windows had about 0.01 GB free while the VM was busy, so the VM's memory was paged to disk. Loading `qwen2.5:3b` alone took 103 s, and generation crawled.
- With one model at a time, each question loads `bge-m3` for the question's embedding, then `qwen2.5:3b` for the answer.

## Conclusion

- **Commands: met.** Three commands and one click.
- **Works: yes, on enough memory.** Every part ran in Docker (models, indexing, retrieval, a grounded and cited answer), but this 7.2 GB laptop is below what Ollama in Docker needs. The docs now say about 16 GB for the demo mode, matching GETTING_STARTED.md's existing advice, and point 8 GB machines to the start script, which runs Ollama outside Docker. That route went from a fresh clone to working in 5 min 38 s on this laptop (Phase 8), and the README's evaluation ran on it.
- **Not tested:** the demo mode on a 16 GB machine.

Clean-up: the test containers and volumes were removed (`down -v`) and Docker Desktop was stopped.
