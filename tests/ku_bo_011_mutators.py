from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Iterator


SCHEMA_VERSION = "ku-bo-011-adversarial-case-v1"
CLAIM_BOUNDARY = "TEST_SPEC_ONLY_NO_KU_BO_011_RUNTIME_ENFORCEMENT_CLAIM"
VARIANTS_PER_PAIR = 4


@dataclass(frozen=True)
class BoundarySpec:
    boundary_id: str
    cli_command: str
    role: str
    write_surface: str


@dataclass(frozen=True)
class MutationSpec:
    mutation_id: str
    authority: str
    operation: str
    target: str
    failure_code: str


@dataclass(frozen=True)
class AttackProfile:
    profile_id: str
    input_channel: str
    timing: str
    failure_phase: str


ATTACK_PROFILES = (
    AttackProfile(
        "cli_surface",
        "CLI_ARGUMENT",
        "COMMAND_ENTRY",
        "ENTRY_PRE_WRITE",
    ),
    AttackProfile(
        "direct_api_surface",
        "DIRECT_API_OBJECT",
        "FUNCTION_ENTRY",
        "ENTRY_PRE_WRITE",
    ),
    AttackProfile(
        "serialized_artifact",
        "SERIALIZED_ARTIFACT",
        "ARTIFACT_PARSE",
        "ARTIFACT_VALIDATION_PRE_WRITE",
    ),
    AttackProfile(
        "post_validation_swap",
        "FILESYSTEM_RACE",
        "AFTER_INITIAL_VALIDATION_BEFORE_COMMIT",
        "PRE_COMMIT_RECHECK",
    ),
)


BOUNDARIES = (
    BoundarySpec(
        "import_user_price_exports",
        "import-user-price-exports",
        "IMPORT",
        "price_history_output_root",
    ),
    BoundarySpec(
        "import_official_foundation",
        "import-official-foundation",
        "IMPORT",
        "official_foundation_output_root",
    ),
    BoundarySpec(
        "import_status_corporate",
        "import-status-corporate",
        "IMPORT",
        "status_corporate_output_root",
    ),
    BoundarySpec(
        "import_ca_enrichment",
        "import-ca-enrichment",
        "IMPORT",
        "ca_enrichment_output_root",
    ),
    BoundarySpec(
        "import_status_history",
        "import-status-history",
        "IMPORT",
        "status_history_output_root",
    ),
    BoundarySpec(
        "import_benchmark_history",
        "import-benchmark-history",
        "IMPORT",
        "benchmark_history_output_root",
    ),
    BoundarySpec(
        "import_official_eod",
        "import-official-eod",
        "IMPORT",
        "official_eod_output_root",
    ),
    BoundarySpec(
        "build_data_foundation_packet",
        "build-data-foundation-packet",
        "FINAL_RECONCILIATION",
        "data_foundation_packet_output_root",
    ),
)


