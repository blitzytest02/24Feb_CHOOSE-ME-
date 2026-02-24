"""
Exponential retry decorator with credential sanitization for resilient external service calls.

This module implements exponential retry logic using the ``tenacity`` library (v9.1.4) as
the foundation for resilient external service calls throughout the Flask application.  It
wraps or re-exports ``@archie_exponential_retry()`` from ``blitzy-platform-shared`` when
the shared library is installed, and provides a full local fallback implementation using
``tenacity`` when it is not available.

Key responsibilities:
    - Retry transient errors (network timeouts, 5xx HTTP responses, connection errors)
      with configurable exponential backoff
    - Sanitize API keys, passwords, tokens, bearer credentials, and other sensitive data
      from ALL error traces and log messages (AAP Section 0.7.2)
    - Classify HTTP errors as transient (retryable) vs. permanent (non-retryable)
    - Provide convenience decorators with sensible defaults for service modules

Exports:
    archie_exponential_retry    – Primary retry decorator (delegates to shared lib or local)
    sanitize_error_message      – Credential-safe error message sanitizer
    retry_with_sanitization     – Convenience decorator with default retry + sanitization
    is_transient_http_error     – HTTP status code classifier
    DEFAULT_MAX_RETRIES         – Default maximum number of retry attempts (3)
    DEFAULT_WAIT_MIN            – Minimum backoff wait in seconds (1)
    DEFAULT_WAIT_MAX            – Maximum backoff wait in seconds (60)
    DEFAULT_WAIT_MULTIPLIER     – Exponential backoff multiplier (2)
    SENSITIVE_PATTERNS          – Compiled regex patterns for credential redaction
    TRANSIENT_EXCEPTIONS        – Tuple of exception types considered transient
"""

from __future__ import annotations

import asyncio
import functools
import logging
import re
from typing import Any, Callable, Optional, Tuple, Type, Union

import requests
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# ---------------------------------------------------------------------------
# Optional import of the shared-library retry decorator.  The schema specifies
# ``blitzy_platform_shared.decorators`` but the actual installed package (v0.0.618)
# exposes ``archie_exponential_retry`` from ``blitzy_platform_shared.common.utils``.
# We attempt both paths to ensure maximum compatibility.
# ---------------------------------------------------------------------------
_shared_archie_retry: Optional[Callable] = None
try:
    from blitzy_platform_shared.decorators import (  # type: ignore[import-untyped]
        archie_exponential_retry as _shared_archie_retry,
    )
except (ImportError, ModuleNotFoundError):
    try:
        from blitzy_platform_shared.common.utils import (  # type: ignore[import-untyped]
            archie_exponential_retry as _shared_archie_retry,
        )
    except (ImportError, ModuleNotFoundError):
        _shared_archie_retry = None

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default retry configuration constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_RETRIES: int = 3
"""Default maximum number of retry attempts before giving up."""

DEFAULT_WAIT_MIN: int = 1
"""Minimum wait time in seconds between retries (exponential backoff floor)."""

DEFAULT_WAIT_MAX: int = 60
"""Maximum wait time in seconds between retries (exponential backoff ceiling)."""

DEFAULT_WAIT_MULTIPLIER: int = 2
"""Multiplier applied to the exponential backoff calculation."""

# ---------------------------------------------------------------------------
# Sensitive credential patterns (compiled for performance)
# ---------------------------------------------------------------------------

SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    # Bearer and Basic auth tokens in HTTP headers — MUST run before the generic
    # key=value pattern so that "Authorization: Bearer <token>" is fully redacted
    # before the "auth:" prefix could partially consume the header name.
    re.compile(r"(Bearer|Basic)\s+[\w\-\.=\+\/]{6,}", re.IGNORECASE),
    # Provider-specific API key prefixes (OpenAI sk-, Stripe pk-/sk-, generic key-)
    re.compile(r"(sk\-|pk\-|key\-|rk\-)[\w\-]{8,}", re.IGNORECASE),
    # Database connection strings containing passwords
    re.compile(
        r"(mongodb|postgres|mysql|neo4j|bolt|redis)(\+\w+)?://[^:]+:[^@]+@",
        re.IGNORECASE,
    ),
    # Inline environment variable assignments that might leak secrets
    re.compile(
        r"(ANTHROPIC_API_KEY|OPENAI_API_KEY|VOYAGE_API_KEY|NEO4J_PASSWORD"
        r"|GCS_CREDENTIALS|PUBSUB_CREDENTIALS|SECRET_MANAGER_KEY"
        r"|LANGSMITH_API_KEY|DATABASE_URL|DB_PASSWORD)"
        r"[=]\s*[\"']?[\S]{4,}[\"']?",
        re.IGNORECASE,
    ),
    # Generic key=value or key: value patterns for common secret names — runs last
    # to catch remaining credential-like patterns not handled above.
    re.compile(
        r"(api[_\-]?key|api[_\-]?secret|password|passwd|token|secret|credential|auth"
        r"|authorization|access[_\-]?key|private[_\-]?key|client[_\-]?secret)"
        r"[=:]\s*[\"']?[\w\-\.\/\+\=]{4,}[\"']?",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Transient (retryable) exception types
# ---------------------------------------------------------------------------

TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    requests.ConnectionError,
    requests.Timeout,
    ConnectionError,
    TimeoutError,
    OSError,
)

# ---------------------------------------------------------------------------
# HTTP status codes considered transient (retryable)
# ---------------------------------------------------------------------------

_TRANSIENT_HTTP_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


# =========================================================================
# Public helper functions
# =========================================================================


def sanitize_error_message(message: str) -> str:
    """Remove credentials, API keys, tokens, and other sensitive data from *message*.

    This function is the **primary credential-safety enforcement point** across the
    entire application.  Every error message that flows through the retry layer or
    any log statement that might contain request/response data **must** be routed
    through this function first.

    Implements the mandatory credential sanitization rule from
    AAP Section 0.7.2:  "API keys and database credentials must NEVER be exposed
    in error traces, logs, or API responses."

    Args:
        message: Raw error message or traceback string that may contain secrets.

    Returns:
        A copy of *message* with all detected sensitive values replaced by
        ``[REDACTED]``.
    """
    if not message:
        return message

    sanitized: str = message

    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)

    return sanitized


def is_transient_http_error(exception: Exception) -> bool:
    """Determine whether *exception* represents a transient (retryable) HTTP error.

    Transient errors are those that may resolve on a subsequent attempt, such as:

    * HTTP 429 (Too Many Requests) — rate limiting, resolved after backoff
    * HTTP 500 (Internal Server Error) — intermittent server failures
    * HTTP 502 (Bad Gateway) — upstream proxy failures
    * HTTP 503 (Service Unavailable) — temporary overload or maintenance
    * HTTP 504 (Gateway Timeout) — upstream timeout

    Non-transient (permanent) errors — HTTP 400, 401, 403, 404 — are client errors
    that will not resolve on retry and should not be retried.

    Connection-level and timeout exceptions are always considered transient.

    Note:
        ``requests.HTTPError`` is a subclass of ``OSError`` in Python 3, so HTTP
        status-code classification **must** be checked before the generic
        ``TRANSIENT_EXCEPTIONS`` tuple to avoid treating 4xx errors as transient.

    Args:
        exception: The exception instance to classify.

    Returns:
        ``True`` if the error is transient and the operation should be retried;
        ``False`` otherwise.
    """
    # IMPORTANT: Check requests.HTTPError FIRST because it inherits from
    # IOError/OSError, which is in TRANSIENT_EXCEPTIONS.  Without this ordering,
    # every HTTPError (including 400, 401, 403, 404) would be classified transient.
    if isinstance(exception, requests.HTTPError):
        response = getattr(exception, "response", None)
        if response is not None:
            status_code: int = getattr(response, "status_code", 0)
            return status_code in _TRANSIENT_HTTP_STATUS_CODES
        # If no response is attached (e.g. network-level failure), treat as transient
        return True

    # Connection-level and timeout exceptions are always transient
    if isinstance(exception, TRANSIENT_EXCEPTIONS):
        return True

    return False


