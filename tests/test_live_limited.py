from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from kubo.cli_v3 import main as cli_main
from kubo.live_limited import stage_limited_live_run
from kubo.source_network import SourceNetworkCatalog, SourceNetworkRunValidator, validate_live_probe


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "parser_contract"


def _plan(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": "staged-live-limited-test",
        "product_id": "next_session_rank",
        "scope": "NAMED_SECURITIES",
        "decision_delay_minutes": 1,
        "budget": {
            "max_requests": 2,
            "max_raw_bytes": 1000000,
            "max_wall_seconds": 60,
        },
        "binding": {
            "security_code": "101",
            "ticker": "AAA",
            "isin": "KW0EQ0000101",
            "valid_from": "2020-01-01",
            "valid_to": None,
        },
        "official_capture": {
            "connector": "file",
            "source_id": "boursa_current",
            "source_url": "https://www.boursakuwait.com.kw/en/",
            "roles_observed": ["IDENTITY_REFERENCE"],
            "access_mode": "USER_EXPORT",
            "capture_kind": "USER_EXPORT",
            "resource_path": "boursa_identity.html",
            "timeout_seconds": 5,
            "max_bytes": 500000,
        },
        "secondary_capture": {
            "connector": "file",
            "source_id": "investing_history",
            "source_url": "https://www.investing.com/equities/generated-test-historical-data",
            "roles_observed": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
            "access_mode": "USER_EXPORT",
            "capture_kind": "USER_EXPORT",
            "resource_path": "investing_history.html",
            "timeout_seconds": 5,
            "max_bytes": 500000,
        },
    }
    payload.update(overrides)
    return payload


class LiveLimitedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")

    def test_staged_limited_run_captures_probe_materializes_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            plan_path = workspace / "plan.json"
            plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
            output_root = workspace / "run"
            report = stage_limited_live_run(
                plan_path=plan_path,
                output_root=output_root,
                fixture_root=FIXTURES,
                catalog=self.catalog,
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["capture"]["status"], "COMPLETE")
            self.assertEqual(report["access_probe"]["status"], "PASS")
            self.assertEqual(report["materialized"]["status"], "PASS")
            self.assertFalse(
                report["claim_boundaries"]["staged_run_upgrades_sources_to_live_operational"]
            )
            self.assertTrue((output_root / "access_probe.json").is_file())
            self.assertTrue((output_root / "parser_plan.json").is_file())
            self.assertTrue((output_root / "research_run.json").is_file())
            self.assertEqual(
                validate_live_probe(output_root / "access_probe.json", self.catalog)["status"],
                "PASS",
            )
            validation = SourceNetworkRunValidator(
                output_root,
                self.catalog,
                "next_session_rank",
            ).validate()
            self.assertEqual(validation.status, "PARTIAL")

    def test_cli_stage_live_limited_runs_fixture_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = StringIO()
            with redirect_stdout(output):
                code = cli_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "stage-live-limited",
                        "--plan",
                        str(ROOT / "examples" / "staged_live_limited_plan.json"),
                        "--fixture-root",
                        str(FIXTURES),
                        "--output-root",
                        str(Path(temporary) / "run"),
                    ]
                )
            report = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "PASS")

    def test_official_slot_cannot_be_replaced_by_secondary_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            changed = _plan()
            official = dict(changed["official_capture"])  # type: ignore[arg-type]
            official["source_id"] = "investing_history"
            changed["official_capture"] = official
            path = workspace / "bad.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires boursa_current"):
                stage_limited_live_run(
                    plan_path=path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )

    def test_v1_rejects_full_market_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            path = workspace / "bad.json"
            path.write_text(json.dumps(_plan(scope="FULL_MARKET")), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "NAMED_SECURITIES"):
                stage_limited_live_run(
                    plan_path=path,
                    output_root=workspace / "run",
                    fixture_root=FIXTURES,
                    catalog=self.catalog,
                )


if __name__ == "__main__":
    unittest.main()
