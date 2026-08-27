from __future__ import annotations

import copy
from contextlib import redirect_stdout
from datetime import datetime, timedelta
import hashlib
import hmac
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ModuleNotFoundError:  # The CI test extra installs jsonschema.
    Draft202012Validator = None  # type: ignore[assignment,misc]
    FormatChecker = None  # type: ignore[assignment,misc]

from kubo.cli_v3 import main as cli_main
from kubo.hashing import hash_json
from kubo.issuer_sequential_collection import (
    IssuerSequentialCollectionError,
    compile_issuer_sequential_collection_plan,
    execute_issuer_sequential_collection_plan as _execute_plan,
    validate_issuer_sequential_collection_plan as _validate_plan,
    validate_issuer_sequential_collection_policy,
    validate_issuer_sequential_collection_run as _validate_run,
    write_issuer_sequential_collection_run as _write_run,
)
from kubo.runtime_trust import (
    RuntimeTrustRegistry,
    canonical_registry_bytes,
    verify_runtime_trust_registry,
)


ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = "2026-08-27T13:00:00+03:00"
OBSERVED_AT = "2026-08-27T14:00:00+03:00"
ARTIFACT_MANIFEST_SHA256 = "a" * 64
UNIVERSE_AUTHORITIES: dict[str, dict[str, object]] = {}


def universe() -> dict[str, object]:
    return json.loads(
        (ROOT / "examples" / "synthetic_issuer_universe.json").read_text(encoding="utf-8")
    )


def write_universe(directory: Path, payload: dict[str, object]) -> Path:
    target = directory / "issuer-universe.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


def compile_plan(directory: Path, payload: dict[str, object]) -> dict[str, object]:
    plan = compile_issuer_sequential_collection_plan(
        ROOT,
        write_universe(directory, payload),
        run_id="unit-test-run",
        generated_at=GENERATED_AT,
    )
    UNIVERSE_AUTHORITIES[str(plan["issuer_universe_sha256"])] = copy.deepcopy(payload)
    return plan


def universe_authority(plan: dict[str, object]) -> dict[str, object]:
    digest = str(plan["issuer_universe_sha256"])
    if digest in UNIVERSE_AUTHORITIES:
        return copy.deepcopy(UNIVERSE_AUTHORITIES[digest])
    standard = universe()
    if hash_json(standard) == digest:
        return standard
    raise AssertionError("test plan lacks an external universe authority")


def execute_issuer_sequential_collection_plan(
    plan: dict[str, object], *args: object, **kwargs: object
) -> dict[str, object]:
    kwargs.setdefault("issuer_universe", universe_authority(plan))
    return _execute_plan(plan, *args, **kwargs)  # type: ignore[arg-type,return-value]


def validate_issuer_sequential_collection_plan(
    plan: dict[str, object], **kwargs: object
) -> dict[str, object]:
    kwargs.setdefault("issuer_universe", universe_authority(plan))
    return _validate_plan(plan, **kwargs)  # type: ignore[arg-type,return-value]


def validate_issuer_sequential_collection_run(
    run: dict[str, object], plan: dict[str, object], **kwargs: object
) -> dict[str, object]:
    kwargs.setdefault("issuer_universe", universe_authority(plan))
    return _validate_run(run, plan, **kwargs)  # type: ignore[arg-type,return-value]


def write_issuer_sequential_collection_run(
    path: Path,
    run: dict[str, object],
    plan: dict[str, object],
    **kwargs: object,
) -> Path:
    kwargs.setdefault("issuer_universe", universe_authority(plan))
    return _write_run(path, run, plan, **kwargs)  # type: ignore[arg-type,return-value]


