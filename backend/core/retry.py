"""
ARA-1 Retry Logic & Circuit Breaker
Uses tenacity for retry with exponential backoff + jitter.
Implements per-service circuit breakers.
"""
from __future__ import annotations

import asyncio
import functools
import time
from collections import defaultdict
from enum import Enum
from typing import Any, Callable, Optional, Type, Tuple

import re

from backend.core.config import settings
from backend.core.errors import (
    ARA1Error,
    CircuitOpenError,
    RateLimitError,
    ExternalServiceError,
)
from backend.core.logging import get_logger

logger = get_logger(__name__)


def _extract_retry_delay(exc: Exception) -> float:
    """Extract retryDelay from Gemini 429 response body, default 20s."""
    try:
        msg = str(exc)
        import re
        m = re.search(r"retryDelay.*?(\d+)s", msg)
        if m:
            return float(m.group(1)) + 2.0  # Add 2s buffer
    except Exception:
        pass
    return 20.0  # Safe default for free tier


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if exception is a 429 rate limit from Gemini/OpenAI."""
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "quota" in msg or "resource_exhausted" in msg


# ── Circuit Breaker ───────────────────────────────────────────
class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing — reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Per-service circuit breaker."""

    def __init__(
        self,
        service: str,
        failure_threshold: int = None,
        timeout: int = None,
    ):
        self.service = service
        self.failure_threshold = failure_threshold or settings.circuit_breaker_threshold
        self.timeout = timeout or settings.circuit_breaker_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.monotonic() - self.last_failure_time > self.timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info("circuit_breaker_half_open", service=self.service)
                else:
                    raise CircuitOpenError(
                        f"Circuit breaker OPEN for service '{self.service}'",
                        service=self.service,
                        code="CIRCUIT_OPEN",
                    )

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    logger.info("circuit_breaker_closed", service=self.service)
            return result
        except Exception as exc:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.monotonic()
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger.warning(
                        "circuit_breaker_opened",
                        service=self.service,
                        failures=self.failure_count,
                    )
            raise


# Global registry of circuit breakers
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(service: str) -> CircuitBreaker:
    if service not in _circuit_breakers:
        _circuit_breakers[service] = CircuitBreaker(service)
    return _circuit_breakers[service]


# ── Retry Decorator ───────────────────────────────────────────
def with_retry(
    max_attempts: int = None,
    min_wait: float = None,
    max_wait: float = None,
    retry_on: Tuple[Type[Exception], ...] = (ExternalServiceError,),
    service: Optional[str] = None,
):
    """
    Decorator: async retry with exponential backoff + jitter.
    Handles Gemini 429 rate-limit errors by waiting the suggested retry delay.
    Optionally wraps calls through a circuit breaker.
    """
    _max_attempts = max_attempts or settings.max_retries
    _min_wait = min_wait or settings.retry_min_wait
    _max_wait = max_wait or settings.retry_max_wait

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = get_circuit_breaker(service or func.__name__) if service else None
            last_exc: Exception = RuntimeError("Unknown error")

            for attempt_num in range(_max_attempts):
                try:
                    if cb:
                        return await cb.call(func, *args, **kwargs)
                    return await func(*args, **kwargs)

                except Exception as exc:
                    last_exc = exc

                    # Handle Gemini 429 rate-limit explicitly
                    if _is_rate_limit_error(exc):
                        wait_time = _extract_retry_delay(exc)
                        logger.warning(
                            "rate_limit_hit",
                            service=service or func.__name__,
                            attempt=attempt_num + 1,
                            wait_seconds=wait_time,
                        )
                        if attempt_num < _max_attempts - 1:
                            await asyncio.sleep(wait_time)
                        continue

                    # For other errors, only retry if in retry_on tuple
                    if isinstance(exc, retry_on):
                        wait_time = min(
                            _max_wait,
                            _min_wait * (2 ** attempt_num) + 1.0,
                        )
                        logger.warning(
                            "retry_attempt",
                            service=service or func.__name__,
                            attempt=attempt_num + 1,
                            wait_seconds=wait_time,
                            error=str(exc),
                        )
                        if attempt_num < _max_attempts - 1:
                            await asyncio.sleep(wait_time)
                        continue

                    # Non-retryable error — raise immediately
                    raise

            raise last_exc

        return wrapper

    return decorator



# ── Rate Limit Handler ────────────────────────────────────────
class RateLimitHandler:
    """Tracks per-service rate limits and enforces waits."""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, service: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        calls = [t for t in self._windows[service] if now - t < window]
        self._windows[service] = calls
        if len(calls) >= limit:
            return True
        self._windows[service].append(now)
        return False

    async def wait_if_limited(
        self, service: str, limit: int = 60, window: float = 60.0
    ) -> None:
        if self.is_rate_limited(service, limit, window):
            wait = window / limit
            logger.info("rate_limit_wait", service=service, wait_seconds=wait)
            await asyncio.sleep(wait)


rate_limiter = RateLimitHandler()
