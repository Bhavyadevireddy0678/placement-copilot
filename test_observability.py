import asyncio
import json
import logging

from starlette.requests import Request
from starlette.responses import Response

import ask_api


def test_request_middleware_returns_id_and_one_structured_log(caplog):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "headers": [(b"x-request-id", b"test-request-id")],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
    }
    request = Request(scope)

    async def call_next(_request):
        return Response(status_code=200)

    with caplog.at_level(logging.INFO, logger="ask_api"):
        response = asyncio.run(ask_api.request_logging_middleware(request, call_next))

    records = [
        record for record in caplog.records
        if record.name == "ask_api" and json.loads(record.message).get("event") == "http_request"
    ]
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert len(records) == 1
    assert json.loads(records[0].message)["status_code"] == 200
