#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Report when a newer major MCP Inspector release is available on npm."""

from __future__ import annotations

import argparse
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from major_version_findings import MajorVersionFinding  # noqa: E402

from e2e.inspector_version import (  # noqa: E402
    latest_version_on_npm,
    load_inspector_version_config,
    major_version,
)


def collect_inspector_major_update() -> MajorVersionFinding | None:
    config = load_inspector_version_config()

    try:
        latest_version = latest_version_on_npm(config.package)
    except urllib.error.URLError as exc:
        print(f"::warning title=npm lookup failed::{config.package}: {exc}")
        return None

    if major_version(latest_version) <= major_version(config.locked_version):
        return None

    return MajorVersionFinding(
        package=config.package,
        locked_version=config.locked_version,
        latest_version=latest_version,
        registry="npm",
    )


def format_summary_markdown(finding: MajorVersionFinding) -> str:
    return "\n".join(
        [
            "## MCP Inspector major-version indicator",
            "",
            "A newer **major** MCP Inspector release is available on npm. "
            "Minor and patch updates are handled automatically within "
            "`e2e/inspector-version.toml`; major bumps require manual "
            "review of the Inspector migration guide and e2e CLI usage.",
            "",
            "| Package | Locked | Latest |",
            "| --- | --- | --- |",
            (
                f"| `{finding.package}` | `{finding.locked_version}` | "
                f"`{finding.latest_version}` |"
            ),
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report when a newer major MCP Inspector release is on npm."
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        help="Optional path for a GitHub Actions job summary markdown file.",
    )
    args = parser.parse_args(argv)

    finding = collect_inspector_major_update()

    if finding is None:
        config = load_inspector_version_config()
        print(
            f"{config.package} is on the latest major version "
            f"({config.locked_version})."
        )
        return 0

    print(
        f"{finding.package} has a newer major release on npm: "
        f"locked {finding.locked_version}, latest {finding.latest_version}."
    )
    print(
        f"::warning title=New major Inspector version available::{finding.package} "
        f"{finding.locked_version} -> {finding.latest_version}"
    )

    if args.summary_file is not None:
        args.summary_file.write_text(format_summary_markdown(finding), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
