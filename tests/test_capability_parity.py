from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from kubo.capability_parity import (
    CapabilityParityError,
    validate_predecessor_capability_parity,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _temporary_project(directory: str, payload: dict[str, object]) -> Path:
    root = Path(directory)
    (root / "config").mkdir()
    for name in ("market_scope.json", "products.json"):
        (root / "config" / name).write_bytes((PROJECT_ROOT / "config" / name).read_bytes())
    (root / "config" / "predecessor_capability_parity.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return root


class CapabilityParityTests(unittest.TestCase):
    def test_repository_manifest_resolves_all_fifteen_jobs(self) -> None:
        report = validate_predecessor_capability_parity(PROJECT_ROOT)

        self.assertEqual(report["status"], "PASS_SOFTWARE_PARITY_NON_OPERATIONAL")
        self.assertEqual(report["capability_count"], 15)
        self.assertEqual(report["resolved_callable_count"], 15)
        self.assertFalse(report["private_source_details_present"])
        self.assertFalse(report["claim_boundaries"]["training_authorized"])
        schema = json.loads(
            (PROJECT_ROOT / "schemas" / "predecessor-capability-parity.schema.json").read_text()
        )
        payload = json.loads(
            (PROJECT_ROOT / "config" / "predecessor_capability_parity.json").read_text()
        )
        Draft202012Validator(schema).validate(payload)

    def test_private_repository_locator_is_rejected(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "config" / "predecessor_capability_parity.json").read_text()
        )
        payload["capabilities"][0]["user_job"] = "Read source from github.com/example/private repository."
        with tempfile.TemporaryDirectory() as directory:
            root = _temporary_project(directory, payload)

            with self.assertRaisesRegex(CapabilityParityError, "private source detail"):
                validate_predecessor_capability_parity(root)

    def test_second_engine_migration_is_rejected(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "config" / "predecessor_capability_parity.json").read_text()
        )
        payload["migration_rules"]["second_engine_allowed"] = True
        with tempfile.TemporaryDirectory() as directory:
            root = _temporary_project(directory, payload)

            with self.assertRaisesRegex(CapabilityParityError, "migration rules"):
                validate_predecessor_capability_parity(root)

    def test_binding_outside_canonical_core_is_rejected(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "config" / "predecessor_capability_parity.json").read_text()
        )
        payload["capabilities"][0]["target_module"] = "legacy.engine"
        with tempfile.TemporaryDirectory() as directory:
            root = _temporary_project(directory, payload)

            with self.assertRaisesRegex(CapabilityParityError, "canonical binding drift"):
                validate_predecessor_capability_parity(root)

    def test_operational_ceiling_drift_is_rejected(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "config" / "predecessor_capability_parity.json").read_text()
        )
        payload["capabilities"][8]["operational_ceiling"] = "RESEARCH_ONLY"
        with tempfile.TemporaryDirectory() as directory:
            root = _temporary_project(directory, payload)

            with self.assertRaisesRegex(CapabilityParityError, "metadata drift"):
                validate_predecessor_capability_parity(root)

    def test_missing_capability_is_rejected(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "config" / "predecessor_capability_parity.json").read_text()
        )
        payload["capabilities"].pop()
        with tempfile.TemporaryDirectory() as directory:
            root = _temporary_project(directory, payload)

            with self.assertRaisesRegex(CapabilityParityError, "all admitted user jobs"):
                validate_predecessor_capability_parity(root)


if __name__ == "__main__":
    unittest.main()
