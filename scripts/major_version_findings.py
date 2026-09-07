# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Shared types for major-version availability checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MajorVersionFinding:
    package: str
    locked_version: str
    latest_version: str
    registry: str
