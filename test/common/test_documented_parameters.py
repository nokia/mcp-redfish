# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Keep documented environment parameters aligned with the implementation."""

from __future__ import annotations

import re
from pathlib import Path

from fastmcp.settings import Settings as FastMCPSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PARAMETER_PATTERN = re.compile(
    r"\b(?:MCP|FASTMCP|REDFISH|EMULATOR)_[A-Z0-9_]+\b"
    r"|\b(?:HTTPS?_PROXY|ALL_PROXY|NO_PROXY|SSL_CERT_FILE|SSL_CERT_DIR"
    r"|OPENAI_API_KEY|PAT_TOKEN)\b"
)

# These variables are consumed by standard HTTP/TLS libraries rather than
# parsed directly by this project.
STANDARD_LIBRARY_PARAMETERS = {
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
}


def _documentation_files() -> list[Path]:
    return sorted(
        {
            *PROJECT_ROOT.glob("*.md"),
            *(PROJECT_ROOT / "docs").rglob("*.md"),
            *(PROJECT_ROOT / ".github").rglob("*.md"),
        }
    )


def _implementation_text() -> str:
    files = [
        *PROJECT_ROOT.glob("Makefile"),
        *PROJECT_ROOT.glob("Dockerfile*"),
        *(PROJECT_ROOT / "src").rglob("*.py"),
        *(PROJECT_ROOT / "e2e").rglob("*.py"),
        *(PROJECT_ROOT / "e2e").rglob("*.sh"),
        *(PROJECT_ROOT / "examples").rglob("*.py"),
        *(PROJECT_ROOT / "scripts").rglob("*.sh"),
        *(PROJECT_ROOT / ".github" / "workflows").rglob("*.yml"),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def _documented_parameters(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {
        match.group()
        for match in PARAMETER_PATTERN.finditer(text)
        # Do not interpret names in links such as MCP_AUTH_PLAN.md as variables.
        if text[match.end() : match.end() + 3].lower() != ".md"
    }


def test_documented_parameters_exist_in_code_or_supported_runtime() -> None:
    implementation = _implementation_text()
    fastmcp_parameters = {
        f"FASTMCP_{field_name.upper()}" for field_name in FastMCPSettings.model_fields
    }
    # Pydantic-settings consumes this control before constructing Settings, so
    # it is not represented as a model field.
    fastmcp_parameters.add("FASTMCP_ENV_FILE")

    missing: dict[str, list[str]] = {}
    for path in _documentation_files():
        unknown = sorted(
            parameter
            for parameter in _documented_parameters(path)
            if parameter not in implementation
            and parameter not in fastmcp_parameters
            and parameter not in STANDARD_LIBRARY_PARAMETERS
        )
        if unknown:
            missing[str(path.relative_to(PROJECT_ROOT))] = unknown

    assert not missing, (
        "Documentation contains parameters that are not implemented. "
        "Add the implementation, correct the name, or explicitly classify a "
        f"standard runtime variable. Missing parameters: {missing}"
    )
