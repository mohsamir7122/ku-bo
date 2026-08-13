#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
for entry in (PROJECT_ROOT, PROJECT_ROOT / "scripts"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from generate_ku_bo_011_corpus import (  # noqa: E402
    CORPUS_PATH,
    MANIFEST_PATH,
    expected_outputs,
    sha256_bytes,
)
from tests.ku_bo_011_harness import (  # noqa: E402
    audit_cases,
    load_cases,
    validate_schema,
    verify_manifest,
)
from tests.ku_bo_011_mutators import TOTAL_CASES  # noqa: E402
from tests.test_ku_bo_011_adversarial_corpus import (  # noqa: E402
    TestKUBO011CaseSpecs,
)


def audit() -> dict[str, object]:
    cases = load_cases()
    validate_schema(cases)
    summary = audit_cases(cases)
    manifest = verify_manifest(cases)

    expected_corpus, expected_manifest = expected_outputs()
    actual_corpus = CORPUS_PATH.read_bytes()
    actual_manifest = MANIFEST_PATH.read_bytes()
    if actual_corpus != expected_corpus:
        raise AssertionError(
            "corpus differs from deterministic generator output: "
            f"actual={sha256_bytes(actual_corpus)}, "
            f"expected={sha256_bytes(expected_corpus)}"
        )
    if actual_manifest != expected_manifest:
        raise AssertionError("manifest differs from deterministic generator output")

    method_names = unittest.TestLoader().getTestCaseNames(TestKUBO011CaseSpecs)
    if len(method_names) != TOTAL_CASES:
        raise AssertionError(
            f"generated unittest method count is {len(method_names)}, expected {TOTAL_CASES}"
        )
    if len(set(method_names)) != len(method_names):
        raise AssertionError("generated unittest method names are not unique")

    return {
        **summary,
        "unittest_case_method_count": len(method_names),
        "corpus_sha256": sha256_bytes(actual_corpus),
        "schema_sha256": manifest["case_schema_sha256"],
        "claim_boundary": manifest["claim_boundary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit deterministic coverage and generated test methods for KU-BO-011."
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON summary")
    args = parser.parse_args(argv)
    try:
        summary = audit()
    except Exception as exc:
        print(f"KU_BO_011_CORPUS_AUDIT_FAILURE: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            "KU-BO-011 corpus audit PASS: "
            f"{summary['case_count']} unique cases, "
            f"{summary['unittest_case_method_count']} unique unittest methods, "
            f"sha256={summary['corpus_sha256']}"
        )
        print("claim boundary: runtime enforcement NOT CLAIMED by this test-spec pack")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
