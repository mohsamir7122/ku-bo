from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from kubo.priority_runtime import (
    AtomicCheckpointStore,
    CheckpointCasError,
    FencingViolation,
    PriorityRuntimeError,
    make_shard,
)


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


class PriorityRuntimeAdversarialTests(unittest.TestCase):
    def create_checkpoint(
        self, temp: str
    ) -> tuple[AtomicCheckpointStore, dict[str, object], Path]:
        root = Path(temp)
        artifacts = root / "artifacts"
        artifacts.mkdir()
        store = AtomicCheckpointStore(root / "checkpoints")
        checkpoint = store.create(
            workload_id="adversarial-backfill",
            workload_class="BACKFILL_90D",
            owner_run_id="run-1",
            scheduled_at=NOW,
            actual_started_at=NOW,
            shards=[
                make_shard(
                    market="KUWAIT",
                    source_id="issuer_disclosures",
                    partition_date="2026-05-30",
                )
            ],
        )
        return store, checkpoint, artifacts

    def start(
        self,
        store: AtomicCheckpointStore,
        checkpoint: dict[str, object],
        *,
        generation: int = 1,
        now: datetime = NOW + timedelta(seconds=1),
    ) -> dict[str, object]:
        row, _ = store.start_shard(
            "adversarial-backfill",
            shard_id_value=checkpoint["shards"][0]["shard_id"],
            expected_generation=generation,
            fencing_token=checkpoint["fencing_token"],
            now=now,
        )
        return row

    def test_path_traversal_and_symlink_outputs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, checkpoint, artifacts = self.create_checkpoint(temp)
            running = self.start(store, checkpoint)
            with self.assertRaisesRegex(ValueError, "inside"):
                store.complete_shard(
                    "adversarial-backfill",
                    shard_id_value=checkpoint["shards"][0]["shard_id"],
                    expected_generation=1,
                    fencing_token=running["fencing_token"],
                    artifact_root=artifacts,
                    output_path="../escaped.jsonl",
                    now=NOW + timedelta(seconds=2),
                )
            outside = Path(temp) / "outside.jsonl"
            outside.write_bytes(b"outside\n")
            (artifacts / "linked.jsonl").symlink_to(outside)
            with self.assertRaisesRegex(PriorityRuntimeError, "symlink"):
                store.complete_shard(
                    "adversarial-backfill",
                    shard_id_value=checkpoint["shards"][0]["shard_id"],
                    expected_generation=1,
                    fencing_token=running["fencing_token"],
                    artifact_root=artifacts,
                    output_path="linked.jsonl",
                    now=NOW + timedelta(seconds=2),
                )

    def test_symlink_artifact_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, checkpoint, artifacts = self.create_checkpoint(temp)
            running = self.start(store, checkpoint)
            (artifacts / "real.jsonl").write_bytes(b"record\n")
            linked_root = Path(temp) / "linked-artifacts"
            linked_root.symlink_to(artifacts, target_is_directory=True)
            with self.assertRaisesRegex(PriorityRuntimeError, "symlink"):
                store.complete_shard(
                    "adversarial-backfill",
                    shard_id_value=checkpoint["shards"][0]["shard_id"],
                    expected_generation=1,
                    fencing_token=running["fencing_token"],
                    artifact_root=linked_root,
                    output_path="real.jsonl",
                    now=NOW + timedelta(seconds=2),
                )

    def test_dangling_checkpoint_symlink_is_not_treated_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "checkpoints"
            store = AtomicCheckpointStore(root)
            path = root / "dangling.checkpoint.json"
            path.symlink_to(root / "missing.json")
            with self.assertRaisesRegex(PriorityRuntimeError, "real regular file"):
                store.load("dangling")

    def test_checkpoint_digest_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, _, _ = self.create_checkpoint(temp)
            path = Path(temp) / "checkpoints/adversarial-backfill.checkpoint.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["checkpoint_digest"] = "f" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(PriorityRuntimeError, "digest mismatch"):
                store.load("adversarial-backfill")

    def test_stale_generation_and_fencing_token_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, checkpoint, _ = self.create_checkpoint(temp)
            with self.assertRaises(CheckpointCasError):
                store.start_shard(
                    "adversarial-backfill",
                    shard_id_value=checkpoint["shards"][0]["shard_id"],
                    expected_generation=2,
                    fencing_token=checkpoint["fencing_token"],
                    now=NOW + timedelta(seconds=1),
                )
            with self.assertRaises(FencingViolation):
                store.start_shard(
                    "adversarial-backfill",
                    shard_id_value=checkpoint["shards"][0]["shard_id"],
                    expected_generation=1,
                    fencing_token="f" * 64,
                    now=NOW + timedelta(seconds=1),
                )

    def test_completed_artifact_hash_mismatch_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, checkpoint, artifacts = self.create_checkpoint(temp)
            running = self.start(store, checkpoint)
            output = artifacts / "result.jsonl"
            output.write_bytes(b"first\n")
            store.complete_shard(
                "adversarial-backfill",
                shard_id_value=checkpoint["shards"][0]["shard_id"],
                expected_generation=1,
                fencing_token=running["fencing_token"],
                artifact_root=artifacts,
                output_path="result.jsonl",
                now=NOW + timedelta(seconds=2),
            )
            output.write_bytes(b"other\n")
            with self.assertRaisesRegex(PriorityRuntimeError, "digest mismatch"):
                store.verify_completed_outputs(
                    "adversarial-backfill", artifact_root=artifacts
                )

    def test_attempt_budget_has_no_unbounded_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, checkpoint, _ = self.create_checkpoint(temp)
            first = self.start(store, checkpoint)
            stopped = store.preempt(
                "adversarial-backfill",
                expected_generation=1,
                fencing_token=first["fencing_token"],
                now=NOW + timedelta(seconds=2),
            )
            second = store.claim_resume(
                "adversarial-backfill",
                expected_generation=1,
                owner_run_id="run-2",
                now=NOW + timedelta(seconds=3),
            )
            second = self.start(
                store,
                second,
                generation=2,
                now=NOW + timedelta(seconds=4),
            )
            stopped = store.preempt(
                "adversarial-backfill",
                expected_generation=2,
                fencing_token=second["fencing_token"],
                now=NOW + timedelta(seconds=5),
            )
            third = store.claim_resume(
                "adversarial-backfill",
                expected_generation=2,
                owner_run_id="run-3",
                now=NOW + timedelta(seconds=6),
            )
            with self.assertRaisesRegex(PriorityRuntimeError, "budget is exhausted"):
                self.start(
                    store,
                    third,
                    generation=3,
                    now=NOW + timedelta(seconds=7),
                )
            self.assertEqual(stopped["shards"][0]["attempt_count"], 2)

    def test_checkpoint_time_cannot_move_backwards(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, checkpoint, _ = self.create_checkpoint(temp)
            with self.assertRaisesRegex(PriorityRuntimeError, "cannot move backwards"):
                store.start_shard(
                    "adversarial-backfill",
                    shard_id_value=checkpoint["shards"][0]["shard_id"],
                    expected_generation=1,
                    fencing_token=checkpoint["fencing_token"],
                    now=NOW - timedelta(seconds=1),
                )


if __name__ == "__main__":
    unittest.main()
