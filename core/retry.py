"""core/retry.py — AI Agent Skill Retry & Fault Tolerance System
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
from typing import Any, Callable, Tuple, Type

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
    """Retry decorator for network operations with exponential backoff.
    
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
    """Retry decorator for skill loading and initialization.
    
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
    """Retry decorator that retries based on return value condition.
    
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
    """Retry decorator with total timeout constraint.
    
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
    """Persistent retry decorator for critical operations.
    
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
        ConnectionError,
        TimeoutError,
        OSError
    )
):
    """Async version of network retry decorator.
    
    Args:
        max_attempts: Maximum number of retry attempts
        max_delay: Maximum delay between retries in seconds
        multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exception types to retry on

    """
    def retry_decorator(coro):
        @wraps(coro)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await coro(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:  # Don't sleep on last attempt
                        delay = min(
                            multiplier * (2 ** attempt) +
                            (0.1 * attempt),  # Small jitter
                            max_delay
                        )
                        logger.warning(
                            f"Attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error("All %s attempts failed. Last error: %s", max_attempts, e)

            raise last_exception
        return wrapper
    return retry_decorator


def circuit_breaker_retry(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    exceptions: Tuple[Type[BaseException], ...] = (
        ConnectionError,
        TimeoutError
    )
):
    """Circuit breaker pattern with retry capability.
    
    Args:
        failure_threshold: Number of consecutive failures before opening circuit
        recovery_timeout: Time in seconds before attempting to close circuit
        exceptions: Tuple of exception types that count as failures

    """
    def retry_decorator(func):
        # Simple circuit breaker state tracking
        state = {'failures': 0, 'last_failure_time': 0, 'open': False}

        @wraps(func)
        def wrapper(*args, **kwargs):

            # Check if circuit is open
            if state['open']:
                time_since_failure = time.time() - state['last_failure_time']
                if time_since_failure >= recovery_timeout:
                    # Attempt to close circuit
                    logger.info("Attempting to reset circuit breaker...")
                    state['open'] = False
                    state['failures'] = 0
                else:
                    raise RuntimeError("Circuit breaker is OPEN")

            try:
                result = func(*args, **kwargs)
                # Reset on success
                state['failures'] = 0
                return result
            except exceptions:
                state['failures'] += 1
                state['last_failure_time'] = time.time()

                if state['failures'] >= failure_threshold:
                    state['open'] = True
                    logger.error("Circuit breaker OPENED after %s failures", failure_threshold)

                raise  # FIX: bare 'raise' preserves original traceback; 'raise e' loses it

        return wrapper
    return retry_decorator


# Predefined retry configurations
network_retry_config = network_retry()
skill_retry_config = skill_retry()
timeout_retry_config = timeout_retry(timeout_seconds=120)


# Example usage functions
async def example_usage():
    """Example usage of retry decorators.
    """

    @network_retry(max_attempts=5)
    def fetch_skill_content_sync(url: str):
        """Example sync function."""
        # Simulate network operation
        if url == "bad_url":
            raise ConnectionError("Failed to connect")
        return f"Fetched content from {url}"

    @async_network_retry(max_attempts=3)
    async def fetch_skill_content_async(url: str):
        """Example async function."""
        # Simulate async network operation
        if url == "bad_url":
            raise ConnectionError("Failed to connect")
        return f"Fetched content from {url}"

    @skill_retry(max_attempts=3)
    def load_skill_module(path: str):
        """Example skill loading function."""
        # Simulate skill loading
        if path == "invalid_path":
            raise ImportError("Module not found")
        return f"Loaded skill from {path}"

    # Test the functions
    try:
        result = fetch_skill_content_sync("good_url")
        print(f"Sync result: {result}")
    except Exception as e:
        print(f"Sync failed: {e}")

    try:
        result = await fetch_skill_content_async("good_url")
        print(f"Async result: {result}")
    except Exception as e:
        print(f"Async failed: {e}")

    try:
        result = load_skill_module("valid_path")
        print(f"Load result: {result}")
    except Exception as e:
        print(f"Load failed: {e}")
