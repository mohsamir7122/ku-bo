from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kubo.official_foundation_import import _import_official_foundation_unchecked
from kubo.official_foundation_workspace import prepare_official_foundation_workspace


ROOT = Path(__file__).resolve().parents[1]

SHORT_SELL_HTML = b"""
<html><body><table>
<tr><th>Sec Code</th><th>Name</th><th>ISIN Code</th><th>Available Shares</th><th>Borrowed Shares</th></tr>
<tr><td>101</td><td>NATIONAL BANK OF KUWAIT</td><td>KW0EQ0100010</td><td>0</td><td>0</td></tr>
<tr><td>108</td><td>KUWAIT FINANCE HOUSE</td><td>KW0EQ0100085</td><td>0</td><td>0</td></tr>
<tr><td>413</td><td>MABANEE COMPANY</td><td>KW0EQ0400725</td><td>0</td><td>0</td></tr>
<tr><td>605</td><td>MOBILE TELECOMMUNICATIONS COMPANY</td><td>KW0EQ0601058</td><td>0</td><td>0</td></tr>
<tr><td>623</td><td>HUMANSOFT HOLDING CO.</td><td>KW0EQ0601694</td><td>0</td><td>0</td></tr>
</table></body></html>
"""

LISTED_HTML = b"""
<html><body><table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th><th>Date of Listing</th></tr>
<tr><td>1</td><td>101</td><td>NBK</td><td>National Bank of Kuwait</td><td>Banks</td><td>Premier</td><td>29-09-1984</td></tr>
<tr><td>2</td><td>108</td><td>KFH</td><td>Kuwait Finance House</td><td>Banks</td><td>Premier</td><td>29-09-1984</td></tr>
<tr><td>3</td><td>413</td><td>MABANEE</td><td>Mabanee Company</td><td>Real Estate</td><td>Premier</td><td>04-11-1999</td></tr>
<tr><td>4</td><td>605</td><td>ZAIN</td><td>Mobile Telecommunications Company</td><td>Telecommunications</td><td>Premier</td><td>15-09-1985</td></tr>
<tr><td>5</td><td>623</td><td>HUMANSOFT</td><td>Humansoft Holding Company</td><td>Consumer Services</td><td>Premier</td><td>20-06-2012</td></tr>
</table></body></html>
"""

HOLIDAYS_HTML = b"""
<html><body><h2>Kuwait Public Holidays 2026</h2><table>
<tr><th>Month</th><th>Date</th><th>Vacation</th></tr>
<tr><td>January</td><td>1</td><td>New Year</td></tr>
<tr><td>January</td><td>18</td><td>Ascension of Prophet Mohammed</td></tr>
<tr><td>February</td><td>25 - 26</td><td>National Day - Liberation Day</td></tr>
<tr><td>March</td><td>19-22</td><td>Eid Al Fitr</td></tr>
<tr><td>April</td><td>-</td><td>-</td></tr>
<tr><td>May</td><td>26</td><td>Arafat Day</td></tr>
<tr><td>May</td><td>27-30</td><td>Eid Al Adha</td></tr>
<tr><td>June</td><td>16</td><td>Hijri New Year</td></tr>
<tr><td>August</td><td>27</td><td>Prophet Mohammed Birthday</td></tr>
</table></body></html>
"""

EXTENSION_HTML = b"""
<html><body>
<h2>Starting October 12th, 2025</h2>
<p>The continuous trading session will run from 9:00 a.m. to 1:00 p.m.</p>
<p>The closing auction session will run from 1:00 p.m. to 1:10 p.m.</p>
<p>The trade at last session will run from 1:10 p.m. to 1:15 p.m.</p>
</body></html>
"""

CONTACT_HTML = b"""
<html><body><p>Trading Hours: 9:00 AM - 1:15 PM (Sunday - Thursday)</p></body></html>
"""

ARTIFACT_CONTENT = {
    "short_sell_identity": SHORT_SELL_HTML,
    "listed_companies": LISTED_HTML,
    "market_holidays": HOLIDAYS_HTML,
    "trading_extension": EXTENSION_HTML,
    "contact_hours": CONTACT_HTML,
}


