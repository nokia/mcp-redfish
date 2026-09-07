#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Report direct runtime dependencies with newer major versions on PyPI."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from major_version_findings import MajorVersionFinding  # noqa: E402

PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
PYPI_URL = "https://pypi.org/pypi/{package}/json"
PACKAGE_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)")


def parse_package_name(requirement: str) -> str:
    match = PACKAGE_NAME_RE.match(requirement.strip())
    if not match:
        raise ValueError(f"Could not parse dependency requirement: {requirement}")
    return match.group(1)


def major_version(version: str) -> int:
    match = re.match(r"(\d+)", version)
    if not match:
        raise ValueError(f"Could not parse version: {version}")
    return int(match.group(1))


def fetch_latest_version(package: str) -> str:
    request = urllib.request.Request(
        PYPI_URL.format(package=package),
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload["info"]["version"]


def load_direct_dependencies() -> list[str]:
    with PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    return list(data["project"]["dependencies"])


def load_locked_versions() -> dict[str, str]:
    with UV_LOCK.open("rb") as handle:
        data = tomllib.load(handle)
    return {package["name"]: package["version"] for package in data["package"]}


def collect_outdated_major_versions() -> list[MajorVersionFinding]:
    locked_versions = load_locked_versions()
    outdated: list[MajorVersionFinding] = []

    for requirement in load_direct_dependencies():
        package = parse_package_name(requirement)
        locked_version = locked_versions.get(package)
        if locked_version is None:
            print(f"::warning title=Missing lock entry::{package} not found in uv.lock")
            continue

        try:
            latest_version = fetch_latest_version(package)
        except urllib.error.URLError as exc:
            print(f"::warning title=PyPI lookup failed::{package}: {exc}")
            continue

        if major_version(latest_version) > major_version(locked_version):
            outdated.append(
                MajorVersionFinding(
                    package=package,
                    locked_version=locked_version,
                    latest_version=latest_version,
                    registry="PyPI",
                )
            )

    return outdated


def format_summary_markdown(findings: list[MajorVersionFinding]) -> str:
    if not findings:
        return ""

    lines = [
        "## Major-version availability indicator",
        "",
        "The following direct runtime dependencies have a newer major release "
        "on PyPI. This check is informational only; automated updates remain "
        "within the bounded ranges in `pyproject.toml`.",
        "",
        "| Package | Locked | Latest |",
        "| --- | --- | --- |",
    ]
    for finding in findings:
        lines.append(
            f"| `{finding.package}` | `{finding.locked_version}` | "
            f"`{finding.latest_version}` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report direct runtime dependencies with newer major versions."
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        help="Optional path for a GitHub Actions job summary markdown file.",
    )
    args = parser.parse_args(argv)

    outdated = collect_outdated_major_versions()

    if not outdated:
        print("All direct runtime dependencies are on the latest major version.")
        return 0

    print("Direct dependencies with a newer major version available on PyPI:")
    for finding in outdated:
        print(
            f"- {finding.package}: locked {finding.locked_version}, "
            f"latest {finding.latest_version}"
        )
        print(
            f"::warning title=New major version available::{finding.package} "
            f"{finding.locked_version} -> {finding.latest_version}"
        )

    if args.summary_file is not None:
        args.summary_file.write_text(
            format_summary_markdown(outdated), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