def blocked_or_zero_result(
    source: dict[str, object],
    *,
    attempted: datetime,
    completed: datetime,
) -> dict[str, object]:
    source_id = str(source["source_id"])
    sensitive = bool(
        source["requires_runtime_domain_registry"] or source["requires_entitlement"]
    )
    status = (
        "ISSUER_OFFICIAL_SITE_UNRESOLVED"
        if source_id == "issuer_ir_verified"
        else "ENTITLEMENT_REQUIRED"
        if sensitive
        else "VERIFIED_ZERO"
    )
    return {
        "terminal_status": status,
        "attempted_at": attempted.isoformat(),
        "completed_at": completed.isoformat(),
        "artifact_count": 0 if sensitive else 1,
        "observation_count": 0,
        "requested_domain": None,
        "activation_id": None,
        "entitlement_id": None,
        "artifact_manifest_sha256": None if sensitive else ARTIFACT_MANIFEST_SHA256,
        "limitation": "Synthetic terminal receipt for contract validation.",
    }


def two_security_universe() -> dict[str, object]:
    payload = universe()
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


def signed_runtime_registry(
    *, registry_id: str = "sequential-plan-registry"
) -> RuntimeTrustRegistry:
    key = b"sequential-plan-runtime-key-material-32bytes"
    payload = {
        "schema_version": "1.0",
        "audience": "kubo-source-network",
        "registry_id": registry_id,
        "issued_at": "2026-08-26T00:00:00+03:00",
        "expires_at": "2026-08-28T00:00:00+03:00",
        "entries": [
            {
                "source_id": "issuer_ir_verified",
                "subject_id": "SYNTHETIC-ISSUER-1",
                "domains": ["synthetic-company.test"],
                "security_codes": ["999001"],
                "activation_id": "activation-synthetic-issuer-1",
                "entitlement_id": None,
                "valid_from": "2026-08-26T00:00:00+03:00",
                "valid_until": "2026-08-28T00:00:00+03:00",
            }
        ],
        "authentication": {
            "algorithm": "HMAC-SHA256",
            "key_id": "sequential-plan-key",
            "tag": "0" * 64,
        },
    }
    payload["authentication"]["tag"] = hmac.new(
        key, canonical_registry_bytes(payload), hashlib.sha256
    ).hexdigest()
    return verify_runtime_trust_registry(
        payload,
        key=key,
        expected_key_id="sequential-plan-key",
        decision_at=GENERATED_AT,
    )


