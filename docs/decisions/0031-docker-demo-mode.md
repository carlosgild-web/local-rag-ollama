# 0031: Docker demo mode as an overlay file, with qwen2.5:3b

**Status:** accepted (2026-11-14)

## Context

PLAN.md Phase 9 asks for "a `demo` compose profile with small models (`llama3.2:3b` plus `bge-m3`)". Its "Done when" is that a reviewer who only has Docker can run the demo in 5 commands or fewer.

Until now, Docker mode A took four commands after the clone: `up`, two `ollama pull`s inside the container, and `CHAT_MODEL=qwen2.5:3b` on machines with 8 GB of RAM, since the default `llama3.1` is an 8B model.

## Decision

- **An overlay file, `compose.demo.yaml`, not a Compose profile.** A profile can only switch services on or off. It can't change another service's environment, and the demo needs the app to use the small model. The overlay:
  - adds a one-off `models` service: the `ollama/ollama` image used as a client (`OLLAMA_HOST=http://ollama:11434`), which pulls `bge-m3` and the chat model and then exits
  - sets the app's `CHAT_MODEL`, and makes the app wait for `models` to finish (`service_completed_successfully`)

  The models stay in the `ollama_models` volume, so later starts skip the download. This is the same pattern as `compose.host-ollama.yaml` (mode B).
- **`qwen2.5:3b` instead of `llama3.2:3b`** (the user's choice). Every number in the README's evaluation (70% → 91% passed) was measured with `qwen2.5:3b`, so the demo behaves like the published results. It's also the low-RAM model from [decision 0004](0004-small-chat-model-on-low-ram.md), and it handles the Spanish half of the demo well. `DEMO_CHAT_MODEL` picks another one, such as `llama3.2:3b`.
- **No automatic seeding.** The dashboard already offers **Load the demo company** when the library is empty, and the reviewer sees what gets loaded. Seeding at start would write to SQLite and Chroma from a second container, and both are single-writer.

The reviewer's path, with only Docker:

```bash
git clone https://github.com/carlosgild-web/local-rag-ollama.git
cd local-rag-ollama
docker compose -f compose.yaml -f compose.demo.yaml up -d
```

Then open http://localhost:8000 and click **Load the demo company**. That's three commands.

## Not done

- The start scripts (`start.cmd`, `start.sh`) don't use the demo overlay. They already pick a model that fits the machine's RAM.
- The `ollama/ollama` image isn't pinned yet. Ollama keeps its API stable, and the app checks the version in `/health`.
