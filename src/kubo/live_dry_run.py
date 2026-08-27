"""Resumable, no-network daily dry-run orchestration for KU-BO-017."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .catalog import Catalog
from .champion_freeze import ChampionFreezeError, validate_champion_freeze
from .codex_live_bootstrap import EXPECTED_PRODUCTS, EXPECTED_STAGES
from .context_research import DEFAULT_FACTOR_REGISTRY, validate_factor_snapshot
from .evidence import EvidenceManifest
from .foundation_io import (
    load_strict_json_object,
    require_real_directory,
    safe_regular_file,
)
from .hashing import canonical_json_bytes, hash_json, sha256_file
from .pack import PackValidator
from .recovery import (
    ActiveLeaseError,
    LeaseError,
    LeaseRecoveryBlockedError,
    acquire_recovery_lease,
    current_process_identity,
    heartbeat_recovery_lease,
    load_recovery_policy,
    release_recovery_lease,
    sanitize_text,
    stable_fingerprint,
)
from .source_access_executor import PROBE_PURPOSE, PROBE_VERSION
from .source_network import SourceNetworkCatalog, validate_live_probe
from .strict import parse_aware, parse_iso_date, require_sha256


DRY_RUN_CLAIM_BOUNDARIES = {
    "network_collection_performed": False,
    "model_training_performed": False,
    "research_candidate_emitted": False,
    "recommendation_emitted": False,
}
RUN_CONTRACT_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "decision_session_date",
        "mode",
        "stages",
        "products",
        "input_bindings",
        "input_validations",
        "claim_boundaries",
    }
)
INPUT_BINDING_KEYS = frozenset(
    {
        "source_probe_sha256",
        "raw_evidence_manifest_sha256",
        "normalized_snapshot_sha256",
        "factor_snapshot_sha256",
        "champion_freeze_sha256",
    }
)
INPUT_VALIDATION_KEYS = frozenset(
    {
        "source_probe",
        "raw_evidence_manifest",
        "normalized_snapshot",
        "factor_snapshot",
        "champion_freeze",
    }
)
VALIDATION_RECORD_KEYS = frozenset(
    {
        "artifact_sha256",
        "validator_id",
        "validator_status",
        "authorization_status",
        "validator_result",
        "validator_report_sha256",
    }
)
VALIDATOR_RESULT_KEYS = frozenset({"status", "object_id", "errors", "facts"})
VALIDATOR_IDS = {
    "source_probe": "kubo.source_network.validate_live_probe@3.1",
    "raw_evidence_manifest": "kubo.evidence.EvidenceManifest@2.0",
    "normalized_snapshot": "kubo.pack.PackValidator@2.0",
    "factor_snapshot": "kubo.context_research.validate_factor_snapshot@1.0",
    "champion_freeze": "kubo.champion_freeze.validate_champion_freeze@1.0",
}
RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "sequence",
        "stage",
        "status",
        "recorded_at",
        "previous_receipt_sha256",
        "input_sha256",
        "output_sha256",
        "reason_codes",
        "claim_boundaries",
    }
)
REPORT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "run_id",
        "decision_session_date",
        "stage_count",
        "receipt_count",
        "last_receipt_sha256",
        "blocked_stage",
        "products",
        "candidate_count",
        "claim_boundaries",
    }
)
SEALED_OUTPUT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "decision_session_date",
        "products",
        "claim_boundaries",
    }
)
SEALED_PRODUCT_KEYS = frozenset(
    {
        "product_id",
        "horizon_sessions",
        "decision",
        "candidates",
        "entry_price",
        "exit_price",
    }
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_PRIVATE_MARKERS = (
    "://",
    "connector_id",
    "folder_id",
    "file_id",
    "webviewlink",
    "oauth",
    "access_token",
)


class LiveDryRunError(ValueError):
    """Raised when a dry-run cannot preserve ordering, privacy, or immutability."""


class LiveDryRunLockError(LiveDryRunError):
    """Raised when another process owns the run lock."""


def _load(path: Path, field: str) -> dict[str, Any]:
    try:
        payload, _ = load_strict_json_object(
            path,
            field=field,
            max_bytes=16 * 1024 * 1024,
        )
    except ValueError as exc:
        raise LiveDryRunError(f"cannot load strict {field}: {path}") from exc
    return payload


def _exact(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveDryRunError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise LiveDryRunError(
            f"{field} has missing={sorted(keys - actual)} unknown={sorted(actual - keys)}"
        )
    return value


def _canonical_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise LiveDryRunError(f"{field} must be a lowercase SHA-256")
    try:
        digest = require_sha256(value, field)
    except ValueError as exc:
        raise LiveDryRunError(str(exc)) from exc
    if digest != value:
        raise LiveDryRunError(f"{field} must be a lowercase SHA-256")
    return digest


def _validate_input_bindings(value: Any) -> Mapping[str, Any]:
    bindings = _exact(value, INPUT_BINDING_KEYS, "input_bindings")
    probes = bindings["source_probe_sha256"]
    if (
        not isinstance(probes, list)
        or any(not isinstance(digest, str) for digest in probes)
        or len(probes) != len(set(probes))
    ):
        raise LiveDryRunError("source_probe_sha256 must be a unique array")
    for index, digest in enumerate(probes):
        _canonical_sha256(digest, f"source_probe_sha256[{index}]")

    for field in (
        "raw_evidence_manifest_sha256",
        "normalized_snapshot_sha256",
        "factor_snapshot_sha256",
    ):
        digest = bindings[field]
        if digest is not None:
            _canonical_sha256(digest, field)

    freeze_hashes = bindings["champion_freeze_sha256"]
    expected_products = frozenset(row["product_id"] for row in EXPECTED_PRODUCTS)
    if not isinstance(freeze_hashes, Mapping) or frozenset(freeze_hashes) != expected_products:
        raise LiveDryRunError("champion_freeze_sha256 must bind all four products exactly")
    for product_id, digest in freeze_hashes.items():
        if digest is not None:
            _canonical_sha256(digest, f"champion_freeze_sha256.{product_id}")
    return bindings


def _validate_validation_record(
    value: Any,
    *,
    field: str,
    expected_artifact_sha256: str,
    expected_validator_id: str,
) -> Mapping[str, Any]:
    record = _exact(value, VALIDATION_RECORD_KEYS, field)
    if record["artifact_sha256"] != expected_artifact_sha256:
        raise LiveDryRunError(f"{field} is not bound to its input artifact")
    if record["validator_id"] != expected_validator_id:
        raise LiveDryRunError(f"{field} uses a non-canonical validator")
    status = record["validator_status"]
    if status not in {"PASS", "BLOCKED"}:
        raise LiveDryRunError(f"{field}.validator_status is invalid")
    expected_authorization = (
        "CANONICAL_AUTHORIZED_INPUT" if status == "PASS" else "REJECTED_INPUT"
    )
    if record["authorization_status"] != expected_authorization:
        raise LiveDryRunError(f"{field}.authorization_status conflicts with validation")
    result = _exact(record["validator_result"], VALIDATOR_RESULT_KEYS, f"{field}.validator_result")
    if result["status"] != status:
        raise LiveDryRunError(f"{field} result status differs from validator_status")
    object_id = result["object_id"]
    if object_id is not None and (
        not isinstance(object_id, str) or not object_id or len(object_id) > 256
    ):
        raise LiveDryRunError(f"{field}.object_id is invalid")
    errors = result["errors"]
    if (
        not isinstance(errors, list)
        or len(errors) > 128
        or any(not isinstance(item, str) or not item or len(item) > 512 for item in errors)
        or len(errors) != len(set(errors))
    ):
        raise LiveDryRunError(f"{field}.errors must be a bounded unique string array")
    if status == "PASS" and errors:
        raise LiveDryRunError(f"{field} cannot pass with validator errors")
    if not isinstance(result["facts"], Mapping):
        raise LiveDryRunError(f"{field}.facts must be an object")
    if _contains_private_locator(record):
        raise LiveDryRunError(f"{field} contains a private locator")
    expected_report_sha = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if record["validator_report_sha256"] != expected_report_sha:
        raise LiveDryRunError(f"{field} validator report hash mismatch")
    return record


def _validate_input_validations(
    value: Any,
    *,
    bindings: Mapping[str, Any],
) -> Mapping[str, Any]:
    validations = _exact(value, INPUT_VALIDATION_KEYS, "input_validations")
    probes = validations["source_probe"]
    if not isinstance(probes, list) or len(probes) != len(bindings["source_probe_sha256"]):
        raise LiveDryRunError("source probe validation denominator differs from bindings")
    for index, record in enumerate(probes):
        _validate_validation_record(
            record,
            field=f"input_validations.source_probe[{index}]",
            expected_artifact_sha256=bindings["source_probe_sha256"][index],
            expected_validator_id=VALIDATOR_IDS["source_probe"],
        )
    optional_pairs = (
        ("raw_evidence_manifest", "raw_evidence_manifest_sha256"),
        ("normalized_snapshot", "normalized_snapshot_sha256"),
        ("factor_snapshot", "factor_snapshot_sha256"),
    )
    for validation_key, binding_key in optional_pairs:
        record = validations[validation_key]
        digest = bindings[binding_key]
        if digest is None:
            if record is not None:
                raise LiveDryRunError(f"{validation_key} validation exists without an input")
            continue
        if record is None:
            raise LiveDryRunError(f"{validation_key} input lacks canonical validation")
        _validate_validation_record(
            record,
            field=f"input_validations.{validation_key}",
            expected_artifact_sha256=digest,
            expected_validator_id=VALIDATOR_IDS[validation_key],
        )
    freezes = validations["champion_freeze"]
    expected_products = frozenset(row["product_id"] for row in EXPECTED_PRODUCTS)
    if not isinstance(freezes, Mapping) or frozenset(freezes) != expected_products:
        raise LiveDryRunError("champion freeze validations must bind all four products")
    for product_id, record in freezes.items():
        digest = bindings["champion_freeze_sha256"][product_id]
        if digest is None:
            if record is not None:
                raise LiveDryRunError("champion validation exists without a freeze input")
            continue
        if record is None:
            raise LiveDryRunError("champion freeze input lacks canonical validation")
        _validate_validation_record(
            record,
            field=f"input_validations.champion_freeze.{product_id}",
            expected_artifact_sha256=digest,
            expected_validator_id=VALIDATOR_IDS["champion_freeze"],
        )
    return validations


def _safe_validator_error(value: Any) -> str:
    text = sanitize_text(value, max_length=512)
    if _contains_private_locator(text) or "/" in text or "\\" in text:
        return "REDACTED_VALIDATOR_ERROR_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16].upper()
    return text


def _validation_record(
    path: Path,
    *,
    validator_id: str,
    object_id: str | None,
    errors: Sequence[Any],
    facts: Mapping[str, Any],
    authorized: bool,
) -> dict[str, Any]:
    try:
        content = safe_regular_file(path, field="live dry-run input", max_bytes=64 * 1024 * 1024)
    except ValueError as exc:
        raise LiveDryRunError(str(exc)) from exc
    normalized_errors = sorted({_safe_validator_error(item) for item in errors})
    status = "PASS" if authorized and not normalized_errors else "BLOCKED"
    result = {
        "status": status,
        "object_id": object_id,
        "errors": normalized_errors,
        "facts": dict(facts),
    }
    if _contains_private_locator(result):
        raise LiveDryRunError("canonical validator result leaked a private locator")
    return {
        "artifact_sha256": hashlib.sha256(content).hexdigest(),
        "validator_id": validator_id,
        "validator_status": status,
        "authorization_status": (
            "CANONICAL_AUTHORIZED_INPUT" if status == "PASS" else "REJECTED_INPUT"
        ),
        "validator_result": result,
        "validator_report_sha256": hashlib.sha256(canonical_json_bytes(result)).hexdigest(),
    }


def _fixture_path(runtime_root: Path, path: Path) -> bool:
    relative = path.relative_to(runtime_root)
    blocked_parts = {"fixture", "fixtures", "sample", "samples", "testdata", "tests"}
    return any(part.casefold() in blocked_parts for part in relative.parts)


def _canonical_validate_input(
    kind: str,
    path: Path,
    *,
    project_root: Path,
    runtime_root: Path,
    decision_date: date,
    recorded_at: datetime,
    raw_validation: Mapping[str, Any] | None = None,
    expected_pack_root: Path | None = None,
    product: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validator_id = VALIDATOR_IDS[kind]
    errors: list[Any] = []
    facts: dict[str, Any] = {}
    object_id: str | None = None
    authorized = False
    try:
        if _fixture_path(runtime_root, path):
            raise ValueError("FIXTURE_PATH_NOT_AUTHORIZED")
        if kind == "source_probe":
            if path.name != "access-probe.json":
                raise ValueError("NON_CANONICAL_ACCESS_PROBE_FILENAME")
            payload = _load(path, "canonical source access probe")
            if payload.get("probe_version") != PROBE_VERSION or payload.get("purpose") != PROBE_PURPOSE:
                raise ValueError("ACCESS_PROBE_NOT_PRODUCED_BY_CANONICAL_EXECUTOR")
            unsigned = dict(payload)
            unsigned["probe_id"] = ""
            expected_id = "public-access-probe-" + hash_json(unsigned)[:24]
            if payload.get("probe_id") != expected_id:
                raise ValueError("ACCESS_PROBE_ID_HASH_MISMATCH")
            report = validate_live_probe(
                path,
                SourceNetworkCatalog(project_root / "config"),
                now=recorded_at,
            )
            object_id = str(report.get("probe_id") or "") or None
            errors.extend(report.get("errors") or [])
            facts = {
                "source_count": len(report.get("sources") or []),
                "probe_hash": report.get("probe_hash"),
                "access_receipt_is_collection": False,
            }
            authorized = report.get("status") == "PASS"
        elif kind == "raw_evidence_manifest":
            if path.name != "file_manifest.json" or path.parent.name != "manifests":
                raise ValueError("NON_CANONICAL_RAW_EVIDENCE_MANIFEST_PATH")
            pack_root = path.parent.parent
            collection = _load(
                pack_root / "manifests" / "collection_run.json",
                "canonical collection contract",
            )
            if collection.get("synthetic") is not False:
                raise ValueError("SYNTHETIC_OR_UNDECLARED_PACK_NOT_AUTHORIZED")
            if collection.get("run_status") != "QUALIFIED":
                raise ValueError("COLLECTION_RUN_NOT_QUALIFIED")
            manifest = EvidenceManifest(pack_root, Catalog(project_root / "config")).validate(
                cutoff=collection.get("as_of")
            )
            object_id = str(collection.get("pack_id") or "") or None
            errors.extend(manifest.errors)
            facts = {
                "artifact_count": len(manifest.artifacts),
                "artifact_hashes": sorted(manifest.hashes),
                "pack_id": object_id,
                "synthetic": False,
            }
            authorized = manifest.status == "PASS"
        elif kind == "normalized_snapshot":
            if path.name != "collection_run.json" or path.parent.name != "manifests":
                raise ValueError("NON_CANONICAL_NORMALIZED_PACK_CONTRACT_PATH")
            pack_root = path.parent.parent
            if expected_pack_root is None or pack_root != expected_pack_root:
                raise ValueError("NORMALIZED_PACK_DIFFERS_FROM_RAW_MANIFEST_PACK")
            validation = PackValidator(
                pack_root, Catalog(project_root / "config")
            ).validate()
            collection = validation.collection
            object_id = collection.pack_id if collection is not None else None
            errors.extend(validation.errors)
            if collection is None:
                errors.append("MISSING_CANONICAL_COLLECTION_CONTRACT")
            else:
                if collection.synthetic:
                    errors.append("SYNTHETIC_PACK_NOT_AUTHORIZED")
                if collection.run_status != "QUALIFIED":
                    errors.append("COLLECTION_RUN_NOT_QUALIFIED")
            facts = {
                "pack_id": object_id,
                "passed_capabilities": sorted(validation.passed_capabilities),
                "synthetic": None if collection is None else collection.synthetic,
                "run_status": None if collection is None else collection.run_status,
            }
            authorized = (
                validation.status == "PASS"
                and collection is not None
                and not collection.synthetic
                and collection.run_status == "QUALIFIED"
            )
        elif kind == "factor_snapshot":
            if path.name != "factor_snapshot.json":
                raise ValueError("NON_CANONICAL_FACTOR_SNAPSHOT_FILENAME")
            if raw_validation is None or raw_validation.get("validator_status") != "PASS":
                raise ValueError("FACTOR_SNAPSHOT_REQUIRES_VALIDATED_RAW_MANIFEST")
            raw_facts = raw_validation["validator_result"]["facts"]
            manifest_hashes = frozenset(raw_facts.get("artifact_hashes") or [])
            if not manifest_hashes:
                raise ValueError("FACTOR_SNAPSHOT_REQUIRES_RAW_ARTIFACT_HASHES")
            snapshot = _load(path, "canonical factor snapshot")
            report = validate_factor_snapshot(
                snapshot,
                registry=DEFAULT_FACTOR_REGISTRY,
                manifest_hashes=manifest_hashes,
            )
            object_id = str(snapshot.get("snapshot_id") or "") or None
            errors.extend(report.get("errors") or [])
            decision_at = parse_aware(snapshot.get("decision_at"), "factor decision_at")
            if decision_at.astimezone(ZoneInfo("Asia/Kuwait")).date() != decision_date:
                errors.append("FACTOR_SNAPSHOT_DECISION_SESSION_MISMATCH")
            facts = {
                "security_count": len(snapshot.get("rows") or []),
                "factor_snapshot_sha256": snapshot.get("factor_snapshot_sha256"),
            }
            authorized = report.get("status") == "PASS" and not errors
        elif kind == "champion_freeze":
            if product is None:
                raise ValueError("CHAMPION_PRODUCT_BINDING_REQUIRED")
            report = validate_champion_freeze(path, decision_session_date=decision_date)
            object_id = str(report.get("freeze_id") or "") or None
            if (
                report.get("product_id") != product["product_id"]
                or report.get("horizon_sessions") != product["horizon_sessions"]
            ):
                errors.append("CHAMPION_FREEZE_PRODUCT_BINDING_MISMATCH")
            facts = {
                "product_id": report.get("product_id"),
                "horizon_sessions": report.get("horizon_sessions"),
                "manifest_sha256": report.get("manifest_sha256"),
            }
            authorized = not errors
        else:
            raise ValueError("UNSUPPORTED_CANONICAL_INPUT_KIND")
    except (ChampionFreezeError, KeyError, OSError, TypeError, ValueError) as exc:
        errors.append(exc)
    return _validation_record(
        path,
        validator_id=validator_id,
        object_id=object_id,
        errors=errors,
        facts=facts,
        authorized=authorized,
    )


def _contains_private_locator(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered_key = str(key).casefold()
            if any(marker in lowered_key for marker in ("connector_id", "folder_id", "file_id", "webviewlink")):
                return True
            if _contains_private_locator(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_private_locator(item) for item in value)
    if isinstance(value, str):
        lowered = value.casefold()
        return any(marker in lowered for marker in _PRIVATE_MARKERS)
    return False


def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    try:
        parent = require_real_directory(path.parent, field="dry-run artifact parent")
    except ValueError as exc:
        raise LiveDryRunError(str(exc)) from exc
    target = parent / path.name
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
            handle.write(canonical_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise LiveDryRunError(f"refusing to overwrite dry-run artifact: {path.name}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _real_directory(path: Path, field: str) -> Path:
    try:
        return require_real_directory(path, field=field)
    except ValueError as exc:
        raise LiveDryRunError(str(exc)) from exc


def _resolve_directory_below(root: Path, value: Path | str, field: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    absolute = Path(os.path.abspath(candidate))
    if root != absolute and root not in absolute.parents:
        raise LiveDryRunError(f"{field} escapes private_runtime_root")
    current = root
    relative = absolute.relative_to(root)
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise LiveDryRunError(f"{field} must not contain symlinks")
    return absolute


def _resolve_input(root: Path, value: Path | str, field: str) -> Path:
    candidate = _resolve_directory_below(root, value, field)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise LiveDryRunError(f"{field} is missing") from exc
    if root != resolved and root not in resolved.parents:
        raise LiveDryRunError(f"{field} escapes private_runtime_root")
    if not resolved.is_file() or resolved.is_symlink():
        raise LiveDryRunError(f"{field} must be a regular file")
    return resolved


def _parse_decision_date(value: date | str) -> date:
    if isinstance(value, datetime):
        raise LiveDryRunError("decision_session_date must be a date, not datetime")
    if isinstance(value, date):
        return value
    try:
        return parse_iso_date(value, "decision_session_date")
    except ValueError as exc:
        raise LiveDryRunError(str(exc)) from exc


def _parse_recorded_at(value: datetime | str | None) -> datetime:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = parse_aware(value, "recorded_at")
        except ValueError as exc:
            raise LiveDryRunError(str(exc)) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveDryRunError("recorded_at must be timezone-aware")
    return parsed


def _dry_run_lease_fingerprint(run_id: str) -> str:
    run_digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:24].upper()
    return stable_fingerprint(
        market="KUWAIT",
        stage="live_dry_run",
        error_class="github_infrastructure",
        component="daily_orchestrator",
        failure_code=f"RUN_{run_digest}",
    )


def _input_bindings(
    project_root: Path,
    runtime_root: Path,
    *,
    decision_date: date,
    recorded_at: datetime,
    source_probe_receipts: Sequence[Path | str],
    raw_evidence_manifest: Path | str | None,
    normalized_snapshot: Path | str | None,
    factor_snapshot: Path | str | None,
    champion_freezes: Mapping[str, Path | str] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    resolved_probes = [
        _resolve_input(runtime_root, path, f"source_probe_receipts[{index}]")
        for index, path in enumerate(source_probe_receipts)
    ]
    probe_validations = [
        _canonical_validate_input(
            "source_probe",
            path,
            project_root=project_root,
            runtime_root=runtime_root,
            decision_date=decision_date,
            recorded_at=recorded_at,
        )
        for path in resolved_probes
    ]
    probe_hashes = [row["artifact_sha256"] for row in probe_validations]
    if len(probe_hashes) != len(set(probe_hashes)):
        raise LiveDryRunError("source probe receipts must be distinct")

    def optional(path: Path | str | None, field: str) -> Path | None:
        if path is None:
            return None
        return _resolve_input(runtime_root, path, field)

    raw_path = optional(raw_evidence_manifest, "raw_evidence_manifest")
    raw_validation = (
        None
        if raw_path is None
        else _canonical_validate_input(
            "raw_evidence_manifest",
            raw_path,
            project_root=project_root,
            runtime_root=runtime_root,
            decision_date=decision_date,
            recorded_at=recorded_at,
        )
    )
    raw_hash = None if raw_validation is None else raw_validation["artifact_sha256"]
    expected_pack_root = (
        raw_path.parent.parent
        if raw_path is not None
        and raw_path.name == "file_manifest.json"
        and raw_path.parent.name == "manifests"
        else None
    )
    normalized_path = optional(normalized_snapshot, "normalized_snapshot")
    normalized_validation = (
        None
        if normalized_path is None
        else _canonical_validate_input(
            "normalized_snapshot",
            normalized_path,
            project_root=project_root,
            runtime_root=runtime_root,
            decision_date=decision_date,
            recorded_at=recorded_at,
            expected_pack_root=expected_pack_root,
        )
    )
    normalized_hash = (
        None if normalized_validation is None else normalized_validation["artifact_sha256"]
    )
    factor_path = optional(factor_snapshot, "factor_snapshot")
    factor_validation = (
        None
        if factor_path is None
        else _canonical_validate_input(
            "factor_snapshot",
            factor_path,
            project_root=project_root,
            runtime_root=runtime_root,
            decision_date=decision_date,
            recorded_at=recorded_at,
            raw_validation=raw_validation,
        )
    )
    factor_hash = None if factor_validation is None else factor_validation["artifact_sha256"]
    freeze_paths: dict[str, Path] = {}
    freeze_hashes: dict[str, str | None] = {row["product_id"]: None for row in EXPECTED_PRODUCTS}
    freeze_validations: dict[str, dict[str, Any] | None] = {
        row["product_id"]: None for row in EXPECTED_PRODUCTS
    }
    if champion_freezes is not None:
        unknown = set(champion_freezes) - set(freeze_hashes)
        if unknown:
            raise LiveDryRunError(f"unknown freeze products: {sorted(unknown)}")
        for product_id, path in champion_freezes.items():
            resolved = _resolve_input(runtime_root, path, f"champion_freezes.{product_id}")
            freeze_paths[product_id] = resolved
            product = next(row for row in EXPECTED_PRODUCTS if row["product_id"] == product_id)
            validation = _canonical_validate_input(
                "champion_freeze",
                resolved,
                project_root=project_root,
                runtime_root=runtime_root,
                decision_date=decision_date,
                recorded_at=recorded_at,
                product=product,
            )
            freeze_validations[product_id] = validation
            freeze_hashes[product_id] = validation["artifact_sha256"]

    public = {
        "source_probe_sha256": probe_hashes,
        "raw_evidence_manifest_sha256": raw_hash,
        "normalized_snapshot_sha256": normalized_hash,
        "factor_snapshot_sha256": factor_hash,
        "champion_freeze_sha256": freeze_hashes,
    }
    private = {
        "source_probe_receipts": resolved_probes,
        "raw_evidence_manifest": raw_path,
        "normalized_snapshot": normalized_path,
        "factor_snapshot": factor_path,
        "champion_freezes": freeze_paths,
    }
    validations = {
        "source_probe": probe_validations,
        "raw_evidence_manifest": raw_validation,
        "normalized_snapshot": normalized_validation,
        "factor_snapshot": factor_validation,
        "champion_freeze": freeze_validations,
    }
    _validate_input_validations(validations, bindings=public)
    return public, private, validations


def _receipt_name(sequence: int, stage: str) -> str:
    return f"{sequence:02d}_{stage}.json"


def _validate_receipt(
    path: Path,
    *,
    run_id: str,
    sequence: int,
    stage: str,
    previous_hash: str | None,
) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise LiveDryRunError(f"dry-run receipt must be a real file: {path.name}")
    payload = _load(path, "dry-run receipt")
    _exact(payload, RECEIPT_KEYS, f"receipt {sequence}")
    if _contains_private_locator(payload):
        raise LiveDryRunError("private locator leaked into a dry-run receipt")
    if payload["schema_version"] != "1.0" or payload["run_id"] != run_id:
        raise LiveDryRunError("dry-run receipt identity mismatch")
    if payload["sequence"] != sequence or payload["stage"] != stage:
        raise LiveDryRunError("dry-run stage receipt was reordered or replayed")
    if payload["status"] not in {"PASS", "BLOCKED", "SKIPPED"}:
        raise LiveDryRunError("dry-run receipt status is invalid")
    try:
        parse_aware(payload["recorded_at"], "recorded_at")
    except ValueError as exc:
        raise LiveDryRunError(str(exc)) from exc
    if payload["previous_receipt_sha256"] != previous_hash:
        raise LiveDryRunError("dry-run receipt chain is broken")
    for field in ("input_sha256", "output_sha256"):
        values = payload[field]
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) for value in values)
            or len(values) != len(set(values))
        ):
            raise LiveDryRunError(f"receipt {field} must be a unique array")
        for index, value in enumerate(values):
            _canonical_sha256(value, f"{field}[{index}]")
    reasons = payload["reason_codes"]
    if (
        not isinstance(reasons, list)
        or not reasons
        or any(not isinstance(reason, str) for reason in reasons)
        or len(reasons) != len(set(reasons))
    ):
        raise LiveDryRunError("receipt reason_codes must be a non-empty unique array")
    if any(not _REASON_RE.fullmatch(reason) for reason in reasons):
        raise LiveDryRunError("receipt reason_codes are not canonical")
    if payload["claim_boundaries"] != DRY_RUN_CLAIM_BOUNDARIES:
        raise LiveDryRunError("dry-run receipt claim boundaries were weakened")
    return payload


def _stage_result(
    *,
    sequence: int,
    blocked: bool,
    inputs: Mapping[str, Any],
    validations: Mapping[str, Any],
    private_inputs: Mapping[str, Any],
    decision_date: date,
    run_path: Path,
) -> tuple[str, list[str], list[str], list[str]]:
    stage = EXPECTED_STAGES[sequence - 1]
    if blocked:
        return "SKIPPED", ["BLOCKED_BY_PREVIOUS_STAGE"], [], []
    if sequence == 1:
        return "PASS", ["RUN_LEASE_AND_SESSION_CONTRACT_VERIFIED"], [], []
    if sequence == 2:
        records = validations["source_probe"]
        if not records:
            return "BLOCKED", ["AUTHORIZED_ACCESS_PROBE_NOT_SUPPLIED"], [], []
        hashes = [
            digest
            for record in records
            for digest in (
                record["artifact_sha256"],
                record["validator_report_sha256"],
            )
        ]
        if any(record["validator_status"] != "PASS" for record in records):
            return "BLOCKED", ["ACCESS_PROBE_CANONICAL_VALIDATION_FAILED"], hashes, []
        return "PASS", ["ACCESS_PROBE_CANONICALLY_VALIDATED_NO_MARKET_EVIDENCE"], hashes, []
    if sequence == 3:
        record = validations["raw_evidence_manifest"]
        if record is None:
            return "BLOCKED", ["RAW_EVIDENCE_MANIFEST_NOT_SUPPLIED"], [], []
        hashes = [record["artifact_sha256"], record["validator_report_sha256"]]
        if record["validator_status"] != "PASS":
            return "BLOCKED", ["RAW_EVIDENCE_CANONICAL_VALIDATION_FAILED"], hashes, []
        return "PASS", ["RAW_EVIDENCE_REOPENED_AND_CANONICALLY_VALIDATED"], hashes, []
    if sequence == 4:
        record = validations["normalized_snapshot"]
        if record is None:
            return "BLOCKED", ["POINT_IN_TIME_SNAPSHOT_NOT_SUPPLIED"], [], []
        hashes = [record["artifact_sha256"], record["validator_report_sha256"]]
        if record["validator_status"] != "PASS":
            return "BLOCKED", ["POINT_IN_TIME_PACK_CANONICAL_VALIDATION_FAILED"], hashes, []
        return "PASS", ["POINT_IN_TIME_PACK_CANONICALLY_VALIDATED"], hashes, []
    if sequence == 5:
        record = validations["factor_snapshot"]
        if record is None:
            return "BLOCKED", ["FACTOR_SNAPSHOT_NOT_SUPPLIED"], [], []
        hashes = [record["artifact_sha256"], record["validator_report_sha256"]]
        if record["validator_status"] != "PASS":
            return "BLOCKED", ["FACTOR_SNAPSHOT_CANONICAL_VALIDATION_FAILED"], hashes, []
        return "PASS", ["FACTOR_SNAPSHOT_CANONICALLY_VALIDATED"], hashes, []
    if sequence == 6:
        freeze_records = validations["champion_freeze"]
        if any(freeze_records[row["product_id"]] is None for row in EXPECTED_PRODUCTS):
            return "BLOCKED", ["COMPLETE_PREVIOUS_CHAMPION_FREEZE_SET_NOT_SUPPLIED"], [], []
        records = [freeze_records[row["product_id"]] for row in EXPECTED_PRODUCTS]
        hashes = [
            digest
            for record in records
            for digest in (
                record["artifact_sha256"],
                record["validator_report_sha256"],
            )
        ]
        if any(record["validator_status"] != "PASS" for record in records):
            return "BLOCKED", ["PREVIOUS_CHAMPION_FREEZE_REJECTED"], hashes, []
        return "PASS", ["PREVIOUS_APPROVED_FREEZES_VERIFIED"], hashes, []
    if sequence == 7:
        sealed = {
            "schema_version": "1.0",
            "status": "SEALED_DRY_RUN_ABSTAIN",
            "decision_session_date": decision_date.isoformat(),
            "products": [
                {
                    "product_id": row["product_id"],
                    "horizon_sessions": row["horizon_sessions"],
                    "decision": "ABSTAIN",
                    "candidates": [],
                    "entry_price": None,
                    "exit_price": None,
                }
                for row in EXPECTED_PRODUCTS
            ],
            "claim_boundaries": DRY_RUN_CLAIM_BOUNDARIES,
        }
        output = run_path / "sealed_research_output.json"
        _write_exclusive(output, sealed)
        return "PASS", ["EMPTY_ABSTAIN_OUTPUT_SEALED"], [], [sha256_file(output)]
    if sequence == 8:
        return "PASS", ["NO_MATURE_OUTCOMES_SCORED_IN_DRY_RUN"], [], []
    if sequence == 9:
        return "SKIPPED", ["MODEL_TRAINING_FORBIDDEN_IN_KU_BO_017"], [], []
    if sequence == 10:
        return "SKIPPED", ["DRAFT_CHANGE_PROPOSAL_REQUIRES_SEPARATE_TASK"], [], []
    raise LiveDryRunError(f"unsupported dry-run stage: {stage}")


def run_daily_dry_run(
    *,
    project_root: Path | str | None = None,
    private_runtime_root: Path | str,
    output_root: Path | str,
    run_id: str,
    decision_session_date: date | str,
    source_probe_receipts: Sequence[Path | str] = (),
    raw_evidence_manifest: Path | str | None = None,
    normalized_snapshot: Path | str | None = None,
    factor_snapshot: Path | str | None = None,
    champion_freezes: Mapping[str, Path | str] | None = None,
    recorded_at: datetime | str | None = None,
    active_run_probe: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Run or safely resume one hash-bound dry-run with no network activity."""

    if not isinstance(run_id, str) or not _ID_RE.fullmatch(run_id):
        raise LiveDryRunError("run_id is not a canonical identifier")
    decision_date = _parse_decision_date(decision_session_date)
    timestamp = _parse_recorded_at(recorded_at)
    project = _real_directory(
        Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2],
        "project_root",
    )
    root = _real_directory(Path(private_runtime_root), "private_runtime_root")
    outputs = _resolve_directory_below(root, output_root, "output_root")
    outputs.mkdir(parents=True, exist_ok=True)
    outputs = _real_directory(outputs, "output_root")
    run_path = outputs / run_id
    if outputs not in run_path.parents:
        raise LiveDryRunError("run_id escapes output_root")

    public_inputs, private_inputs, input_validations = _input_bindings(
        project,
        root,
        decision_date=decision_date,
        recorded_at=timestamp,
        source_probe_receipts=source_probe_receipts,
        raw_evidence_manifest=raw_evidence_manifest,
        normalized_snapshot=normalized_snapshot,
        factor_snapshot=factor_snapshot,
        champion_freezes=champion_freezes,
    )
    contract = {
        "schema_version": "1.0",
        "run_id": run_id,
        "decision_session_date": decision_date.isoformat(),
        "mode": "NO_NETWORK_DRY_RUN",
        "stages": EXPECTED_STAGES,
        "products": EXPECTED_PRODUCTS,
        "input_bindings": public_inputs,
        "input_validations": input_validations,
        "claim_boundaries": DRY_RUN_CLAIM_BOUNDARIES,
    }
    if _contains_private_locator(contract):
        raise LiveDryRunError("private locator leaked into the dry-run contract")

    lease_root = outputs / ".leases"
    lease_root.mkdir(parents=True, exist_ok=True)
    lease_root = _real_directory(lease_root, "dry-run lease directory")
    lease_fingerprint = _dry_run_lease_fingerprint(run_id)
    lease_owner = "kubo-live-dry-run"
    process_identity = current_process_identity()
    recovery_policy, _ = load_recovery_policy(project)
    try:
        acquire_recovery_lease(
            lease_root,
            fingerprint=lease_fingerprint,
            run_id=run_id,
            owner=lease_owner,
            process_identity=process_identity,
            now=datetime.now(timezone.utc),
            policy=recovery_policy,
            active_run_probe=active_run_probe,
        )
    except (ActiveLeaseError, LeaseRecoveryBlockedError) as exc:
        raise LiveDryRunLockError(f"dry-run lease is held or cannot be safely recovered for {run_id}") from exc
    except LeaseError as exc:
        raise LiveDryRunLockError(f"dry-run lease validation failed for {run_id}") from exc

    try:
        if run_path.exists():
            run_path = _real_directory(run_path, "dry-run path")
            existing_contract = _load(run_path / "run_contract.json", "dry-run contract")
            if existing_contract != contract:
                raise LiveDryRunError("run replay changed the immutable input contract")
        else:
            run_path.mkdir()
            run_path = _real_directory(run_path, "dry-run path")
            _write_exclusive(run_path / "run_contract.json", contract)
        receipts_path = run_path / "receipts"
        receipts_path.mkdir(exist_ok=True)
        receipts_path = _real_directory(receipts_path, "dry-run receipts directory")

        allowed_names = {
            _receipt_name(index, stage) for index, stage in enumerate(EXPECTED_STAGES, start=1)
        }
        actual_names = {path.name for path in receipts_path.iterdir() if path.is_file()}
        unexpected = sorted(actual_names - allowed_names)
        if unexpected:
            raise LiveDryRunError(f"unexpected dry-run receipt files: {unexpected}")

        previous_hash: str | None = None
        blocked = False
        blocked_stage: str | None = None
        receipts: list[dict[str, Any]] = []
        for sequence, stage in enumerate(EXPECTED_STAGES, start=1):
            try:
                heartbeat_recovery_lease(
                    lease_root,
                    fingerprint=lease_fingerprint,
                    run_id=run_id,
                    owner=lease_owner,
                    process_identity=process_identity,
                    now=datetime.now(timezone.utc),
                    policy=recovery_policy,
                )
            except LeaseError as exc:
                raise LiveDryRunLockError("dry-run lease heartbeat failed") from exc
            receipt_path = receipts_path / _receipt_name(sequence, stage)
            if receipt_path.exists():
                receipt = _validate_receipt(
                    receipt_path,
                    run_id=run_id,
                    sequence=sequence,
                    stage=stage,
                    previous_hash=previous_hash,
                )
            else:
                status, reasons, input_hashes, output_hashes = _stage_result(
                    sequence=sequence,
                    blocked=blocked,
                    inputs=public_inputs,
                    validations=input_validations,
                    private_inputs=private_inputs,
                    decision_date=decision_date,
                    run_path=run_path,
                )
                receipt = {
                    "schema_version": "1.0",
                    "run_id": run_id,
                    "sequence": sequence,
                    "stage": stage,
                    "status": status,
                    "recorded_at": timestamp.isoformat(),
                    "previous_receipt_sha256": previous_hash,
                    "input_sha256": sorted(set(input_hashes)),
                    "output_sha256": sorted(set(output_hashes)),
                    "reason_codes": reasons,
                    "claim_boundaries": DRY_RUN_CLAIM_BOUNDARIES,
                }
                _write_exclusive(receipt_path, receipt)
                _validate_receipt(
                    receipt_path,
                    run_id=run_id,
                    sequence=sequence,
                    stage=stage,
                    previous_hash=previous_hash,
                )
            if receipt["status"] == "BLOCKED" and blocked_stage is None:
                blocked = True
                blocked_stage = stage
            elif receipt["status"] == "SKIPPED" and sequence < 9 and not blocked:
                raise LiveDryRunError("a required dry-run stage was skipped before any blocker")
            previous_hash = sha256_file(receipt_path)
            receipts.append(receipt)

        assert previous_hash is not None
        report = {
            "schema_version": "1.0",
            "status": "DRY_RUN_BLOCKED" if blocked_stage else "DRY_RUN_COMPLETE_NO_RECOMMENDATION",
            "run_id": run_id,
            "decision_session_date": decision_date.isoformat(),
            "stage_count": len(EXPECTED_STAGES),
            "receipt_count": len(receipts),
            "last_receipt_sha256": previous_hash,
            "blocked_stage": blocked_stage,
            "products": EXPECTED_PRODUCTS,
            "candidate_count": 0,
            "claim_boundaries": DRY_RUN_CLAIM_BOUNDARIES,
        }
        report_path = run_path / "dry_run_report.json"
        if report_path.exists():
            if _load(report_path, "dry-run report") != report:
                raise LiveDryRunError("existing dry-run report does not match the receipt chain")
        else:
            _write_exclusive(report_path, report)
        validate_live_dry_run(run_path)
        return report
    finally:
        try:
            release_recovery_lease(
                lease_root,
                fingerprint=lease_fingerprint,
                run_id=run_id,
                owner=lease_owner,
                process_identity=process_identity,
            )
        except LeaseError as exc:
            raise LiveDryRunError("dry-run lease disappeared or changed before release") from exc


