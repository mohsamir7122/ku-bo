from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
except ModuleNotFoundError:  # pragma: no cover - the CI test extra provides it.
    Draft202012Validator = None  # type: ignore[assignment,misc]
    FormatChecker = None  # type: ignore[assignment,misc]
    Registry = None  # type: ignore[assignment,misc]
    Resource = None  # type: ignore[assignment,misc]

from kubo.issuer_checkpoint_v2 import (
    EXPECTED_SOURCE_COUNT,
    EXPECTED_WAVE_COUNT,
    IssuerCheckpointV2CasError,
    IssuerCheckpointV2Error,
    IssuerCheckpointV2FencingError,
    IssuerCheckpointV2Store,
)
from kubo.issuer_sequential_collection import (
    SOURCE_WAVE_IDS,
    SOURCE_WAVE_SOURCES,
    compile_issuer_sequential_collection_plan,
)


ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
SEAL_KEY = b"issuer-checkpoint-v2-test-only-key-material"
SEAL_KEY_ID = "issuer-checkpoint-v2-test-key"


def synthetic_universe() -> dict[str, object]:
    return json.loads(
        (ROOT / "examples/synthetic_issuer_universe.json").read_text(encoding="utf-8")
    )


def two_security_universe() -> dict[str, object]:
    payload = synthetic_universe()
    second = copy.deepcopy(payload["issuers"][0])  # type: ignore[index]
    second["issuer_id"] = "SYNTHETIC-ISSUER-2"
    second["official_registration_id"] = "SYNTHETIC-REGISTRATION-2"
    second["legal_name_ar"] = "شركة اصطناعية ثانية"
    second["legal_name_en"] = "Second Synthetic Company"
    second["security_identities"][0].update(  # type: ignore[index]
        {"security_code": "999002", "ticker": "SYN2", "isin": "KW0EQ9990028"}
    )
    payload["issuers"].append(second)  # type: ignore[union-attr]
    payload["expected_security_codes"].append("999002")  # type: ignore[union-attr]
    return payload


def compile_plan(directory: Path, universe: dict[str, object]) -> dict[str, object]:
    authority = directory / "issuer-universe-authority.json"
    authority.write_text(json.dumps(universe, ensure_ascii=False), encoding="utf-8")
    return compile_issuer_sequential_collection_plan(
        ROOT,
        authority,
        run_id="issuer-checkpoint-v2-test",
        generated_at="2026-08-27T13:00:00+03:00",
    )


def cas(state: dict[str, object]) -> dict[str, object]:
    return {
        "expected_generation": state["generation"],
        "expected_revision": state["revision"],
        "expected_fencing_token": state["fencing_token"],
        "expected_owner_run_id": state["owner_run_id"],
        "expected_prior_checkpoint_digest": state["checkpoint_digest"],
    }


def source_plan(plan: dict[str, object], security_code: str = "999001") -> list[dict[str, object]]:
    row = next(
        item for item in plan["queue"] if item["security_code"] == security_code  # type: ignore[index,union-attr]
    )
    return row["source_plan"]  # type: ignore[return-value]


def begin_source(
    store: IssuerCheckpointV2Store,
    source: dict[str, object],
    *,
    now: datetime,
    security_code: str = "999001",
) -> dict[str, object]:
    state = store.load()
    return store.begin_next_source(
        security_code=security_code,
        source_ordinal=source["source_ordinal"],  # type: ignore[arg-type]
        source_id=source["source_id"],  # type: ignore[arg-type]
        wave_ordinal=source["wave_ordinal"],  # type: ignore[arg-type]
        wave_id=source["wave_id"],  # type: ignore[arg-type]
        updated_at=now,
        **cas(state),  # type: ignore[arg-type]
    )


def complete_source(
    store: IssuerCheckpointV2Store,
    source: dict[str, object],
    *,
    now: datetime,
    security_code: str = "999001",
    terminal_status: str = "VERIFIED_ZERO",
    raw_artifacts: dict[str, bytes] | None = None,
) -> dict[str, object]:
    state = store.load()
    if raw_artifacts is None:
        raw_artifacts = {"response.json": b'{"items":[]}\n'}
    return store.complete_active_source(
        security_code=security_code,
        source_ordinal=source["source_ordinal"],  # type: ignore[arg-type]
        source_id=source["source_id"],  # type: ignore[arg-type]
        wave_ordinal=source["wave_ordinal"],  # type: ignore[arg-type]
        wave_id=source["wave_id"],  # type: ignore[arg-type]
        terminal_status=terminal_status,
        attempted_at=now,
        completed_at=now,
        raw_artifacts=raw_artifacts,
        updated_at=now,
        **cas(state),  # type: ignore[arg-type]
    )


