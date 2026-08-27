from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kubo.cli_v3 import main
from kubo.ingestion import CaptureResult
from kubo.source_orchestrator import SourceSearchOrchestrator as RealSourceSearchOrchestrator


ROOT = Path(__file__).resolve().parents[1]


class KuwaitWorkflowCliTests(unittest.TestCase):
    def test_source_search_cli_materializes_run_ledger_and_raw_bytes(self) -> None:
        fixed = datetime.fromisoformat("2026-08-13T10:00:00+03:00")

        class QualifiedConnector:
            def capture(self, request):
                return CaptureResult(
                    source_id=request.source_id,
                    source_url=request.source_url,
                    final_url=request.source_url,
                    access_mode=request.access_mode,
                    capture_kind=request.capture_kind,
                    roles_observed=request.roles_observed,
                    attempted_at=fixed,
                    observed_at=fixed,
                    state="AVAILABLE",
                    query_status="QUALIFIED",
                    qualified_items=1,
                    zero_result=False,
                    content=b'{"fixture":"contract-only"}',
                    content_type="application/json",
                    http_status=200,
                    error_code="",
                    data_quality_flags=(),
                    limitations=("TEST_CONNECTOR_NOT_LIVE",),
                )

        def orchestrator_factory(**kwargs):
            return RealSourceSearchOrchestrator(
                **kwargs,
                clock=lambda: fixed,
                sleeper=lambda _seconds: None,
            )

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "search-run"
            output = io.StringIO()
            with (
                patch("kubo.cli_v3.PublicHttpConnector", return_value=QualifiedConnector()),
                patch("kubo.cli_v3.SourceSearchOrchestrator", side_effect=orchestrator_factory),
                redirect_stdout(output),
            ):
                code = main(
                    [
                        "--project-root",
                        str(ROOT),
                        "run-source-search",
                        "--run-id",
                        "cli-integration",
                        "--decision-at",
                        "2026-08-13T08:00:00+00:00",
                        "--output-root",
                        str(output_root),
                        "--source",
                        "boursa_current",
                    ]
                )
            report = json.loads(output.getvalue())
            saved = json.loads(
                (output_root / "source_search_run.json").read_text(encoding="utf-8")
            )
            ledger_rows = (output_root / "source_attempts.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            raw_files = list((output_root / "raw" / "boursa_current").iterdir())
        self.assertEqual(code, 0)
        self.assertEqual(report, saved)
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(report["timezone"], "Asia/Kuwait")
        self.assertEqual(report["decision_at"], "2026-08-13T11:00:00+03:00")
        self.assertEqual(len(ledger_rows), 1)
        self.assertEqual(len(raw_files), 1)

    def test_degraded_source_search_is_persisted_but_exits_nonzero(self) -> None:
        fixed = datetime.fromisoformat("2026-08-13T10:00:00+03:00")

        class BlockedConnector:
            def capture(self, request):
                return CaptureResult(
                    source_id=request.source_id,
                    source_url=request.source_url,
                    final_url=request.source_url,
                    access_mode=request.access_mode,
                    capture_kind=request.capture_kind,
                    roles_observed=request.roles_observed,
                    attempted_at=fixed,
                    observed_at=None,
                    state="BLOCKED",
                    query_status="BLOCKED",
                    qualified_items=0,
                    zero_result=False,
                    content=None,
                    content_type="",
                    http_status=403,
                    error_code="HTTP_FORBIDDEN",
                    data_quality_flags=(),
                    limitations=("TEST_CONNECTOR_NOT_LIVE",),
                )

        def orchestrator_factory(**kwargs):
            return RealSourceSearchOrchestrator(
                **kwargs,
                clock=lambda: fixed,
                sleeper=lambda _seconds: None,
            )

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "degraded-search"
            output = io.StringIO()
            with (
                patch("kubo.cli_v3.PublicHttpConnector", return_value=BlockedConnector()),
                patch("kubo.cli_v3.SourceSearchOrchestrator", side_effect=orchestrator_factory),
                redirect_stdout(output),
            ):
                code = main(
                    [
                        "--project-root",
                        str(ROOT),
                        "run-source-search",
                        "--run-id",
                        "cli-degraded",
                        "--decision-at",
                        "2026-08-13T11:00:00+03:00",
                        "--output-root",
                        str(output_root),
                        "--source",
                        "boursa_current",
                    ]
                )
            report = json.loads(output.getvalue())
            saved = json.loads(
                (output_root / "source_search_run.json").read_text(encoding="utf-8")
            )
        self.assertEqual(code, 1)
        self.assertEqual(report, saved)
        self.assertEqual(report["status"], "DEGRADED")

    def test_workflow_contract_is_available_from_cli(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "validate-research-workflow",
                ]
            )
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS_CONTRACT")
        self.assertEqual(report["readiness_status"], "LIVE_DEPENDENT")
        self.assertEqual(
            report["workflow"]["workflow_id"],
            "KUWAIT_120D_NEXT_SESSION_RESEARCH",
        )
        self.assertEqual(report["workflow"]["context_calendar_days"], 120)
        self.assertEqual(report["workflow"]["decision_sessions"], 40)
        self.assertEqual(report["source_capabilities"]["DEFINED_ONLY"], 69)
        self.assertEqual(report["live_operational_sources"], [])
        self.assertFalse(report["claim_boundaries"]["operational_ready"])
        self.assertFalse(report["claim_boundaries"]["backtest_ready"])

    def test_missing_real_packet_stops_without_accuracy_metric(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(
                    [
                        "--project-root",
                        str(ROOT),
                        "evaluate-forty-session-replay",
                        "--packet",
                        str(runtime_root / "missing-real-packet.json"),
                        "--runtime-root",
                        str(runtime_root),
                    ]
                )
        report = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "STOP_BACKTEST")
        self.assertIsNone(report["metrics"])
        self.assertIsNone(report["agreement_rate"])
        self.assertEqual(report["agreement_rate_status"], "NOT_APPLICABLE")
        self.assertEqual(report["diagnostics"]["process_valid_scoreable_sessions"], 0)
        self.assertTrue(report["claim_boundaries"]["metrics_withheld_on_stop"])


if __name__ == "__main__":
    unittest.main()
