from contextlib import contextmanager
from types import SimpleNamespace

import ask_api


class FakeConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement, parameters=None):
        self.statements.append(str(statement))


class FakeEngine:
    def __init__(self, fail=False):
        self.connection = FakeConnection()
        self.fail = fail

    @contextmanager
    def begin(self):
        if self.fail:
            raise RuntimeError("database unavailable")
        yield self.connection


class FakeEmbeddingModel:
    def encode(self, question):
        return [0.0] * 384


class FailingGroqClient:
    class Completions:
        def create(self, **kwargs):
            raise TimeoutError("provider unavailable")

    chat = SimpleNamespace(completions=Completions())


def test_rag_sets_statement_timeout_before_retrieval(monkeypatch):
    engine = FakeEngine()
    model = FakeEmbeddingModel()
    observed = {}

    def retrieve(connection, question, embedding, top_k, hybrid):
        observed["timeout_set"] = any(
            "SET LOCAL statement_timeout" in statement
            for statement in connection.statements
        )
        return []

    monkeypatch.setattr(ask_api, "retrieve_chunks", retrieve)
    response = ask_api.answer_rag_question(
        "question", "keyword_rag", model, FailingGroqClient(), engine
    )

    assert observed["timeout_set"]
    assert response["intent"] == "rag"
    assert "enough information" in response["answer"]


def test_rag_database_failure_returns_safe_response(monkeypatch):
    response = ask_api.answer_rag_question(
        "question", "keyword_rag", FakeEmbeddingModel(), FailingGroqClient(), FakeEngine(fail=True)
    )

    assert response["error"] is True
    assert response["sources"] == []
    assert "try again" in response["answer"].lower()
    assert "database unavailable" not in response["answer"]


def test_rag_provider_failure_returns_safe_response(monkeypatch):
    monkeypatch.setattr(
        ask_api,
        "retrieve_chunks",
        lambda *args, **kwargs: [("source context", "sample.txt", 0.1)],
    )
    response = ask_api.answer_rag_question(
        "question", "keyword_rag", FakeEmbeddingModel(), FailingGroqClient(), FakeEngine()
    )

    assert response["error"] is True
    assert response["sources"] == []
    assert "provider unavailable" not in response["answer"]
