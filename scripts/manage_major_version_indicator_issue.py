#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Create or update a GitHub issue when newer major versions are available."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check_inspector_version import collect_inspector_major_update  # noqa: E402
from check_major_dependency_updates import collect_outdated_major_versions  # noqa: E402
from major_version_findings import MajorVersionFinding  # noqa: E402

ISSUE_TITLE = "Major version updates available"
ISSUE_LABEL = "major-version-indicator"
ISSUE_MARKER = "<!-- major-version-indicator-issue -->"
GITHUB_API_VERSION = "2022-11-28"


def collect_findings() -> list[MajorVersionFinding]:
    findings = list(collect_outdated_major_versions())
    inspector_finding = collect_inspector_major_update()
    if inspector_finding is not None:
        findings.append(inspector_finding)
    return findings


def format_issue_body(
    findings: list[MajorVersionFinding], workflow_run_url: str | None
) -> str:
    updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        ISSUE_MARKER,
        "",
        "The weekly dependency update workflow found newer **major** versions "
        "available. Automated updates stay within the version ranges in "
        "`pyproject.toml` and `e2e/inspector-version.toml`.",
        "",
    ]
    if workflow_run_url:
        lines.append(f"Last updated: {updated_at} ([workflow run]({workflow_run_url}))")
    else:
        lines.append(f"Last updated: {updated_at}")
    lines.append("")

    python_rows = [f for f in findings if f.registry == "PyPI"]
    npm_rows = [f for f in findings if f.registry == "npm"]

    if python_rows:
        lines.extend(
            [
                "## Python dependencies (PyPI)",
                "",
                "| Package | Locked | Latest |",
                "| --- | --- | --- |",
            ]
        )
        for finding in python_rows:
            lines.append(
                f"| `{finding.package}` | `{finding.locked_version}` | "
                f"`{finding.latest_version}` |"
            )
        lines.append("")

    if npm_rows:
        lines.extend(
            [
                "## MCP Inspector (npm)",
                "",
                "| Package | Locked | Latest |",
                "| --- | --- | --- |",
            ]
        )
        for finding in npm_rows:
            lines.append(
                f"| `{finding.package}` | `{finding.locked_version}` | "
                f"`{finding.latest_version}` |"
            )
        lines.append("")

    lines.extend(
        [
            "Close this issue after the major upgrades are merged or the version "
            "ranges are intentionally kept as-is.",
        ]
    )
    return "\n".join(lines)


def format_resolved_issue_body(workflow_run_url: str | None) -> str:
    updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        ISSUE_MARKER,
        "",
        "No newer major versions are currently available for tracked Python "
        "dependencies or MCP Inspector.",
        "",
    ]
    if workflow_run_url:
        lines.append(f"Last checked: {updated_at} ([workflow run]({workflow_run_url}))")
    else:
        lines.append(f"Last checked: {updated_at}")
    return "\n".join(lines)


def github_api_request(
    method: str,
    url: str,
    token: str,
    payload: dict | list | None = None,
) -> dict | list:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        if not body:
            return {}
        return json.loads(body)


def workflow_run_url() -> str | None:
    server_url = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not server_url or not repository or not run_id:
        return None
    return f"{server_url}/{repository}/actions/runs/{run_id}"


def find_open_indicator_issue(token: str, repository: str) -> int | None:
    owner, repo = repository.split("/", 1)
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/issues"
        f"?state=open&labels={ISSUE_LABEL}&per_page=100"
    )
    payload = github_api_request("GET", url, token)
    if not isinstance(payload, list):
        raise TypeError("Expected a list of issues from GitHub API")

    matches = [
        issue
        for issue in payload
        if issue.get("title") == ISSUE_TITLE and "pull_request" not in issue
    ]
    if not matches:
        return None
    return int(matches[0]["number"])


