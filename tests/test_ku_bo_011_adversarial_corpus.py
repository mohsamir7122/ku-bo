from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import unittest

from jsonschema import Draft202012Validator

from tests.ku_bo_011_harness import (
    CORPUS_PATH,
    MANIFEST_PATH,
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
    BOUNDARIES,
    CLAIM_BOUNDARY,
    MUTATIONS,
    TOTAL_CASES,
    VARIANTS_PER_PAIR,
)


CASES = load_cases()


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

    def test_all_cases_are_schema_valid(self) -> None:
        validate_schema(CASES)

    def test_all_cases_are_unique_balanced_and_semantically_locked(self) -> None:
        summary = audit_cases(CASES)
        self.assertEqual(summary["case_count"], 1280)
        self.assertEqual(summary["unique_case_ids"], 1280)
        self.assertEqual(summary["unique_scenarios"], 1280)
        self.assertEqual(summary["unique_semantic_fingerprints"], 1280)
        self.assertEqual(summary["boundary_mutation_pair_count"], 320)

    def test_manifest_binds_corpus_and_schema(self) -> None:
        manifest = verify_manifest(CASES)
        self.assertEqual(manifest["case_count"], 1280)
        self.assertEqual(manifest["unittest_case_method_count"], 1280)
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

    def test_strict_adapter_contract_accepts_a_zero_write_rejection(self) -> None:
        case = CASES[0]

        def adapter(**kwargs):
            supplied = kwargs["case"]
            return {
                "case_id": supplied["case_id"],
                "decision": supplied["expected"]["decision"],
                "failure_code": supplied["expected"]["failure_code"],
                "failure_phase": supplied["expected"]["failure_phase"],
                "output_writes": [],
            }

        execute_strict_case(case, adapter)

    def test_strict_adapter_contract_detects_a_pre_rejection_write(self) -> None:
        case = CASES[0]

        def adapter(**kwargs):
            (kwargs["output_root"] / "forbidden.txt").write_text(
                "must not exist",
                encoding="utf-8",
            )
            supplied = kwargs["case"]
            return {
                "case_id": supplied["case_id"],
                "decision": supplied["expected"]["decision"],
                "failure_code": supplied["expected"]["failure_code"],
                "failure_phase": supplied["expected"]["failure_phase"],
                "output_writes": [],
            }

        with self.assertRaisesRegex(TargetAdapterFailure, "protected output root"):
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
