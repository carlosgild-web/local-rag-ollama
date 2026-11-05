# 0001 — Approximate chunk token counts with a chars/4 heuristic

## Context

PLAN.md section 6 targets a 600-token chunk size with 12% overlap, but no
tokenizer is in the approved stack, and Ollama's `/api/generate` doesn't
expose a tokenize endpoint for arbitrary text. The two real options were a
heuristic or adding `tiktoken` (an OpenAI tokenizer, not what Ollama models
actually use — so still an approximation, just a different one, for a new
dependency).

## Decision

Estimate tokens as `len(text) / 4`, the common rule of thumb for English
and reasonably close for Spanish. No new dependency.

## Consequences

Chunk sizes are approximate, not exact token counts for `qwen2.5`/`llama3.1`'s
actual tokenizer. This only affects chunk sizing, not correctness — chunks
that land at ~500-700 "tokens" by this measure are still well within the
8192 `num_ctx` budget when 5 are sent to the model. Revisit if retrieval
eval (Phase 7) shows chunk sizing is a real quality problem.
