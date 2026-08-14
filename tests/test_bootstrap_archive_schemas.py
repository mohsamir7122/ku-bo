from __future__ import annotations

import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - CI installs the declared test extra
    Draft202012Validator = None  # type: ignore[assignment,misc]

from kubo.bootstrap_archive.workspace import (
    build_bootstrap_archive_plan,
    prepare_bootstrap_archive,
)


ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 8, 14)
PREPARED_AT = datetime(2026, 8, 14, 18, 30, tzinfo=timezone.utc)
EXTERNAL_TEMP_ROOT = (
    Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
)

SCHEMA_NAMES = (
    "bootstrap-archive-descriptor.schema.json",
    "bootstrap-archive-manifest.schema.json",
    "bootstrap-archive-plan.schema.json",
    "bootstrap-archive-workspace-report.schema.json",
    "historical-source-network-crosswalk.schema.json",
)


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"fixture is not an object: {path}")
    return value


class BootstrapArchiveSchemaTests(unittest.TestCase):
    @staticmethod
    def _validator(name: str) -> Draft202012Validator:
        if Draft202012Validator is None:
            raise unittest.SkipTest("jsonschema optional dependency unavailable")
        schema = _load_json(ROOT / "schemas" / name)
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(
            schema,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )

    def _instances(self, parent: Path) -> dict[str, dict[str, object]]:
        archive = parent / "archive"
        prepare_bootstrap_archive(
            project_root=ROOT,
            output_root=archive,
            as_of=AS_OF,
            prepared_at=PREPARED_AT,
        )
        return {
            "bootstrap-archive-descriptor.schema.json": _load_json(
                archive / "bootstrap_archive.json"
            ),
            "bootstrap-archive-manifest.schema.json": _load_json(
                archive / "manifests" / "bootstrap_archive_manifest.json"
            ),
            "bootstrap-archive-plan.schema.json": build_bootstrap_archive_plan(
                config_root=ROOT / "config",
                as_of=AS_OF,
            ),
            "bootstrap-archive-workspace-report.schema.json": _load_json(
                archive / "reports" / "bootstrap_archive_workspace_report.json"
            ),
            "historical-source-network-crosswalk.schema.json": _load_json(
                ROOT / "config" / "historical_source_network_crosswalk.json"
            ),
        }

    def test_all_bootstrap_schemas_are_valid_draft_2020_12(self) -> None:
        for name in SCHEMA_NAMES:
            with self.subTest(schema=name):
                self._validator(name)

    def test_generated_contracts_validate_with_format_checking_enabled(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            instances = self._instances(Path(directory))
        for name, instance in instances.items():
            with self.subTest(schema=name):
                self.assertEqual(
                    list(self._validator(name).iter_errors(instance)),
                    [],
                )

    def test_descriptor_rejects_malformed_dates_and_ready_stage_forgery(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            descriptor = self._instances(Path(directory))[
                "bootstrap-archive-descriptor.schema.json"
            ]
        validator = self._validator("bootstrap-archive-descriptor.schema.json")

        malformed_date = copy.deepcopy(descriptor)
        malformed_date["as_of"] = "2026-13-99"
        self.assertTrue(list(validator.iter_errors(malformed_date)))

        malformed_timestamp = copy.deepcopy(descriptor)
        malformed_timestamp["prepared_at"] = 123
        self.assertTrue(list(validator.iter_errors(malformed_timestamp)))
        self.assertIsNotNone(validator.format_checker)

        ready_stage = copy.deepcopy(descriptor)
        ready_stage["stages"][1]["status"] = "READY"
        ready_stage["counts"]["company_count"] = 1
        ready_stage["claim_boundaries"]["company_intelligence_ready"] = True
        self.assertTrue(
            list(validator.iter_errors(ready_stage)),
            "descriptor Schema must reject downstream-readiness forgery",
        )

    def test_plan_manifest_report_and_crosswalk_reject_evidence_or_readiness_forgery(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional dependency unavailable")
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            instances = self._instances(Path(directory))

        plan = copy.deepcopy(instances["bootstrap-archive-plan.schema.json"])
        plan["claim_boundaries"]["forecast_allowed"] = True
        self.assertTrue(
            list(self._validator("bootstrap-archive-plan.schema.json").iter_errors(plan))
        )

        manifest = copy.deepcopy(instances["bootstrap-archive-manifest.schema.json"])
        manifest["evidence_artifacts"] = [
            {"path": "raw/forged.bin", "sha256": "a" * 64, "size_bytes": 1}
        ]
        manifest["counts"]["evidence_artifact_count"] = 1
        manifest["claim_boundaries"]["archive_collection_allowed"] = True
        self.assertTrue(
            list(
                self._validator("bootstrap-archive-manifest.schema.json").iter_errors(
                    manifest
                )
            )
        )

        report = copy.deepcopy(
            instances["bootstrap-archive-workspace-report.schema.json"]
        )
        report["company_count"] = 1
        report["claim_boundaries"]["recommendation_allowed"] = True
        self.assertTrue(
            list(
                self._validator(
                    "bootstrap-archive-workspace-report.schema.json"
                ).iter_errors(report)
            ),
            "workspace-report Schema must reject readiness and recommendation forgery",
        )

        crosswalk = copy.deepcopy(
            instances["historical-source-network-crosswalk.schema.json"]
        )
        crosswalk["bindings"][0]["collection_allowed"] = True
        crosswalk["claim_boundaries"]["collection_allowed"] = True
        self.assertTrue(
            list(
                self._validator(
                    "historical-source-network-crosswalk.schema.json"
                ).iter_errors(crosswalk)
            )
        )


if __name__ == "__main__":
    unittest.main()
