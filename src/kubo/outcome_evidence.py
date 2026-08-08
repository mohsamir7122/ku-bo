from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any
import unicodedata
from urllib.parse import urlsplit

from .hashing import canonical_json_bytes, sha256_bytes
from .strict import https_url, parse_aware, require_sha256, safe_relative_path


OUTCOME_EVIDENCE_SCHEMA_VERSION = "1.0"
MAX_OUTCOME_EVIDENCE_ARTIFACTS = 32
MAX_OUTCOME_EVIDENCE_BYTES = 128 * 1024 * 1024
MAX_OUTCOME_EVIDENCE_MANIFEST_BYTES = 1024 * 1024

OUTCOME_UNITS = frozenset(
    {
        "DECIMAL_RETURN",
        "PERCENTAGE_POINTS",
        "BASIS_POINTS",
        "FILS",
        "KWD",
        "RATIO",
        "COUNT",
        "BOOLEAN_FLAG",
    }
)

_MANIFEST_FIELDS = frozenset(
    {"schema_version", "outcome_id", "decision_id", "security_code", "artifacts"}
)
_ARTIFACT_FIELDS = frozenset(
    {
        "path",
        "sha256",
        "size_bytes",
        "source_id",
        "source_url",
        "content_type",
        "observed_at",
    }
)
_OUTCOME_PAYLOAD_FIELDS = frozenset(
    {
        "schema_version",
        "security_code",
        "metric_id",
        "value",
        "unit",
        "measurement_start_at",
        "measurement_end_at",
        "method_id",
        "notes",
    }
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_SECURITY_CODE_RE = re.compile(r"^[0-9]{1,12}$")
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CONTENT_TYPE_RE = re.compile(
    r"^[a-z0-9][a-z0-9!#$%&'*+.^_`|~-]{0,62}/"
    r"[a-z0-9][a-z0-9!#$%&'*+.^_`|~-]{0,62}$"
)


class OutcomeEvidenceError(ValueError):
    """Raised when an outcome evidence packet or payload violates its contract."""


@dataclass(frozen=True)
class OutcomeEvidenceResult:
    outcome_id: str
    decision_id: str
    security_code: str
    packet_hash: str
    artifact_hashes: tuple[str, ...]
    artifact_count: int
    total_bytes: int

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["artifact_hashes"] = list(self.artifact_hashes)
        return value


def _reject_non_json_constant(value: str) -> None:
    raise OutcomeEvidenceError(f"manifest contains non-JSON numeric constant: {value}")


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OutcomeEvidenceError(f"manifest contains duplicate object key: {key}")
        result[key] = value
    return result


def _strict_json_object(content: bytes, field: str) -> dict[str, Any]:
    try:
        decoded = content.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_non_json_constant,
        )
    except OutcomeEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise OutcomeEvidenceError(f"{field} must be strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise OutcomeEvidenceError(f"{field} must contain a JSON object")
    return value


def _strict_json_snapshot(value: Any, field: str) -> dict[str, Any]:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise OutcomeEvidenceError(f"{field} must be strict JSON") from exc
    return _strict_json_object(encoded, field)


def _exact_object_fields(value: Any, expected: frozenset[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OutcomeEvidenceError(f"{field} must be an object")
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise OutcomeEvidenceError(f"{field} is missing fields: " + ",".join(missing))
    if unknown:
        raise OutcomeEvidenceError(f"{field} has unknown fields: " + ",".join(unknown))
    return value


def _canonical_text(
    value: Any,
    field: str,
    *,
    maximum: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise OutcomeEvidenceError(f"{field} must be a string")
    if len(value) > maximum:
        raise OutcomeEvidenceError(f"{field} exceeds {maximum} characters")
    if not allow_empty and not value:
        raise OutcomeEvidenceError(f"{field} is required")
    if value != value.strip():
        raise OutcomeEvidenceError(f"{field} must not have surrounding whitespace")
    if unicodedata.normalize("NFC", value) != value:
        raise OutcomeEvidenceError(f"{field} must use canonical NFC text")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise OutcomeEvidenceError(f"{field} contains control or non-canonical characters")
    return value


def _identifier(value: Any, field: str) -> str:
    text = _canonical_text(value, field, maximum=128)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise OutcomeEvidenceError(f"{field} must be a canonical identifier")
    return text


def _security_code(value: Any, field: str) -> str:
    text = _canonical_text(value, field, maximum=32)
    if not _SECURITY_CODE_RE.fullmatch(text):
        raise OutcomeEvidenceError(f"{field} must be an official numeric security code")
    return text


def _timestamp(value: Any, field: str) -> datetime:
    text = _canonical_text(value, field, maximum=64)
    if "T" not in text:
        raise OutcomeEvidenceError(f"{field} must use canonical ISO-8601 date-time syntax")
    try:
        return parse_aware(text, field)
    except ValueError as exc:
        raise OutcomeEvidenceError(str(exc)) from exc


def _safe_https_url(value: Any, field: str) -> str:
    text = _canonical_text(value, field, maximum=2048)
    if any(character.isspace() for character in text):
        raise OutcomeEvidenceError(f"{field} must not contain whitespace")
    try:
        url = https_url(text, field)
        parsed = urlsplit(url)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise OutcomeEvidenceError(str(exc)) from exc
    if parsed.scheme != "https":
        raise OutcomeEvidenceError(f"{field} must use canonical lowercase https")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise OutcomeEvidenceError(f"{field} must use a public DNS host, not an IP literal")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise OutcomeEvidenceError(f"{field} must use a public DNS host")
    labels = host.split(".")
    if len(labels) < 2 or len(host) > 253 or any(not _DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        raise OutcomeEvidenceError(f"{field} has an invalid public DNS host")
    return url


def _content_type(value: Any, field: str) -> str:
    text = _canonical_text(value, field, maximum=127)
    if not _CONTENT_TYPE_RE.fullmatch(text):
        raise OutcomeEvidenceError(
            f"{field} must be a canonical lowercase media type without parameters"
        )
    return text


def _canonical_artifact_path(value: Any, field: str) -> Path:
    text = _canonical_text(value, field, maximum=1024)
    if "\\" in text:
        raise OutcomeEvidenceError(f"{field} must use forward slashes")
    try:
        relative = safe_relative_path(text, field)
    except ValueError as exc:
        raise OutcomeEvidenceError(str(exc)) from exc
    if len(relative.parts) < 2 or relative.parts[0] != "raw":
        raise OutcomeEvidenceError(f"{field} must identify a file below raw/")
    if relative.as_posix() != text or any(part in {"", ".", ".."} for part in relative.parts):
        raise OutcomeEvidenceError(f"{field} must be a canonical relative path")
    return relative


def _ensure_no_symlink_components(root: Path, relative: Path, field: str) -> Path:
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise OutcomeEvidenceError(f"{field} does not resolve to a file") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise OutcomeEvidenceError(f"{field} must not contain a symlink")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise OutcomeEvidenceError(f"{field} has a non-directory parent")
    try:
        resolved = current.resolve(strict=True)
    except OSError as exc:
        raise OutcomeEvidenceError(f"{field} does not resolve to a file") from exc
    if root not in resolved.parents or not resolved.is_file():
        raise OutcomeEvidenceError(f"{field} escapes the outcome evidence packet")
    return resolved


def _hash_regular_file(path: Path, field: str, *, maximum_bytes: int) -> tuple[str, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise OutcomeEvidenceError(f"{field} cannot be opened safely") from exc
    digest = hashlib.sha256()
    total = 0
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OutcomeEvidenceError(f"{field} must be a regular file")
        if before.st_size > maximum_bytes:
            raise OutcomeEvidenceError(f"outcome evidence exceeds {MAX_OUTCOME_EVIDENCE_BYTES} bytes")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise OutcomeEvidenceError(f"outcome evidence exceeds {MAX_OUTCOME_EVIDENCE_BYTES} bytes")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or total != after.st_size:
            raise OutcomeEvidenceError(f"{field} changed while it was being validated")
    finally:
        os.close(descriptor)
    return digest.hexdigest(), total


def _raw_inventory(root: Path) -> set[str]:
    raw_root = root / "raw"
    try:
        raw_metadata = os.lstat(raw_root)
    except OSError as exc:
        raise OutcomeEvidenceError("outcome evidence packet is missing raw/") from exc
    if stat.S_ISLNK(raw_metadata.st_mode) or not stat.S_ISDIR(raw_metadata.st_mode):
        raise OutcomeEvidenceError("outcome evidence raw/ must be a real directory")
    files: set[str] = set()
    for path in raw_root.rglob("*"):
        metadata = os.lstat(path)
        if stat.S_ISLNK(metadata.st_mode):
            raise OutcomeEvidenceError("outcome evidence raw/ must not contain symlinks")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise OutcomeEvidenceError("outcome evidence raw/ contains a non-regular file")
        files.add(path.relative_to(root).as_posix())
    return files


def validate_outcome_evidence_packet(
    packet_root: Path,
    *,
    outcome_id: str,
    decision_id: str,
    security_code: str,
    decision_at: str,
    observed_at: str,
) -> OutcomeEvidenceResult:
    """Validate and hash one immutable, outcome-linked raw evidence packet.

    The validator is reusable independently, while ``ResearchDecisionLedger``
    invokes it during append, verify, and seal.  Callers must provide the ledger
    envelope identity and timestamps so a packet cannot silently relabel itself
    for another outcome or decision.
    """

    expected_outcome_id = _identifier(outcome_id, "outcome_id")
    expected_decision_id = _identifier(decision_id, "decision_id")
    expected_security_code = _security_code(security_code, "security_code")
    decision_time = _timestamp(decision_at, "decision_at")
    outcome_time = _timestamp(observed_at, "observed_at")
    if outcome_time < decision_time:
        raise OutcomeEvidenceError("observed_at cannot precede decision_at")

    unresolved_root = Path(packet_root)
    if unresolved_root.is_symlink():
        raise OutcomeEvidenceError("outcome evidence packet root must not be a symlink")
    try:
        root = unresolved_root.resolve(strict=True)
    except OSError as exc:
        raise OutcomeEvidenceError("outcome evidence packet directory does not exist") from exc
    if not root.is_dir():
        raise OutcomeEvidenceError("outcome evidence packet root must be a directory")

    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise OutcomeEvidenceError("outcome evidence packet requires a regular manifest.json")
    try:
        manifest_size = manifest_path.stat().st_size
    except OSError as exc:
        raise OutcomeEvidenceError("outcome evidence manifest cannot be inspected") from exc
    if manifest_size > MAX_OUTCOME_EVIDENCE_MANIFEST_BYTES:
        raise OutcomeEvidenceError("outcome evidence manifest is too large")
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise OutcomeEvidenceError("outcome evidence manifest cannot be read") from exc
    manifest = _exact_object_fields(
        _strict_json_object(manifest_bytes, "manifest.json"),
        _MANIFEST_FIELDS,
        "manifest.json",
    )
    if manifest["schema_version"] != OUTCOME_EVIDENCE_SCHEMA_VERSION:
        raise OutcomeEvidenceError("unsupported outcome evidence schema_version")
    if _identifier(manifest["outcome_id"], "manifest.outcome_id") != expected_outcome_id:
        raise OutcomeEvidenceError("manifest outcome_id does not match the outcome envelope")
    if _identifier(manifest["decision_id"], "manifest.decision_id") != expected_decision_id:
        raise OutcomeEvidenceError("manifest decision_id does not match the decision envelope")
    if _security_code(manifest["security_code"], "manifest.security_code") != expected_security_code:
        raise OutcomeEvidenceError("manifest security_code does not match the outcome envelope")

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= MAX_OUTCOME_EVIDENCE_ARTIFACTS:
        raise OutcomeEvidenceError(
            f"manifest artifacts must contain 1..{MAX_OUTCOME_EVIDENCE_ARTIFACTS} entries"
        )

    parsed_rows: list[tuple[Path, str, int]] = []
    paths: set[str] = set()
    declared_hashes: set[str] = set()
    declared_total = 0
    for index, raw_row in enumerate(artifacts):
        field = f"manifest.artifacts[{index}]"
        row = _exact_object_fields(raw_row, _ARTIFACT_FIELDS, field)
        relative = _canonical_artifact_path(row["path"], f"{field}.path")
        relative_text = relative.as_posix()
        if relative_text in paths:
            raise OutcomeEvidenceError(f"manifest contains duplicate artifact path: {relative_text}")
        paths.add(relative_text)
        try:
            declared_hash = require_sha256(row["sha256"], f"{field}.sha256")
        except ValueError as exc:
            raise OutcomeEvidenceError(str(exc)) from exc
        if not isinstance(row["sha256"], str) or row["sha256"] != declared_hash:
            raise OutcomeEvidenceError(f"{field}.sha256 must be canonical lowercase hexadecimal")
        if declared_hash in declared_hashes:
            raise OutcomeEvidenceError("manifest contains duplicate artifact sha256")
        declared_hashes.add(declared_hash)
        declared_size = row["size_bytes"]
        if isinstance(declared_size, bool) or not isinstance(declared_size, int) or declared_size < 0:
            raise OutcomeEvidenceError(f"{field}.size_bytes must be a non-negative integer")
        declared_total += declared_size
        if declared_total > MAX_OUTCOME_EVIDENCE_BYTES:
            raise OutcomeEvidenceError(
                f"outcome evidence exceeds {MAX_OUTCOME_EVIDENCE_BYTES} declared bytes"
            )
        _identifier(row["source_id"], f"{field}.source_id")
        _safe_https_url(row["source_url"], f"{field}.source_url")
        _content_type(row["content_type"], f"{field}.content_type")
        artifact_time = _timestamp(row["observed_at"], f"{field}.observed_at")
        if artifact_time < decision_time or artifact_time > outcome_time:
            raise OutcomeEvidenceError(
                f"{field}.observed_at must satisfy decision_at <= artifact <= observed_at"
            )
        parsed_rows.append((relative, declared_hash, declared_size))

    inventory = _raw_inventory(root)
    if inventory != paths:
        missing = sorted(paths - inventory)
        unreferenced = sorted(inventory - paths)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unreferenced:
            details.append("unreferenced=" + ",".join(unreferenced))
        raise OutcomeEvidenceError("raw/ inventory does not match manifest: " + ";".join(details))

    actual_rows: list[dict[str, Any]] = []
    actual_hashes: list[str] = []
    actual_total = 0
    for relative, declared_hash, declared_size in sorted(parsed_rows, key=lambda item: item[0].as_posix()):
        path = _ensure_no_symlink_components(root, relative, relative.as_posix())
        actual_hash, actual_size = _hash_regular_file(
            path,
            relative.as_posix(),
            maximum_bytes=MAX_OUTCOME_EVIDENCE_BYTES - actual_total,
        )
        if actual_size != declared_size:
            raise OutcomeEvidenceError(f"artifact size mismatch: {relative.as_posix()}")
        if actual_hash != declared_hash:
            raise OutcomeEvidenceError(f"artifact sha256 mismatch: {relative.as_posix()}")
        actual_total += actual_size
        actual_hashes.append(actual_hash)
        actual_rows.append(
            {"path": relative.as_posix(), "sha256": actual_hash, "size_bytes": actual_size}
        )
    if actual_total > MAX_OUTCOME_EVIDENCE_BYTES:
        raise OutcomeEvidenceError(f"outcome evidence exceeds {MAX_OUTCOME_EVIDENCE_BYTES} bytes")

    packet_entries = [
        {"path": "manifest.json", "sha256": sha256_bytes(manifest_bytes)},
        *actual_rows,
    ]
    packet_hash = sha256_bytes(canonical_json_bytes(packet_entries))
    return OutcomeEvidenceResult(
        outcome_id=expected_outcome_id,
        decision_id=expected_decision_id,
        security_code=expected_security_code,
        packet_hash=packet_hash,
        artifact_hashes=tuple(actual_hashes),
        artifact_count=len(actual_hashes),
        total_bytes=actual_total,
    )


def validate_outcome_payload(
    payload: dict[str, Any],
    *,
    expected_security_code: str,
    decision_at: str,
    observed_at: str,
) -> dict[str, Any]:
    """Return a detached strict-JSON outcome measurement after validation."""

    snapshot = _exact_object_fields(
        _strict_json_snapshot(payload, "outcome payload"),
        _OUTCOME_PAYLOAD_FIELDS,
        "outcome payload",
    )
    if snapshot["schema_version"] != OUTCOME_EVIDENCE_SCHEMA_VERSION:
        raise OutcomeEvidenceError("unsupported outcome payload schema_version")
    expected_code = _security_code(expected_security_code, "expected_security_code")
    if _security_code(snapshot["security_code"], "security_code") != expected_code:
        raise OutcomeEvidenceError("outcome payload security_code does not match the decision")
    _identifier(snapshot["metric_id"], "metric_id")
    _identifier(snapshot["method_id"], "method_id")
    unit = snapshot["unit"]
    if not isinstance(unit, str) or unit not in OUTCOME_UNITS:
        raise OutcomeEvidenceError("unit is not supported")
    value = snapshot["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutcomeEvidenceError("value must be a finite JSON number")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise OutcomeEvidenceError("value must be a finite JSON number") from exc
    if not finite:
        raise OutcomeEvidenceError("value must be a finite JSON number")
    if unit == "COUNT" and (not isinstance(value, int) or value < 0):
        raise OutcomeEvidenceError("COUNT value must be a non-negative JSON integer")
    if unit == "BOOLEAN_FLAG" and (not isinstance(value, int) or value not in {0, 1}):
        raise OutcomeEvidenceError("BOOLEAN_FLAG value must be the JSON integer 0 or 1")
    _canonical_text(snapshot["notes"], "notes", maximum=2000, allow_empty=True)

    decision_time = _timestamp(decision_at, "decision_at")
    outcome_time = _timestamp(observed_at, "observed_at")
    start = _timestamp(snapshot["measurement_start_at"], "measurement_start_at")
    end = _timestamp(snapshot["measurement_end_at"], "measurement_end_at")
    if not decision_time <= start <= end <= outcome_time:
        raise OutcomeEvidenceError(
            "measurement timestamps must satisfy decision_at <= start <= end <= observed_at"
        )
    return snapshot


__all__ = [
    "MAX_OUTCOME_EVIDENCE_ARTIFACTS",
    "MAX_OUTCOME_EVIDENCE_BYTES",
    "OUTCOME_EVIDENCE_SCHEMA_VERSION",
    "OUTCOME_UNITS",
    "OutcomeEvidenceError",
    "OutcomeEvidenceResult",
    "validate_outcome_evidence_packet",
    "validate_outcome_payload",
]
