"""Reciprocal Rank Fusion: merges multiple ranked id lists into one ranking.

Each list is assumed already sorted best-first; this only needs positions,
not the underlying scores, so it fuses vector cosine similarity and FTS5
bm25 ranks without needing them on a common scale.
"""


def fuse_rrf(ranked_lists: list[list[int]], *, k: int = 60) -> list[int]:
    return [item_id for item_id, _ in fuse_rrf_scored(ranked_lists, k=k)]


def fuse_rrf_scored(
    ranked_lists: list[list[int]], *, k: int = 60, weights: list[float] | None = None
) -> list[tuple[int, float]]:
    """Like `fuse_rrf`, but keeps each id's fused score (stored per answer in
    message_sources, CLAUDE.md invariant 5). `weights` scales each list's
    contribution (weighted RRF); omitted = 1.0 each."""
    if weights is not None and len(weights) != len(ranked_lists):
        raise ValueError("one weight per ranked list")
    scores: dict[int, float] = {}
    for i, ranked in enumerate(ranked_lists):
        weight = 1.0 if weights is None else weights[i]
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