MUTATIONS = (
    MutationSpec("missing_run_receipt", "RUN_RECEIPT", "OMIT", "/run_receipt", "RUN_RECEIPT_REQUIRED"),
    MutationSpec("malformed_run_receipt", "RUN_RECEIPT", "REPLACE", "/run_receipt", "RUN_RECEIPT_SCHEMA_INVALID"),
    MutationSpec("forged_run_authentication_tag", "RUN_RECEIPT", "REPLACE", "/run_receipt/authentication/tag", "RUN_RECEIPT_AUTHENTICATION_FAILED"),
    MutationSpec("wrong_run_key_id", "RUN_RECEIPT", "REPLACE", "/run_receipt/authentication/key_id", "RUN_RECEIPT_KEY_ID_MISMATCH"),
    MutationSpec("non_independent_authority", "RUN_RECEIPT", "REUSE_AUTHORITY", "/authorities", "AUTHORITY_KEYS_NOT_INDEPENDENT"),
    MutationSpec("expired_run_receipt", "RUN_RECEIPT", "REPLACE", "/run_receipt/expires_at", "RUN_RECEIPT_EXPIRED"),
    MutationSpec("future_run_receipt", "RUN_RECEIPT", "REPLACE", "/run_receipt/issued_at", "RUN_RECEIPT_NOT_YET_VALID"),
    MutationSpec("cross_run_receipt", "RUN_RECEIPT", "REPLACE", "/run_receipt/run_id", "RUN_RECEIPT_RUN_ID_MISMATCH"),
    MutationSpec("wrong_receipt_audience", "RUN_RECEIPT", "REPLACE", "/run_receipt/audience", "RUN_RECEIPT_AUDIENCE_MISMATCH"),
    MutationSpec("wrong_batch_binding", "RUN_RECEIPT", "REPLACE", "/run_receipt/batch_number", "RUN_RECEIPT_BATCH_MISMATCH"),
    MutationSpec("batch_plan_hash_mismatch", "RUN_RECEIPT", "REPLACE", "/run_receipt/batch_plan_sha256", "RUN_RECEIPT_BATCH_PLAN_HASH_MISMATCH"),
    MutationSpec("qualification_window_mismatch", "RUN_RECEIPT", "REPLACE", "/run_receipt/qualification_window", "RUN_RECEIPT_WINDOW_MISMATCH"),
    MutationSpec("cohort_mismatch", "RUN_RECEIPT", "REPLACE", "/run_receipt/cohort", "RUN_RECEIPT_COHORT_MISMATCH"),
    MutationSpec("scoped_manifest_hash_mismatch", "RUN_RECEIPT", "REPLACE", "/run_receipt/scoped_manifest_sha256", "RUN_RECEIPT_MANIFEST_HASH_MISMATCH"),
    MutationSpec("pending_gate_state_mismatch", "RUN_RECEIPT", "REPLACE", "/run_receipt/pending_gate_state", "RUN_RECEIPT_GATE_STATE_MISMATCH"),
    MutationSpec("missing_stage_binding", "STAGE_BINDING", "OMIT", "/stage_binding", "STAGE_BINDING_REQUIRED"),
    MutationSpec("malformed_stage_binding", "STAGE_BINDING", "REPLACE", "/stage_binding", "STAGE_BINDING_SCHEMA_INVALID"),
    MutationSpec("forged_stage_authentication_tag", "STAGE_BINDING", "REPLACE", "/stage_binding/authentication/tag", "STAGE_BINDING_AUTHENTICATION_FAILED"),
    MutationSpec("wrong_stage_key_id", "STAGE_BINDING", "REPLACE", "/stage_binding/authentication/key_id", "STAGE_BINDING_KEY_ID_MISMATCH"),
    MutationSpec("cross_run_stage_binding", "STAGE_BINDING", "REPLACE", "/stage_binding/run_id", "STAGE_BINDING_RUN_ID_MISMATCH"),
    MutationSpec("wrong_stage_id", "STAGE_BINDING", "REPLACE", "/stage_binding/stage_id", "STAGE_BINDING_STAGE_ID_MISMATCH"),
    MutationSpec("stage_manifest_hash_mismatch", "STAGE_BINDING", "REPLACE", "/stage_binding/stage_manifest_sha256", "STAGE_MANIFEST_HASH_MISMATCH"),
    MutationSpec("stage_tree_addition", "STAGE_BINDING", "INSERT_TREE_ENTRY", "/stage_tree", "STAGE_TREE_ADDITION_DETECTED"),
    MutationSpec("stage_tree_deletion", "STAGE_BINDING", "DELETE_TREE_ENTRY", "/stage_tree", "STAGE_TREE_DELETION_DETECTED"),
    MutationSpec("stage_tree_byte_drift", "STAGE_BINDING", "MUTATE_BYTES", "/stage_tree", "STAGE_TREE_HASH_MISMATCH"),
    MutationSpec("unsafe_stage_entry", "STAGE_BINDING", "INSERT_UNSAFE_ENTRY", "/stage_tree", "UNSAFE_STAGE_ENTRY"),
    MutationSpec("stage_tree_toc_tou", "STAGE_BINDING", "SWAP_AFTER_CHECK", "/stage_tree", "STAGE_TREE_CHANGED_DURING_VERIFICATION"),
    MutationSpec("stage_root_overlap_or_alias", "STAGE_BINDING", "ALIAS_ROOT", "/stage_binding/stage_root", "STAGE_ROOT_NOT_DISJOINT"),
    MutationSpec("stage_artifact_inventory_mismatch", "STAGE_BINDING", "REPLACE", "/stage_binding/artifacts", "STAGE_ARTIFACT_INVENTORY_MISMATCH"),
    MutationSpec("predecessor_binding_omission", "BINDING_GRAPH", "OMIT", "/predecessor_bindings", "PREDECESSOR_BINDING_REQUIRED"),
    MutationSpec("predecessor_binding_replay", "BINDING_GRAPH", "REPLACE", "/predecessor_bindings", "PREDECESSOR_BINDING_REPLAYED"),
    MutationSpec("predecessor_binding_wrong_stage", "BINDING_GRAPH", "REPLACE", "/predecessor_bindings/stage_id", "PREDECESSOR_STAGE_MISMATCH"),
    MutationSpec("five_security_denominator_promotion", "CLAIM_GATE", "PROMOTE_CLAIM", "/claims/denominator", "FIVE_SECURITY_DENOMINATOR_FORBIDDEN"),
    MutationSpec("full_market_claim_promotion", "CLAIM_GATE", "PROMOTE_CLAIM", "/claims/full_market", "FULL_MARKET_CLAIM_FORBIDDEN"),
    MutationSpec("benchmark_fallback_promotion", "CLAIM_GATE", "PROMOTE_CLAIM", "/claims/benchmark_status", "BENCHMARK_FALLBACK_FORBIDDEN"),
    MutationSpec("d01_policy_promotion", "CLAIM_GATE", "PROMOTE_CLAIM", "/claims/outcome_session_policy", "KU_BO_008_D01_OPEN"),
    MutationSpec("untrusted_legacy_claim_promotion", "CLAIM_GATE", "PROMOTE_CLAIM", "/claims/legacy_july", "UNTRUSTED_LEGACY_CLAIM_QUARANTINED"),
    MutationSpec("output_root_preexists", "OUTPUT_ATOMICITY", "PRECREATE_OUTPUT", "/output_root", "OUTPUT_ROOT_ALREADY_EXISTS"),
    MutationSpec("partial_output_on_rejection", "OUTPUT_ATOMICITY", "WRITE_THEN_REJECT", "/output_root", "PARTIAL_OUTPUT_FORBIDDEN"),
    MutationSpec("output_commit_toc_tou", "OUTPUT_ATOMICITY", "SWAP_AFTER_CHECK", "/output_root", "OUTPUT_ROOT_CHANGED_DURING_COMMIT"),
)


