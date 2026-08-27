"""Validate private Factor 9 inventory and admission evidence.

Private file locators and bytes remain outside Git. This module accepts only
logical paths, hashes, sizes, source roles, and review states.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .codex_live_bootstrap import EXPECTED_FACTOR9
from .foundation_io import (
    load_strict_json_object,
    require_real_directory,
    safe_regular_file,
)
from .hashing import canonical_json_bytes
from .strict import parse_aware, require_sha256, safe_relative_path


COUNT_KEYS = frozenset(
    {
        "company_master_rows",
        "price_tickers",
        "original_price_rows",
        "clean_price_rows",
        "excluded_price_rows",
        "reported_validation_issues",
    }
)
EXPECTED_GATES = tuple(EXPECTED_FACTOR9["admission_gates"])
EXPECTED_BLOCKERS = tuple(EXPECTED_FACTOR9["known_blockers"])
EXPECTED_ARTIFACT_ROLES = frozenset(EXPECTED_FACTOR9["preserve_without_recomputing"])
CLAIM_BOUNDARIES = {
    "storage_presence_grants_rights": False,
    "asset_is_training_truth": False,
    "asset_is_validated_model": False,
    "probability_allowed": False,
    "recommendation_allowed": False,
    "automatic_promotion_allowed": False,
}
ROOT_KEYS = frozenset(
    {
        "schema_version",
        "inventory_id",
        "generated_at",
        "asset",
        "counts",
        "artifacts",
        "gates",
        "blockers",
        "claim_boundaries",
    }
)
ARTIFACT_KEYS = frozenset(
    {
        "logical_path",
        "sha256",
        "size_bytes",
        "artifact_role",
        "original_source",
        "capture_method",
        "rights_status",
        "point_in_time_status",
        "review_status",
        "duplicate_disposition",
    }
)
GATE_KEYS = frozenset({"gate_id", "status", "evidence_sha256"})
BLOCKER_KEYS = frozenset({"blocker_id", "status", "evidence_sha256"})
GATE_STATES = frozenset({"PASS", "FAIL", "UNKNOWN", "NOT_REVIEWED"})
BLOCKER_STATES = frozenset({"OPEN", "RESOLVED", "UNKNOWN"})
RIGHTS_STATES = frozenset(
    {"AUTHORIZED", "LICENSED", "PUBLIC_ACCESS_ONLY", "REQUIRES_RUNTIME_REVIEW", "UNKNOWN"}
)
POINT_IN_TIME_STATES = frozenset({"PROVEN", "PARTIAL", "UNPROVEN"})
REVIEW_STATES = frozenset({"APPROVED", "REVIEW_REQUIRED", "REJECTED"})
DUPLICATE_STATES = frozenset({"CANONICAL_CANDIDATE", "QUARANTINE_DUPLICATE"})
ORIGINAL_SOURCES = frozenset(
    {"MUBASHER_SECONDARY", "USER_AUTHORIZED_EXPORT", "OFFICIAL_DISCLOSURE", "INTERNAL_DERIVED", "UNKNOWN"}
)
CAPTURE_METHODS = frozenset(
    {"AUTHORIZED_EXPORT", "HISTORICAL_PROJECT_ARTIFACT", "OFFICIAL_DOWNLOAD", "UNKNOWN"}
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_PRIVATE_LOCATOR_MARKERS = (
    "://",
    "oauth",
    "access_token",
    "connector_id",
    "folder_id",
    "file_id",
    "webviewlink",
    "/folders/",
    "/file/d/",
)


class Factor9AdmissionError(ValueError):
    """Raised when private inventory cannot support Factor 9 admission."""


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        return load_strict_json_object(
            path,
            field="Factor 9 manifest",
            max_bytes=16 * 1024 * 1024,
        )
    except ValueError as exc:
        raise Factor9AdmissionError(f"cannot load strict Factor 9 manifest: {path}") from exc


def _exact(value: Any, expected: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Factor9AdmissionError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != expected:
        raise Factor9AdmissionError(
            f"{field} has missing={sorted(expected - actual)} unknown={sorted(actual - expected)}"
        )
    return value


def _private_locator_leak(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered_key = str(key).casefold()
            if any(marker in lowered_key for marker in ("folder_id", "file_id", "connector_id", "webviewlink")):
                return True
            if _private_locator_leak(item):
                return True
        return False
    if isinstance(value, list):
        return any(_private_locator_leak(item) for item in value)
    if isinstance(value, str):
        lowered = value.casefold()
        return any(marker in lowered for marker in _PRIVATE_LOCATOR_MARKERS)
    return False


def _canonical_hash(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise Factor9AdmissionError(f"{field} must be a lowercase SHA-256")
    try:
        digest = require_sha256(value, field)
    except ValueError as exc:
        raise Factor9AdmissionError(str(exc)) from exc
    if digest != value:
        raise Factor9AdmissionError(f"{field} must be a lowercase SHA-256")
    return digest


def _hashes(value: Any, field: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(digest, str) for digest in value)
        or len(value) != len(set(value))
    ):
        raise Factor9AdmissionError(f"{field} must be a unique hash array")
    result: list[str] = []
    for index, digest in enumerate(value):
        result.append(_canonical_hash(digest, f"{field}[{index}]"))
    return tuple(result)


def _validate_artifacts(
    rows: Any,
    *,
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    if not isinstance(rows, list) or not rows:
        raise Factor9AdmissionError("Factor 9 artifacts must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    by_hash: dict[str, list[str]] = {}
    roles: set[str] = set()
    reopened_hashes: set[str] = set()
    for index, row in enumerate(rows):
        item = _exact(row, ARTIFACT_KEYS, f"artifacts[{index}]")
        logical_path = item["logical_path"]
        if not isinstance(logical_path, str) or "\\" in logical_path:
            raise Factor9AdmissionError(f"artifacts[{index}].logical_path must use logical POSIX separators")
        try:
            relative = safe_relative_path(logical_path, f"artifacts[{index}].logical_path")
        except ValueError as exc:
            raise Factor9AdmissionError(str(exc)) from exc
        canonical_path = relative.as_posix()
        if not canonical_path.startswith("PRIVATE_INVENTORY/"):
            raise Factor9AdmissionError(
                "Factor 9 logical paths must use the private inventory alias"
            )
        relative_parts = relative.parts[1:]
        if not relative_parts:
            raise Factor9AdmissionError("Factor 9 logical path must name an artifact")
        if canonical_path in seen_paths:
            raise Factor9AdmissionError(f"duplicate Factor 9 logical path: {canonical_path}")
        seen_paths.add(canonical_path)
        digest = _canonical_hash(item["sha256"], f"artifacts[{index}].sha256")
        size = item["size_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise Factor9AdmissionError(f"artifacts[{index}].size_bytes must be a positive integer")
        role = item["artifact_role"]
        if role not in EXPECTED_ARTIFACT_ROLES:
            raise Factor9AdmissionError(f"artifacts[{index}].artifact_role is unknown")
        roles.add(str(role))
        if item["original_source"] not in ORIGINAL_SOURCES:
            raise Factor9AdmissionError(f"artifacts[{index}].original_source is unknown")
        if item["capture_method"] not in CAPTURE_METHODS:
            raise Factor9AdmissionError(f"artifacts[{index}].capture_method is unknown")
        if item["rights_status"] not in RIGHTS_STATES:
            raise Factor9AdmissionError(f"artifacts[{index}].rights_status is invalid")
        if item["point_in_time_status"] not in POINT_IN_TIME_STATES:
            raise Factor9AdmissionError(f"artifacts[{index}].point_in_time_status is invalid")
        if item["review_status"] not in REVIEW_STATES:
            raise Factor9AdmissionError(f"artifacts[{index}].review_status is invalid")
        if item["duplicate_disposition"] not in DUPLICATE_STATES:
            raise Factor9AdmissionError(f"artifacts[{index}].duplicate_disposition is invalid")
        artifact_path = artifact_root.joinpath(*relative_parts)
        try:
            content = safe_regular_file(
                artifact_path,
                field=f"Factor 9 artifact {canonical_path}",
                max_bytes=512 * 1024 * 1024,
            )
        except ValueError as exc:
            raise Factor9AdmissionError(
                f"cannot reopen Factor 9 artifact from trusted root: {canonical_path}"
            ) from exc
        actual_digest = hashlib.sha256(content).hexdigest()
        if len(content) != size:
            raise Factor9AdmissionError(
                f"Factor 9 artifact size mismatch: {canonical_path}"
            )
        if actual_digest != digest:
            raise Factor9AdmissionError(
                f"Factor 9 artifact hash mismatch: {canonical_path}"
            )
        reopened_hashes.add(actual_digest)
        by_hash.setdefault(digest, []).append(str(item["duplicate_disposition"]))
        normalized.append({**item, "logical_path": canonical_path, "sha256": digest})

    for digest, dispositions in by_hash.items():
        if len(dispositions) > 1 and dispositions.count("CANONICAL_CANDIDATE") != 1:
            raise Factor9AdmissionError(
                f"duplicate hash {digest} needs one canonical candidate and quarantined copies"
            )
    return normalized, roles, reopened_hashes


def _validate_counts(value: Any) -> dict[str, int]:
    counts = _exact(value, COUNT_KEYS, "counts")
    normalized: dict[str, int] = {}
    for key, raw in counts.items():
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise Factor9AdmissionError(f"counts.{key} must be a non-negative integer")
        normalized[str(key)] = raw
    for key in ("company_master_rows", "price_tickers", "original_price_rows", "clean_price_rows"):
        if normalized[key] == 0:
            raise Factor9AdmissionError(f"counts.{key} must be positive")
    if (
        normalized["original_price_rows"]
        != normalized["clean_price_rows"] + normalized["excluded_price_rows"]
    ):
        raise Factor9AdmissionError("Factor 9 raw/clean/excluded reconciliation failed")
    return normalized


def _validate_state_rows(
    rows: Any,
    *,
    expected_ids: tuple[str, ...],
    keys: frozenset[str],
    id_key: str,
    allowed_states: frozenset[str],
    field: str,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) != len(expected_ids):
        raise Factor9AdmissionError(f"{field} must contain the complete denominator")
    normalized: list[dict[str, Any]] = []
    ids: list[str] = []
    for index, row in enumerate(rows):
        item = _exact(row, keys, f"{field}[{index}]")
        identifier = item[id_key]
        if identifier not in expected_ids or identifier in ids:
            raise Factor9AdmissionError(f"{field} has a duplicate or unknown identifier")
        if item["status"] not in allowed_states:
            raise Factor9AdmissionError(f"{field}[{index}].status is invalid")
        evidence = _hashes(item["evidence_sha256"], f"{field}[{index}].evidence_sha256")
        if item["status"] in {"PASS", "RESOLVED"} and not evidence:
            raise Factor9AdmissionError(f"{field}[{index}] cannot pass without hash-bound evidence")
        ids.append(str(identifier))
        normalized.append({id_key: identifier, "status": item["status"], "evidence_sha256": list(evidence)})
    if tuple(ids) != expected_ids:
        raise Factor9AdmissionError(f"{field} rows must follow the locked order")
    return normalized


def validate_factor9_admission_manifest(
    path: Path | str,
    artifact_root: Path | str,
) -> dict[str, Any]:
    """Validate one private manifest and return an admission decision."""

    manifest_path = Path(path)
    try:
        trusted_artifact_root = require_real_directory(
            Path(artifact_root), field="Factor 9 trusted artifact root"
        )
    except ValueError as exc:
        raise Factor9AdmissionError(str(exc)) from exc
    payload, manifest_content = _load(manifest_path)
    if _private_locator_leak(payload):
        raise Factor9AdmissionError("private Drive or connector locator leaked into the manifest")
    _exact(payload, ROOT_KEYS, "Factor 9 manifest")
    if payload["schema_version"] != "1.0":
        raise Factor9AdmissionError("unsupported Factor 9 manifest schema")
    inventory_id = payload["inventory_id"]
    if not isinstance(inventory_id, str) or not _ID_RE.fullmatch(inventory_id):
        raise Factor9AdmissionError("inventory_id is not canonical")
    try:
        generated_at = parse_aware(payload["generated_at"], "generated_at")
    except ValueError as exc:
        raise Factor9AdmissionError(str(exc)) from exc
    if payload["asset"] != {
        "status": "RESEARCH_ASSET_PENDING_ADMISSION",
        "promotion_ceiling": "RESEARCH_INPUT_ONLY",
    }:
        raise Factor9AdmissionError("Factor 9 asset state or promotion ceiling was weakened")
    counts = _validate_counts(payload["counts"])
    if payload["claim_boundaries"] != CLAIM_BOUNDARIES:
        raise Factor9AdmissionError("Factor 9 claim boundaries were weakened")

    artifacts, artifact_roles, reopened_hashes = _validate_artifacts(
        payload["artifacts"], artifact_root=trusted_artifact_root
    )
    gates = _validate_state_rows(
        payload["gates"],
        expected_ids=EXPECTED_GATES,
        keys=GATE_KEYS,
        id_key="gate_id",
        allowed_states=GATE_STATES,
        field="gates",
    )
    blockers = _validate_state_rows(
        payload["blockers"],
        expected_ids=EXPECTED_BLOCKERS,
        keys=BLOCKER_KEYS,
        id_key="blocker_id",
        allowed_states=BLOCKER_STATES,
        field="blockers",
    )
    for collection_name, rows in (("gates", gates), ("blockers", blockers)):
        for row in rows:
            missing_evidence = sorted(set(row["evidence_sha256"]) - reopened_hashes)
            if row["status"] in {"PASS", "RESOLVED"} and missing_evidence:
                raise Factor9AdmissionError(
                    f"{collection_name} evidence is not a reopened manifest artifact"
                )
    missing_roles = sorted(EXPECTED_ARTIFACT_ROLES - artifact_roles)
    artifact_blocked = any(
        row["rights_status"] not in {"AUTHORIZED", "LICENSED"}
        or row["point_in_time_status"] != "PROVEN"
        or row["review_status"] != "APPROVED"
        or row["duplicate_disposition"] != "CANONICAL_CANDIDATE"
        for row in artifacts
    )
    pending_gates = [row["gate_id"] for row in gates if row["status"] != "PASS"]
    open_blockers = [row["blocker_id"] for row in blockers if row["status"] != "RESOLVED"]
    admitted = not missing_roles and not artifact_blocked and not pending_gates and not open_blockers

    return {
        "schema_version": "1.0",
        "status": "ADMITTED_RESEARCH_INPUT_ONLY" if admitted else "RESEARCH_ASSET_PENDING_ADMISSION",
        "inventory_id": inventory_id,
        "generated_at": generated_at.isoformat(),
        "manifest_sha256": hashlib.sha256(manifest_content).hexdigest(),
        "counts": counts,
        "artifact_count": len(artifacts),
        "reopened_artifact_count": len(artifacts),
        "artifact_integrity_status": "PASS_REOPENED_AND_HASHED",
        "missing_artifact_roles": missing_roles,
        "pending_gates": pending_gates,
        "open_blockers": open_blockers,
        "admission_allowed": admitted,
        "promotion_ceiling": "RESEARCH_INPUT_ONLY",
        "model_training_allowed": False,
        "claim_boundaries": CLAIM_BOUNDARIES,
    }


def write_factor9_admission_report(
    manifest_path: Path | str,
    artifact_root: Path | str,
    output_path: Path | str,
) -> dict[str, Any]:
    """Write a sanitized, no-overwrite admission report."""

    report = validate_factor9_admission_manifest(manifest_path, artifact_root)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        parent = require_real_directory(output.parent, field="Factor 9 report parent")
    except ValueError as exc:
        raise Factor9AdmissionError(str(exc)) from exc
    target = parent / output.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(target, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(canonical_json_bytes(report))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise Factor9AdmissionError(f"refusing to overwrite Factor 9 report: {output}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return report


__all__ = [
    "CLAIM_BOUNDARIES",
    "COUNT_KEYS",
    "EXPECTED_BLOCKERS",
    "EXPECTED_GATES",
    "Factor9AdmissionError",
    "validate_factor9_admission_manifest",
    "write_factor9_admission_report",
]
