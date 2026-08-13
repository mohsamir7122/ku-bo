from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.ku_bo_011_mutators import (  # noqa: E402
    ATTACK_PROFILES,
    BOUNDARIES,
    CLAIM_BOUNDARY,
    MUTATIONS,
    TOTAL_CASES,
    UNSAFE_ENTRY_VARIANTS,
    VARIANTS_PER_PAIR,
    build_case,
    semantic_projection,
)


CORPUS_PATH = PROJECT_ROOT / "tests" / "corpus" / "ku_bo_011_cases.jsonl"
MANIFEST_PATH = PROJECT_ROOT / "tests" / "corpus" / "ku_bo_011_manifest.json"
SCHEMA_PATH = PROJECT_ROOT / "tests" / "corpus" / "ku_bo_011_case.schema.json"
CASE_ID_PATTERN = re.compile(
    r"^KU-BO-011-C(?P<index>[0-9]{4})-"
    r"(?P<boundary>[a-z0-9_]+)-(?P<mutation>[a-z0-9_]+)-"
    r"V(?P<variant>[0-9]{2})$"
)
RESULT_KEYS = frozenset(
    {"case_id", "decision", "failure_code", "failure_phase", "output_writes"}
)
REQUIRED_SEMANTIC_GATES = frozenset(
    {
        "wrong_batch_binding",
        "batch_plan_hash_mismatch",
        "qualification_window_mismatch",
        "cohort_mismatch",
        "wrong_stage_id",
        "predecessor_binding_omission",
        "predecessor_binding_replay",
        "predecessor_binding_wrong_stage",
        "five_security_denominator_promotion",
        "full_market_claim_promotion",
        "benchmark_fallback_promotion",
        "d01_policy_promotion",
        "untrusted_legacy_claim_promotion",
        "output_root_preexists",
        "partial_output_on_rejection",
        "output_commit_toc_tou",
        "stage_tree_toc_tou",
    }
)


class CorpusValidationError(ValueError):
    pass


class TargetAdapterUnavailable(RuntimeError):
    pass


class TargetAdapterFailure(AssertionError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CorpusValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


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


def load_cases(path: Path = CORPUS_PATH) -> list[dict[str, Any]]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise CorpusValidationError(f"cannot read corpus: {path}") from exc
    if not content.endswith(b"\n"):
        raise CorpusValidationError("corpus must end with exactly one LF-terminated row")
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise CorpusValidationError("corpus must be strict UTF-8") from exc

    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            raise CorpusValidationError(f"blank corpus row at line {line_number}")
        try:
            case = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    CorpusValidationError(f"non-finite JSON value: {value}")
                ),
            )
        except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
            raise CorpusValidationError(
                f"invalid corpus JSON at line {line_number}"
            ) from exc
        if not isinstance(case, dict):
            raise CorpusValidationError(f"corpus row {line_number} must be an object")
        if line != canonical_json(case):
            raise CorpusValidationError(
                f"corpus row {line_number} is not canonical sorted compact JSON"
            )
        cases.append(case)
    return cases


