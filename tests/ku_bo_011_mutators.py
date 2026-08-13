from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from types import MappingProxyType
from typing import Any, Iterator, Mapping


SCHEMA_VERSION = "ku-bo-011-adversarial-case-v3"
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


@dataclass(frozen=True)
class MaterializationSpec:
    artifact: str
    field: str
    action: str
    resign_policy: str
    value: str | None


MATERIALIZATION_INGRESS_BY_CHANNEL: Mapping[str, str] = MappingProxyType(
    {
        "CLI_ARGUMENT": "CLI_PARSER_TO_PUBLIC_BOUNDARY",
        "DIRECT_API_OBJECT": "DIRECT_PUBLIC_BOUNDARY",
        "SERIALIZED_ARTIFACT": "SERIALIZED_ADMISSION_TO_PUBLIC_BOUNDARY",
        "FILESYSTEM_RACE": "PUBLIC_BOUNDARY_PRE_COMMIT_HOOK",
    }
)


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
    ("symlink_with_fifo_fallback", "raw/unsafe-link.bin"),
)


def _materialization_spec(
    artifact: str,
    field: str,
    action: str,
    resign_policy: str,
    value: str | None,
) -> MaterializationSpec:
    return MaterializationSpec(artifact, field, action, resign_policy, value)


MATERIALIZATION_SPECS: Mapping[str, MaterializationSpec] = MappingProxyType(
    {
        "missing_run_receipt": _materialization_spec(
            "RUN_RECEIPT_FILE", "/", "DELETE_FILE", "NOT_APPLICABLE", None
        ),
        "malformed_run_receipt": _materialization_spec(
            "RUN_RECEIPT_FILE", "/", "WRITE_TRUNCATED_JSON", "NOT_APPLICABLE", '{"truncated":'
        ),
        "forged_run_authentication_tag": _materialization_spec(
            "RUN_RECEIPT_FILE", "/authentication/tag", "FLIP_FIRST_TAG_NIBBLE", "PRESERVE_STALE_AUTHENTICATION", "one changed hex nibble"
        ),
        "wrong_run_key_id": _materialization_spec(
            "RUN_RECEIPT_FILE", "/authentication/key_id", "SET_UNKNOWN_KEY_ID", "PRESERVE_STALE_AUTHENTICATION", "unknown-ku-bo-011-run-key"
        ),
        "non_independent_authority": _materialization_spec(
            "BOUNDARY_ADMISSION_REQUEST", "/v1_stage_key", "REUSE_RUN_SECRET_AS_STAGE_SECRET", "NOT_APPLICABLE", "request.run_key"
        ),
        "expired_run_receipt": _materialization_spec(
            "RUN_RECEIPT_FILE", "/expires_at", "SET_EXPIRY_BEFORE_DECISION", "RESIGN_WITH_RUN_AUTHORITY", "decision_at minus 1 second"
        ),
        "future_run_receipt": _materialization_spec(
            "RUN_RECEIPT_FILE", "/issued_at", "SET_ISSUANCE_AFTER_DECISION", "RESIGN_WITH_RUN_AUTHORITY", "issued_at=decision_at+1s; expires_at=issued_at+1h; recompute run_date"
        ),
        "cross_run_receipt": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/run_binding/run_id", "SET_FOREIGN_RUN_ID", "RESIGN_WITH_SEMANTIC_AUTHORITY", "foreign-${target_run_id}"
        ),
        "wrong_receipt_audience": _materialization_spec(
            "RUN_RECEIPT_FILE", "/audience", "SET_FOREIGN_AUDIENCE", "RESIGN_WITH_RUN_AUTHORITY", "foreign-diagnostic-audience"
        ),
        "wrong_batch_binding": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/run_binding/batch_id", "SET_FOREIGN_BATCH_ID", "RESIGN_WITH_SEMANTIC_AUTHORITY", "tri-999-foreign-batch"
        ),
        "batch_plan_hash_mismatch": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/run_binding/batch_plan_sha256", "SET_ZERO_SHA256", "RESIGN_WITH_SEMANTIC_AUTHORITY", "0 repeated 64 times"
        ),
        "qualification_window_mismatch": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/run_binding/qualification_window", "REPLACE_QUALIFICATION_WINDOW", "RESIGN_WITH_SEMANTIC_AUTHORITY", "2026-08-02..2026-08-12 Asia/Kuwait"
        ),
        "cohort_mismatch": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/run_binding/cohort", "REPLACE_WITH_EMPTY_ZERO_HASH_COHORT", "RESIGN_WITH_SEMANTIC_AUTHORITY", "security_count=3; zero cohort hash; empty securities"
        ),
        "scoped_manifest_hash_mismatch": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/run_binding/scoped_manifest_sha256", "SET_ZERO_SHA256", "RESIGN_WITH_SEMANTIC_AUTHORITY", "0 repeated 64 times"
        ),
        "pending_gate_state_mismatch": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/run_binding/pending_gate_state", "REMOVE_FIRST_GATE", "RESIGN_WITH_SEMANTIC_AUTHORITY", "remove first insertion-ordered gate"
        ),
        "missing_stage_binding": _materialization_spec(
            "STAGE_BINDING_FILE", "/", "DELETE_FILE", "NOT_APPLICABLE", None
        ),
        "malformed_stage_binding": _materialization_spec(
            "STAGE_BINDING_FILE", "/", "WRITE_TRUNCATED_JSON", "NOT_APPLICABLE", '{"truncated":'
        ),
        "forged_stage_authentication_tag": _materialization_spec(
            "STAGE_BINDING_FILE", "/authentication/tag", "FLIP_LAST_TAG_NIBBLE", "PRESERVE_STALE_AUTHENTICATION", "one changed hex nibble"
        ),
        "wrong_stage_key_id": _materialization_spec(
            "STAGE_BINDING_FILE", "/authentication/key_id", "SET_UNKNOWN_KEY_ID", "PRESERVE_STALE_AUTHENTICATION", "unknown-ku-bo-011-stage-key"
        ),
        "cross_run_stage_binding": _materialization_spec(
            "STAGE_BINDING_FILE", "/run_binding/run_id", "SET_FOREIGN_RUN_ID", "RESIGN_WITH_STAGE_AUTHORITY", "foreign-${target_run_id}"
        ),
        "wrong_stage_id": _materialization_spec(
            "STAGE_BINDING_FILE", "/stage_id", "SET_OTHER_STAGE_ID", "RESIGN_WITH_STAGE_AUTHORITY", "STATUS_CORPORATE unless current is STATUS_CORPORATE, otherwise OFFICIAL_FOUNDATION"
        ),
        "stage_manifest_hash_mismatch": _materialization_spec(
            "BOUNDARY_ADMISSION_REQUEST", "/expected_stage_manifest_sha256", "SET_ZERO_SHA256", "NOT_APPLICABLE", "0 repeated 64 times"
        ),
        "stage_tree_addition": _materialization_spec(
            "STAGE_INPUT_TREE", "/raw/unbound.bin", "WRITE_UNBOUND_FILE", "NOT_APPLICABLE", "unbound stage-tree addition"
        ),
        "stage_tree_deletion": _materialization_spec(
            "STAGE_INPUT_TREE", "/raw/evidence.bin", "DELETE_FILE", "NOT_APPLICABLE", None
        ),
        "stage_tree_byte_drift": _materialization_spec(
            "STAGE_INPUT_TREE", "/raw/evidence.bin", "OVERWRITE_FILE_BYTES", "NOT_APPLICABLE", "mutated stage bytes"
        ),
        "unsafe_stage_entry": _materialization_spec(
            "STAGE_INPUT_TREE", "/raw/unsafe-link.bin", "CREATE_SYMLINK_WITH_FIFO_FALLBACK", "NOT_APPLICABLE", "outside-stage.bin; FIFO fallback raw/unsafe-fifo"
        ),
        "stage_tree_toc_tou": _materialization_spec(
            "STAGE_INPUT_TREE", "/ku-bo-011-race-marker.bin", "INJECT_FILE_AFTER_FIRST_TREE_SCAN", "NOT_APPLICABLE", "inserted after first production tree scan"
        ),
        "stage_root_overlap_or_alias": _materialization_spec(
            "VERIFIED_OUTPUT_BINDING", "/output_root", "SET_OUTPUT_ROOT_INSIDE_STAGE", "NOT_APPLICABLE", "input_root/overlapping-output"
        ),
        "stage_artifact_inventory_mismatch": _materialization_spec(
            "STAGE_BINDING_FILE", "/stage_artifact/complete_file_count", "INCREMENT_INTEGER", "RESIGN_WITH_STAGE_AUTHORITY", "+1"
        ),
        "predecessor_binding_omission": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/predecessor_bindings", "REPLACE_WITH_EMPTY_LIST", "RESIGN_WITH_SEMANTIC_AUTHORITY", "[]"
        ),
        "predecessor_binding_replay": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/predecessor_bindings/-", "APPEND_COPY_OF_FIRST_ROW", "RESIGN_WITH_SEMANTIC_AUTHORITY", "copy predecessor_bindings[0]"
        ),
        "predecessor_binding_wrong_stage": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/predecessor_bindings/0/stage_id", "SET_WRONG_PREDECESSOR_STAGE", "RESIGN_WITH_SEMANTIC_AUTHORITY", "WRONG_PREDECESSOR_STAGE"
        ),
        "five_security_denominator_promotion": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/claims/denominator", "SET_CLAIM_VALUE", "RESIGN_WITH_SEMANTIC_AUTHORITY", "FIVE_SECURITY_COHORT"
        ),
        "full_market_claim_promotion": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/claims/full_market", "SET_CLAIM_VALUE", "RESIGN_WITH_SEMANTIC_AUTHORITY", "true"
        ),
        "benchmark_fallback_promotion": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/claims/benchmark_fallback_allowed", "SET_CLAIM_VALUE", "RESIGN_WITH_SEMANTIC_AUTHORITY", "true"
        ),
        "d01_policy_promotion": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/claims/outcome_session_policy", "SET_CLAIM_VALUE", "RESIGN_WITH_SEMANTIC_AUTHORITY", "FROZEN_D01_APPROVED"
        ),
        "untrusted_legacy_claim_promotion": _materialization_spec(
            "SEMANTIC_ADMISSION_FILE", "/claims/legacy_july", "SET_CLAIM_VALUE", "RESIGN_WITH_SEMANTIC_AUTHORITY", "TRUSTED_LEGACY_CLAIM"
        ),
        "output_root_preexists": _materialization_spec(
            "ATOMIC_OUTPUT_TRANSACTION", "/output_root", "CREATE_OUTPUT_ROOT_WITH_RACER_FILE", "NOT_APPLICABLE", "racer.txt=fixture-owned output racer"
        ),
        "partial_output_on_rejection": _materialization_spec(
            "ATOMIC_STAGING_DIRECTORY", "/partial.txt", "WRITE_STAGED_FILE_THEN_RAISE", "NOT_APPLICABLE", "this partial candidate must never be published; then RuntimeError"
        ),
        "output_commit_toc_tou": _materialization_spec(
            "ATOMIC_OUTPUT_TRANSACTION", "/output_root", "CREATE_OUTPUT_ROOT_WITH_RACER_FILE", "NOT_APPLICABLE", "racer.txt=fixture-owned output racer"
        ),
    }
)


