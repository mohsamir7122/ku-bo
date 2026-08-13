from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kubo.status_history_import import _import_status_history_unchecked
from kubo.status_history_workspace import prepare_status_history_workspace
from tests.foundation_fixture_helpers import build_status_corporate_output


HISTORICAL_URL = (
    "https://www.boursakuwait.com.kw/en/announcements/"
    "disclosures-and-announcements/historical-disclosures-and-announcements/"
)


class StatusHistoryImportTests(unittest.TestCase):
    def _workspace(
        self,
        root: Path,
        *,
        zero_suspended_upstream: bool = False,
        include_kfh_suspend: bool = True,
        missing_phrase: bool = False,
        bad_query_count: bool = False,
    ) -> tuple[Path, Path]:
        upstream = build_status_corporate_output(
            root,
            zero_suspended=zero_suspended_upstream,
        )
        workspace = root / "history-workspace"
        prepare_status_history_workspace(
            status_corporate_root=upstream,
            output_root=workspace,
            run_id="status-history-001",
            history_window_from="2026-01-01",
            history_window_to="2026-08-09",
            prepared_by="unit-test",
        )
        manifest_path = workspace / "manifests" / "status_history_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        for query in manifest["queries"]:
            is_kfh = query["ticker"] == "KFH"
            expected_notices = 1 if include_kfh_suspend and is_kfh else 0
            if bad_query_count and query["ticker"] == "NBK":
                expected_notices = 1
            content = (
                f"Rendered historical-disclosure query for {query['ticker']}. "
                f"Result count {expected_notices}."
            ).encode("utf-8")
            path = workspace / "raw_exports" / "queries" / query["raw_file_name"]
            path.write_bytes(content)
            query.update(
                {
                    "raw_sha256": hashlib.sha256(content).hexdigest(),
                    "pages_declared": 1,
                    "pages_received": 1,
                    "result_count_declared": expected_notices,
                    "rows_normalized": expected_notices,
                    "zero_result": expected_notices == 0,
                    "observed_at": "2026-08-09T12:00:00+03:00",
                    "captured_by": "unit-test",
                    "review_status": "ACCEPTED",
                    "review_notes": "complete rendered query fixture",
                }
            )

        for opening in manifest["opening_states"]:
            phrase = f"Opening status for {opening['ticker']} was trading"
            content = phrase.encode("utf-8")
            path = (
                workspace
                / "raw_exports"
                / "opening_states"
                / opening["raw_file_name"]
            )
            path.write_bytes(content)
            opening.update(
                {
                    "status": "TRADING",
                    "source_id": "boursa_historical_disclosures",
                    "source_url": HISTORICAL_URL,
                    "raw_sha256": hashlib.sha256(content).hexdigest(),
                    "evidence_excerpt": phrase,
                    "observed_at": "2026-08-09T12:05:00+03:00",
                    "captured_by": "unit-test",
                    "review_status": "ACCEPTED",
                    "review_notes": "reviewed opening state fixture",
                }
            )

        if include_kfh_suspend:
            query_id = next(
                query["query_id"]
                for query in manifest["queries"]
                if query["ticker"] == "KFH"
            )
            phrase = "KFH suspended from trading effective 1 June 2026"
            raw_content = (
                "Official market status notice. " + phrase + "."
            ).encode("utf-8")
            text_content = raw_content
            raw_name = "kfh-suspend-2026-06-01.official"
            text_name = "kfh-suspend-2026-06-01.txt"
            (workspace / "raw_exports" / "notices" / raw_name).write_bytes(
                raw_content
            )
            (workspace / "text_exports" / "notices" / text_name).write_bytes(
                text_content
            )
            manifest["notices"].append(
                {
                    "notice_id": "kfh-suspend-2026-06-01",
                    "security_code": "108",
                    "ticker": "KFH",
                    "event_type": "SUSPEND",
                    "effective_date": "2026-06-01",
                    "published_date": "2026-06-01",
                    "source_id": "boursa_historical_disclosures",
                    "source_url": HISTORICAL_URL,
                    "raw_file_name": raw_name,
                    "raw_sha256": hashlib.sha256(raw_content).hexdigest(),
                    "text_file_name": text_name,
                    "text_sha256": hashlib.sha256(text_content).hexdigest(),
                    "text_derivation": "OFFICIAL_HTML_VISIBLE_TEXT",
                    "query_id": query_id,
                    "classification_phrase": (
                        "phrase absent" if missing_phrase else phrase
                    ),
                    "captured_at": "2026-08-09T12:10:00+03:00",
                    "captured_by": "unit-test",
                    "review_status": "ACCEPTED",
                    "review_notes": "reviewed status notice fixture",
                }
            )

        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return upstream, workspace

    def test_notice_ledger_builds_declared_window_intervals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(root)
            output = root / "history-output"
            report = _import_status_history_unchecked(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=output,
            )
            self.assertEqual(report["status"], "HISTORICAL_STATUS_INTERVALS_READY")
            self.assertEqual(report["security_count"], 5)
            self.assertEqual(report["notice_count"], 1)
            self.assertEqual(report["interval_count"], 6)
            self.assertTrue(
                report["claim_boundaries"][
                    "status_history_ready_for_declared_window"
                ]
            )
            self.assertFalse(report["claim_boundaries"]["backtest_ready"])

            import csv

            with (output / "normalized" / "status_intervals.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                intervals = list(csv.DictReader(handle))
            kfh = [row for row in intervals if row["ticker"] == "KFH"]
            self.assertEqual(len(kfh), 2)
            self.assertEqual(kfh[0]["status"], "TRADING")
            self.assertEqual(kfh[0]["effective_to"], "2026-05-31")
            self.assertEqual(kfh[1]["status"], "SUSPENDED")
            self.assertEqual(kfh[1]["effective_from"], "2026-06-01")
            self.assertEqual(kfh[1]["effective_to"], "2026-08-09")

    def test_explicit_zero_queries_can_prove_stable_declared_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(
                root,
                zero_suspended_upstream=True,
                include_kfh_suspend=False,
            )
            report = _import_status_history_unchecked(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=root / "history-output",
            )
            self.assertEqual(report["status"], "HISTORICAL_STATUS_INTERVALS_READY")
            self.assertEqual(report["notice_count"], 0)
            self.assertEqual(report["interval_count"], 5)
            self.assertFalse(
                report["claim_boundaries"]["history_outside_declared_window_ready"]
            )

    def test_missing_classification_phrase_blocks_notice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(root, missing_phrase=True)
            report = _import_status_history_unchecked(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=root / "history-output",
            )
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(
                any("classification phrase is absent" in error for error in report["errors"])
            )

    def test_query_notice_count_must_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(root, bad_query_count=True)
            report = _import_status_history_unchecked(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=root / "history-output",
            )
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(
                any("QUERY_NOTICE_RECONCILIATION" in error for error in report["errors"])
            )

    def test_history_must_reconcile_to_current_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream, workspace = self._workspace(
                root,
                zero_suspended_upstream=True,
                include_kfh_suspend=True,
            )
            report = _import_status_history_unchecked(
                status_corporate_root=upstream,
                workspace=workspace,
                output_root=root / "history-output",
            )
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(
                any("CURRENT_STATUS_RECONCILIATION" in error for error in report["errors"])
            )


if __name__ == "__main__":
    unittest.main()