# =========================================================================
# Core retry decorator — archie_exponential_retry
# =========================================================================


def _build_local_retry_decorator(
    max_retries: int = DEFAULT_MAX_RETRIES,
    wait_min: int = DEFAULT_WAIT_MIN,
    wait_max: int = DEFAULT_WAIT_MAX,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry_callback: Optional[Callable[..., Any]] = None,
) -> Callable:
    """Build a local tenacity-based retry decorator (fallback implementation).

    This is used when ``blitzy-platform-shared`` is not installed or its decorator
    is not importable.  It replicates the core behaviour:

    1. Exponential backoff between ``wait_min`` and ``wait_max`` seconds.
    2. Stops after ``max_retries + 1`` total attempts (initial + retries).
    3. Only retries on the specified exception types (defaults to
       ``TRANSIENT_EXCEPTIONS``).
    4. Logs every retry attempt at ``WARNING`` level via ``before_sleep_log``.
    5. Sanitizes credentials in all error log messages before output.
    6. Supports both synchronous and ``async`` decorated functions.
    """
    effective_exceptions: Tuple[Type[Exception], ...] = retryable_exceptions or TRANSIENT_EXCEPTIONS

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            # ----- Async path -----
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                @retry(
                    stop=stop_after_attempt(max_retries + 1),
                    wait=wait_exponential(
                        multiplier=DEFAULT_WAIT_MULTIPLIER,
                        min=wait_min,
                        max=wait_max,
                    ),
                    retry=retry_if_exception_type(effective_exceptions),
                    before_sleep=before_sleep_log(logger, logging.WARNING),
                    reraise=True,
                )
                async def _inner() -> Any:
                    return await func(*args, **kwargs)

                try:
                    return await _inner()
                except RetryError as retry_err:
                    sanitized = sanitize_error_message(str(retry_err))
                    logger.error(
                        "Retry exhausted for %s after %d attempts: %s",
                        func.__name__,
                        max_retries,
                        sanitized,
                    )
                    raise
                except Exception as exc:
                    sanitized = sanitize_error_message(str(exc))
                    logger.error("Error in %s: %s", func.__name__, sanitized)
                    raise

            if on_retry_callback is not None:
                async_wrapper._on_retry_callback = on_retry_callback  # type: ignore[attr-defined]
            return async_wrapper
        else:
            # ----- Synchronous path -----
            @retry(
                stop=stop_after_attempt(max_retries + 1),
                wait=wait_exponential(
                    multiplier=DEFAULT_WAIT_MULTIPLIER,
                    min=wait_min,
                    max=wait_max,
                ),
                retry=retry_if_exception_type(effective_exceptions),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            )
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    sanitized = sanitize_error_message(str(exc))
                    logger.error("Error in %s: %s", func.__name__, sanitized)
                    raise

            if on_retry_callback is not None:
                sync_wrapper._on_retry_callback = on_retry_callback  # type: ignore[attr-defined]
            return sync_wrapper

    return decorator


