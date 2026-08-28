from __future__ import annotations

import copy
from datetime import timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kubo.hashing import canonical_json_bytes, hash_json
from kubo.issuer_security_checkpoint import (
    IssuerSecurityCheckpointCasError,
    IssuerSecurityCheckpointError,
    IssuerSecurityCheckpointFencingError,
    checkpoint_cas,
)

from tests.test_issuer_security_checkpoint import (
    NOW,
    SEAL_KEY,
    SEAL_KEY_ID,
    complete_all_sources,
    create_store,
    result_for_source,
    write_manifest,
)


class IssuerSecurityCheckpointAdversarialTests(unittest.TestCase):
    @staticmethod
    def _rewrite_revision(path: Path, row: dict[str, object]) -> None:
        row["checkpoint_digest"] = hash_json(
            {key: value for key, value in row.items() if key != "checkpoint_digest"}
        )
        path.write_text(json.dumps(row, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _complete_first_two_sources(store, checkpoint, evidence: Path):
        row = checkpoint
        for ordinal, source in enumerate(store.security_plan["source_plan"][:2], start=1):
            started = NOW + timedelta(seconds=ordinal * 10)
            row = store.start_next_source(now=started, **checkpoint_cas(row))
            manifest_path = None
            manifest_sha = None
            if ordinal == 1:
                source_spec = store.catalog.sources[str(source["source_id"])]
                manifest_path, manifest_sha = write_manifest(
                    evidence,
                    source_id=str(source["source_id"]),
                    source_url=source_spec.start_urls[0],
                    ordinal=ordinal,
                    observed_at=started + timedelta(seconds=1),
                )
            row = store.complete_active_source(
                raw_result=result_for_source(
                    source,
                    attempted_at=started + timedelta(seconds=1),
                    completed_at=started + timedelta(seconds=2),
                    manifest_sha256=manifest_sha,
                ),
                evidence_root=evidence,
                manifest_path=manifest_path,
                **checkpoint_cas(row),
            )
        return row

    def test_cas_rejects_boolean_revision_stale_digest_owner_and_fence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, checkpoint, _ = create_store(Path(directory))
            cases = []
            boolean_revision = checkpoint_cas(checkpoint)
            boolean_revision["expected_revision"] = True
            cases.append((boolean_revision, IssuerSecurityCheckpointError))
            boolean_owner = checkpoint_cas(checkpoint)
            boolean_owner["owner_run_id"] = True
            cases.append((boolean_owner, IssuerSecurityCheckpointError))
            stale_digest = checkpoint_cas(checkpoint)
            stale_digest["prior_checkpoint_digest"] = "f" * 64
            cases.append((stale_digest, IssuerSecurityCheckpointCasError))
            stale_owner = checkpoint_cas(checkpoint)
            stale_owner["owner_run_id"] = "another-worker"
            cases.append((stale_owner, IssuerSecurityCheckpointFencingError))
            stale_fence = checkpoint_cas(checkpoint)
            stale_fence["fencing_token"] = "e" * 64
            cases.append((stale_fence, IssuerSecurityCheckpointFencingError))
            for cas, error in cases:
                with self.subTest(error=error.__name__), self.assertRaises(error):
                    store.start_next_source(now=NOW + timedelta(seconds=1), **cas)

    def test_manifest_traversal_and_cross_source_swap_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, checkpoint, evidence = create_store(root)
            running = store.start_next_source(
                now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
            )
            source = store.security_plan["source_plan"][0]
            fake_result = result_for_source(
                source,
                attempted_at=NOW + timedelta(seconds=2),
                completed_at=NOW + timedelta(seconds=3),
                manifest_sha256="a" * 64,
            )
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "portable"):
                store.complete_active_source(
                    raw_result=fake_result,
                    evidence_root=evidence,
                    manifest_path="../outside/manifest.json",
                    **checkpoint_cas(running),
                )

            wrong = store.catalog.sources["cma_ifsah"]
            manifest_path, manifest_sha = write_manifest(
                evidence,
                source_id="cma_ifsah",
                source_url=wrong.start_urls[0],
                ordinal=1,
                observed_at=NOW + timedelta(seconds=2),
            )
            swapped_result = result_for_source(
                source,
                attempted_at=NOW + timedelta(seconds=2),
                completed_at=NOW + timedelta(seconds=3),
                manifest_sha256=manifest_sha,
            )
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "source differs"):
                store.complete_active_source(
                    raw_result=swapped_result,
                    evidence_root=evidence,
                    manifest_path=manifest_path,
                    **checkpoint_cas(running),
                )

    def test_rehashed_cross_security_receipt_and_broken_revision_chain_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, checkpoint, _ = create_store(root)
            store.start_next_source(
                now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
            )
            first_path = root / "checkpoints" / f"{store.checkpoint_id}.revision-00000001.json"
            first = json.loads(first_path.read_text(encoding="utf-8"))
            first["owner_run_id"] = "forged-owner"
            first["fencing_token"] = hash_json(
                {
                    "checkpoint_id": first["checkpoint_id"],
                    "generation": first["generation"],
                    "owner_run_id": first["owner_run_id"],
                }
            )
            first["checkpoint_digest"] = hash_json(
                {key: value for key, value in first.items() if key != "checkpoint_digest"}
            )
            first_path.write_text(json.dumps(first), encoding="utf-8")
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "reopened plan|chain"):
                store.load()

    def test_dangling_revision_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, _, _ = create_store(root)
            revision = root / "checkpoints" / f"{store.checkpoint_id}.revision-00000001.json"
            revision.unlink()
            revision.symlink_to(root / "missing-revision.json")
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "symlink"):
                store.load()

    def test_checkpoint_revision_guard_and_root_swaps_fail_closed(self) -> None:
        for target in ("revision", "guard"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                store, _, _ = create_store(root)
                if target == "revision":
                    path = root / "checkpoints" / f"{store.checkpoint_id}.revision-00000001.json"
                else:
                    path = root / "checkpoints" / f"{store.checkpoint_id}.guard"
                os.link(path, root / f"{target}-hard-link")
                with self.assertRaisesRegex(IssuerSecurityCheckpointError, "hard-linked"):
                    store.load()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, _, _ = create_store(root)
            checkpoint_root = root / "checkpoints"
            checkpoint_root.rename(root / "displaced-checkpoints")
            checkpoint_root.mkdir()
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "root identity changed"):
                store.load()

    def test_manifest_raw_hard_links_and_unmanifested_bytes_fail_closed(self) -> None:
        for target in ("manifest", "raw", "unmanifested"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                store, checkpoint, evidence = create_store(root)
                running = store.start_next_source(
                    now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
                )
                source = store.security_plan["source_plan"][0]
                source_spec = store.catalog.sources[str(source["source_id"])]
                manifest_path, manifest_sha = write_manifest(
                    evidence,
                    source_id=str(source["source_id"]),
                    source_url=source_spec.start_urls[0],
                    ordinal=1,
                    observed_at=NOW + timedelta(seconds=2),
                )
                packet = (evidence / manifest_path).parent
                if target == "manifest":
                    os.link(packet / "manifest.json", root / "manifest-hard-link.json")
                    pattern = "hard-linked"
                elif target == "raw":
                    os.link(packet / "raw" / "receipt.bin", root / "raw-hard-link.bin")
                    pattern = "hard-linked"
                else:
                    (packet / "unlisted.bin").write_bytes(b"unlisted synthetic bytes\n")
                    pattern = "unmanifested"
                result = result_for_source(
                    source,
                    attempted_at=NOW + timedelta(seconds=2),
                    completed_at=NOW + timedelta(seconds=3),
                    manifest_sha256=manifest_sha,
                )
                with self.assertRaisesRegex(IssuerSecurityCheckpointError, pattern):
                    store.complete_active_source(
                        raw_result=result,
                        evidence_root=evidence,
                        manifest_path=manifest_path,
                        **checkpoint_cas(running),
                    )

    def test_empty_catalog_domain_binds_every_artifact_host_to_requested_domain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, _, evidence = create_store(root)
            source = next(
                source
                for source in store.security_plan["source_plan"]
                if not store.catalog.sources[str(source["source_id"])].domains
            )
            requested_domain = "ir.synthetic.example"
            manifest_path, _ = write_manifest(
                evidence,
                source_id=str(source["source_id"]),
                source_url=f"https://news.{requested_domain}/disclosure",
                ordinal=99,
                observed_at=NOW + timedelta(seconds=2),
            )
            binding = store._reopen_manifest(
                evidence_root=evidence,
                manifest_path=manifest_path,
                source_id=str(source["source_id"]),
                requested_domain=requested_domain,
                attempted_at=NOW + timedelta(seconds=1),
                completed_at=NOW + timedelta(seconds=3),
            )
            self.assertEqual(binding["artifact_count"], 1)
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "requested_domain"):
                store._reopen_manifest(
                    evidence_root=evidence,
                    manifest_path=manifest_path,
                    source_id=str(source["source_id"]),
                    requested_domain="other.example",
                    attempted_at=NOW + timedelta(seconds=1),
                    completed_at=NOW + timedelta(seconds=3),
                )
            for invalid_domain in (
                "a..b.com",
                "-bad.example.com",
                "bad-.example.com",
                "127.0.0.1",
                "ir.synthetic.local",
                "IR.SYNTHETIC.EXAMPLE",
            ):
                with self.subTest(invalid_domain=invalid_domain), self.assertRaisesRegex(
                    IssuerSecurityCheckpointError, "requested_domain"
                ):
                    store._reopen_manifest(
                        evidence_root=evidence,
                        manifest_path=manifest_path,
                        source_id=str(source["source_id"]),
                        requested_domain=invalid_domain,
                        attempted_at=NOW + timedelta(seconds=1),
                        completed_at=NOW + timedelta(seconds=3),
                    )

    def test_artifact_observation_must_be_inside_attempt_window(self) -> None:
        for observed_at in (
            NOW + timedelta(seconds=1),
            NOW + timedelta(seconds=4),
        ):
            with self.subTest(observed_at=observed_at), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                store, checkpoint, evidence = create_store(root)
                running = store.start_next_source(
                    now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
                )
                source = store.security_plan["source_plan"][0]
                source_spec = store.catalog.sources[str(source["source_id"])]
                manifest_path, manifest_sha = write_manifest(
                    evidence,
                    source_id=str(source["source_id"]),
                    source_url=source_spec.start_urls[0],
                    ordinal=1,
                    observed_at=observed_at,
                )
                with self.assertRaisesRegex(IssuerSecurityCheckpointError, "attempt window"):
                    store.complete_active_source(
                        raw_result=result_for_source(
                            source,
                            attempted_at=NOW + timedelta(seconds=2),
                            completed_at=NOW + timedelta(seconds=3),
                            manifest_sha256=manifest_sha,
                        ),
                        evidence_root=evidence,
                        manifest_path=manifest_path,
                        **checkpoint_cas(running),
                    )

    def test_recomputed_receipt_wrong_wave_reorder_substitution_and_authority_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, checkpoint, evidence = create_store(root)
            terminal = self._complete_first_two_sources(store, checkpoint, evidence)
            path = root / "checkpoints" / (
                f"{store.checkpoint_id}.revision-{terminal['revision']:08d}.json"
            )
            original = json.loads(path.read_text(encoding="utf-8"))
            different_wave = next(
                source
                for source in store.security_plan["source_plan"]
                if source["wave_ordinal"] != original["source_slots"][0]["wave_ordinal"]
            )

            def rehash(receipt: dict[str, object]) -> None:
                receipt["source_receipt_sha256"] = hash_json(
                    {
                        key: value
                        for key, value in receipt.items()
                        if key != "source_receipt_sha256"
                    }
                )

            def wrong_wave(row: dict[str, object]) -> None:
                receipt = row["source_slots"][0]["source_receipt"]  # type: ignore[index]
                receipt["wave_ordinal"] = different_wave["wave_ordinal"]
                receipt["wave_id"] = different_wave["wave_id"]
                rehash(receipt)

            def substituted_source(row: dict[str, object]) -> None:
                receipt = row["source_slots"][0]["source_receipt"]  # type: ignore[index]
                receipt["source_id"] = store.security_plan["source_plan"][1]["source_id"]
                rehash(receipt)

            def reordered_receipts(row: dict[str, object]) -> None:
                slots = row["source_slots"]  # type: ignore[assignment]
                slots[0]["source_receipt"], slots[1]["source_receipt"] = (  # type: ignore[index]
                    slots[1]["source_receipt"],
                    slots[0]["source_receipt"],
                )

            def forged_authority(row: dict[str, object]) -> None:
                receipt = row["source_slots"][0]["source_receipt"]  # type: ignore[index]
                receipt["authority_registry_id"] = "forged-registry"
                rehash(receipt)

            def extra_receipt_field(row: dict[str, object]) -> None:
                receipt = row["source_slots"][0]["source_receipt"]  # type: ignore[index]
                receipt["unexpected"] = "forged"
                rehash(receipt)

            for mutate in (
                wrong_wave,
                substituted_source,
                reordered_receipts,
                forged_authority,
                extra_receipt_field,
            ):
                with self.subTest(mutation=mutate.__name__):
                    forged = copy.deepcopy(original)
                    mutate(forged)
                    self._rewrite_revision(path, forged)
                    with self.assertRaisesRegex(
                        IssuerSecurityCheckpointError, "receipt|slot|plan"
                    ):
                        store.load()
            self._rewrite_revision(path, original)

    def test_revision_publication_recovers_prepublish_postpublish_and_partial_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, checkpoint, _ = create_store(root)
            with patch(
                "kubo.issuer_security_checkpoint.os.link",
                side_effect=OSError("injected prepublish failure"),
            ):
                with self.assertRaisesRegex(IssuerSecurityCheckpointError, "publication failed"):
                    store.start_next_source(
                        now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
                    )
            checkpoint_root = root / "checkpoints"
            self.assertEqual(len(list(checkpoint_root.glob(".*.stage-*.tmp"))), 1)
            self.assertFalse(
                (checkpoint_root / f"{store.checkpoint_id}.revision-00000002.json").exists()
            )
            running = store.start_next_source(
                now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
            )
            self.assertEqual(running["revision"], 2)
            self.assertEqual(list(checkpoint_root.glob(".*.stage-*.tmp")), [])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, checkpoint, _ = create_store(root)
            with patch(
                "kubo.issuer_security_checkpoint.os.unlink",
                side_effect=OSError("injected postpublish failure"),
            ):
                with self.assertRaisesRegex(IssuerSecurityCheckpointError, "publication failed"):
                    store.start_next_source(
                        now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
                    )
            recovered = store.load()
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered["revision"], 2)
            self.assertEqual(list((root / "checkpoints").glob(".*.stage-*.tmp")), [])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, checkpoint, _ = create_store(root)
            checkpoint_root = root / "checkpoints"
            partial = checkpoint_root / (
                f".{store.checkpoint_id}.revision-00000002.json."
                "stage-00000000000000000000000000000000.tmp"
            )
            partial.write_bytes(b'{"partial":')
            self.assertEqual(store.load()["revision"], 1)
            self.assertFalse(partial.exists())
            running = store.start_next_source(
                now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
            )
            self.assertEqual(running["revision"], 2)

    def test_worker_attempt_budget_is_bounded_across_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, checkpoint, _ = create_store(Path(directory))
            first = store.start_next_source(
                now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
            )
            stopped = store.preempt(
                now=NOW + timedelta(seconds=2), **checkpoint_cas(first)
            )
            resumed = store.resume(
                new_owner_run_id="worker-2",
                now=NOW + timedelta(seconds=3),
                **checkpoint_cas(stopped),
            )
            second = store.start_next_source(
                now=NOW + timedelta(seconds=4), **checkpoint_cas(resumed)
            )
            stopped = store.preempt(
                now=NOW + timedelta(seconds=5), **checkpoint_cas(second)
            )
            resumed = store.resume(
                new_owner_run_id="worker-3",
                now=NOW + timedelta(seconds=6),
                **checkpoint_cas(stopped),
            )
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "budget"):
                store.start_next_source(
                    now=NOW + timedelta(seconds=7), **checkpoint_cas(resumed)
                )

    def test_raw_bytes_are_reopened_and_mutation_blocks_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, checkpoint, evidence = create_store(Path(directory))
            terminal = complete_all_sources(store, checkpoint, evidence)
            (evidence / "source-01" / "raw" / "receipt.bin").write_bytes(b"tampered\n")
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "size or digest"):
                store.reconcile(
                    evidence_root=evidence,
                    now=NOW + timedelta(seconds=400),
                    **checkpoint_cas(terminal),
                )

    def test_wrong_hmac_key_and_post_seal_mutation_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, checkpoint, evidence = create_store(Path(directory))
            terminal = complete_all_sources(store, checkpoint, evidence)
            reconciled = store.reconcile(
                evidence_root=evidence,
                now=NOW + timedelta(seconds=400),
                **checkpoint_cas(terminal),
            )
            sealed = store.seal(
                evidence_root=evidence,
                seal_key=SEAL_KEY,
                seal_key_id=SEAL_KEY_ID,
                now=NOW + timedelta(seconds=401),
                **checkpoint_cas(reconciled),
            )
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "HMAC"):
                store.verify_bundle(
                    evidence_root=evidence,
                    seal_key=b"wrong-synthetic-terminal-seal-key-material",
                    expected_seal_key_id=SEAL_KEY_ID,
                )
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "immutable"):
                store.resume(
                    new_owner_run_id="forged-resume",
                    now=NOW + timedelta(seconds=402),
                    **checkpoint_cas(sealed),
                )

    def test_hmac_valid_terminal_seal_binding_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, checkpoint, evidence = create_store(root)
            terminal = complete_all_sources(store, checkpoint, evidence)
            reconciled = store.reconcile(
                evidence_root=evidence,
                now=NOW + timedelta(seconds=400),
                **checkpoint_cas(terminal),
            )
            sealed = store.seal(
                evidence_root=evidence,
                seal_key=SEAL_KEY,
                seal_key_id=SEAL_KEY_ID,
                now=NOW + timedelta(seconds=401),
                **checkpoint_cas(reconciled),
            )
            path = root / "checkpoints" / (
                f"{store.checkpoint_id}.revision-{sealed['revision']:08d}.json"
            )
            original = json.loads(path.read_text(encoding="utf-8"))

            def receipts(row: dict[str, object]) -> None:
                row["terminal_seal"]["source_receipt_sha256s"][0] = "0" * 64  # type: ignore[index]

            def manifests(row: dict[str, object]) -> None:
                row["terminal_seal"]["manifest_sha256s"][0] = "0" * 64  # type: ignore[index]

            def preseal(row: dict[str, object]) -> None:
                row["terminal_seal"]["preseal_checkpoint_digest"] = "0" * 64  # type: ignore[index]

            def timestamp(row: dict[str, object]) -> None:
                row["terminal_seal"]["sealed_at"] = (  # type: ignore[index]
                    NOW + timedelta(seconds=402)
                ).isoformat()

            for mutate in (receipts, manifests, preseal, timestamp):
                with self.subTest(mutation=mutate.__name__):
                    forged = copy.deepcopy(original)
                    mutate(forged)
                    seal = forged["terminal_seal"]
                    seal["seal_tag"] = hmac.new(  # type: ignore[index]
                        SEAL_KEY,
                        canonical_json_bytes(
                            {key: value for key, value in seal.items() if key != "seal_tag"}  # type: ignore[union-attr]
                        ),
                        hashlib.sha256,
                    ).hexdigest()
                    self._rewrite_revision(path, forged)
                    with self.assertRaisesRegex(IssuerSecurityCheckpointError, "terminal seal"):
                        store.load()
            self._rewrite_revision(path, original)

            revision_two = root / "checkpoints" / f"{store.checkpoint_id}.revision-00000002.json"
            original_two = json.loads(revision_two.read_text(encoding="utf-8"))
            for state in (reconciled, sealed):
                with self.subTest(forged_status=state["status"]):
                    forged_jump = copy.deepcopy(state)
                    forged_jump["revision"] = 2
                    forged_jump["prior_checkpoint_digest"] = checkpoint["checkpoint_digest"]
                    if forged_jump["terminal_seal"] is not None:
                        forged_jump["terminal_seal"]["preseal_checkpoint_digest"] = checkpoint[
                            "checkpoint_digest"
                        ]
                        forged_jump["terminal_seal"]["seal_tag"] = hmac.new(
                            SEAL_KEY,
                            canonical_json_bytes(
                                {
                                    key: value
                                    for key, value in forged_jump["terminal_seal"].items()
                                    if key != "seal_tag"
                                }
                            ),
                            hashlib.sha256,
                        ).hexdigest()
                    self._rewrite_revision(revision_two, forged_jump)
                    with self.assertRaisesRegex(IssuerSecurityCheckpointError, "transition"):
                        store.load()
            self._rewrite_revision(revision_two, original_two)

    def test_rehashed_generation_owner_and_source_state_skips_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, checkpoint, evidence = create_store(root)
            running = store.start_next_source(
                now=NOW + timedelta(seconds=1), **checkpoint_cas(checkpoint)
            )
            revision_two = root / "checkpoints" / f"{store.checkpoint_id}.revision-00000002.json"
            original_two = json.loads(revision_two.read_text(encoding="utf-8"))

            forged_owner = copy.deepcopy(original_two)
            forged_owner["generation"] = 2
            forged_owner["owner_run_id"] = "forged-owner"
            forged_owner["fencing_token"] = hash_json(
                {
                    "checkpoint_id": forged_owner["checkpoint_id"],
                    "generation": forged_owner["generation"],
                    "owner_run_id": forged_owner["owner_run_id"],
                }
            )
            self._rewrite_revision(revision_two, forged_owner)
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "only during resume"):
                store.load()
            self._rewrite_revision(revision_two, original_two)

            source = store.security_plan["source_plan"][0]
            source_spec = store.catalog.sources[str(source["source_id"])]
            manifest_path, manifest_sha = write_manifest(
                evidence,
                source_id=str(source["source_id"]),
                source_url=source_spec.start_urls[0],
                ordinal=1,
                observed_at=NOW + timedelta(seconds=2),
            )
            completed = store.complete_active_source(
                raw_result=result_for_source(
                    source,
                    attempted_at=NOW + timedelta(seconds=2),
                    completed_at=NOW + timedelta(seconds=3),
                    manifest_sha256=manifest_sha,
                ),
                evidence_root=evidence,
                manifest_path=manifest_path,
                **checkpoint_cas(running),
            )
            forged_skip = copy.deepcopy(completed)
            forged_skip["revision"] = 2
            forged_skip["prior_checkpoint_digest"] = checkpoint["checkpoint_digest"]
            self._rewrite_revision(revision_two, forged_skip)
            with self.assertRaisesRegex(IssuerSecurityCheckpointError, "state transition"):
                store.load()


if __name__ == "__main__":
    unittest.main()
