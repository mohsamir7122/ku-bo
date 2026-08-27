from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from kubo.source_resilience import (
    SourceResilienceController,
    SourceResilienceError,
    classify_source_result,
    source_attempt_idempotency_key,
    source_failure_fingerprint,
)


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def outcome(*, code: str, state: str = "ERROR", query: str = "ERROR", flags=()):
    return SimpleNamespace(
        error_code=code,
        state=state,
        query_status=query,
        data_quality_flags=tuple(flags),
    )


class SourceResilienceTests(unittest.TestCase):
    def key(self, attempt: int = 1) -> str:
        return source_attempt_idempotency_key(
            run_id="run-1",
            event_type="CAPTURE_ATTEMPT",
            source_id="boursa_current",
            route_id="boursa_current:route-01",
            strategy_id="LANDING_ROUTE",
            attempt_ordinal=attempt,
            requested_url="https://www.boursakuwait.com.kw/en/",
            window_from="2026-08-01T00:00:00+03:00",
            window_to="2026-08-27T15:00:00+03:00",
        )

    def test_fingerprint_and_idempotency_are_stable(self) -> None:
        first = source_failure_fingerprint(
            source_id="Boursa_Current",
            error_code="http_timeout",
            registrable_domain="BoursaKuwait.com.kw",
        )
        second = source_failure_fingerprint(
            source_id="boursa_current",
            error_code="HTTP_TIMEOUT",
            registrable_domain="boursakuwait.com.kw",
        )
        self.assertEqual(first, second)
        self.assertEqual(self.key(), self.key())
        self.assertNotEqual(self.key(1), self.key(2))

    def test_duplicate_idempotency_and_attempt_overflow_are_rejected(self) -> None:
        controller = SourceResilienceController(max_attempts=2)
        controller.reserve(self.key(), attempt_ordinal=1)
        with self.assertRaisesRegex(SourceResilienceError, "duplicate"):
            controller.reserve(self.key(), attempt_ordinal=1)
        with self.assertRaisesRegex(SourceResilienceError, "budget exhausted"):
            controller.reserve(self.key(2), attempt_ordinal=3)

    def test_classification_is_derived_from_result(self) -> None:
        self.assertEqual(classify_source_result(outcome(code="HTTP_TIMEOUT")), "TRANSIENT")
        self.assertEqual(
            classify_source_result(
                outcome(code="HTTP_RATE_LIMITED", state="BLOCKED", query="BLOCKED")
            ),
            "RATE_LIMITED",
        )
        self.assertEqual(
            classify_source_result(
                outcome(code="HTTP_FORBIDDEN", state="BLOCKED", query="BLOCKED")
            ),
            "HARD_BLOCK",
        )
        self.assertEqual(
            classify_source_result(
                outcome(code="PARSER_DRIFT", state="PARTIAL", query="PARSER_DRIFT")
            ),
            "QUARANTINE",
        )

    def test_429_circuit_records_retry_after_without_waiting(self) -> None:
        controller = SourceResilienceController(max_attempts=2)
        record = controller.open_circuit(
            source_id="boursa_current",
            error_code="HTTP_RATE_LIMITED",
            registrable_domain="boursakuwait.com.kw",
            classification="RATE_LIMITED",
            opened_at=NOW,
            attempt_count=1,
            retry_after_seconds=90,
        )
        self.assertEqual(record.state, "CIRCUIT_OPEN")
        self.assertEqual(record.retry_after_at, "2026-08-27T12:01:30Z")
        self.assertFalse(controller.adapter_available("boursa_current"))

    def test_policy_block_disables_and_parser_failure_quarantines_only_adapter(self) -> None:
        controller = SourceResilienceController(max_attempts=2)
        blocked = controller.open_circuit(
            source_id="kcc_maqasa_official",
            error_code="ROBOTS_DISALLOWED",
            registrable_domain="maqasa.com",
            classification="HARD_BLOCK",
            opened_at=NOW,
            attempt_count=1,
        )
        quarantined = controller.open_circuit(
            source_id="mubasher_kuwait",
            error_code="PARSER_SCHEMA_FAILURE",
            registrable_domain="mubasher.info",
            classification="QUARANTINE",
            opened_at=NOW,
            attempt_count=1,
        )
        self.assertEqual(blocked.state, "DISABLED")
        self.assertIsNone(blocked.retry_after_at)
        self.assertEqual(quarantined.state, "QUARANTINED")
        self.assertEqual(len(controller.snapshot()), 2)


if __name__ == "__main__":
    unittest.main()
