#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.ku_bo_011_mutators import (  # noqa: E402
    BOUNDARIES,
    CLAIM_BOUNDARY,
    MUTATIONS,
    TOTAL_CASES,
    VARIANTS_PER_PAIR,
    case_dimensions,
    iter_cases,
    semantic_projection,
)


CORPUS_PATH = PROJECT_ROOT / "tests" / "corpus" / "ku_bo_011_cases.jsonl"
MANIFEST_PATH = PROJECT_ROOT / "tests" / "corpus" / "ku_bo_011_manifest.json"
SCHEMA_PATH = PROJECT_ROOT / "tests" / "corpus" / "ku_bo_011_case.schema.json"
GENERATOR_PATH = PROJECT_ROOT / "scripts" / "generate_ku_bo_011_corpus.py"
AUDITOR_PATH = PROJECT_ROOT / "scripts" / "audit_ku_bo_011_corpus.py"
HARNESS_PATH = PROJECT_ROOT / "tests" / "ku_bo_011_harness.py"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def render_corpus(cases: Iterable[dict[str, Any]]) -> bytes:
    return ("\n".join(canonical_json(case) for case in cases) + "\n").encode("utf-8")


def render_manifest(cases: list[dict[str, Any]], corpus_bytes: bytes) -> bytes:
    boundary_counts = Counter(case["boundary"]["id"] for case in cases)
    mutation_counts = Counter(case["mutation"]["id"] for case in cases)
    decision_counts = Counter(case["expected"]["decision"] for case in cases)
    phase_counts = Counter(case["expected"]["failure_phase"] for case in cases)
    semantic_fingerprints = sorted(
        sha256_bytes(canonical_json(semantic_projection(case)).encode("utf-8"))
        for case in cases
    )
    schema_bytes = SCHEMA_PATH.read_bytes()
    manifest = {
        "schema_version": "ku-bo-011-adversarial-corpus-manifest-v1",
        "generator_version": "1.0",
        "corpus_path": CORPUS_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "case_schema_path": SCHEMA_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "generator_path": GENERATOR_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "auditor_path": AUDITOR_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "harness_path": HARNESS_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "case_count": len(cases),
        "unittest_case_method_count": len(cases),
        "corpus_sha256": sha256_bytes(corpus_bytes),
        "case_schema_sha256": sha256_bytes(schema_bytes),
        "semantic_fingerprint_count": len(set(semantic_fingerprints)),
        "semantic_fingerprint_set_sha256": sha256_bytes(
            ("\n".join(semantic_fingerprints) + "\n").encode("utf-8")
        ),
        "semantic_fingerprint_excludes": [
            "case_id",
            "case_seed_sha256",
            "target_run_id",
            "receipt_run_id",
            "binding_run_id",
            "evaluation_time",
            "stage_root",
            "output_root",
            "variant_index",
            "profile_id"
        ],
        "dimensions": case_dimensions(),
        "boundary_counts": dict(sorted(boundary_counts.items())),
        "mutation_counts": dict(sorted(mutation_counts.items())),
        "expected_decision_counts": dict(sorted(decision_counts.items())),
        "expected_failure_phase_counts": dict(sorted(phase_counts.items())),
        "first_case_id": cases[0]["case_id"],
        "last_case_id": cases[-1]["case_id"],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def expected_outputs() -> tuple[bytes, bytes]:
    cases = list(iter_cases())
    if len(cases) != TOTAL_CASES:
        raise AssertionError(f"design produced {len(cases)} cases, expected {TOTAL_CASES}")
    corpus_bytes = render_corpus(cases)
    manifest_bytes = render_manifest(cases, corpus_bytes)
    return corpus_bytes, manifest_bytes


def _check_file(path: Path, expected: bytes) -> list[str]:
    if not path.is_file():
        return [f"missing generated file: {path.relative_to(PROJECT_ROOT)}"]
    actual = path.read_bytes()
    if actual != expected:
        return [
            f"generated file drift: {path.relative_to(PROJECT_ROOT)} "
            f"(actual={sha256_bytes(actual)}, expected={sha256_bytes(expected)})"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic 1,280-case KU-BO-011 test-spec corpus."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed generated files without rewriting them",
    )
    args = parser.parse_args(argv)

    if len(BOUNDARIES) != 8 or len(MUTATIONS) != 40 or VARIANTS_PER_PAIR != 4:
        raise AssertionError("the locked corpus dimensions must remain 8 x 40 x 4")
    corpus_bytes, manifest_bytes = expected_outputs()

    if args.check:
        errors = _check_file(CORPUS_PATH, corpus_bytes)
        errors.extend(_check_file(MANIFEST_PATH, manifest_bytes))
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print(
            f"KU-BO-011 corpus generation check PASS: {TOTAL_CASES} cases, "
            f"sha256={sha256_bytes(corpus_bytes)}"
        )
        return 0

    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_bytes(corpus_bytes)
    MANIFEST_PATH.write_bytes(manifest_bytes)
    print(
        f"wrote {TOTAL_CASES} deterministic cases to "
        f"{CORPUS_PATH.relative_to(PROJECT_ROOT)}"
    )
    print(f"corpus sha256: {sha256_bytes(corpus_bytes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
