from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from kubo.source_fallback import (
    SourceFallbackError,
    plan_source_fallback,
    validate_source_fallback_policy,
    zero_result_receipt_digest,
)
from kubo.hashing import canonical_json_bytes


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
    zero_receipt: object = None,
    urls: list[str] | None = None,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "attempted_at": "2026-08-25T09:00:00+03:00",
        "transport_status": transport,
        "semantic_status": semantic,
        "qualified_row_count": rows,
        "zero_result_receipt": zero_receipt,
        "cited_original_urls": urls or [],
    }


def _write_zero_receipt(
    root: Path,
    *,
    source_id: str = "boursa_disclosure_archive",
    capability_id: str = "official_disclosures",
) -> tuple[dict[str, str], dict[str, object], Path, Path]:
    raw_path = root / "raw" / "zero-page.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_content = b'{"items":[],"next_page":null}\n'
    raw_path.write_bytes(raw_content)
    receipt = {
        "schema_version": "1.0",
        "receipt_id": "zero-receipt-001",
        "canonical_query": (
            f"capability={capability_id};source={source_id};strategy=PAGED_WINDOW_QUERY_ROUTE;"
            "from=2026-08-01;to=2026-08-25"
        ),
        "query_time": "2026-08-25T08:59:00+03:00",
        "pagination_coverage": {
            "requested_pages": 1,
            "received_pages": 1,
            "first_page": 1,
            "last_page": 1,
            "terminal_page_reached": True,
            "next_page_token_present": False,
        },
        "source_id": source_id,
        "strategy_id": "PAGED_WINDOW_QUERY_ROUTE",
        "raw_artifact": {
            "logical_path": "raw/zero-page.json",
            "sha256": hashlib.sha256(raw_content).hexdigest(),
            "size_bytes": len(raw_content),
        },
        "qualified_row_count": 0,
        "receipt_digest": "",
    }
    receipt["receipt_digest"] = zero_result_receipt_digest(receipt)
    receipt_path = root / "receipts" / "zero-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_content = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_content)
    reference = {
        "logical_path": "receipts/zero-receipt.json",
        "sha256": hashlib.sha256(receipt_content).hexdigest(),
    }
    return reference, receipt, raw_path, receipt_path


def _verified_request(reference: object) -> dict[str, object]:
    request = _request()
    request["observations"] = [
        _observation(
            "boursa_disclosure_archive",
            transport="SUCCESS",
            semantic="VERIFIED_ZERO_RESULT",
            zero_receipt=reference,
        )
    ]
    return request


