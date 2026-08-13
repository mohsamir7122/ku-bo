from __future__ import annotations

import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unittest

from jsonschema import Draft202012Validator
from tests import ku_bo_011_harness

from tests.ku_bo_011_harness import (
    CORPUS_PATH,
    MANIFEST_PATH,
    PUBLIC_BOUNDARIES,
    SCHEMA_PATH,
    CorpusValidationError,
    TargetAdapterFailure,
    TargetAdapterUnavailable,
    audit_cases,
    execute_strict_case,
    load_case_schema,
    load_cases,
    load_target_adapter,
    validate_case_semantics,
    validate_schema,
    verify_manifest,
)
from tests.ku_bo_011_mutators import (
    ATTACK_PROFILES,
    BOUNDARIES,
    CLAIM_BOUNDARY,
    EXPECTED_FAILURE_CODE_OVERRIDE_CASE_COUNT,
    EXPECTED_FAILURE_PHASE_OVERRIDE_CASE_COUNT,
    EXPECTED_REJECTION_OVERRIDE_CASE_COUNT,
    EXPECTED_REJECTION_OVERRIDE_RULE_COUNT,
    EXPECTED_REJECTION_OVERRIDES,
    MATERIALIZATION_INGRESS_BY_CHANNEL,
    MATERIALIZATION_SPECS,
    MUTATIONS,
    TOTAL_CASES,
    VARIANTS_PER_PAIR,
    _expected_rejection,
    build_case,
)


CASES = load_cases()