def advance_sources(
    store: IssuerCheckpointV2Store,
    plan: dict[str, object],
    count: int,
    *,
    now: datetime = START,
    security_code: str = "999001",
) -> datetime:
    for source in source_plan(plan, security_code)[:count]:
        now += timedelta(seconds=1)
        begin_source(store, source, now=now, security_code=security_code)
        now += timedelta(seconds=1)
        complete_source(store, source, now=now, security_code=security_code)
    return now


def seal_full_fixture(
    directory: Path,
    *,
    universe: dict[str, object] | None = None,
) -> tuple[IssuerCheckpointV2Store, dict[str, object], dict[str, object]]:
    authority = universe or synthetic_universe()
    plan = compile_plan(directory, authority)
    store = IssuerCheckpointV2Store.create(
        directory / "checkpoint",
        plan=plan,
        issuer_universe=authority,
        project_root=ROOT,
        security_code="999001",
        owner_run_id="owner-1",
        created_at=START,
    )
    now = advance_sources(store, plan, EXPECTED_SOURCE_COUNT)
    state = store.load()
    now += timedelta(seconds=1)
    state = store.reconcile(reconciled_at=now, **cas(state))  # type: ignore[arg-type]
    now += timedelta(seconds=1)
    report = store.seal(
        key=SEAL_KEY,
        key_id=SEAL_KEY_ID,
        key_issuer_id="synthetic-test-suite",
        issued_at=now,
        **cas(state),  # type: ignore[arg-type]
    )
    return store, plan, report


