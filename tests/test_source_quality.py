from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

from kubo.source_quality import (
    DIMENSION_IDS,
    SourceQualityError,
    assess_source_quality,
    validate_source_quality_policy,
)


ROOT = Path(__file__).resolve().parents[1]


def _scores(value: float) -> dict[str, float]:
    return {dimension: value for dimension in DIMENSION_IDS}


class SourceQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = ROOT / "config/source_quality_policy.json"
        self.payload = json.loads(self.path.read_text(encoding="utf-8"))

    def _validate_changed(self, payload: object) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return validate_source_quality_policy(path)

    def test_policy_passes(self) -> None:
        report = validate_source_quality_policy(ROOT)
        self.assertEqual(report["status"], "PASS_SOURCE_QUALITY_CONTRACT")
        self.assertAlmostEqual(sum(report["dimension_weights"].values()), 1.0)

    def test_schema_accepts_policy(self) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema unavailable")
        schema = json.loads(
            (ROOT / "schemas/source-quality-policy.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(self.payload)), [])

    def test_admit_is_routing_only(self) -> None:
        report = assess_source_quality(
            ROOT,
            source_id="boursa_current",
            requested_fact_role="OFFICIAL_FACT",
            dimension_scores=_scores(0.95),
        )
        self.assertEqual(report["disposition"], "ADMIT")
        self.assertEqual(report["source_role"], "OFFICIAL_TRUTH")
        self.assertEqual(report["trusted_source_role"], "OFFICIAL_PRIMARY")
        self.assertTrue(report["source_role_resolved_from_registry"])
        self.assertFalse(report["access_authorized"])
        self.assertFalse(report["automatic_promotion_allowed"])
        self.assertFalse(report["quality_score_is_probability"])

    def test_corroboration_band(self) -> None:
        report = assess_source_quality(
            ROOT,
            source_id="mubasher_kuwait",
            source_role="SECONDARY_RESEARCH",
            requested_fact_role="NEWS_CORROBORATION",
            dimension_scores=_scores(0.7),
        )
        self.assertEqual(report["disposition"], "CORROBORATION_ONLY")

    def test_low_quality_is_quarantined(self) -> None:
        report = assess_source_quality(
            ROOT,
            source_id="mubasher_kuwait",
            source_role="SECONDARY_RESEARCH",
            requested_fact_role="RESEARCH_CONTEXT",
            dimension_scores=_scores(0.2),
        )
        self.assertEqual(report["disposition"], "QUARANTINE")

    def test_hard_block_overrides_high_score(self) -> None:
        report = assess_source_quality(
            ROOT,
            source_id="mubasher_kuwait",
            source_role="SECONDARY_RESEARCH",
            requested_fact_role="PRICE_CONTEXT",
            dimension_scores=_scores(1.0),
            failure_codes=["RIGHTS_UNKNOWN_FOR_SYSTEMATIC_REUSE"],
        )
        self.assertEqual(report["disposition"], "BLOCK")

    def test_community_cannot_create_official_fact(self) -> None:
        report = assess_source_quality(
            ROOT,
            source_id="indexsignal_forum",
            source_role="COMMUNITY_ROUTING_ONLY",
            requested_fact_role="OFFICIAL_FACT",
            dimension_scores=_scores(1.0),
        )
        self.assertEqual(report["disposition"], "BLOCK")
        self.assertIn("ROLE_LIMIT_VIOLATION", report["failure_codes"])

    def test_incomplete_dimension_denominator_rejected(self) -> None:
        values = _scores(1.0)
        values.pop("authority")
        with self.assertRaises(SourceQualityError):
            assess_source_quality(
                ROOT,
                source_id="mubasher_kuwait",
                source_role="SECONDARY_RESEARCH",
                requested_fact_role="PRICE_CONTEXT",
                dimension_scores=values,
            )

    def test_boolean_score_rejected(self) -> None:
        values = _scores(1.0)
        values["authority"] = True
        with self.assertRaises(SourceQualityError):
            assess_source_quality(
                ROOT,
                source_id="mubasher_kuwait",
                source_role="SECONDARY_RESEARCH",
                requested_fact_role="PRICE_CONTEXT",
                dimension_scores=values,
            )

    def test_duplicate_failure_code_rejected(self) -> None:
        with self.assertRaises(SourceQualityError):
            assess_source_quality(
                ROOT,
                source_id="mubasher_kuwait",
                source_role="SECONDARY_RESEARCH",
                requested_fact_role="PRICE_CONTEXT",
                dimension_scores=_scores(1.0),
                failure_codes=["PARSER_DRIFT", "PARSER_DRIFT"],
            )

    def test_weakened_claim_boundary_rejected(self) -> None:
        payload = deepcopy(self.payload)
        payload["claim_boundaries"]["quality_score_is_probability"] = True
        with self.assertRaises(SourceQualityError):
            self._validate_changed(payload)

    def test_removed_hard_block_rejected(self) -> None:
        payload = deepcopy(self.payload)
        payload["hard_blocks"].pop()
        with self.assertRaises(SourceQualityError):
            self._validate_changed(payload)

    def test_weight_sum_rejected(self) -> None:
        payload = deepcopy(self.payload)
        payload["dimensions"][0]["weight"] = 0.5
        with self.assertRaises(SourceQualityError):
            self._validate_changed(payload)

    def test_v1_weights_thresholds_and_actions_are_immutable(self) -> None:
        payload = deepcopy(self.payload)
        payload["dimensions"][0]["weight"] = 0.23
        payload["dimensions"][-1]["weight"] = 0.07
        with self.assertRaises(SourceQualityError):
            self._validate_changed(payload)

        payload = deepcopy(self.payload)
        payload["thresholds"] = {
            "admit": 0.7,
            "corroboration_only": 0.5,
            "quarantine_below": 0.5,
        }
        with self.assertRaises(SourceQualityError):
            self._validate_changed(payload)

        payload = deepcopy(self.payload)
        payload["adaptive_actions"]["ADMIT"] = "AUTO_PROMOTE"
        with self.assertRaises(SourceQualityError):
            self._validate_changed(payload)

    def test_malformed_role_and_failure_arrays_fail_cleanly(self) -> None:
        payload = deepcopy(self.payload)
        payload["role_limits"]["OFFICIAL_TRUTH"] = [{}]
        with self.assertRaises(SourceQualityError):
            self._validate_changed(payload)

        with self.assertRaises(SourceQualityError):
            assess_source_quality(
                ROOT,
                source_id="boursa_current",
                source_role="OFFICIAL_TRUTH",
                requested_fact_role="OFFICIAL_FACT",
                dimension_scores=_scores(1.0),
                failure_codes=({},),
            )

    def test_duplicate_json_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
            with self.assertRaises(SourceQualityError):
                validate_source_quality_policy(path)


if __name__ == "__main__":
    unittest.main()
