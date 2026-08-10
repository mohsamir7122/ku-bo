from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.status_history_workspace import prepare_status_history_workspace
from tests.foundation_fixture_helpers import build_status_corporate_output


class StatusHistoryWorkspaceTests(unittest.TestCase):
    def test_workspace_requires_one_query_and_opening_state_per_security(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = build_status_corporate_output(root)
            workspace = root / "history-workspace"
            report = prepare_status_history_workspace(
                status_corporate_root=upstream,
                output_root=workspace,
                run_id="status-history-001",
                history_window_from="2026-01-01",
                history_window_to="2026-08-09",
                prepared_by="unit-test",
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["security_count"], 5)
            manifest = json.loads(
                (workspace / "manifests" / "status_history_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(manifest["queries"]), 5)
            self.assertEqual(len(manifest["opening_states"]), 5)
            self.assertEqual(manifest["notices"], [])
            self.assertTrue(
                all(query["review_status"] == "PENDING" for query in manifest["queries"])
            )
            self.assertTrue(
                all(
                    opening["status"] == ""
                    for opening in manifest["opening_states"]
                )
            )
            self.assertEqual(
                len(
                    list(
                        (workspace / "raw_exports" / "queries").glob(
                            "*.placeholder"
                        )
                    )
                ),
                5,
            )
            self.assertFalse(
                report["claim_boundaries"]["current_status_is_opening_status"]
            )
            self.assertFalse(report["claim_boundaries"]["status_history_ready"])

    def test_history_window_must_end_at_current_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = build_status_corporate_output(root)
            with self.assertRaisesRegex(ValueError, "must equal"):
                prepare_status_history_workspace(
                    status_corporate_root=upstream,
                    output_root=root / "history-workspace",
                    run_id="status-history-001",
                    history_window_from="2026-01-01",
                    history_window_to="2026-08-08",
                )

    def test_non_empty_workspace_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = build_status_corporate_output(root)
            workspace = root / "history-workspace"
            workspace.mkdir()
            (workspace / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty status-history workspace"):
                prepare_status_history_workspace(
                    status_corporate_root=upstream,
                    output_root=workspace,
                    run_id="status-history-001",
                    history_window_from="2026-01-01",
                    history_window_to="2026-08-09",
                )
            self.assertEqual(
                (workspace / "keep.txt").read_text(encoding="utf-8"),
                "keep",
            )


if __name__ == "__main__":
    unittest.main()