EXPECTED_REJECTION_OVERRIDES: Mapping[
    tuple[str, int], tuple[str, str]
] = MappingProxyType(
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
    }
)
EXPECTED_REJECTION_OVERRIDE_RULE_COUNT = 4
EXPECTED_REJECTION_OVERRIDE_CASE_COUNT = 32
EXPECTED_FAILURE_CODE_OVERRIDE_CASE_COUNT = 16
EXPECTED_FAILURE_PHASE_OVERRIDE_CASE_COUNT = 24


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
) -> tuple[str | None, str | None, str | None, str, dict[str, Any]]:
    try:
        spec = MATERIALIZATION_SPECS[mutation.mutation_id]
    except KeyError as exc:
        raise AssertionError(
            f"mutation has no production materializer: {mutation.mutation_id}"
        ) from exc

    timing_by_channel = {
        "CLI_ARGUMENT": "BEFORE_CLI_PARSE_AND_PUBLIC_BOUNDARY",
        "DIRECT_API_OBJECT": "BEFORE_DIRECT_PUBLIC_BOUNDARY",
        "SERIALIZED_ARTIFACT": "BEFORE_SERIALIZED_ARTIFACT_ADMISSION",
        "FILESYSTEM_RACE": "PUBLIC_BOUNDARY_PRE_COMMIT_RECHECK",
    }
    artifact = spec.artifact
    field = spec.field
    action = spec.action
    resign_policy = spec.resign_policy
    value = spec.value
    actual_timing = timing_by_channel[profile.input_channel]

    if mutation.mutation_id in {"missing_run_receipt", "missing_stage_binding"}:
        if variant_index < 2:
            artifact = "BOUNDARY_ADMISSION_REQUEST"
            field = (
                "/receipt_path"
                if mutation.mutation_id == "missing_run_receipt"
                else "/stage_binding_path"
            )
            action = "SET_REQUEST_PATH_NONE"
        else:
            action = "DELETE_FILE"
    elif mutation.mutation_id == "stage_tree_toc_tou":
        actual_timing = "DURING_PRODUCTION_TREE_DOUBLE_SNAPSHOT"
    elif mutation.mutation_id == "partial_output_on_rejection":
        actual_timing = "INSIDE_ATOMIC_OUTPUT_WORKER_AFTER_ADMISSION"
    elif mutation.mutation_id == "output_commit_toc_tou":
        actual_timing = "PUBLIC_BOUNDARY_PRE_COMMIT_RECHECK"
        if variant_index == 2:
            artifact = "ATOMIC_STAGING_DIRECTORY"
            field = "/"
            action = "DELETE_STAGING_DIRECTORY"
            value = None

    materialization = {
        "handler_id": mutation.mutation_id,
        "ingress": MATERIALIZATION_INGRESS_BY_CHANNEL[profile.input_channel],
        "artifact": artifact,
        "field": field,
        "action": action,
        "timing": actual_timing,
        "resign_policy": resign_policy,
        "value": value,
    }
    secondary_value: str | None = None
    unsafe_entry_kind: str | None = None
    if mutation.mutation_id == "unsafe_stage_entry":
        unsafe_entry_kind, _ = UNSAFE_ENTRY_VARIANTS[0]
    attack_shape = (
        f"handler_id={mutation.mutation_id}; ingress={materialization['ingress']}; "
        f"action={action}; artifact={artifact}; field={field}; "
        f"timing={actual_timing}; resign_policy={resign_policy}; "
        f"value={value if value is not None else 'null'}"
    )
    return value, secondary_value, unsafe_entry_kind, attack_shape, materialization


def _expected_rejection(
    mutation: MutationSpec,
    profile: AttackProfile,
    variant_index: int,
) -> tuple[str, str]:
    """Return the code and phase at the production detection point.

    Most cases retain the mutation-family code and attack-channel phase. The
    explicit overrides are the small locked set where the channel label is
    earlier than the point at which atomic output can actually detect the
    failure.
    """

    if not 0 <= variant_index < VARIANTS_PER_PAIR:
        raise IndexError("variant_index is out of range")
    return EXPECTED_REJECTION_OVERRIDES.get(
        (mutation.mutation_id, variant_index),
        (mutation.failure_code, profile.failure_phase),
    )


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

    (
        value,
        secondary_value,
        unsafe_entry_kind,
        attack_shape,
        materialization,
    ) = _mutation_values(
        mutation,
        profile=profile,
        variant_index=variant_index,
    )
    failure_code, failure_phase = _expected_rejection(
        mutation,
        profile,
        variant_index,
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
        "materialization": materialization,
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
            "failure_code": failure_code,
            "failure_phase": failure_phase,
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
