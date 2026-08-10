from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from kubo.ledger import ForecastLedger
from kubo.hashing import canonical_json_bytes, sha256_bytes

from tests.helpers import HASHES


def payload() -> dict:
    return {
        "decision_id": "d1", "security_code": "101", "product_id": "next_session_rank",
        "target_rule": "NET_EXCESS_GT_0", "decision_at": "2026-08-06T14:00:00+03:00",
        "outcome_due_at": "2026-08-09T13:15:00+03:00", "horizon_sessions": 1,
        "model_version": "m1", "entry_rule": "first feasible", "eligible": True,
        "selected": True, "abstained": False, "score": .5, "probability": None,
        "rank": 1, "thesis_episode_id": "episode-1",
    }


def append_valid(ledger: ForecastLedger, **overrides):
    authority = ledger.outcome_session_authority
    args = {
        "event_type": "CREATE", "claim_id": "c1", "issued_at": "2026-08-06T14:00:00+03:00",
        "effective_at": "2026-08-06T14:00:00+03:00", "recorded_at": "2026-08-06T14:01:00+03:00",
        "test_mode": True, "source_hash": HASHES["f"], "actor_or_model_id": "m1",
        "policy_hash": authority.policy_sha256 if authority else HASHES["a"],
        "code_hash": HASHES["b"], "feature_snapshot_hash": HASHES["c"],
        "universe_hash": HASHES["d"],
        "trading_calendar_hash": authority.trading_calendar_sha256 if authority else HASHES["e"],
        "security_status_hash": authority.security_status_sha256 if authority else HASHES["f"],
        "forecast_evidence_mode": "SYNTHETIC_CONTRACT_ONLY",
        "payload": payload(),
    }
    args.update(overrides)
    return ledger.append(**args)


def append_in_process(path: str, index: int) -> int:
    """Create contention after reading while keeping the worker picklable."""

    import kubo.ledger as ledger_module

    original_read = ledger_module._read_events_unlocked

    def delayed_read(ledger_path: Path):
        events = original_read(ledger_path)
        time.sleep(0.02)
        return events

    value = payload()
    value["decision_id"] = f"d-{index}"
    ledger = ForecastLedger(Path(path), "L1")
    with mock.patch("kubo.ledger._read_events_unlocked", side_effect=delayed_read):
        event = append_valid(
            ledger,
            claim_id=f"c-{index}",
            payload=value,
            recorded_at=None,
        )
    return int(event["event_seq"])


