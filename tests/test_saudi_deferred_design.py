from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


class SaudiDeferredDesignTests(unittest.TestCase):
    def test_design_contract_is_schema_valid_and_runtime_is_closed(self) -> None:
        contract = json.loads(
            (ROOT / "config" / "saudi-deferred-design-gates.json").read_text(
                encoding="utf-8"
            )
        )
        schema = json.loads(
            (ROOT / "schemas" / "saudi-deferred-design-gates.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(contract)
        self.assertFalse(contract["implementation_started"])
        self.assertTrue(all(value is False for value in contract["claim_boundaries"].values()))

    def test_all_five_review_invariants_are_frozen(self) -> None:
        contract = json.loads(
            (ROOT / "config" / "saudi-deferred-design-gates.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [row["gate_id"] for row in contract["invariants"]],
            [
                "SAUDI_TRUSTED_SOURCE_REGISTRY",
                "SAUDI_SUSPENDED_DENOMINATOR",
                "SAUDI_GLOBAL_TEMPORAL_CUTOFF",
                "SAUDI_OFFICIAL_HOLIDAY_CALENDAR",
                "SAUDI_OBSERVATION_KNOWN_AT",
            ],
        )
        requirements = " ".join(row["requirement"] for row in contract["invariants"])
        for marker in (
            "source_role",
            "rights_status",
            "tradable=false",
            "global known_at",
            "official holiday calendar",
            "observed_at",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, requirements)


if __name__ == "__main__":
    unittest.main()
