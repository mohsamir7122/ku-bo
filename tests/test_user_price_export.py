from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kubo.price_collection_workspace import MANIFEST_HEADERS, prepare_price_collection_workspace
from kubo.user_price_export import (
    INVESTING_EXPORT_HEADERS,
    _import_investing_user_exports_unchecked,
)


ROOT = Path(__file__).resolve().parents[1]


class UserPriceExportTests(unittest.TestCase):
    @staticmethod
    def _export_bytes() -> bytes:
        from io import StringIO

        output = StringIO(newline="")
        writer = csv.DictWriter(
            output,
            fieldnames=INVESTING_EXPORT_HEADERS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "Date": "Aug 08, 2026",
                "Price": "101",
                "Open": "100",
                "High": "102",
                "Low": "99",
                "Vol.": "1K",
                "Change %": "1.00%",
            }
        )
        writer.writerow(
            {
                "Date": "Aug 07, 2026",
                "Price": "100",
                "Open": "100",
                "High": "101",
                "Low": "99",
                "Vol.": "900",
                "Change %": "0.00%",
            }
        )
        return output.getvalue().encode("utf-8")

    def _workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        prepare_price_collection_workspace(
            config_dir=ROOT / "config",
            output_root=workspace,
            downloaded_by="unit-test",
        )
        return workspace

    def _accept_exports(
        self,
        workspace: Path,
        *,
        tickers: set[str] | None = None,
        corrupt_hash_for: str | None = None,
    ) -> None:
        manifest_path = workspace / "manifests" / "price_collection_manifest.csv"
        with manifest_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        selected = tickers or {row["ticker"] for row in rows}
        content = self._export_bytes()
        for row in rows:
            if row["ticker"] not in selected:
                continue
            path = workspace / "raw_exports" / "investing" / f"{row['ticker']}.csv"
            path.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            row.update(
                {
                    "downloaded_at": "2026-08-09T09:00:00+03:00",
                    "downloaded_by": "unit-test",
                    "file_sha256": (
                        "b" * 64 if row["ticker"] == corrupt_hash_for else digest
                    ),
                    "date_range_start": "2026-08-07",
                    "date_range_end": "2026-08-08",
                    "row_count": "2",
                    "price_basis": "RAW",
                    "currency": "KWD",
                    "unit": "fils",
                    "allowed_use": "USER_EXPORT",
                    "review_status": "ACCEPTED",
                    "review_notes": "validated fixture",
                }
            )
        with manifest_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=MANIFEST_HEADERS,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)

    def test_all_five_exports_produce_ready_price_history_but_block_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._workspace(root)
            self._accept_exports(workspace)
            output = root / "output"
            report = _import_investing_user_exports_unchecked(
                config_dir=ROOT / "config",
                input_dir=workspace / "raw_exports" / "investing",
                output_root=output,
                observed_at="2026-08-09T10:00:00+03:00",
            )
            self.assertEqual(report["status"], "BLOCKED_OFFICIAL_IDENTITY")
            self.assertEqual(
                report["price_history_status"],
                "RESEARCH_PRICE_HISTORY_READY",
            )
            self.assertEqual(report["promotion_ceiling"], "PRICE_IMPORT_READY_ONLY")
            self.assertEqual(report["row_count"], 10)
            self.assertEqual(len(report["imported_symbols"]), 5)
            self.assertFalse(report["official_identity_ready"])
            self.assertTrue(
                (output / "normalized" / "research_price_history.csv").is_file()
            )
            self.assertFalse(list(output.rglob("*.html")))
            self.assertFalse(
                report["claim_boundaries"][
                    "promotion_beyond_price_import_ready_allowed"
                ]
            )
            quality = json.loads(
                (output / "reports" / "data_quality_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(quality["status"], "PASS")
            evidence = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(evidence["artifacts"]), 5)

    def test_missing_exports_are_partial_not_synthetic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._workspace(root)
            self._accept_exports(workspace, tickers={"NBK"})
            output = root / "output"
            report = _import_investing_user_exports_unchecked(
                config_dir=ROOT / "config",
                input_dir=workspace / "raw_exports" / "investing",
                output_root=output,
                observed_at="2026-08-09T10:00:00+03:00",
            )
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["row_count"], 2)
            self.assertEqual(report["imported_symbols"], ["NBK"])
            self.assertEqual(len(report["missing_exports"]), 4)
            self.assertTrue(report["claim_boundaries"]["no_synthetic_market_fields_created"])

    def test_manifest_hash_mismatch_rejects_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._workspace(root)
            self._accept_exports(
                workspace,
                tickers={"NBK"},
                corrupt_hash_for="NBK",
            )
            report = _import_investing_user_exports_unchecked(
                config_dir=ROOT / "config",
                input_dir=workspace / "raw_exports" / "investing",
                output_root=root / "output",
                observed_at="2026-08-09T10:00:00+03:00",
            )
            self.assertEqual(report["status"], "BLOCKED")
            self.assertIn("NBK", report["rejected_exports"])
            self.assertIn("file_sha256", report["rejected_exports"]["NBK"])

    def test_non_empty_output_root_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._workspace(root)
            output = root / "output"
            output.mkdir()
            (output / "existing.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be empty"):
                _import_investing_user_exports_unchecked(
                    config_dir=ROOT / "config",
                    input_dir=workspace / "raw_exports" / "investing",
                    output_root=output,
                    observed_at="2026-08-09T10:00:00+03:00",
                )
            self.assertEqual(
                (output / "existing.txt").read_text(encoding="utf-8"),
                "keep",
            )


if __name__ == "__main__":
    unittest.main()
