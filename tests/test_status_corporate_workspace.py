from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.status_corporate_workspace import (
    STATUS_CORPORATE_ARTIFACT_SPECS,
    prepare_status_corporate_workspace,
)


class StatusCorporateWorkspaceTests(unittest.TestCase):
    def test_workspace_contains_exact_artifact_and_query_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "status-ca"
            report = prepare_status_corporate_workspace(
                output_root=root,
                run_id="status-ca-001",
                action_window_from="2021-01-01",
                action_window_to="2026-08-09",
                prepared_by="unit-test",
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(
                report["artifact_count"],
                len(STATUS_CORPORATE_ARTIFACT_SPECS),
            )
            manifest = json.loads(
                (root / "manifests" / "status_corporate_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["corporate_action_window_from"], "2021-01-01")
            self.assertEqual(manifest["corporate_action_window_to"], "2026-08-09")
            self.assertFalse(manifest["corporate_action_query"]["filter_applied"])
            self.assertEqual(
                {row["artifact_id"] for row in manifest["artifacts"]},
                {row["artifact_id"] for row in STATUS_CORPORATE_ARTIFACT_SPECS},
            )
            placeholders = list(
                (root / "raw_exports" / "boursa").glob("*.placeholder")
            )
            self.assertEqual(len(placeholders), len(STATUS_CORPORATE_ARTIFACT_SPECS))
            self.assertFalse(
                report["claim_boundaries"]["current_status_is_status_history"]
            )
            self.assertFalse(
                report["claim_boundaries"][
                    "corporate_action_schedule_contains_adjustment_factor"
                ]
            )

    def test_reversed_action_window_is_rejected_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "status-ca"
            with self.assertRaisesRegex(ValueError, "reversed"):
                prepare_status_corporate_workspace(
                    output_root=root,
                    run_id="status-ca-001",
                    action_window_from="2026-08-09",
                    action_window_to="2021-01-01",
                )
            self.assertFalse(root.exists())

    def test_non_empty_workspace_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "status-ca"
            root.mkdir()
            (root / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty status/corporate workspace"):
                prepare_status_corporate_workspace(
                    output_root=root,
                    run_id="status-ca-001",
                    action_window_from="2021-01-01",
                    action_window_to="2026-08-09",
                )
            self.assertEqual((root / "keep.txt").read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