class IssuerSequentialCollectionTests(unittest.TestCase):
    @unittest.skipUnless(Draft202012Validator is not None, "jsonschema test extra unavailable")
    def test_policy_and_generated_plan_validate_against_schemas(self) -> None:
        assert Draft202012Validator is not None
        assert FormatChecker is not None
        policy = json.loads(
            (ROOT / "config" / "issuer_sequential_collection_policy.json").read_text(
                encoding="utf-8"
            )
        )
        policy_schema = json.loads(
            (ROOT / "schemas" / "issuer-sequential-collection-policy.schema.json").read_text(
                encoding="utf-8"
            )
        )
        plan_schema = json.loads(
            (ROOT / "schemas" / "issuer-sequential-collection-plan.schema.json").read_text(
                encoding="utf-8"
            )
        )
        run_schema = json.loads(
            (ROOT / "schemas" / "issuer-sequential-collection-run.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(policy_schema)
        Draft202012Validator(policy_schema).validate(policy)
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), universe())
        Draft202012Validator.check_schema(plan_schema)
        Draft202012Validator(
            plan_schema, format_checker=FormatChecker()
        ).validate(plan)
        attempted = datetime.fromisoformat("2026-08-27T13:01:00+03:00")

        def zero_executor(
            _security: dict[str, object], source: dict[str, object]
        ) -> dict[str, object]:
            completed = attempted + timedelta(seconds=int(source["source_ordinal"]))
            return blocked_or_zero_result(source, attempted=attempted, completed=completed)

        run = execute_issuer_sequential_collection_plan(
            plan,
            zero_executor,
            project_root=ROOT,
            observed_at=OBSERVED_AT,
        )
        Draft202012Validator.check_schema(run_schema)
        Draft202012Validator(
            run_schema, format_checker=FormatChecker()
        ).validate(run)

    def test_policy_is_one_security_at_a_time_and_exhaustive_per_security(self) -> None:
        report = validate_issuer_sequential_collection_policy(ROOT)
        self.assertEqual(report["status"], "PASS_CONTRACT_NOT_EXECUTED")
        self.assertEqual(report["security_grain"], "SECURITY")
        self.assertEqual(report["security_execution_mode"], "SECURITY_SEQUENTIAL")
        self.assertEqual(report["max_active_securities"], 1)
        self.assertGreaterEqual(report["planned_source_count_per_security"], 29)
        self.assertTrue(report["official_company_site_required"])

    def test_every_security_receives_the_full_source_plan_and_official_site(self) -> None:
        payload = two_security_universe()

        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), payload)
        self.assertEqual(plan["security_count"], 2)
        self.assertEqual(
            plan["total_source_attempts_planned"],
            plan["security_count"] * plan["planned_source_count_per_security"],
        )
        for row in plan["queue"]:  # type: ignore[union-attr]
            self.assertEqual(len(row["source_plan"]), plan["planned_source_count_per_security"])
            self.assertEqual(row["official_company_site"]["source_id"], "issuer_ir_verified")
            self.assertTrue(row["official_company_site"]["required"])
            self.assertEqual(
                row["official_company_site"]["binding_status"], "REQUIRED_AT_EXECUTION"
            )
            self.assertIn(
                "issuer_ir_verified", {source["source_id"] for source in row["source_plan"]}
            )
        self.assertIsNot(plan["queue"][0]["source_plan"], plan["queue"][1]["source_plan"])

    def test_numeric_security_order_is_deterministic(self) -> None:
        payload = universe()
        first_identity = payload["issuers"][0]["security_identities"][0]  # type: ignore[index]
        first_identity.update(
            {"security_code": "10", "ticker": "TEN", "isin": "KW0EQ0000101"}
        )
        second = copy.deepcopy(payload["issuers"][0])  # type: ignore[index]
        second["issuer_id"] = "SYNTHETIC-ISSUER-2"
        second["official_registration_id"] = "SYNTHETIC-REGISTRATION-2"
        second["security_identities"][0].update(  # type: ignore[index]
            {"security_code": "2", "ticker": "TWO", "isin": "KW0EQ0000028"}
        )
        payload["issuers"].append(second)  # type: ignore[union-attr]
        payload["expected_security_codes"] = ["10", "2"]
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), payload)
        self.assertEqual(
            [row["security_code"] for row in plan["queue"]],  # type: ignore[index]
            ["2", "10"],
        )
        self.assertEqual([row["ordinal"] for row in plan["queue"]], [1, 2])  # type: ignore[index]

    def test_two_securities_of_one_issuer_remain_two_independent_queue_items(self) -> None:
        payload = universe()
        payload["issuers"][0]["security_identities"][0].update(  # type: ignore[index]
            {"security_code": "20", "ticker": "SYN20", "isin": "KW0EQ0000200"}
        )
        second_identity = copy.deepcopy(
            payload["issuers"][0]["security_identities"][0]  # type: ignore[index]
        )
        second_identity.update(
            {"security_code": "21", "ticker": "SYN21", "isin": "KW0EQ0000218"}
        )
        payload["issuers"][0]["security_identities"].append(second_identity)  # type: ignore[index]
        payload["expected_security_codes"] = ["20", "21"]
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), payload)
        self.assertEqual([row["security_code"] for row in plan["queue"]], ["20", "21"])  # type: ignore[index]
        self.assertEqual(len({row["issuer_id"] for row in plan["queue"]}), 1)  # type: ignore[index]

    def test_partial_universe_is_rejected_before_collection_planning(self) -> None:
        payload = universe()
        payload["universe_status"] = "PARTIAL"
        payload["expected_security_codes"].append("999002")  # type: ignore[union-attr]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                IssuerSequentialCollectionError, "requires an EXACT point-in-time universe"
            ):
                compile_plan(Path(directory), payload)

    def test_generated_at_cannot_precede_universe_as_of(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_universe(Path(directory), universe())
            with self.assertRaisesRegex(
                IssuerSequentialCollectionError, "cannot precede"
            ):
                compile_issuer_sequential_collection_plan(
                    ROOT,
                    path,
                    run_id="past-plan",
                    generated_at="2020-01-01T00:00:00+03:00",
                )

    def test_signed_runtime_registry_binds_the_company_site_per_security(self) -> None:
        registry = signed_runtime_registry()
        with tempfile.TemporaryDirectory() as directory:
            path = write_universe(Path(directory), universe())
            plan = compile_issuer_sequential_collection_plan(
                ROOT,
                path,
                run_id="bound-company-site",
                generated_at=GENERATED_AT,
                runtime_trust_registry=registry,
            )
        official = plan["queue"][0]["official_company_site"]  # type: ignore[index]
        self.assertEqual(official["binding_status"], "BOUND")
        self.assertEqual(official["authority_subject_id"], "SYNTHETIC-ISSUER-1")
        self.assertEqual(official["verified_domains"], ["synthetic-company.test"])
        report = validate_issuer_sequential_collection_plan(
            plan,
            project_root=ROOT,
            runtime_trust_registry=registry,
        )
        self.assertEqual(report["official_company_sites_bound"], 1)
        self.assertEqual(report["official_company_sites_pending"], 0)

    @unittest.skipUnless(Draft202012Validator is not None, "jsonschema test extra unavailable")
    def test_runtime_identifier_limits_match_the_signed_registry_contract(self) -> None:
        assert Draft202012Validator is not None
        registry = signed_runtime_registry(registry_id="r" * 129)
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_issuer_sequential_collection_plan(
                ROOT,
                write_universe(Path(directory), universe()),
                run_id="long-runtime-id",
                generated_at=GENERATED_AT,
                runtime_trust_registry=registry,
            )
        schema = json.loads(
            (ROOT / "schemas" / "issuer-sequential-collection-plan.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(schema).validate(plan)

    def test_user_sources_and_rights_boundaries_are_preserved_per_security(self) -> None:
        required = {
            "boursa_current",
            "boursa_disclosure_archive",
            "boursa_reports_archive",
            "cma_ifsah",
            "kcc_maqasa_official",
            "issuer_ir_verified",
            "investing_history",
            "reuters_middle_east",
            "yahoo_finance_kw",
            "alqabas_economy",
            "alanba_economy",
            "indexsignal_forum",
            "web_search_router",
            "lseg_workspace_authorized",
            "alphastocks_authorized_connector",
        }
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), universe())
        self.assertEqual(set(plan["user_required_source_ids"]), required)
        sources = {
            row["source_id"]: row for row in plan["queue"][0]["source_plan"]  # type: ignore[index]
        }
        self.assertEqual(len(sources), plan["planned_source_count_per_security"])
        for source_id in ("lseg_workspace_authorized", "alphastocks_authorized_connector"):
            self.assertTrue(sources[source_id]["requires_entitlement"])
            self.assertFalse(sources[source_id]["enabled_by_default"])
        self.assertEqual(sources["indexsignal_forum"]["source_class"], "COMMUNITY")
        self.assertEqual(sources["web_search_router"]["source_class"], "SEARCH_ROUTER")
        self.assertFalse(plan["claim_boundaries"]["community_or_search_confirms_official_fact"])

    def test_executor_seals_one_security_before_starting_the_next(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), two_security_universe())
        calls: list[tuple[str, str]] = []
        base = datetime.fromisoformat("2026-08-27T13:01:00+03:00")

        def executor(security: object, source: object) -> dict[str, object]:
            security_row = security  # type: ignore[assignment]
            source_row = source  # type: ignore[assignment]
            calls.append((security_row["security_code"], source_row["source_id"]))
            attempted = base + timedelta(minutes=(security_row["ordinal"] - 1) * 10)
            return blocked_or_zero_result(
                source_row,
                attempted=attempted,
                completed=attempted + timedelta(seconds=source_row["source_ordinal"]),
            )

        run = execute_issuer_sequential_collection_plan(  # type: ignore[arg-type]
            plan,
            executor,
            project_root=ROOT,
            observed_at=OBSERVED_AT,
        )
        self.assertEqual(len(calls), plan["total_source_attempts_planned"])
        first_source_count = plan["planned_source_count_per_security"]
        self.assertEqual({code for code, _source in calls[:first_source_count]}, {"999001"})
        self.assertEqual({code for code, _source in calls[first_source_count:]}, {"999002"})
        self.assertEqual(
            run["status"], "ALL_SECURITIES_TERMINAL_WITH_EXPLICIT_GAPS"
        )
        self.assertEqual(
            [item["seal_status"] for item in run["security_receipts"]],
            ["SEALED_WITH_EXPLICIT_GAPS", "SEALED_WITH_EXPLICIT_GAPS"],
        )
        self.assertIsNone(run["security_receipts"][0]["previous_security_seal_sha256"])
        self.assertEqual(
            run["security_receipts"][1]["previous_security_seal_sha256"],
            run["security_receipts"][0]["security_seal_sha256"],
        )

    def test_executor_rejects_overlapping_security_windows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), two_security_universe())
        base = datetime.fromisoformat("2026-08-27T13:01:00+03:00")

        def overlapping_executor(security: object, source: object) -> dict[str, object]:
            security_row = security  # type: ignore[assignment]
            source_row = source  # type: ignore[assignment]
            attempted = base + timedelta(minutes=security_row["ordinal"] - 1)
            return blocked_or_zero_result(
                source_row,
                attempted=attempted,
                completed=attempted + timedelta(minutes=5),
            )

        with self.assertRaisesRegex(IssuerSequentialCollectionError, "before the previous"):
            execute_issuer_sequential_collection_plan(  # type: ignore[arg-type]
                plan,
                overlapping_executor,
                project_root=ROOT,
                observed_at=OBSERVED_AT,
            )

    def test_sensitive_collected_source_requires_external_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), universe())
        attempted = datetime.fromisoformat("2026-08-27T13:01:00+03:00")

        def unsafe_executor(_security: object, source: object) -> dict[str, object]:
            source_row = source  # type: ignore[assignment]
            is_official_site = source_row["source_id"] == "issuer_ir_verified"
            return {
                "terminal_status": "COLLECTED" if is_official_site else "VERIFIED_ZERO",
                "attempted_at": attempted.isoformat(),
                "completed_at": (attempted + timedelta(seconds=1)).isoformat(),
                "artifact_count": 1,
                "observation_count": 1 if is_official_site else 0,
                "requested_domain": "synthetic-company.test" if is_official_site else None,
                "activation_id": None,
                "entitlement_id": None,
                "artifact_manifest_sha256": ARTIFACT_MANIFEST_SHA256,
                "limitation": "Synthetic authority negative test.",
            }

        with self.assertRaisesRegex(IssuerSequentialCollectionError, "unbound official"):
            execute_issuer_sequential_collection_plan(  # type: ignore[arg-type]
                plan,
                unsafe_executor,
                project_root=ROOT,
                observed_at=OBSERVED_AT,
            )

    def test_bound_official_site_reopens_registry_and_run_receipt(self) -> None:
        registry = signed_runtime_registry()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = compile_issuer_sequential_collection_plan(
                ROOT,
                write_universe(root, universe()),
                run_id="bound-execution",
                generated_at=GENERATED_AT,
                runtime_trust_registry=registry,
            )
            attempted = datetime.fromisoformat("2026-08-27T13:01:00+03:00")

            def executor(_security: object, source: object) -> dict[str, object]:
                source_row = source  # type: ignore[assignment]
                if source_row["source_id"] == "issuer_ir_verified":
                    return {
                        "terminal_status": "COLLECTED",
                        "attempted_at": attempted.isoformat(),
                        "completed_at": (attempted + timedelta(seconds=1)).isoformat(),
                        "artifact_count": 1,
                        "observation_count": 1,
                        "requested_domain": "synthetic-company.test",
                        "activation_id": None,
                        "entitlement_id": None,
                        "artifact_manifest_sha256": ARTIFACT_MANIFEST_SHA256,
                        "limitation": "Synthetic authority-positive fixture.",
                    }
                return blocked_or_zero_result(
                    source_row,
                    attempted=attempted,
                    completed=attempted + timedelta(seconds=source_row["source_ordinal"]),
                )

            run = execute_issuer_sequential_collection_plan(  # type: ignore[arg-type]
                plan,
                executor,
                project_root=ROOT,
                observed_at=OBSERVED_AT,
                runtime_trust_registry=registry,
            )
            source_receipt = run["security_receipts"][0]["source_receipts"][2]
            self.assertTrue(source_receipt["runtime_authority_bound"])
            self.assertEqual(
                source_receipt["authority_registry_sha256"], registry.content_sha256
            )
            report = validate_issuer_sequential_collection_run(
                run,
                plan,
                project_root=ROOT,
                runtime_trust_registry=registry,
            )
            self.assertEqual(
                report["status"], "PASS_RUN_RECEIPT_INTERNAL_CONSISTENCY_ONLY"
            )
            output = root / "run.json"
            write_issuer_sequential_collection_run(
                output,
                run,
                plan,
                project_root=ROOT,
                runtime_trust_registry=registry,
            )
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), run)

            with self.assertRaisesRegex(
                IssuerSequentialCollectionError, "reopened runtime trust registry"
            ):
                validate_issuer_sequential_collection_run(
                    run,
                    plan,
                    project_root=ROOT,
                )

    def test_lseg_cannot_use_an_adapter_authority_assertion_without_registry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), universe())
        attempted = datetime.fromisoformat("2026-08-27T13:01:00+03:00")

        def executor(_security: object, source: object) -> dict[str, object]:
            source_row = source  # type: ignore[assignment]
            if source_row["source_id"] == "lseg_workspace_authorized":
                source_row["requires_entitlement"] = False
                return {
                    "terminal_status": "COLLECTED",
                    "attempted_at": attempted.isoformat(),
                    "completed_at": (attempted + timedelta(seconds=1)).isoformat(),
                    "artifact_count": 1,
                    "observation_count": 1,
                    "requested_domain": "lseg.com",
                    "activation_id": None,
                    "entitlement_id": "asserted-entitlement",
                    "artifact_manifest_sha256": ARTIFACT_MANIFEST_SHA256,
                    "limitation": "Untrusted adapter assertion.",
                }
            return blocked_or_zero_result(
                source_row,
                attempted=attempted,
                completed=attempted + timedelta(seconds=source_row["source_ordinal"]),
            )

        with self.assertRaisesRegex(
            IssuerSequentialCollectionError, "reopened runtime trust registry"
        ):
            execute_issuer_sequential_collection_plan(  # type: ignore[arg-type]
                plan,
                executor,
                project_root=ROOT,
                observed_at=OBSERVED_AT,
            )

    def test_executor_rejects_receipts_older_than_the_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), universe())
        old = datetime.fromisoformat("2020-01-01T00:00:00+03:00")

        def replay_executor(_security: object, source: object) -> dict[str, object]:
            source_row = source  # type: ignore[assignment]
            return blocked_or_zero_result(
                source_row,
                attempted=old,
                completed=old + timedelta(seconds=1),
            )

        with self.assertRaisesRegex(IssuerSequentialCollectionError, "before the collection plan"):
            execute_issuer_sequential_collection_plan(  # type: ignore[arg-type]
                plan,
                replay_executor,
                project_root=ROOT,
                observed_at=OBSERVED_AT,
            )

    def test_adapter_contract_exception_is_fatal_not_a_source_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), universe())

        def broken_adapter(_security: object, _source: object) -> dict[str, object]:
            raise RuntimeError("adapter failed to normalize its source outcome")

        with self.assertRaisesRegex(RuntimeError, "failed to normalize"):
            execute_issuer_sequential_collection_plan(  # type: ignore[arg-type]
                plan,
                broken_adapter,
                project_root=ROOT,
                observed_at=OBSERVED_AT,
            )

    def test_semantic_plan_validator_rejects_count_or_denominator_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), two_security_universe())
        forged = copy.deepcopy(plan)
        forged["security_count"] = 1
        material = {key: value for key, value in forged.items() if key != "plan_sha256"}
        forged["plan_sha256"] = hash_json(material)
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "security count"):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

        forged = copy.deepcopy(plan)
        forged["queue"][1]["source_plan"][0]["source_id"] = "kuna"
        material = {key: value for key, value in forged.items() if key != "plan_sha256"}
        forged["plan_sha256"] = hash_json(material)
        with self.assertRaises(IssuerSequentialCollectionError):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

        forged = copy.deepcopy(plan)
        forged["queue"][0]["source_plan"][7]["requires_entitlement"] = False
        material = {key: value for key, value in forged.items() if key != "plan_sha256"}
        forged["plan_sha256"] = hash_json(material)
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "locked per-security"):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

        forged = copy.deepcopy(plan)
        forged["queue"][0]["source_plan"][0]["independence_group"] = "forged-group"
        forged["queue"][1]["source_plan"][0]["independence_group"] = "forged-group"
        material = {key: value for key, value in forged.items() if key != "plan_sha256"}
        forged["plan_sha256"] = hash_json(material)
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "reopened catalog"):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

        forged = copy.deepcopy(plan)
        forged["completion_rules"]["source_substitution_allowed"] = True
        material = {key: value for key, value in forged.items() if key != "plan_sha256"}
        forged["plan_sha256"] = hash_json(material)
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "completion rules"):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

        forged = copy.deepcopy(plan)
        forged["queue"][0]["ticker"] = "FORGED"
        material = {key: value for key, value in forged.items() if key != "plan_sha256"}
        forged["plan_sha256"] = hash_json(material)
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "reopened issuer universe"):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

        forged = copy.deepcopy(plan)
        forged["terminal_source_statuses"].append(
            forged["terminal_source_statuses"][0]
        )
        material = {key: value for key, value in forged.items() if key != "plan_sha256"}
        forged["plan_sha256"] = hash_json(material)
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "terminal source"):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

    def test_rehashed_forged_identity_cannot_replace_the_external_universe(self) -> None:
        payload = universe()
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), payload)
        forged = copy.deepcopy(plan)
        identity = forged["queue"][0]
        identity.update(
            {
                "issuer_id": "FORGED-ISSUER",
                "security_code": "123456",
                "ticker": "FORGED",
                "isin": "KW0EQ1234567",
                "legal_name_ar": "شركة مزورة",
                "legal_name_en": "Forged Company",
                "query_terms": [
                    "FORGED",
                    "KW0EQ1234567",
                    "شركة مزورة",
                    "Forged Company",
                    "123456",
                ],
            }
        )
        identity_payload = {
            field: identity[field]
            for field in (
                "issuer_id",
                "security_code",
                "ticker",
                "isin",
                "board",
                "market_segment",
                "listing_status",
                "legal_name_ar",
                "legal_name_en",
            )
        }
        identity["identity_sha256"] = hash_json(identity_payload)
        forged["plan_sha256"] = hash_json(
            {key: value for key, value in forged.items() if key != "plan_sha256"}
        )
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "reopened issuer universe"):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

    def test_bound_company_site_cannot_be_self_asserted_in_a_rehashed_plan(self) -> None:
        registry = signed_runtime_registry()
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_issuer_sequential_collection_plan(
                ROOT,
                write_universe(Path(directory), universe()),
                run_id="forged-official-binding",
                generated_at=GENERATED_AT,
                runtime_trust_registry=registry,
            )
        forged = copy.deepcopy(plan)
        official = forged["queue"][0]["official_company_site"]
        official["authority_registry_id"] = "forged-registry"
        official["authority_registry_sha256"] = "f" * 64
        official["authority_authenticated_key_id"] = "forged-key"
        official["verified_domains"] = ["forged-company.example"]
        forged["plan_sha256"] = hash_json(
            {key: value for key, value in forged.items() if key != "plan_sha256"}
        )
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "reopened runtime registry"):
            validate_issuer_sequential_collection_plan(
                forged,
                project_root=ROOT,
                runtime_trust_registry=registry,
            )

    def test_plan_run_identity_is_semantically_bound_without_schema_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_plan(Path(directory), universe())
        forged = copy.deepcopy(plan)
        forged["run_id"] = ""
        forged["plan_id"] = "not-derived"
        forged["plan_sha256"] = hash_json(
            {key: value for key, value in forged.items() if key != "plan_sha256"}
        )
        with self.assertRaisesRegex(IssuerSequentialCollectionError, "run_id"):
            validate_issuer_sequential_collection_plan(forged, project_root=ROOT)

    def test_plan_hash_is_deterministic_and_excludes_its_own_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = compile_plan(Path(directory), universe())
        expected_hash = first.pop("plan_sha256")
        self.assertEqual(hash_json(first), expected_hash)

    def test_cli_writes_once_and_never_claims_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.json"
            args = [
                "--project-root",
                str(ROOT),
                "plan-issuer-sequential-collection",
                "--universe",
                str(ROOT / "examples" / "synthetic_issuer_universe.json"),
                "--run-id",
                "cli-unit-test",
                "--generated-at",
                GENERATED_AT,
                "--output",
                str(output),
            ]
            stream = io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(cli_main(args), 0)
            receipt = json.loads(stream.getvalue())
            self.assertEqual(receipt["status"], "PLANNED_NOT_EXECUTED")
            self.assertTrue(output.is_file())
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                with redirect_stdout(io.StringIO()):
                    cli_main(args)

    def test_cli_reopens_a_blocked_or_zero_run_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = compile_plan(root, universe())
            attempted = datetime.fromisoformat("2026-08-27T13:01:00+03:00")

            def executor(_security: object, source: object) -> dict[str, object]:
                source_row = source  # type: ignore[assignment]
                return blocked_or_zero_result(
                    source_row,
                    attempted=attempted,
                    completed=attempted + timedelta(seconds=source_row["source_ordinal"]),
                )

            run = execute_issuer_sequential_collection_plan(  # type: ignore[arg-type]
                plan,
                executor,
                project_root=ROOT,
                observed_at=OBSERVED_AT,
            )
            plan_path = root / "plan.json"
            run_path = root / "run.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            run_path.write_text(json.dumps(run), encoding="utf-8")
            stream = io.StringIO()
            with redirect_stdout(stream):
                result = cli_main(
                    [
                        "--project-root",
                        str(ROOT),
                        "validate-issuer-sequential-collection-run",
                        "--plan",
                        str(plan_path),
                        "--run",
                        str(run_path),
                        "--universe",
                        str(root / "issuer-universe.json"),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertEqual(
                json.loads(stream.getvalue())["status"],
                "PASS_RUN_RECEIPT_INTERNAL_CONSISTENCY_ONLY",
            )

    def test_policy_rejects_group_processing_or_missing_user_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            shutil.copytree(ROOT / "config", project / "config")
            policy_path = project / "config" / "issuer_sequential_collection_policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["execution"]["max_active_securities"] = 2
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(
                IssuerSequentialCollectionError, "max_active_securities violates"
            ):
                validate_issuer_sequential_collection_policy(project)

    def test_policy_rejects_community_source_in_official_wave(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            shutil.copytree(ROOT / "config", project / "config")
            policy_path = project / "config" / "issuer_sequential_collection_policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["source_waves"][0]["source_ids"][0] = "indexsignal_forum"
            policy["source_waves"][6]["source_ids"][0] = "boursa_current"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(IssuerSequentialCollectionError, "locked source"):
                validate_issuer_sequential_collection_policy(project)


if __name__ == "__main__":
    unittest.main()
