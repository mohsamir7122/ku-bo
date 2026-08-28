"""Synthetic-only, security-aware durable checkpoint contract.

This module is deliberately separate from :mod:`kubo.priority_runtime`.  The
legacy DATE/PAGE shard schema remains unchanged.  A v2 checkpoint binds exactly
one validated issuer-sequential plan security, its 29 ordered source attempts,
reopened raw bytes, reconciliation, and an HMAC terminal seal.

Constructing this store does not authorize a production checkpoint location,
source access, private-runtime writes, or a second security.

Production remains blocked on an authority-owned evidence store that can pin a
manifest/raw snapshot across validation and checkpoint publication.  This
synthetic local contract reopens and rehashes evidence but does not claim to
eliminate that external evidence-store TOCTOU boundary.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import ipaddress
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import urlsplit

from .foundation_io import (
    load_strict_json_object,
    require_real_directory,
    safe_regular_file,
    snapshot_regular_tree,
    strict_json_object,
)
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .issuer_sequential_collection import (
    IssuerSequentialCollectionError,
    SOURCE_WAVE_IDS,
    SOURCE_WAVE_SOURCES,
    TERMINAL_SOURCE_STATUSES,
    _SOURCE_RECEIPT_FIELDS,
    _attempt_receipt,
    _validate_compiled_plan,
)
from .runtime_trust import RuntimeTrustRegistry
from .source_network import SourceNetworkCatalog
from .strict import https_url, parse_aware, require_sha256, safe_relative_path


POLICY_PATH = Path("config/issuer_security_checkpoint_policy.json")
SCHEMA_VERSION = "issuer-security-checkpoint-v2"
RECONCILIATION_VERSION = "issuer-security-reconciliation-v1"
TERMINAL_SEAL_VERSION = "issuer-security-terminal-seal-v1"
CHECKPOINT_STATUSES = frozenset({"RUNNING", "PREEMPTED", "RECONCILED", "SEALED"})
SLOT_STATUSES = frozenset({"PENDING", "IN_PROGRESS", "TERMINAL"})
MAX_REVISION_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RAW_BYTES = 512 * 1024 * 1024
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_LOCAL_DOMAIN_SUFFIXES = frozenset({"local", "localhost", "internal", "test", "invalid"})
_REVISION_RE = re.compile(r"^(ISCP2-[A-F0-9]{24})\.revision-([0-9]{8})\.json$")
_STAGE_RE = re.compile(
    r"^\.(ISCP2-[A-F0-9]{24}\.revision-[0-9]{8}\.json)\.stage-([0-9a-f]{32})\.tmp$"
)
EXTERNAL_EVIDENCE_STORE_TOCTOU_STATUS = (
    "BLOCKED_PENDING_AUTHORITY_OWNED_SNAPSHOT_AND_ATOMIC_PUBLICATION"
)

CLAIM_BOUNDARIES = {
    "synthetic_checkpoint_is_live_operational": False,
    "content_digest_is_external_authentication": False,
    "checkpoint_grants_source_access": False,
    "checkpoint_grants_private_runtime_write_authority": False,
    "checkpoint_unlocks_training_backtest_forecast_or_execution": False,
    "terminal_seal_authorizes_a_second_security": False,
}
EXPECTED_POLICY = {
    "schema_version": "1.0",
    "policy_id": "ku-bo-issuer-security-checkpoint-v2",
    "status": "SYNTHETIC_CONTRACT_ONLY",
    "market": "BOURSA_KUWAIT",
    "scope": {
        "security_count": 1,
        "planned_source_count": 29,
        "wave_count": 7,
        "max_active_sources": 1,
        "maximum_worker_attempts_per_source": 2,
    },
    "cas": {
        "revision_required": True,
        "generation_required": True,
        "fencing_token_required": True,
        "owner_run_id_required": True,
        "prior_checkpoint_digest_required": True,
        "revision_files_create_exclusive": True,
        "terminal_sources_immutable": True,
    },
    "completion": {
        "all_29_terminal_before_reconciliation": True,
        "all_manifests_reopened_before_reconciliation": True,
        "terminal_hmac_required": True,
        "second_security_allowed": False,
    },
    "production": {
        "authorized": False,
        "status": "BLOCKED_PENDING_DURABLE_STORE_AND_RUNTIME_AUTHORITY",
    },
    "claim_boundaries": CLAIM_BOUNDARIES,
}

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "checkpoint_id",
        "policy_id",
        "policy_sha256",
        "run_id",
        "plan_id",
        "plan_sha256",
        "issuer_universe_sha256",
        "market",
        "security",
        "status",
        "revision",
        "generation",
        "fencing_token",
        "owner_run_id",
        "created_at",
        "updated_at",
        "source_slots",
        "reconciliation",
        "terminal_seal",
        "prior_checkpoint_digest",
        "checkpoint_digest",
        "production_authorized",
        "claim_boundaries",
    }
)
_SECURITY_KEYS = frozenset(
    {
        "ordinal",
        "issuer_id",
        "security_code",
        "ticker",
        "identity_sha256",
        "source_plan_sha256",
    }
)
_SLOT_KEYS = frozenset(
    {
        "source_ordinal",
        "wave_ordinal",
        "wave_id",
        "source_id",
        "status",
        "attempt_count",
        "idempotency_key",
        "started_at",
        "completed_at",
        "source_receipt",
        "evidence_manifest",
    }
)
_EVIDENCE_KEYS = frozenset(
    {"manifest_path", "manifest_sha256", "artifact_count", "raw_sha256s"}
)
_RECON_KEYS = frozenset(
    {
        "schema_version",
        "checkpoint_id",
        "plan_sha256",
        "security_code",
        "planned_source_count",
        "terminal_source_count",
        "wave_count",
        "source_receipt_sha256s",
        "manifest_sha256s",
        "status",
        "reconciled_at",
        "reconciliation_sha256",
    }
)
_SEAL_KEYS = frozenset(
    {
        "schema_version",
        "checkpoint_id",
        "plan_sha256",
        "security_code",
        "identity_sha256",
        "reconciliation_sha256",
        "preseal_checkpoint_digest",
        "source_receipt_sha256s",
        "manifest_sha256s",
        "previous_security_seal_sha256",
        "algorithm",
        "key_id",
        "sealed_at",
        "production_authorized",
        "second_security_authorized",
        "seal_tag",
    }
)


class IssuerSecurityCheckpointError(ValueError):
    """Raised when checkpoint state, evidence, or a terminal seal is invalid."""


class IssuerSecurityCheckpointCasError(IssuerSecurityCheckpointError):
    """Raised when revision/generation/digest compare-and-swap state is stale."""


class IssuerSecurityCheckpointFencingError(IssuerSecurityCheckpointError):
    """Raised when an owner or fencing token is stale."""


def _exact(value: Any, keys: frozenset[str], field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise IssuerSecurityCheckpointError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise IssuerSecurityCheckpointError(
            f"{field} fields differ: missing={sorted(keys - actual)} extra={sorted(actual - keys)}"
        )
    return dict(value)


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or _ID_RE.fullmatch(value) is None:
        raise IssuerSecurityCheckpointError(f"{field} must be a safe identifier")
    return value


def _requested_domain(value: Any) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise IssuerSecurityCheckpointError(
            "requested_domain must be a canonical public hostname"
        )
    if value != value.casefold() or value.endswith(".") or len(value) > 253 or "." not in value:
        raise IssuerSecurityCheckpointError(
            "requested_domain must be lowercase, undotted at the end, and registrable-looking"
        )
    if any(marker in value for marker in ("://", "/", "?", "#", "@", ":", "*")):
        raise IssuerSecurityCheckpointError("requested_domain must contain a hostname only")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise IssuerSecurityCheckpointError("requested_domain must not be an IP address")
    labels = value.split(".")
    if any(_DOMAIN_LABEL_RE.fullmatch(label) is None for label in labels):
        raise IssuerSecurityCheckpointError(
            "requested_domain contains an invalid DNS label"
        )
    if labels[-1] in _LOCAL_DOMAIN_SUFFIXES:
        raise IssuerSecurityCheckpointError(
            "requested_domain must not use a local or non-public suffix"
        )
    return value


def _integer(value: Any, field: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise IssuerSecurityCheckpointError(f"{field} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise IssuerSecurityCheckpointError(f"{field} must be <= {maximum}")
    return value


def _utc(value: Any, field: str) -> datetime:
    try:
        return parse_aware(value, field).astimezone(timezone.utc)
    except ValueError as exc:
        raise IssuerSecurityCheckpointError(str(exc)) from exc


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IssuerSecurityCheckpointError("checkpoint timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _digest(value: Mapping[str, Any]) -> str:
    return hash_json({key: item for key, item in value.items() if key != "checkpoint_digest"})


def _fencing_token(checkpoint_id: str, generation: int, owner_run_id: str) -> str:
    return hash_json(
        {
            "checkpoint_id": checkpoint_id,
            "generation": generation,
            "owner_run_id": owner_run_id,
        }
    )


def _idempotency_key(checkpoint_id: str, security_code: str, source_ordinal: int, attempt: int) -> str:
    return hash_json(
        {
            "checkpoint_id": checkpoint_id,
            "security_code": security_code,
            "source_ordinal": source_ordinal,
            "worker_attempt": attempt,
        }
    )


def validate_issuer_security_checkpoint_policy(project_root: Path | str) -> dict[str, Any]:
    path = Path(project_root).resolve() / POLICY_PATH
    try:
        payload, content = load_strict_json_object(
            path, field="issuer security checkpoint policy", max_bytes=512 * 1024
        )
    except ValueError as exc:
        raise IssuerSecurityCheckpointError(str(exc)) from exc
    if payload != EXPECTED_POLICY:
        raise IssuerSecurityCheckpointError("issuer security checkpoint policy differs from contract")
    return {
        "schema_version": "1.0",
        "status": "PASS_SYNTHETIC_CHECKPOINT_V2_POLICY",
        "policy_id": payload["policy_id"],
        "policy_sha256": sha256_bytes(content),
        "production_authorized": False,
        "production_status": payload["production"]["status"],
        "second_security_allowed": False,
    }


def _safe_store_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    if absolute == Path(absolute.anchor):
        raise IssuerSecurityCheckpointError("checkpoint root cannot be a filesystem root")
    parent = require_real_directory(absolute.parent, field="checkpoint root parent")
    target = parent / absolute.name
    if target.exists() or target.is_symlink():
        return require_real_directory(target, field="checkpoint root")
    try:
        target.mkdir(mode=0o700)
    except OSError as exc:
        raise IssuerSecurityCheckpointError("cannot create checkpoint root") from exc
    return require_real_directory(target, field="checkpoint root")


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise IssuerSecurityCheckpointError("cannot open checkpoint lock safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise IssuerSecurityCheckpointError("checkpoint lock must be a regular file")
        if metadata.st_nlink != 1:
            raise IssuerSecurityCheckpointError("checkpoint lock must not be hard-linked")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    """Crash-safely publish one immutable revision without replacing a peer."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    content = canonical_json_bytes(dict(payload)) + b"\n"
    stage = path.parent / f".{path.name}.stage-{secrets.token_hex(16)}.tmp"
    descriptor: int | None = None
    stage_created = False
    published = False
    try:
        descriptor = os.open(stage, flags, 0o600)
        stage_created = True
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise IssuerSecurityCheckpointError("revision stage must be a regular file")
        if metadata.st_nlink != 1:
            raise IssuerSecurityCheckpointError("revision stage must not be hard-linked")
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("revision write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(stage, path, follow_symlinks=False)
        published = True
        _fsync_directory(path.parent)
        os.unlink(stage)
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        if stage_created and not published:
            try:
                os.unlink(stage)
                _fsync_directory(path.parent)
            except OSError:
                pass
        raise IssuerSecurityCheckpointCasError("checkpoint revision already exists") from exc
    except OSError as exc:
        raise IssuerSecurityCheckpointError("checkpoint revision publication failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _single_link_regular_file(path: Path, *, field: str, max_bytes: int) -> bytes:
    """Read a regular file while requiring one pathname before and after."""

    try:
        before = os.lstat(path)
    except OSError as exc:
        raise IssuerSecurityCheckpointError(f"{field} is missing or unreadable") from exc
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise IssuerSecurityCheckpointError(f"{field} must be a non-hard-linked regular file")
    try:
        content = safe_regular_file(path, field=field, max_bytes=max_bytes)
        after = os.lstat(path)
    except (OSError, ValueError) as exc:
        raise IssuerSecurityCheckpointError(str(exc)) from exc
    if (
        not stat.S_ISREG(after.st_mode)
        or after.st_nlink != 1
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise IssuerSecurityCheckpointError(f"{field} changed or became hard-linked while being read")
    return content


def _validate_evidence_binding(value: Any) -> dict[str, Any]:
    row = _exact(value, _EVIDENCE_KEYS, "evidence manifest binding")
    relative = safe_relative_path(row["manifest_path"], "manifest_path")
    if "\\" in str(row["manifest_path"]) or relative.name != "manifest.json":
        raise IssuerSecurityCheckpointError("manifest_path must be a portable manifest.json path")
    row["manifest_path"] = relative.as_posix()
    row["manifest_sha256"] = require_sha256(row["manifest_sha256"], "manifest_sha256")
    count = _integer(row["artifact_count"], "artifact_count", minimum=1)
    hashes = row["raw_sha256s"]
    if not isinstance(hashes, list) or len(hashes) != count or len(set(hashes)) != count:
        raise IssuerSecurityCheckpointError("raw_sha256s must match the unique artifact denominator")
    row["raw_sha256s"] = [require_sha256(item, "raw_sha256") for item in hashes]
    if row["raw_sha256s"] != sorted(row["raw_sha256s"]):
        raise IssuerSecurityCheckpointError("raw_sha256s must be sorted")
    return row


def _validate_reconciliation(value: Any, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    row = _exact(value, _RECON_KEYS, "security reconciliation")
    if row["schema_version"] != RECONCILIATION_VERSION:
        raise IssuerSecurityCheckpointError("reconciliation schema version is invalid")
    if (
        row["checkpoint_id"] != checkpoint["checkpoint_id"]
        or row["plan_sha256"] != checkpoint["plan_sha256"]
        or row["security_code"] != checkpoint["security"]["security_code"]
        or row["status"] != "PASS_29_TERMINAL_SOURCE_DENOMINATOR"
    ):
        raise IssuerSecurityCheckpointError("reconciliation identity or status differs")
    if (
        _integer(row["planned_source_count"], "planned_source_count") != 29
        or _integer(row["terminal_source_count"], "terminal_source_count") != 29
        or _integer(row["wave_count"], "wave_count") != 7
    ):
        raise IssuerSecurityCheckpointError("reconciliation denominator differs")
    receipt_hashes = row["source_receipt_sha256s"]
    if not isinstance(receipt_hashes, list) or len(receipt_hashes) != 29:
        raise IssuerSecurityCheckpointError("reconciliation requires 29 receipt hashes")
    row["source_receipt_sha256s"] = [require_sha256(item, "source receipt hash") for item in receipt_hashes]
    manifests = row["manifest_sha256s"]
    if not isinstance(manifests, list) or len(manifests) != len(set(manifests)):
        raise IssuerSecurityCheckpointError("reconciliation manifest hashes must be unique")
    row["manifest_sha256s"] = [require_sha256(item, "manifest hash") for item in manifests]
    expected_receipts = [
        slot["source_receipt"]["source_receipt_sha256"]
        for slot in checkpoint["source_slots"]
    ]
    expected_manifests = sorted(
        {
            slot["evidence_manifest"]["manifest_sha256"]
            for slot in checkpoint["source_slots"]
            if slot["evidence_manifest"] is not None
        }
    )
    if row["source_receipt_sha256s"] != expected_receipts or row["manifest_sha256s"] != expected_manifests:
        raise IssuerSecurityCheckpointError("reconciliation hashes differ from terminal source slots")
    _utc(row["reconciled_at"], "reconciled_at")
    submitted = require_sha256(row["reconciliation_sha256"], "reconciliation_sha256")
    if submitted != hash_json({key: item for key, item in row.items() if key != "reconciliation_sha256"}):
        raise IssuerSecurityCheckpointError("reconciliation digest mismatch")
    return row


def _validate_terminal_seal(value: Any, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    row = _exact(value, _SEAL_KEYS, "terminal seal")
    if (
        row["schema_version"] != TERMINAL_SEAL_VERSION
        or row["checkpoint_id"] != checkpoint["checkpoint_id"]
        or row["plan_sha256"] != checkpoint["plan_sha256"]
        or row["security_code"] != checkpoint["security"]["security_code"]
        or row["identity_sha256"] != checkpoint["security"]["identity_sha256"]
        or row["algorithm"] != "HMAC-SHA256"
        or row["production_authorized"] is not False
        or row["second_security_authorized"] is not False
        or row["previous_security_seal_sha256"] is not None
    ):
        raise IssuerSecurityCheckpointError("terminal seal identity or boundaries differ")
    for field in ("reconciliation_sha256", "preseal_checkpoint_digest", "seal_tag"):
        row[field] = require_sha256(row[field], field)
    _identifier(row["key_id"], "terminal seal key_id")
    sealed_at = _utc(row["sealed_at"], "sealed_at")
    if not isinstance(row["source_receipt_sha256s"], list) or len(row["source_receipt_sha256s"]) != 29:
        raise IssuerSecurityCheckpointError("terminal seal requires 29 receipt hashes")
    row["source_receipt_sha256s"] = [require_sha256(item, "source receipt hash") for item in row["source_receipt_sha256s"]]
    if not isinstance(row["manifest_sha256s"], list):
        raise IssuerSecurityCheckpointError("terminal seal manifest hashes must be an array")
    row["manifest_sha256s"] = [require_sha256(item, "manifest hash") for item in row["manifest_sha256s"]]
    reconciliation = checkpoint.get("reconciliation")
    if not isinstance(reconciliation, Mapping) or (
        row["reconciliation_sha256"] != reconciliation.get("reconciliation_sha256")
        or row["source_receipt_sha256s"] != reconciliation.get("source_receipt_sha256s")
        or row["manifest_sha256s"] != reconciliation.get("manifest_sha256s")
        or row["preseal_checkpoint_digest"] != checkpoint.get("prior_checkpoint_digest")
        or sealed_at != _utc(checkpoint.get("updated_at"), "checkpoint updated_at")
    ):
        raise IssuerSecurityCheckpointError("terminal seal differs from reconciliation or preseal revision")
    return row


def _validate_slot(value: Any, checkpoint_id: str, security_code: str) -> dict[str, Any]:
    row = _exact(value, _SLOT_KEYS, "source slot")
    ordinal = _integer(row["source_ordinal"], "source_ordinal", minimum=1, maximum=29)
    _integer(row["wave_ordinal"], "wave_ordinal", minimum=1, maximum=7)
    _identifier(row["wave_id"], "wave_id")
    _identifier(row["source_id"], "source_id")
    if row["status"] not in SLOT_STATUSES:
        raise IssuerSecurityCheckpointError("source slot status is invalid")
    attempts = _integer(row["attempt_count"], "attempt_count", maximum=2)
    expected_key = _idempotency_key(checkpoint_id, security_code, ordinal, attempts)
    if require_sha256(row["idempotency_key"], "idempotency_key") != expected_key:
        raise IssuerSecurityCheckpointError("source slot idempotency key is invalid")
    started = None if row["started_at"] is None else _utc(row["started_at"], "started_at")
    completed = None if row["completed_at"] is None else _utc(row["completed_at"], "completed_at")
    receipt = row["source_receipt"]
    evidence = row["evidence_manifest"]
    if row["status"] == "PENDING":
        if started is not None or completed is not None or receipt is not None or evidence is not None:
            raise IssuerSecurityCheckpointError("pending source slot has attempt or terminal fields")
    elif row["status"] == "IN_PROGRESS":
        if attempts < 1 or started is None or completed is not None or receipt is not None or evidence is not None:
            raise IssuerSecurityCheckpointError("in-progress source slot fields are inconsistent")
    else:
        if attempts < 1 or started is None or completed is None or completed < started or not isinstance(receipt, Mapping):
            raise IssuerSecurityCheckpointError("terminal source slot fields are inconsistent")
        receipt = _exact(receipt, _SOURCE_RECEIPT_FIELDS, "terminal source receipt")
        receipt_ordinal = _integer(
            receipt["source_ordinal"], "receipt source_ordinal", minimum=1, maximum=29
        )
        receipt_wave = _integer(
            receipt["wave_ordinal"], "receipt wave_ordinal", minimum=1, maximum=7
        )
        _identifier(receipt["wave_id"], "receipt wave_id")
        _identifier(receipt["source_id"], "receipt source_id")
        if (
            receipt_ordinal != ordinal
            or receipt_wave != row["wave_ordinal"]
            or receipt["wave_id"] != row["wave_id"]
            or receipt["source_id"] != row["source_id"]
            or receipt["security_code"] != security_code
        ):
            raise IssuerSecurityCheckpointError(
                "source receipt ordinal, wave, source, or security differs from its slot"
            )
        if receipt["terminal_status"] not in TERMINAL_SOURCE_STATUSES:
            raise IssuerSecurityCheckpointError("source receipt terminal status is invalid")
        attempted = _utc(receipt["attempted_at"], "receipt attempted_at")
        receipt_completed = _utc(receipt["completed_at"], "receipt completed_at")
        if started > attempted or attempted > receipt_completed or completed != receipt_completed:
            raise IssuerSecurityCheckpointError(
                "source receipt timestamps differ from the slot attempt window"
            )
        authority_bound = receipt["runtime_authority_bound"]
        if type(authority_bound) is not bool:
            raise IssuerSecurityCheckpointError(
                "source receipt runtime_authority_bound must be a boolean"
            )
        authority_fields = (
            "authority_registry_id",
            "authority_registry_sha256",
            "authority_authenticated_key_id",
        )
        if authority_bound:
            for field in ("authority_registry_id", "authority_authenticated_key_id"):
                value = receipt[field]
                if (
                    not isinstance(value, str)
                    or not value
                    or value != value.strip()
                    or len(value) > 255
                ):
                    raise IssuerSecurityCheckpointError(
                        f"source receipt {field} must be a bounded identifier"
                    )
            receipt["authority_registry_sha256"] = require_sha256(
                receipt["authority_registry_sha256"], "authority_registry_sha256"
            )
        elif any(receipt[field] is not None for field in authority_fields):
            raise IssuerSecurityCheckpointError(
                "unbound source receipt cannot assert runtime authority fields"
            )
        submitted = require_sha256(receipt["source_receipt_sha256"], "source_receipt_sha256")
        if submitted != hash_json({key: item for key, item in receipt.items() if key != "source_receipt_sha256"}):
            raise IssuerSecurityCheckpointError("source receipt digest mismatch")
        artifact_count = receipt["artifact_count"]
        if isinstance(artifact_count, bool) or not isinstance(artifact_count, int) or artifact_count < 0:
            raise IssuerSecurityCheckpointError("source receipt artifact count is invalid")
        if artifact_count:
            binding = _validate_evidence_binding(evidence)
            if binding["artifact_count"] != artifact_count or binding["manifest_sha256"] != receipt.get("artifact_manifest_sha256"):
                raise IssuerSecurityCheckpointError("source receipt and evidence manifest differ")
            row["evidence_manifest"] = binding
        elif evidence is not None:
            raise IssuerSecurityCheckpointError("artifact-free receipt cannot bind a manifest")
        row["source_receipt"] = receipt
    return row


def _validate_checkpoint(value: Any) -> dict[str, Any]:
    row = _exact(value, _ROOT_KEYS, "issuer security checkpoint")
    if row["schema_version"] != SCHEMA_VERSION or row["market"] != "BOURSA_KUWAIT":
        raise IssuerSecurityCheckpointError("checkpoint schema or market is invalid")
    if not isinstance(row["checkpoint_id"], str) or re.fullmatch(r"ISCP2-[A-F0-9]{24}", row["checkpoint_id"]) is None:
        raise IssuerSecurityCheckpointError("checkpoint_id is invalid")
    _identifier(row["run_id"], "run_id")
    if not isinstance(row["plan_id"], str) or not row["plan_id"]:
        raise IssuerSecurityCheckpointError("plan_id is invalid")
    for field in ("policy_sha256", "plan_sha256", "issuer_universe_sha256"):
        row[field] = require_sha256(row[field], field)
    if row["policy_id"] != EXPECTED_POLICY["policy_id"]:
        raise IssuerSecurityCheckpointError("checkpoint policy_id is invalid")
    security = _exact(row["security"], _SECURITY_KEYS, "checkpoint security")
    _integer(security["ordinal"], "security ordinal", minimum=1)
    if not isinstance(security["security_code"], str) or not security["security_code"].isdigit():
        raise IssuerSecurityCheckpointError("security_code must remain an exact numeric string")
    _identifier(security["issuer_id"], "issuer_id")
    _identifier(security["ticker"], "ticker")
    security["identity_sha256"] = require_sha256(security["identity_sha256"], "identity_sha256")
    security["source_plan_sha256"] = require_sha256(security["source_plan_sha256"], "source_plan_sha256")
    row["security"] = security
    if row["status"] not in CHECKPOINT_STATUSES:
        raise IssuerSecurityCheckpointError("checkpoint status is invalid")
    revision = _integer(row["revision"], "revision", minimum=1)
    generation = _integer(row["generation"], "generation", minimum=1)
    owner = _identifier(row["owner_run_id"], "owner_run_id")
    if require_sha256(row["fencing_token"], "fencing_token") != _fencing_token(row["checkpoint_id"], generation, owner):
        raise IssuerSecurityCheckpointError("checkpoint fencing token is invalid")
    created = _utc(row["created_at"], "created_at")
    updated = _utc(row["updated_at"], "updated_at")
    if updated < created:
        raise IssuerSecurityCheckpointError("checkpoint updated_at precedes created_at")
    if revision == 1 and row["prior_checkpoint_digest"] is not None:
        raise IssuerSecurityCheckpointError("initial checkpoint cannot have a prior digest")
    if revision > 1:
        row["prior_checkpoint_digest"] = require_sha256(row["prior_checkpoint_digest"], "prior_checkpoint_digest")
    slots = row["source_slots"]
    if not isinstance(slots, list) or len(slots) != 29:
        raise IssuerSecurityCheckpointError("checkpoint requires exactly 29 source slots")
    validated = [_validate_slot(slot, row["checkpoint_id"], security["security_code"]) for slot in slots]
    expected_sources = [source for wave in SOURCE_WAVE_SOURCES for source in wave]
    if [slot["source_id"] for slot in validated] != expected_sources:
        raise IssuerSecurityCheckpointError("checkpoint source denominator or ordering differs")
    if [slot["source_ordinal"] for slot in validated] != list(range(1, 30)):
        raise IssuerSecurityCheckpointError("checkpoint source ordinals are not contiguous")
    for slot in validated:
        wave_index = slot["wave_ordinal"] - 1
        if slot["wave_id"] != SOURCE_WAVE_IDS[wave_index] or slot["source_id"] not in SOURCE_WAVE_SOURCES[wave_index]:
            raise IssuerSecurityCheckpointError("checkpoint wave binding differs")
    active = sum(slot["status"] == "IN_PROGRESS" for slot in validated)
    if active > 1:
        raise IssuerSecurityCheckpointError("checkpoint permits at most one active source")
    terminal_prefix = 0
    for slot in validated:
        if slot["status"] == "TERMINAL":
            terminal_prefix += 1
        else:
            break
    if any(slot["status"] == "TERMINAL" for slot in validated[terminal_prefix:]):
        raise IssuerSecurityCheckpointError("terminal source slots must form a strict prefix")
    row["source_slots"] = validated
    if row["status"] == "PREEMPTED" and active:
        raise IssuerSecurityCheckpointError("preempted checkpoint cannot retain active work")
    if row["status"] in {"RECONCILED", "SEALED"} and terminal_prefix != 29:
        raise IssuerSecurityCheckpointError("reconciled/sealed checkpoint lacks 29 terminal sources")
    if row["reconciliation"] is not None:
        row["reconciliation"] = _validate_reconciliation(row["reconciliation"], row)
    if row["status"] in {"RECONCILED", "SEALED"} and row["reconciliation"] is None:
        raise IssuerSecurityCheckpointError("terminal checkpoint lacks reconciliation")
    if row["status"] == "SEALED":
        if row["terminal_seal"] is None:
            raise IssuerSecurityCheckpointError("sealed checkpoint lacks terminal seal")
        row["terminal_seal"] = _validate_terminal_seal(row["terminal_seal"], row)
    elif row["terminal_seal"] is not None:
        raise IssuerSecurityCheckpointError("non-sealed checkpoint cannot contain a terminal seal")
    if row["production_authorized"] is not False or row["claim_boundaries"] != CLAIM_BOUNDARIES:
        raise IssuerSecurityCheckpointError("checkpoint production or claim boundaries changed")
    submitted_digest = require_sha256(row["checkpoint_digest"], "checkpoint_digest")
    if submitted_digest != _digest(row):
        raise IssuerSecurityCheckpointError("checkpoint digest mismatch")
    return row


class IssuerSecurityCheckpointStore:
    """Append-only local checkpoint store for one validated synthetic security."""

    def __init__(
        self,
        root: Path | str,
        *,
        project_root: Path | str,
        plan: Mapping[str, Any],
        issuer_universe: Path | str | Mapping[str, Any],
        runtime_trust_registry: RuntimeTrustRegistry | None = None,
    ) -> None:
        self.root = _safe_store_root(Path(root))
        root_metadata = os.lstat(self.root)
        self._root_identity = (root_metadata.st_dev, root_metadata.st_ino)
        self.project_root = Path(project_root).resolve()
        self.issuer_universe = issuer_universe
        self.runtime_trust_registry = runtime_trust_registry
        self.policy_report = validate_issuer_security_checkpoint_policy(self.project_root)
        self.plan = _validate_compiled_plan(
            plan,
            issuer_universe=issuer_universe,
            project_root=self.project_root,
            runtime_trust_registry=runtime_trust_registry,
        )
        queue = self.plan["queue"]
        if self.plan["security_count"] != 1 or len(queue) != 1:
            raise IssuerSecurityCheckpointError("checkpoint v2 requires exactly one plan security")
        self.security_plan = queue[0]
        if len(self.security_plan["source_plan"]) != 29:
            raise IssuerSecurityCheckpointError("checkpoint v2 requires exactly 29 planned sources")
        self.catalog = SourceNetworkCatalog(self.project_root / "config")
        self.checkpoint_id = "ISCP2-" + hash_json(
            {
                "plan_sha256": self.plan["plan_sha256"],
                "security_code": self.security_plan["security_code"],
                "identity_sha256": self.security_plan["identity_sha256"],
            }
        )[:24].upper()

    def _lock_path(self) -> Path:
        return self.root / f"{self.checkpoint_id}.guard"

    def _revision_path(self, revision: int) -> Path:
        return self.root / f"{self.checkpoint_id}.revision-{revision:08d}.json"

    def _cleanup_orphan_stages_unlocked(self) -> None:
        changed = False
        for entry in self.root.iterdir():
            match = _STAGE_RE.fullmatch(entry.name)
            if match is None or not match.group(1).startswith(self.checkpoint_id + "."):
                continue
            try:
                stage_metadata = os.lstat(entry)
            except OSError as exc:
                raise IssuerSecurityCheckpointError(
                    "checkpoint revision stage changed during cleanup"
                ) from exc
            if not stat.S_ISREG(stage_metadata.st_mode) or stage_metadata.st_nlink not in {1, 2}:
                raise IssuerSecurityCheckpointError(
                    "checkpoint revision stage is not a safe orphan"
                )
            final_path = self.root / match.group(1)
            try:
                final_metadata = os.lstat(final_path)
            except FileNotFoundError:
                final_metadata = None
            except OSError as exc:
                raise IssuerSecurityCheckpointError(
                    "checkpoint revision target changed during cleanup"
                ) from exc
            if final_metadata is None:
                if stage_metadata.st_nlink != 1:
                    raise IssuerSecurityCheckpointError(
                        "unpublished checkpoint stage has unexpected hard links"
                    )
            else:
                if not stat.S_ISREG(final_metadata.st_mode):
                    raise IssuerSecurityCheckpointError(
                        "checkpoint revision target is not a regular file"
                    )
                same_file = (stage_metadata.st_dev, stage_metadata.st_ino) == (
                    final_metadata.st_dev,
                    final_metadata.st_ino,
                )
                if (same_file and stage_metadata.st_nlink != 2) or (
                    not same_file and stage_metadata.st_nlink != 1
                ):
                    raise IssuerSecurityCheckpointError(
                        "checkpoint revision stage link state is invalid"
                    )
            try:
                os.unlink(entry)
            except OSError as exc:
                raise IssuerSecurityCheckpointError(
                    "checkpoint revision stage cleanup failed"
                ) from exc
            changed = True
        if changed:
            _fsync_directory(self.root)

    def _assert_root_identity(self) -> None:
        try:
            metadata = os.lstat(self.root)
        except OSError as exc:
            raise IssuerSecurityCheckpointError("checkpoint root changed after store initialization") from exc
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != self._root_identity
        ):
            raise IssuerSecurityCheckpointError("checkpoint root identity changed after store initialization")

    @contextmanager
    def _checkpoint_lock(self) -> Iterator[None]:
        self._assert_root_identity()
        with _locked(self._lock_path()):
            self._assert_root_identity()
            try:
                yield
            finally:
                self._assert_root_identity()

    def _read_revisions_unlocked(self) -> list[dict[str, Any]]:
        self._assert_root_identity()
        self._cleanup_orphan_stages_unlocked()
        candidates: list[tuple[int, Path]] = []
        for entry in self.root.iterdir():
            match = _REVISION_RE.fullmatch(entry.name)
            if match is None or match.group(1) != self.checkpoint_id:
                continue
            if entry.is_symlink():
                raise IssuerSecurityCheckpointError("checkpoint revision must not be a symlink")
            candidates.append((int(match.group(2)), entry))
        candidates.sort()
        if not candidates:
            return []
        if [item[0] for item in candidates] != list(range(1, len(candidates) + 1)):
            raise IssuerSecurityCheckpointError("checkpoint revision chain has a gap")
        rows: list[dict[str, Any]] = []
        previous: dict[str, Any] | None = None
        for revision, path in candidates:
            try:
                content = _single_link_regular_file(
                    path, field="checkpoint revision", max_bytes=MAX_REVISION_BYTES
                )
                row = _validate_checkpoint(strict_json_object(content, "checkpoint revision"))
            except ValueError as exc:
                if isinstance(exc, IssuerSecurityCheckpointError):
                    raise
                raise IssuerSecurityCheckpointError(str(exc)) from exc
            if row["revision"] != revision or row["checkpoint_id"] != self.checkpoint_id:
                raise IssuerSecurityCheckpointError("checkpoint revision filename and content differ")
            self._bind_to_plan(row)
            if previous is not None:
                if row["prior_checkpoint_digest"] != previous["checkpoint_digest"]:
                    raise IssuerSecurityCheckpointError("checkpoint revision digest chain is broken")
                self._validate_transition(previous, row)
            rows.append(row)
            previous = row
        self._assert_root_identity()
        return rows

    def _bind_to_plan(self, row: Mapping[str, Any]) -> None:
        expected_security = {
            "ordinal": self.security_plan["ordinal"],
            "issuer_id": self.security_plan["issuer_id"],
            "security_code": self.security_plan["security_code"],
            "ticker": self.security_plan["ticker"],
            "identity_sha256": self.security_plan["identity_sha256"],
            "source_plan_sha256": hash_json(self.security_plan["source_plan"]),
        }
        if (
            row["policy_sha256"] != self.policy_report["policy_sha256"]
            or row["run_id"] != self.plan["run_id"]
            or row["plan_id"] != self.plan["plan_id"]
            or row["plan_sha256"] != self.plan["plan_sha256"]
            or row["issuer_universe_sha256"] != self.plan["issuer_universe_sha256"]
            or row["security"] != expected_security
        ):
            raise IssuerSecurityCheckpointError("checkpoint differs from the reopened plan/universe")
        for slot, source in zip(row["source_slots"], self.security_plan["source_plan"], strict=True):
            for field in ("source_ordinal", "wave_ordinal", "wave_id", "source_id"):
                if slot[field] != source[field]:
                    raise IssuerSecurityCheckpointError("checkpoint slot differs from the reopened source plan")
            if slot["status"] == "TERMINAL":
                receipt = slot["source_receipt"]
                raw_result = {
                    "terminal_status": receipt["terminal_status"],
                    "attempted_at": receipt["attempted_at"],
                    "completed_at": receipt["completed_at"],
                    "artifact_count": receipt["artifact_count"],
                    "observation_count": receipt["observation_count"],
                    "requested_domain": receipt["requested_domain"],
                    "activation_id": receipt["activation_id"],
                    "entitlement_id": receipt["entitlement_id"],
                    "artifact_manifest_sha256": receipt["artifact_manifest_sha256"],
                    "limitation": receipt["limitation"],
                }
                try:
                    reopened_receipt = _attempt_receipt(
                        self.security_plan,
                        source,
                        raw_result,
                        runtime_trust_registry=self.runtime_trust_registry,
                    )
                except IssuerSequentialCollectionError as exc:
                    raise IssuerSecurityCheckpointError(
                        f"source receipt plan/authority binding failed: {exc}"
                    ) from exc
                if reopened_receipt != receipt:
                    raise IssuerSecurityCheckpointError(
                        "source receipt differs from its reopened plan/authority binding"
                    )

    @staticmethod
    def _validate_transition(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        mutable_root = {
            "status",
            "revision",
            "generation",
            "fencing_token",
            "owner_run_id",
            "updated_at",
            "source_slots",
            "reconciliation",
            "terminal_seal",
            "prior_checkpoint_digest",
            "checkpoint_digest",
        }
        immutable_root = _ROOT_KEYS - mutable_root
        if any(previous[field] != current[field] for field in immutable_root):
            raise IssuerSecurityCheckpointError("checkpoint immutable identity changed")
        if (
            current["revision"] != previous["revision"] + 1
            or current["prior_checkpoint_digest"] != previous["checkpoint_digest"]
        ):
            raise IssuerSecurityCheckpointError("checkpoint revision is not contiguous")
        if _utc(current["updated_at"], "updated_at") < _utc(previous["updated_at"], "updated_at"):
            raise IssuerSecurityCheckpointError("checkpoint time moved backwards")
        transition = (previous["status"], current["status"])
        allowed = {
            ("RUNNING", "RUNNING"),
            ("RUNNING", "PREEMPTED"),
            ("PREEMPTED", "RUNNING"),
            ("RUNNING", "RECONCILED"),
            ("RECONCILED", "SEALED"),
        }
        if transition not in allowed:
            raise IssuerSecurityCheckpointError("checkpoint status transition is invalid")

        resume = transition == ("PREEMPTED", "RUNNING")
        if resume:
            if current["generation"] != previous["generation"] + 1:
                raise IssuerSecurityCheckpointError("resume must advance generation exactly once")
        elif (
            current["generation"] != previous["generation"]
            or current["owner_run_id"] != previous["owner_run_id"]
            or current["fencing_token"] != previous["fencing_token"]
        ):
            raise IssuerSecurityCheckpointError(
                "owner, fence, and generation may change only during resume"
            )

        slot_deltas = [
            (before, after)
            for before, after in zip(
                previous["source_slots"], current["source_slots"], strict=True
            )
            if before != after
        ]
        if transition == ("RUNNING", "RUNNING"):
            if (
                previous["reconciliation"] != current["reconciliation"]
                or previous["terminal_seal"] != current["terminal_seal"]
                or len(slot_deltas) != 1
            ):
                raise IssuerSecurityCheckpointError("running mutation must change exactly one source slot")
            before, after = slot_deltas[0]
            if before["status"] == "PENDING" and after["status"] == "IN_PROGRESS":
                expected = copy.deepcopy(before)
                expected.update(
                    {
                        "status": "IN_PROGRESS",
                        "attempt_count": before["attempt_count"] + 1,
                        "idempotency_key": _idempotency_key(
                            current["checkpoint_id"],
                            current["security"]["security_code"],
                            before["source_ordinal"],
                            before["attempt_count"] + 1,
                        ),
                        "started_at": current["updated_at"],
                    }
                )
                if after != expected:
                    raise IssuerSecurityCheckpointError("source start delta is invalid")
            elif before["status"] == "IN_PROGRESS" and after["status"] == "TERMINAL":
                unchanged = {
                    "source_ordinal",
                    "wave_ordinal",
                    "wave_id",
                    "source_id",
                    "attempt_count",
                    "idempotency_key",
                    "started_at",
                }
                if (
                    any(before[field] != after[field] for field in unchanged)
                    or _utc(after["completed_at"], "slot completed_at")
                    != _utc(after["source_receipt"]["completed_at"], "receipt completed_at")
                    or _utc(current["updated_at"], "checkpoint updated_at")
                    != _utc(after["completed_at"], "slot completed_at")
                ):
                    raise IssuerSecurityCheckpointError("source completion delta is invalid")
            else:
                raise IssuerSecurityCheckpointError("running source state transition is invalid")
        elif transition == ("RUNNING", "PREEMPTED"):
            if (
                previous["reconciliation"] != current["reconciliation"]
                or previous["terminal_seal"] != current["terminal_seal"]
                or len(slot_deltas) > 1
            ):
                raise IssuerSecurityCheckpointError("preemption delta is invalid")
            if slot_deltas:
                before, after = slot_deltas[0]
                expected = copy.deepcopy(before)
                expected.update({"status": "PENDING", "started_at": None})
                if before["status"] != "IN_PROGRESS" or after != expected:
                    raise IssuerSecurityCheckpointError("preemption source reset is invalid")
        elif resume:
            if (
                slot_deltas
                or previous["reconciliation"] != current["reconciliation"]
                or previous["terminal_seal"] != current["terminal_seal"]
            ):
                raise IssuerSecurityCheckpointError("resume may change only owner and fencing state")
        elif transition == ("RUNNING", "RECONCILED"):
            if (
                slot_deltas
                or previous["reconciliation"] is not None
                or current["reconciliation"] is None
                or previous["terminal_seal"] is not None
                or current["terminal_seal"] is not None
                or current["reconciliation"]["reconciled_at"] != current["updated_at"]
            ):
                raise IssuerSecurityCheckpointError("reconciliation transition delta is invalid")
        elif (
            slot_deltas
            or previous["reconciliation"] != current["reconciliation"]
            or previous["terminal_seal"] is not None
            or current["terminal_seal"] is None
        ):
            raise IssuerSecurityCheckpointError("terminal seal transition delta is invalid")

    def load(self) -> dict[str, Any] | None:
        with self._checkpoint_lock():
            rows = self._read_revisions_unlocked()
            return copy.deepcopy(rows[-1]) if rows else None

    def create(self, *, owner_run_id: str, now: datetime) -> dict[str, Any]:
        owner = _identifier(owner_run_id, "owner_run_id")
        current = _utc(now, "now")
        security = {
            "ordinal": self.security_plan["ordinal"],
            "issuer_id": self.security_plan["issuer_id"],
            "security_code": self.security_plan["security_code"],
            "ticker": self.security_plan["ticker"],
            "identity_sha256": self.security_plan["identity_sha256"],
            "source_plan_sha256": hash_json(self.security_plan["source_plan"]),
        }
        slots = []
        for source in self.security_plan["source_plan"]:
            slots.append(
                {
                    "source_ordinal": source["source_ordinal"],
                    "wave_ordinal": source["wave_ordinal"],
                    "wave_id": source["wave_id"],
                    "source_id": source["source_id"],
                    "status": "PENDING",
                    "attempt_count": 0,
                    "idempotency_key": _idempotency_key(
                        self.checkpoint_id,
                        security["security_code"],
                        source["source_ordinal"],
                        0,
                    ),
                    "started_at": None,
                    "completed_at": None,
                    "source_receipt": None,
                    "evidence_manifest": None,
                }
            )
        row = {
            "schema_version": SCHEMA_VERSION,
            "checkpoint_id": self.checkpoint_id,
            "policy_id": EXPECTED_POLICY["policy_id"],
            "policy_sha256": self.policy_report["policy_sha256"],
            "run_id": self.plan["run_id"],
            "plan_id": self.plan["plan_id"],
            "plan_sha256": self.plan["plan_sha256"],
            "issuer_universe_sha256": self.plan["issuer_universe_sha256"],
            "market": "BOURSA_KUWAIT",
            "security": security,
            "status": "RUNNING",
            "revision": 1,
            "generation": 1,
            "fencing_token": _fencing_token(self.checkpoint_id, 1, owner),
            "owner_run_id": owner,
            "created_at": _timestamp(current),
            "updated_at": _timestamp(current),
            "source_slots": slots,
            "reconciliation": None,
            "terminal_seal": None,
            "prior_checkpoint_digest": None,
            "checkpoint_digest": "",
            "production_authorized": False,
            "claim_boundaries": CLAIM_BOUNDARIES,
        }
        row["checkpoint_digest"] = _digest(row)
        validated = _validate_checkpoint(row)
        self._bind_to_plan(validated)
        with self._checkpoint_lock():
            if self._read_revisions_unlocked():
                raise IssuerSecurityCheckpointCasError("checkpoint already exists")
            self._assert_root_identity()
            _write_exclusive(self._revision_path(1), validated)
            self._assert_root_identity()
        return copy.deepcopy(validated)

    def _mutate(
        self,
        *,
        expected_revision: int,
        expected_generation: int,
        fencing_token: str,
        owner_run_id: str,
        prior_checkpoint_digest: str,
        mutate: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        expected_revision = _integer(expected_revision, "expected_revision", minimum=1)
        expected_generation = _integer(expected_generation, "expected_generation", minimum=1)
        owner = _identifier(owner_run_id, "owner_run_id")
        token = require_sha256(fencing_token, "fencing_token")
        prior = require_sha256(prior_checkpoint_digest, "prior_checkpoint_digest")
        with self._checkpoint_lock():
            rows = self._read_revisions_unlocked()
            if not rows:
                raise IssuerSecurityCheckpointCasError("checkpoint is missing")
            current = rows[-1]
            if current["revision"] != expected_revision or current["generation"] != expected_generation or current["checkpoint_digest"] != prior:
                raise IssuerSecurityCheckpointCasError("checkpoint revision/generation/digest CAS mismatch")
            if current["fencing_token"] != token or current["owner_run_id"] != owner:
                raise IssuerSecurityCheckpointFencingError("checkpoint owner or fencing token is stale")
            if current["status"] == "SEALED":
                raise IssuerSecurityCheckpointError("sealed checkpoint is immutable")
            next_row = copy.deepcopy(current)
            mutate(next_row)
            next_row["revision"] += 1
            next_row["prior_checkpoint_digest"] = current["checkpoint_digest"]
            next_row["checkpoint_digest"] = ""
            next_row["checkpoint_digest"] = _digest(next_row)
            validated = _validate_checkpoint(next_row)
            self._bind_to_plan(validated)
            self._validate_transition(current, validated)
            self._assert_root_identity()
            _write_exclusive(self._revision_path(validated["revision"]), validated)
            self._assert_root_identity()
            return copy.deepcopy(validated)

    @staticmethod
    def _advance(row: dict[str, Any], now: datetime) -> None:
        current = _utc(now, "now")
        if current < _utc(row["updated_at"], "updated_at"):
            raise IssuerSecurityCheckpointError("checkpoint time cannot move backwards")
        row["updated_at"] = _timestamp(current)

    def start_next_source(self, *, now: datetime, **cas: Any) -> dict[str, Any]:
        def mutate(row: dict[str, Any]) -> None:
            if row["status"] != "RUNNING":
                raise IssuerSecurityCheckpointError("only a running checkpoint may start work")
            if any(slot["status"] == "IN_PROGRESS" for slot in row["source_slots"]):
                raise IssuerSecurityCheckpointError("one source is already in progress")
            target = next((slot for slot in row["source_slots"] if slot["status"] == "PENDING"), None)
            if target is None:
                raise IssuerSecurityCheckpointError("all source slots are already terminal")
            if target["attempt_count"] >= 2:
                raise IssuerSecurityCheckpointError("source worker attempt budget is exhausted")
            self._advance(row, now)
            target["attempt_count"] += 1
            target["idempotency_key"] = _idempotency_key(
                row["checkpoint_id"], row["security"]["security_code"], target["source_ordinal"], target["attempt_count"]
            )
            target["status"] = "IN_PROGRESS"
            target["started_at"] = row["updated_at"]

        return self._mutate(mutate=mutate, **cas)

    def _reopen_manifest(
        self,
        *,
        evidence_root: Path | str,
        manifest_path: str,
        source_id: str,
        requested_domain: str | None,
        attempted_at: datetime,
        completed_at: datetime,
    ) -> dict[str, Any]:
        root = require_real_directory(Path(os.path.abspath(evidence_root)), field="evidence root")
        try:
            relative = safe_relative_path(manifest_path, "manifest_path")
        except ValueError as exc:
            raise IssuerSecurityCheckpointError(
                "manifest path must be portable and remain inside the evidence root"
            ) from exc
        if "\\" in manifest_path or relative.name != "manifest.json":
            raise IssuerSecurityCheckpointError("manifest path must be portable and end in manifest.json")
        manifest_file = root / relative
        try:
            packet = snapshot_regular_tree(
                manifest_file.parent,
                field="source evidence packet",
                max_files=4096,
                max_entries=8192,
                max_depth=64,
                max_file_bytes=MAX_RAW_BYTES,
                max_total_bytes=MAX_RAW_BYTES,
            ).by_path()
            manifest_snapshot = packet.get("manifest.json")
            if manifest_snapshot is None:
                raise IssuerSecurityCheckpointError("source evidence packet lacks manifest.json")
            content = manifest_snapshot.content
            if len(content) > MAX_MANIFEST_BYTES:
                raise IssuerSecurityCheckpointError(
                    f"source manifest exceeds {MAX_MANIFEST_BYTES} bytes"
                )
            payload = strict_json_object(content, "source manifest")
        except ValueError as exc:
            if isinstance(exc, IssuerSecurityCheckpointError):
                raise
            raise IssuerSecurityCheckpointError(str(exc)) from exc
        if frozenset(payload) != {"schema_version", "artifacts"} or payload["schema_version"] != "3.0":
            raise IssuerSecurityCheckpointError("source manifest must use the exact v3 artifact contract")
        artifacts = payload["artifacts"]
        if not isinstance(artifacts, list) or not artifacts:
            raise IssuerSecurityCheckpointError("source manifest artifacts must be non-empty")
        source = self.catalog.sources.get(source_id)
        if source is None:
            raise IssuerSecurityCheckpointError("manifest source is not in the reopened catalog")
        hashes: list[str] = []
        paths: set[str] = set()
        for index, raw in enumerate(artifacts):
            row = _exact(
                raw,
                frozenset({"path", "sha256", "size_bytes", "source_id", "source_url", "observed_at", "capture_kind"}),
                f"manifest artifact[{index}]",
            )
            try:
                artifact_relative = safe_relative_path(row["path"], "artifact path")
            except ValueError as exc:
                raise IssuerSecurityCheckpointError(
                    "manifest artifact path must be portable and remain inside raw/"
                ) from exc
            if "\\" in str(row["path"]) or not artifact_relative.parts or artifact_relative.parts[0] != "raw":
                raise IssuerSecurityCheckpointError("manifest artifact must remain inside raw/")
            path_text = artifact_relative.as_posix()
            if path_text in paths:
                raise IssuerSecurityCheckpointError("manifest artifact paths must be unique")
            paths.add(path_text)
            if row["source_id"] != source_id:
                raise IssuerSecurityCheckpointError("manifest artifact source differs from checkpoint slot")
            source_url = https_url(row["source_url"], "source_url")
            host = (urlsplit(source_url).hostname or "").casefold().rstrip(".")
            if source.domains and not any(host == domain or host.endswith("." + domain) for domain in source.domains):
                raise IssuerSecurityCheckpointError("manifest artifact URL is outside the registered source")
            if not source.domains:
                checked_requested_domain = _requested_domain(requested_domain)
                if host != checked_requested_domain and not host.endswith(
                    "." + checked_requested_domain
                ):
                    raise IssuerSecurityCheckpointError(
                        "manifest artifact host differs from receipt requested_domain"
                    )
            observed = _utc(row["observed_at"], "observed_at")
            if observed < attempted_at or observed > completed_at:
                raise IssuerSecurityCheckpointError(
                    "manifest artifact observed_at is outside the source attempt window"
                )
            if row["capture_kind"] not in {"RAW_PAGE", "RAW_DOWNLOAD", "USER_EXPORT", "ACCESS_RECEIPT", "ARCHIVE_CAPTURE"}:
                raise IssuerSecurityCheckpointError("manifest artifact capture_kind is invalid")
            digest = require_sha256(row["sha256"], "artifact sha256")
            size = _integer(row["size_bytes"], "artifact size_bytes")
            raw_snapshot = packet.get(path_text)
            if raw_snapshot is None:
                raise IssuerSecurityCheckpointError("manifest raw source artifact is missing")
            raw_bytes = raw_snapshot.content
            if len(raw_bytes) != size or sha256_bytes(raw_bytes) != digest:
                raise IssuerSecurityCheckpointError("raw source artifact size or digest mismatch")
            hashes.append(digest)
        if len(set(hashes)) != len(hashes):
            raise IssuerSecurityCheckpointError("manifest raw artifact hashes must be unique")
        expected_packet_paths = {"manifest.json", *paths}
        if set(packet) != expected_packet_paths:
            raise IssuerSecurityCheckpointError(
                "source evidence packet contains unmanifested files"
            )
        return {
            "manifest_path": relative.as_posix(),
            "manifest_sha256": sha256_bytes(content),
            "artifact_count": len(artifacts),
            "raw_sha256s": sorted(hashes),
        }

    def complete_active_source(
        self,
        *,
        raw_result: Mapping[str, Any],
        evidence_root: Path | str,
        manifest_path: str | None,
        **cas: Any,
    ) -> dict[str, Any]:
        active_snapshot = self.load()
        if active_snapshot is None:
            raise IssuerSecurityCheckpointCasError("checkpoint is missing")
        active_slots = [slot for slot in active_snapshot["source_slots"] if slot["status"] == "IN_PROGRESS"]
        if len(active_slots) != 1:
            raise IssuerSecurityCheckpointError("checkpoint must have one active source")
        active = active_slots[0]
        source = self.security_plan["source_plan"][active["source_ordinal"] - 1]
        receipt = _attempt_receipt(
            self.security_plan,
            source,
            raw_result,
            runtime_trust_registry=self.runtime_trust_registry,
        )
        completed = _utc(receipt["completed_at"], "source receipt completed_at")
        attempted = _utc(receipt["attempted_at"], "source receipt attempted_at")
        binding = None
        if receipt["artifact_count"]:
            if manifest_path is None:
                raise IssuerSecurityCheckpointError("retained artifacts require a manifest path")
            binding = self._reopen_manifest(
                evidence_root=evidence_root,
                manifest_path=manifest_path,
                source_id=source["source_id"],
                requested_domain=receipt["requested_domain"],
                attempted_at=attempted,
                completed_at=completed,
            )
            if (
                binding["manifest_sha256"] != receipt["artifact_manifest_sha256"]
                or binding["artifact_count"] != receipt["artifact_count"]
            ):
                raise IssuerSecurityCheckpointError("reopened manifest differs from the source receipt")
        elif manifest_path is not None:
            raise IssuerSecurityCheckpointError("artifact-free source receipt cannot name a manifest")

        def mutate(row: dict[str, Any]) -> None:
            slots = [slot for slot in row["source_slots"] if slot["status"] == "IN_PROGRESS"]
            if len(slots) != 1 or slots[0]["source_ordinal"] != active["source_ordinal"]:
                raise IssuerSecurityCheckpointError("active source changed before completion")
            slot = slots[0]
            started = _utc(slot["started_at"], "slot started_at")
            if attempted < started or completed < attempted:
                raise IssuerSecurityCheckpointError("source receipt time precedes the checkpoint attempt")
            self._advance(row, completed)
            slot["status"] = "TERMINAL"
            slot["completed_at"] = _timestamp(completed)
            slot["source_receipt"] = copy.deepcopy(receipt)
            slot["evidence_manifest"] = copy.deepcopy(binding)

        return self._mutate(mutate=mutate, **cas)

    def preempt(self, *, now: datetime, **cas: Any) -> dict[str, Any]:
        def mutate(row: dict[str, Any]) -> None:
            if row["status"] != "RUNNING":
                raise IssuerSecurityCheckpointError("only a running checkpoint may be preempted")
            self._advance(row, now)
            for slot in row["source_slots"]:
                if slot["status"] == "IN_PROGRESS":
                    slot["status"] = "PENDING"
                    slot["started_at"] = None
            row["status"] = "PREEMPTED"

        return self._mutate(mutate=mutate, **cas)

    def resume(
        self,
        *,
        new_owner_run_id: str,
        now: datetime,
        **cas: Any,
    ) -> dict[str, Any]:
        new_owner = _identifier(new_owner_run_id, "new_owner_run_id")

        def mutate(row: dict[str, Any]) -> None:
            if row["status"] != "PREEMPTED":
                raise IssuerSecurityCheckpointError("only a preempted checkpoint may resume")
            self._advance(row, now)
            row["generation"] += 1
            row["owner_run_id"] = new_owner
            row["fencing_token"] = _fencing_token(row["checkpoint_id"], row["generation"], new_owner)
            row["status"] = "RUNNING"

        return self._mutate(mutate=mutate, **cas)

    def _reopen_all_evidence(self, row: Mapping[str, Any], evidence_root: Path | str) -> None:
        for slot in row["source_slots"]:
            receipt = slot["source_receipt"]
            binding = slot["evidence_manifest"]
            if receipt["artifact_count"]:
                reopened = self._reopen_manifest(
                    evidence_root=evidence_root,
                    manifest_path=binding["manifest_path"],
                    source_id=slot["source_id"],
                    requested_domain=receipt["requested_domain"],
                    attempted_at=_utc(receipt["attempted_at"], "source attempted_at"),
                    completed_at=_utc(receipt["completed_at"], "source completed_at"),
                )
                if reopened != binding:
                    raise IssuerSecurityCheckpointError("persisted evidence binding changed on reopen")

    def reconcile(self, *, evidence_root: Path | str, now: datetime, **cas: Any) -> dict[str, Any]:
        snapshot = self.load()
        if snapshot is None or any(slot["status"] != "TERMINAL" for slot in snapshot["source_slots"]):
            raise IssuerSecurityCheckpointError("reconciliation requires all 29 terminal source receipts")
        self._reopen_all_evidence(snapshot, evidence_root)

        def mutate(row: dict[str, Any]) -> None:
            if row["status"] != "RUNNING" or any(slot["status"] != "TERMINAL" for slot in row["source_slots"]):
                raise IssuerSecurityCheckpointError("reconciliation requires a running 29-terminal checkpoint")
            self._advance(row, now)
            receipt_hashes = [slot["source_receipt"]["source_receipt_sha256"] for slot in row["source_slots"]]
            manifests = sorted(
                {
                    slot["evidence_manifest"]["manifest_sha256"]
                    for slot in row["source_slots"]
                    if slot["evidence_manifest"] is not None
                }
            )
            reconciliation = {
                "schema_version": RECONCILIATION_VERSION,
                "checkpoint_id": row["checkpoint_id"],
                "plan_sha256": row["plan_sha256"],
                "security_code": row["security"]["security_code"],
                "planned_source_count": 29,
                "terminal_source_count": 29,
                "wave_count": 7,
                "source_receipt_sha256s": receipt_hashes,
                "manifest_sha256s": manifests,
                "status": "PASS_29_TERMINAL_SOURCE_DENOMINATOR",
                "reconciled_at": row["updated_at"],
                "reconciliation_sha256": "",
            }
            reconciliation["reconciliation_sha256"] = hash_json(
                {key: item for key, item in reconciliation.items() if key != "reconciliation_sha256"}
            )
            row["reconciliation"] = reconciliation
            row["status"] = "RECONCILED"

        return self._mutate(mutate=mutate, **cas)

    def seal(
        self,
        *,
        evidence_root: Path | str,
        seal_key: bytes,
        seal_key_id: str,
        now: datetime,
        **cas: Any,
    ) -> dict[str, Any]:
        if not isinstance(seal_key, bytes) or len(seal_key) < 32:
            raise IssuerSecurityCheckpointError("terminal seal key must contain at least 32 runtime bytes")
        key_id = _identifier(seal_key_id, "seal_key_id")
        snapshot = self.load()
        if snapshot is None or snapshot["status"] != "RECONCILED":
            raise IssuerSecurityCheckpointError("terminal seal requires a reconciled checkpoint")
        self._reopen_all_evidence(snapshot, evidence_root)

        def mutate(row: dict[str, Any]) -> None:
            if row["status"] != "RECONCILED" or row["reconciliation"] is None:
                raise IssuerSecurityCheckpointError("terminal seal requires reconciliation")
            self._advance(row, now)
            material = {
                "schema_version": TERMINAL_SEAL_VERSION,
                "checkpoint_id": row["checkpoint_id"],
                "plan_sha256": row["plan_sha256"],
                "security_code": row["security"]["security_code"],
                "identity_sha256": row["security"]["identity_sha256"],
                "reconciliation_sha256": row["reconciliation"]["reconciliation_sha256"],
                "preseal_checkpoint_digest": row["checkpoint_digest"],
                "source_receipt_sha256s": row["reconciliation"]["source_receipt_sha256s"],
                "manifest_sha256s": row["reconciliation"]["manifest_sha256s"],
                "previous_security_seal_sha256": None,
                "algorithm": "HMAC-SHA256",
                "key_id": key_id,
                "sealed_at": row["updated_at"],
                "production_authorized": False,
                "second_security_authorized": False,
                "seal_tag": "",
            }
            material["seal_tag"] = hmac.new(
                seal_key,
                canonical_json_bytes({key: item for key, item in material.items() if key != "seal_tag"}),
                hashlib.sha256,
            ).hexdigest()
            row["terminal_seal"] = material
            row["status"] = "SEALED"

        return self._mutate(mutate=mutate, **cas)

    def verify_bundle(
        self,
        *,
        evidence_root: Path | str,
        seal_key: bytes,
        expected_seal_key_id: str,
    ) -> dict[str, Any]:
        if not isinstance(seal_key, bytes) or len(seal_key) < 32:
            raise IssuerSecurityCheckpointError("terminal seal key must contain at least 32 runtime bytes")
        key_id = _identifier(expected_seal_key_id, "expected_seal_key_id")
        with self._checkpoint_lock():
            rows = self._read_revisions_unlocked()
        if not rows or rows[-1]["status"] != "SEALED":
            raise IssuerSecurityCheckpointError("checkpoint bundle is not terminally sealed")
        row = rows[-1]
        self._reopen_all_evidence(row, evidence_root)
        recon = _validate_reconciliation(row["reconciliation"], row)
        seal = _validate_terminal_seal(row["terminal_seal"], row)
        if seal["key_id"] != key_id or seal["reconciliation_sha256"] != recon["reconciliation_sha256"]:
            raise IssuerSecurityCheckpointError("terminal seal key or reconciliation binding differs")
        expected_tag = hmac.new(
            seal_key,
            canonical_json_bytes({key: item for key, item in seal.items() if key != "seal_tag"}),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_tag, seal["seal_tag"]):
            raise IssuerSecurityCheckpointError("terminal seal HMAC mismatch")
        return {
            "schema_version": "1.0",
            "status": "PASS_SYNTHETIC_ONE_SECURITY_CHECKPOINT_BUNDLE",
            "checkpoint_id": row["checkpoint_id"],
            "security_code": row["security"]["security_code"],
            "revision_count": len(rows),
            "terminal_source_count": 29,
            "terminal_seal_tag": seal["seal_tag"],
            "production_authorized": False,
            "second_security_authorized": False,
        }


def checkpoint_cas(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact CAS arguments required by the next mutation."""

    row = _validate_checkpoint(checkpoint)
    return {
        "expected_revision": row["revision"],
        "expected_generation": row["generation"],
        "fencing_token": row["fencing_token"],
        "owner_run_id": row["owner_run_id"],
        "prior_checkpoint_digest": row["checkpoint_digest"],
    }


__all__ = [
    "IssuerSecurityCheckpointCasError",
    "IssuerSecurityCheckpointError",
    "IssuerSecurityCheckpointFencingError",
    "IssuerSecurityCheckpointStore",
    "POLICY_PATH",
    "checkpoint_cas",
    "validate_issuer_security_checkpoint_policy",
]
