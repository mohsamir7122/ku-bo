from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .strict import parse_aware


RUNTIME_TRUST_AUDIENCE = "kubo-source-network"
RUNTIME_TRUST_ALGORITHM = "HMAC-SHA256"

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "audience",
        "registry_id",
        "issued_at",
        "expires_at",
        "entries",
        "authentication",
    }
)
_ENTRY_KEYS = frozenset(
    {
        "source_id",
        "subject_id",
        "domains",
        "security_codes",
        "activation_id",
        "entitlement_id",
        "valid_from",
        "valid_until",
    }
)
_AUTHENTICATION_KEYS = frozenset({"algorithm", "key_id", "tag"})
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TAG_RE = re.compile(r"^[0-9a-f]{64}$")
_LOCAL_DOMAIN_SUFFIXES = frozenset(
    {"home", "internal", "lan", "local", "localdomain", "localhost", "onion"}
)


class RuntimeTrustError(ValueError):
    """Raised when an external runtime trust registry cannot be trusted."""


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeTrustError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> None:
    raise RuntimeTrustError(f"non-finite JSON value is forbidden: {value}")


def _exact_keys(value: Any, expected: frozenset[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeTrustError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise RuntimeTrustError(f"{field} keys must be strings")
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise RuntimeTrustError(f"{field} missing keys: {','.join(missing)}")
    if unknown:
        raise RuntimeTrustError(f"{field} has unknown keys: {','.join(unknown)}")
    return value


def _identifier(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or value != value.strip() or not _IDENTIFIER_RE.fullmatch(value):
        raise RuntimeTrustError(f"{field} must be a non-empty canonical identifier")
    return value


def _normalize_domain(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise RuntimeTrustError(f"{field} must be a canonical HTTPS domain")
    domain = value.lower().rstrip(".")
    if domain != value:
        raise RuntimeTrustError(f"{field} must be lowercase without a trailing dot")
    if len(domain) > 253 or "." not in domain:
        raise RuntimeTrustError(f"{field} must be a registrable-looking HTTPS domain")
    if any(marker in domain for marker in ("://", "/", "?", "#", "@", ":", "*")):
        raise RuntimeTrustError(f"{field} must contain a hostname only")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise RuntimeTrustError(f"{field} must not be an IP address")
    labels = domain.split(".")
    if any(not _DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        raise RuntimeTrustError(f"{field} contains an invalid DNS label")
    if labels[-1] in _LOCAL_DOMAIN_SUFFIXES:
        raise RuntimeTrustError(f"{field} must not use a local or non-public domain suffix")
    return domain


def _security_code(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.isdigit():
        raise RuntimeTrustError(f"{field} must be a numeric string")
    return value


def _decision_time(value: Any) -> datetime:
    try:
        return parse_aware(value, "decision_at")
    except ValueError as exc:
        raise RuntimeTrustError(str(exc)) from exc


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeTrustError(f"registry is not canonicalizable JSON: {exc}") from exc
    return text.encode("utf-8")


def _canonical_registry_content_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return only the portable registry content used for provenance."""

    if not isinstance(payload, Mapping):
        raise RuntimeTrustError("registry must be an object")
    unsigned = {key: value for key, value in payload.items() if key != "authentication"}
    return _canonical_json_bytes(unsigned)


def canonical_registry_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return HMAC input binding content, algorithm, and key identity.

    The authentication tag itself is excluded.  The provenance digest remains
    the digest of the portable registry content alone.
    """

    if not isinstance(payload, Mapping):
        raise RuntimeTrustError("registry must be an object")
    authentication = payload.get("authentication")
    if not isinstance(authentication, Mapping):
        raise RuntimeTrustError("authentication must be an object")
    authenticated_value = {
        "registry": {
            key: value for key, value in payload.items() if key != "authentication"
        },
        "algorithm": authentication.get("algorithm"),
        "key_id": authentication.get("key_id"),
    }
    return _canonical_json_bytes(authenticated_value)


@dataclass(frozen=True)
class RuntimeTrustEntry:
    source_id: str
    subject_id: str
    domains: tuple[str, ...]
    security_codes: frozenset[str]
    activation_id: str | None
    entitlement_id: str | None
    valid_from: datetime
    valid_until: datetime

    def active_at(self, decision_at: Any) -> bool:
        instant = _decision_time(decision_at)
        return self.valid_from <= instant < self.valid_until

    def authorizes_domain(self, domain: str) -> bool:
        candidate = _normalize_domain(domain, "domain")
        return any(candidate == allowed or candidate.endswith("." + allowed) for allowed in self.domains)


@dataclass(frozen=True)
class RuntimeTrustRegistry:
    registry_id: str
    issued_at: datetime
    expires_at: datetime
    entries: tuple[RuntimeTrustEntry, ...]
    authenticated_key_id: str
    content_sha256: str

    def active_at(self, decision_at: Any) -> bool:
        instant = _decision_time(decision_at)
        return self.issued_at <= instant < self.expires_at

    def _active_entries(self, source_id: str, decision_at: Any) -> tuple[RuntimeTrustEntry, ...]:
        source = _identifier(source_id, "source_id")
        instant = _decision_time(decision_at)
        if not self.issued_at <= instant < self.expires_at:
            raise RuntimeTrustError("runtime trust registry is not valid at decision_at")
        return tuple(
            entry
            for entry in self.entries
            if entry.source_id == source and entry.valid_from <= instant < entry.valid_until
        )

    def require_authority(
        self,
        *,
        source_id: str,
        subject_id: str,
        domain: str,
        decision_at: Any,
        security_code: str | None = None,
    ) -> RuntimeTrustEntry:
        subject = _identifier(subject_id, "subject_id")
        code = None if security_code is None else _security_code(security_code, "security_code")
        matches = [
            entry
            for entry in self._active_entries(source_id, decision_at)
            if entry.subject_id == subject
            and (code is None or code in entry.security_codes)
            and entry.authorizes_domain(domain)
        ]
        if len(matches) != 1:
            raise RuntimeTrustError("runtime authority is not uniquely authorized")
        return matches[0]

    def require_activation(
        self,
        *,
        source_id: str,
        activation_id: str,
        decision_at: Any,
        security_code: str | None = None,
    ) -> RuntimeTrustEntry:
        activation = _identifier(activation_id, "activation_id")
        code = None if security_code is None else _security_code(security_code, "security_code")
        matches = [
            entry
            for entry in self._active_entries(source_id, decision_at)
            if entry.activation_id == activation
            and (code is None or code in entry.security_codes)
        ]
        if len(matches) != 1:
            raise RuntimeTrustError("runtime activation is not uniquely authorized")
        return matches[0]

    def require_entitlement(
        self,
        *,
        source_id: str,
        entitlement_id: str,
        decision_at: Any,
        security_code: str | None = None,
    ) -> RuntimeTrustEntry:
        entitlement = _identifier(entitlement_id, "entitlement_id")
        code = None if security_code is None else _security_code(security_code, "security_code")
        matches = [
            entry
            for entry in self._active_entries(source_id, decision_at)
            if entry.entitlement_id == entitlement
            and (code is None or code in entry.security_codes)
        ]
        if len(matches) != 1:
            raise RuntimeTrustError("runtime entitlement is not uniquely authorized")
        return matches[0]


def _parse_registry(
    payload: dict[str, Any],
    *,
    key: bytes,
    expected_key_id: str,
    decision_at: Any,
) -> RuntimeTrustRegistry:
    top = _exact_keys(payload, _TOP_LEVEL_KEYS, "registry")
    if top["schema_version"] != "1.0":
        raise RuntimeTrustError("unsupported runtime trust registry schema")
    if top["audience"] != RUNTIME_TRUST_AUDIENCE:
        raise RuntimeTrustError("runtime trust registry audience mismatch")
    registry_id = _identifier(top["registry_id"], "registry_id")
    assert registry_id is not None

    if not isinstance(key, bytes) or len(key) < 32:
        raise RuntimeTrustError("runtime trust HMAC key must contain at least 32 bytes")
    expected = _identifier(expected_key_id, "expected_key_id")
    assert expected is not None
    authentication = _exact_keys(top["authentication"], _AUTHENTICATION_KEYS, "authentication")
    if authentication["algorithm"] != RUNTIME_TRUST_ALGORITHM:
        raise RuntimeTrustError("unsupported runtime trust authentication algorithm")
    key_id = _identifier(authentication["key_id"], "authentication.key_id")
    if key_id != expected:
        raise RuntimeTrustError("runtime trust authentication key_id mismatch")
    tag = authentication["tag"]
    if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
        raise RuntimeTrustError("authentication.tag must be a lowercase HMAC-SHA256 tag")
    authenticated_bytes = canonical_registry_bytes(top)
    calculated = hmac.new(key, authenticated_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, tag):
        raise RuntimeTrustError("runtime trust authentication failed")

    try:
        issued_at = parse_aware(top["issued_at"], "issued_at")
        expires_at = parse_aware(top["expires_at"], "expires_at")
    except ValueError as exc:
        raise RuntimeTrustError(str(exc)) from exc
    if issued_at >= expires_at:
        raise RuntimeTrustError("issued_at must precede expires_at")
    instant = _decision_time(decision_at)
    if not issued_at <= instant < expires_at:
        raise RuntimeTrustError("runtime trust registry is not valid at decision_at")

    rows = top["entries"]
    if not isinstance(rows, list) or not rows:
        raise RuntimeTrustError("entries must be a non-empty list")
    entries: list[RuntimeTrustEntry] = []
    seen_entries: set[tuple[str, str, str | None, str | None]] = set()
    for index, value in enumerate(rows):
        row = _exact_keys(value, _ENTRY_KEYS, f"entries[{index}]")
        source_id = _identifier(row["source_id"], f"entries[{index}].source_id")
        subject_id = _identifier(row["subject_id"], f"entries[{index}].subject_id")
        assert source_id is not None and subject_id is not None
        raw_domains = row["domains"]
        if not isinstance(raw_domains, list) or not raw_domains:
            raise RuntimeTrustError(f"entries[{index}].domains must be a non-empty list")
        domains = tuple(
            _normalize_domain(item, f"entries[{index}].domains") for item in raw_domains
        )
        if len(domains) != len(set(domains)):
            raise RuntimeTrustError(f"entries[{index}].domains contains duplicates")
        raw_codes = row["security_codes"]
        if not isinstance(raw_codes, list) or not raw_codes:
            raise RuntimeTrustError(f"entries[{index}].security_codes must be a non-empty list")
        codes = tuple(
            _security_code(item, f"entries[{index}].security_codes") for item in raw_codes
        )
        if len(codes) != len(set(codes)):
            raise RuntimeTrustError(f"entries[{index}].security_codes contains duplicates")
        activation_id = _identifier(
            row["activation_id"], f"entries[{index}].activation_id", nullable=True
        )
        entitlement_id = _identifier(
            row["entitlement_id"], f"entries[{index}].entitlement_id", nullable=True
        )
        try:
            valid_from = parse_aware(row["valid_from"], f"entries[{index}].valid_from")
            valid_until = parse_aware(row["valid_until"], f"entries[{index}].valid_until")
        except ValueError as exc:
            raise RuntimeTrustError(str(exc)) from exc
        if not issued_at <= valid_from < valid_until <= expires_at:
            raise RuntimeTrustError(f"entries[{index}] validity is outside the registry envelope")
        identity = (source_id, subject_id, activation_id, entitlement_id)
        if identity in seen_entries:
            raise RuntimeTrustError(f"duplicate runtime trust entry: {source_id}:{subject_id}")
        seen_entries.add(identity)
        entries.append(
            RuntimeTrustEntry(
                source_id=source_id,
                subject_id=subject_id,
                domains=domains,
                security_codes=frozenset(codes),
                activation_id=activation_id,
                entitlement_id=entitlement_id,
                valid_from=valid_from,
                valid_until=valid_until,
            )
        )

    return RuntimeTrustRegistry(
        registry_id=registry_id,
        issued_at=issued_at,
        expires_at=expires_at,
        entries=tuple(entries),
        authenticated_key_id=key_id,
        content_sha256=hashlib.sha256(_canonical_registry_content_bytes(top)).hexdigest(),
    )


def verify_runtime_trust_registry(
    document: Mapping[str, Any] | str | bytes,
    *,
    key: bytes,
    expected_key_id: str,
    decision_at: Any,
) -> RuntimeTrustRegistry:
    """Authenticate and validate an external registry, failing closed."""

    if isinstance(document, Mapping):
        payload = dict(document)
    else:
        if isinstance(document, bytes):
            try:
                text = document.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RuntimeTrustError("runtime trust registry must be UTF-8 JSON") from exc
        elif isinstance(document, str):
            text = document
        else:
            raise RuntimeTrustError("runtime trust registry must be JSON bytes, text, or an object")
        try:
            payload = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_object_keys,
                parse_constant=_reject_non_json_constant,
            )
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeTrustError(f"invalid runtime trust registry JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeTrustError("registry must be an object")
    return _parse_registry(
        payload,
        key=key,
        expected_key_id=expected_key_id,
        decision_at=decision_at,
    )


def load_runtime_trust_registry(
    path: Path,
    *,
    key: bytes,
    expected_key_id: str,
    decision_at: Any,
) -> RuntimeTrustRegistry:
    """Read and authenticate a registry from a trusted out-of-packet path."""

    try:
        document = path.read_bytes()
    except OSError as exc:
        raise RuntimeTrustError(f"cannot read runtime trust registry: {exc}") from exc
    return verify_runtime_trust_registry(
        document,
        key=key,
        expected_key_id=expected_key_id,
        decision_at=decision_at,
    )


__all__ = [
    "RUNTIME_TRUST_ALGORITHM",
    "RUNTIME_TRUST_AUDIENCE",
    "RuntimeTrustEntry",
    "RuntimeTrustError",
    "RuntimeTrustRegistry",
    "canonical_registry_bytes",
    "load_runtime_trust_registry",
    "verify_runtime_trust_registry",
]
