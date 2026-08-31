#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Report direct runtime dependencies with newer major versions on PyPI."""

from __future__ import annotations

import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def main() -> int:
    locked_versions = load_locked_versions()
    outdated: list[tuple[str, str, str, int, int]] = []

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

        locked_major = major_version(locked_version)
        latest_major = major_version(latest_version)
        if latest_major > locked_major:
            outdated.append(
                (package, locked_version, latest_version, locked_major, latest_major)
            )

    if not outdated:
        print("All direct runtime dependencies are on the latest major version.")
        return 0

    print("Direct dependencies with a newer major version available on PyPI:")
    for package, locked, latest, locked_major, latest_major in outdated:
        print(
            f"- {package}: locked major {locked_major} ({locked}), "
            f"latest major {latest_major} ({latest})"
        )
        print(
            f"::warning title=New major version available::{package} "
            f"{locked} -> {latest}"
        )

    summary_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if summary_path is not None:
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
        for package, locked, latest, _, _ in outdated:
            lines.append(f"| `{package}` | `{locked}` | `{latest}` |")
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