def archie_exponential_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    wait_min: int = DEFAULT_WAIT_MIN,
    wait_max: int = DEFAULT_WAIT_MAX,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry_callback: Optional[Callable[..., Any]] = None,
) -> Callable:
    """Exponential-backoff retry decorator for external service calls.

    This is the **primary** retry decorator used across the entire Flask application.
    When ``blitzy-platform-shared`` is installed, it delegates to the shared library's
    ``archie_exponential_retry`` implementation (which includes a broader set of
    provider-specific retryable exceptions).  When the library is unavailable, a
    feature-equivalent local implementation built on ``tenacity`` is used instead.

    Either way, ``from app.utils.retry import archie_exponential_retry`` always works.

    The decorator:
        1. Retries on transient errors (network timeouts, 5xx HTTP responses,
           connection errors) — see ``TRANSIENT_EXCEPTIONS``.
        2. Does **not** retry on 4xx client errors (except 429 Too Many Requests).
        3. Uses exponential backoff between ``wait_min`` and ``wait_max`` seconds.
        4. Sanitizes credentials in **all** error traces and log messages
           (AAP Section 0.7.2).
        5. Logs each retry attempt at ``WARNING`` level.
        6. Supports both synchronous and ``async`` decorated functions.

    Args:
        max_retries:
            Maximum number of retry attempts.  The decorated function is called at
            most ``max_retries + 1`` times (initial attempt + retries).
            Defaults to ``DEFAULT_MAX_RETRIES`` (3).
        wait_min:
            Minimum backoff wait in seconds.  Defaults to ``DEFAULT_WAIT_MIN`` (1).
        wait_max:
            Maximum backoff wait in seconds.  Defaults to ``DEFAULT_WAIT_MAX`` (60).
        retryable_exceptions:
            Tuple of exception types that trigger a retry.  Defaults to
            ``TRANSIENT_EXCEPTIONS`` when ``None``.
        on_retry_callback:
            Optional callback invoked before each retry attempt.

    Returns:
        A decorator that wraps the target function with retry logic.

    Example::

        @archie_exponential_retry(max_retries=5, wait_min=2, wait_max=120)
        def call_external_api(url: str) -> dict:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
    """
    # ----- Delegate to shared library when available -----
    if _shared_archie_retry is not None:
        try:
            return _shared_archie_retry(
                max_retries=max_retries,
                min_wait=wait_min,
                max_wait=wait_max,
                multiplier=DEFAULT_WAIT_MULTIPLIER,
                exceptions=retryable_exceptions or TRANSIENT_EXCEPTIONS,
            )
        except TypeError:
            # Signature mismatch — fall through to local implementation
            logger.warning(
                "blitzy-platform-shared archie_exponential_retry signature mismatch; "
                "using local fallback."
            )

    # ----- Local tenacity-based fallback -----
    return _build_local_retry_decorator(
        max_retries=max_retries,
        wait_min=wait_min,
        wait_max=wait_max,
        retryable_exceptions=retryable_exceptions,
        on_retry_callback=on_retry_callback,
    )


# =========================================================================
# Convenience decorator — retry_with_sanitization
# =========================================================================


def retry_with_sanitization(
    max_retries: int = DEFAULT_MAX_RETRIES,
    wait_min: int = DEFAULT_WAIT_MIN,
    wait_max: int = DEFAULT_WAIT_MAX,
) -> Callable:
    """Convenience retry decorator with default settings and credential sanitization.

    A simpler interface to ``archie_exponential_retry`` for the common case where
    callers want standard retry behaviour with credential-safe error logging and
    do not need to customise retryable exception types or attach a callback.

    Usage::

        @retry_with_sanitization()
        def publish_notification(payload: dict) -> None:
            ...

    Args:
        max_retries: Maximum retry attempts.  Defaults to ``DEFAULT_MAX_RETRIES``.
        wait_min: Minimum backoff seconds.  Defaults to ``DEFAULT_WAIT_MIN``.
        wait_max: Maximum backoff seconds.  Defaults to ``DEFAULT_WAIT_MAX``.

    Returns:
        A decorator that wraps the target function with retry logic and
        credential sanitization.
    """
    return archie_exponential_retry(
        max_retries=max_retries,
        wait_min=wait_min,
        wait_max=wait_max,
        retryable_exceptions=TRANSIENT_EXCEPTIONS,
        on_retry_callback=None,
    )


# =========================================================================
# Module-level __all__ for explicit public API surface
# =========================================================================

__all__: list[str] = [
    "archie_exponential_retry",
    "sanitize_error_message",
    "retry_with_sanitization",
    "is_transient_http_error",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_WAIT_MIN",
    "DEFAULT_WAIT_MAX",
    "DEFAULT_WAIT_MULTIPLIER",
    "SENSITIVE_PATTERNS",
    "TRANSIENT_EXCEPTIONS",
]
