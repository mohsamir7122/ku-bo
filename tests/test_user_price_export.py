from __future__ import annotations

from contextlib import redirect_stdout
import csv
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from kubo.cli_v3 import main as cli_main
from kubo.hashing import sha256_bytes
from kubo.price_collection_workspace import MANIFEST_HEADERS
from kubo.user_price_export import import_investing_user_exports


ROOT = Path(__file__).resolve().parents[1]
OBSERVED_AT = "2026-08-07T00:50:00+03:00"


class UserPriceExportTests(unittest.TestCase):
    def _fixture_config(self, directory: Path, symbols: tuple[str, ...] = ("AAA",)) -> Path:
        config = directory / "config"
        config.mkdir()
        for name in (
            "source_network.json",
            "methods.json",
            "products.json",
            "research_policies.json",
            "source_capabilities.json",
            "sources.json",
        ):
            shutil.copyfile(ROOT / "config" / name, config / name)
        mappings = []
        valid_isins = ("KW0EQ0100010", "KW0EQ0100085")
        for index, symbol in enumerate(symbols, start=1):
            mappings.append(
                {
                    "security_code": str(100 + index),
                    "boursa_symbol": symbol,
                    "name_en": f"{symbol} Test Company",
                    "name_ar": "",
                    "isin": valid_isins[index - 1],
                    "sector": "Test",
                    "investing_slug": f"{symbol.lower()}-test",
                    "investing_url": f"https://www.investing.com/equities/{symbol.lower()}-test-historical-data",
                    "tradingview_symbol": f"KSE:{symbol}",
                    "marketscreener_query": f"{symbol} Test Company",
                    "mapping_state": "CANDIDATE_URL_OBSERVED",
                    "evidence_notes": "Generated fixture.",
                }
            )
        mapping = {
            "schema_version": "1.0",
            "as_of": "2026-08-08",
            "coverage": {"scope": "TEST_FIXTURE", "security_count": len(mappings)},
            "mappings": mappings,
        }
        (config / "symbol_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
        return config

    def _fixture_export(self, directory: Path, symbol: str = "AAA") -> Path:
        exports = directory / "exports"
        exports.mkdir(exist_ok=True)
        (exports / f"{symbol}.csv").write_bytes(
            (
                "Date,Price,Open,High,Low,Vol.,Change %\n"
                '"Aug 06, 2026",101.000,100.000,102.000,99.000,1.25M,+1.00%\n'
                '"Aug 05, 2026",100.000,99.000,101.000,98.000,1.00M,0.00%\n'
            ).encode("utf-8")
        )
        return exports

    def _write_manifest(
        self,
        exports: Path,
        symbols: tuple[str, ...] = ("AAA",),
        overrides: dict[str, str] | None = None,
    ) -> Path:
        rows = []
        valid_isins = ("KW0EQ0100010", "KW0EQ0100085")
        for index, symbol in enumerate(symbols, start=1):
            content = (exports / f"{symbol}.csv").read_bytes()
            row = {
                "ticker": symbol,
                "security_code": str(100 + index),
                "isin": valid_isins[index - 1],
                "name_en": f"{symbol} Test Company",
                "sector": "Test",
                "source_name": "investing",
                "source_type": "SECONDARY_MANUAL_EXPORT",
                "source_url_or_location": f"https://www.investing.com/equities/{symbol.lower()}-test-historical-data",
                "downloaded_at": "2026-08-06T18:00:00+03:00",
                "downloaded_by": "authorized tester",
                "file_name": f"{symbol}.csv",
                "file_sha256": sha256_bytes(content),
                "date_range_start": "2026-08-05",
                "date_range_end": "2026-08-06",
                "row_count": "2",
                "price_basis": "RAW",
                "currency": "KWD",
                "unit": "fils",
                "allowed_use": "USER_EXPORT",
                "review_status": "ACCEPTED",
                "review_notes": "fixture accepted",
            }
            if overrides:
                row.update(overrides)
            rows.append(row)
        path = exports / "price_collection_manifest.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_HEADERS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _import(self, root: Path, exports: Path) -> tuple[dict[str, object], Path]:
        output = root / "run"
        report = import_investing_user_exports(
            config_dir=root / "config",
            input_dir=exports,
            output_root=output,
            observed_at=OBSERVED_AT,
        )
        return report, output

    def test_import_writes_manifest_bound_normalized_pack_and_blocked_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            original = (exports / "AAA.csv").read_bytes()
            manifest_path = self._write_manifest(exports)
            report, output = self._import(root, exports)

            self.assertEqual(report["status"], "PRICE_IMPORT_READY_ONLY")
            self.assertEqual(report["row_count"], 2)
            self.assertEqual(
                (output / "price_collection_manifest.csv").read_bytes(),
                manifest_path.read_bytes(),
            )
            self.assertEqual(
                report["collection_manifest_sha256"],
                sha256_bytes(manifest_path.read_bytes()),
            )
            self.assertEqual((output / "raw" / "AAA.investing_export.csv").read_bytes(), original)
            eod_rows = list(
                csv.DictReader(StringIO((output / "normalized" / "eod_ohlcv.csv").read_text(encoding="utf-8")))
            )
            self.assertEqual((eod_rows[0]["price_basis"], eod_rows[0]["currency"], eod_rows[0]["unit"]), ("RAW", "KWD", "fils"))
            self.assertEqual(eod_rows[0]["raw_sha256"], sha256_bytes(original))
            observations = json.loads((output / "source_observations.json").read_text())
            self.assertEqual([row["source_id"] for row in observations["sources"]], ["investing_history"])
            self.assertFalse((output / "parser_plan_investing_user_export.json").exists())
            draft = json.loads((output / "parser_plan_investing_user_export_draft.json").read_text())
            self.assertEqual(draft["status"], "BLOCKED_REQUIREMENTS")
            self.assertFalse(draft["materialization_ready"])
            self.assertNotIn("2020-01-01", json.dumps(draft))

    def test_cli_import_uses_ready_only_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            self._write_manifest(exports)
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = cli_main(
                    ["--project-root", str(root), "import-investing-user-exports", "--input-dir", str(exports), "--output-root", str(root / "run"), "--observed-at", OBSERVED_AT]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "PRICE_IMPORT_READY_ONLY")

    def test_missing_manifest_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            report, _ = self._import(root, exports)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(report["manifest_errors"])
            self.assertIn("AAA", report["rejected_exports"])

    def test_one_valid_and_one_missing_export_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root, ("AAA", "BBB"))
            exports = self._fixture_export(root, "AAA")
            self._write_manifest(exports, ("AAA",))
            report, _ = self._import(root, exports)
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["imported_symbols"], ["AAA"])
            self.assertEqual(report["missing_exports"], ["BBB"])

    def test_manifest_hash_mismatch_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            self._write_manifest(exports, overrides={"file_sha256": "0" * 64})
            report, _ = self._import(root, exports)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertIn("does not match", report["rejected_exports"]["AAA"])

    def test_latest_session_cannot_exceed_observed_at_in_kuwait(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            (exports / "AAA.csv").write_text(
                "Date,Price,Open,High,Low,Vol.,Change %\n"
                '"Aug 08, 2026",101.000,100.000,102.000,99.000,1.25M,+1.00%\n'
                '"Aug 07, 2026",100.000,99.000,101.000,98.000,1.00M,0.00%\n',
                encoding="utf-8",
            )
            self._write_manifest(
                exports,
                overrides={"date_range_start": "2026-08-07", "date_range_end": "2026-08-08"},
            )
            report, _ = self._import(root, exports)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertIn("Asia/Kuwait", report["rejected_exports"]["AAA"])

    def test_manifest_policy_fields_are_enforced(self) -> None:
        cases = (
            ({"security_code": "999"}, "security_code"),
            ({"isin": "KW0EQ9999999"}, "isin"),
            ({"source_name": "other"}, "source_name"),
            ({"source_url_or_location": "https://example.com/wrong"}, "source_url"),
            ({"downloaded_at": "2026-08-08T00:00:00+03:00"}, "downloaded_at"),
            ({"file_name": "wrong.csv"}, "file_name"),
            ({"date_range_start": "2026-08-04"}, "date range"),
            ({"row_count": "3"}, "row_count"),
            ({"price_basis": "UNKNOWN"}, "price_basis"),
            ({"currency": "USD"}, "currency"),
            ({"unit": "shares"}, "unit"),
            ({"allowed_use": "SECONDARY_CHECK"}, "allowed_use"),
            ({"review_status": "PENDING"}, "review_status"),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._fixture_config(root)
                exports = self._fixture_export(root)
                self._write_manifest(exports, overrides=overrides)
                report, _ = self._import(root, exports)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertIn(expected, report["rejected_exports"]["AAA"])

    def test_future_session_symlink_and_limits_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            self._write_manifest(exports)
            real = exports / "AAA.csv"
            saved = exports / "saved.csv"
            real.rename(saved)
            real.symlink_to(saved)
            report, _ = self._import(root, exports)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertIn("symlink", report["rejected_exports"]["AAA"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            self._write_manifest(exports)
            with patch("kubo.user_price_export.MAX_EXPORT_BYTES", 10):
                report, _ = self._import(root, exports)
            self.assertIn("exceeds", report["rejected_exports"]["AAA"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            self._write_manifest(exports)
            with patch("kubo.user_price_export.MAX_EXPORT_ROWS", 1):
                report, _ = self._import(root, exports)
            self.assertIn("exceeds", report["rejected_exports"]["AAA"])

    def test_output_root_must_be_empty_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture_config(root)
            exports = self._fixture_export(root)
            self._write_manifest(exports)
            output = root / "run"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be empty"):
                import_investing_user_exports(
                    config_dir=root / "config",
                    input_dir=exports,
                    output_root=output,
                    observed_at=OBSERVED_AT,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
            self.assertEqual(list(output.iterdir()), [sentinel])


if __name__ == "__main__":
    unittest.main()
