"""Reciprocal Rank Fusion: merges multiple ranked id lists into one ranking.

Each list is assumed already sorted best-first; this only needs positions,
not the underlying scores, so it fuses vector cosine similarity and FTS5
bm25 ranks without needing them on a common scale.
"""


def fuse_rrf(ranked_lists: list[list[int]], *, k: int = 60) -> list[int]:
    return [item_id for item_id, _ in fuse_rrf_scored(ranked_lists, k=k)]


def fuse_rrf_scored(ranked_lists: list[list[int]], *, k: int = 60) -> list[tuple[int, float]]:
    """Like `fuse_rrf`, but keeps each id's fused score (stored per answer in
    message_sources, CLAUDE.md invariant 5)."""
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
