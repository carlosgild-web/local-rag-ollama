# 0004: Small chat model on low-RAM machines

**Status:** accepted (2026-11-05)

## Context

CLAUDE.md fixes the chat model to `qwen2.5:7b` or `llama3.1:8b`. On the
development laptop (Ryzen 5 7520U, 7.2 GB RAM, integrated Radeon that
Ollama does not use) `llama3.1:8b` needs 6.3 GB and runs 100% on the CPU.
Together with `bge-m3` and the app, Windows swaps to disk, and a short
answer over two chunks did not finish in 5 minutes.

## Decision

- On this machine, chat uses `qwen2.5:3b` (about 2 GB), set with
  `CHAT_MODEL` in the gitignored `backend/.env`. It is the same model family
  as the listed `qwen2.5:7b` and handles English and Spanish.
- The `default` RAG profile got a new version with `chat_model=qwen2.5:3b`
  through `POST /api/profiles`, so answers record which model produced them.
- The repo default (`config.py`, `.env.example`) stays `llama3.1`, the
  recommended model for machines with 16 GB RAM or more.
- Embeddings stay on `bge-m3`. Changing them would mean a blue/green rebuild.

## Consequences

- Answers are faster but somewhat less precise than with a 7B/8B model.
- Phase 7 evaluation should be run with the model the README recommends.
  It can also show what a 3B model loses.
- The README (Phase 9) should list hardware tiers: 8 GB RAM uses a 3B chat
  model, 16 GB or more uses a 7B/8B one.
