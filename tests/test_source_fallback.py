from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from kubo.source_fallback import (
    SourceFallbackError,
    plan_source_fallback,
    validate_source_fallback_policy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _request() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": "fallback-001",
        "capability_id": "official_disclosures",
        "decision_at": "2026-08-25T09:30:00+03:00",
        "observations": [],
    }


def _observation(
    source_id: str,
    *,
    transport: str,
    semantic: str,
    rows: int = 0,
    verified_zero: bool = False,
    urls: list[str] | None = None,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "attempted_at": "2026-08-25T09:00:00+03:00",
        "transport_status": transport,
        "semantic_status": semantic,
        "qualified_row_count": rows,
        "zero_result_verified": verified_zero,
        "cited_original_urls": urls or [],
    }


class SourceFallbackTests(unittest.TestCase):
    def test_repository_policy_is_bound_to_catalog_and_market(self) -> None:
        report = validate_source_fallback_policy(PROJECT_ROOT)

        self.assertEqual(report["status"], "PASS_CONTRACT_ONLY_NO_NETWORK")
        self.assertEqual(report["capability_count"], 9)
        self.assertFalse(report["claim_boundaries"]["network_access_performed"])

        schema = json.loads(
            (PROJECT_ROOT / "schemas" / "source-fallback-policy.schema.json").read_text()
        )
        payload = json.loads(
            (PROJECT_ROOT / "config" / "source_fallback_policy.json").read_text()
        )
        Draft202012Validator(schema).validate(payload)

    def test_transport_success_with_unverified_zero_falls_back(self) -> None:
        request = _request()
        request["observations"] = [
            _observation(
                "boursa_disclosure_archive",
                transport="SUCCESS",
                semantic="ZERO_ROWS",
            )
        ]

        report = plan_source_fallback(PROJECT_ROOT, request)

        self.assertEqual(report["status"], "CAPABILITY_FALLBACK_REQUIRED")
        self.assertEqual(report["next_source"]["source_id"], "cma_ifsah")
        self.assertEqual(report["attempts"][0]["disposition"], "UNVERIFIED_ZERO_RESULT")

    def test_verified_zero_can_satisfy_only_an_admitted_capability(self) -> None:
        request = _request()
        request["observations"] = [
            _observation(
                "boursa_disclosure_archive",
                transport="SUCCESS",
                semantic="VERIFIED_ZERO_RESULT",
                verified_zero=True,
            )
        ]

        report = plan_source_fallback(PROJECT_ROOT, request)

        self.assertEqual(report["status"], "CAPABILITY_VERIFIED_ZERO_RESULT")
        self.assertEqual(report["source_certainty_state"], "VERIFIED_ZERO_RECEIPT")
        self.assertFalse(report["claim_boundaries"]["probability_computed"])

    def test_blocked_source_does_not_bypass_access_or_end_capability(self) -> None:
        request = _request()
        request["observations"] = [
            _observation(
                "boursa_disclosure_archive",
                transport="ACCESS_BLOCKED",
                semantic="ACCESS_BLOCKED",
            )
        ]

        report = plan_source_fallback(PROJECT_ROOT, request)

        self.assertEqual(report["status"], "CAPABILITY_FALLBACK_REQUIRED")
        self.assertEqual(report["next_source"]["source_id"], "cma_ifsah")
        self.assertFalse(report["claim_boundaries"]["access_control_bypassed"])

    def test_secondary_lead_is_queued_for_original_verification(self) -> None:
        request = _request()
        request["capability_id"] = "news_context"
        request["observations"] = [
            _observation(
                "issuer_ir_verified",
                transport="ENTITLEMENT_REQUIRED",
                semantic="ACCESS_BLOCKED",
            ),
            _observation(
                "kuna",
                transport="TIMEOUT",
                semantic="NOT_EVALUATED",
            ),
            _observation(
                "reuters_middle_east",
                transport="SUCCESS",
                semantic="ROWS_PRESENT",
                rows=2,
                urls=["https://www.boursakuwait.com.kw/news/example"],
            )
        ]

        report = plan_source_fallback(PROJECT_ROOT, request)

        self.assertEqual(report["status"], "CAPABILITY_EVIDENCE_AVAILABLE")
        self.assertEqual(
            report["source_certainty_state"],
            "NON_PRIMARY_RECEIPT_PENDING_CONFIRMATION",
        )
        queue = report["original_source_verification_queue"]
        self.assertIn("boursa_current", queue[0]["matched_registered_source_ids"])
        request_schema = json.loads(
            (PROJECT_ROOT / "schemas" / "source-fallback-request.schema.json").read_text()
        )
        report_schema = json.loads(
            (PROJECT_ROOT / "schemas" / "source-fallback-report.schema.json").read_text()
        )
        Draft202012Validator(request_schema).validate(request)
        Draft202012Validator(report_schema).validate(report)

    def test_inconsistent_semantics_are_rejected(self) -> None:
        request = _request()
        request["observations"] = [
            _observation(
                "boursa_disclosure_archive",
                transport="SUCCESS",
                semantic="ROWS_PRESENT",
                rows=0,
            )
        ]

        with self.assertRaisesRegex(SourceFallbackError, "positive qualified rows"):
            plan_source_fallback(PROJECT_ROOT, request)

    def test_policy_rejects_storage_as_a_fact_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            for name in (
                "source_network.json",
                "source_capabilities.json",
                "research_policies.json",
                "market_scope.json",
                "products.json",
            ):
                (root / "config" / name).write_bytes((PROJECT_ROOT / "config" / name).read_bytes())
            policy = json.loads((PROJECT_ROOT / "config" / "source_fallback_policy.json").read_text())
            policy["capabilities"][0]["source_chain"][0] = "artifact_storage"
            (root / "config" / "source_fallback_policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )

            with self.assertRaisesRegex(SourceFallbackError, "factual fallback"):
                validate_source_fallback_policy(root)

    def test_policy_rejects_source_without_capability_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            for name in (
                "source_network.json",
                "source_capabilities.json",
                "research_policies.json",
                "market_scope.json",
                "products.json",
            ):
                (root / "config" / name).write_bytes((PROJECT_ROOT / "config" / name).read_bytes())
            policy = json.loads((PROJECT_ROOT / "config" / "source_fallback_policy.json").read_text())
            policy["capabilities"][0]["source_chain"][0] = "kuna"
            (root / "config" / "source_fallback_policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )

            with self.assertRaisesRegex(SourceFallbackError, "lacks a role"):
                validate_source_fallback_policy(root)

    def test_observation_after_decision_time_is_rejected(self) -> None:
        request = copy.deepcopy(_request())
        row = _observation(
            "boursa_disclosure_archive",
            transport="SUCCESS",
            semantic="ZERO_ROWS",
        )
        row["attempted_at"] = "2026-08-25T10:00:00+03:00"
        request["observations"] = [row]

        with self.assertRaisesRegex(SourceFallbackError, "after decision_at"):
            plan_source_fallback(PROJECT_ROOT, request)

    def test_observations_cannot_skip_or_reorder_the_fallback_chain(self) -> None:
        request = _request()
        request["observations"] = [
            _observation(
                "cma_ifsah",
                transport="SUCCESS",
                semantic="ROWS_PRESENT",
                rows=1,
            )
        ]

        with self.assertRaisesRegex(SourceFallbackError, "ordered prefix"):
            plan_source_fallback(PROJECT_ROOT, request)


if __name__ == "__main__":
    unittest.main()
