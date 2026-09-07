# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for final defensive log redaction."""

from __future__ import annotations

import logging

import pytest

from src.common.logging_utils import SensitiveDataFilter, redact_sensitive_text


def test_redacts_headers_queries_keys_and_configured_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDFISH_PASSWORD", "bmc-password-value")
    monkeypatch.setenv(
        "HTTPS_PROXY", "http://proxy-user:proxy-password@example.com:3128"
    )
    message = (
        "Authorization: Bearer token-value "
        "Basic dXNlcjpwYXNz "
        "https://example.test/path?access_token=query-token&ok=true "
        "https://idp.example/cb?code=oauth-code&id_token=id-token-value "
        "&refresh_token=refresh-token-value "
        "bmc-password-value "
        "http://proxy-user:proxy-password@example.com:3128 "
        "-----BEGIN PRIVATE KEY-----\nprivate-key-value\n"
        "-----END PRIVATE KEY-----"
    )

    redacted = redact_sensitive_text(message)

    for sensitive in (
        "token-value",
        "dXNlcjpwYXNz",
        "query-token",
        "oauth-code",
        "id-token-value",
        "refresh-token-value",
        "bmc-password-value",
        "proxy-password",
        "private-key-value",
    ):
        assert sensitive not in redacted
    assert redacted.count("<redacted>") >= 4
    assert "<redacted-key>" in redacted


def test_filter_formats_then_redacts_record_arguments() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Request used Bearer %s",
        args=("sensitive-token",),
        exc_info=None,
    )

    assert SensitiveDataFilter().filter(record)
    assert record.getMessage() == "Request used Bearer <redacted>"
    assert record.args == ()
