from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from kubo.benchmark_history import (
    BENCHMARK_HISTORY_HEADERS,
    RIGHTS_STATUSES,
    BenchmarkEvidenceBinding,
    parse_benchmark_history_row,
    read_benchmark_history,
    validate_benchmark_history_rows,
)
from kubo.benchmark_import import RIGHTS_STATUSES as IMPORT_RIGHTS_STATUSES
from kubo.benchmark_registry import load_benchmark_registry
from kubo.official_eod_workspace import RIGHTS_STATUSES as SHARED_RIGHTS_STATUSES


ROOT = Path(__file__).resolve().parents[1]
DIGEST = "a" * 64


class BenchmarkHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_benchmark_registry(ROOT / "config")
        cls.definition = cls.registry.by_code["KU_BO_BROAD_MARKET_PRICE"]

    def _binding(
        self,
        *,
        capture_mode: str = "RECORDED_AUTHORIZED_FIXTURE",
        rights_status: str = "FIXTURE_ONLY",
        evidence_classification: str = "RECORDED_AUTHORIZED_FIXTURE",
    ) -> BenchmarkEvidenceBinding:
        return BenchmarkEvidenceBinding(
            benchmark_code=self.definition.benchmark_code,
            source_url=self.definition.source_url,
            raw_sha256=DIGEST,
            observed_at="2026-08-10T09:00:00+03:00",
            capture_mode=capture_mode,
            rights_status=rights_status,
            evidence_classification=evidence_classification,
        )

    def _row(self, trade_date: str = "2026-08-03") -> dict[str, str]:
        definition = self.definition
        return {
            "trade_date": trade_date,
            "benchmark_code": definition.benchmark_code,
            "benchmark_name": definition.benchmark_name,
            "market_scope": definition.market_scope,
            "sector": definition.sector,
            "calculation_basis": definition.calculation_basis,
            "benchmark_value": "1234.50",
            "currency": definition.currency,
            "unit": definition.unit,
            "provider": definition.provider,
            "source_id": definition.source_id,
            "source_url": definition.source_url,
            "raw_sha256": DIGEST,
            "observed_at": "2026-08-10T09:00:00+03:00",
            "capture_mode": "RECORDED_AUTHORIZED_FIXTURE",
            "rights_status": "FIXTURE_ONLY",
            "evidence_classification": "RECORDED_AUTHORIZED_FIXTURE",
        }

    def _parse(self, row: dict[str, str], binding: BenchmarkEvidenceBinding | None = None):
        binding = binding or self._binding()
        return parse_benchmark_history_row(
            row,
            registry=self.registry,
            bindings={self.definition.benchmark_code: binding},
            manifest_hashes=frozenset({DIGEST}),
        )

    def test_rights_vocabulary_matches_shared_eod_contract(self) -> None:
        self.assertEqual(RIGHTS_STATUSES, SHARED_RIGHTS_STATUSES)
        self.assertEqual(IMPORT_RIGHTS_STATUSES, SHARED_RIGHTS_STATUSES)

    def test_normalized_recorded_fixture_contract_parses_without_real_claim(self) -> None:
        parsed = self._parse(self._row())
        self.assertEqual(parsed.benchmark_code, "KU_BO_BROAD_MARKET_PRICE")
        self.assertEqual(parsed.evidence_classification, "RECORDED_AUTHORIZED_FIXTURE")

    def test_scope_basis_currency_and_unit_are_registry_bound(self) -> None:
        cases = {
            "market_scope": "SECTOR",
            "sector": "Banks",
            "calculation_basis": "TOTAL_RETURN_INDEX",
            "currency": "USD",
            "unit": "PERCENT",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                row = self._row()
                row[field] = value
                with self.assertRaisesRegex(ValueError, "differs from the benchmark registry"):
                    self._parse(row)

    def test_impossible_values_fail_closed(self) -> None:
        for value in ("0", "-1", "NaN", "Infinity", "1000000000001"):
            with self.subTest(value=value):
                row = self._row()
                row["benchmark_value"] = value
                with self.assertRaisesRegex(ValueError, "benchmark_value"):
                    self._parse(row)

    def test_hash_and_source_url_must_match_accepted_evidence_binding(self) -> None:
        for field, value in (
            ("raw_sha256", "b" * 64),
            ("source_url", "https://example.invalid/export.csv"),
        ):
            with self.subTest(field=field):
                row = self._row()
                row[field] = value
                with self.assertRaisesRegex(ValueError, "differs from the accepted binding"):
                    self._parse(row)

    def test_recorded_fixture_cannot_claim_proven_real_evidence(self) -> None:
        row = self._row()
        row["evidence_classification"] = "PROVEN_REAL_EVIDENCE"
        binding = self._binding(evidence_classification="PROVEN_REAL_EVIDENCE")
        with self.assertRaisesRegex(ValueError, "conflict"):
            self._parse(row, binding)

    def test_licensed_rows_remain_licensed_feed_dependent(self) -> None:
        row = self._row()
        row.update(
            {
                "capture_mode": "LICENSED_VENDOR_EXPORT",
                "rights_status": "RESEARCH_USE_AUTHORIZED",
                "evidence_classification": "LICENSED_FEED_DEPENDENT",
            }
        )
        binding = self._binding(
            capture_mode="LICENSED_VENDOR_EXPORT",
            rights_status="RESEARCH_USE_AUTHORIZED",
            evidence_classification="LICENSED_FEED_DEPENDENT",
        )
        parsed = self._parse(row, binding)
        self.assertEqual(parsed.evidence_classification, "LICENSED_FEED_DEPENDENT")

    def test_duplicate_and_out_of_order_dates_are_blocked(self) -> None:
        duplicate_rows = [self._row(), self._row()]
        out_of_order_rows = [self._row("2026-08-04"), self._row("2026-08-03")]
        for rows, expected in (
            (duplicate_rows, "duplicate benchmark/trading-date key"),
            (out_of_order_rows, "strictly increasing"),
        ):
            with self.subTest(expected=expected):
                _, report = validate_benchmark_history_rows(
                    rows,
                    registry=self.registry,
                    bindings={self.definition.benchmark_code: self._binding()},
                    manifest_hashes=frozenset({DIGEST}),
                    trading_dates=frozenset({date(2026, 8, 3), date(2026, 8, 4)}),
                    window_from=date(2026, 8, 3),
                    window_to=date(2026, 8, 4),
                    expected_codes=frozenset({self.definition.benchmark_code}),
                )
                self.assertEqual(report.status, "BLOCKED")
                self.assertTrue(any(expected in error for error in report.errors))

    def test_calendar_gap_is_reported_without_forward_fill(self) -> None:
        parsed, report = validate_benchmark_history_rows(
            [self._row("2026-08-03")],
            registry=self.registry,
            bindings={self.definition.benchmark_code: self._binding()},
            manifest_hashes=frozenset({DIGEST}),
            trading_dates=frozenset({date(2026, 8, 3), date(2026, 8, 4)}),
            window_from=date(2026, 8, 3),
            window_to=date(2026, 8, 4),
            expected_codes=frozenset({self.definition.benchmark_code}),
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(report.status, "BLOCKED")
        coverage = report.coverage[self.definition.benchmark_code]
        self.assertEqual(coverage["missing_trading_dates"], ["2026-08-04"])
        self.assertFalse(report.claim_boundaries["forward_fill_used"])

    def test_reader_rejects_noncanonical_headers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark_history.csv"
            headers = list(BENCHMARK_HISTORY_HEADERS)
            headers[-1] = "classification"
            path.write_text(",".join(headers) + "\n", encoding="utf-8")
            parsed, report = read_benchmark_history(
                path,
                registry=self.registry,
                bindings={},
                manifest_hashes=frozenset(),
                trading_dates=frozenset({date(2026, 8, 3)}),
                window_from=date(2026, 8, 3),
                window_to=date(2026, 8, 3),
                expected_codes=frozenset(),
            )
        self.assertEqual(parsed, ())
        self.assertEqual(report.status, "BLOCKED")
        self.assertIn("headers", report.errors[0])


if __name__ == "__main__":
    unittest.main()