class IssuerCheckpointV2Tests(unittest.TestCase):
    def create_store(
        self,
        directory: Path,
        *,
        universe: dict[str, object] | None = None,
        security_code: str = "999001",
    ) -> tuple[IssuerCheckpointV2Store, dict[str, object], dict[str, object]]:
        authority = universe or synthetic_universe()
        plan = compile_plan(directory, authority)
        store = IssuerCheckpointV2Store.create(
            directory / "checkpoint",
            plan=plan,
            issuer_universe=authority,
            project_root=ROOT,
            security_code=security_code,
            owner_run_id="owner-1",
            created_at=START,
        )
        return store, plan, authority

    def test_create_binds_exact_one_security_and_frozen_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, plan, _ = self.create_store(Path(temp))
            state = store.load()
            self.assertEqual(state["security_code"], "999001")
            self.assertEqual(state["expected_source_count"], 29)
            self.assertEqual(state["expected_wave_count"], 7)
            self.assertEqual(
                [len(wave) for wave in SOURCE_WAVE_SOURCES], [2, 1, 3, 3, 7, 8, 5]
            )
            self.assertEqual(len(source_plan(plan)), 29)

    def test_non_numeric_or_multi_value_selection_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            universe = synthetic_universe()
            plan = compile_plan(directory, universe)
            for invalid in ("SYN1", "999001,999002", ["999001"]):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(
                    IssuerCheckpointV2Error, "exactly one numeric"
                ):
                    IssuerCheckpointV2Store.create(
                        directory / f"checkpoint-{len(str(invalid))}",
                        plan=plan,
                        issuer_universe=universe,
                        project_root=ROOT,
                        security_code=invalid,  # type: ignore[arg-type]
                        owner_run_id="owner-1",
                        created_at=START,
                    )

    def test_created_at_cannot_precede_the_bound_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            universe = synthetic_universe()
            plan = compile_plan(directory, universe)
            with self.assertRaisesRegex(
                IssuerCheckpointV2Error, "precedes the bound plan"
            ):
                IssuerCheckpointV2Store.create(
                    directory / "checkpoint",
                    plan=plan,
                    issuer_universe=universe,
                    project_root=ROOT,
                    security_code="999001",
                    owner_run_id="owner-1",
                    created_at=START - timedelta(seconds=1),
                )

    def test_only_next_exact_source_and_one_active_source_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, plan, _ = self.create_store(Path(temp))
            first, second = source_plan(plan)[:2]
            state = store.load()
            with self.assertRaisesRegex(IssuerCheckpointV2Error, "next expected"):
                store.begin_next_source(
                    security_code="999001",
                    source_ordinal=2,
                    source_id=second["source_id"],  # type: ignore[arg-type]
                    wave_ordinal=second["wave_ordinal"],  # type: ignore[arg-type]
                    wave_id=second["wave_id"],  # type: ignore[arg-type]
                    updated_at=START + timedelta(seconds=1),
                    **cas(state),  # type: ignore[arg-type]
                )
            running = begin_source(store, first, now=START + timedelta(seconds=2))
            with self.assertRaisesRegex(IssuerCheckpointV2Error, "another active"):
                store.begin_next_source(
                    security_code="999001",
                    source_ordinal=2,
                    source_id=second["source_id"],  # type: ignore[arg-type]
                    wave_ordinal=second["wave_ordinal"],  # type: ignore[arg-type]
                    wave_id=second["wave_id"],  # type: ignore[arg-type]
                    updated_at=START + timedelta(seconds=3),
                    **cas(running),  # type: ignore[arg-type]
                )

    def test_source_local_block_is_terminal_and_does_not_abort_next_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, plan, _ = self.create_store(Path(temp))
            first, second = source_plan(plan)[:2]
            begin_source(store, first, now=START + timedelta(seconds=1))
            completed = complete_source(
                store,
                first,
                now=START + timedelta(seconds=2),
                terminal_status="BLOCKED_ACCESS",
                raw_artifacts={},
            )
            self.assertEqual(completed["terminal_receipt_count"], 1)
            next_state = begin_source(store, second, now=START + timedelta(seconds=3))
            self.assertEqual(next_state["active_source_ordinal"], 2)

    def test_preempt_resume_preserves_receipts_and_rotates_generation_fence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, plan, _ = self.create_store(Path(temp))
            now = advance_sources(store, plan, 2)
            state = store.load()
            terminal_digests = list(state["terminal_receipt_sha256s"])
            preempted = store.preempt(
                updated_at=now + timedelta(seconds=1),
                **cas(state),  # type: ignore[arg-type]
            )
            resumed = store.resume(
                new_owner_run_id="owner-2",
                updated_at=now + timedelta(seconds=2),
                **cas(preempted),  # type: ignore[arg-type]
            )
            self.assertEqual(resumed["generation"], 2)
            self.assertEqual(resumed["owner_run_id"], "owner-2")
            self.assertNotEqual(resumed["fencing_token"], state["fencing_token"])
            self.assertEqual(resumed["terminal_receipt_sha256s"], terminal_digests)
            self.assertEqual(resumed["next_source_ordinal"], 3)

    def test_all_five_cas_dimensions_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, plan, _ = self.create_store(Path(temp))
            source = source_plan(plan)[0]
            state = store.load()
            cases = {
                "expected_generation": (2, IssuerCheckpointV2CasError),
                "expected_revision": (2, IssuerCheckpointV2CasError),
                "expected_owner_run_id": ("stale-owner", IssuerCheckpointV2CasError),
                "expected_prior_checkpoint_digest": ("f" * 64, IssuerCheckpointV2CasError),
                "expected_fencing_token": ("f" * 64, IssuerCheckpointV2FencingError),
            }
            for field, (replacement, error) in cases.items():
                kwargs = cas(state)
                kwargs[field] = replacement
                with self.subTest(field=field), self.assertRaises(error):
                    store.begin_next_source(
                        security_code="999001",
                        source_ordinal=1,
                        source_id=source["source_id"],  # type: ignore[arg-type]
                        wave_ordinal=source["wave_ordinal"],  # type: ignore[arg-type]
                        wave_id=source["wave_id"],  # type: ignore[arg-type]
                        updated_at=START + timedelta(seconds=1),
                        **kwargs,  # type: ignore[arg-type]
                    )

    def test_reconciliation_at_28_and_early_sealing_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, plan, _ = self.create_store(Path(temp))
            now = advance_sources(store, plan, 28)
            state = store.load()
            with self.assertRaisesRegex(IssuerCheckpointV2Error, "all 29"):
                store.reconcile(reconciled_at=now + timedelta(seconds=1), **cas(state))  # type: ignore[arg-type]
            with self.assertRaisesRegex(IssuerCheckpointV2Error, "exact 29"):
                store.seal(
                    key=SEAL_KEY,
                    key_id=SEAL_KEY_ID,
                    key_issuer_id="synthetic-test-suite",
                    issued_at=now + timedelta(seconds=2),
                    **cas(state),  # type: ignore[arg-type]
                )

    def test_generated_fixture_reconciles_29_receipts_and_authenticates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store, _plan, report = seal_full_fixture(Path(temp))
            self.assertEqual(report["terminal_receipt_count"], 29)
            self.assertEqual(report["wave_count"], 7)
            reopened = store.validate_terminal_seal(
                key=SEAL_KEY, expected_key_id=SEAL_KEY_ID
            )
            self.assertEqual(
                reopened["status"], "PASS_SYNTHETIC_ONE_SECURITY_TERMINAL_SEAL"
            )
            self.assertFalse(any(reopened["claim_boundaries"].values()))

    @unittest.skipUnless(Draft202012Validator is not None, "jsonschema unavailable")
    def test_generated_documents_validate_against_v2_schemas(self) -> None:
        assert Draft202012Validator is not None
        assert FormatChecker is not None
        with tempfile.TemporaryDirectory() as temp:
            store, plan, _report = seal_full_fixture(Path(temp))
            bundle = store.root
            documents = (
                ("issuer-checkpoint-v2.schema.json", bundle / "journal/00000001.json"),
                (
                    "issuer-checkpoint-journal-entry-v2.schema.json",
                    bundle / "journal/00000001.json",
                ),
                (
                    "issuer-checkpoint-source-receipt-v2.schema.json",
                    bundle / f"receipts/001-{source_plan(plan)[0]['source_id']}/receipt.json",
                ),
                (
                    "issuer-checkpoint-source-manifest-v2.schema.json",
                    bundle / f"receipts/001-{source_plan(plan)[0]['source_id']}/manifest.json",
                ),
                ("issuer-checkpoint-reconciliation-v2.schema.json", bundle / "reconciliation.json"),
                ("issuer-checkpoint-terminal-seal-v2.schema.json", bundle / "terminal-seal.json"),
            )
            schemas = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in (ROOT / "schemas").glob("*.schema.json")
            ]
            assert Registry is not None
            assert Resource is not None
            registry = Registry().with_resources(
                [
                    (schema["$id"], Resource.from_contents(schema))
                    for schema in schemas
                    if "$id" in schema
                ]
            )
            for schema_name, document_path in documents:
                schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
                document = json.loads(document_path.read_text(encoding="utf-8"))
                with self.subTest(schema=schema_name):
                    Draft202012Validator(
                        schema,
                        registry=registry,
                        format_checker=FormatChecker(),
                    ).validate(document)

            state_schema = json.loads(
                (ROOT / "schemas/issuer-checkpoint-v2.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            false_sealed = json.loads(
                (bundle / "journal/00000001.json").read_text(encoding="utf-8")
            )
            false_sealed["event_type"] = "SEALED"
            state_validator = Draft202012Validator(
                state_schema,
                registry=registry,
                format_checker=FormatChecker(),
            )
            self.assertTrue(list(state_validator.iter_errors(false_sealed)))

            reconciliation_schema = json.loads(
                (
                    ROOT
                    / "schemas/issuer-checkpoint-reconciliation-v2.schema.json"
                ).read_text(encoding="utf-8")
            )
            forged_reconciliation = json.loads(
                (bundle / "reconciliation.json").read_text(encoding="utf-8")
            )
            for item in forged_reconciliation["receipt_inventory"]:
                item["source_ordinal"] = 1
            forged_reconciliation["wave_reconciliation"][0][
                "terminal_source_ordinals"
            ] = [1]
            reconciliation_validator = Draft202012Validator(
                reconciliation_schema,
                registry=registry,
                format_checker=FormatChecker(),
            )
            self.assertTrue(
                list(reconciliation_validator.iter_errors(forged_reconciliation))
            )

            seal_schema = json.loads(
                (
                    ROOT / "schemas/issuer-checkpoint-terminal-seal-v2.schema.json"
                ).read_text(encoding="utf-8")
            )
            seal_document = json.loads(
                (bundle / "terminal-seal.json").read_text(encoding="utf-8")
            )
            seal_validator = Draft202012Validator(
                seal_schema,
                registry=registry,
                format_checker=FormatChecker(),
            )
            for invalid_path in (
                "CON",
                "nested/Lpt1.txt",
                "trailing./file.json",
                "nested/trailing.",
            ):
                mutated = copy.deepcopy(seal_document)
                mutated["bundle_inventory"][0]["path"] = invalid_path
                with self.subTest(seal_inventory_path=invalid_path):
                    self.assertTrue(list(seal_validator.iter_errors(mutated)))

            manifest_schema = json.loads(
                (
                    ROOT / "schemas/issuer-checkpoint-source-manifest-v2.schema.json"
                ).read_text(encoding="utf-8")
            )
            manifest_document = json.loads(
                (
                    bundle
                    / f"receipts/001-{source_plan(plan)[0]['source_id']}/manifest.json"
                ).read_text(encoding="utf-8")
            )
            manifest_validator = Draft202012Validator(
                manifest_schema,
                registry=registry,
                format_checker=FormatChecker(),
            )
            for invalid_path in (
                "raw/CON",
                "raw/nested/Lpt1.txt",
                "raw/trailing./file.json",
                "raw/nested/trailing.",
            ):
                mutated = copy.deepcopy(manifest_document)
                mutated["artifacts"][0]["path"] = invalid_path
                with self.subTest(manifest_artifact_path=invalid_path):
                    self.assertTrue(list(manifest_validator.iter_errors(mutated)))

    def test_later_security_requires_authenticated_immediate_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            universe = two_security_universe()
            plan = compile_plan(directory, universe)
            with self.assertRaisesRegex(IssuerCheckpointV2Error, "prior security terminal seal"):
                IssuerCheckpointV2Store.create(
                    directory / "second-checkpoint",
                    plan=plan,
                    issuer_universe=universe,
                    project_root=ROOT,
                    security_code="999002",
                    owner_run_id="owner-2",
                    created_at=START,
                )

    def test_authenticated_predecessor_digest_survives_restart_and_seal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            universe = two_security_universe()
            (directory / "first").mkdir()
            first, plan, first_report = seal_full_fixture(
                directory / "first", universe=universe
            )
            predecessor_issued_at = datetime.fromisoformat(
                str(first_report["issued_at"])
            )
            with self.assertRaisesRegex(
                IssuerCheckpointV2Error, "precedes the authenticated predecessor"
            ):
                IssuerCheckpointV2Store.create(
                    directory / "second-checkpoint-too-early",
                    plan=plan,
                    issuer_universe=universe,
                    project_root=ROOT,
                    security_code="999002",
                    owner_run_id="owner-2",
                    created_at=START,
                    prior_checkpoint_root=first.root,
                    prior_hmac_key=SEAL_KEY,
                    prior_expected_key_id=SEAL_KEY_ID,
                )
            second = IssuerCheckpointV2Store.create(
                directory / "second-checkpoint",
                plan=plan,
                issuer_universe=universe,
                project_root=ROOT,
                security_code="999002",
                owner_run_id="owner-2",
                created_at=predecessor_issued_at,
                prior_checkpoint_root=first.root,
                prior_hmac_key=SEAL_KEY,
                prior_expected_key_id=SEAL_KEY_ID,
            )
            predecessor_sha256 = first_report["terminal_seal_sha256"]
            self.assertEqual(
                second.load()["previous_security_terminal_seal_sha256"],
                predecessor_sha256,
            )
            second_root = second.root
            second.close()
            reopened = IssuerCheckpointV2Store(second_root, project_root=ROOT)
            self.assertEqual(
                reopened.load()["previous_security_terminal_seal_sha256"],
                predecessor_sha256,
            )
            now = advance_sources(
                reopened,
                plan,
                EXPECTED_SOURCE_COUNT,
                now=predecessor_issued_at,
                security_code="999002",
            )
            state = reopened.reconcile(
                reconciled_at=now + timedelta(seconds=1),
                **cas(reopened.load()),  # type: ignore[arg-type]
            )
            with self.assertRaisesRegex(
                IssuerCheckpointV2Error, "predecessor differs"
            ):
                reopened.seal(
                    key=SEAL_KEY,
                    key_id=SEAL_KEY_ID,
                    key_issuer_id="synthetic-test-suite",
                    issued_at=now + timedelta(seconds=2),
                    previous_security_terminal_seal_sha256="f" * 64,
                    **cas(state),  # type: ignore[arg-type]
                )
            second_report = reopened.seal(
                key=SEAL_KEY,
                key_id=SEAL_KEY_ID,
                key_issuer_id="synthetic-test-suite",
                issued_at=now + timedelta(seconds=2),
                **cas(state),  # type: ignore[arg-type]
            )
            self.assertEqual(
                second_report["previous_security_terminal_seal_sha256"],
                predecessor_sha256,
            )


if __name__ == "__main__":
    unittest.main()
