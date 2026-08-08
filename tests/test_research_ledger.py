from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from kubo.reporting import build_report
from kubo.request_contracts import AnalysisRequest
from kubo.research_ledger import ResearchDecisionLedger, validate_research_report


POLICY_HASH = "a" * 64
CODE_HASH = "b" * 64
CONFIGURATION_HASH = "d" * 64
EVIDENCE_HASH = "c" * 64
DECISION_AT = "2026-08-07T01:00:00+03:00"
ISSUED_AT = "2026-08-07T02:00:00+03:00"
RECORDED_AT = "2026-08-07T02:01:00+03:00"
OUTCOME_OBSERVED_AT = "2026-08-08T13:00:00+03:00"
OUTCOME_RECORDED_AT = "2026-08-08T13:01:00+03:00"


def built_report(request_id: str = "request-1") -> dict:
    request = AnalysisRequest.from_dict(
        {
            "request_id": request_id,
            "product_id": "next_session_rank",
            "mode": "research_network",
        }
    )
    plan = {
        "status": "RESEARCH_READY",
        "mode": "research_network",
        "evidence_packet_hash": EVIDENCE_HASH,
        "product": {"product_id": "next_session_rank"},
        "network_run": {
            "status": "PASS",
            "evidence_packet_hash": EVIDENCE_HASH,
            "contract": {"scope": "CANDIDATE_SET", "decision_at": DECISION_AT},
            "independent_sources": 5,
            "role_coverage": {"NEWS_ARCHIVE": 2, "PRICE_HISTORY": 1},
            "official_confirmation_available": False,
            "coverage_gaps": [],
            "warnings": [],
        },
        "ranked_candidates": [
            {
                "security_code": "101",
                "ticker": "AAA",
                "rank": 1,
                "decision_status": "WATCH",
                "research_score": 54.0,
                "score_kind": "SOURCE_MOSAIC_EVIDENCE_SCORE_NOT_PROBABILITY",
                "probability": None,
                "recommendation": None,
                "reason_codes": ["OFFICIAL_CONFIRMATION_UNAVAILABLE"],
            }
        ],
        "reasons": ["OFFICIAL_CONFIRMATION_UNAVAILABLE"],
        "claim_boundaries": {
            "probability_allowed": False,
            "recommendation_allowed": False,
        },
    }
    return build_report(plan, request)


def make_ledger(directory: str) -> ResearchDecisionLedger:
    root = Path(directory)
    return ResearchDecisionLedger(root / "decisions.jsonl", root / "outcomes.jsonl", "research-L1")


def record(
    ledger: ResearchDecisionLedger,
    report: dict | None = None,
    *,
    decision_id: str = "decision-1",
    issued_at: str = ISSUED_AT,
    recorded_at: str = RECORDED_AT,
) -> dict:
    return ledger.record_report(
        report or built_report(),
        decision_id=decision_id,
        actor_or_model_id="research-engine-v3",
        policy_hash=POLICY_HASH,
        code_hash=CODE_HASH,
        configuration_hash=CONFIGURATION_HASH,
        issued_at=issued_at,
        recorded_at=recorded_at,
        test_mode=True,
    )


def outcome_payload(
    *,
    security_code: str = "101",
    observed_at: str = OUTCOME_OBSERVED_AT,
    value: int | float = 0.02,
) -> dict:
    return {
        "schema_version": "1.0",
        "security_code": security_code,
        "metric_id": "next_session_decimal_return",
        "value": value,
        "unit": "DECIMAL_RETURN",
        "measurement_start_at": DECISION_AT,
        "measurement_end_at": observed_at,
        "method_id": "official_close_to_close_v1",
        "notes": "Measured from official closing-price evidence.",
    }


