from loadtest import percentile


def test_percentile_uses_nearest_rank_for_small_samples():
    assert percentile([4, 1, 3, 2], 0.50) == 2
    assert percentile([4, 1, 3, 2], 0.95) == 4
    assert percentile([], 0.95) is None
