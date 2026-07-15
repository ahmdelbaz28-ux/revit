# File-level suppression removed per audit (V143 hardening).
# Per-line justified suppressions (e.g., '# noqa: S3776 ...') are preserved.
"""
core/retry.py — AI Agent Skill Retry & Fault Tolerance System.
=============================================================

Production-ready retry mechanism using Tenacity patterns.
Implements sophisticated retry strategies for network operations and skill loading.

ARCHITECTURE:
- @retry decorator patterns with configurable strategies
- Wait strategies (exponential, fixed, random)
- Stop strategies (timeout, max attempts)
- Specific exception handling

USAGE:
    from core.retry import network_retry, skill_retry
    @network_retry(max_attempts=5)
    async def fetch_skill_content(url: str):
        ...
"""

import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_random_exponential,
)


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is in the OPEN state."""
    pass


class CircuitBreaker:
    """
    Simple circuit breaker implementation to prevent cascading failures.

    When failures exceed the threshold, the circuit opens and subsequent
    calls fail fast without attempting the operation.
    """
    def __init__(self, max_failures: int = 5, reset_timeout: int = 30):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.opened_at: Optional[float] = None
        self.last_failure_time: Optional[float] = None
        self.is_open_flag = False
        self._lock = asyncio.Lock()  # Add async lock for thread safety

    async def is_open(self) -> bool:
        """Check if the circuit breaker is in OPEN state."""
        if self.failures < self.max_failures:
            return False
        if self.opened_at is None:
            self.opened_at = time.time()
            return True

        elapsed = time.time() - self.opened_at
        if elapsed > self.reset_timeout:
            await self.reset()
            return False

        return True

    async def record_failure(self) -> None:
        """Record a failure and potentially open the circuit."""
        async with self._lock:
            self.failures += 1
            if self.failures >= self.max_failures and self.opened_at is None:
                self.opened_at = time.time()

    async def reset(self) -> None:
        """Reset the circuit breaker to CLOSED state."""
        async with self._lock:
            self.failures = 0
            self.opened_at = None


    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Execute the function, applying circuit breaker logic."""
        if await self.is_open():
            raise CircuitBreakerOpenError("Circuit breaker is open")
        try:
            result = await func(*args, **kwargs)
            await self.reset()
            return result
        except Exception:
            await self.record_failure()
            raise

logger = logging.getLogger(__name__)


def network_retry(
    max_attempts: int = 3,
    max_delay: int = 300,  # 5 minutes max
    multiplier: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
        OSError
    )
):
    """
    Retry decorator for network operations with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        max_delay: Maximum delay between retries in seconds
        multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exception types to retry on

    """
    def retry_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(
                    multiplier=multiplier,
                    min=1,
                    max=max_delay
                ),
                retry=retry_if_exception_type(exceptions),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                after=after_log(logger, logging.INFO),
                reraise=True,
            )(func)(*args, **kwargs)
        return wrapper
    return retry_decorator


def skill_retry(
    max_attempts: int = 5,
    max_delay: int = 30,  # 30 seconds max
    multiplier: float = 0.5,
    exceptions: Tuple[Type[BaseException], ...] = (
        ImportError,
        ModuleNotFoundError,
        AttributeError,
        SyntaxError
    )
):
    """
    Retry decorator for skill loading and initialization.

    Args:
        max_attempts: Maximum number of retry attempts
        max_delay: Maximum delay between retries in seconds
        multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exception types to retry on

    """
    def retry_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(
                    multiplier=multiplier,
                    min=1,
                    max=max_delay
                ),
                retry=retry_if_exception_type(exceptions),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                after=after_log(logger, logging.INFO),
                reraise=True,
            )(func)(*args, **kwargs)
        return wrapper
    return retry_decorator


def conditional_retry(
    condition_func: Callable[[Any], bool],
    max_attempts: int = 3,
    max_delay: int = 60
):
    """
    Retry decorator that retries based on return value condition.

    Args:
        condition_func: Function that returns True if retry is needed
        max_attempts: Maximum number of retry attempts
        max_delay: Maximum delay between retries in seconds

    """
    def retry_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_random_exponential(multiplier=1, max=max_delay),
                retry=retry_if_result(condition_func),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                after=after_log(logger, logging.INFO),
                reraise=True,
            )(func)(*args, **kwargs)
        return wrapper
    return retry_decorator


def timeout_retry(
    timeout_seconds: int = 60,
    max_delay: int = 10,
    exceptions: Tuple[Type[BaseException], ...] = (TimeoutError,)
):
    """
    Retry decorator with total timeout constraint.

    Args:
        timeout_seconds: Total timeout in seconds
        max_delay: Maximum delay between retries in seconds
        exceptions: Tuple of exception types to retry on

    """
    def retry_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry(
                stop=stop_after_delay(timeout_seconds),
                wait=wait_random_exponential(multiplier=1, max=max_delay),
                retry=retry_if_exception_type(exceptions),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                after=after_log(logger, logging.INFO),
                reraise=True,
            )(func)(*args, **kwargs)
        return wrapper
    return retry_decorator


def persistent_retry(
    max_attempts: int = 10,
    exceptions: Tuple[Type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
        RuntimeError
    )
):
    """
    Persistent retry decorator for critical operations.

    Args:
        max_attempts: Maximum number of retry attempts (high for critical ops)
        exceptions: Tuple of exception types to retry on

    """
    def retry_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_random_exponential(multiplier=1, max=60),
                retry=retry_if_exception_type(exceptions),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                after=after_log(logger, logging.INFO),
                reraise=True,
            )(func)(*args, **kwargs)
        return wrapper
    return retry_decorator


def async_network_retry(
    max_attempts: int = 3,
    max_delay: int = 300,
    multiplier: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = (
        TimeoutError,
        ConnectionError,
        OSError,
    )
):
    """Async version of network retry decorator."""
    def retry_decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(
                    multiplier=multiplier,
                    min=1,
                    max=max_delay
                ),
                retry=retry_if_exception_type(exceptions),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                after=after_log(logger, logging.INFO),
                reraise=True,
            )(func)(*args, **kwargs)
        return wrapper
    return retry_decorator
