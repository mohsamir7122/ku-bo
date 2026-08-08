from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kubo.price_collection_workspace import MANIFEST_HEADERS, prepare_price_collection_workspace


ROOT = Path(__file__).resolve().parents[1]


class PriceCollectionWorkspaceTests(unittest.TestCase):
    def test_documented_manifest_template_matches_the_executable_contract(self) -> None:
        with (ROOT / "examples" / "price_file_collection_manifest_template.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        self.assertEqual(tuple(reader.fieldnames or ()), MANIFEST_HEADERS)
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["review_status"] for row in rows}, {"PENDING"})
        self.assertEqual({row["ticker"] for row in rows}, {"KFH", "NBK", "ZAIN", "HUMANSOFT", "MABANEE"})

    def test_prepare_workspace_for_mapped_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            report = prepare_price_collection_workspace(
                config_dir=Path("config"),
                output_root=root,
                source_name="investing",
                downloaded_by="test",
                expected_scope="mapped",
                drive_folder_url="https://drive.google.com/drive/folders/example",
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["symbol_count"], 5)
            self.assertTrue((root / "manifests" / "price_collection_manifest.csv").is_file())
            self.assertTrue((root / "reports" / "price_collection_checklist.md").is_file())
            self.assertTrue((root / "raw_exports" / "investing" / "KFH.csv.placeholder").is_file())
            persisted = json.loads(
                (root / "reports" / "price_collection_workspace_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(persisted["drive_folder_url"], "https://drive.google.com/drive/folders/example")

    def test_all_market_scope_blocks_when_mapping_is_seed_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = prepare_price_collection_workspace(
                config_dir=Path("config"),
                output_root=Path(tmp) / "workspace",
                expected_scope="all_market",
            )
            self.assertEqual(report["status"], "FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED")
            self.assertTrue(
                report["claim_boundaries"][
                    "full_market_requires_external_point_in_time_identity_evidence"
                ]
            )

    def test_all_market_scope_cannot_be_self_proved_by_config_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config"
            config.mkdir()
            payload = json.loads(
                (Path("config") / "symbol_mapping.json").read_text(encoding="utf-8")
            )
            payload["coverage"]["scope"] = "ALL_LISTED_SECURITIES"
            (config / "symbol_mapping.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            report = prepare_price_collection_workspace(
                config_dir=config,
                output_root=root / "workspace",
                expected_scope="all_market",
            )
            self.assertEqual(report["status"], "FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED")
            self.assertTrue(
                report["claim_boundaries"]["config_scope_is_not_reconciliation_evidence"]
            )
            self.assertTrue(
                report["claim_boundaries"]["config_declares_all_listed_securities"]
            )

    def test_source_name_must_be_one_safe_path_component(self) -> None:
        for source_name in ("../escape", "nested/source", "/absolute", "."):
            with self.subTest(source_name=source_name), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "workspace"
                with self.assertRaisesRegex(ValueError, "path-safe"):
                    prepare_price_collection_workspace(
                        config_dir=Path("config"),
                        output_root=output,
                        source_name=source_name,
                    )
                self.assertFalse(output.exists())

    def test_non_empty_workspace_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "workspace"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("do not overwrite", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty workspace"):
                prepare_price_collection_workspace(
                    config_dir=Path("config"),
                    output_root=output,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not overwrite")

    def test_workspace_excludes_retired_or_url_less_mappings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config"
            config.mkdir()
            payload = json.loads(
                (Path("config") / "symbol_mapping.json").read_text(encoding="utf-8")
            )
            payload["mappings"][0]["mapping_state"] = "RETIRED"
            payload["mappings"][1]["mapping_state"] = "UNRESOLVED_INVESTING_URL"
            payload["mappings"][1]["investing_url"] = ""
            (config / "symbol_mapping.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            output = root / "workspace"
            report = prepare_price_collection_workspace(
                config_dir=config,
                output_root=output,
            )
            self.assertEqual(report["symbol_count"], 3)
            self.assertFalse(
                (output / "raw_exports" / "investing" / "KFH.csv.placeholder").exists()
            )
            self.assertFalse(
                (output / "raw_exports" / "investing" / "NBK.csv.placeholder").exists()
            )


if __name__ == "__main__":
    unittest.main()