def _rewrite_receipt(
    receipt_path: Path,
    receipt: dict[str, object],
    reference: dict[str, str],
    *,
    recompute_digest: bool = True,
) -> None:
    if recompute_digest:
        receipt["receipt_digest"] = zero_result_receipt_digest(receipt)
    content = canonical_json_bytes(receipt)
    receipt_path.write_bytes(content)
    reference["sha256"] = hashlib.sha256(content).hexdigest()


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
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            reference, receipt, _, _ = _write_zero_receipt(artifact_root)
            request = _request()
            request["observations"] = [
                _observation(
                    "boursa_disclosure_archive",
                    transport="SUCCESS",
                    semantic="VERIFIED_ZERO_RESULT",
                    zero_receipt=reference,
                )
            ]

            report = plan_source_fallback(
                PROJECT_ROOT, request, artifact_root=artifact_root
            )

        self.assertEqual(report["status"], "CAPABILITY_VERIFIED_ZERO_RESULT")
        self.assertEqual(report["source_certainty_state"], "VERIFIED_ZERO_RECEIPT")
        self.assertFalse(report["claim_boundaries"]["probability_computed"])
        self.assertEqual(
            report["attempts"][0]["zero_result_receipt"]["validation_status"],
            "PASS_REOPENED_AND_HASHED",
        )
        receipt_schema = json.loads(
            (PROJECT_ROOT / "schemas" / "verified-zero-result-receipt.schema.json").read_text()
        )
        Draft202012Validator(receipt_schema).validate(receipt)
        report_schema = json.loads(
            (PROJECT_ROOT / "schemas" / "source-fallback-report.schema.json").read_text()
        )
        Draft202012Validator(report_schema).validate(report)

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

    def test_caller_boolean_cannot_create_verified_zero_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            request = _verified_request(True)
            with self.assertRaisesRegex(SourceFallbackError, "unknown or missing"):
                plan_source_fallback(
                    PROJECT_ROOT, request, artifact_root=artifact_root
                )

            request = _verified_request(None)
            request["observations"][0]["zero_result_verified"] = True
            with self.assertRaisesRegex(SourceFallbackError, "unknown or missing"):
                plan_source_fallback(
                    PROJECT_ROOT, request, artifact_root=artifact_root
                )

    def test_verified_zero_requires_trusted_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reference, _, _, _ = _write_zero_receipt(Path(directory))
            with self.assertRaisesRegex(SourceFallbackError, "trusted artifact_root"):
                plan_source_fallback(PROJECT_ROOT, _verified_request(reference))

    def test_zero_receipt_path_traversal_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            reference, _, _, receipt_path = _write_zero_receipt(artifact_root)
            escaped = dict(reference)
            escaped["logical_path"] = "../zero-receipt.json"
            with self.assertRaisesRegex(SourceFallbackError, "trusted artifact root"):
                plan_source_fallback(
                    PROJECT_ROOT,
                    _verified_request(escaped),
                    artifact_root=artifact_root,
                )

            target = artifact_root / "receipt-target.json"
            target.write_bytes(receipt_path.read_bytes())
            receipt_path.unlink()
            try:
                receipt_path.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(SourceFallbackError, "trusted artifact root"):
                plan_source_fallback(
                    PROJECT_ROOT,
                    _verified_request(reference),
                    artifact_root=artifact_root,
                )

    def test_receipt_and_raw_artifact_hash_mismatch_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            reference, _, raw_path, receipt_path = _write_zero_receipt(artifact_root)
            receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
            with self.assertRaisesRegex(SourceFallbackError, "receipt file hash mismatch"):
                plan_source_fallback(
                    PROJECT_ROOT,
                    _verified_request(reference),
                    artifact_root=artifact_root,
                )

            reference, _, raw_path, _ = _write_zero_receipt(artifact_root)
            raw_path.write_bytes(b"changed")
            with self.assertRaisesRegex(SourceFallbackError, "raw artifact hash mismatch"):
                plan_source_fallback(
                    PROJECT_ROOT,
                    _verified_request(reference),
                    artifact_root=artifact_root,
                )

    def test_receipt_digest_and_pagination_must_be_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            reference, receipt, _, receipt_path = _write_zero_receipt(artifact_root)
            receipt["receipt_digest"] = "f" * 64
            _rewrite_receipt(
                receipt_path, receipt, reference, recompute_digest=False
            )
            with self.assertRaisesRegex(SourceFallbackError, "receipt digest mismatch"):
                plan_source_fallback(
                    PROJECT_ROOT,
                    _verified_request(reference),
                    artifact_root=artifact_root,
                )

            reference, receipt, _, receipt_path = _write_zero_receipt(artifact_root)
            receipt["pagination_coverage"]["terminal_page_reached"] = False
            _rewrite_receipt(receipt_path, receipt, reference)
            with self.assertRaisesRegex(SourceFallbackError, "coverage is incomplete"):
                plan_source_fallback(
                    PROJECT_ROOT,
                    _verified_request(reference),
                    artifact_root=artifact_root,
                )

    def test_receipt_source_and_strategy_are_bound_to_trusted_registries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            reference, receipt, _, receipt_path = _write_zero_receipt(artifact_root)
            receipt["strategy_id"] = "CALLER_CHOSEN_STRATEGY"
            _rewrite_receipt(receipt_path, receipt, reference)
            with self.assertRaisesRegex(SourceFallbackError, "strategy_id is not trusted"):
                plan_source_fallback(
                    PROJECT_ROOT,
                    _verified_request(reference),
                    artifact_root=artifact_root,
                )


if __name__ == "__main__":
    unittest.main()
