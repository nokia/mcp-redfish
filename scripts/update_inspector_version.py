#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Update the pinned MCP Inspector version within the configured semver range."""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from e2e.inspector_version import (  # noqa: E402
    latest_version_in_constraint,
    load_inspector_version_config,
    write_locked_version,
)


def main() -> int:
    config = load_inspector_version_config()

    try:
        latest_allowed = latest_version_in_constraint(config.package, config.constraint)
    except urllib.error.URLError as exc:
        print(f"::warning title=npm lookup failed::{config.package}: {exc}")
        return 0

    if latest_allowed == config.locked_version:
        print(
            f"{config.package} is already at the latest allowed version "
            f"({config.locked_version})."
        )
        return 0

    write_locked_version(latest_allowed)
    print(f"Updated {config.package} lock: {config.locked_version} -> {latest_allowed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
