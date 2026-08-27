from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None

from kubo.cli_v3 import main as cli_main
from kubo.hashing import canonical_json_bytes, sha256_bytes
from kubo.source_access_recipes import (
    SourceAccessRecipeCatalog,
    compile_source_probe_plan,
    validate_access_probe_against_plan,
    validate_source_probe_plan,
)
from kubo.source_network import SourceNetworkCatalog


ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class SourceAccessRecipeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = SourceNetworkCatalog(ROOT / "config")
        self.recipes = SourceAccessRecipeCatalog(
            ROOT / "config" / "source_access_recipes.json",
            self.network,
        )
        self.planned_at = datetime.fromisoformat("2026-08-24T09:00:00+03:00")

    def _write_single_source_plan(self, directory: Path) -> tuple[Path, dict[str, object]]:
        plan = compile_source_probe_plan(
            self.recipes,
            self.network,
            planned_at=self.planned_at,
            source_ids=["boursa_current"],
        )
        path = directory / "probe_plan.json"
        path.write_bytes(canonical_json_bytes(plan))
        return path, plan

    def _write_probe(
        self,
        directory: Path,
        plan: dict[str, object],
        *,
        state: str = "AVAILABLE",
        flags: list[str] | None = None,
        tested_url: str | None = None,
    ) -> Path:
        raw = directory / "raw" / "boursa.html"
        raw.parent.mkdir(parents=True, exist_ok=True)
        content = b"<html><body>generated source access receipt</body></html>"
        raw.write_bytes(content)
        task = plan["tasks"][0]
        readable = state in {"AVAILABLE", "PARTIAL"}
        payload = {
            "schema_version": "3.1-access-probe",
            "probe_id": "probe-source-access-recipes-001",
            "probe_version": "source-access-recipes-v1",
            "observed_at": "2026-08-24T09:06:00+03:00",
            "expires_at": "2026-08-25T09:00:00+03:00",
            "purpose": "Capability access receipt only; not market evidence.",
            "sources": [
                {
                    "source_id": "boursa_current",
                    "state": state,
                    "tested_url": tested_url or task["tested_url"],
                    "final_url": task["tested_url"],
                    "attempted_at": "2026-08-24T09:05:00+03:00",
                    "http_status": 200 if readable else 403,
                    "observation": "Generated contract-only access observation.",
                    "data_quality_flags": flags or [],
                    "artifact": (
                        {
                            "path": "raw/boursa.html",
                            "sha256": sha256_bytes(content),
                            "size_bytes": len(content),
                            "content_type": "text/html",
                            "capture_kind": "RAW_PAGE",
                        }
                        if readable
                        else None
                    ),
                }
            ],
        }
        path = directory / "access_probe.json"
        _write_json(path, payload)
        return path

    def test_registry_is_defined_only_and_covers_priority_sources(self) -> None:
        report = self.recipes.report(self.network)
        self.assertEqual(report["status"], "PASS_CONTRACT")
        self.assertEqual(report["readiness_status"], "DEFINED_ONLY")
        self.assertEqual(report["recipe_count"], 15)
        self.assertEqual(report["covered_source_count"], 31)
        self.assertEqual(report["catalog_source_count"], 69)
        for source_id in (
            "boursa_current",
            "boursa_reports_archive",
            "boursa_disclosure_archive",
            "kcc_maqasa_official",
            "investing_history",
            "tradingview_screeners",
            "mubasher_kuwait",
            "argaam_kuwait",
            "reuters_middle_east",
            "indexsignal_forum",
            "telegram_kuwaitstockex",
        ):
            self.assertIn(source_id, self.recipes.recipe_by_source)
        self.assertNotIn("authorized_broker_feed", self.recipes.recipe_by_source)
        self.assertTrue(all(value is False for value in report["claim_boundaries"].values()))

    def test_manual_importer_is_capped_at_price_import_ready_only(self) -> None:
        importer = self.recipes.manual_importers[0]
        self.assertEqual(importer.importer_id, "INVESTING_USER_PRICE_EXPORT_V1")
        self.assertEqual(importer.promotion_ceiling, "PRICE_IMPORT_READY_ONLY")
        self.assertEqual(
            importer.cli_command,
            "kubo-data-foundation import-user-price-exports",
        )
        self.assertTrue(all(value is False for value in importer.claim_boundaries.values()))

    def test_systematic_public_access_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recipes.json"
            payload = _read_json(ROOT / "config" / "source_access_recipes.json")
            payload["recipes"][0]["collection_frequency"] = "SYSTEMATIC"
            _write_json(path, payload)
            with self.assertRaisesRegex(ValueError, "systematic public access"):
                SourceAccessRecipeCatalog(path, self.network)

    def test_duplicate_source_assignment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recipes.json"
            payload = _read_json(ROOT / "config" / "source_access_recipes.json")
            payload["recipes"][1]["source_ids"].append("boursa_current")
            _write_json(path, payload)
            with self.assertRaisesRegex(ValueError, "duplicate_recipe_sources"):
                SourceAccessRecipeCatalog(path, self.network)

    def test_unregistered_access_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recipes.json"
            payload = _read_json(ROOT / "config" / "source_access_recipes.json")
            payload["recipes"][0]["route_kind"] = "LICENSED_OR_BROKER_EXPORT"
            payload["recipes"][0]["access_mode"] = "LICENSED_VENDOR"
            payload["recipes"][0]["capture_method"] = "LICENSED_EXPORT"
            payload["recipes"][0]["rights_status"] = "LICENSED"
            _write_json(path, payload)
            with self.assertRaisesRegex(ValueError, "not registered"):
                SourceAccessRecipeCatalog(path, self.network)

    def test_public_access_cannot_claim_authorized_rights(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recipes.json"
            payload = _read_json(ROOT / "config" / "source_access_recipes.json")
            payload["recipes"][0]["rights_status"] = "AUTHORIZED"
            _write_json(path, payload)
            with self.assertRaisesRegex(ValueError, "access_mode/rights_status"):
                SourceAccessRecipeCatalog(path, self.network)

    def test_route_must_match_access_and_capture_method(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recipes.json"
            payload = _read_json(ROOT / "config" / "source_access_recipes.json")
            payload["recipes"][0]["route_kind"] = "AUTHORIZED_USER_EXPORT"
            _write_json(path, payload)
            with self.assertRaisesRegex(ValueError, "route/access/capture"):
                SourceAccessRecipeCatalog(path, self.network)

    def test_probe_plan_is_deterministic_hash_bound_and_metadata_only(self) -> None:
        source_ids = ["investing_history", "boursa_current"]
        first = compile_source_probe_plan(
            self.recipes,
            self.network,
            planned_at=self.planned_at,
            source_ids=source_ids,
        )
        second = compile_source_probe_plan(
            self.recipes,
            self.network,
            planned_at=self.planned_at,
            source_ids=reversed(source_ids),
        )
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PLANNED_NOT_EXECUTED")
        self.assertEqual(first["purpose"], "CAPABILITY_PROBE_ONLY")
        self.assertEqual(first["recipe_set_sha256"], self.recipes.registry_sha256)
        self.assertEqual(
            [task["source_id"] for task in first["tasks"]],
            ["boursa_current", "investing_history"],
        )
        self.assertTrue(all(value is False for value in first["claim_boundaries"].values()))
        serialized = json.dumps(first["tasks"], sort_keys=True).lower()
        for forbidden in ("price_fils", "probability", "recommendation", "entry_price"):
            self.assertNotIn(forbidden, serialized)

    def test_full_plan_stays_within_repository_aggregate_budgets(self) -> None:
        plan = compile_source_probe_plan(
            self.recipes,
            self.network,
            planned_at=self.planned_at,
        )
        self.assertEqual(len(plan["tasks"]), 31)
        self.assertLessEqual(
            sum(task["budget"]["max_bytes"] for task in plan["tasks"]),
            128 * 1024 * 1024,
        )
        self.assertLessEqual(
            sum(task["budget"]["timeout_seconds"] for task in plan["tasks"]),
            300,
        )

    def test_plan_rejects_an_aggregate_timeout_over_300_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recipes.json"
            payload = _read_json(ROOT / "config" / "source_access_recipes.json")
            payload["defaults"]["timeout_seconds"] = 11
            _write_json(path, payload)
            recipes = SourceAccessRecipeCatalog(path, self.network)
            with self.assertRaisesRegex(ValueError, "300-second"):
                compile_source_probe_plan(
                    recipes,
                    self.network,
                    planned_at=self.planned_at,
                )

    def test_plan_and_recipe_json_schemas_accept_generated_artifacts(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        recipe_schema = _read_json(ROOT / "schemas" / "source-access-recipes.schema.json")
        plan_schema = _read_json(ROOT / "schemas" / "source-access-probe-plan.schema.json")
        Draft202012Validator(recipe_schema).validate(
            _read_json(ROOT / "config" / "source_access_recipes.json")
        )
        Draft202012Validator(plan_schema).validate(
            compile_source_probe_plan(
                self.recipes,
                self.network,
                planned_at=self.planned_at,
            )
        )

    def test_forged_plan_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, plan = self._write_single_source_plan(directory)
            forged = deepcopy(plan)
            forged["tasks"][0]["rights_status"] = "LICENSED"
            path.write_bytes(canonical_json_bytes(forged))
            report = validate_source_probe_plan(path, self.recipes, self.network)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("does not reproduce", report["errors"][0])

    def test_available_probe_passes_as_access_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            plan_path, plan = self._write_single_source_plan(directory)
            probe_path = self._write_probe(directory, plan)
            report = validate_access_probe_against_plan(
                probe_path=probe_path,
                plan_path=plan_path,
                recipes=self.recipes,
                source_catalog=self.network,
                now=datetime.fromisoformat("2026-08-24T09:10:00+03:00"),
            )
        self.assertEqual(report["status"], "PASS_ACCESS_ONLY")
        self.assertTrue(report["claim_boundaries"]["plan_bound_access_only"])
        self.assertFalse(report["claim_boundaries"]["access_probe_is_market_evidence"])
        self.assertFalse(report["claim_boundaries"]["access_probe_is_live_operational"])

    def test_blocked_probe_requires_a_controlled_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            plan_path, plan = self._write_single_source_plan(directory)
            probe_path = self._write_probe(directory, plan, state="BLOCKED")
            report = validate_access_probe_against_plan(
                probe_path=probe_path,
                plan_path=plan_path,
                recipes=self.recipes,
                source_catalog=self.network,
                now=datetime.fromisoformat("2026-08-24T09:10:00+03:00"),
            )
            self.assertEqual(report["status"], "BLOCKED")
            self.assertIn("PROBE_TERMINAL_STATE_REQUIRES_REASON", report["errors"][0])
            probe_path = self._write_probe(
                directory,
                plan,
                state="BLOCKED",
                flags=["HTTP_BLOCKED"],
            )
            report = validate_access_probe_against_plan(
                probe_path=probe_path,
                plan_path=plan_path,
                recipes=self.recipes,
                source_catalog=self.network,
                now=datetime.fromisoformat("2026-08-24T09:10:00+03:00"),
            )
        self.assertEqual(report["status"], "PASS_ACCESS_ONLY")
        self.assertEqual(report["sources"][0]["state"], "BLOCKED")

    def test_probe_url_must_match_the_planned_catalog_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            plan_path, plan = self._write_single_source_plan(directory)
            probe_path = self._write_probe(
                directory,
                plan,
                tested_url="https://www.boursakuwait.com.kw/en/disclaimer/",
            )
            report = validate_access_probe_against_plan(
                probe_path=probe_path,
                plan_path=plan_path,
                recipes=self.recipes,
                source_catalog=self.network,
                now=datetime.fromisoformat("2026-08-24T09:10:00+03:00"),
            )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("PROBE_TESTED_URL_MISMATCH", report["errors"][0])

    def test_probe_expiry_cannot_exceed_the_plan_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            plan_path, plan = self._write_single_source_plan(directory)
            probe_path = self._write_probe(directory, plan)
            payload = _read_json(probe_path)
            payload["expires_at"] = "2026-08-25T09:01:00+03:00"
            _write_json(probe_path, payload)
            report = validate_access_probe_against_plan(
                probe_path=probe_path,
                plan_path=plan_path,
                recipes=self.recipes,
                source_catalog=self.network,
                now=datetime.fromisoformat("2026-08-24T09:10:00+03:00"),
            )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("PROBE_EXPIRY_EXCEEDS_PLAN_WINDOW", report["errors"])

    def test_probe_with_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            plan_path, plan = self._write_single_source_plan(directory)
            probe_path = self._write_probe(directory, plan)
            serialized = probe_path.read_text(encoding="utf-8")
            probe_path.write_text(
                serialized.replace(
                    "{\n",
                    '{\n  "probe_id": "duplicate-probe-id",\n',
                    1,
                ),
                encoding="utf-8",
            )
            report = validate_access_probe_against_plan(
                probe_path=probe_path,
                plan_path=plan_path,
                recipes=self.recipes,
                source_catalog=self.network,
                now=datetime.fromisoformat("2026-08-24T09:10:00+03:00"),
            )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("duplicate JSON key", report["errors"][0])

    def test_cli_writes_a_no_overwrite_probe_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan.json"
            argv = [
                "--project-root",
                str(ROOT),
                "plan-source-access-probe",
                "--planned-at",
                "2026-08-24T09:00:00+03:00",
                "--source",
                "boursa_current",
                "--output",
                str(output),
            ]
            with redirect_stdout(StringIO()):
                self.assertEqual(cli_main(argv), 0)
            self.assertTrue(output.is_file())
            with self.assertRaises(FileExistsError):
                with redirect_stdout(StringIO()):
                    cli_main(argv)


if __name__ == "__main__":
    unittest.main()
