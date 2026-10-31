from caches import CachedEmbeddingEncoder, TTLCache


class CountingModel:
    def __init__(self):
        self.questions = []

    def encode(self, question):
        self.questions.append(question)
        return [question]


def test_embedding_cache_hits_repeats_and_evicts_lru():
    model = CountingModel()
    encoder = CachedEmbeddingEncoder(model, max_size=2)

    assert encoder.encode_with_status("one") == (["one"], False)
    assert encoder.encode_with_status("two") == (["two"], False)
    assert encoder.encode_with_status("one") == (["one"], True)
    assert encoder.encode_with_status("three") == (["three"], False)
    assert encoder.encode_with_status("two") == (["two"], False)
    assert model.questions == ["one", "two", "three", "two"]


def test_embedding_cache_zero_capacity_disables_storage():
    model = CountingModel()
    encoder = CachedEmbeddingEncoder(model, max_size=0)

    encoder.encode("same")
    encoder.encode("same")

    assert model.questions == ["same", "same"]


def test_sql_result_ttl_cache_expires_evicts_and_copies_values():
    cache = TTLCache(max_entries=2, ttl_seconds=5)
    original = {"answer": [1, 2]}
    cache.set("query-a", original, now=10)
    original["answer"].append(3)

    found, result = cache.get("query-a", now=11)
    assert found
    assert result == {"answer": [1, 2]}

    cache.set("query-b", "b", now=11)
    cache.get("query-a", now=12)
    cache.set("query-c", "c", now=12)
    assert cache.get("query-b", now=12) == (False, None)
    assert cache.get("query-a", now=16) == (False, None)


def test_zero_ttl_cache_does_not_store_values():
    cache = TTLCache(max_entries=2, ttl_seconds=0)
    cache.set("query", "answer", now=0)

    assert cache.get("query", now=0) == (False, None)
