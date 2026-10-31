import pytest
from fastapi import HTTPException
from types import SimpleNamespace
import time

from api_security import SlidingWindowRateLimiter, require_api_key


def test_api_key_requires_matching_nonempty_key():
    require_api_key("correct-key", "correct-key")
    with pytest.raises(HTTPException) as error:
        require_api_key("wrong-key", "correct-key")
    assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        require_api_key("clé-invalide", "correct-key")
    assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        require_api_key(None, "correct-key")
    assert error.value.status_code == 401


def test_api_key_configuration_is_required():
    with pytest.raises(RuntimeError, match="API_KEY is not configured"):
        require_api_key("provided", "")


def test_sliding_window_rate_limit_and_retry_after():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10)

    assert limiter.check("client-a", now=100) == (True, 0)
    assert limiter.check("client-a", now=104) == (True, 0)
    allowed, retry_after = limiter.check("client-a", now=106)
    assert not allowed
    assert retry_after == 4
    assert limiter.check("client-b", now=106) == (True, 0)
    assert limiter.check("client-a", now=111) == (True, 0)


def test_invalid_rate_limit_configuration_is_rejected():
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(max_requests=0, window_seconds=10)


def test_ask_endpoint_returns_429_and_retry_after(monkeypatch):
    import ask_api

    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=10)
    limiter.check("127.0.0.1", now=time.monotonic())
    monkeypatch.setattr(ask_api, "API_KEY", "correct-key")
    monkeypatch.setattr(ask_api, "rate_limiter", limiter)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    with pytest.raises(HTTPException) as error:
        ask_api.ask(
            ask_api.AskRequest(question="a question"),
            request,
            x_api_key="correct-key",
        )

    assert error.value.status_code == 429
    assert int(error.value.headers["Retry-After"]) > 0
