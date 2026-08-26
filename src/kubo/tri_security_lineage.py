from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

from .foundation_io import (
    load_strict_json_object,
    require_real_directory,
    safe_regular_file,
    strict_json_object,
)
from .hashing import canonical_json_bytes, sha256_bytes
from .tri_security_admission import (
    BOUNDARY_STAGE_MAP,
    SEMANTIC_ADMISSION_ALGORITHM,
    SEMANTIC_ADMISSION_AUDIENCE,
    SEMANTIC_ADMISSION_CLAIM_BOUNDARY,
    SEMANTIC_ADMISSION_FILE,
    SEMANTIC_ADMISSION_SCHEMA_VERSION,
    STAGE_PREDECESSORS,
    BoundaryAdmissionError,
    VerifiedBoundaryAdmission,
)


LINEAGE_SCHEMA_VERSION = "1.0"
LINEAGE_AUDIENCE = "kubo-tri-security-output-lineage"
LINEAGE_CLAIM_BOUNDARY = "AUTHENTICATED_OUTPUT_LINEAGE_NOT_MARKET_EVIDENCE"
LINEAGE_FILE = "reports/tri_security_lineage.json"

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_LINEAGE_FIELDS = {
    "schema_version",
    "audience",
    "boundary_id",
    "stage_id",
    "run_id",
    "batch_id",
    "semantic_admission",
    "predecessor_bindings",
    "claim_boundary",
    "authentication",
}
_ADMISSION_FIELDS = {
    "schema_version",
    "audience",
    "admission_id",
    "issued_at",
    "boundary_id",
    "stage_id",
    "v1_references",
    "run_binding",
    "input_tree",
    "boundary_inputs",
    "operation_binding",
    "predecessor_bindings",
    "claims",
    "claim_boundary",
    "authentication",
}
_AUTHENTICATION_FIELDS = {"algorithm", "key_id", "tag"}
_ADMISSION_REFERENCE_FIELDS = {"path", "sha256", "size_bytes"}
_PREDECESSOR_FIELDS = {"stage_id", "run_id", "admission_sha256"}


