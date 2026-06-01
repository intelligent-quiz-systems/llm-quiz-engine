"""
Structured classification and logging of provider and model errors.

Classifies exceptions from LLM API calls into a consistent ProviderErrorInfo dict.
Does not depend on batching, retry, or quiz_runner modules.
"""
from __future__ import annotations
from typing import TypedDict

import openai
from pydantic import ValidationError as PydanticValidationError

SNIPPET_MAX = 150  # characters per start/end snippet


class ProviderErrorInfo(TypedDict):
    error_class: str
    http_status: int | None
    error_code: str | None           # e.g. "json_validate_failed"
    error_type: str | None           # e.g. "invalid_request_error"
    error_message: str | None
    is_json_validation_failure: bool # BadRequestError with provider-side JSON failure
    is_truncated_output: bool        # LengthFinishReasonError (finish_reason="length")
    is_rate_limit: bool              # RateLimitError
    is_timeout: bool                 # APITimeoutError
    is_connection: bool              # APIConnectionError (excl. timeout)
    is_content_filter: bool          # ContentFilterFinishReasonError
    is_pydantic_validation: bool     # Pydantic ValidationError on our side
    failed_generation: str | None    # None when provider returned no content
    failed_generation_chars: int
    failed_generation_start: str | None
    failed_generation_end: str | None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _body_block(body: object) -> dict:
    """Return the inner error dict from a response body, handling both layouts."""
    if not isinstance(body, dict):
        return {}
    return body.get("error", body)  # type: ignore[return-value]


def _snippet(text: str, start: bool) -> str:
    if start:
        return text[:SNIPPET_MAX]
    return text[-SNIPPET_MAX:]


# ── Main classifier ───────────────────────────────────────────────────────────

def classify_provider_error(exc: Exception) -> ProviderErrorInfo:
    """Extract structured diagnostic info from any exception raised during LLM calls."""
    body = getattr(exc, "body", None)
    block = _body_block(body)

    http_status: int | None = getattr(exc, "status_code", None)
    error_code    = block.get("code")    if block else None
    error_type    = block.get("type")    if block else None
    error_message = (
        getattr(exc, "message", None)
        or (block.get("message") if block else None)
        or str(exc)
    )

    raw_fgen: str | None = block.get("failed_generation") if block else None
    if raw_fgen == "":
        raw_fgen = None

    fgen_chars = len(raw_fgen) if raw_fgen else 0
    fgen_start = _snippet(raw_fgen, start=True)  if raw_fgen else None
    fgen_end   = _snippet(raw_fgen, start=False) if raw_fgen and fgen_chars > SNIPPET_MAX else None

    return ProviderErrorInfo(
        error_class               = type(exc).__name__,
        http_status               = http_status,
        error_code                = error_code,
        error_type                = error_type,
        error_message             = error_message,
        is_json_validation_failure= isinstance(exc, openai.BadRequestError),
        is_truncated_output       = isinstance(exc, openai.LengthFinishReasonError),
        is_rate_limit             = isinstance(exc, openai.RateLimitError),
        is_timeout                = isinstance(exc, openai.APITimeoutError),
        is_connection             = (
            isinstance(exc, openai.APIConnectionError)
            and not isinstance(exc, openai.APITimeoutError)
        ),
        is_content_filter         = isinstance(exc, openai.ContentFilterFinishReasonError),
        is_pydantic_validation    = isinstance(exc, PydanticValidationError),
        failed_generation         = raw_fgen,
        failed_generation_chars   = fgen_chars,
        failed_generation_start   = fgen_start,
        failed_generation_end     = fgen_end,
    )


# ── Log formatter ─────────────────────────────────────────────────────────────

def format_error_log(info: ProviderErrorInfo) -> str:
    """Return a structured log block suitable for printing to stdout."""
    lines = [
        "\n===== PROVIDER ERROR =====",
        f"error_class:              {info['error_class']}",
        f"http_status:              {info['http_status']}",
        f"error_code:               {info['error_code']}",
        f"error_type:               {info['error_type']}",
        f"error_message:            {(info['error_message'] or '')[:200]}",
        f"is_json_validation:       {info['is_json_validation_failure']}",
        f"is_truncated_output:      {info['is_truncated_output']}",
        f"is_rate_limit:            {info['is_rate_limit']}",
        f"is_timeout:               {info['is_timeout']}",
        f"is_connection_error:      {info['is_connection']}",
        f"is_content_filter:        {info['is_content_filter']}",
        f"is_pydantic_validation:   {info['is_pydantic_validation']}",
        f"failed_generation_chars:  {info['failed_generation_chars']}",
    ]
    if info["failed_generation_start"] is not None:
        lines.append(f"failed_generation_start:  {info['failed_generation_start']!r}")
    if info["failed_generation_end"] is not None:
        lines.append(f"failed_generation_end:    {info['failed_generation_end']!r}")
    return "\n".join(lines)
