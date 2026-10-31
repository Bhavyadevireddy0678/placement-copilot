import pytest

from retrieval import HYBRID_QUERY, VECTOR_QUERY, retrieve_chunks


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, parameters):
        self.calls.append((query, parameters))
        return self

    def fetchall(self):
        return []


def test_vector_mode_uses_cosine_query_and_configured_top_k():
    connection = FakeConnection()

    assert retrieve_chunks(connection, "question", [0.1], top_k=5, hybrid=False) == []
    query, parameters = connection.calls[0]

    assert query is VECTOR_QUERY
    assert parameters["top_k"] == 5


def test_hybrid_mode_uses_fts_and_reciprocal_rank_fusion():
    connection = FakeConnection()

    retrieve_chunks(connection, "eligibility rules", [0.1], top_k=3, hybrid=True)
    query, parameters = connection.calls[0]
    query_text = str(query)

    assert query is HYBRID_QUERY
    assert parameters["candidate_limit"] == 20
    assert parameters["question"] == "eligibility rules"
    assert "search_vector @@ plainto_tsquery('english', :question)" in query_text
    assert "SUM(1.0 / (60 + result_rank))" in query_text


def test_retrieval_rejects_nonpositive_top_k():
    with pytest.raises(ValueError):
        retrieve_chunks(FakeConnection(), "question", [0.1], top_k=0)
