from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kubo.official_foundation_import import _import_official_foundation_unchecked
from kubo.official_foundation_workspace import prepare_official_foundation_workspace
from kubo.status_corporate_import import _import_status_corporate_unchecked
from kubo.status_corporate_workspace import prepare_status_corporate_workspace
from tests.test_official_foundation_import import (
    CONTACT_HTML,
    EXTENSION_HTML,
    HOLIDAYS_HTML,
    LISTED_HTML,
    SHORT_SELL_HTML,
)


ROOT = Path(__file__).resolve().parents[1]

SUSPENDED_HTML = b"""
<html><body><table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th></tr>
<tr><td>1</td><td>108</td><td>KFH</td><td>Kuwait Finance House</td><td>Banks</td><td>Premier</td></tr>
</table></body></html>
"""

EMPTY_SUSPENDED_HTML = b"""
<html><body><table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th></tr>
</table></body></html>
"""

DELISTED_HTML = b"""
<html><body><table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th><th>Date of Delisting</th></tr>
<tr><td>1</td><td>999</td><td>OLDCO</td><td>Old Company</td><td>Services</td><td>Main</td><td>30-06-2020</td></tr>
</table></body></html>
"""

DELISTED_KFH_HTML = b"""
<html><body><table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th><th>Date of Delisting</th></tr>
<tr><td>1</td><td>108</td><td>KFH</td><td>Kuwait Finance House</td><td>Banks</td><td>Premier</td><td>30-06-2026</td></tr>
</table></body></html>
"""

CORPORATE_ACTIONS_HTML = b"""
<html><body><table>
<tr><th>ISIN Code</th><th>Sec. Code</th><th>Ticker</th><th>Cum-Dividend Date</th><th>Ex-Dividend Date</th><th>Record Date</th><th>Payment Date</th></tr>
<tr><td>KW0EQ0100010</td><td>101</td><td>NBK</td><td>2026-03-10</td><td>2026-03-11</td><td>2026-03-13</td><td>2026-03-20</td></tr>
<tr><td>KW0EQ0100085</td><td>108</td><td>KFH</td><td>2026-08-10</td><td>2026-08-11</td><td>2026-08-13</td><td>2026-08-18</td></tr>
</table></body></html>
"""

EMPTY_CORPORATE_ACTIONS_HTML = b"""
<html><body><table>
<tr><th>ISIN Code</th><th>Sec. Code</th><th>Ticker</th><th>Cum-Dividend Date</th><th>Ex-Dividend Date</th><th>Record Date</th><th>Payment Date</th></tr>
</table></body></html>
"""