def write_outcome_pack(
    ledger: ResearchDecisionLedger,
    *,
    outcome_id: str = "outcome-1",
    decision_id: str = "decision-1",
    security_code: str = "101",
    observed_at: str = OUTCOME_OBSERVED_AT,
    packet_root: Path | None = None,
    content: bytes = b'{"security_code":"101","close_fils":100}\n',
) -> Path:
    root = packet_root or ledger.ledger_root / "outcome_evidence" / outcome_id
    raw_path = root / "raw" / "official-close.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(content)
    manifest = {
        "schema_version": "1.0",
        "outcome_id": outcome_id,
        "decision_id": decision_id,
        "security_code": security_code,
        "artifacts": [
            {
                "path": "raw/official-close.json",
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
                "source_id": "official-market-close",
                "source_url": "https://www.example.com/market/official-close.json",
                "content_type": "application/json",
                "observed_at": observed_at,
            }
        ],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return root


class ResearchLedgerTests(unittest.TestCase):
    def test_report_and_ledger_bind_the_complete_evidence_packet(self) -> None:
        report = built_report()
        self.assertEqual(report["evidence_packet_hash"], EVIDENCE_HASH)
        with tempfile.TemporaryDirectory() as directory:
            event = record(make_ledger(directory), report)
            self.assertEqual(event["evidence_packet_hash"], EVIDENCE_HASH)
            self.assertEqual(event["configuration_hash"], CONFIGURATION_HASH)

    def test_missing_evidence_packet_hash_is_rejected(self) -> None:
        report = built_report()
        report.pop("evidence_packet_hash")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "MISSING_OR_INVALID_EVIDENCE_PACKET_HASH"):
                record(make_ledger(directory), report)

    def test_candidate_claim_boundary_is_enforced_recursively_at_ledger(self) -> None:
        report = built_report()
        report["candidates"][0]["analysis"] = {
            "Probability": 0.99,
            "recommendation": "BUY",
            "execution": {"entryPrice": 100, "exit_price": 110},
        }
        errors = validate_research_report(report)
        self.assertTrue(
            any("FORBIDDEN_RESEARCH_CLAIM_FIELD" in error for error in errors),
            errors,
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "FORBIDDEN_RESEARCH_CLAIM_FIELD"):
                record(make_ledger(directory), report)

    def test_candidate_cannot_disguise_probability_as_score_kind_or_status(self) -> None:
        report = built_report()
        candidate = report["candidates"][0]
        candidate["score_kind"] = "CALIBRATED_PROBABILITY"
        candidate["decision_status"] = "BUY"
        candidate["source_conflict"] = "SELL"
        errors = validate_research_report(report)
        self.assertIn("CANDIDATE_SCORE_KIND_INVALID:report.candidates[0]", errors)
        self.assertIn("CANDIDATE_DECISION_STATUS_INVALID:report.candidates[0]", errors)
        self.assertIn(
            "CANDIDATE_BOOLEAN_FIELD_INVALID:report.candidates[0].source_conflict",
            errors,
        )

    def test_ledger_rejects_named_request_over_candidate_packet(self) -> None:
        report = built_report()
        report["request"]["scope"] = "NAMED_SECURITIES"
        report["request"]["claim_type"] = "SINGLE_SECURITY"
        report["request"]["security_codes"] = ["101"]
        errors = validate_research_report(report)
        self.assertIn(
            "REPORT_SCOPE_INCOMPATIBLE_WITH_REQUEST:NAMED_SECURITIES:CANDIDATE_SET",
            errors,
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "REPORT_SCOPE_INCOMPATIBLE_WITH_REQUEST"):
                record(make_ledger(directory), report)

    def test_build_report_api_records_exact_detached_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            report = built_report()
            event = record(ledger, report)
            report["candidates"][0]["research_score"] = 999

            self.assertEqual(event["report"]["candidates"][0]["research_score"], 54.0)
            self.assertEqual(ledger.decisions()[0]["report"]["candidates"][0]["research_score"], 54.0)
            self.assertEqual(ledger.verify()["status"], "PASS")

    def test_duplicate_decision_cannot_rewrite_past_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            before = ledger.decision_path.read_bytes()
            changed = built_report()
            changed["candidates"][0]["research_score"] = 1
            with self.assertRaisesRegex(ValueError, "cannot be rewritten"):
                record(ledger, changed)
            self.assertEqual(ledger.decision_path.read_bytes(), before)

    def test_nested_case_insensitive_outcome_field_is_rejected(self) -> None:
        report = built_report()
        report["candidates"][0]["explanation"] = [{"Realized_Return": 0.25}]
        self.assertTrue(any("FORBIDDEN_OUTCOME_FIELD" in error for error in validate_research_report(report)))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "FORBIDDEN_OUTCOME_FIELD"):
                record(make_ledger(directory), report)

    def test_forecast_mode_report_is_rejected(self) -> None:
        report = built_report()
        report["mode"] = "validated_forecast"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "REPORT_MODE_NOT_RESEARCH_NETWORK"):
                record(make_ledger(directory), report)

    def test_missing_probability_boundary_is_rejected(self) -> None:
        report = built_report()
        report["claim_boundaries"].pop("research_score_is_probability")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "PROBABILITY_BOUNDARY_MISSING"):
                record(make_ledger(directory), report)

    def test_outcome_is_separate_and_must_link_existing_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            with self.assertRaisesRegex(ValueError, "existing decision_id"):
                ledger.append_outcome(
                    outcome_id="outcome-orphan",
                    decision_id="missing",
                    observed_at=OUTCOME_OBSERVED_AT,
                    recorded_at=OUTCOME_RECORDED_AT,
                    test_mode=True,
                    payload=outcome_payload(),
                    evidence_pack=Path(directory) / "missing-pack",
                    actor_or_model_id="outcome-worker",
                )

            record(ledger)
            pack = write_outcome_pack(ledger)
            event = ledger.append_outcome(
                outcome_id="outcome-1",
                decision_id="decision-1",
                observed_at=OUTCOME_OBSERVED_AT,
                recorded_at=OUTCOME_RECORDED_AT,
                test_mode=True,
                payload=outcome_payload(),
                evidence_pack=pack,
                actor_or_model_id="outcome-worker",
            )
            self.assertEqual(len(ledger.decisions()), 1)
            self.assertNotIn("actual_return", json.dumps(ledger.decisions()))
            self.assertEqual(ledger.outcomes()[0]["decision_id"], "decision-1")
            self.assertEqual(event["evidence_packet_path"], "outcome_evidence/outcome-1")
            self.assertEqual(
                event["evidence_hashes"],
                [hashlib.sha256((pack / "raw" / "official-close.json").read_bytes()).hexdigest()],
            )
            self.assertEqual(ledger.verify()["status"], "PASS")

    def test_outcome_before_decision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            with self.assertRaisesRegex(ValueError, "cannot precede decision_at"):
                ledger.append_outcome(
                    outcome_id="outcome-1",
                    decision_id="decision-1",
                    observed_at="2026-08-06T13:00:00+03:00",
                    recorded_at="2026-08-07T03:00:00+03:00",
                    test_mode=True,
                    payload=outcome_payload(),
                    evidence_pack=Path(directory) / "unused-pack",
                    actor_or_model_id="outcome-worker",
                )

    def test_outcome_observed_before_decision_issuance_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            with self.assertRaisesRegex(ValueError, "cannot precede decision issued_at"):
                ledger.append_outcome(
                    outcome_id="outcome-1",
                    decision_id="decision-1",
                    observed_at="2026-08-07T01:30:00+03:00",
                    recorded_at="2026-08-07T03:00:00+03:00",
                    test_mode=True,
                    payload=outcome_payload(),
                    evidence_pack=Path(directory) / "unused-pack",
                    actor_or_model_id="outcome-worker",
                )

    def test_outcome_observed_before_decision_recording_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            with self.assertRaisesRegex(ValueError, "cannot precede decision recorded_at"):
                ledger.append_outcome(
                    outcome_id="outcome-1",
                    decision_id="decision-1",
                    observed_at="2026-08-07T02:00:30+03:00",
                    recorded_at="2026-08-07T03:00:00+03:00",
                    test_mode=True,
                    payload=outcome_payload(),
                    evidence_pack=Path(directory) / "unused-pack",
                    actor_or_model_id="outcome-worker",
                )

    def test_outcome_api_accepts_only_an_evidence_pack_not_caller_hashes(self) -> None:
        parameters = inspect.signature(ResearchDecisionLedger.append_outcome).parameters
        self.assertIn("evidence_pack", parameters)
        self.assertNotIn("evidence_hashes", parameters)

    def test_outcome_payload_cannot_shadow_linkage_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            pack = write_outcome_pack(ledger)
            payload = outcome_payload()
            payload["decision_id"] = "different-decision"
            with self.assertRaisesRegex(ValueError, "shadows envelope"):
                ledger.append_outcome(
                    outcome_id="outcome-1",
                    decision_id="decision-1",
                    observed_at=OUTCOME_OBSERVED_AT,
                    recorded_at=OUTCOME_RECORDED_AT,
                    test_mode=True,
                    payload=payload,
                    evidence_pack=pack,
                    actor_or_model_id="outcome-worker",
                )

    def test_tampering_report_breaks_payload_and_event_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            event = json.loads(ledger.decision_path.read_text(encoding="utf-8"))
            event["report"]["candidates"][0]["research_score"] = 99
            ledger.decision_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            result = ledger.verify()
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(any("REPORT_HASH" in error for error in result["errors"]))
            self.assertTrue(any("EVENT_HASH" in error for error in result["errors"]))

    def test_reordering_breaks_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            record(
                ledger,
                built_report("request-2"),
                decision_id="decision-2",
                recorded_at="2026-08-07T02:02:00+03:00",
            )
            lines = ledger.decision_path.read_text(encoding="utf-8").splitlines()
            ledger.decision_path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
            result = ledger.verify()
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(any("PREVIOUS_HASH" in error or "SEQUENCE" in error for error in result["errors"]))

    def test_truncated_append_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            with ledger.decision_path.open("ab") as handle:
                handle.write(b'{"partial":')
            result = ledger.verify()
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(any("truncated" in error for error in result["errors"]))

    def test_short_write_rolls_back_uncommitted_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            real_write = __import__("os").write

            def short_write(descriptor: int, data: bytes) -> int:
                return real_write(descriptor, data[:11])

            with mock.patch("kubo.research_ledger.os.write", side_effect=short_write):
                with self.assertRaisesRegex(OSError, "short atomic append"):
                    record(ledger)
            self.assertEqual(ledger.decision_path.read_bytes(), b"")
            record(ledger)
            self.assertEqual(ledger.verify()["status"], "PASS")

    def test_tampered_stream_refuses_further_append(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            event = json.loads(ledger.decision_path.read_text(encoding="utf-8"))
            event["report"]["status"] = "TAMPERED"
            ledger.decision_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid decision stream"):
                record(
                    ledger,
                    built_report("request-2"),
                    decision_id="decision-2",
                    recorded_at="2026-08-07T02:02:00+03:00",
                )

    def test_concurrent_writers_are_locked_and_chain_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)

            def append(index: int) -> None:
                ledger.record_report(
                    built_report(f"request-{index}"),
                    decision_id=f"decision-{index}",
                    actor_or_model_id="parallel-test",
                    policy_hash=POLICY_HASH,
                    code_hash=CODE_HASH,
                    configuration_hash=CONFIGURATION_HASH,
                )

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(append, range(20)))

            result = ledger.verify()
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["decision_events"], 20)
            self.assertEqual([event["event_seq"] for event in ledger.decisions()], list(range(1, 21)))

    def test_hmac_seal_uses_runtime_key_and_detects_wrong_or_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            seal_path = Path(directory) / "seal.json"
            runtime_key = bytes(range(32))
            ledger.seal(
                seal_path,
                hmac_key=runtime_key,
                key_id="runtime-key-v1",
                sealed_at="2026-08-07T02:02:00+03:00",
                test_mode=True,
            )
            self.assertNotIn(runtime_key.hex(), seal_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ledger.verify_seal(
                    seal_path,
                    hmac_key=runtime_key,
                    expected_key_id="runtime-key-v1",
                )["status"],
                "PASS",
            )
            self.assertIn("HMAC_KEY_REQUIRED", ledger.verify_seal(seal_path)["errors"])
            self.assertIn(
                "HMAC_MISMATCH",
                ledger.verify_seal(
                    seal_path,
                    hmac_key=b"x" * 32,
                    expected_key_id="runtime-key-v1",
                )["errors"],
            )
            self.assertIn(
                "HMAC_KEY_ID_MISMATCH",
                ledger.verify_seal(
                    seal_path,
                    hmac_key=runtime_key,
                    expected_key_id="runtime-key-v2",
                )["errors"],
            )

            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            seal["notes"] = "unsigned-extra-field"
            seal_path.write_text(json.dumps(seal), encoding="utf-8")
            self.assertIn(
                "SEAL_FIELDS",
                ledger.verify_seal(
                    seal_path,
                    hmac_key=runtime_key,
                    expected_key_id="runtime-key-v1",
                )["errors"],
            )
            seal.pop("notes")
            seal["authentication"]["key_id"] = "tampered-key-id"
            seal_path.write_text(json.dumps(seal), encoding="utf-8")
            self.assertIn(
                "HMAC_MISMATCH",
                ledger.verify_seal(
                    seal_path,
                    hmac_key=runtime_key,
                    expected_key_id="runtime-key-v1",
                )["errors"],
            )

    def test_hmac_verification_rejects_content_only_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            seal_path = Path(directory) / "seal.json"
            runtime_key = bytes(range(32))
            ledger.seal(
                seal_path,
                hmac_key=runtime_key,
                key_id="runtime-key-v1",
                sealed_at="2026-08-07T02:02:00+03:00",
                test_mode=True,
            )
            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            seal["authentication"] = {"algorithm": "SHA256-CONTENT"}
            seal_path.write_text(json.dumps(seal), encoding="utf-8")
            result = ledger.verify_seal(
                seal_path,
                hmac_key=runtime_key,
                expected_key_id="runtime-key-v1",
            )
            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("HMAC_DOWNGRADE_REJECTED", result["errors"])

    def test_runtime_trust_registry_hash_is_bound_into_decision_event(self) -> None:
        report = built_report()
        report.update(
            {
                "runtime_trust_required": True,
                "runtime_trust_registry_id": "registry-1",
                "runtime_trust_registry_hash": "e" * 64,
                "runtime_trust_key_id": "runtime-key-v1",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            event = record(ledger, report)
            self.assertEqual(event["runtime_trust_registry_hash"], "e" * 64)
            self.assertEqual(ledger.verify()["status"], "PASS")
            event = json.loads(ledger.decision_path.read_text(encoding="utf-8"))
            event["runtime_trust_registry_hash"] = None
            ledger.decision_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            errors = ledger.verify()["errors"]
            self.assertTrue(
                any("RUNTIME_TRUST_REGISTRY_HASH_BINDING" in item for item in errors),
                errors,
            )

    def test_old_seal_is_invalidated_by_later_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            seal_path = Path(directory) / "seal.json"
            ledger.seal(
                seal_path,
                sealed_at="2026-08-07T02:02:00+03:00",
                test_mode=True,
            )
            pack = write_outcome_pack(ledger)
            ledger.append_outcome(
                outcome_id="outcome-1",
                decision_id="decision-1",
                observed_at=OUTCOME_OBSERVED_AT,
                recorded_at=OUTCOME_RECORDED_AT,
                test_mode=True,
                payload=outcome_payload(),
                evidence_pack=pack,
                actor_or_model_id="outcome-worker",
            )
            result = ledger.verify_seal(seal_path)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(any("OUTCOME_STREAM" in error for error in result["errors"]))

    def test_runtime_timestamp_cannot_be_caller_backdated_in_production(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            with self.assertRaisesRegex(ValueError, "requires test_mode"):
                ledger.record_report(
                    built_report(),
                    decision_id="decision-1",
                    actor_or_model_id="research-engine-v3",
                    policy_hash=POLICY_HASH,
                    code_hash=CODE_HASH,
                    configuration_hash=CONFIGURATION_HASH,
                    recorded_at=RECORDED_AT,
                )

    def test_decision_and_outcome_paths_must_be_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.jsonl"
            with self.assertRaisesRegex(ValueError, "separate paths"):
                ResearchDecisionLedger(path, path, "research-L1")


if __name__ == "__main__":
    unittest.main()