def _dummy_dispatch_proof(case: dict[str, object]) -> dict[str, object]:
    boundary = case["boundary"]
    mutation = case["mutation"]
    assert isinstance(boundary, dict)
    assert isinstance(mutation, dict)
    boundary_id = str(boundary["id"])
    input_channel = str(mutation["input_channel"])
    mutation_id = str(mutation["id"])
    events = [
        {
            "event": "mutation",
            "boundary_id": boundary_id,
            "input_channel": input_channel,
            "implementation": f"_{mutation_id}",
        },
        {
            "event": "channel_gate",
            "boundary_id": boundary_id,
            "input_channel": input_channel,
            "implementation": "data_foundation_cli.parser+public_boundary",
        },
        {
            "event": "public_boundary",
            "boundary_id": boundary_id,
            "input_channel": input_channel,
            "implementation": PUBLIC_BOUNDARIES[boundary_id],
        },
    ]
    encoded = json.dumps(
        events,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    return {
        "schema_version": "ku-bo-011-dispatch-proof-v1",
        "boundary_id": boundary_id,
        "input_channel": input_channel,
        "mutation_id": mutation_id,
        "public_boundary": PUBLIC_BOUNDARIES[boundary_id],
        "rejection_type": "kubo.tri_security_admission.BoundaryAdmissionError",
        "authority_key_sha256": ("1" * 64, "2" * 64, "3" * 64),
        "events": events,
        "events_sha256": hashlib.sha256(encoded).hexdigest(),
    }


class TestKUBO011CaseSpecs(unittest.TestCase):
    """One real unittest method per deterministic acceptance-case specification."""


def _method_name(case_id: str) -> str:
    return "test_" + re.sub(r"[^a-z0-9]+", "_", case_id.lower()).strip("_")


def _make_case_test(case: dict[str, object]):
    def test_case(self: TestKUBO011CaseSpecs) -> None:
        validate_case_semantics(case)
        self.assertEqual(case["expected"]["decision"], "REJECT")
        self.assertIn(
            case["expected"]["failure_phase"],
            {
                "ENTRY_PRE_WRITE",
                "ARTIFACT_VALIDATION_PRE_WRITE",
                "PRE_COMMIT_RECHECK",
            },
        )
        self.assertEqual(case["expected"]["maximum_output_writes"], 0)
        self.assertTrue(case["implementation_adapter_required"])
        self.assertEqual(case["claim_boundary"], CLAIM_BOUNDARY)

    test_case.__name__ = _method_name(str(case["case_id"]))
    test_case.__qualname__ = f"TestKUBO011CaseSpecs.{test_case.__name__}"
    test_case.__doc__ = f"Validate locked test-spec scenario {case['case_id']}."
    return test_case


for _case in CASES:
    _name = _method_name(str(_case["case_id"]))
    if hasattr(TestKUBO011CaseSpecs, _name):
        raise RuntimeError(f"duplicate generated unittest method: {_name}")
    setattr(TestKUBO011CaseSpecs, _name, _make_case_test(_case))
del _case, _name


class TestKUBO011CorpusInfrastructure(unittest.TestCase):
    def test_exactly_1280_unique_case_methods_are_discoverable(self) -> None:
        method_names = unittest.TestLoader().getTestCaseNames(TestKUBO011CaseSpecs)
        self.assertEqual(len(method_names), 1280)
        self.assertEqual(len(method_names), TOTAL_CASES)
        self.assertEqual(len(set(method_names)), TOTAL_CASES)

    def test_locked_dimensions_are_8_by_40_by_4(self) -> None:
        self.assertEqual(len(BOUNDARIES), 8)
        self.assertEqual(len(MUTATIONS), 40)
        self.assertEqual(VARIANTS_PER_PAIR, 4)
        self.assertEqual(len(BOUNDARIES) * len(MUTATIONS) * VARIANTS_PER_PAIR, 1280)

    def test_v3_detection_order_overrides_are_exact_and_limited(self) -> None:
        self.assertEqual(
            dict(EXPECTED_REJECTION_OVERRIDES),
            {
                ("output_root_preexists", 3): (
                    "OUTPUT_ROOT_CHANGED_DURING_COMMIT",
                    "PRE_COMMIT_RECHECK",
                ),
                ("output_commit_toc_tou", 0): (
                    "OUTPUT_ROOT_CHANGED_DURING_COMMIT",
                    "PRE_COMMIT_RECHECK",
                ),
                ("output_commit_toc_tou", 1): (
                    "OUTPUT_ROOT_CHANGED_DURING_COMMIT",
                    "PRE_COMMIT_RECHECK",
                ),
                ("output_commit_toc_tou", 2): (
                    "PARTIAL_OUTPUT_FORBIDDEN",
                    "PRE_COMMIT_RECHECK",
                ),
            },
        )
        self.assertEqual(EXPECTED_REJECTION_OVERRIDE_RULE_COUNT, 4)
        self.assertEqual(EXPECTED_REJECTION_OVERRIDE_CASE_COUNT, 32)
        self.assertEqual(EXPECTED_FAILURE_CODE_OVERRIDE_CASE_COUNT, 16)
        self.assertEqual(EXPECTED_FAILURE_PHASE_OVERRIDE_CASE_COUNT, 24)

        overridden_case_numbers: set[int] = set()
        code_override_count = 0
        phase_override_count = 0
        generated_cases: list[dict[str, object]] = []
        for boundary_index, _boundary in enumerate(BOUNDARIES):
            for mutation_index, mutation in enumerate(MUTATIONS):
                for variant_index, profile in enumerate(ATTACK_PROFILES):
                    code, phase = _expected_rejection(
                        mutation,
                        profile,
                        variant_index,
                    )
                    if (code, phase) == (
                        mutation.failure_code,
                        profile.failure_phase,
                    ):
                        continue
                    case = build_case(
                        boundary_index,
                        mutation_index,
                        variant_index,
                    )
                    generated_cases.append(case)
                    overridden_case_numbers.add(
                        int(str(case["case_id"]).split("-C", 1)[1].split("-", 1)[0])
                    )
                    code_override_count += code != mutation.failure_code
                    phase_override_count += phase != profile.failure_phase
                    self.assertEqual(
                        case["expected"],
                        {
                            "decision": "REJECT",
                            "failure_code": code,
                            "failure_phase": phase,
                            "maximum_output_writes": 0,
                            "market_evidence_claim": "NOT_EVALUATED",
                        },
                    )

        self.assertEqual(len(generated_cases), EXPECTED_REJECTION_OVERRIDE_CASE_COUNT)
        self.assertEqual(
            code_override_count,
            EXPECTED_FAILURE_CODE_OVERRIDE_CASE_COUNT,
        )
        self.assertEqual(
            phase_override_count,
            EXPECTED_FAILURE_PHASE_OVERRIDE_CASE_COUNT,
        )
        self.assertEqual(
            overridden_case_numbers,
            {
                base + boundary_offset
                for base in (152, 157, 158, 159)
                for boundary_offset in range(0, 1121, 160)
            },
        )

        phase_counts = Counter(case["expected"]["failure_phase"] for case in CASES)
        self.assertEqual(
            phase_counts,
            {
                "ENTRY_PRE_WRITE": 624,
                "ARTIFACT_VALIDATION_PRE_WRITE": 312,
                "PRE_COMMIT_RECHECK": 344,
            },
        )

    def test_all_cases_are_schema_valid(self) -> None:
        validate_schema(CASES)

    def test_v3_materialization_is_complete_and_matches_the_handler(self) -> None:
        self.assertEqual(set(MATERIALIZATION_SPECS), {row.mutation_id for row in MUTATIONS})
        for case in CASES:
            mutation = case["mutation"]
            materialization = case["materialization"]
            self.assertEqual(materialization["handler_id"], mutation["id"])
            self.assertEqual(
                materialization["ingress"],
                MATERIALIZATION_INGRESS_BY_CHANNEL[mutation["input_channel"]],
            )
            self.assertEqual(materialization["value"], mutation["value"])
            for field in (
                "handler_id",
                "ingress",
                "artifact",
                "field",
                "action",
                "timing",
                "resign_policy",
            ):
                self.assertIn(f"{field}={materialization[field]}", mutation["attack_shape"])

    def test_harness_passes_materialization_without_the_expected_oracle(self) -> None:
        supplied = ku_bo_011_harness._adapter_case(CASES[0])
        self.assertIn("materialization", supplied)
        self.assertEqual(
            supplied["materialization"]["handler_id"],
            supplied["mutation"]["id"],
        )
        self.assertNotIn("expected", supplied)
        self.assertNotIn("claim_boundary", supplied)

    def test_all_cases_are_unique_balanced_and_semantically_locked(self) -> None:
        summary = audit_cases(CASES)
        self.assertEqual(summary["case_count"], 1280)
        self.assertEqual(summary["unique_case_ids"], 1280)
        self.assertEqual(summary["unique_scenarios"], 1280)
        self.assertEqual(summary["unique_semantic_fingerprints"], 1280)
        self.assertEqual(summary["boundary_mutation_pair_count"], 320)

    def test_manifest_binds_corpus_and_schema(self) -> None:
        manifest = verify_manifest(CASES)
        self.assertEqual(
            manifest["schema_version"],
            "ku-bo-011-adversarial-corpus-manifest-v3",
        )
        self.assertEqual(manifest["generator_version"], "3.0")
        self.assertEqual(
            manifest["expectation_model"],
            "PRODUCTION_DETECTION_ORDER_V3_MATERIALIZED",
        )
        self.assertEqual(
            manifest["materialization_model"],
            "PRODUCTION_HANDLER_DESCRIPTOR_V1",
        )
        self.assertEqual(manifest["case_count"], 1280)
        self.assertEqual(manifest["unittest_case_method_count"], 1280)
        self.assertEqual(
            manifest["expected_rejection_override_case_count"],
            EXPECTED_REJECTION_OVERRIDE_CASE_COUNT,
        )
        self.assertEqual(
            manifest["expected_failure_code_override_case_count"],
            EXPECTED_FAILURE_CODE_OVERRIDE_CASE_COUNT,
        )
        self.assertEqual(
            manifest["expected_failure_phase_override_case_count"],
            EXPECTED_FAILURE_PHASE_OVERRIDE_CASE_COUNT,
        )
        self.assertEqual(manifest["claim_boundary"], CLAIM_BOUNDARY)

    def test_corpus_files_are_committed_under_tests_only(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for path in (CORPUS_PATH, MANIFEST_PATH, SCHEMA_PATH):
            self.assertTrue(path.is_file())
            self.assertTrue(path.resolve().is_relative_to((root / "tests").resolve()))

    def test_schema_rejects_unknown_fields(self) -> None:
        invalid = copy.deepcopy(CASES[0])
        invalid["unexpected"] = True
        errors = list(Draft202012Validator(load_case_schema()).iter_errors(invalid))
        self.assertTrue(errors)

    def test_schema_requires_the_executable_materialization_descriptor(self) -> None:
        invalid = copy.deepcopy(CASES[0])
        invalid.pop("materialization")
        errors = list(Draft202012Validator(load_case_schema()).iter_errors(invalid))
        self.assertTrue(errors)

    def test_schema_rejects_claim_promotion(self) -> None:
        invalid = copy.deepcopy(CASES[0])
        invalid["expected"]["decision"] = "ACCEPT"
        invalid["claim_boundary"] = "RUNTIME_ENFORCEMENT_PROVEN"
        errors = list(Draft202012Validator(load_case_schema()).iter_errors(invalid))
        self.assertGreaterEqual(len(errors), 2)

    def test_semantic_validator_rejects_expected_write(self) -> None:
        invalid = copy.deepcopy(CASES[0])
        invalid["expected"]["maximum_output_writes"] = 1
        with self.assertRaises(CorpusValidationError):
            validate_case_semantics(invalid)

    def test_strict_mode_requires_an_explicit_implementation_adapter(self) -> None:
        with self.assertRaisesRegex(
            TargetAdapterUnavailable,
            "does not prove downstream runtime enforcement",
        ):
            load_target_adapter(None)

    def test_strict_adapter_contract_accepts_a_zero_write_rejection_without_oracle(
        self,
    ) -> None:
        case = CASES[0]

        def adapter(**kwargs):
            supplied = kwargs["case"]
            self.assertNotIn("expected", supplied)
            self.assertNotIn("claim_boundary", supplied)
            return {
                "case_id": supplied["case_id"],
                "decision": "REJECT",
                "failure_code": "RUN_RECEIPT_REQUIRED",
                "failure_phase": "ENTRY_PRE_WRITE",
                "output_writes": [],
                "dispatch_proof": _dummy_dispatch_proof(case),
            }

        execute_strict_case(case, adapter)

    def test_strict_adapter_contract_detects_a_pre_rejection_write(self) -> None:
        case = CASES[0]

        def adapter(**kwargs):
            kwargs["output_root"].mkdir()
            (kwargs["output_root"] / "forbidden.txt").write_text(
                "must not exist",
                encoding="utf-8",
            )
            supplied = kwargs["case"]
            return {
                "case_id": supplied["case_id"],
                "decision": "REJECT",
                "failure_code": "RUN_RECEIPT_REQUIRED",
                "failure_phase": "ENTRY_PRE_WRITE",
                "output_writes": [],
                "dispatch_proof": _dummy_dispatch_proof(case),
            }

        with self.assertRaisesRegex(TargetAdapterFailure, "protected output root"):
            execute_strict_case(case, adapter)

    def test_strict_adapter_cannot_read_or_rewrite_expected_values(self) -> None:
        case = CASES[0]
        original_failure_code = case["expected"]["failure_code"]

        def adapter(**kwargs):
            supplied = kwargs["case"]
            self.assertNotIn("expected", supplied)
            return {
                "case_id": supplied["case_id"],
                "decision": "REJECT",
                "failure_code": "ORACLE_REWRITE",
                "failure_phase": "ENTRY_PRE_WRITE",
                "output_writes": [],
                "dispatch_proof": _dummy_dispatch_proof(case),
            }

        with self.assertRaisesRegex(TargetAdapterFailure, "failure_code"):
            execute_strict_case(case, adapter)
        self.assertEqual(case["expected"]["failure_code"], original_failure_code)

    def test_strict_harness_expected_canary_is_not_visible_to_adapter(self) -> None:
        case = copy.deepcopy(CASES[0])
        case["expected"]["failure_code"] = "HARNESS_CANARY"

        def adapter(**kwargs):
            supplied = kwargs["case"]
            self.assertNotIn("expected", supplied)
            return {
                "case_id": supplied["case_id"],
                "decision": "REJECT",
                "failure_code": "RUN_RECEIPT_REQUIRED",
                "failure_phase": "ENTRY_PRE_WRITE",
                "output_writes": [],
                "dispatch_proof": _dummy_dispatch_proof(case),
            }

        with self.assertRaisesRegex(TargetAdapterFailure, "HARNESS_CANARY"):
            execute_strict_case(case, adapter)

    def test_strict_harness_detects_sibling_staging_residue(self) -> None:
        case = CASES[0]

        def adapter(**kwargs):
            supplied = kwargs["case"]
            (kwargs["case_root"] / ".output.staging-residue").mkdir()
            return {
                "case_id": supplied["case_id"],
                "decision": "REJECT",
                "failure_code": "RUN_RECEIPT_REQUIRED",
                "failure_phase": "ENTRY_PRE_WRITE",
                "output_writes": [],
                "dispatch_proof": _dummy_dispatch_proof(case),
            }

        with self.assertRaisesRegex(TargetAdapterFailure, "protected case surface"):
            execute_strict_case(case, adapter)

    def test_jsonl_contains_one_canonical_object_per_nonblank_line(self) -> None:
        content = CORPUS_PATH.read_text(encoding="utf-8")
        self.assertTrue(content.endswith("\n"))
        lines = content.splitlines()
        self.assertEqual(len(lines), 1280)
        self.assertNotIn("", lines)
        for line in lines:
            parsed = json.loads(line)
            canonical = json.dumps(
                parsed,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            self.assertEqual(line, canonical)


if __name__ == "__main__":
    unittest.main()
