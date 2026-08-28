"""Authenticated authority for private KU-BO runtime storage.

This module validates a private, HMAC-authenticated grant.  It does not create
directories, write checkpoints, resolve Drive identifiers, or turn a logical
path into a physical storage location.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
from pathlib import Path
import re
import weakref
from typing import Any, Mapping

from .foundation_io import load_strict_json_object
from .strict import parse_aware


STORAGE_AUTHORITY_SCHEMA_VERSION = "runtime-storage-authority-v1"
STORAGE_AUTHORITY_AUDIENCE = "kubo-issuer-security-checkpoint"
STORAGE_AUTHORITY_ALGORITHM = "HMAC-SHA256"
STORAGE_LOGICAL_ROOT = "AI Rebuild/04_Curated_Core/KU_BO"
STORAGE_STORE_KIND = "AUTHORIZED_FILESYSTEM"
STORAGE_MARKET = "BOURSA_KUWAIT"
STORAGE_ALLOWED_SUBPATHS = (
    "00_Manifests/Issuer_Security_Runs",
    "02_Event_Evidence/Issuer_Security_Runs",
)
STORAGE_OPERATIONS = (
    "READ_REOPEN",
    "CREATE_EXCLUSIVE",
    "APPEND_GENERATION",
)

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "audience",
        "grant_id",
        "subject_id",
        "logical_root",
        "allowed_subpaths",
        "store_kind",
        "market",
        "security_codes",
        "operations",
        "issued_at",
        "expires_at",
        "authentication",
    }
)
_AUTHENTICATION_KEYS = frozenset({"algorithm", "key_id", "tag"})
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_TAG_RE = re.compile(r"^[0-9a-f]{64}$")


class RuntimeStorageAuthorityError(ValueError):
    """Raised when a private runtime storage grant is not trustworthy."""


def _exact_object(value: Any, expected: frozenset[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeStorageAuthorityError(f"{field} must be an object")
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise RuntimeStorageAuthorityError(f"{field} missing keys: {','.join(missing)}")
    if unknown:
        raise RuntimeStorageAuthorityError(f"{field} has unknown keys: {','.join(unknown)}")
    return value


def _identifier(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _IDENTIFIER_RE.fullmatch(value) is None
    ):
        raise RuntimeStorageAuthorityError(f"{field} must be a canonical identifier")
    return value


def _security_code(value: Any, field: str = "security_code") -> str:
    if not isinstance(value, str) or not value or not value.isdigit():
        raise RuntimeStorageAuthorityError(f"{field} must be a non-empty numeric string")
    return value


def _decision_time(value: Any, field: str) -> datetime:
    if isinstance(value, bool):
        raise RuntimeStorageAuthorityError(f"{field} must be a timezone-aware date-time")
    try:
        return parse_aware(value, field)
    except (TypeError, ValueError) as exc:
        raise RuntimeStorageAuthorityError(str(exc)) from exc


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RuntimeStorageAuthorityError(
            f"storage authority is not canonicalizable JSON: {exc}"
        ) from exc


def _authenticated_bytes(payload: Mapping[str, Any]) -> bytes:
    authentication = payload.get("authentication")
    if not isinstance(authentication, Mapping):
        raise RuntimeStorageAuthorityError("authentication must be an object")
    unsigned_authentication = {
        key: value for key, value in authentication.items() if key != "tag"
    }
    unsigned = dict(payload)
    unsigned["authentication"] = unsigned_authentication
    return _canonical_json_bytes(unsigned)


@dataclass(frozen=True, eq=False)
class RuntimeStorageAuthority:
    grant_id: str
    subject_id: str
    logical_root: str
    allowed_subpaths: tuple[str, ...]
    store_kind: str
    market: str
    security_codes: frozenset[str]
    operations: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    authenticated_key_id: str
    content_sha256: str

    def active_at(self, decision_at: Any) -> bool:
        instant = _decision_time(decision_at, "decision_at")
        return self.issued_at <= instant < self.expires_at


_AUTHORITY_ADMISSIONS: weakref.WeakKeyDictionary[
    RuntimeStorageAuthority, tuple[Any, ...]
] = weakref.WeakKeyDictionary()
_AUTHORITY_FIELD_NAMES = frozenset(RuntimeStorageAuthority.__dataclass_fields__)


def _authority_state(authority: RuntimeStorageAuthority) -> tuple[Any, ...]:
    return (
        authority.grant_id,
        authority.subject_id,
        authority.logical_root,
        authority.allowed_subpaths,
        authority.store_kind,
        authority.market,
        authority.security_codes,
        authority.operations,
        authority.issued_at,
        authority.expires_at,
        authority.authenticated_key_id,
        authority.content_sha256,
    )


def load_runtime_storage_authority(
    path: Path | str,
    key: bytes | bytearray,
    expected_key_id: str,
    decision_at: Any,
) -> RuntimeStorageAuthority:
    """Load and authenticate one narrowly scoped private-storage grant."""

    if isinstance(key, bool) or not isinstance(key, (bytes, bytearray)):
        raise RuntimeStorageAuthorityError("storage authority HMAC key must be bytes")
    key_bytes = bytes(key)
    if len(key_bytes) < 32:
        raise RuntimeStorageAuthorityError(
            "storage authority HMAC key must contain at least 32 bytes"
        )
    checked_key_id = _identifier(expected_key_id, "expected_key_id")
    instant = _decision_time(decision_at, "decision_at")

    try:
        payload, _content = load_strict_json_object(
            Path(path),
            field="runtime storage authority",
            max_bytes=1024 * 1024,
        )
    except ValueError as exc:
        raise RuntimeStorageAuthorityError(str(exc)) from exc
    root = _exact_object(payload, _TOP_LEVEL_KEYS, "runtime storage authority")

    if root["schema_version"] != STORAGE_AUTHORITY_SCHEMA_VERSION:
        raise RuntimeStorageAuthorityError("unsupported storage authority schema")
    if root["audience"] != STORAGE_AUTHORITY_AUDIENCE:
        raise RuntimeStorageAuthorityError("storage authority audience mismatch")
    grant_id = _identifier(root["grant_id"], "grant_id")
    subject_id = _identifier(root["subject_id"], "subject_id")
    if root["logical_root"] != STORAGE_LOGICAL_ROOT:
        raise RuntimeStorageAuthorityError("storage authority logical root mismatch")
    if root["allowed_subpaths"] != list(STORAGE_ALLOWED_SUBPATHS):
        raise RuntimeStorageAuthorityError("storage authority subpaths differ from policy")
    if root["store_kind"] != STORAGE_STORE_KIND:
        raise RuntimeStorageAuthorityError("storage authority store kind mismatch")
    if root["market"] != STORAGE_MARKET:
        raise RuntimeStorageAuthorityError("storage authority market mismatch")
    if root["operations"] != list(STORAGE_OPERATIONS):
        raise RuntimeStorageAuthorityError("storage authority operations differ from policy")

    codes = root["security_codes"]
    if not isinstance(codes, list) or len(codes) != 1:
        raise RuntimeStorageAuthorityError(
            "storage authority must bind exactly one security"
        )
    code = _security_code(codes[0], "security_codes[0]")

    issued_at = _decision_time(root["issued_at"], "issued_at")
    expires_at = _decision_time(root["expires_at"], "expires_at")
    if issued_at >= expires_at:
        raise RuntimeStorageAuthorityError("storage authority validity window is empty")
    if not issued_at <= instant < expires_at:
        raise RuntimeStorageAuthorityError(
            "storage authority is not valid at decision_at"
        )

    authentication = _exact_object(
        root["authentication"], _AUTHENTICATION_KEYS, "authentication"
    )
    if authentication["algorithm"] != STORAGE_AUTHORITY_ALGORITHM:
        raise RuntimeStorageAuthorityError("storage authority algorithm mismatch")
    key_id = _identifier(authentication["key_id"], "authentication.key_id")
    if key_id != checked_key_id:
        raise RuntimeStorageAuthorityError("storage authority key_id mismatch")
    tag = authentication["tag"]
    if not isinstance(tag, str) or _TAG_RE.fullmatch(tag) is None:
        raise RuntimeStorageAuthorityError(
            "authentication.tag must be a lowercase HMAC-SHA256 tag"
        )
    authenticated_bytes = _authenticated_bytes(root)
    calculated = hmac.new(key_bytes, authenticated_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, tag):
        raise RuntimeStorageAuthorityError("storage authority HMAC verification failed")

    authority = RuntimeStorageAuthority(
        grant_id=grant_id,
        subject_id=subject_id,
        logical_root=STORAGE_LOGICAL_ROOT,
        allowed_subpaths=STORAGE_ALLOWED_SUBPATHS,
        store_kind=STORAGE_STORE_KIND,
        market=STORAGE_MARKET,
        security_codes=frozenset({code}),
        operations=STORAGE_OPERATIONS,
        issued_at=issued_at,
        expires_at=expires_at,
        authenticated_key_id=key_id,
        content_sha256=hashlib.sha256(authenticated_bytes).hexdigest(),
    )
    _AUTHORITY_ADMISSIONS[authority] = _authority_state(authority)
    return authority


def require_storage_grant(
    authority: RuntimeStorageAuthority,
    logical_root: str,
    security_code: str,
    operation: str,
    decision_at: Any,
) -> RuntimeStorageAuthority:
    """Require an authenticated active grant for one exact storage operation."""

    if not isinstance(authority, RuntimeStorageAuthority):
        raise RuntimeStorageAuthorityError(
            "storage authority must be loaded from an authenticated registry"
        )
    try:
        admitted_state = _AUTHORITY_ADMISSIONS.get(authority)
        current_state = _authority_state(authority)
        instance_fields = frozenset(vars(authority))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeStorageAuthorityError(
            "storage authority admission state is invalid"
        ) from exc
    if (
        admitted_state is None
        or current_state != admitted_state
        or instance_fields != _AUTHORITY_FIELD_NAMES
    ):
        raise RuntimeStorageAuthorityError(
            "storage authority was not admitted by the authenticated loader or was modified"
        )
    if not isinstance(logical_root, str) or logical_root != STORAGE_LOGICAL_ROOT:
        raise RuntimeStorageAuthorityError("requested logical root is not authorized")
    if authority.logical_root != logical_root:
        raise RuntimeStorageAuthorityError("authority logical root differs")
    code = _security_code(security_code)
    if authority.security_codes != frozenset({code}):
        raise RuntimeStorageAuthorityError("security_code is not uniquely authorized")
    if not isinstance(operation, str) or operation not in STORAGE_OPERATIONS:
        raise RuntimeStorageAuthorityError("storage operation is not authorized")
    if operation not in authority.operations:
        raise RuntimeStorageAuthorityError("authority does not contain the operation")
    instant = _decision_time(decision_at, "decision_at")
    if not authority.issued_at <= instant < authority.expires_at:
        raise RuntimeStorageAuthorityError(
            "storage authority is not valid at decision_at"
        )
    return authority


__all__ = [
    "RuntimeStorageAuthorityError",
    "STORAGE_ALLOWED_SUBPATHS",
    "STORAGE_AUTHORITY_ALGORITHM",
    "STORAGE_AUTHORITY_AUDIENCE",
    "STORAGE_AUTHORITY_SCHEMA_VERSION",
    "STORAGE_LOGICAL_ROOT",
    "STORAGE_MARKET",
    "STORAGE_OPERATIONS",
    "STORAGE_STORE_KIND",
    "load_runtime_storage_authority",
    "require_storage_grant",
]
