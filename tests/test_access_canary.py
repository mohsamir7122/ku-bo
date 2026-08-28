from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from kubo.access_canary import (
    ALLOWED_SOURCE_IDS,
    CANARY_CLAIM_BOUNDARIES,
    run_access_canary_audit,
)
from kubo.atomic_output import AtomicOutputError
from kubo.hashing import canonical_json_bytes
from kubo.ingestion import CaptureResult
from kubo.source_access_executor import execute_public_source_probe
from kubo.source_access_recipes import (
    SourceAccessRecipeCatalog,
    compile_source_probe_plan,
)
from kubo.source_network import SourceNetworkCatalog


ROOT = Path(__file__).resolve().parents[1]
PLANNED_AT = datetime.fromisoformat("2026-08-27T06:00:00+03:00")
RUN_AT = datetime.fromisoformat("2026-08-27T06:05:00+03:00")
FIXTURE_BYTES = b"<html><body>access canary fixture; not market evidence</body></html>"


class CanaryConnector:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls = 0

    def capture(self, request):
        self.calls += 1
        if self.available:
            return CaptureResult(
                source_id=request.source_id,
                source_url=request.source_url,
                final_url=request.source_url,
                access_mode=request.access_mode,
                capture_kind=request.capture_kind,
                roles_observed=request.roles_observed,
                attempted_at=RUN_AT,
                observed_at=RUN_AT,
                state="AVAILABLE",
                query_status="DATA_QUALITY_REJECTED",
                qualified_items=0,
                zero_result=False,
                content=FIXTURE_BYTES,
                content_type="text/html",
                http_status=200,
                error_code="",
                data_quality_flags=("RAW_CAPTURE_PENDING_PARSER_VALIDATION",),
                limitations=("CAPTURE_ONLY_REQUIRES_PARSER_VALIDATION",),
            )
        return CaptureResult(
            source_id=request.source_id,
            source_url=request.source_url,
            final_url=request.source_url,
            access_mode=request.access_mode,
            capture_kind=request.capture_kind,
            roles_observed=request.roles_observed,
            attempted_at=RUN_AT,
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
            limitations=(),
        )


class AccessCanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = SourceNetworkCatalog(ROOT / "config")
        self.recipes = SourceAccessRecipeCatalog(
            ROOT / "config" / "source_access_recipes.json", self.network
        )

    def _inputs(
        self,
        root: Path,
        *,
        source_id: str = "kcc_maqasa_official",
        available: bool = True,
    ) -> tuple[Path, Path, Path, CanaryConnector]:
        plan = compile_source_probe_plan(
            self.recipes,
            self.network,
            planned_at=PLANNED_AT,
            source_ids=[source_id],
        )
        plan_path = root / "source-probe-plan.json"
        plan_path.write_bytes(canonical_json_bytes(plan))
        connector = CanaryConnector(available=available)
        probe_root = root / "private-probe"
        report = execute_public_source_probe(
            plan_path=plan_path,
            output_root=probe_root,
            recipes=self.recipes,
            source_catalog=self.network,
            connector=connector,
            clock=lambda: RUN_AT,
        )
        execution_path = root / "probe-execution-report.json"
        execution_path.write_bytes(canonical_json_bytes(report))
        return plan_path, probe_root / "access-probe.json", execution_path, connector

    def _audit(
        self,
        root: Path,
        *,
        source_id: str = "kcc_maqasa_official",
        available: bool = True,
        confirm_no_trade: bool = True,
    ) -> tuple[dict[str, object], Path, Path, Path, CanaryConnector]:
        plan, probe, execution, connector = self._inputs(
            root, source_id=source_id, available=available
        )
        output = root / "public"
        report = run_access_canary_audit(
            project_root=ROOT,
            source_id=source_id,
            confirm_no_trade=confirm_no_trade,
            plan_path=plan,
            probe_path=probe,
            execution_report_path=execution,
            output_root=output,
            now=RUN_AT,
        )
        return report, output, probe, execution, connector

    def test_each_allowlisted_available_source_passes_access_only(self):
        for source_id in ALLOWED_SOURCE_IDS:
            with self.subTest(source_id=source_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report, output, _probe, _execution, connector = self._audit(
                    root, source_id=source_id
                )
                self.assertEqual(report["status"], "PASS_ACCESS_ONLY_CANARY")
                self.assertEqual(report["source_state"], "AVAILABLE")
                self.assertEqual(report["candidate_count"], 0)
                self.assertTrue(report["no_trade"])
                self.assertEqual(report["failure_codes"], [])
                self.assertEqual(report["claim_boundaries"], CANARY_CLAIM_BOUNDARIES)
                self.assertTrue(report["artifact"]["reopened"])
                self.assertGreater(report["artifact"]["size_bytes"], 0)
                self.assertEqual(connector.calls, 1)

                self.assertEqual(
                    sorted(path.name for path in output.iterdir()),
                    [
                        "access-probe-receipt.sanitized.json",
                        "canary-audit.json",
                        "source-probe-plan.sanitized.json",
                    ],
                )
                receipt = json.loads(
                    (output / "access-probe-receipt.sanitized.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertNotIn("path", receipt["source"]["artifact"])
                public_bytes = b"".join(path.read_bytes() for path in output.iterdir())
                self.assertNotIn(FIXTURE_BYTES, public_bytes)
                self.assertNotIn(str(root).encode("utf-8"), public_bytes)
                self.assertNotIn(b"private-probe", public_bytes)

    def test_blocked_access_creates_truthful_sanitized_blocked_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report, output, _probe, _execution, connector = self._audit(
                root, available=False
            )
            self.assertEqual(report["status"], "BLOCKED_ACCESS_ONLY_CANARY")
            self.assertEqual(report["source_state"], "BLOCKED")
            self.assertIn("SOURCE_STATE_BLOCKED", report["failure_codes"])
            self.assertIsNone(report["artifact"])
            self.assertEqual(report["candidate_count"], 0)
            self.assertTrue(report["no_trade"])
            self.assertEqual(connector.calls, 1)
            self.assertTrue((output / "canary-audit.json").is_file())
            self.assertTrue((output / "source-probe-plan.sanitized.json").is_file())
            self.assertTrue(
                (output / "access-probe-receipt.sanitized.json").is_file()
            )

    def test_explicit_no_trade_confirmation_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _output, _probe, _execution, _connector = self._audit(
                Path(directory), confirm_no_trade=False
            )
        self.assertEqual(report["status"], "BLOCKED_ACCESS_ONLY_CANARY")
        self.assertIn(
            "EXPLICIT_NO_TRADE_CONFIRMATION_REQUIRED", report["failure_codes"]
        )
        self.assertEqual(report["candidate_count"], 0)
        self.assertTrue(report["no_trade"])

    def test_executor_market_evidence_claim_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, probe, execution, _connector = self._inputs(root)
            payload = json.loads(execution.read_text(encoding="utf-8"))
            payload["market_evidence_created"] = True
            execution.write_bytes(canonical_json_bytes(payload))
            report = run_access_canary_audit(
                project_root=ROOT,
                source_id="kcc_maqasa_official",
                confirm_no_trade=True,
                plan_path=plan,
                probe_path=probe,
                execution_report_path=execution,
                output_root=root / "public",
                now=RUN_AT,
            )
        self.assertEqual(report["status"], "BLOCKED_ACCESS_ONLY_CANARY")
        self.assertIn(
            "EXECUTOR_REPORT_CLAIM_BOUNDARY_REJECTED", report["failure_codes"]
        )
        self.assertEqual(report["candidate_count"], 0)
        self.assertFalse(report["claim_boundaries"]["market_evidence_created"])
        self.assertFalse(
            report["claim_boundaries"]["candidate_generation_invoked"]
        )

    def test_executor_candidate_claim_is_rejected_even_if_added(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, probe, execution, _connector = self._inputs(root)
            payload = json.loads(execution.read_text(encoding="utf-8"))
            payload["candidate_generation_invoked"] = True
            execution.write_bytes(canonical_json_bytes(payload))
            report = run_access_canary_audit(
                project_root=ROOT,
                source_id="kcc_maqasa_official",
                confirm_no_trade=True,
                plan_path=plan,
                probe_path=probe,
                execution_report_path=execution,
                output_root=root / "public",
                now=RUN_AT,
            )
        self.assertEqual(report["status"], "BLOCKED_ACCESS_ONLY_CANARY")
        self.assertIn(
            "EXECUTOR_REPORT_CLAIM_BOUNDARY_REJECTED", report["failure_codes"]
        )
        self.assertEqual(report["candidate_count"], 0)
        self.assertTrue(report["no_trade"])

    def test_changed_raw_bytes_cannot_produce_a_false_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, probe, execution, _connector = self._inputs(root)
            payload = json.loads(probe.read_text(encoding="utf-8"))
            raw_path = probe.parent / payload["sources"][0]["artifact"]["path"]
            raw_path.write_bytes(b"tampered")
            report = run_access_canary_audit(
                project_root=ROOT,
                source_id="kcc_maqasa_official",
                confirm_no_trade=True,
                plan_path=plan,
                probe_path=probe,
                execution_report_path=execution,
                output_root=root / "public",
                now=RUN_AT,
            )
        self.assertEqual(report["status"], "BLOCKED_ACCESS_ONLY_CANARY")
        self.assertIn("CANARY_INPUT_VALIDATION_FAILED", report["failure_codes"])
        self.assertIsNone(report["artifact"])
        self.assertEqual(report["candidate_count"], 0)

    def test_existing_public_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, probe, execution, _connector = self._inputs(root)
            output = root / "public"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaises(AtomicOutputError):
                run_access_canary_audit(
                    project_root=ROOT,
                    source_id="kcc_maqasa_official",
                    confirm_no_trade=True,
                    plan_path=plan,
                    probe_path=probe,
                    execution_report_path=execution,
                    output_root=output,
                    now=RUN_AT,
                )
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
