# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Load and resolve the pinned MCP Inspector CLI version for e2e tooling."""

from __future__ import annotations

import json
import re
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "inspector-version.toml"
LOCK_PATH = Path(__file__).parent / "inspector-version.lock"
NPM_REGISTRY_URL = "https://registry.npmjs.org/{package}"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class InspectorVersionConfig:
    package: str
    constraint: str
    locked_version: str

    @property
    def package_spec(self) -> str:
        return f"{self.package}@{self.locked_version}"


def parse_version(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.match(version)
    if not match:
        raise ValueError(f"Unsupported version format: {version}")
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def parse_constraint(constraint: str) -> tuple[tuple[int, int, int], int]:
    minimum_match = re.search(r">=(\d+)\.(\d+)\.(\d+)", constraint)
    maximum_major_match = re.search(r",<(\d+)", constraint)
    if minimum_match is None or maximum_major_match is None:
        raise ValueError(
            f"Inspector constraint must use '>=X.Y.Z,<N' format, got: {constraint!r}"
        )
    minimum = (
        int(minimum_match.group(1)),
        int(minimum_match.group(2)),
        int(minimum_match.group(3)),
    )
    maximum_major = int(maximum_major_match.group(1))
    return minimum, maximum_major


def version_satisfies_constraint(version: str, constraint: str) -> bool:
    minimum, maximum_major = parse_constraint(constraint)
    major, minor, patch = parse_version(version)
    if major >= maximum_major:
        return False
    return (major, minor, patch) >= minimum


def load_inspector_version_config() -> InspectorVersionConfig:
    with CONFIG_PATH.open("rb") as handle:
        config = tomllib.load(handle)
    locked_version = LOCK_PATH.read_text(encoding="utf-8").strip()
    return InspectorVersionConfig(
        package=config["package"],
        constraint=config["constraint"],
        locked_version=locked_version,
    )


def load_inspector_package_spec() -> str:
    return load_inspector_version_config().package_spec


def write_locked_version(version: str) -> None:
    parse_version(version)
    LOCK_PATH.write_text(f"{version}\n", encoding="utf-8")


def fetch_npm_versions(package: str) -> list[str]:
    encoded_package = package.removeprefix("@").replace("/", "%2F")
    if package.startswith("@"):
        encoded_package = f"@{encoded_package}"
    request = urllib.request.Request(
        NPM_REGISTRY_URL.format(package=encoded_package),
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    versions = [
        version for version in payload.get("versions", {}) if VERSION_RE.match(version)
    ]
    return sorted(versions, key=parse_version)


def latest_version_on_npm(package: str) -> str:
    versions = fetch_npm_versions(package)
    if not versions:
        raise ValueError(f"No semver releases found for {package}")
    return versions[-1]


def latest_version_in_constraint(package: str, constraint: str) -> str:
    matching = sorted(
        (
            version
            for version in fetch_npm_versions(package)
            if version_satisfies_constraint(version, constraint)
        ),
        key=parse_version,
    )
    if not matching:
        raise ValueError(
            f"No npm releases for {package} satisfy constraint {constraint}"
        )
    return matching[-1]


def major_version(version: str) -> int:
    return parse_version(version)[0]
