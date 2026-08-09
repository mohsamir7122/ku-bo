from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest

from kubo.research_price_history import (
    RESEARCH_PRICE_HISTORY_HEADERS,
    read_research_price_history,
    validate_research_price_history_rows,
)


class ResearchPriceHistoryTests(unittest.TestCase):
    @staticmethod
    def _row(
        trade_date: str,
        close: str,
        change_percent: str,
        *,
        unit: str = "fils",
        raw_sha256: str = "a" * 64,
    ) -> dict[str, str]:
        return {
            "trade_date": trade_date,
            "security_code": "101",
            "ticker": "NBK",
            "open": close,
            "high": str(float(close) + 1),
            "low": str(float(close) - 1),
            "close": close,
            "volume": "0" if trade_date.endswith("07") else "1000",
            "change_percent": change_percent,
            "source_id": "investing_history",
            "source_url": "https://www.investing.com/equities/national-bank-kt-historical-data",
            "raw_sha256": raw_sha256,
            "capture_mode": "USER_EXPORT",
            "price_basis": "RAW",
            "currency": "KWD",
            "unit": unit,
            "corporate_action_status": "raw_unadjusted",
        }

    def test_valid_rows_pass_without_inventing_complete_eod(self) -> None:
        rows = [
            self._row("2026-08-08", "101", "1.0"),
            self._row("2026-08-07", "100", "0.0"),
        ]
        parsed, report = validate_research_price_history_rows(
            rows,
            manifest_hashes=frozenset({"a" * 64}),
        )
        self.assertEqual(report.status, "PASS")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(report.coverage["101"]["zero_volume_rows"], 1)
        self.assertFalse(
            report.claim_boundaries["research_price_history_is_complete_daily_eod"]
        )
        self.assertFalse(report.claim_boundaries["backtest_ready"])

    def test_mixed_units_and_bases_are_blocked(self) -> None:
        rows = [
            self._row("2026-08-08", "101", "1.0", unit="KWD"),
            self._row("2026-08-07", "100", "0.0"),
        ]
        _, report = validate_research_price_history_rows(rows)
        self.assertEqual(report.status, "BLOCKED")
        self.assertTrue(any("mixed price units" in error for error in report.errors))

    def test_impossible_ohlc_and_unresolved_hash_are_blocked(self) -> None:
        row = self._row("2026-08-08", "101", "1.0")
        row["high"] = "99"
        _, report = validate_research_price_history_rows(
            [row],
            manifest_hashes=frozenset({"b" * 64}),
        )
        self.assertEqual(report.status, "BLOCKED")
        self.assertTrue(any("OHLC high constraint" in error for error in report.errors))

    def test_change_percent_is_reconciled(self) -> None:
        rows = [
            self._row("2026-08-08", "101", "8.0"),
            self._row("2026-08-07", "100", "0.0"),
        ]
        _, report = validate_research_price_history_rows(rows)
        self.assertEqual(report.status, "BLOCKED")
        self.assertTrue(any("change_percent mismatch" in error for error in report.errors))

    def test_csv_headers_must_match_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(*RESEARCH_PRICE_HISTORY_HEADERS, "trade_count"),
                )
                writer.writeheader()
            _, report = read_research_price_history(path)
            self.assertEqual(report.status, "BLOCKED")
            self.assertTrue(any("headers" in error for error in report.errors))


if __name__ == "__main__":
    unittest.main()
