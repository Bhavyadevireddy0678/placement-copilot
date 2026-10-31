import random
import threading
import time


class LLMUnavailableError(RuntimeError):
    pass


class CircuitOpenError(LLMUnavailableError):
    pass


def is_transient_provider_error(error):
    status_code = getattr(error, "status_code", None)
    if status_code in (408, 409, 425, 429):
        return True
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return True
    return type(error).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
        "TimeoutError",
        "ConnectionError",
    }


class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=30, clock=None):
        if failure_threshold < 1 or recovery_timeout <= 0:
            raise ValueError("Circuit breaker settings must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.clock = clock or time.monotonic
        self.failure_count = 0
        self.opened_at = None
        self.half_open_in_flight = False
        self.lock = threading.Lock()

    def before_call(self):
        with self.lock:
            if self.opened_at is None:
                return
            if self.clock() - self.opened_at < self.recovery_timeout:
                raise CircuitOpenError("LLM circuit is open")
            if self.half_open_in_flight:
                raise CircuitOpenError("LLM circuit recovery probe is in progress")
            self.half_open_in_flight = True

    def record_success(self):
        with self.lock:
            self.failure_count = 0
            self.opened_at = None
            self.half_open_in_flight = False

    def record_failure(self):
        with self.lock:
            self.half_open_in_flight = False
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.opened_at = self.clock()


class LLMResilience:
    def __init__(
        self,
        circuit_breaker,
        max_attempts=3,
        base_delay=0.2,
        max_delay=2.0,
        jitter_seconds=0.1,
        sleeper=None,
        random_uniform=None,
    ):
        if max_attempts < 1 or base_delay < 0 or max_delay < 0 or jitter_seconds < 0:
            raise ValueError("Retry settings must be non-negative with at least one attempt")
        self.circuit_breaker = circuit_breaker
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_seconds = jitter_seconds
        self.sleeper = sleeper or time.sleep
        self.random_uniform = random_uniform or random.uniform

    def call(self, operation):
        for attempt in range(self.max_attempts):
            self.circuit_breaker.before_call()
            try:
                result = operation()
            except Exception as error:
                self.circuit_breaker.record_failure()
                if not is_transient_provider_error(error):
                    raise LLMUnavailableError("LLM provider request failed") from error
                if attempt + 1 >= self.max_attempts:
                    raise LLMUnavailableError("LLM provider retries exhausted") from error
                exponential_delay = min(
                    self.max_delay,
                    self.base_delay * (2 ** attempt),
                )
                delay = exponential_delay + self.random_uniform(0, self.jitter_seconds)
                self.sleeper(delay)
            else:
                self.circuit_breaker.record_success()
                return result
        raise LLMUnavailableError("LLM provider retries exhausted")


def resilient_chat_completion(client, resilience, **request_options):
    operation = lambda: client.chat.completions.create(**request_options)
    if resilience is None:
        return operation()
    return resilience.call(operation)
