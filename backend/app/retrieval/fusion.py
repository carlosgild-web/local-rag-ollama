"""Reciprocal Rank Fusion: merges multiple ranked id lists into one ranking.

Each list is assumed already sorted best-first; this only needs positions,
not the underlying scores, so it fuses vector cosine similarity and FTS5
bm25 ranks without needing them on a common scale.
"""


def fuse_rrf(ranked_lists: list[list[int]], *, k: int = 60) -> list[int]:
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda item_id: scores[item_id], reverse=True)
