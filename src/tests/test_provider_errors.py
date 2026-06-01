"""
Tests for provider error classification.
No API access required — all exceptions are constructed with mocks.

Run with pytest or directly:  python src/tests/test_provider_errors.py
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import openai
import pytest

# Import provider_errors directly from its directory to avoid triggering
# llm/__init__.py which requires GROQ_* env vars (pulls in llm_client at import time).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from provider_errors import classify_provider_error, format_error_log, SNIPPET_MAX


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _mock_response(status_code: int = 400) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.request = MagicMock()
    resp.headers = MagicMock()
    resp.headers.get = MagicMock(return_value=None)
    return resp


def _bad_request(code: str = "json_validate_failed", failed_gen: str = "") -> openai.BadRequestError:
    body = {
        "error": {
            "message": f"Provider error: {code}",
            "type": "invalid_request_error",
            "code": code,
            "failed_generation": failed_gen,
        }
    }
    return openai.BadRequestError("test", response=_mock_response(400), body=body)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_json_validate_failed_no_content():
    info = classify_provider_error(_bad_request(failed_gen=""))
    assert info["error_class"] == "BadRequestError"
    assert info["http_status"] == 400
    assert info["error_code"] == "json_validate_failed"
    assert info["error_type"] == "invalid_request_error"
    assert info["is_json_validation_failure"] is True
    assert info["is_truncated_output"] is False
    assert info["is_rate_limit"] is False
    assert info["failed_generation"] is None
    assert info["failed_generation_chars"] == 0
    assert info["failed_generation_start"] is None
    assert info["failed_generation_end"] is None


def test_json_validate_failed_with_short_content():
    content = '{"questions": [{"question": "test"'
    info = classify_provider_error(_bad_request(failed_gen=content))
    assert info["failed_generation"] == content
    assert info["failed_generation_chars"] == len(content)
    assert info["failed_generation_start"] == content  # fits in SNIPPET_MAX
    assert info["failed_generation_end"] is None       # short — no end snippet


def test_json_validate_failed_with_long_content():
    start_part = "S" * SNIPPET_MAX
    middle     = "M" * SNIPPET_MAX
    end_part   = "E" * SNIPPET_MAX
    content = start_part + middle + end_part
    info = classify_provider_error(_bad_request(failed_gen=content))
    assert info["failed_generation_chars"] == len(content)
    assert len(info["failed_generation_start"]) == SNIPPET_MAX
    assert len(info["failed_generation_end"]) == SNIPPET_MAX
    assert info["failed_generation_start"] == start_part
    assert info["failed_generation_end"] == end_part


def test_rate_limit():
    exc = openai.RateLimitError("Rate limit exceeded", response=_mock_response(429), body=None)
    info = classify_provider_error(exc)
    assert info["is_rate_limit"] is True
    assert info["http_status"] == 429
    assert info["is_json_validation_failure"] is False


def test_truncated_output():
    mock_completion = MagicMock()
    exc = openai.LengthFinishReasonError(completion=mock_completion)
    info = classify_provider_error(exc)
    assert info["is_truncated_output"] is True
    assert info["http_status"] is None
    assert info["is_json_validation_failure"] is False


def test_content_filter():
    exc = openai.ContentFilterFinishReasonError()
    info = classify_provider_error(exc)
    assert info["is_content_filter"] is True
    assert info["is_truncated_output"] is False


def test_timeout():
    exc = openai.APITimeoutError(request=MagicMock())
    info = classify_provider_error(exc)
    assert info["is_timeout"] is True
    assert info["is_connection"] is False


def test_connection_error():
    exc = openai.APIConnectionError(request=MagicMock())
    info = classify_provider_error(exc)
    assert info["is_connection"] is True
    assert info["is_timeout"] is False


def test_pydantic_validation_error():
    from pydantic import BaseModel, ValidationError
    class M(BaseModel):
        x: int
    try:
        M(x="not_an_int")
    except ValidationError as exc:
        info = classify_provider_error(exc)
        assert info["is_pydantic_validation"] is True
        assert info["is_json_validation_failure"] is False


def test_generic_exception():
    exc = ValueError("something unexpected")
    info = classify_provider_error(exc)
    assert info["error_class"] == "ValueError"
    assert info["http_status"] is None
    assert info["is_json_validation_failure"] is False
    assert info["is_rate_limit"] is False


def test_format_log_contains_key_fields():
    info = classify_provider_error(_bad_request(failed_gen="partial json content"))
    log = format_error_log(info)
    assert "===== PROVIDER ERROR =====" in log
    assert "BadRequestError" in log
    assert "json_validate_failed" in log
    assert "failed_generation_chars" in log
    assert "failed_generation_start" in log


def test_format_log_no_failed_generation():
    info = classify_provider_error(_bad_request(failed_gen=""))
    log = format_error_log(info)
    assert "failed_generation_start" not in log
    assert "failed_generation_end" not in log


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in tests:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} passed.")
