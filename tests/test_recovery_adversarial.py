from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from kubo.recovery import (
    ActiveLeaseError,
    LeaseError,
    RecoveryError,
    acquire_recovery_lease,
    build_incident,
    load_recovery_policy,
    next_source_fallback,
    read_recovery_lease,
    record_retry_attempt,
    recovery_decision,
    stable_fingerprint,
    validate_dispatch_inputs,
    validate_incident,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


class RecoveryAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, _ = load_recovery_policy(ROOT)

    def incident(self, error_class: str = "transient_source") -> dict[str, object]:
        return build_incident(
            ROOT,
            market="KUWAIT",
            stage="validation",
            error_class=error_class,
            component="provenance_gate",
            failure_code="VALIDATION_FAILED",
            code_sha="1" * 40,
            failed_run_id="run-42",
            summary="validation failed closed",
            now=NOW,
        )

    def test_forged_fingerprint_is_rejected(self) -> None:
        incident = self.incident()
        incident["fingerprint"] = "f" * 64
        with self.assertRaisesRegex(RecoveryError, "fingerprint"):
            validate_incident(incident, policy=self.policy)

    def test_caller_cannot_override_retriable_policy(self) -> None:
        incident = self.incident("permission_required")
        incident["retriable"] = True
        incident["retry_after"] = "2026-08-27T12:30:00Z"
        with self.assertRaisesRegex(RecoveryError, "trusted policy"):
            validate_incident(incident, policy=self.policy)

    def test_publish_allowed_true_is_always_rejected(self) -> None:
        incident = self.incident()
        incident["publish_allowed"] = True
        with self.assertRaisesRegex(RecoveryError, "publish_allowed=false"):
            validate_incident(incident, policy=self.policy)

    def test_unsanitized_summary_is_rejected(self) -> None:
        incident = self.incident()
        token = "github_" + "pat_" + ("Q" * 30)
        incident["sanitized_summary"] = "Authorization: Bearer " + token
        with self.assertRaisesRegex(RecoveryError, "sensitive"):
            validate_incident(incident, policy=self.policy)

    def test_duplicate_fallbacks_and_unknown_fields_are_rejected(self) -> None:
        duplicate = self.incident()
        duplicate["fallbacks_tried"] = ["official_export", "official_export"]
        with self.assertRaisesRegex(RecoveryError, "unique"):
            validate_incident(duplicate, policy=self.policy)
        unknown = self.incident()
        unknown["disable_safety_gate"] = True
        with self.assertRaisesRegex(RecoveryError, "unknown"):
            validate_incident(unknown, policy=self.policy)

    def test_invalid_dispatch_modes_and_overrides_are_rejected(self) -> None:
        incident_id = self.incident()["incident_id"]
        invalid = (
            {"mode": "force", "incident_id": incident_id},
            {"mode": "retry", "incident_id": None},
            {"mode": "retry", "incident_id": incident_id, "checkpoint": "stage-1"},
            {"mode": "normal", "incident_id": incident_id},
            {"mode": "resume", "incident_id": "INC-not-valid"},
            {"mode": "resume", "incident_id": incident_id, "checkpoint": "../main"},
        )
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(RecoveryError):
                validate_dispatch_inputs(**row)

    def test_retry_window_expiry_fails_closed(self) -> None:
        decision = recovery_decision(
            self.incident(),
            now=NOW + timedelta(hours=24, seconds=1),
            policy=self.policy,
        )
        self.assertEqual(decision["action"], "RETRY_WINDOW_EXPIRED")
        self.assertFalse(decision["dispatch_allowed"])
        self.assertTrue(decision["alert_due"])

    def test_attempt_cannot_be_recorded_before_it_is_due(self) -> None:
        with self.assertRaisesRegex(RecoveryError, "not due"):
            record_retry_attempt(
                self.incident(), now=NOW + timedelta(minutes=29), policy=self.policy
            )

    def test_source_fallback_cannot_skip_reorder_or_start_with_secondary(self) -> None:
        invalid_attempts = (
            ["alternate_official_page_or_repository"],
            [
                "official_documented_api_or_export",
                "issuer_official_disclosures",
            ],
            ["secondary_discovery_only"],
        )
        for attempted in invalid_attempts:
            with self.subTest(attempted=attempted), self.assertRaisesRegex(
                RecoveryError, "ordered prefix"
            ):
                next_source_fallback(self.policy, attempted)

        weakened = json.loads(json.dumps(self.policy))
        weakened["source_fallback_order"].reverse()
        with self.assertRaisesRegex(RecoveryError, "trusted policy"):
            next_source_fallback(weakened, [])


class RecoveryLeaseAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, _ = load_recovery_policy(ROOT)
        cls.fingerprint = stable_fingerprint(
            market="KUWAIT",
            stage="collection",
            error_class="github_infrastructure",
            component="runner",
            failure_code="RUNNER_LOST",
        )

    def test_path_traversal_fingerprint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(LeaseError):
            acquire_recovery_lease(
                temp,
                fingerprint="../" + ("a" * 61),
                run_id="run-1",
                owner="owner-1",
                process_identity="github:run-1:job",
                now=NOW,
                policy=self.policy,
            )

    def test_symlink_lease_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target = base / "target"
            target.mkdir()
            link = base / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(LeaseError):
                acquire_recovery_lease(
                    link,
                    fingerprint=self.fingerprint,
                    run_id="run-1",
                    owner="owner-1",
                    process_identity="github:run-1:job",
                    now=NOW,
                    policy=self.policy,
                )

    def test_symlink_lease_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = root / f"{self.fingerprint}.lease.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(LeaseError):
                acquire_recovery_lease(
                    root,
                    fingerprint=self.fingerprint,
                    run_id="run-1",
                    owner="owner-1",
                    process_identity="github:run-1:job",
                    now=NOW,
                    policy=self.policy,
                )

    def test_tampered_lease_digest_is_rejected(self) -> None:
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
            path = Path(temp) / f"{self.fingerprint}.lease.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["owner"] = "attacker"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(LeaseError, "digest"):
                read_recovery_lease(temp, fingerprint=self.fingerprint)

    def test_expired_lease_with_live_local_process_is_not_recovered(self) -> None:
        from kubo.recovery import current_process_identity

        with tempfile.TemporaryDirectory() as temp:
            acquire_recovery_lease(
                temp,
                fingerprint=self.fingerprint,
                run_id="run-1",
                owner="owner-1",
                process_identity=current_process_identity(),
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
                    now=NOW + timedelta(minutes=16),
                    policy=self.policy,
                    active_run_probe=lambda _: False,
                )


if __name__ == "__main__":
    unittest.main()
