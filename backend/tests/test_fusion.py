from app.retrieval.fusion import fuse_rrf


def test_item_in_both_lists_outranks_item_in_one():
    vector_ranked = [1, 2, 3]
    fts_ranked = [2, 4, 5]
    fused = fuse_rrf([vector_ranked, fts_ranked])
    assert fused[0] == 2  # appears near the top of both lists


def test_single_list_preserves_order():
    fused = fuse_rrf([[3, 1, 2]])
    assert fused == [3, 1, 2]


def test_disjoint_lists_are_interleaved_by_rank():
    fused = fuse_rrf([[1, 2], [3, 4]])
    # rank-1 items (1 and 3) tie and must both outrank rank-2 items (2 and 4)
    assert set(fused[:2]) == {1, 3}
    assert set(fused[2:]) == {2, 4}


def test_empty_lists_yield_empty_result():
    assert fuse_rrf([[], []]) == []
