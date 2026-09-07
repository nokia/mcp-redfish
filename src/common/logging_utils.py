# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Logging helpers that prevent credentials from reaching log handlers."""

from __future__ import annotations

import logging
import os
import re

_AUTH_HEADER_PATTERN = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*[\"']?)"
    r"(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_BASIC_PATTERN = re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{8,}")
_SENSITIVE_QUERY_PATTERN = re.compile(
    r"(?i)([?&](?:access_token|id_token|refresh_token|token|code|client_secret|"
    r"password|api_key)=)[^&\s]+"
)
_PEM_KEY_PATTERN = re.compile(
    r"-----BEGIN [^-]*(?:PRIVATE|PUBLIC) KEY-----.*?"
    r"-----END [^-]*(?:PRIVATE|PUBLIC) KEY-----",
    re.DOTALL,
)


def _is_sensitive_environment_name(name: str) -> bool:
    normalized = name.upper()
    return (
        normalized == "REDFISH_HOSTS"
        or normalized == "MCP_AUTH_JWT_PUBLIC_KEY"
        or normalized
        in {
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "OPENAI_API_KEY",
            "PAT_TOKEN",
        }
        or any(
            marker in normalized
            for marker in (
                "PASSWORD",
                "CLIENT_SECRET",
                "PRIVATE_KEY",
                "SIGNING_KEY",
                "ENCRYPTION_KEY",
                "REDIS_URL",
            )
        )
    )


def redact_sensitive_text(message: str) -> str:
    """Redact common credential forms and configured secret values."""
    redacted = _AUTH_HEADER_PATTERN.sub(r"\1<redacted>", message)
    redacted = _BEARER_PATTERN.sub("Bearer <redacted>", redacted)
    redacted = _BASIC_PATTERN.sub("Basic <redacted>", redacted)
    redacted = _SENSITIVE_QUERY_PATTERN.sub(r"\1<redacted>", redacted)
    redacted = _PEM_KEY_PATTERN.sub("<redacted-key>", redacted)

    secret_values = {
        value
        for name, value in os.environ.items()
        if value and _is_sensitive_environment_name(name)
    }
    for value in sorted(secret_values, key=len, reverse=True):
        redacted = redacted.replace(value, "<redacted>")
    return redacted


class SensitiveDataFilter(logging.Filter):
    """Apply final defensive redaction before a handler emits a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(record.getMessage())
        record.args = ()
        # Exception messages and stack text are not under this project's
        # control and may contain request data. Callers that need diagnostics
        # log safe exception types and frame locations separately.
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def configure_sensitive_data_filter() -> None:
    """Install the redaction filter on every configured root handler."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(isinstance(item, SensitiveDataFilter) for item in handler.filters):
            handler.addFilter(SensitiveDataFilter())
