from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from kubo.hashing import canonical_json_bytes, sha256_bytes
from kubo.cli_v3 import main as cli_main
from kubo.parser_materialization import materialize_parser_run
from kubo.pipeline import ResearchPipeline
from kubo.source_network import SourceNetworkCatalog
from kubo.source_parsers import (
    ParserDriftError,
    investing_price_finding,
    parse_boursa_identity_html,
    parse_investing_history_html,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "parser_contract"


class SourceParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SourceNetworkCatalog(ROOT / "config")

    def test_source_specific_parsers_accept_generated_contract_layouts(self) -> None:
        identities = parse_boursa_identity_html(
            (FIXTURES / "boursa_identity.html").read_bytes()
        )
        instrument = parse_investing_history_html(
            (FIXTURES / "investing_history.html").read_bytes()
        )
        self.assertEqual(identities[0].security_code, "101")
        self.assertEqual(identities[0].isin, instrument.isin)
        self.assertEqual(instrument.ticker, "AAA")
        self.assertEqual(len(instrument.rows), 2)

    def test_parser_drift_is_fail_closed(self) -> None:
        content = (FIXTURES / "investing_history.html").read_text(encoding="utf-8")
        changed = content.replace("<th>Change %</th>", "<th>Unrecognized metric</th>")
        with self.assertRaisesRegex(ParserDriftError, "REQUIRED_TABLE_HEADERS_NOT_FOUND"):
            parse_investing_history_html(changed.encode("utf-8"))

    def test_price_change_reconciliation_rejects_bad_provider_row(self) -> None:
        content = (FIXTURES / "investing_history.html").read_text(encoding="utf-8")
        changed = content.replace("+1.00%", "+9.00%")
        with self.assertRaisesRegex(ParserDriftError, "CHANGE_PERCENT_RECONCILIATION_FAILED"):
            parse_investing_history_html(changed.encode("utf-8"))

    def test_daily_price_finding_freshness_uses_session_date_not_capture_date(self) -> None:
        instrument = parse_investing_history_html(
            (FIXTURES / "investing_history.html").read_bytes()
        )
        historical = replace(
            instrument,
            rows=tuple(
                replace(
                    row,
                    session_date=f"2020-01-{2 - index:02d}",
                )
                for index, row in enumerate(instrument.rows)
            ),
        )
        captured_at = datetime.fromisoformat("2026-08-07T00:50:00+03:00")
        finding = investing_price_finding(
            historical,
            security_code="101",
            source_url="https://www.investing.com/equities/generated-test-historical-data",
            raw_sha256="a" * 64,
            observed_at=captured_at,
            capture_mode="USER_EXPORT",
        )
        self.assertEqual(finding["published_at"], "2020-01-02T00:00:00+03:00")
        self.assertEqual(finding["available_at"], captured_at.isoformat())

    def _capture_and_plan(self, directory: Path) -> tuple[Path, Path, dict[str, object]]:
        run_root = directory / "capture"
        raw_root = run_root / "raw"
        raw_root.mkdir(parents=True)
        official = (FIXTURES / "boursa_identity.html").read_bytes()
        secondary = (FIXTURES / "investing_history.html").read_bytes()
        official_path = raw_root / "boursa.html"
        secondary_path = raw_root / "investing.html"
        official_path.write_bytes(official)
        secondary_path.write_bytes(secondary)
        official_hash = sha256_bytes(official)
        secondary_hash = sha256_bytes(secondary)
        observed = "2026-08-07T00:50:00+03:00"
        manifest = {
            "schema_version": "3.0",
            "artifacts": [
                {
                    "path": "raw/boursa.html",
                    "sha256": official_hash,
                    "size_bytes": len(official),
                    "source_id": "boursa_current",
                    "source_url": "https://reports.boursakuwait.com.kw/en/shortsell",
                    "observed_at": observed,
                    "capture_kind": "USER_EXPORT",
                },
                {
                    "path": "raw/investing.html",
                    "sha256": secondary_hash,
                    "size_bytes": len(secondary),
                    "source_id": "investing_history",
                    "source_url": "https://www.investing.com/equities/generated-test-historical-data",
                    "observed_at": observed,
                    "capture_kind": "USER_EXPORT",
                },
            ],
        }
        observations = {
            "schema_version": "3.0",
            "sources": [
                {
                    "source_id": "boursa_current",
                    "state": "AVAILABLE",
                    "access_mode": "USER_EXPORT",
                    "attempted_at": observed,
                    "query_status": "DATA_QUALITY_REJECTED",
                    "roles_observed": ["IDENTITY_REFERENCE"],
                    "qualified_items": 0,
                    "zero_result": False,
                    "raw_sha256s": [official_hash],
                    "data_quality_flags": ["RAW_CAPTURE_PENDING_PARSER_VALIDATION"],
                    "limitations": ["GENERATED_CONTRACT_FIXTURE"],
                    "entitlement_id": "",
                },
                {
                    "source_id": "investing_history",
                    "state": "AVAILABLE",
                    "access_mode": "USER_EXPORT",
                    "attempted_at": observed,
                    "query_status": "DATA_QUALITY_REJECTED",
                    "roles_observed": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
                    "qualified_items": 0,
                    "zero_result": False,
                    "raw_sha256s": [secondary_hash],
                    "data_quality_flags": ["RAW_CAPTURE_PENDING_PARSER_VALIDATION"],
                    "limitations": ["GENERATED_CONTRACT_FIXTURE"],
                    "entitlement_id": "",
                },
            ],
        }
        (run_root / "manifest.json").write_bytes(canonical_json_bytes(manifest))
        (run_root / "source_observations.json").write_bytes(canonical_json_bytes(observations))
        plan = {
            "schema_version": "1.0",
            "run_id": "parser-e2e-contract-run",
            "product_id": "next_session_rank",
            "decision_at": "2026-08-07T01:00:00+03:00",
            "scope": "NAMED_SECURITIES",
            "budget": {
                "max_requests": 10,
                "max_raw_bytes": 1000000,
                "max_wall_seconds": 60,
            },
            "usage_wall_seconds": 1,
            "bindings": [
                {
                    "security_code": "101",
                    "ticker": "AAA",
                    "isin": "KW0EQ0000101",
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                    "official_artifact_sha256": official_hash,
                    "secondary_artifact_sha256": secondary_hash,
                }
            ],
            "parser_tasks": [
                {
                    "parser_id": "boursa_identity_html_v1",
                    "artifact_sha256": official_hash,
                },
                {
                    "parser_id": "investing_history_html_v1",
                    "artifact_sha256": secondary_hash,
                },
            ],
        }
        plan_path = directory / "parser-plan.json"
        plan_path.write_bytes(canonical_json_bytes(plan))
        return run_root, plan_path, plan

    def test_two_source_bytes_materialize_to_validated_partial_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root, plan_path, _ = self._capture_and_plan(Path(temporary))
            report = materialize_parser_run(
                capture_root=run_root,
                parser_plan_path=plan_path,
                catalog=self.catalog,
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["finding_count"], 1)
            self.assertEqual(report["network_validation"]["status"], "PARTIAL")
            finding = json.loads((run_root / "findings.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(finding["source_id"], "investing_history")
            self.assertEqual(finding["signal_kind"], "PRICE_ACTIVITY")
            plan_report = ResearchPipeline(ROOT).plan(
                "next_session_rank", network_run_root=run_root
            )
            self.assertEqual(plan_report["status"], "RESEARCH_PARTIAL")
            self.assertEqual(plan_report["ranked_candidates"], [])
            self.assertFalse(
                plan_report["claim_boundaries"]["probability_allowed"]
            )
            self.assertFalse(
                plan_report["claim_boundaries"]["recommendation_allowed"]
            )

    def test_identity_mismatch_rolls_back_materialized_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root, plan_path, plan = self._capture_and_plan(Path(temporary))
            changed = deepcopy(plan)
            changed["bindings"][0]["isin"] = "KW0EQ0000999"
            plan_path.write_bytes(canonical_json_bytes(changed))
            original_observations = (run_root / "source_observations.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "official security-code/ISIN"):
                materialize_parser_run(
                    capture_root=run_root,
                    parser_plan_path=plan_path,
                    catalog=self.catalog,
                )
            self.assertFalse((run_root / "research_run.json").exists())
            self.assertFalse((run_root / "universe.json").exists())
            self.assertFalse((run_root / "findings.jsonl").exists())
            self.assertEqual(
                (run_root / "source_observations.json").read_bytes(),
                original_observations,
            )

    def test_materialize_parser_cli_runs_the_contract_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root, plan_path, _ = self._capture_and_plan(Path(temporary))
            output = StringIO()
            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "materialize-parser-run",
                        "--capture-root",
                        str(run_root),
                        "--parser-plan",
                        str(plan_path),
                    ]
                )
            report = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["network_validation"]["status"], "PARTIAL")

    def test_parser_plan_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root, plan_path, plan = self._capture_and_plan(Path(temporary))
            changed = deepcopy(plan)
            changed["caller_claim"] = "trust me"
            plan_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown/missing fields"):
                materialize_parser_run(
                    capture_root=run_root,
                    parser_plan_path=plan_path,
                    catalog=self.catalog,
                )

    def test_parser_budget_is_enforced_before_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root, plan_path, plan = self._capture_and_plan(Path(temporary))
            changed = deepcopy(plan)
            changed["budget"]["max_raw_bytes"] = 1
            plan_path.write_bytes(canonical_json_bytes(changed))
            with self.assertRaisesRegex(ValueError, "raw-byte budget"):
                materialize_parser_run(
                    capture_root=run_root,
                    parser_plan_path=plan_path,
                    catalog=self.catalog,
                )
            self.assertFalse((run_root / "research_run.json").exists())

    def test_capability_matrix_does_not_overstate_live_operation(self) -> None:
        report = self.catalog.report()
        self.assertEqual(
            report["parser_sources"], ["boursa_current", "investing_history"]
        )
        self.assertEqual(report["live_operational_sources"], [])
        self.assertFalse(report["claim_boundaries"]["contract_fixture_is_live_acceptance"])
        self.assertFalse(
            report["claim_boundaries"]["parser_implemented_is_live_operational"]
        )


if __name__ == "__main__":
    unittest.main()
