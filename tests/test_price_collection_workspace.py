from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest

from kubo.price_collection_workspace import (
    MANIFEST_HEADERS,
    prepare_price_collection_workspace,
)


ROOT = Path(__file__).resolve().parents[1]


class PriceCollectionWorkspaceTests(unittest.TestCase):
    def test_prepare_workspace_for_five_mapped_securities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            report = prepare_price_collection_workspace(
                config_dir=ROOT / "config",
                output_root=workspace,
                downloaded_by="test-user",
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["symbol_count"], 5)
            self.assertFalse(report["official_identity_ready"])
            placeholders = sorted(
                (workspace / "raw_exports" / "investing").glob("*.csv.placeholder")
            )
            self.assertEqual(len(placeholders), 5)
            manifest = workspace / "manifests" / "price_collection_manifest.csv"
            with manifest.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames or ()), MANIFEST_HEADERS)
                rows = list(reader)
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(row["review_status"] == "PENDING" for row in rows))

    def test_non_empty_workspace_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            (workspace / "existing.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty workspace"):
                prepare_price_collection_workspace(
                    config_dir=ROOT / "config",
                    output_root=workspace,
                )
            self.assertEqual(
                (workspace / "existing.txt").read_text(encoding="utf-8"),
                "keep",
            )

    def test_all_market_request_is_blocked_by_missing_universe_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = prepare_price_collection_workspace(
                config_dir=ROOT / "config",
                output_root=Path(directory) / "workspace",
                expected_scope="all_market",
            )
            self.assertEqual(
                report["status"],
                "FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED",
            )
            self.assertFalse(report["claim_boundaries"]["full_market_claim_allowed"])

    def test_source_name_is_one_path_safe_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "path-safe"):
                prepare_price_collection_workspace(
                    config_dir=ROOT / "config",
                    output_root=Path(directory) / "workspace",
                    source_name="../investing",
                )


if __name__ == "__main__":
    unittest.main()
