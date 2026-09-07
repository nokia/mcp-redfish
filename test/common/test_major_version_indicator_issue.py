# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from major_version_findings import MajorVersionFinding
from manage_major_version_indicator_issue import (
    ISSUE_MARKER,
    ISSUE_TITLE,
    find_open_indicator_issue,
    format_issue_body,
    format_resolved_issue_body,
    main,
    sync_indicator_issue,
)


class TestMajorVersionIndicatorIssue(unittest.TestCase):
    def test_format_issue_body_includes_marker_and_findings(self) -> None:
        body = format_issue_body(
            [
                MajorVersionFinding("fastmcp", "3.4.7", "4.0.3", "PyPI"),
                MajorVersionFinding(
                    "@modelcontextprotocol/inspector",
                    "2.5.0",
                    "3.0.0",
                    "npm",
                ),
            ],
            "https://github.com/example/repo/actions/runs/1",
        )
        self.assertIn(ISSUE_MARKER, body)
        self.assertIn("## Python dependencies (PyPI)", body)
        self.assertIn("## MCP Inspector (npm)", body)
        self.assertIn("`fastmcp`", body)
        self.assertIn("workflow run", body)

    def test_format_resolved_issue_body(self) -> None:
        body = format_resolved_issue_body(None)
        self.assertIn(ISSUE_MARKER, body)
        self.assertIn("No newer major versions are currently available", body)

    @patch("manage_major_version_indicator_issue.github_api_request")
    def test_find_open_indicator_issue_returns_matching_issue(
        self, github_api_request
    ) -> None:
        github_api_request.return_value = [
            {
                "number": 42,
                "title": ISSUE_TITLE,
            },
            {
                "number": 43,
                "title": "Unrelated",
            },
        ]
        self.assertEqual(
            find_open_indicator_issue("token", "nokia/mcp-redfish"),
            42,
        )

    @patch("manage_major_version_indicator_issue.update_indicator_issue")
    @patch("manage_major_version_indicator_issue.find_open_indicator_issue")
    def test_sync_indicator_issue_updates_existing_open_issue(
        self, find_open_issue, update_issue
    ) -> None:
        find_open_issue.return_value = 42
        findings = [MajorVersionFinding("fastmcp", "3.4.7", "4.0.3", "PyPI")]

        result = sync_indicator_issue("token", "nokia/mcp-redfish", findings, None)

        self.assertEqual(result, "Updated issue #42")
        update_issue.assert_called_once()
        self.assertEqual(update_issue.call_args.args[2], 42)
        self.assertEqual(update_issue.call_args.kwargs["state"], "open")

    @patch("manage_major_version_indicator_issue.create_indicator_issue")
    @patch("manage_major_version_indicator_issue.find_open_indicator_issue")
    def test_sync_indicator_issue_creates_issue_when_missing(
        self, find_open_issue, create_issue
    ) -> None:
        find_open_issue.return_value = None
        create_issue.return_value = 99
        findings = [MajorVersionFinding("fastmcp", "3.4.7", "4.0.3", "PyPI")]

        result = sync_indicator_issue("token", "nokia/mcp-redfish", findings, None)

        self.assertEqual(result, "Created issue #99")
        create_issue.assert_called_once()

    @patch("manage_major_version_indicator_issue.update_indicator_issue")
    @patch("manage_major_version_indicator_issue.find_open_indicator_issue")
    def test_sync_indicator_issue_closes_open_issue_when_resolved(
        self, find_open_issue, update_issue
    ) -> None:
        find_open_issue.return_value = 42

        result = sync_indicator_issue("token", "nokia/mcp-redfish", [], None)

        self.assertEqual(result, "Closed issue #42")
        update_issue.assert_called_once()
        self.assertEqual(update_issue.call_args.kwargs["state"], "closed")

    @patch("manage_major_version_indicator_issue.sync_indicator_issue")
    @patch("manage_major_version_indicator_issue.collect_findings")
    def test_main_skips_github_sync_without_token(
        self, collect_findings, sync_indicator_issue
    ) -> None:
        collect_findings.return_value = [
            MajorVersionFinding("fastmcp", "3.4.7", "4.0.3", "PyPI")
        ]

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(main([]), 0)

        sync_indicator_issue.assert_not_called()

    @patch("manage_major_version_indicator_issue.sync_indicator_issue")
    @patch("manage_major_version_indicator_issue.describe_indicator_issue_action")
    @patch("manage_major_version_indicator_issue.collect_findings")
    def test_main_dry_run_previews_without_sync(
        self, collect_findings, describe_action, sync_indicator_issue
    ) -> None:
        collect_findings.return_value = [
            MajorVersionFinding("fastmcp", "3.4.7", "4.0.3", "PyPI")
        ]
        describe_action.return_value = "Dry run: would create a new indicator issue"

        with patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "token", "GITHUB_REPOSITORY": "nokia/mcp-redfish"},
            clear=True,
        ):
            self.assertEqual(main(["--dry-run"]), 0)

        describe_action.assert_called_once()
        sync_indicator_issue.assert_not_called()

    @patch(
        "manage_major_version_indicator_issue.collect_findings",
        return_value=[],
    )
    def test_collect_findings_is_used_by_main(self, _collect_findings) -> None:
        with patch.dict(
            "os.environ",
            {"GITHUB_TOKEN": "token", "GITHUB_REPOSITORY": "nokia/mcp-redfish"},
            clear=True,
        ):
            with patch(
                "manage_major_version_indicator_issue.sync_indicator_issue",
                return_value="No newer major versions and no open indicator issue",
            ) as sync_indicator_issue:
                self.assertEqual(main([]), 0)
        sync_indicator_issue.assert_called_once_with(
            "token", "nokia/mcp-redfish", [], None
        )


if __name__ == "__main__":
    unittest.main()