UNSAFE_ENTRY_VARIANTS = (
    ("parent_traversal", "../escape.bin"),
    ("absolute_path", "/tmp/escape.bin"),
    ("symlink", "raw/symlink.bin"),
    ("special_file", "raw/service.sock"),
)


_VALUE_PROFILES: dict[str, tuple[str | None, ...]] = {
    "missing_run_receipt": (
        "CLI_OPTION_ABSENT",
        "API_ARGUMENT_NONE",
        "RECEIPT_FILE_ABSENT",
        "VALID_RECEIPT_REMOVED_AFTER_CHECK",
    ),
    "malformed_run_receipt": (
        "CLI_PATH_POINTS_TO_ZERO_BYTE_FILE",
        "API_ARGUMENT_IS_NON_OBJECT",
        "SERIALIZED_RECEIPT_HAS_UNKNOWN_FIELD",
        "VALID_RECEIPT_SWAPPED_FOR_TRUNCATED_JSON",
    ),
    "forged_run_authentication_tag": (
        "SINGLE_HEX_NIBBLE_CHANGED",
        "AUTHENTICATION_TAG_TRUNCATED",
        "VALID_TAG_FROM_FOREIGN_PAYLOAD",
        "TAG_SWAPPED_AFTER_SCHEMA_VALIDATION",
    ),
    "wrong_run_key_id": (
        "UNKNOWN_KEY_ID",
        "STAGE_KEY_ID_USED_AS_RUN_KEY_ID",
        "RETIRED_RUN_KEY_ID",
        "KEY_ID_SWAPPED_AFTER_LOOKUP",
    ),
    "non_independent_authority": (
        "SAME_KEY_ID_FOR_RUN_AND_STAGE",
        "SAME_SECRET_BYTES_UNDER_TWO_KEY_IDS",
        "RUN_AUTHORITY_OBJECT_REUSED_FOR_STAGE",
        "STAGE_AUTHORITY_SWAPPED_TO_RUN_AUTHORITY",
    ),
    "expired_run_receipt": (
        "EXPIRES_ONE_SECOND_BEFORE_EVALUATION",
        "EXPIRES_ONE_DAY_BEFORE_EVALUATION",
        "EXPIRES_AT_EVALUATION_BOUNDARY",
        "CLOCK_ADVANCED_PAST_EXPIRY_AFTER_CHECK",
    ),
    "future_run_receipt": (
        "ISSUED_ONE_SECOND_AFTER_EVALUATION",
        "ISSUED_ONE_DAY_AFTER_EVALUATION",
        "VALID_FROM_AFTER_EVALUATION",
        "CLOCK_REWOUND_BEFORE_ISSUANCE_AFTER_CHECK",
    ),
    "cross_run_receipt": (
        "RECEIPT_FROM_PRIOR_RUN",
        "RECEIPT_FROM_LATER_RUN",
        "RECEIPT_FROM_SIBLING_BATCH_RUN",
        "RUN_ID_SWAPPED_AFTER_AUTHENTICATION",
    ),
    "wrong_receipt_audience": (
        "AUDIENCE_IS_DIAGNOSTIC_TOOL",
        "AUDIENCE_IS_DIFFERENT_IMPORTER",
        "AUDIENCE_IS_WILDCARD",
        "AUDIENCE_SWAPPED_AFTER_AUTHENTICATION",
    ),
    "wrong_batch_binding": (
        "BATCH_NUMBER_ZERO",
        "BATCH_NUMBER_TWO",
        "BATCH_NUMBER_FIVE_SECURITY_LEGACY",
        "BATCH_NUMBER_SWAPPED_AFTER_AUTHENTICATION",
    ),
    "batch_plan_hash_mismatch": (
        "ALL_ZERO_PLAN_DIGEST",
        "DIGEST_OF_REORDERED_PLAN",
        "DIGEST_OF_OTHER_BATCH_PLAN",
        "PLAN_BYTES_SWAPPED_AFTER_DIGEST_CHECK",
    ),
    "qualification_window_mismatch": (
        "WINDOW_START_SHIFTED_FORWARD",
        "WINDOW_END_SHIFTED_BACKWARD",
        "WINDOW_BOUNDS_REVERSED",
        "WINDOW_SWAPPED_AFTER_RECEIPT_CHECK",
    ),
    "cohort_mismatch": (
        "EXPECTED_SECURITY_REMOVED",
        "FOREIGN_SECURITY_ADDED",
        "SECURITY_DUPLICATED",
        "COHORT_ORDER_AND_IDENTITY_SWAPPED_AFTER_CHECK",
    ),
    "scoped_manifest_hash_mismatch": (
        "ALL_ZERO_MANIFEST_DIGEST",
        "DIGEST_OF_UNSCOPED_MANIFEST",
        "DIGEST_OF_OTHER_RUN_MANIFEST",
        "MANIFEST_BYTES_SWAPPED_AFTER_DIGEST_CHECK",
    ),
    "pending_gate_state_mismatch": (
        "PENDING_GATE_REMOVED",
        "PENDING_GATE_MARKED_PASS",
        "UNKNOWN_GATE_INSERTED",
        "GATE_STATE_SWAPPED_AFTER_RECEIPT_CHECK",
    ),
    "missing_stage_binding": (
        "CLI_OPTION_ABSENT",
        "API_ARGUMENT_NONE",
        "BINDING_FILE_ABSENT",
        "VALID_BINDING_REMOVED_AFTER_CHECK",
    ),
    "malformed_stage_binding": (
        "CLI_PATH_POINTS_TO_ZERO_BYTE_FILE",
        "API_ARGUMENT_IS_NON_OBJECT",
        "SERIALIZED_BINDING_HAS_UNKNOWN_FIELD",
        "VALID_BINDING_SWAPPED_FOR_TRUNCATED_JSON",
    ),
    "forged_stage_authentication_tag": (
        "SINGLE_HEX_NIBBLE_CHANGED",
        "AUTHENTICATION_TAG_TRUNCATED",
        "VALID_TAG_FROM_FOREIGN_STAGE_TREE",
        "TAG_SWAPPED_AFTER_SCHEMA_VALIDATION",
    ),
    "wrong_stage_key_id": (
        "UNKNOWN_KEY_ID",
        "RUN_KEY_ID_USED_AS_STAGE_KEY_ID",
        "RETIRED_STAGE_KEY_ID",
        "KEY_ID_SWAPPED_AFTER_LOOKUP",
    ),
    "cross_run_stage_binding": (
        "BINDING_FROM_PRIOR_RUN",
        "BINDING_FROM_LATER_RUN",
        "BINDING_FROM_SIBLING_BATCH_RUN",
        "BINDING_RUN_ID_SWAPPED_AFTER_AUTHENTICATION",
    ),
    "wrong_stage_id": (
        "PREDECESSOR_STAGE_ID_USED",
        "SUCCESSOR_STAGE_ID_USED",
        "UNKNOWN_STAGE_ID_USED",
        "STAGE_ID_SWAPPED_AFTER_AUTHENTICATION",
    ),
    "stage_manifest_hash_mismatch": (
        "ALL_ZERO_STAGE_MANIFEST_DIGEST",
        "DIGEST_OF_PARTIAL_STAGE_MANIFEST",
        "DIGEST_OF_FOREIGN_STAGE_MANIFEST",
        "STAGE_MANIFEST_SWAPPED_AFTER_DIGEST_CHECK",
    ),
    "stage_tree_addition": (
        "UNBOUND_REGULAR_FILE_ADDED",
        "UNBOUND_NESTED_DIRECTORY_ADDED",
        "UNBOUND_EMPTY_FILE_ADDED",
        "FILE_ADDED_AFTER_TREE_SNAPSHOT",
    ),
    "stage_tree_deletion": (
        "BOUND_REGULAR_FILE_REMOVED",
        "BOUND_EMPTY_FILE_REMOVED",
        "BOUND_NESTED_FILE_REMOVED",
        "FILE_REMOVED_AFTER_TREE_SNAPSHOT",
    ),
    "stage_tree_byte_drift": (
        "FIRST_BYTE_CHANGED_SAME_SIZE",
        "FILE_TRUNCATED",
        "FILE_EXTENDED",
        "BYTES_SWAPPED_AFTER_OPEN_HANDLE_CHECK",
    ),
    "unsafe_stage_entry": tuple(value for _, value in UNSAFE_ENTRY_VARIANTS),
    "stage_tree_toc_tou": (
        "FILE_RENAMED_BETWEEN_STAT_AND_OPEN",
        "DIRECTORY_REPLACED_BETWEEN_WALKS",
        "FILE_REPLACED_WITH_SYMLINK_AFTER_OPEN",
        "TREE_MUTATED_BEFORE_FINAL_IDENTITY_RECHECK",
    ),
    "stage_root_overlap_or_alias": (
        "STAGE_ROOT_EQUALS_RECEIPT_ROOT",
        "STAGE_ROOT_IS_CHILD_OF_OUTPUT_ROOT",
        "STAGE_ROOT_SYMLINK_ALIASES_RUN_ROOT",
        "ROOT_REPLACED_WITH_ALIAS_AFTER_DISJOINTNESS_CHECK",
    ),
    "stage_artifact_inventory_mismatch": (
        "DECLARED_ARTIFACT_MISSING_FROM_TREE",
        "TREE_ARTIFACT_MISSING_FROM_DECLARATION",
        "DECLARED_ARTIFACT_DIGEST_DIFFERS",
        "INVENTORY_SWAPPED_AFTER_BINDING_CHECK",
    ),
    "predecessor_binding_omission": (
        "PREDECESSOR_ARGUMENT_OMITTED",
        "PREDECESSOR_LIST_EMPTY",
        "PREDECESSOR_EDGE_ABSENT_FROM_ARTIFACT",
        "PREDECESSOR_EDGE_REMOVED_AFTER_GRAPH_CHECK",
    ),
    "predecessor_binding_replay": (
        "PREDECESSOR_FROM_PRIOR_RUN",
        "PREDECESSOR_FROM_PRIOR_BATCH",
        "DUPLICATE_PREDECESSOR_EDGE",
        "CURRENT_EDGE_SWAPPED_FOR_REPLAYED_EDGE",
    ),
    "predecessor_binding_wrong_stage": (
        "EDGE_NAMES_NON_PREDECESSOR_STAGE",
        "EDGE_REVERSES_STAGE_ORDER",
        "EDGE_SKIPS_REQUIRED_STAGE",
        "EDGE_STAGE_ID_SWAPPED_AFTER_GRAPH_CHECK",
    ),
    "five_security_denominator_promotion": (
        "CLI_REQUESTS_FIVE_SECURITY_DENOMINATOR",
        "API_RESULT_SETS_DENOMINATOR_TO_FIVE",
        "ARTIFACT_COPIES_LEGACY_FIVE_SECURITY_DENOMINATOR",
        "DENOMINATOR_PROMOTED_AFTER_CLAIM_CHECK",
    ),
    "full_market_claim_promotion": (
        "CLI_REQUESTS_FULL_MARKET_SCOPE",
        "API_RESULT_SETS_FULL_MARKET_TRUE",
        "ARTIFACT_LABELS_TRI_COHORT_FULL_MARKET",
        "FULL_MARKET_FLAG_PROMOTED_AFTER_CLAIM_CHECK",
    ),
    "benchmark_fallback_promotion": (
        "CLI_ALLOWS_GENERIC_BENCHMARK_FALLBACK",
        "API_ACCEPTS_INCOMPATIBLE_FIVE_SECURITY_SERIES",
        "ARTIFACT_MARKS_MISSING_SECTORS_QUALIFIED",
        "BENCHMARK_STATUS_PROMOTED_AFTER_CLAIM_CHECK",
    ),
    "d01_policy_promotion": (
        "CLI_SELECTS_D01_OPTION_WITHOUT_DECISION",
        "API_SETS_OUTCOME_POLICY_FROZEN",
        "ARTIFACT_EMBEDS_UNAPPROVED_POLICY",
        "D01_STATUS_PROMOTED_AFTER_CLAIM_CHECK",
    ),
    "untrusted_legacy_claim_promotion": (
        "CLI_IMPORTS_QUARANTINED_JULY_CLAIM",
        "API_MARKS_LEGACY_CLAIM_TRUSTED",
        "ARTIFACT_USES_LEGACY_CLAIM_AS_EVIDENCE",
        "LEGACY_STATUS_PROMOTED_AFTER_CLAIM_CHECK",
    ),
    "output_root_preexists": (
        "CLI_OUTPUT_PATH_ALREADY_EXISTS",
        "API_OUTPUT_DIRECTORY_ALREADY_EXISTS",
        "SERIALIZED_PLAN_TARGETS_EXISTING_OUTPUT",
        "OUTPUT_ROOT_CREATED_BY_RACER_AFTER_CHECK",
    ),
    "partial_output_on_rejection": (
        "CLI_FAILURE_LEAVES_REPORT_FILE",
        "API_FAILURE_LEAVES_TEMP_DIRECTORY",
        "ARTIFACT_FAILURE_LEAVES_NORMALIZED_BYTES",
        "RACE_FAILURE_LEAVES_PARTIAL_COMMIT",
    ),
    "output_commit_toc_tou": (
        "OUTPUT_PARENT_RENAMED_BEFORE_COMMIT",
        "OUTPUT_ROOT_REPLACED_BEFORE_COMMIT",
        "TEMP_OUTPUT_REPLACED_WITH_SYMLINK",
        "COMMIT_DESTINATION_CHANGED_AFTER_FINAL_CHECK",
    ),
}


