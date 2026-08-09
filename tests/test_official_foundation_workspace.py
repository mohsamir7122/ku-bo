from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.official_foundation_workspace import (
    OFFICIAL_ARTIFACT_SPECS,
    prepare_official_foundation_workspace,
)


class OfficialFoundationWorkspaceTests(unittest.TestCase):
    def test_workspace_contains_exact_official_artifact_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "official"
            report = prepare_official_foundation_workspace(
                output_root=root,
                run_id="official-pilot-001",
                calendar_year=2026,
                prepared_by="unit-test",
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["artifact_count"], len(OFFICIAL_ARTIFACT_SPECS))
            manifest = json.loads(
                (root / "manifests" / "official_foundation_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["calendar_window_from"], "2026-01-01")
            self.assertEqual(manifest["calendar_window_to"], "2026-12-31")
            self.assertEqual(
                {row["artifact_id"] for row in manifest["artifacts"]},
                {row["artifact_id"] for row in OFFICIAL_ARTIFACT_SPECS},
            )
            self.assertTrue(
                all(row["review_status"] == "PENDING" for row in manifest["artifacts"])
            )
            placeholders = list((root / "raw_exports" / "boursa").glob("*.placeholder"))
            self.assertEqual(len(placeholders), len(OFFICIAL_ARTIFACT_SPECS))
            self.assertFalse(report["claim_boundaries"]["workspace_contains_official_evidence"])

    def test_workspace_never_overwrites_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "official"
            root.mkdir()
            (root / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty official workspace"):
                prepare_official_foundation_workspace(
                    output_root=root,
                    run_id="official-pilot-001",
                )
            self.assertEqual((root / "keep.txt").read_text(encoding="utf-8"), "keep")

    def test_invalid_run_id_is_rejected_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "official"
            with self.assertRaisesRegex(ValueError, "canonical"):
                prepare_official_foundation_workspace(
                    output_root=root,
                    run_id="../official",
                )
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
