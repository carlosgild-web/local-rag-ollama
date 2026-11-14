# 0024: The retrieval inspector: its own read-only endpoint, weighted RRF and a cosine floor

**Status:** accepted (2026-11-14)

## Context

Phase 6 asks for a retrieval inspector: "chunks, scores, final prompt, parameter sliders". It is done when "changing a slider changes retrieval results live in the inspector". `PLAN.md` section 7 lists the sliders as k, threshold, hybrid weight and reranker.

`POST /api/retrieve` already returned chunks and fused scores, but not why a chunk ranked where it did. It had no way to change anything except top-k, and it didn't show the prompt.

The user chose (2026-11-14) to keep the inspector's settings **for exploring only**. They aren't saved in profiles, and the chat behaves exactly as before. Saving retrieval settings in profiles can come later, measured with the evaluation.

## Decision

- **A new endpoint, `POST /api/retrieve/inspect`.** `/api/retrieve` keeps its contract. The inspector's endpoint:
  - reads only: it writes nothing, so there's nothing to audit (invariant 7)
  - returns every fused candidate (up to `candidates`, as the chat's reranker path fetches), marks the top-k the model would see, and gives each chunk its vector rank and cosine, its keyword rank and BM25, its fused RRF score and its reranker score
  - returns the question after glossary expansion and the exact prompt (`build_prompt` with the profile's instructions)
  - returns timings for the embedding, the search and the reranker
  - scope: one shelf, all shelves (the console's "All shelves") or the portal's shelves
- **With the defaults it shows exactly what the chat would send.** A test checks that the sent chunks and the prompt equal `prepare_context`'s output for the same question, shelf and profile.
- **Parameters:**
  - `mode`: hybrid, vector or keyword
  - `top_k`: default from the profile
  - `candidates`: per side, default `RETRIEVAL_CANDIDATES`
  - `vector_weight` (0..1): weighted RRF. Each vector list counts `2w` and the keyword list `2(1-w)`, so 0.5 gives plain RRF's scores exactly. A side weighted 0 is left out rather than adding zeros. With w = 1 the ranking equals vector-only search, and with w = 0 keyword-only search, but the breakdown still shows both sides.
  - `min_cosine` (0..1): vector matches under the floor are dropped before ranking. Keyword matches are never dropped. 0 = off.
  - `rerank`: refused with 409 when the model isn't downloaded.
- **Question embedding cache.** A bounded LRU (64 entries) on the `Runtime`, used only by the inspector. On the demo library the first query took 10 s, almost all of it embedding with `bge-m3` on this CPU. With the cached embedding, a slider move takes about 15 ms. The chat doesn't use the cache.
- **The page** (`/inspector`, under a new "Control panel" group in the sidebar):
  - Sliders re-query after a 300 ms pause. A superseded request is aborted, and the last result stays on screen while the next one loads.
  - Each row shows how far it moved since the previous result. A dashed line marks the top-k cut.
  - The prompt is collapsible, with a copy button.
  - The page lists the settings that differ from the chat's, and a reset button goes back to the chat's settings.
- **No new dependencies.** The sliders are native `<input type="range">`, not a Radix slider.

## Consequences

- `retrieve_many` takes `candidates`, `vector_weight` and `min_cosine`. Their defaults keep the chat, the portal and the evaluation unchanged. The full test suite passed without changes, apart from one monkeypatch signature.
- `RetrievedChunk` carries the per-side ranks and scores. Nothing stores them: `message_sources` still records rank and score only.
- The weighted fusion and the cosine floor are now cheap to try on the golden set. Whether either helps hasn't been measured. If one does, it would go into profiles as a new decision.
