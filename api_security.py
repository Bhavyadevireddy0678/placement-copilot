import hmac
import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException


def require_api_key(provided_key, configured_key):
    if not configured_key:
        raise RuntimeError("API_KEY is not configured")
    provided_bytes = provided_key.encode("utf-8") if provided_key else b""
    configured_bytes = configured_key.encode("utf-8")
    if not provided_bytes or not hmac.compare_digest(provided_bytes, configured_bytes):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class SlidingWindowRateLimiter:
    def __init__(self, max_requests, window_seconds):
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError("Rate-limit settings must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, client_key, now=None):
        current_time = time.monotonic() if now is None else now
        cutoff = current_time - self.window_seconds
        with self.lock:
            client_requests = self.requests[client_key]
            while client_requests and client_requests[0] <= cutoff:
                client_requests.popleft()
            if len(client_requests) >= self.max_requests:
                retry_after = max(
                    1,
                    math.ceil(self.window_seconds - (current_time - client_requests[0])),
                )
                return False, retry_after
            client_requests.append(current_time)
            return True, 0
