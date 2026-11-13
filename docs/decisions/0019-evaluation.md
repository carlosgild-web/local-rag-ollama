# 0019: Evaluation before the control panel

**Status:** accepted (2026-11-13)

## Context

`PLAN.md` puts Phase 6 (control panel: retrieval inspector, profile compare, models manager, watched folders) before Phase 7 (evaluation). The open problems are now about answer quality, not controls:

- "vacation" vs "PTO" answered "not found"
- the custom-color answer missing its email
- answers built from unrelated text on the wrong shelf
- about 1 in 5 citations pointing at the wrong document

Each fix so far was checked by hand on a few questions (decisions 0007, 0016). The Phase 6 sliders would change retrieval with no way to tell whether answers got better. Measuring first means every later change, including the Phase 6 tuning, can be judged by numbers.

## Decision

**Phase 7 comes before Phase 6.** Phase 6 is unchanged and follows.

**Golden set.** The `eval_sets` and `eval_cases` tables from the initial schema are used and extended (migration 0008):
- each case names a shelf by name (a blue/green swap keeps the name), or none for "All shelves"
- expected source files: any of them counts as a hit
- required facts as groups of alternatives, matched after normalizing case, accents and dashes (the end-to-end test's rule)
- an "expect not found" flag
- a kind and a wording group (variants of one question)

The demo company's set lives in `backend/demo/eval/hilda-luna-golden.json`. It has 53 cases:
- the end-to-end questions, mapped to the demo shelves
- the three manual cases from 2026-11-12/13
- wording variants (vacation/PTO, quit/resignation, Spanish)
- 10 questions whose answer isn't on the shelf searched

A test checks that every required fact is in one of its case's expected files.

**Runner.** A run is a `run_eval` job in the single worker. It can be cancelled between cases, and it never competes with indexing for Ollama. Each case goes through the chat's path:
- the same `retrieve_many` over the case's shelf or all shelves
- the profile's top-k, system prompt, chat model and temperature
- the same prompt builder

The run stores the config, the profile version, and an index snapshot per shelf: documents, chunks, and a fingerprint of the active versions. Two runs then show whether they searched the same index, which is how "two index versions" are compared. Each case's result is copied with the question, so editing the set later doesn't change old runs.

**Metrics.** Retrieval is scored per document, not per chunk: a hit is any chunk from an expected file. That is what a reader checks, and it doesn't break when a reindex renumbers chunks.
- **hit rate@5** and **MRR**, over all fused candidates (20), so a miss still has a rank
- with answers on:
  - **answered** (not "not found")
  - **required facts present**
  - **"not found" when it should be**
  - **citations to the right file**: every cited `[n]` points at an expected file. This catches what `citation_status` can't (decision 0007)
- **LLM-judged faithfulness** (optional): the local chat model answers YES / PARTLY / NO to "is every fact in the answer in the sources?", scored 1 / 0.5 / 0. A 3B judge is weak, so it is a hint to read the answer, not ground truth. The judge model can be set per run.
- **wording groups all passed**: a group counts only if every wording of the question passes

**Modes.** `retrieve_many` takes `mode`: `hybrid` (the chat's), `vector` or `keyword`. These stay on the run, not on profiles, until Phase 6 decides what profiles should hold.

**Reranker.** `bge-reranker-v2-m3` through ONNX Runtime, as an optional install (`requirements-rerank.txt`). The model goes in `DATA_DIR/hf`. It comes in a later change of this phase, with its own measurement.

**CLI.** `python -m app.cli eval` (the app must be stopped) runs a set in-process and prints the totals. It loads the demo set when there is none. `eval-compare A B` compares two runs. The README's eval table will come from these commands.

## Consequences

- Answers on a CPU take about a minute each with `qwen2.5:3b`, so a full run with answers takes about an hour and holds the job queue: uploads wait until it ends or is cancelled. Retrieval-only runs take seconds.
- First numbers on the demo library (retrieval only, top 5):

  | Mode | hit rate@5 | MRR |
  |---|---|---|
  | hybrid | 100% | 0.901 |
  | vector | 96% | 0.844 |
  | keyword | 96% | 0.919 |

  Retrieval finds the right file for every question. The known failures happen in the answer step, so the answer metrics are what the next fixes are measured on.
- Deleting a golden set deletes its runs. There is no trash for eval data: it holds no documents, and the JSON export is the backup.
