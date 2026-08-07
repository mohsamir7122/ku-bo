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

from helpers import HASHES


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
    args = {
        "event_type": "CREATE", "claim_id": "c1", "issued_at": "2026-08-06T14:00:00+03:00",
        "effective_at": "2026-08-06T14:00:00+03:00", "recorded_at": "2026-08-06T14:01:00+03:00",
        "test_mode": True, "source_hash": HASHES["f"], "actor_or_model_id": "m1",
        "policy_hash": HASHES["a"], "code_hash": HASHES["b"], "feature_snapshot_hash": HASHES["c"],
        "universe_hash": HASHES["d"], "trading_calendar_hash": HASHES["e"], "payload": payload(),
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
    def test_valid_chain_and_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ForecastLedger(Path(directory) / "ledger.jsonl", "L1")
            append_valid(ledger)
            self.assertEqual(ledger.verify()["status"], "PASS")
            seal_path = Path(directory) / "seal.json"
            ledger.seal(seal_path, sealed_at="2026-08-06T14:02:00+03:00", test_mode=True)
            self.assertEqual(ledger.verify_seal(seal_path)["status"], "PASS")

    def test_bad_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ForecastLedger(Path(directory) / "ledger.jsonl", "L1")
            with self.assertRaises(ValueError):
                append_valid(ledger, policy_hash="bad")

    def test_backdated_recorded_at_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ForecastLedger(Path(directory) / "ledger.jsonl", "L1")
            with self.assertRaises(ValueError):
                append_valid(ledger, recorded_at="2020-01-01T00:00:00+00:00")

    def test_nested_outcome_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ForecastLedger(Path(directory) / "ledger.jsonl", "L1")
            value = payload()
            value["reason_codes"] = [{"gross_return": .9}]
            with self.assertRaises(ValueError):
                append_valid(ledger, payload=value)

    def test_string_boolean_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ForecastLedger(Path(directory) / "ledger.jsonl", "L1")
            value = payload()
            value["selected"] = "False"
            with self.assertRaises(ValueError):
                append_valid(ledger, payload=value)

    def test_payload_mutation_breaks_both_payload_and_event_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            ledger = ForecastLedger(path, "L1")
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
            ledger = ForecastLedger(path, "L1")
            append_valid(ledger)
            ledger.seal(seal_path, sealed_at="2026-08-06T14:02:00+03:00", test_mode=True)
            amended = payload()
            amended["score"] = .4
            ledger.append(
                event_type="AMEND", claim_id="c1", issued_at="2026-08-06T14:03:00+03:00",
                effective_at="2026-08-06T14:04:00+03:00", recorded_at="2026-08-06T14:04:00+03:00", test_mode=True,
                source_hash=HASHES["f"], actor_or_model_id="m1", policy_hash=HASHES["a"], code_hash=HASHES["b"],
                feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"], trading_calendar_hash=HASHES["e"], payload=amended,
            )
            self.assertEqual(ledger.verify_seal(seal_path)["status"], "BLOCKED")

    def test_backdated_amendment_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ForecastLedger(Path(directory) / "ledger.jsonl", "L1")
            append_valid(ledger)
            with self.assertRaises(ValueError):
                ledger.append(
                    event_type="AMEND", claim_id="c1", issued_at="2026-08-06T14:03:00+03:00",
                    effective_at="2026-08-06T14:03:00+03:00", recorded_at="2026-08-06T14:04:00+03:00", test_mode=True,
                    source_hash=HASHES["f"], actor_or_model_id="m1", policy_hash=HASHES["a"], code_hash=HASHES["b"],
                    feature_snapshot_hash=HASHES["c"], universe_hash=HASHES["d"], trading_calendar_hash=HASHES["e"], payload=payload(),
                )

    def test_concurrent_process_writers_keep_one_valid_hash_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            with ProcessPoolExecutor(max_workers=6) as pool:
                sequences = list(pool.map(append_in_process, [str(path)] * 12, range(12)))

            ledger = ForecastLedger(path, "L1")
            result = ledger.verify()
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["events"], 12)
            self.assertEqual(sorted(sequences), list(range(1, 13)))
            self.assertEqual(
                [event["event_seq"] for event in ledger.events()],
                list(range(1, 13)),
            )

    def test_short_atomic_append_restores_the_previous_valid_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            ledger = ForecastLedger(path, "L1")
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
            self.assertEqual(ledger.verify()["status"], "PASS")

            append_valid(ledger, claim_id="c2")
            self.assertEqual(ledger.verify()["status"], "PASS")
            self.assertEqual(ledger.verify()["events"], 2)


if __name__ == "__main__":
    unittest.main()
