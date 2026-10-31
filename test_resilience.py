from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from resilience import (
    CircuitBreaker,
    CircuitOpenError,
    LLMResilience,
    LLMUnavailableError,
    is_transient_provider_error,
)


class ProviderError(Exception):
    def __init__(self, status_code):
        super().__init__("provider failure")
        self.status_code = status_code


class FakeEngine:
    @contextmanager
    def begin(self):
        yield SimpleNamespace(execute=lambda *args, **kwargs: None)


def test_transient_provider_errors_are_classified():
    assert is_transient_provider_error(ProviderError(429))
    assert is_transient_provider_error(ProviderError(503))
    assert not is_transient_provider_error(ProviderError(400))


def test_retries_transient_error_with_exponential_backoff_and_jitter():
    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
    delays = []
    calls = []

    def operation():
        calls.append(True)
        if len(calls) < 3:
            raise ProviderError(503)
        return "ok"

    resilience = LLMResilience(
        breaker,
        max_attempts=3,
        base_delay=0.1,
        max_delay=1,
        jitter_seconds=0.05,
        sleeper=delays.append,
        random_uniform=lambda _low, high: high,
    )

    assert resilience.call(operation) == "ok"
    assert delays == pytest.approx([0.15, 0.25])
    assert len(calls) == 3
    assert breaker.failure_count == 0


def test_non_transient_provider_error_is_not_retried():
    calls = []
    resilience = LLMResilience(
        CircuitBreaker(failure_threshold=5),
        max_attempts=3,
        sleeper=lambda _delay: None,
    )

    def operation():
        calls.append(True)
        raise ProviderError(400)

    with pytest.raises(LLMUnavailableError):
        resilience.call(operation)
    assert len(calls) == 1


def test_circuit_opens_and_fails_fast_after_repeated_failures():
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=30)
    resilience = LLMResilience(
        breaker,
        max_attempts=2,
        base_delay=0,
        jitter_seconds=0,
        sleeper=lambda _delay: None,
    )
    calls = []

    def operation():
        calls.append(True)
        raise ProviderError(503)

    with pytest.raises(LLMUnavailableError):
        resilience.call(operation)
    assert len(calls) == 2
    with pytest.raises(CircuitOpenError):
        resilience.call(operation)
    assert len(calls) == 2


def test_circuit_allows_a_successful_half_open_probe():
    current_time = [0]
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=10,
        clock=lambda: current_time[0],
    )
    resilience = LLMResilience(
        breaker,
        max_attempts=1,
        sleeper=lambda _delay: None,
    )

    with pytest.raises(LLMUnavailableError):
        resilience.call(lambda: (_ for _ in ()).throw(ProviderError(503)))
    current_time[0] = 11

    assert resilience.call(lambda: "recovered") == "recovered"
    assert breaker.failure_count == 0
    assert breaker.opened_at is None


def test_circuit_failure_returns_explicit_degraded_rag_response(monkeypatch):
    import ask_api

    monkeypatch.setattr(
        ask_api,
        "retrieve_chunks",
        lambda *args, **kwargs: [("context", "sample.txt", 0.1)],
    )
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=30)
    resilience = LLMResilience(
        breaker,
        max_attempts=1,
        sleeper=lambda _delay: None,
    )

    class GroqClient:
        class Completions:
            def create(self, **kwargs):
                raise ProviderError(503)

        chat = SimpleNamespace(completions=Completions())

    response = ask_api.answer_rag_question(
        "question",
        "keyword_rag",
        SimpleNamespace(encode=lambda _question: [0.0] * 384),
        GroqClient(),
        FakeEngine(),
        llm_resilience=resilience,
    )

    assert response["degraded"] is True
    assert response["error"] is True
    assert "temporarily unavailable" in response["answer"]
