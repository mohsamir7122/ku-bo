from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from kubo.hashing import canonical_json_bytes, sha256_bytes
from kubo.ingestion import CaptureResult
from kubo.source_access_executor import execute_public_source_probe
from kubo.source_access_recipes import SourceAccessRecipeCatalog, compile_source_probe_plan
from kubo.source_network import SourceNetworkCatalog


ROOT = Path(__file__).resolve().parents[1]
PLANNED_AT = datetime.fromisoformat("2026-08-27T06:00:00+03:00")
RUN_AT = datetime.fromisoformat("2026-08-27T06:05:00+03:00")


class FakeConnector:
    def __init__(self, *, readable: bool = True):
        self.readable = readable
        self.calls = []

    def capture(self, request):
        self.calls.append(request)
        if self.readable:
            content = b"<html><body>public capability fixture</body></html>"
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
                content=content,
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


class ExplodingConnector:
    def __init__(self):
        self.calls = 0

    def capture(self, _request):
        self.calls += 1
        raise RuntimeError("connector implementation failure")


class MixedConnector:
    def __init__(self):
        self.calls = []
        self.readable = FakeConnector()

    def capture(self, request):
        self.calls.append(request.source_id)
        if request.source_id == "kcc_maqasa_official":
            raise RuntimeError("one source failed")
        return self.readable.capture(request)


class SourceAccessExecutorTests(unittest.TestCase):
    def setUp(self):
        self.network = SourceNetworkCatalog(ROOT / "config")
        self.recipes = SourceAccessRecipeCatalog(
            ROOT / "config" / "source_access_recipes.json", self.network
        )

    def _plan(self, directory: Path, source_id: str = "kcc_maqasa_official") -> Path:
        plan = compile_source_probe_plan(
            self.recipes,
            self.network,
            planned_at=PLANNED_AT,
            source_ids=[source_id],
        )
        path = directory / "plan.json"
        path.write_bytes(canonical_json_bytes(plan))
        return path

    def test_readable_public_probe_is_hash_bound_and_access_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._plan(root)
            connector = FakeConnector()
            output = root / "probe"
            report = execute_public_source_probe(
                plan_path=plan,
                output_root=output,
                recipes=self.recipes,
                source_catalog=self.network,
                connector=connector,
                clock=lambda: RUN_AT,
            )
            probe = json.loads((output / "access-probe.json").read_text(encoding="utf-8"))
            artifact = probe["sources"][0]["artifact"]
            raw = output / artifact["path"]
            self.assertEqual(raw.read_bytes(), b"<html><body>public capability fixture</body></html>")
            self.assertEqual(artifact["sha256"], sha256_bytes(raw.read_bytes()))
        self.assertEqual(report["status"], "PASS_ACCESS_ONLY")
        self.assertTrue(report["network_access_attempted"])
        self.assertTrue(report["network_access_executed"])
        self.assertFalse(report["market_data_collected"])
        self.assertFalse(report["market_evidence_created"])
        self.assertFalse(report["parser_executed"])
        self.assertFalse(report["forecast_or_recommendation_created"])
        self.assertEqual(len(connector.calls), 1)

    def test_terminal_failure_is_preserved_without_fabricated_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._plan(root)
            output = root / "probe"
            report = execute_public_source_probe(
                plan_path=plan,
                output_root=output,
                recipes=self.recipes,
                source_catalog=self.network,
                connector=FakeConnector(readable=False),
                clock=lambda: RUN_AT,
            )
            probe = json.loads((output / "access-probe.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS_ACCESS_ONLY")
        self.assertEqual(probe["sources"][0]["state"], "BLOCKED")
        self.assertIsNone(probe["sources"][0]["artifact"])
        self.assertIn("HTTP_BLOCKED", probe["sources"][0]["data_quality_flags"])

    def test_connector_exception_becomes_auditable_error_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._plan(root)
            output = root / "probe"
            connector = ExplodingConnector()
            report = execute_public_source_probe(
                plan_path=plan,
                output_root=output,
                recipes=self.recipes,
                source_catalog=self.network,
                connector=connector,
                clock=lambda: RUN_AT,
            )
            probe = json.loads((output / "access-probe.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS_ACCESS_ONLY")
        self.assertTrue(report["network_access_attempted"])
        self.assertFalse(report["network_access_executed"])
        self.assertEqual(connector.calls, 1)
        self.assertEqual(probe["sources"][0]["state"], "ERROR")
        self.assertIsNone(probe["sources"][0]["artifact"])
        self.assertIn("NETWORK_ERROR", probe["sources"][0]["data_quality_flags"])
        self.assertIn("CONNECTOR_INTERNAL_ERROR", probe["sources"][0]["observation"])

    def test_one_source_exception_does_not_stop_a_readable_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_payload = compile_source_probe_plan(
                self.recipes,
                self.network,
                planned_at=PLANNED_AT,
                source_ids=["kcc_maqasa_official", "boursa_reports_archive"],
            )
            plan = root / "plan.json"
            plan.write_bytes(canonical_json_bytes(plan_payload))
            connector = MixedConnector()
            output = root / "probe"
            report = execute_public_source_probe(
                plan_path=plan,
                output_root=output,
                recipes=self.recipes,
                source_catalog=self.network,
                connector=connector,
                clock=lambda: RUN_AT,
            )
            probe = json.loads((output / "access-probe.json").read_text(encoding="utf-8"))
        rows = {row["source_id"]: row for row in probe["sources"]}
        self.assertEqual(report["status"], "PASS_ACCESS_ONLY")
        self.assertEqual(report["source_count"], 2)
        self.assertEqual(rows["kcc_maqasa_official"]["state"], "ERROR")
        self.assertEqual(rows["boursa_reports_archive"]["state"], "AVAILABLE")
        self.assertIsNotNone(rows["boursa_reports_archive"]["artifact"])
        self.assertEqual(
            connector.calls,
            ["boursa_reports_archive", "kcc_maqasa_official"],
        )

    def test_browser_recipe_is_rejected_before_connector_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._plan(root, "boursa_current")
            connector = FakeConnector()
            with self.assertRaisesRegex(ValueError, "only one-off"):
                execute_public_source_probe(
                    plan_path=plan,
                    output_root=root / "probe",
                    recipes=self.recipes,
                    source_catalog=self.network,
                    connector=connector,
                    clock=lambda: RUN_AT,
                )
        self.assertEqual(connector.calls, [])

    def test_nonempty_output_is_rejected_before_connector_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._plan(root)
            output = root / "probe"
            output.mkdir()
            (output / "existing.txt").write_text("preserve", encoding="utf-8")
            connector = FakeConnector()
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                execute_public_source_probe(
                    plan_path=plan,
                    output_root=output,
                    recipes=self.recipes,
                    source_catalog=self.network,
                    connector=connector,
                    clock=lambda: RUN_AT,
                )
            self.assertEqual((output / "existing.txt").read_text(encoding="utf-8"), "preserve")
        self.assertEqual(connector.calls, [])

    def test_expired_plan_is_rejected_before_output_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._plan(root)
            connector = FakeConnector()
            with self.assertRaisesRegex(ValueError, "outside the validated plan window"):
                execute_public_source_probe(
                    plan_path=plan,
                    output_root=root / "probe",
                    recipes=self.recipes,
                    source_catalog=self.network,
                    connector=connector,
                    clock=lambda: datetime.fromisoformat("2026-08-28T06:00:01+03:00"),
                )
            self.assertFalse((root / "probe").exists())
        self.assertEqual(connector.calls, [])


if __name__ == "__main__":
    unittest.main()
