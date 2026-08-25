#!/usr/bin/env python3
"""Validate the privacy-safe preparation controls for a private-source migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Mapping


CONTROL = Path(
    "docs/codex/migrations/private-predecessor-to-ku-bo/migration-control.json"
)
MANIFEST = Path("docs/codex/migrations/private-predecessor-to-ku-bo/manifest.json")
PARITY = Path(
    "docs/codex/migrations/private-predecessor-to-ku-bo/capability-parity.json"
)
ORIENTATION = Path(
    "docs/codex/migrations/private-predecessor-to-ku-bo/PRIVATE_SOURCE_ORIENTATION.md"
)
TASK = Path("docs/codex/CURRENT_TASK.md")
EXECPLAN = Path("docs/codex/PRIVATE_PREDECESSOR_MIGRATION_EXECPLAN.md")

EXPECTED_MIGRATION_ID = "KU-BO-MIG-001"
EXPECTED_BRANCH = "agent/private-predecessor-capability-migration-v1"
EXPECTED_PR_BASE = "agent/ku-bo-016-codex-live-bootstrap"
EXPECTED_TARGET_REPOSITORY = "mohsamir7122/ku-bo"
EXPECTED_SOURCE_ALIAS = "PRIVATE_PREDECESSOR_SOURCE"
EXPECTED_CAPABILITIES = frozenset(
    f"private-cap-{index:03d}" for index in range(1, 15)
)
EXPECTED_REF_ROLES = {
    "private-ref-primary": "PRIMARY_REF_AT_EXECUTION",
    "private-ref-known-reference": "KNOWN_UNMERGED_REFERENCE_AT_EXECUTION",
}
EXPECTED_READ_SCOPE = {
    "private_source_repository_read_allowed": True,
    "repository_code_and_git_metadata_only": True,
    "runtime_private_data_read_allowed": False,
    "credentials_or_secret_material_read_allowed": False,
    "private_locator_publication_allowed": False,
}
EXPECTED_PERMISSIONS = {
    "main_write_allowed": False,
    "merge_allowed": False,
    "force_push_allowed": False,
    "permanent_delete_or_archive_allowed": False,
    "source_repository_write_allowed": False,
    "private_runtime_data_access_allowed": False,
    "credential_export_allowed": False,
    "licensed_or_paid_source_activation_allowed": False,
    "real_data_commit_allowed": False,
    "model_training_allowed": False,
    "real_backtest_allowed": False,
    "live_activation_allowed": False,
    "financial_execution_allowed": False,
}
EXPECTED_COMPLETION_EVIDENCE = {
    "preparation_validator_can_claim_migration_complete": False,
    "dedicated_completion_validator_required": True,
    "private_source_runtime_receipt_required": True,
    "source_tree_and_blob_reconciliation_required": True,
    "sanitized_user_job_denominator_required": True,
    "semantic_and_negative_parity_receipts_required": True,
    "full_test_and_package_receipt_required": True,
    "exact_head_ci_receipt_required": True,
    "draft_pr_state_receipt_required": True,
    "merge_not_performed_required": True,
}
EXPECTED_CONTROL_CLAIMS = {
    "preparation_is_migration_complete": False,
    "capability_parity_is_live_operational": False,
    "software_migration_is_real_backtest_ready": False,
    "synthetic_tests_prove_predictive_skill": False,
    "score_is_probability": False,
    "research_candidate_is_buy_recommendation": False,
    "source_definition_proves_access_or_rights": False,
}
GIT_OID_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")
OPAQUE_ID_RE = re.compile(r"^(?:opaque|private-receipt)-[a-z0-9][a-z0-9._-]{2,127}$")
PUBLIC_ITEM_ID_RE = re.compile(r"^migration-item-[a-z0-9][a-z0-9._-]{2,127}$")


class MigrationControlError(ValueError):
    """Raised when preparation controls are inconsistent, unsafe, or overstated."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationControlError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise MigrationControlError(f"non-finite JSON value is forbidden: {value}")


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MigrationControlError(f"cannot load strict JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise MigrationControlError(f"JSON root must be an object: {path}")
    return payload


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MigrationControlError(f"{field} must be an object")
    return value


def _require(value: Any, expected: Any, field: str) -> None:
    if value != expected:
        raise MigrationControlError(f"{field} does not match the locked preparation contract")


def _exact_mapping(value: Any, expected: Mapping[str, Any], field: str) -> None:
    item = _mapping(value, field)
    if dict(item) != dict(expected):
        raise MigrationControlError(f"{field} is incomplete, extended, or unsafe")


def _string_list(value: Any, field: str, *, nonempty: bool) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise MigrationControlError(f"{field} must be a{' non-empty' if nonempty else ''} list")
    if any(not isinstance(item, str) or not item for item in value):
        raise MigrationControlError(f"{field} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise MigrationControlError(f"{field} must not contain duplicates")
    return value


def _validate_ref_roles(value: Any, field: str) -> None:
    if not isinstance(value, list) or len(value) != len(EXPECTED_REF_ROLES):
        raise MigrationControlError(f"{field} must contain the two opaque ref roles")
    actual: dict[str, str] = {}
    for index, row in enumerate(value):
        item = _mapping(row, f"{field}[{index}]")
        if set(item) != {"ref_id", "role", "locator_storage"}:
            raise MigrationControlError(f"{field}[{index}] has unexpected fields")
        ref_id = item.get("ref_id")
        role = item.get("role")
        if not isinstance(ref_id, str) or not isinstance(role, str) or ref_id in actual:
            raise MigrationControlError(f"{field} ref IDs and roles must be unique strings")
        _require(item.get("locator_storage"), "PRIVATE_RUNTIME_ONLY", f"{field} locator storage")
        actual[ref_id] = role
    _require(actual, EXPECTED_REF_ROLES, field)


def _reject_private_metadata(payloads: list[Mapping[str, Any]], orientation: str) -> None:
    serialized = json.dumps(payloads, ensure_ascii=True, sort_keys=True)
    lowered = (serialized + "\n" + orientation).lower()
    forbidden_markers = (
        "drive.google.com",
        "docs.google.com",
        "access_token",
        "refresh_token",
        "sessionid",
        "private-user-images",
        "github.com/",  # source locators must never appear in source-control JSON
        "refs/heads/",
    )
    found = [marker for marker in forbidden_markers if marker in lowered]
    if found:
        raise MigrationControlError(
            "public migration controls contain a private locator or credential marker: "
            + ",".join(found)
        )
    source_surfaces = json.dumps(payloads[1:], ensure_ascii=True, sort_keys=True)
    if GIT_OID_RE.search(source_surfaces) or GIT_OID_RE.search(orientation):
        raise MigrationControlError("public source controls must not publish private Git OIDs")


def _validate_control(payload: Mapping[str, Any]) -> None:
    if set(payload) != {
        "schema_version",
        "migration_id",
        "status",
        "target",
        "source",
        "authorized_read_scope",
        "architecture",
        "permissions",
        "phase_order",
        "required_seed_capabilities",
        "required_artifacts",
        "completion_evidence_contract",
        "claim_boundaries",
    }:
        raise MigrationControlError("control root has unexpected fields")
    _require(payload.get("schema_version"), "1.1", "control.schema_version")
    _require(payload.get("migration_id"), EXPECTED_MIGRATION_ID, "control.migration_id")
    _require(
        payload.get("status"),
        "READY_FOR_PRIVATE_SOURCE_ORIENTATION",
        "control.status",
    )

    target = _mapping(payload.get("target"), "control.target")
    if set(target) != {
        "repository",
        "canonical_single_codebase",
        "control_base_branch",
        "control_base_sha",
        "task_branch",
        "expected_pr_base",
        "package_root",
        "cli",
        "pr_mode",
    }:
        raise MigrationControlError("control.target has unexpected fields")
    _require(target.get("repository"), EXPECTED_TARGET_REPOSITORY, "target.repository")
    _require(target.get("canonical_single_codebase"), True, "target.canonical_single_codebase")
    _require(target.get("control_base_branch"), EXPECTED_PR_BASE, "target.control_base_branch")
    base_sha = target.get("control_base_sha")
    if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        raise MigrationControlError("target.control_base_sha must be a public 40-hex Git OID")
    _require(target.get("task_branch"), EXPECTED_BRANCH, "target.task_branch")
    _require(target.get("expected_pr_base"), EXPECTED_PR_BASE, "target.expected_pr_base")
    _require(target.get("package_root"), "src/kubo", "target.package_root")
    _require(target.get("cli"), "kubo", "target.cli")
    _require(target.get("pr_mode"), "DRAFT", "target.pr_mode")

    source = _mapping(payload.get("source"), "control.source")
    if set(source) != {
        "public_alias",
        "repository_locator_storage",
        "write_allowed",
        "git_history_merge_allowed",
        "discover_additional_unique_refs",
        "required_ref_roles",
        "inventory_scope",
        "sensitive_locator_policy",
    }:
        raise MigrationControlError("control.source has unexpected or locator-bearing fields")
    _require(source.get("public_alias"), EXPECTED_SOURCE_ALIAS, "source.public_alias")
    _require(
        source.get("repository_locator_storage"),
        "PRIVATE_RUNTIME_ONLY",
        "source.repository_locator_storage",
    )
    _require(source.get("write_allowed"), False, "source.write_allowed")
    _require(source.get("git_history_merge_allowed"), False, "source.git_history_merge_allowed")
    _require(
        source.get("discover_additional_unique_refs"),
        True,
        "source.discover_additional_unique_refs",
    )
    _require(
        source.get("sensitive_locator_policy"),
        "OPAQUE_PUBLIC_ID_PRIVATE_RUNTIME_LOCATOR",
        "source.sensitive_locator_policy",
    )
    _validate_ref_roles(source.get("required_ref_roles"), "source.required_ref_roles")

    _exact_mapping(payload.get("authorized_read_scope"), EXPECTED_READ_SCOPE, "authorized_read_scope")
    _exact_mapping(payload.get("permissions"), EXPECTED_PERMISSIONS, "permissions")
    _exact_mapping(
        payload.get("completion_evidence_contract"),
        EXPECTED_COMPLETION_EVIDENCE,
        "completion_evidence_contract",
    )
    _exact_mapping(payload.get("claim_boundaries"), EXPECTED_CONTROL_CLAIMS, "claim_boundaries")

    architecture = _mapping(payload.get("architecture"), "control.architecture")
    if set(architecture) != {
        "migration_mode",
        "blind_file_merge_allowed",
        "second_engine_allowed",
        "second_package_allowed",
        "conflicting_registry_allowed",
        "skills_policy",
        "unsafe_behavior_policy",
    }:
        raise MigrationControlError("control.architecture has unexpected fields")
    _require(
        architecture.get("migration_mode"),
        "COMPLETE_CAPABILITY_REIMPLEMENTATION",
        "architecture.migration_mode",
    )
    _require(
        architecture.get("skills_policy"),
        "THIN_WRAPPERS_OVER_KUBO_CORE",
        "architecture.skills_policy",
    )
    for field in (
        "blind_file_merge_allowed",
        "second_engine_allowed",
        "second_package_allowed",
        "conflicting_registry_allowed",
    ):
        _require(architecture.get(field), False, f"architecture.{field}")

    capability_ids = _string_list(
        payload.get("required_seed_capabilities"),
        "required_seed_capabilities",
        nonempty=True,
    )
    if frozenset(capability_ids) != EXPECTED_CAPABILITIES:
        raise MigrationControlError("opaque seed capability set is not locked")
    required_artifacts = _string_list(
        payload.get("required_artifacts"), "required_artifacts", nonempty=True
    )
    for required in (MANIFEST, PARITY, ORIENTATION):
        if required.as_posix() not in required_artifacts:
            raise MigrationControlError(f"required artifact is missing: {required}")


def _validate_manifest(payload: Mapping[str, Any]) -> None:
    if set(payload) != {
        "schema_version",
        "migration_id",
        "public_summary_status",
        "source_alias",
        "declared_source_ref_roles",
        "private_inventory_receipt_id",
        "private_inventory_receipt_storage",
        "sanitized_items",
        "public_item_contract",
        "completion_claim_allowed",
        "claim_boundaries",
    }:
        raise MigrationControlError("manifest root has unexpected or locator-bearing fields")
    _require(payload.get("schema_version"), "1.1", "manifest.schema_version")
    _require(payload.get("migration_id"), EXPECTED_MIGRATION_ID, "manifest.migration_id")
    if payload.get("public_summary_status") not in {
        "NOT_STARTED",
        "IN_PROGRESS",
        "BLOCKED",
        "PRIVATE_CENSUS_RECEIPT_AVAILABLE",
    }:
        raise MigrationControlError("manifest public_summary_status cannot claim completion")
    _require(payload.get("source_alias"), EXPECTED_SOURCE_ALIAS, "manifest.source_alias")
    _validate_ref_roles(
        payload.get("declared_source_ref_roles"), "manifest.declared_source_ref_roles"
    )
    receipt_id = payload.get("private_inventory_receipt_id")
    if receipt_id is not None and (
        not isinstance(receipt_id, str) or not OPAQUE_ID_RE.fullmatch(receipt_id)
    ):
        raise MigrationControlError("private_inventory_receipt_id must be opaque")
    _require(
        payload.get("private_inventory_receipt_storage"),
        "UNCOMMITTED_RUNTIME_ONLY",
        "manifest.private_inventory_receipt_storage",
    )
    _require(payload.get("completion_claim_allowed"), False, "manifest.completion_claim_allowed")

    contract = {
        "normal_source_locator_allowed_after_privacy_review": True,
        "sensitive_source_locator_allowed": False,
        "sensitive_item_public_id_format": "opaque-LOWERCASE_TOKEN",
        "source_commit_or_tree_oid_publication_allowed": False,
        "private_inventory_count_publication_allowed": False,
    }
    _exact_mapping(payload.get("public_item_contract"), contract, "manifest.public_item_contract")
    _exact_mapping(
        payload.get("claim_boundaries"),
        {
            "empty_public_summary_proves_inventory": False,
            "private_receipt_id_alone_proves_inventory": False,
            "preparation_validator_proves_source_access": False,
            "preparation_validator_proves_migration_completion": False,
        },
        "manifest.claim_boundaries",
    )

    items = payload.get("sanitized_items")
    if not isinstance(items, list):
        raise MigrationControlError("manifest.sanitized_items must be a list")
    seen: set[str] = set()
    allowed_fields = {
        "item_id",
        "private_binding_id",
        "classification",
        "privacy_review_status",
        "capability_ids",
        "user_job_ids",
        "target_paths",
        "migration_status",
        "sanitized_reason",
    }
    for index, row in enumerate(items):
        item = _mapping(row, f"manifest.sanitized_items[{index}]")
        if set(item) != allowed_fields:
            raise MigrationControlError("sanitized item has missing or locator-bearing fields")
        item_id = item.get("item_id")
        binding_id = item.get("private_binding_id")
        if not isinstance(item_id, str) or not PUBLIC_ITEM_ID_RE.fullmatch(item_id):
            raise MigrationControlError("sanitized item_id is invalid")
        if item_id in seen:
            raise MigrationControlError("sanitized item IDs must be unique")
        seen.add(item_id)
        if not isinstance(binding_id, str) or not OPAQUE_ID_RE.fullmatch(binding_id):
            raise MigrationControlError("private_binding_id must be opaque")
        _require(item.get("privacy_review_status"), "SAFE_TO_PUBLISH", "item privacy review")
        _string_list(item.get("capability_ids"), "item capability_ids", nonempty=True)
        _string_list(item.get("user_job_ids"), "item user_job_ids", nonempty=True)
        _string_list(item.get("target_paths"), "item target_paths", nonempty=False)
        reason = item.get("sanitized_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise MigrationControlError("sanitized item reason is required")


def _validate_parity(payload: Mapping[str, Any]) -> int:
    if set(payload) != {
        "schema_version",
        "migration_id",
        "denominator_status",
        "source_binding",
        "capabilities",
        "user_jobs",
        "completion_claim_allowed",
        "claim_boundaries",
    }:
        raise MigrationControlError("parity root has unexpected or locator-bearing fields")
    _require(payload.get("schema_version"), "1.1", "parity.schema_version")
    _require(payload.get("migration_id"), EXPECTED_MIGRATION_ID, "parity.migration_id")
    if payload.get("denominator_status") not in {
        "PRIVATE_DISCOVERY_NOT_STARTED",
        "PRIVATE_DISCOVERY_IN_PROGRESS",
        "SANITIZED_DENOMINATOR_DRAFT",
    }:
        raise MigrationControlError("preparation parity denominator cannot claim completion")
    _require(payload.get("source_binding"), "PRIVATE_RUNTIME_ONLY", "parity.source_binding")
    _require(payload.get("completion_claim_allowed"), False, "parity.completion_claim_allowed")
    _exact_mapping(
        payload.get("claim_boundaries"),
        {
            "opaque_seed_is_capability_definition": False,
            "empty_user_jobs_is_complete_denominator": False,
            "preparation_matrix_proves_parity": False,
            "preparation_matrix_proves_live_operation": False,
        },
        "parity.claim_boundaries",
    )
    rows = payload.get("capabilities")
    if not isinstance(rows, list) or not rows:
        raise MigrationControlError("opaque capability seeds are required")
    identifiers: set[str] = set()
    bindings: set[str] = set()
    for index, row in enumerate(rows):
        item = _mapping(row, f"parity.capabilities[{index}]")
        if set(item) != {
            "capability_id",
            "private_source_binding_id",
            "mapping_status",
            "implementation_status",
            "contract_parity_status",
            "user_job_parity_status",
            "runtime_capability_status",
            "evidence_status",
            "required_test_classes",
        }:
            raise MigrationControlError("capability row has unexpected or locator-bearing fields")
        capability_id = item.get("capability_id")
        binding_id = item.get("private_source_binding_id")
        if not isinstance(capability_id, str) or capability_id in identifiers:
            raise MigrationControlError("capability IDs must be unique strings")
        if not isinstance(binding_id, str) or not binding_id.startswith("private-binding-"):
            raise MigrationControlError("private source binding must be opaque")
        if binding_id in bindings:
            raise MigrationControlError("private source bindings must be unique")
        identifiers.add(capability_id)
        bindings.add(binding_id)
        if item.get("runtime_capability_status") not in {"DEFINED_ONLY", "END_TO_END_TESTED"}:
            raise MigrationControlError("preparation parity contains unsafe runtime status")
        if item.get("evidence_status") not in {
            "PRIVATE_SOURCE_DISCOVERY_REQUIRED",
            "CODE_ONLY",
            "SYNTHETIC_ONLY",
            "RECORDED_AUTHORIZED_FIXTURE",
            "LIVE_DEPENDENT",
            "LICENSED_FEED_DEPENDENT",
        }:
            raise MigrationControlError("preparation parity contains unsafe evidence status")
        tests = _string_list(
            item.get("required_test_classes"),
            f"required_test_classes for {capability_id}",
            nonempty=True,
        )
        if len(tests) < 2:
            raise MigrationControlError("semantic and negative test classes are required")
    if not EXPECTED_CAPABILITIES.issubset(identifiers):
        raise MigrationControlError("one or more opaque seed capabilities are missing")
    user_jobs = payload.get("user_jobs")
    if not isinstance(user_jobs, list):
        raise MigrationControlError("parity.user_jobs must be a list")
    allowed_job_fields = {
        "user_job_id",
        "private_binding_ids",
        "capability_ids",
        "sanitized_contract_id",
        "disposition_status",
        "privacy_review_status",
        "semantic_test_ids",
        "negative_test_ids",
        "software_blockers",
        "operational_blockers",
    }
    seen_jobs: set[str] = set()
    for index, row in enumerate(user_jobs):
        job = _mapping(row, f"parity.user_jobs[{index}]")
        if set(job) != allowed_job_fields:
            raise MigrationControlError("user-job row has unexpected or locator-bearing fields")
        job_id = job.get("user_job_id")
        if not isinstance(job_id, str) or not job_id or job_id in seen_jobs:
            raise MigrationControlError("user-job IDs must be unique non-empty strings")
        seen_jobs.add(job_id)
        binding_ids = _string_list(
            job.get("private_binding_ids"), "user-job private bindings", nonempty=True
        )
        if any(not binding.startswith("private-binding-") for binding in binding_ids):
            raise MigrationControlError("user-job private bindings must be opaque")
        _string_list(job.get("capability_ids"), "user-job capability IDs", nonempty=True)
        _string_list(job.get("semantic_test_ids"), "user-job semantic tests", nonempty=False)
        _string_list(job.get("negative_test_ids"), "user-job negative tests", nonempty=False)
        _string_list(job.get("software_blockers"), "user-job software blockers", nonempty=False)
        _string_list(job.get("operational_blockers"), "user-job operational blockers", nonempty=False)
        _require(job.get("privacy_review_status"), "SAFE_TO_PUBLISH", "user-job privacy review")
    return len(rows)


def validate(project_root: Path | str) -> dict[str, Any]:
    root = Path(project_root).resolve()
    control = _load(root / CONTROL)
    manifest = _load(root / MANIFEST)
    parity = _load(root / PARITY)
    orientation = (root / ORIENTATION).read_text(encoding="utf-8")
    _reject_private_metadata([control, manifest, parity], orientation)
    _validate_control(control)
    _validate_manifest(manifest)
    capability_count = _validate_parity(parity)

    task_text = (root / TASK).read_text(encoding="utf-8")
    execplan_text = (root / EXECPLAN).read_text(encoding="utf-8")
    for marker in (
        EXPECTED_MIGRATION_ID,
        EXPECTED_BRANCH,
        f"EXPECTED_PR_BASE: {EXPECTED_PR_BASE}",
        "PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: YES",
        "PRIVATE_RUNTIME_DATA_ACCESS_ALLOWED: NO",
        "MERGE_ALLOWED: NO",
    ):
        if marker not in task_text:
            raise MigrationControlError(f"CURRENT_TASK is missing marker: {marker}")
    for marker in (
        "Private source census and authenticated receipt",
        "User-job denominator",
        "Dedicated completion validator",
        "MERGE_NOT_PERFORMED",
    ):
        if marker not in execplan_text:
            raise MigrationControlError(f"ExecPlan is missing marker: {marker}")
    for marker in (
        "no private repository locator",
        "Authorized read boundary",
        "uncommitted private runtime record",
        "validates preparation only",
    ):
        if marker not in orientation:
            raise MigrationControlError(f"private-source orientation is missing marker: {marker}")

    return {
        "schema_version": "1.1",
        "status": "PASS_PREPARATION_CONTROL",
        "migration_id": EXPECTED_MIGRATION_ID,
        "task_branch": EXPECTED_BRANCH,
        "expected_pr_base": EXPECTED_PR_BASE,
        "source_alias": EXPECTED_SOURCE_ALIAS,
        "private_source_repository_read_allowed": True,
        "private_runtime_data_access_allowed": False,
        "opaque_seed_capability_count": len(EXPECTED_CAPABILITIES),
        "parity_row_count": capability_count,
        "completion_claim_allowed": False,
        "claim_boundaries": {
            "validator_proves_source_inventory": False,
            "validator_proves_capability_parity": False,
            "validator_proves_migration_complete": False,
            "validator_authorizes_merge": False,
            "validator_proves_live_operational": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--project-root", type=Path, default=Path.cwd())
    result.add_argument("--json", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = validate(args.project_root)
    except (MigrationControlError, OSError, UnicodeError) as exc:
        report = {"schema_version": "1.1", "status": "FAIL", "error": str(exc)}
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
