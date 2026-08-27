from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from kubo.priority_runtime import (
    AtomicCheckpointStore,
    BlockedCheckpointStore,
    PRIORITIES,
    make_shard,
    require_production_checkpoint_store,
    shard_id,
    shard_idempotency_key,
    validate_priority_policy,
)
from kubo.recovery import (
    acquire_recovery_lease,
    load_recovery_policy,
    release_recovery_lease,
    request_recovery_lease_preemption,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def dates_in_window() -> list[date]:
    first = date(2026, 5, 30)
    last = date(2026, 8, 27)
    return [first + timedelta(days=index) for index in range((last - first).days + 1)]


class PriorityPolicyTests(unittest.TestCase):
    def test_policy_schema_and_locked_priority_order(self) -> None:
        policy = json.loads(
            (ROOT / "config/execution-priority-policy.json").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (ROOT / "schemas/execution-priority-policy.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(policy)
        self.assertEqual(
            policy["priorities"],
            {
                "LIVE_DAILY_1500": 100,
                "LIVE_RECOVERY": 90,
                "VALIDATION_AND_PUBLISH": 70,
                "CHALLENGER_TRAINING": 40,
                "BACKFILL_90D": 10,
            },
        )
        self.assertEqual(policy["priorities"], PRIORITIES)

    def test_production_checkpoint_store_remains_fail_closed(self) -> None:
        report = validate_priority_policy(ROOT)
        self.assertEqual(
            report["production_checkpoint_store_status"],
            "BLOCKED_CHECKPOINT_STORE",
        )
        self.assertFalse(report["production_checkpoint_store_configured"])
        self.assertFalse(report["schedule_active"])
        with self.assertRaisesRegex(BlockedCheckpointStore, "BLOCKED_CHECKPOINT_STORE"):
            require_production_checkpoint_store(ROOT)

    def test_backfill_window_is_inclusive_and_exactly_ninety_days(self) -> None:
        window = dates_in_window()
        self.assertEqual(len(window), 90)
        self.assertEqual(window[0].isoformat(), "2026-05-30")
        self.assertEqual(window[-1].isoformat(), "2026-08-27")
        shards = [
            make_shard(
                market="KUWAIT",
                source_id="boursa_kuwait",
                partition_date=item,
            )
            for item in window
        ]
        self.assertEqual(len({item["shard_id"] for item in shards}), 90)

    def test_shard_identity_and_idempotency_are_canonical(self) -> None:
        shard = make_shard(
            market="kuwait",
            source_id="issuer_disclosures",
            page_id="page-001",
        )
        self.assertEqual(
            shard["shard_id"],
            shard_id(
                market="KUWAIT",
                source_id="issuer_disclosures",
                partition_kind="PAGE",
                partition_value="page-001",
            ),
        )
        self.assertEqual(shard["idempotency_key"], shard_idempotency_key(shard, 0))


class PriorityCheckpointTests(unittest.TestCase):
    def create_checkpoint(
        self,
        temp: str,
        *,
        workload_id: str = "backfill-kuwait-90d",
        shard_count: int = 3,
    ) -> tuple[AtomicCheckpointStore, dict[str, object]]:
        store = AtomicCheckpointStore(Path(temp) / "checkpoints")
        shards = [
            make_shard(
                market="KUWAIT",
                source_id="issuer_disclosures",
                partition_date=dates_in_window()[index],
            )
            for index in range(shard_count)
        ]
        checkpoint = store.create(
            workload_id=workload_id,
            workload_class="BACKFILL_90D",
            owner_run_id="background-run-1",
            scheduled_at=NOW,
            actual_started_at=NOW + timedelta(seconds=1),
            shards=shards,
        )
        return store, checkpoint

    def test_checkpoint_schema_and_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, checkpoint = self.create_checkpoint(temp)
            schema = json.loads(
                (ROOT / "schemas/priority-checkpoint.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(checkpoint)
            self.assertEqual(checkpoint["scheduled_at"], "2026-08-27T12:00:00Z")
            self.assertEqual(checkpoint["actual_started_at"], "2026-08-27T12:00:01Z")
            self.assertIsNone(checkpoint["finished_at"])
            self.assertEqual(checkpoint["generation"], 1)
            self.assertEqual(len(str(checkpoint["fencing_token"])), 64)

    def test_shard_requires_reopened_output_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            store, checkpoint = self.create_checkpoint(temp, shard_count=1)
            shard = checkpoint["shards"][0]
            running, changed = store.start_shard(
                "backfill-kuwait-90d",
                shard_id_value=shard["shard_id"],
                expected_generation=1,
                fencing_token=checkpoint["fencing_token"],
                now=NOW + timedelta(seconds=2),
            )
            self.assertTrue(changed)
            with self.assertRaisesRegex(ValueError, "missing or unreadable"):
                store.complete_shard(
                    "backfill-kuwait-90d",
                    shard_id_value=shard["shard_id"],
                    expected_generation=1,
                    fencing_token=running["fencing_token"],
                    artifact_root=artifacts,
                    output_path="shard-1.jsonl",
                    now=NOW + timedelta(seconds=3),
                )
            content = b'{"record_id":"OBS-1"}\n'
            (artifacts / "shard-1.jsonl").write_bytes(content)
            completed = store.complete_shard(
                "backfill-kuwait-90d",
                shard_id_value=shard["shard_id"],
                expected_generation=1,
                fencing_token=running["fencing_token"],
                artifact_root=artifacts,
                output_path="shard-1.jsonl",
                now=NOW + timedelta(seconds=3),
            )
            output = completed["shards"][0]["output"]
            self.assertEqual(output["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(output["size_bytes"], len(content))
            report = store.verify_completed_outputs(
                "backfill-kuwait-90d", artifact_root=artifacts
            )
            self.assertEqual(report["verified_completed_shards"], 1)

    def test_start_is_idempotent_and_attempt_budget_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, checkpoint = self.create_checkpoint(temp, shard_count=1)
            shard_id_value = checkpoint["shards"][0]["shard_id"]
            first, changed = store.start_shard(
                "backfill-kuwait-90d",
                shard_id_value=shard_id_value,
                expected_generation=1,
                fencing_token=checkpoint["fencing_token"],
                now=NOW + timedelta(seconds=2),
            )
            repeated, repeated_changed = store.start_shard(
                "backfill-kuwait-90d",
                shard_id_value=shard_id_value,
                expected_generation=1,
                fencing_token=checkpoint["fencing_token"],
                now=NOW + timedelta(seconds=3),
            )
            self.assertTrue(changed)
            self.assertFalse(repeated_changed)
            self.assertEqual(first["shards"][0]["attempt_count"], 1)
            self.assertEqual(repeated["shards"][0]["attempt_count"], 1)

    def test_live_preempts_background_and_resume_only_replays_incomplete_shard(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            champion = root / "champion.json"
            champion.write_bytes(b'{"champion":"frozen"}\n')
            champion_before = hashlib.sha256(champion.read_bytes()).hexdigest()
            store, checkpoint = self.create_checkpoint(temp)
            workload_id = "backfill-kuwait-90d"
            token = checkpoint["fencing_token"]
            shards = checkpoint["shards"]

            for index, shard in enumerate(shards[:2]):
                state, changed = store.start_shard(
                    workload_id,
                    shard_id_value=shard["shard_id"],
                    expected_generation=1,
                    fencing_token=token,
                    now=NOW + timedelta(seconds=2 + index * 2),
                )
                self.assertTrue(changed)
                path = f"background-{index}.jsonl"
                (artifacts / path).write_bytes(
                    (json.dumps({"shard": shard["shard_id"]}) + "\n").encode()
                )
                checkpoint = store.complete_shard(
                    workload_id,
                    shard_id_value=shard["shard_id"],
                    expected_generation=1,
                    fencing_token=state["fencing_token"],
                    artifact_root=artifacts,
                    output_path=path,
                    now=NOW + timedelta(seconds=3 + index * 2),
                )

            checkpoint, changed = store.start_shard(
                workload_id,
                shard_id_value=shards[2]["shard_id"],
                expected_generation=1,
                fencing_token=token,
                now=NOW + timedelta(seconds=6),
            )
            self.assertTrue(changed)

            recovery_policy, _ = load_recovery_policy(ROOT)
            lease_root = root / "leases"
            fingerprint = "e" * 64
            identity = "github:background-run-1:backfill"
            acquire_recovery_lease(
                lease_root,
                fingerprint=fingerprint,
                run_id="background-run-1",
                owner="backfill-worker",
                process_identity=identity,
                now=NOW,
                policy=recovery_policy,
                priority=10,
                generation=1,
                checkpoint_id=checkpoint["checkpoint_id"],
                expected_generation=0,
            )
            preemption = request_recovery_lease_preemption(
                lease_root,
                fingerprint=fingerprint,
                requester_run_id="live-run-1",
                requester_priority=100,
                expected_generation=1,
                now=NOW + timedelta(seconds=7),
            )
            self.assertTrue(preemption["preempt_requested"])
            preempted = store.preempt(
                workload_id,
                expected_generation=1,
                fencing_token=token,
                now=NOW + timedelta(seconds=8),
            )
            self.assertEqual(
                [item["status"] for item in preempted["shards"]],
                ["COMPLETED", "COMPLETED", "PENDING"],
            )
            self.assertEqual(preempted["shards"][2]["attempt_count"], 1)
            release_recovery_lease(
                lease_root,
                fingerprint=fingerprint,
                run_id="background-run-1",
                owner="backfill-worker",
                process_identity=identity,
            )

            live_shard = make_shard(
                market="KUWAIT",
                source_id="market_gate",
                page_id="live-20260827-1500",
            )
            live = store.create(
                workload_id="live-kuwait-20260827-1500",
                workload_class="LIVE_DAILY_1500",
                owner_run_id="live-run-1",
                scheduled_at=NOW + timedelta(seconds=9),
                actual_started_at=NOW + timedelta(seconds=9),
                shards=[live_shard],
            )
            live, _ = store.start_shard(
                "live-kuwait-20260827-1500",
                shard_id_value=live_shard["shard_id"],
                expected_generation=1,
                fencing_token=live["fencing_token"],
                now=NOW + timedelta(seconds=10),
            )
            (artifacts / "live-result.json").write_bytes(b'{"decision":"NO_TRADE"}\n')
            live = store.complete_shard(
                "live-kuwait-20260827-1500",
                shard_id_value=live_shard["shard_id"],
                expected_generation=1,
                fencing_token=live["fencing_token"],
                artifact_root=artifacts,
                output_path="live-result.json",
                now=NOW + timedelta(seconds=11),
            )
            live = store.finish(
                "live-kuwait-20260827-1500",
                expected_generation=1,
                fencing_token=live["fencing_token"],
                now=NOW + timedelta(seconds=12),
            )
            self.assertEqual(live["status"], "COMPLETED")

            resumed = store.claim_resume(
                workload_id,
                expected_generation=1,
                owner_run_id="background-run-2",
                now=NOW + timedelta(seconds=13),
            )
            self.assertEqual(resumed["generation"], 2)
            resumed, changed = store.start_shard(
                workload_id,
                shard_id_value=shards[2]["shard_id"],
                expected_generation=2,
                fencing_token=resumed["fencing_token"],
                now=NOW + timedelta(seconds=14),
            )
            self.assertTrue(changed)
            (artifacts / "background-2.jsonl").write_bytes(
                (json.dumps({"shard": shards[2]["shard_id"]}) + "\n").encode()
            )
            resumed = store.complete_shard(
                workload_id,
                shard_id_value=shards[2]["shard_id"],
                expected_generation=2,
                fencing_token=resumed["fencing_token"],
                artifact_root=artifacts,
                output_path="background-2.jsonl",
                now=NOW + timedelta(seconds=15),
            )
            resumed = store.finish(
                workload_id,
                expected_generation=2,
                fencing_token=resumed["fencing_token"],
                now=NOW + timedelta(seconds=16),
            )
            self.assertEqual(resumed["status"], "COMPLETED")
            self.assertEqual(
                [item["attempt_count"] for item in resumed["shards"]],
                [1, 1, 2],
            )
            self.assertEqual(
                len({item["output"]["path"] for item in resumed["shards"]}),
                3,
            )
            self.assertEqual(
                hashlib.sha256(champion.read_bytes()).hexdigest(), champion_before
            )


if __name__ == "__main__":
    unittest.main()
