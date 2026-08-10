from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.ca_enrichment_workspace import prepare_ca_enrichment_workspace
from tests.foundation_fixture_helpers import build_status_corporate_output


class CorporateActionEnrichmentWorkspaceTests(unittest.TestCase):
    def test_workspace_is_populated_from_pending_upstream_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = build_status_corporate_output(root)
            workspace = root / "ca-workspace"
            report = prepare_ca_enrichment_workspace(
                status_corporate_root=upstream,
                output_root=workspace,
                run_id="ca-enrichment-001",
                prepared_by="unit-test",
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["pending_action_count"], 2)
            manifest = json.loads(
                (workspace / "manifests" / "ca_enrichment_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(manifest["actions"]), 2)
            self.assertTrue(
                all(
                    row["terms"]["formula_mode"] == "NO_AUTOMATIC_FORMULA"
                    for row in manifest["actions"]
                )
            )
            self.assertTrue(
                all(
                    row["disclosure"]["review_status"] == "PENDING"
                    for row in manifest["actions"]
                )
            )
            self.assertEqual(
                len(
                    list(
                        (workspace / "raw_exports" / "disclosures").glob(
                            "*.placeholder"
                        )
                    )
                ),
                2,
            )
            self.assertFalse(
                report["claim_boundaries"]["mechanical_factor_is_official_factor"]
            )

    def test_zero_action_upstream_creates_explicit_zero_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = build_status_corporate_output(root, zero_actions=True)
            report = prepare_ca_enrichment_workspace(
                status_corporate_root=upstream,
                output_root=root / "ca-workspace",
                run_id="ca-enrichment-zero",
            )
            self.assertEqual(report["status"], "NO_PENDING_ACTIONS")
            self.assertEqual(report["pending_action_count"], 0)

    def test_non_empty_workspace_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = build_status_corporate_output(root)
            workspace = root / "ca-workspace"
            workspace.mkdir()
            (workspace / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty enrichment workspace"):
                prepare_ca_enrichment_workspace(
                    status_corporate_root=upstream,
                    output_root=workspace,
                    run_id="ca-enrichment-001",
                )
            self.assertEqual(
                (workspace / "keep.txt").read_text(encoding="utf-8"),
                "keep",
            )


if __name__ == "__main__":
    unittest.main()
