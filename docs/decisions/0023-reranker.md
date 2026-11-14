# 0023: bge-reranker-v2-m3 through ONNX Runtime, off in the chat by default

**Status:** accepted (2026-11-14)

## Context

`PLAN.md` section 6 plans a reranker, `bge-reranker-v2-m3` rescoring the top 20, for later. Phase 7 is done when "vector only, hybrid and hybrid + reranker can be compared on the same question set". The code only had a no-op hook, and that hook reordered the top-k it was given, so it could never bring in a better passage.

The user chose the ONNX route, as an optional install, over `sentence-transformers` and torch (about 1 GB, and CUDA wheels on Linux) or the chat model as a judge (minutes per question).

## Decision

- **Model:** `onnx-community/bge-reranker-v2-m3-ONNX`, the 8-bit export (`onnx/model_int8.onnx`, 570.7 MB, plus a 17.1 MB tokenizer), pinned to commit `6f5ff65` with SHA-256 checks. It is an export of BAAI's Apache-2.0 model.
  - `python -m app.cli reranker-download` fetches it into `DATA_DIR/hf/bge-reranker-v2-m3-onnx`. This is an explicit command, like `ollama pull`. The app never downloads at runtime, and the model is never baked into an image.
  - `RERANK_MODEL_DIR` points elsewhere.
- **Packages:** `onnxruntime` and `tokenizers` already come with ChromaDB, so nothing new is installed. `requirements-rerank.txt` lists them so the reranker doesn't rely on that.
- **`OnnxReranker`:**
  - loads on first use (about 4 s, roughly 0.6 GB of RAM)
  - scores question + passage pairs in batches of 4: batches of 8 ran this 7.2 GB machine out of memory next to Ollama
  - turns the logit into 0..1
  - is thread-safe
- **Chat:** `RERANK_ENABLED=true` turns it on. It then rescores all fused candidates (20) and keeps the top-k, as the plan says. It is **off by default** (see Measurements).
- **Evaluation:** a run can rerank in any mode (API `rerank`, `--rerank`, a checkbox on the page). It's refused with a hint when the model isn't downloaded, and `GET /api/eval/options` says whether it is. The run label shows `+rerank`.

## Measurements

Retrieval only, the 53-question golden set, the glossary on, top 20 candidates. The demo library is 11 documents on 4 shelves.

| Retrieval | Hit rate@5 | Hit rate@1 | MRR | Retrieval time per question |
|---|---|---|---|---|
| Vectors only | 96% | 78% | 0.865 | 2.7 s |
| Keywords only (FTS5) | 100% | 96% | **0.978** | 2 ms |
| Hybrid (RRF, the chat's) | 100% | 89% | 0.934 | 2.5 s |
| Hybrid + reranker | 100% | 91% | 0.956 | 15.0 s |

Against hybrid, the reranker moved the right file up in 3 questions:
- the Opal Mist retail price
- custom colors on the operations shelf
- outbound spot checks

It moved it down in 1: the holiday party, asked across all shelves.

## Consequences

- **The reranker is off in the chat by default.** On this CPU it adds about 12 s per question for +0.02 MRR, and retrieval already finds the right file in the top 5 for every question. The wrong answers that remain come from the 3B model, not the search (decisions 0020–0022). It's worth turning on with a faster CPU, a GPU, or a larger library where the right passage isn't always in the top 5.
- **Answers with the reranker weren't measured.** A run with the chat model and the reranker loaded together was stopped twice by the low-memory guard on this 7.2 GB machine.
- **Keywords alone rank best here.** The golden set reuses the documents' own words (product names, SKUs, policy terms), and the glossary adds more. Hybrid stays the default because vectors cover questions worded unlike the text, which a small golden set underrepresents. This should be rechecked on a larger, less literal set.
- With this, Phase 7's "done when" is met: vector only, hybrid and hybrid + reranker are compared on the same question set.
