"""Retry transient upstream LLM failures (HTTP 5xx, rate limits, timeouts)."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_transient_llm_error(exc: Exception) -> bool:
    """Best-effort detection without tight coupling to a single SDK version."""
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        resp = getattr(exc, "response", None)
        if resp is not None:
            status = getattr(resp, "status_code", None)
    if isinstance(status, int):
        if status in (408, 425, 429):
            return True
        if status >= 500:
            return True

    msg_l = str(exc).lower()
    if "internal server error" in msg_l:
        return True
    if "error code: 500" in msg_l or "error code: 502" in msg_l or "error code: 503" in msg_l:
        return True
    if "error code: 529" in msg_l or "status code 529" in msg_l:
        return True

    try:
        import openai

        if isinstance(exc, openai.APIError):
            # Subclasses (InternalServerError, RateLimitError) usually set status_code on the instance.
            api_status = getattr(exc, "status_code", None)
            if isinstance(api_status, int) and (api_status >= 500 or api_status == 429):
                return True
    except ImportError:
        pass

    name = type(exc).__name__
    # OpenAI / httpx common transient types
    if name in (
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "RemoteProtocolError",
        "InternalServerError",
        "GatewayTimeoutError",
    ):
        return True
    return False


def invoke_with_transient_retries(fn: Callable[[], T]) -> T:
    """Run ``fn`` with exponential backoff on transient errors."""
    raw = os.getenv("TRADINGAGENTS_LLM_TRANSIENT_RETRIES", "8").strip()
    try:
        attempts = max(1, int(raw))
    except ValueError:
        attempts = 8

    base_delay = float(os.getenv("TRADINGAGENTS_LLM_TRANSIENT_BACKOFF_BASE", "1.25"))
    max_delay_s = float(os.getenv("TRADINGAGENTS_LLM_TRANSIENT_BACKOFF_CAP", "45"))

    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if not is_transient_llm_error(exc) or i == attempts - 1:
                raise
            delay = min(max_delay_s, base_delay * (2**i) * (0.75 + 0.5 * random.random()))
            logger.warning(
                "LLM transient error (%s: %s), sleeping %.1fs (%d/%d)",
                type(exc).__name__,
                exc,
                delay,
                i + 1,
                attempts,
            )
            time.sleep(delay)
    raise AssertionError("unreachable") from last