class StatusCorporateImportTests(unittest.TestCase):
    def _official_foundation(self, root: Path) -> Path:
        workspace = root / "official-workspace"
        prepare_official_foundation_workspace(
            output_root=workspace,
            run_id="official-pilot-001",
            calendar_year=2026,
            prepared_by="unit-test",
        )
        manifest_path = workspace / "manifests" / "official_foundation_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["identity_snapshot_effective_date"] = "2026-08-09"
        contents = {
            "short_sell_identity": SHORT_SELL_HTML,
            "listed_companies": LISTED_HTML,
            "market_holidays": HOLIDAYS_HTML,
            "trading_extension": EXTENSION_HTML,
            "contact_hours": CONTACT_HTML,
        }
        raw_dir = workspace / "raw_exports" / "boursa"
        for row in manifest["artifacts"]:
            content = contents[row["artifact_id"]]
            (raw_dir / row["file_name"]).write_bytes(content)
            row["file_sha256"] = hashlib.sha256(content).hexdigest()
            row["observed_at"] = "2026-08-09T09:00:00+03:00"
            row["captured_by"] = "unit-test"
            row["review_status"] = "ACCEPTED"
            row["review_notes"] = "authorized contract fixture"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        output = root / "official-output"
        report = _import_official_foundation_unchecked(
            config_dir=ROOT / "config",
            workspace=workspace,
            output_root=output,
        )
        self.assertEqual(report["status"], "CURRENT_IDENTITY_AND_CALENDAR_READY")
        return output

    def _status_workspace(
        self,
        root: Path,
        *,
        suspended_html: bytes = SUSPENDED_HTML,
        delisted_html: bytes = DELISTED_HTML,
        corporate_html: bytes = CORPORATE_ACTIONS_HTML,
        result_count: int = 2,
        corrupt_hash: str | None = None,
        observed_date: str = "2026-08-09",
    ) -> Path:
        workspace = root / "status-workspace"
        prepare_status_corporate_workspace(
            output_root=workspace,
            run_id="status-ca-001",
            action_window_from="2026-01-01",
            action_window_to="2026-12-31",
            prepared_by="unit-test",
        )
        manifest_path = workspace / "manifests" / "status_corporate_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status_snapshot_effective_date"] = observed_date
        manifest["corporate_action_query"].update(
            {
                "filter_applied": True,
                "pages_declared": 1,
                "pages_received": 1,
                "result_count_declared": result_count,
                "review_status": "ACCEPTED",
                "review_notes": "rendered page count reconciled",
            }
        )
        contents = {
            "suspended_companies": suspended_html,
            "delisted_companies": delisted_html,
            "corporate_actions": corporate_html,
        }
        raw_dir = workspace / "raw_exports" / "boursa"
        for row in manifest["artifacts"]:
            content = contents[row["artifact_id"]]
            (raw_dir / row["file_name"]).write_bytes(content)
            row["file_sha256"] = (
                "f" * 64
                if row["artifact_id"] == corrupt_hash
                else hashlib.sha256(content).hexdigest()
            )
            row["observed_at"] = observed_date + "T10:00:00+03:00"
            row["captured_by"] = "unit-test"
            row["review_status"] = "ACCEPTED"
            row["review_notes"] = "authorized rendered contract fixture"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return workspace

    def test_current_status_and_action_schedule_are_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = self._official_foundation(root)
            workspace = self._status_workspace(root)
            output = root / "status-output"
            report = _import_status_corporate_unchecked(
                config_dir=ROOT / "config",
                official_foundation_root=official,
                workspace=workspace,
                output_root=output,
            )
            self.assertEqual(report["status"], "CURRENT_STATUS_AND_CA_SCHEDULE_READY")
            self.assertEqual(report["security_status"], "PASS")
            self.assertEqual(report["corporate_action_schedule_status"], "PASS")
            self.assertEqual(report["pilot_corporate_action_rows"], 2)
            self.assertEqual(report["pending_corporate_action_factor_rows"], 2)
            self.assertFalse(report["claim_boundaries"]["security_status_history_ready"])
            self.assertFalse(
                report["claim_boundaries"]["corporate_action_factor_ledger_ready"]
            )
            self.assertFalse(report["claim_boundaries"]["backtest_ready"])

            with (output / "normalized" / "security_status_evidence.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                status_rows = list(csv.DictReader(handle))
            self.assertEqual(len(status_rows), 5)
            by_ticker = {row["ticker"]: row for row in status_rows}
            self.assertEqual(by_ticker["KFH"]["status"], "SUSPENDED")
            self.assertEqual(by_ticker["NBK"]["status"], "TRADING")
            self.assertTrue(
                all(row["temporal_scope"] == "CURRENT_SNAPSHOT_ONLY" for row in status_rows)
            )

            with (output / "normalized" / "corporate_action_schedule.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                action_rows = list(csv.DictReader(handle))
            self.assertEqual(len(action_rows), 2)
            self.assertTrue(
                all(row["action_type"] == "UNCLASSIFIED_ENTITLEMENT" for row in action_rows)
            )
            self.assertTrue(all(row["factor_status"] == "pending" for row in action_rows))
            self.assertTrue(all(row["adjustment_factor"] == "" for row in action_rows))

    def test_observed_zero_suspended_and_actions_is_valid_but_not_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = self._official_foundation(root)
            workspace = self._status_workspace(
                root,
                suspended_html=EMPTY_SUSPENDED_HTML,
                corporate_html=EMPTY_CORPORATE_ACTIONS_HTML,
                result_count=0,
            )
            report = _import_status_corporate_unchecked(
                config_dir=ROOT / "config",
                official_foundation_root=official,
                workspace=workspace,
                output_root=root / "status-output",
            )
            self.assertEqual(report["status"], "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY")
            self.assertEqual(report["pilot_corporate_action_rows"], 0)
            self.assertTrue(
                report["claim_boundaries"]["corporate_action_factor_ledger_ready"]
            )
            self.assertFalse(report["claim_boundaries"]["security_status_history_ready"])

    def test_current_identity_in_delisted_archive_blocks_status_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = self._official_foundation(root)
            workspace = self._status_workspace(root, delisted_html=DELISTED_KFH_HTML)
            report = _import_status_corporate_unchecked(
                config_dir=ROOT / "config",
                official_foundation_root=official,
                workspace=workspace,
                output_root=root / "status-output",
            )
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["security_status"], "BLOCKED")
            self.assertEqual(report["corporate_action_schedule_status"], "PASS")
            status_report = json.loads(
                (root / "status-output" / "reports" / "security_status_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("CURRENT_IDENTITY_APPEARS_DELISTED:108", status_report["errors"])

    def test_corporate_action_result_count_mismatch_blocks_schedule_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = self._official_foundation(root)
            workspace = self._status_workspace(root, result_count=3)
            report = _import_status_corporate_unchecked(
                config_dir=ROOT / "config",
                official_foundation_root=official,
                workspace=workspace,
                output_root=root / "status-output",
            )
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["security_status"], "PASS")
            self.assertEqual(report["corporate_action_schedule_status"], "BLOCKED")

    def test_artifact_hash_mismatch_fails_before_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = self._official_foundation(root)
            workspace = self._status_workspace(root, corrupt_hash="corporate_actions")
            with self.assertRaisesRegex(
                ValueError,
                "artifact hash mismatch: corporate_actions",
            ):
                _import_status_corporate_unchecked(
                    config_dir=ROOT / "config",
                    official_foundation_root=official,
                    workspace=workspace,
                    output_root=root / "status-output",
                )

    def test_snapshot_cannot_precede_upstream_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = self._official_foundation(root)
            workspace = self._status_workspace(root, observed_date="2026-08-08")
            with self.assertRaisesRegex(ValueError, "precedes the upstream identity snapshot"):
                _import_status_corporate_unchecked(
                    config_dir=ROOT / "config",
                    official_foundation_root=official,
                    workspace=workspace,
                    output_root=root / "status-output",
                )


if __name__ == "__main__":
    unittest.main()