def _reject(code: str, phase: str, message: str = "") -> None:
    raise BoundaryAdmissionError(code, phase, message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _authority(
    semantic_key: bytes,
    semantic_key_id: str,
    *,
    phase: str,
) -> tuple[bytes, str]:
    if not isinstance(semantic_key, bytes) or len(semantic_key) < 32:
        _reject(
            "STAGE_BINDING_AUTHENTICATION_FAILED",
            phase,
            "semantic authority key must contain at least 32 bytes",
        )
    if (
        not isinstance(semantic_key_id, str)
        or not semantic_key_id
        or semantic_key_id != semantic_key_id.strip()
    ):
        _reject("STAGE_BINDING_KEY_ID_MISMATCH", phase)
    return semantic_key, semantic_key_id


def _authentication_bytes(payload: Mapping[str, Any]) -> bytes:
    authentication = payload["authentication"]
    return canonical_json_bytes(
        {
            "document": {
                key: value
                for key, value in payload.items()
                if key != "authentication"
            },
            "algorithm": authentication["algorithm"],
            "key_id": authentication["key_id"],
        }
    )


def _sign(
    payload: dict[str, Any],
    *,
    semantic_key: bytes,
    semantic_key_id: str,
) -> dict[str, Any]:
    secret, key_id = _authority(
        semantic_key,
        semantic_key_id,
        phase="PRE_COMMIT_RECHECK",
    )
    payload["authentication"] = {
        "algorithm": SEMANTIC_ADMISSION_ALGORITHM,
        "key_id": key_id,
        "tag": "0" * 64,
    }
    payload["authentication"]["tag"] = hmac.new(
        secret,
        _authentication_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    return payload


def _verify_signature(
    payload: Mapping[str, Any],
    *,
    semantic_key: bytes,
    semantic_key_id: str,
    phase: str,
) -> None:
    secret, expected_key_id = _authority(
        semantic_key,
        semantic_key_id,
        phase=phase,
    )
    authentication = payload.get("authentication")
    if not isinstance(authentication, dict) or set(authentication) != _AUTHENTICATION_FIELDS:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    if authentication.get("algorithm") != SEMANTIC_ADMISSION_ALGORITHM:
        _reject("STAGE_BINDING_AUTHENTICATION_FAILED", phase)
    if authentication.get("key_id") != expected_key_id:
        _reject("STAGE_BINDING_KEY_ID_MISMATCH", phase)
    tag = authentication.get("tag")
    if not isinstance(tag, str) or not _HASH_RE.fullmatch(tag):
        _reject("STAGE_BINDING_AUTHENTICATION_FAILED", phase)
    expected = hmac.new(
        secret,
        _authentication_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, tag):
        _reject("STAGE_BINDING_AUTHENTICATION_FAILED", phase)


def _predecessor_rows(
    value: Any,
    *,
    stage_id: str,
    run_id: str,
    phase: str,
) -> list[dict[str, str]]:
    rows = _plain(value)
    if not isinstance(rows, list) or not rows:
        _reject("PREDECESSOR_BINDING_REQUIRED", phase)
    expected_stages = STAGE_PREDECESSORS.get(stage_id)
    if expected_stages is None:
        _reject("PREDECESSOR_STAGE_MISMATCH", phase)
    normalized: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != _PREDECESSOR_FIELDS:
            _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
        if (
            not isinstance(row.get("stage_id"), str)
            or row.get("run_id") != run_id
            or not isinstance(row.get("admission_sha256"), str)
            or not _HASH_RE.fullmatch(row["admission_sha256"])
        ):
            _reject("PREDECESSOR_STAGE_MISMATCH", phase)
        normalized.append(dict(row))
    if tuple(row["stage_id"] for row in normalized) != expected_stages:
        _reject("PREDECESSOR_STAGE_MISMATCH", phase)
    hashes = [row["admission_sha256"] for row in normalized]
    if len(hashes) != len(set(hashes)):
        _reject("PREDECESSOR_BINDING_REPLAYED", phase)
    return normalized


def _write_exclusive(path: Path, content: bytes) -> None:
    reports = require_real_directory(path.parent, field="TRI_SECURITY_LINEAGE_REPORTS")
    target = reports / path.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(target, flags, 0o600)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("lineage write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    except (OSError, ValueError) as exc:
        _reject("UNSAFE_STAGE_ENTRY", "PRE_COMMIT_RECHECK", str(exc))
    finally:
        if descriptor is not None:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class VerifiedBoundaryLineage:
    boundary_id: str
    stage_id: str
    run_id: str
    batch_id: str
    admission_sha256: str
    predecessor_bindings: tuple[Mapping[str, str], ...]
    payload: Mapping[str, Any]
    lineage_sha256: str


def materialize_boundary_lineage(
    admission: VerifiedBoundaryAdmission,
    staging_root: Path,
) -> Path:
    """Persist a signed, non-claim lineage report beside an exact admission sidecar."""

    if not isinstance(admission, VerifiedBoundaryAdmission):
        _reject(
            "STAGE_BINDING_AUTHENTICATION_FAILED",
            "PRE_COMMIT_RECHECK",
            "lineage writer requires a verified boundary admission",
        )
    root = require_real_directory(staging_root, field="TRI_SECURITY_LINEAGE_OUTPUT")
    sidecar_path = root / SEMANTIC_ADMISSION_FILE
    try:
        sidecar = safe_regular_file(
            sidecar_path,
            field="TRI_SECURITY_SEMANTIC_ADMISSION_SIDECAR",
        )
    except (OSError, ValueError) as exc:
        _reject("STAGE_BINDING_REQUIRED", "PRE_COMMIT_RECHECK", str(exc))
    if sidecar != admission._admission_bytes:
        _reject(
            "PREDECESSOR_BINDING_REPLAYED",
            "PRE_COMMIT_RECHECK",
            "materialized admission differs from verified bytes",
        )
    predecessors = _predecessor_rows(
        admission.payload.get("predecessor_bindings"),
        stage_id=admission.stage_id,
        run_id=admission.run_id,
        phase="PRE_COMMIT_RECHECK",
    )
    payload = {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "audience": LINEAGE_AUDIENCE,
        "boundary_id": admission.boundary_id,
        "stage_id": admission.stage_id,
        "run_id": admission.run_id,
        "batch_id": admission.batch_id,
        "semantic_admission": {
            "path": SEMANTIC_ADMISSION_FILE,
            "sha256": admission.admission_sha256,
            "size_bytes": len(sidecar),
        },
        "predecessor_bindings": predecessors,
        "claim_boundary": LINEAGE_CLAIM_BOUNDARY,
    }
    _sign(
        payload,
        semantic_key=admission.request.semantic_key,
        semantic_key_id=admission.request.semantic_key_id,
    )
    content = canonical_json_bytes(payload)
    path = root / LINEAGE_FILE
    _write_exclusive(path, content)
    return path


def verify_boundary_lineage(
    output_root: Path,
    *,
    semantic_key: bytes,
    semantic_key_id: str,
    phase: str = "ENTRY_PRE_WRITE",
) -> VerifiedBoundaryLineage:
    """Verify one fixed lineage report and its exact authenticated admission bytes."""

    try:
        root = require_real_directory(output_root, field="TRI_SECURITY_LINEAGE_OUTPUT")
        lineage_path = root / LINEAGE_FILE
        if not lineage_path.exists():
            _reject("PREDECESSOR_BINDING_REQUIRED", phase, "lineage report is missing")
        payload, content = load_strict_json_object(
            lineage_path,
            field="TRI_SECURITY_LINEAGE_REPORT",
        )
    except BoundaryAdmissionError:
        raise
    except (OSError, ValueError) as exc:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, str(exc))
    if content != canonical_json_bytes(payload) or set(payload) != _LINEAGE_FIELDS:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    if (
        payload.get("schema_version") != LINEAGE_SCHEMA_VERSION
        or payload.get("audience") != LINEAGE_AUDIENCE
        or payload.get("claim_boundary") != LINEAGE_CLAIM_BOUNDARY
    ):
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    boundary_id = payload.get("boundary_id")
    stage_id = payload.get("stage_id")
    run_id = payload.get("run_id")
    batch_id = payload.get("batch_id")
    if (
        not isinstance(boundary_id, str)
        or BOUNDARY_STAGE_MAP.get(boundary_id) != stage_id
        or not isinstance(run_id, str)
        or not run_id
        or not isinstance(batch_id, str)
        or not batch_id
    ):
        _reject("PREDECESSOR_STAGE_MISMATCH", phase)
    predecessors = _predecessor_rows(
        payload.get("predecessor_bindings"),
        stage_id=stage_id,
        run_id=run_id,
        phase=phase,
    )
    _verify_signature(
        payload,
        semantic_key=semantic_key,
        semantic_key_id=semantic_key_id,
        phase=phase,
    )

    reference = payload.get("semantic_admission")
    if not isinstance(reference, dict) or set(reference) != _ADMISSION_REFERENCE_FIELDS:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    if reference.get("path") != SEMANTIC_ADMISSION_FILE:
        _reject("PREDECESSOR_BINDING_REPLAYED", phase)
    declared_hash = reference.get("sha256")
    size_bytes = reference.get("size_bytes")
    if (
        not isinstance(declared_hash, str)
        or not _HASH_RE.fullmatch(declared_hash)
        or isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes < 1
    ):
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    try:
        sidecar = safe_regular_file(
            root / SEMANTIC_ADMISSION_FILE,
            field="TRI_SECURITY_SEMANTIC_ADMISSION_SIDECAR",
        )
        admission_payload = strict_json_object(
            sidecar,
            "TRI_SECURITY_SEMANTIC_ADMISSION_SIDECAR",
        )
    except (OSError, ValueError) as exc:
        _reject("STAGE_BINDING_REQUIRED", phase, str(exc))
    if (
        len(sidecar) != size_bytes
        or sha256_bytes(sidecar) != declared_hash
        or sidecar != canonical_json_bytes(admission_payload)
    ):
        _reject("PREDECESSOR_BINDING_REPLAYED", phase)
    if set(admission_payload) != _ADMISSION_FIELDS:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    if (
        admission_payload.get("schema_version") != SEMANTIC_ADMISSION_SCHEMA_VERSION
        or admission_payload.get("audience") != SEMANTIC_ADMISSION_AUDIENCE
        or admission_payload.get("claim_boundary") != SEMANTIC_ADMISSION_CLAIM_BOUNDARY
    ):
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    _verify_signature(
        admission_payload,
        semantic_key=semantic_key,
        semantic_key_id=semantic_key_id,
        phase=phase,
    )
    run_binding = admission_payload.get("run_binding")
    if (
        not isinstance(run_binding, dict)
        or admission_payload.get("boundary_id") != boundary_id
        or admission_payload.get("stage_id") != stage_id
        or run_binding.get("run_id") != run_id
        or run_binding.get("batch_id") != batch_id
        or _plain(admission_payload.get("predecessor_bindings")) != predecessors
    ):
        _reject("PREDECESSOR_BINDING_REPLAYED", phase)
    return VerifiedBoundaryLineage(
        boundary_id=boundary_id,
        stage_id=stage_id,
        run_id=run_id,
        batch_id=batch_id,
        admission_sha256=declared_hash,
        predecessor_bindings=tuple(_freeze(row) for row in predecessors),
        payload=_freeze(payload),
        lineage_sha256=sha256_bytes(content),
    )


def verify_final_predecessor_lineages(
    final_admission: VerifiedBoundaryAdmission,
    *,
    predecessor_roots: Mapping[str, Path],
) -> tuple[VerifiedBoundaryLineage, ...]:
    """Verify the final stage's six ordered authenticated output lineages."""

    phase = "ENTRY_PRE_WRITE"
    if (
        not isinstance(final_admission, VerifiedBoundaryAdmission)
        or final_admission.boundary_id != "build_data_foundation_packet"
    ):
        _reject("PREDECESSOR_STAGE_MISMATCH", phase)
    rows = _predecessor_rows(
        final_admission.payload.get("predecessor_bindings"),
        stage_id=final_admission.stage_id,
        run_id=final_admission.run_id,
        phase=phase,
    )
    expected_stages = tuple(row["stage_id"] for row in rows)
    if set(predecessor_roots) != set(expected_stages):
        _reject("PREDECESSOR_BINDING_REQUIRED", phase)
    verified: list[VerifiedBoundaryLineage] = []
    for row in rows:
        lineage = verify_boundary_lineage(
            predecessor_roots[row["stage_id"]],
            semantic_key=final_admission.request.semantic_key,
            semantic_key_id=final_admission.request.semantic_key_id,
            phase=phase,
        )
        if (
            lineage.stage_id != row["stage_id"]
            or lineage.run_id != final_admission.run_id
            or lineage.batch_id != final_admission.batch_id
            or lineage.admission_sha256 != row["admission_sha256"]
        ):
            _reject("PREDECESSOR_BINDING_REPLAYED", phase)
        verified.append(lineage)
    if tuple(item.stage_id for item in verified) != expected_stages:
        _reject("PREDECESSOR_STAGE_MISMATCH", phase)
    return tuple(verified)


__all__ = [
    "LINEAGE_AUDIENCE",
    "LINEAGE_CLAIM_BOUNDARY",
    "LINEAGE_FILE",
    "LINEAGE_SCHEMA_VERSION",
    "VerifiedBoundaryLineage",
    "materialize_boundary_lineage",
    "verify_boundary_lineage",
    "verify_final_predecessor_lineages",
]