def load_case_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    try:
        schema = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CorpusValidationError(f"non-finite schema value: {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CorpusValidationError(f"cannot load strict case schema: {path}") from exc
    if not isinstance(schema, dict):
        raise CorpusValidationError("case schema must be a JSON object")
    return schema


def validate_schema(cases: Iterable[Mapping[str, Any]]) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise CorpusValidationError(
            "jsonschema test dependency is required to validate the corpus schema"
        ) from exc

    schema = load_case_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    for row_number, case in enumerate(cases, start=1):
        errors = sorted(validator.iter_errors(case), key=lambda error: list(error.path))
        if errors:
            first = errors[0]
            location = "/".join(str(item) for item in first.absolute_path) or "<root>"
            raise CorpusValidationError(
                f"schema error in row {row_number} at {location}: {first.message}"
            )


def _parsed_case_coordinates(case: Mapping[str, Any]) -> tuple[int, int, int, int]:
    case_id = case.get("case_id")
    if not isinstance(case_id, str):
        raise CorpusValidationError("case_id must be a string")
    match = CASE_ID_PATTERN.fullmatch(case_id)
    if match is None:
        raise CorpusValidationError(f"invalid case_id: {case_id!r}")

    boundary_by_id = {boundary.boundary_id: index for index, boundary in enumerate(BOUNDARIES)}
    mutation_by_id = {mutation.mutation_id: index for index, mutation in enumerate(MUTATIONS)}
    try:
        boundary_index = boundary_by_id[match.group("boundary")]
        mutation_index = mutation_by_id[match.group("mutation")]
    except KeyError as exc:
        raise CorpusValidationError(f"case_id names an unknown dimension: {case_id}") from exc
    variant_index = int(match.group("variant"))
    case_index = int(match.group("index"))
    return case_index, boundary_index, mutation_index, variant_index


def validate_case_semantics(case: Mapping[str, Any]) -> None:
    case_index, boundary_index, mutation_index, variant_index = _parsed_case_coordinates(
        case
    )
    expected_index = (
        boundary_index * len(MUTATIONS) * VARIANTS_PER_PAIR
        + mutation_index * VARIANTS_PER_PAIR
        + variant_index
        + 1
    )
    if case_index != expected_index:
        raise CorpusValidationError(
            f"case index/order mismatch for {case.get('case_id')}: "
            f"expected C{expected_index:04d}"
        )
    if variant_index >= VARIANTS_PER_PAIR:
        raise CorpusValidationError(f"variant is out of range: {case.get('case_id')}")

    expected = build_case(boundary_index, mutation_index, variant_index)
    if dict(case) != expected:
        raise CorpusValidationError(
            f"case differs from the locked deterministic design: {case.get('case_id')}"
        )

    context = case["context"]
    mutation_id = case["mutation"]["id"]
    if mutation_id == "cross_run_receipt":
        if context["receipt_run_id"] == context["target_run_id"]:
            raise CorpusValidationError("cross-run receipt did not change receipt_run_id")
    elif context["receipt_run_id"] != context["target_run_id"]:
        raise CorpusValidationError("non-cross-run case changed receipt_run_id")
    if mutation_id == "cross_run_stage_binding":
        if context["binding_run_id"] == context["target_run_id"]:
            raise CorpusValidationError("cross-run binding did not change binding_run_id")
    elif context["binding_run_id"] != context["target_run_id"]:
        raise CorpusValidationError("non-cross-run case changed binding_run_id")

    if case["expected"] != {
        "decision": "REJECT",
        "failure_code": MUTATIONS[mutation_index].failure_code,
        "failure_phase": ATTACK_PROFILES[variant_index].failure_phase,
        "maximum_output_writes": 0,
        "market_evidence_claim": "NOT_EVALUATED",
    }:
        raise CorpusValidationError("case weakens its fail-closed zero-write expectation")
    if case["claim_boundary"] != CLAIM_BOUNDARY:
        raise CorpusValidationError("case overstates KU-BO-011 runtime enforcement")


def audit_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    if len(cases) != TOTAL_CASES:
        raise CorpusValidationError(
            f"corpus has {len(cases)} cases; locked design requires {TOTAL_CASES}"
        )

    case_ids = [case.get("case_id") for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise CorpusValidationError("case_id values are not unique")
    canonical_rows = [canonical_json(case) for case in cases]
    if len(set(canonical_rows)) != len(canonical_rows):
        raise CorpusValidationError("corpus contains duplicate scenario objects")
    semantic_rows = [canonical_json(semantic_projection(case)) for case in cases]
    if len(set(semantic_rows)) != len(semantic_rows):
        raise CorpusValidationError(
            "semantic scenarios are not unique after removing case IDs, timestamps, "
            "run IDs, paths, and profile/index labels"
        )

    for case in cases:
        validate_case_semantics(case)

    boundary_counts = Counter(case["boundary"]["id"] for case in cases)
    mutation_counts = Counter(case["mutation"]["id"] for case in cases)
    pair_counts = Counter(
        (case["boundary"]["id"], case["mutation"]["id"]) for case in cases
    )
    expected_boundary_count = len(MUTATIONS) * VARIANTS_PER_PAIR
    expected_mutation_count = len(BOUNDARIES) * VARIANTS_PER_PAIR
    if set(boundary_counts.values()) != {expected_boundary_count}:
        raise CorpusValidationError("boundary coverage is not balanced")
    if set(mutation_counts.values()) != {expected_mutation_count}:
        raise CorpusValidationError("mutation coverage is not balanced")
    missing_semantic_gates = REQUIRED_SEMANTIC_GATES - set(mutation_counts)
    if missing_semantic_gates:
        raise CorpusValidationError(
            "required admission/graph/claim/atomicity gates are missing: "
            + ", ".join(sorted(missing_semantic_gates))
        )
    if len(pair_counts) != len(BOUNDARIES) * len(MUTATIONS):
        raise CorpusValidationError("one or more boundary/mutation pairs are missing")
    if set(pair_counts.values()) != {VARIANTS_PER_PAIR}:
        raise CorpusValidationError(
            "a boundary/mutation pair does not have exactly "
            f"{VARIANTS_PER_PAIR} attack profiles"
        )

    unsafe_kinds = {
        case["mutation"]["unsafe_entry_kind"]
        for case in cases
        if case["mutation"]["id"] == "unsafe_stage_entry"
    }
    if unsafe_kinds != {kind for kind, _ in UNSAFE_ENTRY_VARIANTS}:
        raise CorpusValidationError("unsafe-entry variant coverage drifted")

    return {
        "case_count": len(cases),
        "unique_case_ids": len(set(case_ids)),
        "unique_scenarios": len(set(canonical_rows)),
        "unique_semantic_fingerprints": len(set(semantic_rows)),
        "boundary_count": len(boundary_counts),
        "mutation_family_count": len(mutation_counts),
        "boundary_mutation_pair_count": len(pair_counts),
        "variants_per_pair": VARIANTS_PER_PAIR,
    }


def verify_manifest(cases: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        manifest_bytes = MANIFEST_PATH.read_bytes()
        manifest = json.loads(
            manifest_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CorpusValidationError(f"non-finite manifest value: {value}")
            ),
        )
        corpus_bytes = CORPUS_PATH.read_bytes()
        schema_bytes = SCHEMA_PATH.read_bytes()
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CorpusValidationError("cannot read strict corpus manifest") from exc
    if not isinstance(manifest, dict):
        raise CorpusValidationError("corpus manifest must be a JSON object")
    semantic_fingerprints = sorted(
        sha256_bytes(canonical_json(semantic_projection(case)).encode("utf-8"))
        for case in cases
    )
    expected_scalars = {
        "schema_version": "ku-bo-011-adversarial-corpus-manifest-v1",
        "generator_version": "1.0",
        "case_count": TOTAL_CASES,
        "unittest_case_method_count": TOTAL_CASES,
        "corpus_sha256": sha256_bytes(corpus_bytes),
        "case_schema_sha256": sha256_bytes(schema_bytes),
        "semantic_fingerprint_count": len(set(semantic_fingerprints)),
        "semantic_fingerprint_set_sha256": sha256_bytes(
            ("\n".join(semantic_fingerprints) + "\n").encode("utf-8")
        ),
        "claim_boundary": CLAIM_BOUNDARY,
        "first_case_id": cases[0]["case_id"],
        "last_case_id": cases[-1]["case_id"],
    }
    for key, expected in expected_scalars.items():
        if manifest.get(key) != expected:
            raise CorpusValidationError(
                f"manifest {key} mismatch: {manifest.get(key)!r} != {expected!r}"
            )
    if not manifest_bytes.endswith(b"\n"):
        raise CorpusValidationError("manifest must end with LF")
    return manifest


def load_target_adapter(spec: str | None) -> Callable[..., Mapping[str, Any]]:
    if not spec:
        raise TargetAdapterUnavailable(
            "KU-BO-011 strict target-adapter mode requires --adapter module:callable; "
            "the committed corpus validates only the acceptance specification and "
            "does not prove downstream runtime enforcement"
        )
    module_name, separator, attribute_path = spec.partition(":")
    if not separator or not module_name or not attribute_path:
        raise TargetAdapterUnavailable(
            "target adapter must use the form module:callable"
        )
    try:
        target: Any = importlib.import_module(module_name)
        for component in attribute_path.split("."):
            target = getattr(target, component)
    except (ImportError, AttributeError) as exc:
        raise TargetAdapterUnavailable(f"cannot load target adapter {spec!r}") from exc
    if not callable(target):
        raise TargetAdapterUnavailable(f"target adapter {spec!r} is not callable")
    return target


def _snapshot_output_tree(root: Path) -> tuple[tuple[str, str, int], ...]:
    if not root.exists() and not root.is_symlink():
        return (("<root>", "missing", 0),)
    if not root.is_dir() or root.is_symlink():
        metadata = os.lstat(root)
        kind = "symlink" if stat.S_ISLNK(metadata.st_mode) else "non-directory"
        return (("<root>", kind, metadata.st_size),)
    rows: list[tuple[str, str, int]] = []

    def walk(directory: Path, relative: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise TargetAdapterFailure("cannot inspect adapter output root") from exc
        for entry in entries:
            entry_relative = (relative / entry.name).as_posix()
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISREG(metadata.st_mode):
                digest = sha256_bytes(Path(entry.path).read_bytes())
                rows.append((entry_relative, f"file:{digest}", metadata.st_size))
            elif stat.S_ISDIR(metadata.st_mode):
                rows.append((entry_relative, "directory", 0))
                walk(Path(entry.path), relative / entry.name)
            elif stat.S_ISLNK(metadata.st_mode):
                rows.append((entry_relative, "symlink", 0))
            else:
                rows.append((entry_relative, f"special:{metadata.st_mode}", 0))

    walk(root, Path())
    return (("<root>", "directory", 0), *rows)


def execute_strict_case(
    case: Mapping[str, Any],
    adapter: Callable[..., Mapping[str, Any]],
) -> None:
    with tempfile.TemporaryDirectory(prefix="ku-bo-011-adapter-") as temp_name:
        case_root = Path(temp_name)
        input_root = case_root / "input"
        output_root = case_root / "output"
        input_root.mkdir()
        original_case = copy.deepcopy(dict(case))
        expected = copy.deepcopy(original_case["expected"])
        checks = {
            "case_id": original_case["case_id"],
            "decision": expected["decision"],
            "failure_code": expected["failure_code"],
            "failure_phase": expected["failure_phase"],
            "output_writes": [],
        }
        before = _snapshot_output_tree(output_root)
        try:
            result = adapter(
                case=copy.deepcopy(original_case),
                case_root=case_root,
                input_root=input_root,
                output_root=output_root,
            )
        except Exception as exc:
            raise TargetAdapterFailure(
                f"adapter raised for {case.get('case_id')}: {type(exc).__name__}: {exc}"
            ) from exc
        after = _snapshot_output_tree(output_root)

    if dict(case) != original_case:
        raise TargetAdapterFailure(
            f"adapter mutated the locked source case {case.get('case_id')}"
        )

    if not isinstance(result, Mapping):
        raise TargetAdapterFailure(
            f"adapter result for {case.get('case_id')} must be a mapping"
        )
    if set(result) != RESULT_KEYS:
        raise TargetAdapterFailure(
            f"adapter result keys for {case.get('case_id')} must be "
            f"{sorted(RESULT_KEYS)}"
        )
    for key, expected_value in checks.items():
        if result[key] != expected_value:
            raise TargetAdapterFailure(
                f"adapter result mismatch for {case.get('case_id')} field {key}: "
                f"{result[key]!r} != {expected_value!r}"
            )
    if before != after:
        raise TargetAdapterFailure(
            f"adapter wrote to the protected output root before rejecting "
            f"{case.get('case_id')}: before={before!r}, after={after!r}"
        )


def run_strict_adapter(
    cases: Iterable[Mapping[str, Any]],
    adapter_spec: str | None,
) -> int:
    adapter = load_target_adapter(adapter_spec)
    count = 0
    for case in cases:
        execute_strict_case(case, adapter)
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit the KU-BO-011 test spec or run a separate strict target adapter."
    )
    parser.add_argument(
        "--strict-target-adapter",
        action="store_true",
        help="execute acceptance cases against a supplied implementation adapter",
    )
    parser.add_argument(
        "--adapter",
        help="implementation adapter in module:callable form (strict mode only)",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="run only an exact case ID; may be repeated in strict mode",
    )
    args = parser.parse_args(argv)

    try:
        if args.strict_target_adapter:
            # Fail with the adapter-specific contract message before optional
            # schema tooling can obscure a missing implementation target.
            load_target_adapter(args.adapter)
        cases = load_cases()
        validate_schema(cases)
        summary = audit_cases(cases)
        verify_manifest(cases)
        if not args.strict_target_adapter:
            if args.adapter or args.case_id:
                parser.error("--adapter and --case-id require --strict-target-adapter")
            print(
                "KU-BO-011 test-spec audit PASS: "
                f"{summary['case_count']} unique deterministic cases; "
                "runtime enforcement NOT CLAIMED"
            )
            return 0

        selected = cases
        if args.case_id:
            requested = set(args.case_id)
            selected = [case for case in cases if case["case_id"] in requested]
            found = {case["case_id"] for case in selected}
            missing = sorted(requested - found)
            if missing:
                raise CorpusValidationError(
                    f"unknown requested case IDs: {', '.join(missing)}"
                )
        count = run_strict_adapter(selected, args.adapter)
        print(f"KU-BO-011 strict target adapter PASS: {count} cases")
        return 0
    except TargetAdapterUnavailable as exc:
        print(f"TARGET_ADAPTER_UNAVAILABLE: {exc}", file=sys.stderr)
        return 2
    except (CorpusValidationError, TargetAdapterFailure) as exc:
        print(f"KU_BO_011_ACCEPTANCE_FAILURE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