class LedgerTests(unittest.TestCase):
    @staticmethod
    def ledger(directory: str, name: str = "ledger.jsonl") -> ForecastLedger:
        root = Path(directory)
        return ForecastLedger(root / name, "L1")

    def test_synthetic_chain_is_valid_but_cannot_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self.ledger(directory)
            append_valid(ledger)
            self.assertEqual(ledger.verify()["status"], "SYNTHETIC_CONTRACT_ONLY")
            seal_path = Path(directory) / "seal.json"
            with self.assertRaisesRegex(ValueError, "cannot seal invalid ledger"):
                ledger.seal(seal_path, sealed_at="2026-08-06T14:02:00+03:00", test_mode=True)

    def test_bad_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self.ledger(directory)
            with self.assertRaises(ValueError):
                append_valid(ledger, policy_hash="bad")

    def test_backdated_recorded_at_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self.ledger(directory)
            with self.assertRaises(ValueError):
                append_valid(ledger, recorded_at="2020-01-01T00:00:00+00:00")

    def test_nested_outcome_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self.ledger(directory)
            value = payload()
            value["reason_codes"] = [{"gross_return": .9}]
            with self.assertRaises(ValueError):
                append_valid(ledger, payload=value)

    def test_imported_forecast_field_smuggling_is_rejected_before_append(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self.ledger(directory)
            smuggled = {"reason": "claimed import", **payload()}
            with self.assertRaisesRegex(
                ValueError, "NON_FORECAST_METADATA_FIELDS_MUST_BE_EXACT_REASON"
            ):
                ledger.append(
                    event_type="IMPORTED", claim_id="c1",
                    issued_at="2026-08-06T14:00:00+03:00",
                    effective_at="2026-08-06T14:00:00+03:00",
                    recorded_at="2026-08-06T14:01:00+03:00", test_mode=True,
                    source_hash=HASHES["f"], actor_or_model_id="importer",
                    policy_hash=HASHES["a"], code_hash=HASHES["b"],
                    feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"],
                    trading_calendar_hash=HASHES["e"], payload=smuggled,
                )
            self.assertFalse((Path(directory) / "ledger.jsonl").exists())

    def test_forged_imported_forecast_payload_blocks_verify_and_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            ledger = self.ledger(directory)
            ledger.append(
                event_type="IMPORTED", claim_id="c1",
                issued_at="2026-08-06T14:00:00+03:00",
                effective_at="2026-08-06T14:00:00+03:00",
                recorded_at="2026-08-06T14:01:00+03:00", test_mode=True,
                source_hash=HASHES["f"], actor_or_model_id="importer",
                policy_hash=HASHES["a"], code_hash=HASHES["b"],
                feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"],
                trading_calendar_hash=HASHES["e"],
                payload={"reason": "non-forecast import metadata"},
            )
            event = ledger.events()[0]
            event["payload"] = {"reason": "smuggled forecast", **payload()}
            event["payload_hash"] = sha256_bytes(canonical_json_bytes(event["payload"]))
            unsigned = dict(event)
            unsigned.pop("event_hash")
            event["event_hash"] = sha256_bytes(canonical_json_bytes(unsigned))
            path.write_bytes(canonical_json_bytes(event))

            report = ledger.verify()
            self.assertEqual(report["status"], "BLOCKED", report)
            self.assertTrue(
                any(
                    "NON_FORECAST_METADATA_FIELDS_MUST_BE_EXACT_REASON" in error
                    for error in report["errors"]
                ),
                report,
            )
            with self.assertRaisesRegex(ValueError, "cannot seal invalid ledger"):
                ledger.seal(Path(directory) / "seal.json")

    def test_withdraw_and_expire_metadata_are_exact_reason_only(self):
        for event_type in ("WITHDRAW", "EXPIRE"):
            with self.subTest(event_type=event_type), tempfile.TemporaryDirectory() as directory:
                ledger = self.ledger(directory)
                ledger.append(
                    event_type="IMPORTED", claim_id="c1",
                    issued_at="2026-08-06T14:00:00+03:00",
                    effective_at="2026-08-06T14:00:00+03:00",
                    recorded_at="2026-08-06T14:01:00+03:00", test_mode=True,
                    source_hash=HASHES["f"], actor_or_model_id="importer",
                    policy_hash=HASHES["a"], code_hash=HASHES["b"],
                    feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"],
                    trading_calendar_hash=HASHES["e"], payload={"reason": "origin"},
                )
                with self.assertRaisesRegex(
                    ValueError, "NON_FORECAST_METADATA_FIELDS_MUST_BE_EXACT_REASON"
                ):
                    ledger.append(
                        event_type=event_type, claim_id="c1",
                        issued_at="2026-08-06T14:02:00+03:00",
                        effective_at="2026-08-06T14:03:00+03:00",
                        recorded_at="2026-08-06T14:03:00+03:00", test_mode=True,
                        source_hash=HASHES["f"], actor_or_model_id="importer",
                        policy_hash=HASHES["a"], code_hash=HASHES["b"],
                        feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"],
                        trading_calendar_hash=HASHES["e"],
                        payload={"reason": "smuggle", "decision_id": "d1"},
                    )

    def test_string_boolean_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self.ledger(directory)
            value = payload()
            value["selected"] = "False"
            with self.assertRaises(ValueError):
                append_valid(ledger, payload=value)

    def test_payload_mutation_breaks_both_payload_and_event_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            ledger = self.ledger(directory)
            append_valid(ledger)
            event = json.loads(path.read_text())
            event["payload"]["score"] = .99
            path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report = ledger.verify()
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(any("PAYLOAD_HASH" in item for item in report["errors"]))

    def test_event_after_seal_invalidates_old_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            seal_path = Path(directory) / "seal.json"
            ledger = self.ledger(directory)
            ledger.append(
                event_type="IMPORTED", claim_id="c1", issued_at="2026-08-06T14:00:00+03:00",
                effective_at="2026-08-06T14:00:00+03:00", recorded_at="2026-08-06T14:01:00+03:00", test_mode=True,
                source_hash=HASHES["f"], actor_or_model_id="m1", policy_hash=HASHES["a"], code_hash=HASHES["b"],
                feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"], trading_calendar_hash=HASHES["e"],
                payload={"reason": "non-forecast import metadata"},
            )
            ledger.seal(seal_path, sealed_at="2026-08-06T14:02:00+03:00", test_mode=True)
            ledger.append(
                event_type="WITHDRAW", claim_id="c1", issued_at="2026-08-06T14:03:00+03:00",
                effective_at="2026-08-06T14:04:00+03:00", recorded_at="2026-08-06T14:04:00+03:00", test_mode=True,
                source_hash=HASHES["f"], actor_or_model_id="m1", policy_hash=HASHES["a"], code_hash=HASHES["b"],
                feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"], trading_calendar_hash=HASHES["e"],
                payload={"reason": "withdraw after seal"},
            )
            self.assertEqual(ledger.verify_seal(seal_path)["status"], "BLOCKED")

    def test_backdated_amendment_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = self.ledger(directory)
            append_valid(ledger)
            with self.assertRaises(ValueError):
                ledger.append(
                    event_type="AMEND", claim_id="c1", issued_at="2026-08-06T14:03:00+03:00",
                    effective_at="2026-08-06T14:03:00+03:00", recorded_at="2026-08-06T14:04:00+03:00", test_mode=True,
                    source_hash=HASHES["f"], actor_or_model_id="m1", policy_hash=HASHES["a"], code_hash=HASHES["b"],
                    feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"], trading_calendar_hash=HASHES["e"],
                    security_status_hash=HASHES["f"], forecast_evidence_mode="SYNTHETIC_CONTRACT_ONLY", payload=payload(),
                )

    def test_concurrent_process_writers_keep_one_valid_hash_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            with ProcessPoolExecutor(max_workers=6) as pool:
                sequences = list(pool.map(append_in_process, [str(path)] * 12, range(12)))

            ledger = ForecastLedger(path, "L1")
            result = ledger.verify()
            self.assertEqual(result["status"], "SYNTHETIC_CONTRACT_ONLY", result)
            self.assertEqual(result["events"], 12)
            self.assertEqual(sorted(sequences), list(range(1, 13)))
            self.assertEqual(
                [event["event_seq"] for event in ledger.events()],
                list(range(1, 13)),
            )

    def test_short_atomic_append_restores_the_previous_valid_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            ledger = self.ledger(directory)
            append_valid(ledger)
            valid_prefix = path.read_bytes()
            real_write = os.write

            def short_write(descriptor: int, data: bytes) -> int:
                return real_write(descriptor, data[:17])

            with mock.patch("kubo.ledger.os.write", side_effect=short_write) as patched_write:
                with self.assertRaisesRegex(OSError, "short atomic append"):
                    append_valid(ledger, claim_id="c2")
            self.assertEqual(patched_write.call_count, 1)
            self.assertEqual(path.read_bytes(), valid_prefix)
            self.assertEqual(ledger.verify()["status"], "SYNTHETIC_CONTRACT_ONLY")

            append_valid(ledger, claim_id="c2")
            self.assertEqual(ledger.verify()["status"], "SYNTHETIC_CONTRACT_ONLY")
            self.assertEqual(ledger.verify()["events"], 2)


if __name__ == "__main__":
    unittest.main()
