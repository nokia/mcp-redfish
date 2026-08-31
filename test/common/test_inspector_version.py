# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from e2e.inspector_version import (
    InspectorVersionConfig,
    latest_version_in_constraint,
    load_inspector_package_spec,
    parse_constraint,
    version_satisfies_constraint,
)


class TestInspectorVersion(unittest.TestCase):
    def test_parse_constraint(self) -> None:
        minimum, maximum_major = parse_constraint(">=2.4.0,<3")
        self.assertEqual(minimum, (2, 4, 0))
        self.assertEqual(maximum_major, 3)

    def test_version_satisfies_constraint(self) -> None:
        constraint = ">=2.4.0,<3"
        self.assertTrue(version_satisfies_constraint("2.4.0", constraint))
        self.assertTrue(version_satisfies_constraint("2.9.1", constraint))
        self.assertFalse(version_satisfies_constraint("2.3.9", constraint))
        self.assertFalse(version_satisfies_constraint("3.0.0", constraint))

    def test_load_inspector_package_spec(self) -> None:
        self.assertEqual(
            load_inspector_package_spec(),
            "@modelcontextprotocol/inspector@2.4.0",
        )

    @patch("e2e.inspector_version.fetch_npm_versions")
    def test_latest_version_in_constraint(self, fetch_versions) -> None:
        fetch_versions.return_value = ["2.4.0", "2.5.0", "3.0.0", "2.4.1"]
        latest = latest_version_in_constraint(
            "@modelcontextprotocol/inspector", ">=2.4.0,<3"
        )
        self.assertEqual(latest, "2.5.0")


class TestCheckInspectorVersionScript(unittest.TestCase):
    @patch("check_inspector_version.latest_version_on_npm", return_value="3.0.0")
    @patch(
        "check_inspector_version.load_inspector_version_config",
        return_value=InspectorVersionConfig(
            package="@modelcontextprotocol/inspector",
            constraint=">=2.4.0,<3",
            locked_version="2.4.0",
        ),
    )
    def test_check_major_reports_new_major(self, _load_config, _latest_version) -> None:
        import check_inspector_version

        self.assertEqual(check_inspector_version.main(), 1)


class TestUpdateInspectorVersionScript(unittest.TestCase):
    @patch("update_inspector_version.write_locked_version")
    @patch(
        "update_inspector_version.latest_version_in_constraint",
        return_value="2.5.0",
    )
    @patch(
        "update_inspector_version.load_inspector_version_config",
        return_value=InspectorVersionConfig(
            package="@modelcontextprotocol/inspector",
            constraint=">=2.4.0,<3",
            locked_version="2.4.0",
        ),
    )
    def test_update_lock_bumps_allowed_version(
        self, _load_config, _latest_allowed, write_locked
    ) -> None:
        import update_inspector_version

        self.assertEqual(update_inspector_version.main(), 0)
        write_locked.assert_called_once_with("2.5.0")


if __name__ == "__main__":
    unittest.main()
