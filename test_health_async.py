import inspect
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import ask_api


class FakeConnection:
    def __init__(self):
        self.queries = []

    def execute(self, query):
        self.queries.append(str(query))


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()

    @contextmanager
    def connect(self):
        yield self.connection


def test_health_checks_model_and_both_databases(monkeypatch):
    rag_engine = FakeEngine()
    sql_engine = FakeEngine()
    application = SimpleNamespace(
        state=SimpleNamespace(embedding_model=object())
    )
    request = SimpleNamespace(app=application)
    monkeypatch.setattr(ask_api, "rag_engine", rag_engine)
    monkeypatch.setattr(ask_api, "sql_engine", sql_engine)

    assert ask_api.health(request) == {"status": "ready"}
    assert rag_engine.connection.queries == ["SELECT 1"]
    assert sql_engine.connection.queries == ["SELECT 1"]


def test_health_returns_503_when_model_is_not_loaded(monkeypatch):
    application = SimpleNamespace(state=SimpleNamespace())
    request = SimpleNamespace(app=application)

    with pytest.raises(HTTPException) as error:
        ask_api.health(request)

    assert error.value.status_code == 503


def test_blocking_endpoints_are_sync_fastapi_handlers():
    assert not inspect.iscoroutinefunction(ask_api.ask)
    assert not inspect.iscoroutinefunction(ask_api.health)