def ensure_issue_label(token: str, repository: str) -> None:
    owner, repo = repository.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{repo}/labels"
    try:
        github_api_request(
            "POST",
            url,
            token,
            {
                "name": ISSUE_LABEL,
                "color": "fbca04",
                "description": "Tracks newer major dependency versions reported by CI",
            },
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 422:
            raise


def create_indicator_issue(token: str, repository: str, body: str) -> int:
    owner, repo = repository.split("/", 1)
    ensure_issue_label(token, repository)
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    payload = github_api_request(
        "POST",
        url,
        token,
        {"title": ISSUE_TITLE, "body": body, "labels": [ISSUE_LABEL]},
    )
    if not isinstance(payload, dict):
        raise TypeError("Expected issue payload from GitHub API")
    return int(payload["number"])


def update_indicator_issue(
    token: str, repository: str, issue_number: int, body: str, *, state: str = "open"
) -> None:
    owner, repo = repository.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    github_api_request("PATCH", url, token, {"body": body, "state": state})


def sync_indicator_issue(
    token: str,
    repository: str,
    findings: list[MajorVersionFinding],
    workflow_url: str | None,
) -> str:
    open_issue = find_open_indicator_issue(token, repository)

    if findings:
        body = format_issue_body(findings, workflow_url)
        if open_issue is None:
            issue_number = create_indicator_issue(token, repository, body)
            return f"Created issue #{issue_number}"
        update_indicator_issue(token, repository, open_issue, body, state="open")
        return f"Updated issue #{open_issue}"

    if open_issue is None:
        return "No newer major versions and no open indicator issue"

    body = format_resolved_issue_body(workflow_url)
    update_indicator_issue(token, repository, open_issue, body, state="closed")
    return f"Closed issue #{open_issue}"


def emit_warnings(findings: list[MajorVersionFinding]) -> None:
    for finding in findings:
        print(
            f"::warning title=New major version available::{finding.package} "
            f"{finding.locked_version} -> {finding.latest_version}"
        )


def write_summary_files(summary_dir: Path, findings: list[MajorVersionFinding]) -> None:
    from check_inspector_version import format_summary_markdown as inspector_summary
    from check_major_dependency_updates import format_summary_markdown as python_summary

    summary_dir.mkdir(parents=True, exist_ok=True)
    python_rows = [finding for finding in findings if finding.registry == "PyPI"]
    npm_rows = [finding for finding in findings if finding.registry == "npm"]

    if python_rows:
        (summary_dir / "major-versions.md").write_text(
            python_summary(python_rows),
            encoding="utf-8",
        )
    if npm_rows:
        (summary_dir / "inspector-major.md").write_text(
            inspector_summary(npm_rows[0]),
            encoding="utf-8",
        )


def describe_indicator_issue_action(
    token: str,
    repository: str,
    findings: list[MajorVersionFinding],
) -> str:
    open_issue = find_open_indicator_issue(token, repository)

    if findings:
        if open_issue is None:
            return "Dry run: would create a new indicator issue"
        return f"Dry run: would update open indicator issue #{open_issue}"

    if open_issue is None:
        return "Dry run: no indicator issue changes"

    return f"Dry run: would close open indicator issue #{open_issue}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create or update the major-version indicator GitHub issue."
    )
    parser.add_argument(
        "--summary-dir",
        type=Path,
        help="Optional directory for GitHub Actions job summary markdown files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report findings and preview issue actions without writing to GitHub.",
    )
    args = parser.parse_args(argv)

    findings = collect_findings()

    if findings:
        print("Newer major versions are available:")
        for finding in findings:
            print(
                f"- {finding.package} ({finding.registry}): "
                f"{finding.locked_version} -> {finding.latest_version}"
            )
        emit_warnings(findings)
    else:
        print("All tracked dependencies are on the latest major version.")

    if args.summary_dir is not None:
        write_summary_files(args.summary_dir, findings)

    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repository:
        print(
            "Skipping GitHub issue sync because GITHUB_TOKEN or "
            "GITHUB_REPOSITORY is not set."
        )
        return 0

    if args.dry_run:
        try:
            print(describe_indicator_issue_action(token, repository, findings))
        except urllib.error.URLError as exc:
            print(f"::warning title=GitHub issue preview failed::{exc}")
        return 0

    try:
        result = sync_indicator_issue(token, repository, findings, workflow_run_url())
    except urllib.error.URLError as exc:
        print(f"::warning title=GitHub issue sync failed::{exc}")
        return 0

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
