from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None
    FormatChecker = None

from kubo.recovery import (
    ActiveLeaseError,
    LeaseRecoveryBlockedError,
    acquire_recovery_lease,
    alert_due,
    build_incident,
    current_process_identity,
    heartbeat_recovery_lease,
    load_recovery_policy,
    next_source_fallback,
    mark_alert_sent,
    read_recovery_lease,
    record_retry_attempt,
    recovery_idempotency_key,
    recovery_decision,
    release_recovery_lease,
    sanitize_diagnostics,
    stable_fingerprint,
    validate_dispatch_inputs,
    validate_incident,
    validate_recovery_policy,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
CODE_SHA = "a" * 40


class RecoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, _ = load_recovery_policy(ROOT)

    def incident(self, error_class: str = "transient_network") -> dict[str, object]:
        return build_incident(
            ROOT,
            market="KUWAIT",
            stage="collection",
            error_class=error_class,
            component="boursa_probe",
            failure_code="CONNECTION_RESET",
            code_sha=CODE_SHA,
            failed_run_id="33043529715",
            run_url="https://github.com/mohsamir7122/ku-bo/actions/runs/33043529715",
            summary="source connection reset without a response",
            now=NOW,
        )

    def test_policy_is_complete_and_fail_closed(self) -> None:
        report = validate_recovery_policy(ROOT)
        self.assertEqual(report["classification_count"], 16)
        self.assertEqual(report["maximum_automatic_attempts"], 2)
        self.assertFalse(report["publish_allowed_while_blocked"])
        self.assertEqual(report["direct_email_status"], "DIRECT_EMAIL_NOT_CONFIGURED")

    def test_incident_schema_accepts_canonical_incident(self) -> None:
        if Draft202012Validator is None or FormatChecker is None:
            self.skipTest("jsonschema optional dependency unavailable")
        schema = json.loads(
            (ROOT / "schemas" / "recovery-incident.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(self.incident())

    def test_stable_fingerprint_uses_canonical_basis(self) -> None:
        first = stable_fingerprint(
            market="kuwait",
            stage="COLLECTION",
            error_class="TRANSIENT_NETWORK",
            component="BOURSA_PROBE",
            failure_code="connection_reset",
        )
        second = stable_fingerprint(
            market="KUWAIT",
            stage="collection",
            error_class="transient_network",
            component="boursa_probe",
            failure_code="CONNECTION_RESET",
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_diagnostics_are_recursively_redacted(self) -> None:
        token = "ghp_" + ("Z" * 36)
        result = sanitize_diagnostics(
            {
                "Authorization": "Bearer " + token,
                "nested": {
                    "url": "https://example.test/a?signa" + "ture=" + token + "&page=2",
                    "cookie": "ses" + "sion=" + token,
                },
            }
        )
        encoded = json.dumps(result)
        self.assertNotIn(token, encoded)
        self.assertIn("[REDACTED]", encoded)
        self.assertIn("page=2", encoded)

    def test_transient_retry_is_due_immediately(self) -> None:
        incident = self.incident()
        due = recovery_decision(
            incident, now=NOW, policy=self.policy
        )
        self.assertEqual(due["action"], "DISPATCH_RETRY")
        self.assertTrue(due["dispatch_allowed"])
        self.assertEqual(incident["retry_after"], incident["last_seen_at"])

    def test_retry_attempt_budget_and_idempotency_are_enforced(self) -> None:
        incident = self.incident()
        self.assertEqual(
            incident["idempotency_key"],
            recovery_idempotency_key(
                fingerprint=incident["fingerprint"],
                code_sha=incident["code_sha"],
                failed_run_id=incident["failed_run_id"],
                attempt_count=0,
            ),
        )
        first = record_retry_attempt(incident, now=NOW, policy=self.policy)
        self.assertEqual(first["attempt_count"], 1)
        self.assertEqual(first["retry_after"], "2026-08-27T12:00:00Z")
        self.assertNotEqual(first["idempotency_key"], incident["idempotency_key"])
        second = record_retry_attempt(first, now=NOW + timedelta(seconds=1), policy=self.policy)
        self.assertEqual(second["attempt_count"], 2)
        self.assertEqual(second["status"], "EXHAUSTED")
        self.assertIsNone(second["retry_after"])
        decision = recovery_decision(
            second, now=NOW + timedelta(seconds=2), policy=self.policy
        )
        self.assertEqual(decision["action"], "RETRY_EXHAUSTED")
        self.assertTrue(decision["alert_due"])

    def test_active_market_run_suppresses_duplicate_retry(self) -> None:
        decision = recovery_decision(
            self.incident(),
            now=NOW,
            policy=self.policy,
            active_runs=[{"market": "KUWAIT", "status": "in_progress"}],
        )
        self.assertEqual(decision["action"], "SUPPRESS_ACTIVE_RUN")
        self.assertFalse(decision["dispatch_allowed"])

    def test_missing_secret_runs_probe_then_resumes_after_presence(self) -> None:
        incident = self.incident("missing_secret")
        missing = recovery_decision(
            incident,
            now=NOW,
            policy=self.policy,
            required_secret_available=False,
        )
        present = recovery_decision(
            incident,
            now=NOW,
            policy=self.policy,
            required_secret_available=True,
        )
        self.assertEqual(missing["action"], "HEALTH_PROBE_ONLY")
        self.assertFalse(missing["dispatch_allowed"])
        self.assertEqual(present["action"], "DISPATCH_RESUME_AFTER_SECRET")
        self.assertTrue(present["dispatch_allowed"])

    def test_deterministic_failure_requires_related_validated_new_code(self) -> None:
        incident = self.incident("deterministic_code")
        blocked = recovery_decision(
            incident,
            now=NOW,
            policy=self.policy,
            current_code_sha="b" * 40,
            relevant_code_change=False,
            ci_passed=True,
            smoke_passed=True,
        )
        allowed = recovery_decision(
            incident,
            now=NOW,
            policy=self.policy,
            current_code_sha="b" * 40,
            relevant_code_change=True,
            ci_passed=True,
            smoke_passed=True,
        )
        self.assertEqual(blocked["action"], "NO_RETRY_DETERMINISTIC")
        self.assertEqual(allowed["action"], "DISPATCH_RESUME_AFTER_VALIDATED_FIX")

    def test_security_failure_blocks_immediately(self) -> None:
        decision = recovery_decision(
            self.incident("security"), now=NOW, policy=self.policy
        )
        self.assertEqual(decision["action"], "BLOCK_SECURITY")
        self.assertFalse(decision["dispatch_allowed"])
        self.assertTrue(decision["alert_due"])
        self.assertFalse(decision["publish_allowed"])

    def test_duplicate_alert_is_suppressed_for_six_hours(self) -> None:
        incident = self.incident("permission_required")
        sent = mark_alert_sent(incident, now=NOW, policy=self.policy)
        self.assertFalse(alert_due(sent, now=NOW + timedelta(hours=5, minutes=59), policy=self.policy))
        self.assertTrue(alert_due(sent, now=NOW + timedelta(hours=6), policy=self.policy))

    def test_dispatch_inputs_are_locked_by_mode(self) -> None:
        incident_id = self.incident()["incident_id"]
        self.assertEqual(
            validate_dispatch_inputs(
                mode="resume", incident_id=incident_id, checkpoint="STAGE_4"
            )["mode"],
            "resume",
        )

    def test_source_fallbacks_follow_primary_first_order(self) -> None:
        expected = list(self.policy["source_fallback_order"])
        tried: list[str] = []
        for fallback in expected:
            self.assertEqual(next_source_fallback(self.policy, tried), fallback)
            tried.append(fallback)
        self.assertIsNone(next_source_fallback(self.policy, tried))


class RecoveryLeaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, _ = load_recovery_policy(ROOT)
        cls.fingerprint = stable_fingerprint(
            market="KUWAIT",
            stage="live_scoring",
            error_class="transient_network",
            component="pipeline",
            failure_code="RUNNER_FAILURE",
        )

    def test_active_lease_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            lease = acquire_recovery_lease(
                temp,
                fingerprint=self.fingerprint,
                run_id="run-1",
                owner="owner-1",
                process_identity="github:run-1:job",
                now=NOW,
                policy=self.policy,
            )
            with self.assertRaises(ActiveLeaseError):
                acquire_recovery_lease(
                    temp,
                    fingerprint=self.fingerprint,
                    run_id="run-2",
                    owner="owner-2",
                    process_identity="github:run-2:job",
                    now=NOW + timedelta(minutes=1),
                    policy=self.policy,
                    active_run_probe=lambda _: False,
                )
            self.assertEqual(read_recovery_lease(temp, fingerprint=self.fingerprint), lease)

    def test_stale_lease_requires_and_obeys_active_run_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            acquire_recovery_lease(
                temp,
                fingerprint=self.fingerprint,
                run_id="run-1",
                owner="owner-1",
                process_identity="github:run-1:job",
                now=NOW,
                policy=self.policy,
            )
            stale_time = NOW + timedelta(minutes=16)
            with self.assertRaises(LeaseRecoveryBlockedError):
                acquire_recovery_lease(
                    temp,
                    fingerprint=self.fingerprint,
                    run_id="run-2",
                    owner="owner-2",
                    process_identity="github:run-2:job",
                    now=stale_time,
                    policy=self.policy,
                )
            with self.assertRaises(ActiveLeaseError):
                acquire_recovery_lease(
                    temp,
                    fingerprint=self.fingerprint,
                    run_id="run-2",
                    owner="owner-2",
                    process_identity="github:run-2:job",
                    now=stale_time,
                    policy=self.policy,
                    active_run_probe=lambda _: True,
                )
            recovered = acquire_recovery_lease(
                temp,
                fingerprint=self.fingerprint,
                run_id="run-2",
                owner="owner-2",
                process_identity="github:run-2:job",
                now=stale_time,
                policy=self.policy,
                active_run_probe=lambda _: False,
            )
            self.assertEqual(recovered["run_id"], "run-2")

    def test_heartbeat_and_owned_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            identity = "github:run-1:job"
            acquire_recovery_lease(
                temp,
                fingerprint=self.fingerprint,
                run_id="run-1",
                owner="owner-1",
                process_identity=identity,
                now=NOW,
                policy=self.policy,
            )
            heartbeat = heartbeat_recovery_lease(
                temp,
                fingerprint=self.fingerprint,
                run_id="run-1",
                owner="owner-1",
                process_identity=identity,
                now=NOW + timedelta(minutes=1),
                policy=self.policy,
            )
            self.assertEqual(heartbeat["heartbeat"], "2026-08-27T12:01:00Z")
            release_recovery_lease(
                temp,
                fingerprint=self.fingerprint,
                run_id="run-1",
                owner="owner-1",
                process_identity=identity,
            )
            self.assertIsNone(read_recovery_lease(temp, fingerprint=self.fingerprint))

    def test_current_process_identity_is_stable_for_process(self) -> None:
        self.assertEqual(current_process_identity(), current_process_identity())


if __name__ == "__main__":
    unittest.main()
