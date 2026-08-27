from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import kubo.issuer_checkpoint_v2 as checkpoint_module

from kubo.issuer_checkpoint_v2 import (
    CLAIM_BOUNDARIES,
    IssuerCheckpointV2Error,
    IssuerCheckpointV2FencingError,
    IssuerCheckpointV2Store,
)
from kubo.hashing import canonical_json_bytes, hash_json, sha256_bytes

from tests.test_issuer_checkpoint_v2 import (
    ROOT,
    SEAL_KEY,
    SEAL_KEY_ID,
    START,
    advance_sources,
    begin_source,
    cas,
    complete_source,
    compile_plan,
    seal_full_fixture,
    source_plan,
    synthetic_universe,
)


class IssuerCheckpointV2AdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._template_temp = tempfile.TemporaryDirectory()
        parent = Path(cls._template_temp.name)
        store, plan, _report = seal_full_fixture(parent)
        cls.template = store.root
        cls.plan = plan

    @classmethod
    def tearDownClass(cls) -> None:
        cls._template_temp.cleanup()

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.directory = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def sealed_copy(self) -> IssuerCheckpointV2Store:
        target = self.directory / "sealed-checkpoint"
        shutil.copytree(self.template, target)
        return IssuerCheckpointV2Store(target, project_root=ROOT)

    def new_store(self) -> tuple[IssuerCheckpointV2Store, dict[str, object]]:
        universe = synthetic_universe()
        plan = compile_plan(self.directory, universe)
        store = IssuerCheckpointV2Store.create(
            self.directory / "checkpoint",
            plan=plan,
            issuer_universe=universe,
            project_root=ROOT,
            security_code="999001",
            owner_run_id="owner-1",
            created_at=START,
        )
        return store, plan

    def test_traversal_absolute_backslash_and_dot_aliases_fail_before_raw_write(self) -> None:
        invalid_paths = (
            "../escape",
            "/absolute",
            "nested\\escape",
            "./alias",
            "valid+runtime.json",
            "غير-ASCII.json",
            "CON",
            "raw/NUL.txt",
            "trailing.",
            "a" * 513,
        )
        for index, invalid in enumerate(invalid_paths):
            with self.subTest(path=invalid):
                child = self.directory / f"case-{index}"
                child.mkdir()
                universe = synthetic_universe()
                plan = compile_plan(child, universe)
                store = IssuerCheckpointV2Store.create(
                    child / "checkpoint",
                    plan=plan,
                    issuer_universe=universe,
                    project_root=ROOT,
                    security_code="999001",
                    owner_run_id="owner-1",
                    created_at=START,
                )
                source = source_plan(plan)[0]
                begin_source(store, source, now=START)
                state = store.load()
                with self.assertRaisesRegex(IssuerCheckpointV2Error, "inside|canonical"):
                    store.complete_active_source(
                        security_code="999001",
                        source_ordinal=1,
                        source_id=source["source_id"],  # type: ignore[arg-type]
                        wave_ordinal=source["wave_ordinal"],  # type: ignore[arg-type]
                        wave_id=source["wave_id"],  # type: ignore[arg-type]
                        terminal_status="VERIFIED_ZERO",
                        attempted_at=START,
                        completed_at=START,
                        raw_artifacts={invalid: b"escape"},
                        updated_at=START,
                        **cas(state),  # type: ignore[arg-type]
                    )

    def test_cross_security_substitution_wrong_order_and_wrong_wave_fail_closed(self) -> None:
        cases = (
            {"security_code": "999002"},
            {"source_ordinal": 2},
            {"source_id": "substituted_source"},
            {"wave_ordinal": 7},
            {"wave_id": "DISCOVERY_AND_SENTIMENT_ONLY"},
        )
        for index, replacement in enumerate(cases):
            with self.subTest(replacement=replacement):
                child = self.directory / f"binding-{index}"
                child.mkdir()
                universe = synthetic_universe()
                plan = compile_plan(child, universe)
                store = IssuerCheckpointV2Store.create(
                    child / "checkpoint",
                    plan=plan,
                    issuer_universe=universe,
                    project_root=ROOT,
                    security_code="999001",
                    owner_run_id="owner-1",
                    created_at=START,
                )
                source = source_plan(plan)[0]
                arguments = {
                    "security_code": "999001",
                    "source_ordinal": 1,
                    "source_id": source["source_id"],
                    "wave_ordinal": source["wave_ordinal"],
                    "wave_id": source["wave_id"],
                }
                arguments.update(replacement)
                with self.assertRaises(IssuerCheckpointV2Error):
                    store.begin_next_source(
                        **arguments,  # type: ignore[arg-type]
                        updated_at=START,
                        **cas(store.load()),  # type: ignore[arg-type]
                    )

    def test_boolean_ordinals_are_not_numeric_order_or_wave_values(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        state = store.load()
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "positive integer"):
            store.begin_next_source(
                security_code="999001",
                source_ordinal=True,  # type: ignore[arg-type]
                source_id=source["source_id"],  # type: ignore[arg-type]
                wave_ordinal=True,  # type: ignore[arg-type]
                wave_id=source["wave_id"],  # type: ignore[arg-type]
                updated_at=START,
                **cas(state),  # type: ignore[arg-type]
            )
        begin_source(store, source, now=START)
        active = store.load()
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "positive integer"):
            store.complete_active_source(
                security_code="999001",
                source_ordinal=True,  # type: ignore[arg-type]
                source_id=source["source_id"],  # type: ignore[arg-type]
                wave_ordinal=True,  # type: ignore[arg-type]
                wave_id=source["wave_id"],  # type: ignore[arg-type]
                terminal_status="VERIFIED_ZERO",
                attempted_at=START,
                completed_at=START,
                raw_artifacts={"response.json": b"{}"},
                updated_at=START,
                **cas(active),  # type: ignore[arg-type]
            )
        self.assertEqual(store.load(), active)

    def test_symlink_binding_is_rejected(self) -> None:
        store, _plan = self.new_store()
        plan_path = store.root / "bindings/collection-plan.json"
        outside = self.directory / "outside.json"
        outside.write_bytes(plan_path.read_bytes())
        plan_path.unlink()
        plan_path.symlink_to(outside)
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "symlink"):
            store.load()

    def test_hardlinked_binding_is_rejected(self) -> None:
        store, _plan = self.new_store()
        plan_path = store.root / "bindings/collection-plan.json"
        outside = self.directory / "hardlink-source.json"
        outside.write_bytes(plan_path.read_bytes())
        plan_path.unlink()
        os.link(outside, plan_path)
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "hard-linked"):
            store.load()

    def test_root_swap_after_store_construction_is_rejected(self) -> None:
        store, _plan = self.new_store()
        moved = self.directory / "moved-checkpoint"
        store.root.rename(moved)
        store.root.mkdir()
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "root identity changed"):
            store.load()

    def test_raw_mutation_after_seal_is_rejected(self) -> None:
        store = self.sealed_copy()
        source_id = source_plan(self.plan)[0]["source_id"]
        raw = store.root / f"receipts/001-{source_id}/raw/response.json"
        raw.write_bytes(b'{"mutated":true}\n')
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "raw artifact digest"):
            store.validate_terminal_seal(key=SEAL_KEY, expected_key_id=SEAL_KEY_ID)

    def test_manifest_mutation_after_seal_is_rejected(self) -> None:
        store = self.sealed_copy()
        source_id = source_plan(self.plan)[0]["source_id"]
        manifest_path = store.root / f"receipts/001-{source_id}/manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["manifest_sha256"] = "f" * 64
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(IssuerCheckpointV2Error):
            store.validate_terminal_seal(key=SEAL_KEY, expected_key_id=SEAL_KEY_ID)

    def test_reconciliation_mutation_after_seal_is_rejected(self) -> None:
        store = self.sealed_copy()
        path = store.root / "reconciliation.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["terminal_source_count"] = 28
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(IssuerCheckpointV2Error):
            store.validate_terminal_seal(key=SEAL_KEY, expected_key_id=SEAL_KEY_ID)

    def test_unlisted_bytes_before_or_after_seal_are_rejected(self) -> None:
        for sealed in (False, True):
            with self.subTest(sealed=sealed):
                if sealed:
                    store = self.sealed_copy()
                else:
                    child = self.directory / "unsealed"
                    child.mkdir()
                    universe = synthetic_universe()
                    plan = compile_plan(child, universe)
                    store = IssuerCheckpointV2Store.create(
                        child / "checkpoint",
                        plan=plan,
                        issuer_universe=universe,
                        project_root=ROOT,
                        security_code="999001",
                        owner_run_id="owner-1",
                        created_at=START,
                    )
                (store.root / "unlisted.bin").write_bytes(b"not declared")
                with self.assertRaisesRegex(IssuerCheckpointV2Error, "unlisted"):
                    store.load()

    def test_journal_reordering_or_duplicate_revision_fails_closed(self) -> None:
        store, plan = self.new_store()
        begin_source(store, source_plan(plan)[0], now=START)
        first = store.root / "journal/00000001.json"
        second = store.root / "journal/00000002.json"
        first_bytes = first.read_bytes()
        first.write_bytes(second.read_bytes())
        second.write_bytes(first_bytes)
        with self.assertRaises(IssuerCheckpointV2Error):
            store.load()

    def test_existing_checkpoint_or_receipt_targets_are_never_overwritten(self) -> None:
        store, plan = self.new_store()
        universe = synthetic_universe()
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "non-empty|overwrite"):
            IssuerCheckpointV2Store.create(
                store.root,
                plan=plan,
                issuer_universe=universe,
                project_root=ROOT,
                security_code="999001",
                owner_run_id="owner-2",
                created_at=START,
            )
        source = source_plan(plan)[0]
        begin_source(store, source, now=START)
        package = store.root / f"receipts/001-{source['source_id']}"
        package.mkdir(parents=True)
        (package / "manifest.json").write_bytes(b"existing")
        with self.assertRaises(IssuerCheckpointV2Error):
            state = store.load()
            store.complete_active_source(
                security_code="999001",
                source_ordinal=1,
                source_id=source["source_id"],  # type: ignore[arg-type]
                wave_ordinal=source["wave_ordinal"],  # type: ignore[arg-type]
                wave_id=source["wave_id"],  # type: ignore[arg-type]
                terminal_status="VERIFIED_ZERO",
                attempted_at=START,
                completed_at=START,
                raw_artifacts={"response.json": b"{}"},
                updated_at=START,
                **cas(state),  # type: ignore[arg-type]
            )
        self.assertEqual((package / "manifest.json").read_bytes(), b"existing")

    def test_wrong_missing_or_mismatched_hmac_key_fails_closed(self) -> None:
        store = self.sealed_copy()
        for key, key_id in (
            (b"", SEAL_KEY_ID),
            (b"wrong-key-material-that-is-at-least-32-bytes", SEAL_KEY_ID),
            (SEAL_KEY, "different-key-id"),
        ):
            with self.subTest(key_id=key_id), self.assertRaises(IssuerCheckpointV2Error):
                store.validate_terminal_seal(key=key, expected_key_id=key_id)

    def test_post_seal_journal_or_receipt_append_is_rejected_as_unlisted(self) -> None:
        store = self.sealed_copy()
        (store.root / "journal/99999999.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(IssuerCheckpointV2Error):
            store.validate_terminal_seal(key=SEAL_KEY, expected_key_id=SEAL_KEY_ID)

    def test_backdated_transition_is_rejected_before_staging(self) -> None:
        store, plan = self.new_store()
        first, second = source_plan(plan)[:2]
        begin_source(store, first, now=START + timedelta(seconds=1))
        complete_source(
            store, first, now=START + timedelta(seconds=2)
        )
        before = store.load()
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "time moved backwards"):
            begin_source(
                store,
                second,
                now=START + timedelta(seconds=1),
            )
        self.assertEqual(store.load(), before)
        self.assertEqual(list((store.root / ".staging").iterdir()), [])

    def test_source_receipt_times_are_bounded_by_start_and_terminal_journal(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        begin_source(store, source, now=START + timedelta(seconds=1))
        before = store.load()

        def complete(*, attempted: object, completed: object, updated: object) -> None:
            store.complete_active_source(
                security_code="999001",
                source_ordinal=1,
                source_id=source["source_id"],  # type: ignore[arg-type]
                wave_ordinal=source["wave_ordinal"],  # type: ignore[arg-type]
                wave_id=source["wave_id"],  # type: ignore[arg-type]
                terminal_status="VERIFIED_ZERO",
                attempted_at=attempted,  # type: ignore[arg-type]
                completed_at=completed,  # type: ignore[arg-type]
                raw_artifacts={"response.json": b"{}\n"},
                updated_at=updated,  # type: ignore[arg-type]
                **cas(before),  # type: ignore[arg-type]
            )

        with self.assertRaisesRegex(IssuerCheckpointV2Error, "precedes the active"):
            complete(attempted=START, completed=START, updated=START + timedelta(seconds=1))
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "precedes source completed"):
            complete(
                attempted=START + timedelta(seconds=2),
                completed=START + timedelta(seconds=3),
                updated=START + timedelta(seconds=2),
            )
        self.assertEqual(store.load(), before)
        self.assertEqual(list((store.root / ".staging").iterdir()), [])

    def test_transaction_faults_recover_with_journal_as_last_commit_marker(self) -> None:
        for failing_link in (1, 2, 4):
            with self.subTest(failing_link=failing_link):
                child = self.directory / f"fault-{failing_link}"
                child.mkdir()
                universe = synthetic_universe()
                plan = compile_plan(child, universe)
                store = IssuerCheckpointV2Store.create(
                    child / "checkpoint",
                    plan=plan,
                    issuer_universe=universe,
                    project_root=ROOT,
                    security_code="999001",
                    owner_run_id="owner-1",
                    created_at=START,
                )
                source = source_plan(plan)[0]
                begin_source(store, source, now=START)
                original_link = checkpoint_module.os.link
                call_count = 0

                def injected_link(*args: object, **kwargs: object) -> None:
                    nonlocal call_count
                    call_count += 1
                    if call_count == failing_link:
                        raise OSError("injected durable-publish interruption")
                    original_link(*args, **kwargs)  # type: ignore[arg-type]

                with mock.patch.object(
                    checkpoint_module.os, "link", side_effect=injected_link
                ), self.assertRaisesRegex(
                    IssuerCheckpointV2Error, "publish was interrupted"
                ):
                    complete_source(store, source, now=START)
                self.assertFalse((store.root / "journal/00000003.json").exists())
                self.assertEqual(len(list((store.root / ".staging").iterdir())), 1)
                root = store.root
                store.close()
                reopened = IssuerCheckpointV2Store(root, project_root=ROOT)
                state = reopened.load()
                self.assertEqual(state["revision"], 3)
                self.assertEqual(state["terminal_receipt_count"], 1)
                self.assertTrue((root / "journal/00000003.json").is_file())
                self.assertEqual(list((root / ".staging").iterdir()), [])

    def test_pending_seal_recovery_requires_and_uses_the_hmac_key(self) -> None:
        store, plan = self.new_store()
        now = advance_sources(store, plan, 29)
        state = store.reconcile(
            reconciled_at=now + timedelta(seconds=1),
            **cas(store.load()),  # type: ignore[arg-type]
        )
        with mock.patch.object(
            checkpoint_module.os,
            "link",
            side_effect=OSError("injected seal publish interruption"),
        ), self.assertRaisesRegex(IssuerCheckpointV2Error, "publish was interrupted"):
            store.seal(
                key=SEAL_KEY,
                key_id=SEAL_KEY_ID,
                key_issuer_id="synthetic-test-suite",
                issued_at=now + timedelta(seconds=2),
                **cas(state),  # type: ignore[arg-type]
            )
        self.assertFalse((store.root / f"journal/{state['revision'] + 1:08d}.json").exists())
        self.assertEqual(len(list((store.root / ".staging").iterdir())), 1)
        with self.assertRaisesRegex(
            IssuerCheckpointV2Error, "requires authenticated HMAC key"
        ):
            store.load()
        with self.assertRaisesRegex(
            IssuerCheckpointV2Error, "authentication failed"
        ):
            store.validate_terminal_seal(
                key=b"wrong-key-material-that-is-at-least-32-bytes",
                expected_key_id=SEAL_KEY_ID,
            )
        report = store.validate_terminal_seal(
            key=SEAL_KEY, expected_key_id=SEAL_KEY_ID
        )
        self.assertEqual(report["terminal_receipt_count"], 29)
        self.assertEqual(list((store.root / ".staging").iterdir()), [])

    def test_tampered_pending_seal_is_rejected_before_false_sealed_commit(self) -> None:
        target = self.directory / "reconciled-checkpoint"
        shutil.copytree(self.template, target)
        final_journal = sorted((target / "journal").glob("*.json"))[-1]
        final_journal.unlink()
        (target / "terminal-seal.json").unlink()
        store = IssuerCheckpointV2Store(target, project_root=ROOT)
        before = store.load()
        issued_at = datetime.fromisoformat(str(before["updated_at"])) + timedelta(
            seconds=1
        )
        with mock.patch.object(
            checkpoint_module.os,
            "link",
            side_effect=OSError("injected seal publish interruption"),
        ), self.assertRaisesRegex(IssuerCheckpointV2Error, "publish was interrupted"):
            store.seal(
                key=SEAL_KEY,
                key_id=SEAL_KEY_ID,
                key_issuer_id="synthetic-test-suite",
                issued_at=issued_at,
                **cas(before),  # type: ignore[arg-type]
            )
        stage = next((store.root / ".staging").iterdir())
        manifest_path = stage / "transaction.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        targets = {row["target"]: row for row in manifest["targets"]}
        journal_target = f"journal/{before['revision'] + 1:08d}.json"
        seal_path = stage / targets["terminal-seal.json"]["staged_name"]
        journal_path = stage / targets[journal_target]["staged_name"]
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
        seal["authentication"]["tag"] = "0" * 64
        seal_bytes = canonical_json_bytes(seal)
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["terminal_seal_sha256"] = sha256_bytes(seal_bytes)
        journal["checkpoint_digest"] = checkpoint_module._state_digest(journal)
        journal_bytes = canonical_json_bytes(journal)
        seal_path.write_bytes(seal_bytes)
        journal_path.write_bytes(journal_bytes)
        for target_name, content in (
            ("terminal-seal.json", seal_bytes),
            (journal_target, journal_bytes),
        ):
            targets[target_name]["sha256"] = sha256_bytes(content)
            targets[target_name]["size_bytes"] = len(content)
        manifest["resulting_checkpoint_digest"] = journal["checkpoint_digest"]
        manifest["transaction_sha256"] = hash_json(
            {
                key: value
                for key, value in manifest.items()
                if key != "transaction_sha256"
            }
        )
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        with self.assertRaisesRegex(
            IssuerCheckpointV2Error, "authentication failed"
        ):
            store.validate_terminal_seal(
                key=SEAL_KEY, expected_key_id=SEAL_KEY_ID
            )
        self.assertFalse((store.root / "terminal-seal.json").exists())
        self.assertFalse((store.root / journal_target).exists())
        self.assertTrue(stage.exists())

    def test_recovery_rejects_manifest_binding_rewrite(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        begin_source(store, source, now=START)
        with mock.patch.object(
            checkpoint_module.os,
            "link",
            side_effect=OSError("injected interruption before publish"),
        ), self.assertRaisesRegex(
            IssuerCheckpointV2Error, "publish was interrupted"
        ):
            complete_source(store, source, now=START)
        stage = next((store.root / ".staging").iterdir())
        manifest_path = stage / "transaction.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["checkpoint_id"] = "CHK2-SUBSTITUTED"
        manifest["transaction_sha256"] = hash_json(
            {
                key: value
                for key, value in manifest.items()
                if key != "transaction_sha256"
            }
        )
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        with self.assertRaisesRegex(
            IssuerCheckpointV2Error, "manifest differs from resulting state"
        ):
            store.load()

    def test_recovery_rejects_semantically_forged_reconciliation_before_publish(self) -> None:
        store, plan = self.new_store()
        now = advance_sources(store, plan, 29)
        before = store.load()
        with mock.patch.object(
            checkpoint_module.os,
            "link",
            side_effect=OSError("injected reconciliation publish interruption"),
        ), self.assertRaisesRegex(IssuerCheckpointV2Error, "publish was interrupted"):
            store.reconcile(
                reconciled_at=now + timedelta(seconds=1),
                **cas(before),  # type: ignore[arg-type]
            )
        stage = next((store.root / ".staging").iterdir())
        manifest_path = stage / "transaction.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        targets = {row["target"]: row for row in manifest["targets"]}
        reconciliation_path = stage / targets["reconciliation.json"]["staged_name"]
        journal_target = f"journal/{before['revision'] + 1:08d}.json"
        journal_path = stage / targets[journal_target]["staged_name"]
        reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
        reconciliation["terminal_source_count"] = 28
        reconciliation["reconciliation_sha256"] = checkpoint_module._reconciliation_digest(
            reconciliation
        )
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["reconciliation_sha256"] = reconciliation["reconciliation_sha256"]
        journal["checkpoint_digest"] = checkpoint_module._state_digest(journal)
        reconciliation_bytes = canonical_json_bytes(reconciliation)
        journal_bytes = canonical_json_bytes(journal)
        reconciliation_path.write_bytes(reconciliation_bytes)
        journal_path.write_bytes(journal_bytes)
        for target, content in (
            ("reconciliation.json", reconciliation_bytes),
            (journal_target, journal_bytes),
        ):
            targets[target]["sha256"] = sha256_bytes(content)
            targets[target]["size_bytes"] = len(content)
        manifest["resulting_checkpoint_digest"] = journal["checkpoint_digest"]
        manifest["transaction_sha256"] = hash_json(
            {
                key: value
                for key, value in manifest.items()
                if key != "transaction_sha256"
            }
        )
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        with self.assertRaisesRegex(
            IssuerCheckpointV2Error, "reconciliation binding is invalid"
        ):
            store.load()
        self.assertFalse((store.root / "reconciliation.json").exists())
        self.assertFalse((store.root / journal_target).exists())
        self.assertTrue(stage.exists())

    def test_unlisted_staged_byte_is_rejected_before_any_target_commit(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        begin_source(store, source, now=START)
        with mock.patch.object(
            checkpoint_module.os,
            "link",
            side_effect=OSError("injected interruption before publish"),
        ), self.assertRaises(IssuerCheckpointV2Error):
            complete_source(store, source, now=START)
        stage = next((store.root / ".staging").iterdir())
        (stage / "unlisted.bin").write_bytes(b"must never be committed")
        with self.assertRaisesRegex(
            IssuerCheckpointV2Error, "unlisted staged bytes"
        ):
            store.load()
        self.assertFalse((store.root / "journal/00000003.json").exists())
        self.assertFalse(
            any(
                path.is_file()
                for path in (store.root / "receipts").rglob("*")
            )
        )
        (stage / "unlisted.bin").unlink()
        self.assertEqual(store.load()["terminal_receipt_count"], 1)

    def test_listed_but_event_illegal_target_is_rejected_before_commit(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        begin_source(store, source, now=START)
        with mock.patch.object(
            checkpoint_module.os,
            "link",
            side_effect=OSError("injected interruption before publish"),
        ), self.assertRaises(IssuerCheckpointV2Error):
            complete_source(store, source, now=START)
        stage = next((store.root / ".staging").iterdir())
        manifest_path = stage / "transaction.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        commit = manifest["targets"].pop()
        old_commit = stage / commit["staged_name"]
        commit["staged_name"] = f"payload-{len(manifest['targets']) + 1:04d}.bin"
        old_commit.rename(stage / commit["staged_name"])
        evil_content = b"listed but forbidden by SOURCE_TERMINAL"
        evil_name = f"payload-{len(manifest['targets']):04d}.bin"
        (stage / evil_name).write_bytes(evil_content)
        manifest["targets"].append(
            {
                "staged_name": evil_name,
                "target": "evil.bin",
                "sha256": sha256_bytes(evil_content),
                "size_bytes": len(evil_content),
                "is_commit_marker": False,
            }
        )
        manifest["targets"].append(commit)
        manifest["transaction_sha256"] = hash_json(
            {
                key: value
                for key, value in manifest.items()
                if key != "transaction_sha256"
            }
        )
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "target set"):
            store.load()
        self.assertFalse((store.root / "evil.bin").exists())
        self.assertFalse((store.root / "journal/00000003.json").exists())

    def test_noncanonical_staged_journal_is_rejected_before_commit(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        begin_source(store, source, now=START)
        with mock.patch.object(
            checkpoint_module.os,
            "link",
            side_effect=OSError("injected interruption before publish"),
        ), self.assertRaises(IssuerCheckpointV2Error):
            complete_source(store, source, now=START)
        stage = next((store.root / ".staging").iterdir())
        manifest_path = stage / "transaction.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        commit = manifest["targets"][-1]
        commit_path = stage / commit["staged_name"]
        noncanonical = b" " + commit_path.read_bytes()
        commit_path.write_bytes(noncanonical)
        commit["sha256"] = sha256_bytes(noncanonical)
        commit["size_bytes"] = len(noncanonical)
        manifest["transaction_sha256"] = hash_json(
            {
                key: value
                for key, value in manifest.items()
                if key != "transaction_sha256"
            }
        )
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "not canonical JSON"):
            store.load()
        self.assertFalse((store.root / "journal/00000003.json").exists())

    def test_crash_after_link_before_directory_fsync_recovers_durably(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        begin_source(store, source, now=START)
        original_link = checkpoint_module.os.link
        original_fsync = checkpoint_module.os.fsync
        linked = False
        interrupted = False

        def tracking_link(*args: object, **kwargs: object) -> None:
            nonlocal linked
            original_link(*args, **kwargs)  # type: ignore[arg-type]
            linked = True

        def interrupting_fsync(descriptor: int) -> None:
            nonlocal interrupted
            if linked and not interrupted:
                interrupted = True
                raise OSError("injected crash before destination directory fsync")
            original_fsync(descriptor)

        with mock.patch.object(
            checkpoint_module.os, "link", side_effect=tracking_link
        ), mock.patch.object(
            checkpoint_module.os, "fsync", side_effect=interrupting_fsync
        ), self.assertRaisesRegex(
            IssuerCheckpointV2Error, "target fsync was interrupted"
        ):
            complete_source(store, source, now=START)
        self.assertTrue(linked)
        self.assertTrue(interrupted)
        self.assertFalse((store.root / "journal/00000003.json").exists())
        root = store.root
        store.close()
        reopened = IssuerCheckpointV2Store(root, project_root=ROOT)
        self.assertEqual(reopened.load()["terminal_receipt_count"], 1)
        self.assertEqual(list((root / ".staging").iterdir()), [])

    def test_injected_root_swap_during_commit_writes_nothing_to_replacement(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        moved = self.directory / "anchored-checkpoint"
        replacement = store.root
        original_rename = checkpoint_module.os.rename
        swapped = False

        def swapping_rename(*args: object, **kwargs: object) -> None:
            nonlocal swapped
            original_rename(*args, **kwargs)  # type: ignore[arg-type]
            if not swapped and kwargs.get("dst_dir_fd") is not None:
                swapped = True
                original_rename(replacement, moved)
                replacement.mkdir()

        with mock.patch.object(
            checkpoint_module.os, "rename", side_effect=swapping_rename
        ), self.assertRaisesRegex(IssuerCheckpointV2Error, "root identity changed"):
            begin_source(store, source, now=START)
        self.assertTrue(swapped)
        self.assertEqual(list(replacement.iterdir()), [])
        replacement.rmdir()
        original_rename(moved, replacement)
        state = store.load()
        self.assertEqual(state["active_source_ordinal"], 1)
        self.assertEqual(state["revision"], 2)

    def test_transient_root_path_swap_cannot_redirect_anchored_snapshot(self) -> None:
        store, _plan = self.new_store()
        expected = store.load()
        moved = self.directory / "snapshot-anchored-checkpoint"
        replacement = store.root
        original_snapshot = store._anchored_snapshot_once
        swapped = False

        def transient_swap() -> dict[str, bytes]:
            nonlocal swapped
            if swapped:
                return original_snapshot()
            swapped = True
            checkpoint_module.os.rename(replacement, moved)
            replacement.mkdir()
            marker = replacement / "attacker-replacement.bin"
            marker.write_bytes(b"must not be snapshotted")
            try:
                return original_snapshot()
            finally:
                marker.unlink()
                replacement.rmdir()
                checkpoint_module.os.rename(moved, replacement)

        with mock.patch.object(
            store, "_anchored_snapshot_once", side_effect=transient_swap
        ):
            self.assertEqual(store.load(), expected)
        self.assertTrue(swapped)

    def test_receipt_parent_swap_during_link_is_detected_and_recoverable(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        begin_source(store, source, now=START)
        package = store.root / f"receipts/001-{source['source_id']}"
        moved = self.directory / "moved-receipt-package"
        original_link = checkpoint_module.os.link
        swapped = False

        def swapping_parent_link(*args: object, **kwargs: object) -> None:
            nonlocal swapped
            original_link(*args, **kwargs)  # type: ignore[arg-type]
            if not swapped:
                swapped = True
                package.rename(moved)
                package.mkdir()

        with mock.patch.object(
            checkpoint_module.os, "link", side_effect=swapping_parent_link
        ), self.assertRaisesRegex(
            IssuerCheckpointV2Error, "target parent identity changed"
        ):
            complete_source(store, source, now=START)
        self.assertTrue(swapped)
        self.assertFalse((store.root / "journal/00000003.json").exists())
        self.assertEqual(list(moved.iterdir()), [])
        self.assertEqual(len(list((store.root / ".staging").iterdir())), 1)
        self.assertEqual(store.load()["terminal_receipt_count"], 1)
        self.assertEqual(list((store.root / ".staging").iterdir()), [])

    def test_staging_directory_swap_during_stage_rename_is_rescued(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        staging = store.root / ".staging"
        moved = self.directory / "detached-staging"
        original_rename = checkpoint_module.os.rename
        swapped = False

        def swapping_staging_rename(*args: object, **kwargs: object) -> None:
            nonlocal swapped
            destination = args[1] if len(args) > 1 else None
            if not swapped and destination == "00000002":
                swapped = True
                original_rename(staging, moved)
                staging.mkdir()
            original_rename(*args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(
            checkpoint_module.os, "rename", side_effect=swapping_staging_rename
        ):
            state = begin_source(store, source, now=START)
        self.assertTrue(swapped)
        self.assertEqual(state["revision"], 2)
        self.assertEqual(state["active_source_ordinal"], 1)
        self.assertEqual(store.load(), state)
        self.assertTrue((store.root / "journal/00000002.json").is_file())
        self.assertEqual(list(staging.iterdir()), [])
        self.assertEqual(list(moved.iterdir()), [])

    def test_staging_swap_at_recovery_boundary_consumes_open_descriptor(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        staging = store.root / ".staging"
        moved = self.directory / "recovery-boundary-staging"
        original_recover = store._recover_transactions
        swapped = False

        def swapping_recover(*args: object, **kwargs: object) -> None:
            nonlocal swapped
            if not swapped and (staging / "00000002").is_dir():
                swapped = True
                staging.rename(moved)
                staging.mkdir()
            original_recover(*args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(
            store, "_recover_transactions", side_effect=swapping_recover
        ):
            state = begin_source(store, source, now=START)
        self.assertTrue(swapped)
        self.assertEqual(state["revision"], 2)
        self.assertEqual(state["active_source_ordinal"], 1)
        self.assertEqual(store.load(), state)
        self.assertTrue((store.root / "journal/00000002.json").is_file())
        self.assertEqual(list(staging.iterdir()), [])
        self.assertEqual(list(moved.iterdir()), [])

    def test_uncommitted_cleanup_never_deletes_a_swapped_sibling_directory(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        parent = store.root.parent
        victim = parent / "victim-uncommitted"
        victim.mkdir()
        (victim / "user-data.txt").write_text("retain", encoding="utf-8")
        saved_original = parent / "saved-generated-stage"
        original_open = store._open_directory_descriptor
        swapped_path: Path | None = None

        def swapping_open(relative: str, *, create: bool) -> int:
            nonlocal swapped_path
            candidates = list(parent.glob(f".{store.root.name}.txn-*"))
            if relative == ".staging" and candidates and swapped_path is None:
                generated = candidates[0]
                generated.rename(saved_original)
                victim.rename(generated)
                swapped_path = generated
                raise IssuerCheckpointV2Error("injected uncommitted cleanup boundary")
            return original_open(relative, create=create)

        with mock.patch.object(
            store, "_open_directory_descriptor", side_effect=swapping_open
        ), self.assertRaisesRegex(
            IssuerCheckpointV2Error, "injected uncommitted cleanup boundary"
        ):
            begin_source(store, source, now=START)
        assert swapped_path is not None
        self.assertEqual(
            (swapped_path / "user-data.txt").read_text(encoding="utf-8"),
            "retain",
        )
        self.assertEqual(list(saved_original.iterdir()), [])
        self.assertEqual(store.load()["revision"], 1)

    def test_temp_path_swap_at_rename_is_evacuated_without_relocation(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        parent = store.root.parent
        victim = parent / "victim-at-rename"
        victim.mkdir()
        (victim / "user-data.txt").write_text("retain", encoding="utf-8")
        saved_original = parent / "saved-rename-stage"
        original_rename = checkpoint_module.os.rename
        swapped_path: Path | None = None

        def swapping_rename(*args: object, **kwargs: object) -> None:
            nonlocal swapped_path
            source_name = args[0] if args else None
            destination_name = args[1] if len(args) > 1 else None
            if (
                swapped_path is None
                and isinstance(source_name, str)
                and source_name.startswith(f".{store.root.name}.txn-")
                and destination_name == "00000002"
            ):
                generated = parent / source_name
                generated.rename(saved_original)
                victim.rename(generated)
                swapped_path = generated
            original_rename(*args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(
            checkpoint_module.os, "rename", side_effect=swapping_rename
        ), self.assertRaisesRegex(
            IssuerCheckpointV2Error, "changed during rename"
        ):
            begin_source(store, source, now=START)
        assert swapped_path is not None
        self.assertEqual(
            (swapped_path / "user-data.txt").read_text(encoding="utf-8"),
            "retain",
        )
        self.assertEqual(list(saved_original.iterdir()), [])
        self.assertEqual(list((store.root / ".staging").iterdir()), [])
        self.assertEqual(store.load()["revision"], 1)

    def test_committed_cleanup_never_deletes_a_swapped_sibling_directory(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        parent = store.root.parent
        victim = parent / "victim-committed"
        victim.mkdir()
        (victim / "user-data.txt").write_text("retain", encoding="utf-8")
        saved_original = parent / "saved-committed-stage"
        original_stat = checkpoint_module.os.stat
        swapped_path: Path | None = None

        def swapping_stat(path: object, *args: object, **kwargs: object) -> object:
            nonlocal swapped_path
            if (
                swapped_path is None
                and isinstance(path, str)
                and ".committed-" in path
                and kwargs.get("dir_fd") is not None
            ):
                cleanup = parent / path
                cleanup.rename(saved_original)
                victim.rename(cleanup)
                swapped_path = cleanup
            return original_stat(path, *args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(
            checkpoint_module.os, "stat", side_effect=swapping_stat
        ), self.assertRaisesRegex(
            IssuerCheckpointV2Error, "changed during retirement"
        ):
            begin_source(store, source, now=START)
        assert swapped_path is not None
        self.assertEqual(
            (store.root / ".staging/00000002/user-data.txt").read_text(
                encoding="utf-8"
            ),
            "retain",
        )
        self.assertTrue((saved_original / "transaction.json").is_file())
        self.assertFalse(
            any(
                path.name.startswith(f".{store.root.name}.committed-")
                for path in self.directory.iterdir()
            )
        )
        self.assertTrue((store.root / "journal/00000002.json").is_file())

    def test_committed_stage_swap_before_retirement_is_not_relocated(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        staging = store.root / ".staging"
        victim = self.directory / "victim-before-retirement"
        victim.mkdir()
        (victim / "user-data.txt").write_text("retain", encoding="utf-8")
        saved_original = self.directory / "saved-real-committed-stage"
        original_retire = store._retire_committed_stage
        swapped = False

        def swapping_retire(*args: object, **kwargs: object) -> None:
            nonlocal swapped
            if not swapped:
                swapped = True
                stage_name = str(kwargs["stage_name"])
                (staging / stage_name).rename(saved_original)
                victim.rename(staging / stage_name)
            original_retire(*args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(
            store, "_retire_committed_stage", side_effect=swapping_retire
        ), self.assertRaisesRegex(
            IssuerCheckpointV2Error, "identity changed before retirement"
        ):
            begin_source(store, source, now=START)
        self.assertTrue(swapped)
        self.assertEqual(
            (staging / "00000002" / "user-data.txt").read_text(encoding="utf-8"),
            "retain",
        )
        self.assertFalse(
            any(path.name.startswith(f".{store.root.name}.committed-") for path in self.directory.iterdir())
        )
        self.assertTrue((saved_original / "transaction.json").is_file())

    def test_guard_inode_swap_during_mutation_is_detected(self) -> None:
        store, plan = self.new_store()
        source = source_plan(plan)[0]
        state = store.load()
        original_load = store._load
        swapped = False

        def swapping_load() -> object:
            nonlocal swapped
            result = original_load()
            if not swapped:
                swapped = True
                guard = store.root / ".checkpoint-v2.guard"
                guard.unlink()
                guard.write_bytes(b"")
            return result

        with mock.patch.object(
            store, "_load", side_effect=swapping_load
        ), self.assertRaisesRegex(IssuerCheckpointV2Error, "guard"):
            store.begin_next_source(
                security_code="999001",
                source_ordinal=1,
                source_id=source["source_id"],  # type: ignore[arg-type]
                wave_ordinal=source["wave_ordinal"],  # type: ignore[arg-type]
                wave_id=source["wave_id"],  # type: ignore[arg-type]
                updated_at=START,
                **cas(state),  # type: ignore[arg-type]
            )
        self.assertTrue(swapped)
        # The create-exclusive journal protocol remains coherent even though
        # the caller is told that lock ownership was compromised.
        self.assertEqual(store.load()["active_source_ordinal"], 1)

    def test_preempted_owner_fence_cannot_write_after_resume(self) -> None:
        store, plan = self.new_store()
        created = store.load()
        preempted = store.preempt(updated_at=START, **cas(created))  # type: ignore[arg-type]
        resumed = store.resume(
            new_owner_run_id="owner-2", updated_at=START, **cas(preempted)  # type: ignore[arg-type]
        )
        source = source_plan(plan)[0]
        stale_cas = cas(resumed)
        stale_cas["expected_fencing_token"] = preempted["fencing_token"]
        with self.assertRaises(IssuerCheckpointV2FencingError):
            store.begin_next_source(
                security_code="999001",
                source_ordinal=1,
                source_id=source["source_id"],  # type: ignore[arg-type]
                wave_ordinal=source["wave_ordinal"],  # type: ignore[arg-type]
                wave_id=source["wave_id"],  # type: ignore[arg-type]
                updated_at=START,
                **stale_cas,  # type: ignore[arg-type]
            )
        self.assertEqual(store.load(), resumed)

    def test_raw_budgets_fail_before_any_receipt_write(self) -> None:
        cases = (
            (
                {"a": b"1", "b": b"2", "c": b"3"},
                {"MAX_RAW_FILES_PER_SOURCE": 2},
                "count exceeds",
            ),
            (
                {"a": b"1234"},
                {"MAX_RAW_FILE_BYTES": 3},
                "artifact exceeds",
            ),
            (
                {"a": b"12", "b": b"34"},
                {"MAX_RAW_BYTES_PER_SOURCE": 3},
                "total exceeds",
            ),
        )
        for index, (artifacts, limits, message) in enumerate(cases):
            with self.subTest(message=message):
                child = self.directory / f"budget-{index}"
                child.mkdir()
                universe = synthetic_universe()
                plan = compile_plan(child, universe)
                store = IssuerCheckpointV2Store.create(
                    child / "checkpoint",
                    plan=plan,
                    issuer_universe=universe,
                    project_root=ROOT,
                    security_code="999001",
                    owner_run_id="owner-1",
                    created_at=START,
                )
                source = source_plan(plan)[0]
                begin_source(store, source, now=START)
                before = store.load()
                with mock.patch.multiple(checkpoint_module, **limits), self.assertRaisesRegex(
                    IssuerCheckpointV2Error, message
                ):
                    complete_source(
                        store, source, now=START, raw_artifacts=artifacts
                    )
                self.assertEqual(store.load(), before)
                self.assertFalse((store.root / "receipts").exists())
                self.assertEqual(list((store.root / ".staging").iterdir()), [])

    def test_begin_after_all_29_receipts_has_explicit_domain_error(self) -> None:
        store, plan = self.new_store()
        advance_sources(store, plan, 29)
        state = store.load()
        with self.assertRaisesRegex(IssuerCheckpointV2Error, "all 29"):
            store.begin_next_source(
                security_code="999001",
                source_ordinal=30,
                source_id="not_a_source",
                wave_ordinal=7,
                wave_id="DISCOVERY_AND_SENTIMENT_ONLY",
                updated_at=START,
                **cas(state),  # type: ignore[arg-type]
            )

    def test_aggregate_raw_budgets_are_checked_before_second_receipt_write(self) -> None:
        for limit_name, limit_value, message in (
            ("MAX_CHECKPOINT_RAW_FILES", 1, "count budget"),
            ("MAX_CHECKPOINT_RAW_BYTES", 3, "byte budget"),
        ):
            with self.subTest(limit=limit_name):
                child = self.directory / limit_name.lower()
                child.mkdir()
                universe = synthetic_universe()
                plan = compile_plan(child, universe)
                store = IssuerCheckpointV2Store.create(
                    child / "checkpoint",
                    plan=plan,
                    issuer_universe=universe,
                    project_root=ROOT,
                    security_code="999001",
                    owner_run_id="owner-1",
                    created_at=START,
                )
                first, second = source_plan(plan)[:2]
                begin_source(store, first, now=START)
                complete_source(
                    store, first, now=START, raw_artifacts={"first": b"12"}
                )
                begin_source(store, second, now=START)
                before = store.load()
                with mock.patch.object(
                    checkpoint_module, limit_name, limit_value
                ), self.assertRaisesRegex(IssuerCheckpointV2Error, message):
                    complete_source(
                        store,
                        second,
                        now=START,
                        raw_artifacts={"second": b"34"},
                    )
                self.assertEqual(store.load(), before)
                self.assertFalse(
                    (store.root / f"receipts/002-{second['source_id']}").exists()
                )

    def test_final_journal_rehash_cannot_escape_authenticated_seal_time(self) -> None:
        store = self.sealed_copy()
        state = store.load()
        final_path = store.root / f"journal/{state['revision']:08d}.json"
        final_state = json.loads(final_path.read_text(encoding="utf-8"))
        final_state["updated_at"] = "2026-08-27T23:59:59Z"
        final_state["checkpoint_digest"] = ""
        final_state["checkpoint_digest"] = checkpoint_module._state_digest(final_state)
        final_path.write_bytes(canonical_json_bytes(final_state))
        with self.assertRaisesRegex(
            IssuerCheckpointV2Error, "authenticated seal derivation"
        ):
            store.validate_terminal_seal(
                key=SEAL_KEY, expected_key_id=SEAL_KEY_ID
            )

    def test_claim_boundaries_are_immutable_and_each_document_gets_a_fresh_copy(self) -> None:
        with self.assertRaises(TypeError):
            CLAIM_BOUNDARIES["terminal_seal_proves_market_completeness"] = True  # type: ignore[index]
        store, _plan = self.new_store()
        state = store.load()
        state["claim_boundaries"]["terminal_seal_proves_market_completeness"] = True  # type: ignore[index]
        self.assertFalse(
            store.load()["claim_boundaries"]["terminal_seal_proves_market_completeness"]  # type: ignore[index]
        )


if __name__ == "__main__":
    unittest.main()
