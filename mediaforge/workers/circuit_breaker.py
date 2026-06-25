"""Lightweight circuit breaker for external API calls.

States:
  CLOSED  — requests flow normally, failures are counted.
  OPEN    — all requests fail-fast with CircuitOpenError for `recovery_timeout` seconds.
  HALF_OPEN — one probe request is allowed through; success → CLOSED, failure → OPEN.

Usage:
    from mediaforge.workers.circuit_breaker import circuit_breaker, CircuitOpenError

    breaker = circuit_breaker("openrouter")

    async def call_api():
        if not breaker.allow_request():
            raise CircuitOpenError(breaker.name)
        try:
            result = await do_request()
            breaker.record_success()
            return result
        except Exception as exc:
            breaker.record_failure()
            raise
"""

import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    def __init__(self, name: str):
        super().__init__(f"Circuit breaker '{name}' is OPEN — failing fast")
        self.breaker_name = name


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_allowed = False

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_allowed = True
        return self._state

    def allow_request(self) -> bool:
        s = self.state
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.HALF_OPEN and self._half_open_allowed:
            self._half_open_allowed = False
            return True
        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN


_breakers: dict[str, CircuitBreaker] = {}


def circuit_breaker(
    name: str = "openrouter",
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, failure_threshold, recovery_timeout)
    return _breakers[name]
