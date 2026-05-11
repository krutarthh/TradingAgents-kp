"""Tests for LLM transient retry helper."""

import pytest

from tradingagents.llm_clients.transient_retry import (
    invoke_with_transient_retries,
    is_transient_llm_error,
)


class _Err500(Exception):
    status_code = 500


class _Err400(Exception):
    status_code = 400


def test_is_transient_llm_error_recognizes_status_codes():
    assert is_transient_llm_error(_Err500())
    assert is_transient_llm_error(type("E", (), {"status_code": 429})())
    assert not is_transient_llm_error(_Err400())


def test_invoke_with_transient_retries_succeeds_after_failure(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_TRANSIENT_RETRIES", "4")
    monkeypatch.setenv("TRADINGAGENTS_LLM_TRANSIENT_BACKOFF_BASE", "0.01")

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _Err500("upstream boom")
        return "ok"

    assert invoke_with_transient_retries(flaky) == "ok"
    assert calls["n"] == 3


def test_invoke_with_transient_retries_reraises_non_transient():
    def boom():
        raise ValueError("logic")

    with pytest.raises(ValueError, match="logic"):
        invoke_with_transient_retries(boom)


def test_is_transient_llm_error_matches_error_code_string():
    class Weird(Exception):
        pass

    assert is_transient_llm_error(
        Weird("Error code: 500 - {'error': 'Internal Server Error'}")
    )