TOTAL_CASES = len(BOUNDARIES) * len(MUTATIONS) * VARIANTS_PER_PAIR


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _iso8601(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _mutation_values(
    mutation: MutationSpec,
    *,
    profile: AttackProfile,
    variant_index: int,
) -> tuple[str | None, str | None, str | None, str]:
    try:
        values = _VALUE_PROFILES[mutation.mutation_id]
    except KeyError as exc:
        raise AssertionError(
            f"mutation has no semantic value profiles: {mutation.mutation_id}"
        ) from exc
    if len(values) != len(ATTACK_PROFILES):
        raise AssertionError(
            f"mutation must define {len(ATTACK_PROFILES)} semantic profiles: "
            f"{mutation.mutation_id}"
        )
    value = values[variant_index]
    secondary_value: str | None = (
        f"ORIGINAL_BOUND_VALUE_FOR_{mutation.target.strip('/').replace('/', '_').upper()}"
    )
    unsafe_entry_kind: str | None = None
    if mutation.mutation_id == "unsafe_stage_entry":
        unsafe_entry_kind, value = UNSAFE_ENTRY_VARIANTS[variant_index]
    attack_shape = (
        f"{mutation.operation} {mutation.target} through {profile.input_channel} "
        f"at {profile.timing}: {value or 'OMITTED'}"
    )
    return value, secondary_value, unsafe_entry_kind, attack_shape


def build_case(
    boundary_index: int,
    mutation_index: int,
    variant_index: int,
) -> dict[str, Any]:
    if not 0 <= boundary_index < len(BOUNDARIES):
        raise IndexError("boundary_index is out of range")
    if not 0 <= mutation_index < len(MUTATIONS):
        raise IndexError("mutation_index is out of range")
    if not 0 <= variant_index < VARIANTS_PER_PAIR:
        raise IndexError("variant_index is out of range")

    boundary = BOUNDARIES[boundary_index]
    mutation = MUTATIONS[mutation_index]
    profile = ATTACK_PROFILES[variant_index]
    case_index = (
        boundary_index * len(MUTATIONS) * VARIANTS_PER_PAIR
        + mutation_index * VARIANTS_PER_PAIR
        + variant_index
        + 1
    )
    case_id = (
        f"KU-BO-011-C{case_index:04d}-{boundary.boundary_id}-"
        f"{mutation.mutation_id}-V{variant_index:02d}"
    )
    token = _sha256(case_id)
    target_run_id = f"ku-bo-011-target-run-{case_index:04d}"
    evaluation_time = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc) + timedelta(
        minutes=case_index
    )
    receipt_run_id = target_run_id
    binding_run_id = target_run_id
    if mutation.mutation_id == "cross_run_receipt":
        receipt_run_id = f"foreign-receipt-run-{case_index:04d}"
    if mutation.mutation_id == "cross_run_stage_binding":
        binding_run_id = f"foreign-binding-run-{case_index:04d}"

    value, secondary_value, unsafe_entry_kind, attack_shape = _mutation_values(
        mutation,
        profile=profile,
        variant_index=variant_index,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "boundary": {
            "id": boundary.boundary_id,
            "cli_command": boundary.cli_command,
            "role": boundary.role,
            "write_surface": boundary.write_surface,
            "required_authorities": ["RUN_RECEIPT", "STAGE_BINDING"],
        },
        "mutation": {
            "id": mutation.mutation_id,
            "authority": mutation.authority,
            "operation": mutation.operation,
            "target": mutation.target,
            "variant_index": variant_index,
            "profile_id": profile.profile_id,
            "input_channel": profile.input_channel,
            "timing": profile.timing,
            "attack_shape": attack_shape,
            "value": value,
            "secondary_value": secondary_value,
            "unsafe_entry_kind": unsafe_entry_kind,
        },
        "context": {
            "case_seed_sha256": token,
            "target_run_id": target_run_id,
            "receipt_run_id": receipt_run_id,
            "binding_run_id": binding_run_id,
            "evaluation_time": _iso8601(evaluation_time),
            "stage_root": f"stage/ku_bo_011_case_{case_index:04d}",
            "output_root": f"output/ku_bo_011_case_{case_index:04d}",
        },
        "expected": {
            "decision": "REJECT",
            "failure_code": mutation.failure_code,
            "failure_phase": profile.failure_phase,
            "maximum_output_writes": 0,
            "market_evidence_claim": "NOT_EVALUATED",
        },
        "implementation_adapter_required": True,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def iter_cases() -> Iterator[dict[str, Any]]:
    for boundary_index in range(len(BOUNDARIES)):
        for mutation_index in range(len(MUTATIONS)):
            for variant_index in range(VARIANTS_PER_PAIR):
                yield build_case(boundary_index, mutation_index, variant_index)


def semantic_projection(case: dict[str, Any]) -> dict[str, Any]:
    """Return attack semantics with IDs, timestamps, and per-case path noise removed."""

    mutation = case["mutation"]
    return {
        "boundary": case["boundary"],
        "mutation": {
            key: value
            for key, value in mutation.items()
            if key not in {"variant_index", "profile_id"}
        },
        "expected": case["expected"],
        "implementation_adapter_required": case["implementation_adapter_required"],
        "claim_boundary": case["claim_boundary"],
    }


def case_dimensions() -> dict[str, int]:
    return {
        "boundaries": len(BOUNDARIES),
        "mutation_families": len(MUTATIONS),
        "variants_per_boundary_mutation_pair": VARIANTS_PER_PAIR,
    }
