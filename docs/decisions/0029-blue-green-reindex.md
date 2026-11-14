# 0029: Blue/green rebuilds when the embedding model or chunking changes

**Status:** accepted (Phase 3, written down 2026-11-14; the mechanics are in [0003](0003-per-collection-chunks.md))

## Context

Vectors from two embedding models live in different spaces. A `bge-m3` question vector compared with `nomic-embed-text` passages gives meaningless scores, with no error. Changing the chunk size changes every chunk. So a change of model or chunking means rebuilding a shelf's whole index (invariant 4). On a laptop that takes minutes to hours, and the shelf must keep answering meanwhile.

## Decision

- **A new collection for each generation.** Each `collections` row stores its embedding model, chunk size, overlap and Chroma collection name. A rebuild never changes those on a live collection.
- **Three steps in one background job** (`versioning/service.py`):
  1. `start_collection_rebuild`: creates the next generation, inactive, with the new settings.
  2. `build_collection`: re-chunks and re-embeds **every version** of every document into it, trashed documents included, so rollback and restore keep working without re-embedding ([0028](0028-active-version-pointer.md)). Progress shows on the Jobs page.
  3. `swap_collection`: one SQLite transaction marks the new generation active, the old one inactive, and moves the documents over. It keeps the portal setting and writes `collection_swap` to the audit log.
- **The old generation answers until the swap**, and it stays afterwards (inactive, vectors kept), so the change can be compared or undone. The **Collections** page lists retired copies. New uploads to the shelf go to whichever generation is live when the job runs. `test_an_ingest_job_queued_before_a_swap_lands_in_the_live_generation` covers that race.
- **Mixed vectors are refused at the bottom.** Both vector stores raise on a model mismatch ([0027](0027-chroma-behind-an-interface.md)), and retrieval groups shelves by model and fuses them by rank, never by score.

## Consequences

- No downtime and no half-built index in service: the swap is one commit, and a failed or cancelled build never reaches the swap, so the live shelf is untouched. The partial generation stays inactive.
- A rebuild needs room for two copies of the shelf's vectors until the old one is removed.
- One job worker means a rebuild delays other jobs on the queue. That's intended: embedded Chroma and SQLite are single-writer.

Tested in `test_blue_green_rebuild_serves_old_until_swap_then_keeps_it`, `test_rebuild_job_builds_then_swaps`, `test_only_generations_of_the_same_shelf_can_be_swapped` and `test_swap_keeps_the_portal_setting`.

## Alternatives considered

- **Rebuild in place:** simpler, but the shelf answers badly or not at all for the whole rebuild, and there's no way back.
- **Store several models' vectors per chunk:** every upload pays for two embeddings, and nothing prevents comparing them by mistake.