def validate_live_dry_run(run_root: Path | str) -> dict[str, Any]:
    """Reopen a persisted dry-run and verify its immutable receipt chain."""

    root = _real_directory(Path(run_root), "dry-run root")
    contract = _load(root / "run_contract.json", "dry-run contract")
    _exact(contract, RUN_CONTRACT_KEYS, "dry-run contract")
    if _contains_private_locator(contract):
        raise LiveDryRunError("private locator leaked into the dry-run contract")
    if contract["schema_version"] != "1.0" or contract["mode"] != "NO_NETWORK_DRY_RUN":
        raise LiveDryRunError("unsupported dry-run contract")
    run_id = contract["run_id"]
    if not isinstance(run_id, str) or not _ID_RE.fullmatch(run_id):
        raise LiveDryRunError("dry-run run_id is invalid")
    _parse_decision_date(contract["decision_session_date"])
    if contract["stages"] != EXPECTED_STAGES:
        raise LiveDryRunError("dry-run stage order changed")
    if contract["products"] != EXPECTED_PRODUCTS:
        raise LiveDryRunError("dry-run product bindings changed")
    bindings = _validate_input_bindings(contract["input_bindings"])
    _validate_input_validations(contract["input_validations"], bindings=bindings)
    if contract["claim_boundaries"] != DRY_RUN_CLAIM_BOUNDARIES:
        raise LiveDryRunError("dry-run contract claim boundaries were weakened")

    receipts_root = _real_directory(root / "receipts", "dry-run receipts directory")
    allowed_receipts = {
        _receipt_name(index, stage) for index, stage in enumerate(EXPECTED_STAGES, start=1)
    }
    actual_receipts = {path.name for path in receipts_root.iterdir()}
    unexpected_receipts = sorted(actual_receipts - allowed_receipts)
    if unexpected_receipts:
        raise LiveDryRunError(f"unexpected dry-run receipt files: {unexpected_receipts}")
    previous_hash: str | None = None
    blocked_stage: str | None = None
    for sequence, stage in enumerate(EXPECTED_STAGES, start=1):
        path = receipts_root / _receipt_name(sequence, stage)
        if not path.is_file() or path.is_symlink():
            raise LiveDryRunError(f"dry-run receipt is missing: {path.name}")
        receipt = _validate_receipt(
            path,
            run_id=run_id,
            sequence=sequence,
            stage=stage,
            previous_hash=previous_hash,
        )
        if receipt["status"] == "BLOCKED" and blocked_stage is None:
            blocked_stage = stage
        if blocked_stage is not None and sequence > EXPECTED_STAGES.index(blocked_stage) + 1:
            if receipt["status"] != "SKIPPED":
                raise LiveDryRunError("a stage ran after an earlier blocking receipt")
        previous_hash = sha256_file(path)
    assert previous_hash is not None

    report = _load(root / "dry_run_report.json", "dry-run report")
    _exact(report, REPORT_KEYS, "dry-run report")
    expected_status = "DRY_RUN_BLOCKED" if blocked_stage else "DRY_RUN_COMPLETE_NO_RECOMMENDATION"
    if (
        report["schema_version"] != "1.0"
        or report["run_id"] != run_id
        or report["decision_session_date"] != contract["decision_session_date"]
        or report["status"] != expected_status
        or report["stage_count"] != len(EXPECTED_STAGES)
        or report["receipt_count"] != len(EXPECTED_STAGES)
        or report["last_receipt_sha256"] != previous_hash
        or report["blocked_stage"] != blocked_stage
        or report["products"] != EXPECTED_PRODUCTS
        or report["candidate_count"] != 0
        or report["claim_boundaries"] != DRY_RUN_CLAIM_BOUNDARIES
    ):
        raise LiveDryRunError("dry-run report does not reconcile to the contract and receipts")
    if _contains_private_locator(report):
        raise LiveDryRunError("private locator leaked into the dry-run report")

    sealed = root / "sealed_research_output.json"
    champion_receipt = _load(
        receipts_root / _receipt_name(6, EXPECTED_STAGES[5]), "Champion receipt"
    )
    seal_receipt = _load(
        receipts_root / _receipt_name(7, EXPECTED_STAGES[6]), "seal receipt"
    )
    if seal_receipt["status"] == "PASS":
        if champion_receipt["status"] != "PASS" or not sealed.is_file() or sealed.is_symlink():
            raise LiveDryRunError("sealed output exists without a passing previous-freeze chain")
        if seal_receipt["output_sha256"] != [sha256_file(sealed)]:
            raise LiveDryRunError("sealed output hash does not match its receipt")
        payload = _load(sealed, "sealed dry-run output")
        _exact(payload, SEALED_OUTPUT_KEYS, "sealed dry-run output")
        products = payload["products"]
        if not isinstance(products, list) or len(products) != len(EXPECTED_PRODUCTS):
            raise LiveDryRunError("sealed dry-run output must bind all four products")
        expected_products = []
        for row in EXPECTED_PRODUCTS:
            expected_products.append(
                {
                    "product_id": row["product_id"],
                    "horizon_sessions": row["horizon_sessions"],
                    "decision": "ABSTAIN",
                    "candidates": [],
                    "entry_price": None,
                    "exit_price": None,
                }
            )
        for index, product in enumerate(products):
            _exact(product, SEALED_PRODUCT_KEYS, f"sealed products[{index}]")
        if (
            payload["schema_version"] != "1.0"
            or payload["status"] != "SEALED_DRY_RUN_ABSTAIN"
            or payload["decision_session_date"] != contract["decision_session_date"]
            or products != expected_products
            or payload["claim_boundaries"] != DRY_RUN_CLAIM_BOUNDARIES
            or _contains_private_locator(payload)
        ):
            raise LiveDryRunError("sealed dry-run output attempted to emit a candidate")
    elif sealed.exists():
        raise LiveDryRunError("sealed output exists after a blocked Champion chain")

    allowed_root_entries = {
        "run_contract.json",
        "dry_run_report.json",
        "receipts",
    }
    if seal_receipt["status"] == "PASS":
        allowed_root_entries.add("sealed_research_output.json")
    unexpected_root_entries = sorted(
        path.name for path in root.iterdir() if path.name not in allowed_root_entries
    )
    if unexpected_root_entries:
        raise LiveDryRunError(f"unexpected dry-run artifacts: {unexpected_root_entries}")
    return report


class DryRunOrchestrator:
    """Small object wrapper for callers that prefer a configured orchestrator."""

    def __init__(
        self,
        project_root: Path | str,
        private_runtime_root: Path | str,
        output_root: Path | str,
    ):
        self.project_root = Path(project_root)
        self.private_runtime_root = Path(private_runtime_root)
        self.output_root = Path(output_root)

    def run(self, **kwargs: Any) -> dict[str, Any]:
        return run_daily_dry_run(
            project_root=self.project_root,
            private_runtime_root=self.private_runtime_root,
            output_root=self.output_root,
            **kwargs,
        )


__all__ = [
    "DRY_RUN_CLAIM_BOUNDARIES",
    "DryRunOrchestrator",
    "LiveDryRunError",
    "LiveDryRunLockError",
    "run_daily_dry_run",
    "validate_live_dry_run",
]