class OfficialFoundationImportTests(unittest.TestCase):
    def _accepted_workspace(
        self,
        root: Path,
        *,
        listed_html: bytes = LISTED_HTML,
        identity_dates: tuple[str, str] = (
            "2026-08-09T09:00:00+03:00",
            "2026-08-09T09:05:00+03:00",
        ),
        corrupt_hash: str | None = None,
    ) -> Path:
        workspace = root / "workspace"
        prepare_official_foundation_workspace(
            output_root=workspace,
            run_id="official-pilot-001",
            calendar_year=2026,
            prepared_by="unit-test",
        )
        manifest_path = workspace / "manifests" / "official_foundation_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["identity_snapshot_effective_date"] = "2026-08-09"
        content_map = dict(ARTIFACT_CONTENT)
        content_map["listed_companies"] = listed_html
        identity_times = {
            "short_sell_identity": identity_dates[0],
            "listed_companies": identity_dates[1],
        }
        raw_dir = workspace / "raw_exports" / "boursa"
        for artifact in manifest["artifacts"]:
            artifact_id = artifact["artifact_id"]
            content = content_map[artifact_id]
            (raw_dir / artifact["file_name"]).write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            artifact["file_sha256"] = (
                "f" * 64 if artifact_id == corrupt_hash else digest
            )
            artifact["observed_at"] = identity_times.get(
                artifact_id,
                "2026-08-09T09:10:00+03:00",
            )
            artifact["captured_by"] = "unit-test"
            artifact["review_status"] = "ACCEPTED"
            artifact["review_notes"] = "generated authorized contract fixture"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return workspace

    def test_end_to_end_current_identity_and_calendar_are_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._accepted_workspace(root)
            output = root / "output"
            report = _import_official_foundation_unchecked(
                config_dir=ROOT / "config",
                workspace=workspace,
                output_root=output,
            )
            self.assertEqual(
                report["status"],
                "CURRENT_IDENTITY_AND_CALENDAR_READY",
            )
            self.assertEqual(report["identity_status"], "PASS")
            self.assertEqual(report["calendar_status"], "PASS")
            self.assertFalse(report["claim_boundaries"]["backtest_ready"])
            self.assertFalse(
                report["claim_boundaries"]["current_identity_is_historical_identity"]
            )

            with (output / "normalized" / "security_master.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                identities = list(csv.DictReader(handle))
            self.assertEqual(len(identities), 5)
            self.assertTrue(
                all(row["identity_scope"] == "CURRENT_SNAPSHOT_ONLY" for row in identities)
            )
            self.assertTrue(
                all(row["supporting_raw_sha256s"] for row in identities)
            )
            self.assertTrue(all(row["valid_from"] == "2026-08-09" for row in identities))

            with (output / "normalized" / "trading_calendar.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                calendar = list(csv.DictReader(handle))
            self.assertEqual(len(calendar), 365)
            holiday = next(row for row in calendar if row["trade_date"] == "2026-02-25")
            self.assertEqual(holiday["session_type"], "HOLIDAY")
            self.assertEqual(holiday["is_trading_day"], "false")
            normal = next(row for row in calendar if row["trade_date"] == "2026-02-24")
            self.assertEqual(normal["session_type"], "NORMAL")
            self.assertEqual(normal["continuous_start"], "09:00:00")
            self.assertEqual(normal["continuous_end"], "13:00:00")
            self.assertEqual(normal["trade_at_last_end"], "13:15:00")

    def test_official_isin_conflict_blocks_identity_but_not_calendar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_short = SHORT_SELL_HTML.replace(b"KW0EQ0100010", b"KW0EQ0100028")
            original = ARTIFACT_CONTENT["short_sell_identity"]
            ARTIFACT_CONTENT["short_sell_identity"] = bad_short
            try:
                workspace = self._accepted_workspace(root)
            finally:
                ARTIFACT_CONTENT["short_sell_identity"] = original
            report = _import_official_foundation_unchecked(
                config_dir=ROOT / "config",
                workspace=workspace,
                output_root=root / "output",
            )
            self.assertEqual(report["status"], "PARTIAL")
            self.assertEqual(report["identity_status"], "BLOCKED")
            self.assertEqual(report["calendar_status"], "PASS")
            identity_report = json.loads(
                (root / "output" / "reports" / "official_identity_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(
                any("OFFICIAL_ISIN_CONFLICT:101" in item for item in identity_report["errors"])
            )

    def test_hash_mismatch_is_rejected_before_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._accepted_workspace(root, corrupt_hash="market_holidays")
            with self.assertRaisesRegex(ValueError, "hash mismatch: market_holidays"):
                _import_official_foundation_unchecked(
                    config_dir=ROOT / "config",
                    workspace=workspace,
                    output_root=root / "output",
                )

    def test_identity_artifacts_must_share_one_kuwait_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._accepted_workspace(
                root,
                identity_dates=(
                    "2026-08-09T23:50:00+03:00",
                    "2026-08-10T00:05:00+03:00",
                ),
            )
            with self.assertRaisesRegex(ValueError, "one Kuwait civil date"):
                _import_official_foundation_unchecked(
                    config_dir=ROOT / "config",
                    workspace=workspace,
                    output_root=root / "output",
                )

    def test_unrendered_listed_companies_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._accepted_workspace(
                root,
                listed_html=b"<html><body><div id='client-app'></div></body></html>",
            )
            with self.assertRaisesRegex(
                ValueError,
                "REQUIRED_OFFICIAL_TABLE_HEADERS_NOT_FOUND",
            ):
                _import_official_foundation_unchecked(
                    config_dir=ROOT / "config",
                    workspace=workspace,
                    output_root=root / "output",
                )


if __name__ == "__main__":
    unittest.main()
