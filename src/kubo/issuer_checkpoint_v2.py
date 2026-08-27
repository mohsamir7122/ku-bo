"""Immutable one-security checkpoint, reconciliation, and terminal sealing.

This module is deliberately separate from :mod:`kubo.priority_runtime` and
``issuer_sequential_collection``.  The older serialized contracts remain
unchanged; v2 reopens their authorities and persists generated, synthetic test
bundles as an append-only journal.  A production durable-store adapter is not
provided here.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from types import MappingProxyType
from typing import Any, Iterator, Mapping

from .foundation_io import (
    prepare_output_root,
    require_real_directory,
    safe_regular_file,
    strict_json_object,
)
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .issuer_sequential_collection import (
    SOURCE_WAVE_IDS,
    SOURCE_WAVE_SOURCES,
    TERMINAL_SOURCE_STATUSES,
    IssuerSequentialCollectionError,
    validate_issuer_sequential_collection_plan,
)
from .strict import parse_aware, require_sha256


CHECKPOINT_SCHEMA_VERSION = "issuer-checkpoint-v2"
JOURNAL_SCHEMA_VERSION = "issuer-checkpoint-journal-entry-v2"
MANIFEST_SCHEMA_VERSION = "issuer-checkpoint-source-manifest-v2"
RECEIPT_SCHEMA_VERSION = "issuer-checkpoint-source-receipt-v2"
RECONCILIATION_SCHEMA_VERSION = "issuer-checkpoint-reconciliation-v2"
SEAL_SCHEMA_VERSION = "issuer-checkpoint-terminal-seal-v2"
SEAL_AUDIENCE = "kubo-one-security-checkpoint-v2"
SEAL_ALGORITHM = "HMAC-SHA256"
EXPECTED_SOURCE_COUNT = 29
EXPECTED_WAVE_COUNT = 7
ZERO_DIGEST = "0" * 64

CLAIM_BOUNDARIES = MappingProxyType({
    "generated_fixture_is_real_market_evidence": False,
    "checkpoint_structure_proves_production_durability": False,
    "terminal_receipts_prove_live_source_access": False,
    "terminal_receipts_prove_source_rights": False,
    "terminal_seal_proves_market_completeness": False,
    "sealed_fixture_unlocks_training_or_backtest": False,
    "sealed_fixture_proves_forecast_or_recommendation_quality": False,
    "sealed_fixture_authorizes_financial_execution": False,
})

MAX_RAW_FILES_PER_SOURCE = 128
MAX_RAW_FILE_BYTES = 16 * 1024 * 1024
MAX_RAW_BYTES_PER_SOURCE = 64 * 1024 * 1024
MAX_CHECKPOINT_RAW_FILES = 256
MAX_CHECKPOINT_RAW_BYTES = 128 * 1024 * 1024
MAX_CHECKPOINT_FILES = 512
MAX_CHECKPOINT_BYTES = 256 * 1024 * 1024

_SECURITY_CODE_RE = re.compile(r"^[0-9]{1,12}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,127}$")
_SAFE_RELATIVE_PATH_RE = re.compile(
    r"^(?!\.{1,2}(?:/|$))(?!.*(?:/\.{1,2})(?:/|$))"
    r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
)
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_NON_BLOCKING_TERMINAL_STATUSES = frozenset(
    {"COLLECTED", "VERIFIED_ZERO", "REVIEWED_NOT_APPLICABLE"}
)

_STATE_FIELDS = frozenset(
    {
        "schema_version",
        "checkpoint_id",
        "run_id",
        "market",
        "issuer_id",
        "security_code",
        "selected_queue_ordinal",
        "plan_id",
        "plan_sha256",
        "plan_content_sha256",
        "issuer_universe_sha256",
        "universe_content_sha256",
        "identity_sha256",
        "source_plan_sha256",
        "previous_security_terminal_seal_sha256",
        "expected_source_count",
        "expected_wave_count",
        "status",
        "event_type",
        "generation",
        "revision",
        "owner_run_id",
        "fencing_token",
        "prior_checkpoint_digest",
        "next_source_ordinal",
        "active_source_ordinal",
        "terminal_receipt_count",
        "terminal_receipt_sha256s",
        "reconciliation_sha256",
        "terminal_seal_sha256",
        "created_at",
        "updated_at",
        "claim_boundaries",
        "checkpoint_digest",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "checkpoint_id",
        "security_code",
        "source_ordinal",
        "wave_ordinal",
        "wave_id",
        "source_id",
        "artifacts",
        "manifest_sha256",
    }
)
_ARTIFACT_FIELDS = frozenset({"path", "sha256", "size_bytes"})
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "checkpoint_id",
        "run_id",
        "plan_sha256",
        "identity_sha256",
        "issuer_id",
        "security_code",
        "source_ordinal",
        "wave_ordinal",
        "wave_id",
        "source_id",
        "terminal_status",
        "attempted_at",
        "completed_at",
        "artifact_count",
        "observation_count",
        "artifact_manifest_path",
        "artifact_manifest_sha256",
        "raw_size_bytes",
        "limitation",
        "previous_terminal_receipt_sha256",
        "receipt_sha256",
    }
)
_RECONCILIATION_FIELDS = frozenset(
    {
        "schema_version",
        "checkpoint_id",
        "run_id",
        "issuer_id",
        "security_code",
        "plan_sha256",
        "issuer_universe_sha256",
        "identity_sha256",
        "source_plan_sha256",
        "reconciled_at",
        "evidence_class",
        "status",
        "expected_source_count",
        "terminal_source_count",
        "expected_wave_count",
        "reconciled_wave_count",
        "receipt_inventory",
        "wave_reconciliation",
        "terminal_status_counts",
        "retained_manifest_count",
        "reopened_manifest_count",
        "raw_artifact_count",
        "reopened_raw_artifact_count",
        "raw_size_bytes",
        "reconciled_checkpoint_digest",
        "claim_boundaries",
        "reconciliation_sha256",
    }
)
_RECONCILIATION_RECEIPT_FIELDS = frozenset(
    {
        "source_ordinal",
        "wave_ordinal",
        "wave_id",
        "source_id",
        "terminal_status",
        "receipt_sha256",
        "manifest_sha256",
    }
)
_WAVE_RECONCILIATION_FIELDS = frozenset(
    {
        "wave_ordinal",
        "wave_id",
        "expected_source_ordinals",
        "terminal_source_ordinals",
        "status",
    }
)
_SEAL_FIELDS = frozenset(
    {
        "schema_version",
        "audience",
        "seal_id",
        "key_issuer_id",
        "issued_at",
        "checkpoint_id",
        "run_id",
        "market",
        "issuer_id",
        "security_code",
        "identity_sha256",
        "plan_sha256",
        "issuer_universe_sha256",
        "source_plan_sha256",
        "generation",
        "revision",
        "owner_run_id",
        "fencing_token",
        "terminal_checkpoint_digest",
        "reconciliation_sha256",
        "terminal_receipt_count",
        "wave_count",
        "bundle_inventory",
        "bundle_root_sha256",
        "previous_security_terminal_seal_sha256",
        "claim_boundaries",
        "authentication",
    }
)
_AUTH_FIELDS = frozenset({"algorithm", "key_id", "tag"})
_INVENTORY_FIELDS = frozenset({"path", "sha256", "size_bytes"})


class IssuerCheckpointV2Error(ValueError):
    """Raised when an immutable issuer checkpoint fails closed."""


class IssuerCheckpointV2CasError(IssuerCheckpointV2Error):
    """Raised when generation/revision/owner/digest CAS does not match."""


class IssuerCheckpointV2FencingError(IssuerCheckpointV2Error):
    """Raised when a stale writer supplies a superseded fencing token."""


def _claim_boundaries() -> dict[str, bool]:
    """Return a fresh mutable JSON object from an immutable module authority."""

    return dict(CLAIM_BOUNDARIES)


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise IssuerCheckpointV2Error(
            f"{label} fields differ: missing={sorted(fields - actual)} "
            f"extra={sorted(actual - fields)}"
        )
    return dict(value)


def _identifier(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _IDENTIFIER_RE.fullmatch(value) is None
    ):
        raise IssuerCheckpointV2Error(f"{label} must be a canonical identifier")
    return value


def _security_code(value: Any) -> str:
    if not isinstance(value, str) or _SECURITY_CODE_RE.fullmatch(value) is None:
        raise IssuerCheckpointV2Error(
            "execution selection must contain exactly one numeric security_code"
        )
    return value


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise IssuerCheckpointV2Error(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise IssuerCheckpointV2Error(f"{label} must be a non-negative integer")
    return value


def _instant(value: Any, label: str) -> datetime:
    try:
        return parse_aware(value, label)
    except ValueError as exc:
        raise IssuerCheckpointV2Error(str(exc)) from exc


def _timestamp(value: Any, label: str) -> str:
    return _instant(value, label).isoformat()


def _relative_path(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or _SAFE_RELATIVE_PATH_RE.fullmatch(value) is None
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise IssuerCheckpointV2Error(
            f"{label} must be a canonical relative POSIX path"
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise IssuerCheckpointV2Error(f"{label} must remain inside the checkpoint")
    for component in path.parts:
        if (
            component != component.strip()
            or component.endswith((".", " "))
            or component.split(".", 1)[0].upper() in _WINDOWS_RESERVED
        ):
            raise IssuerCheckpointV2Error(
                f"{label} must be a canonical relative POSIX path"
            )
    return value


def _document_bytes(value: Path | str | Mapping[str, Any], label: str) -> tuple[dict[str, Any], bytes]:
    if isinstance(value, Mapping):
        payload = dict(value)
        return payload, canonical_json_bytes(payload)
    path = Path(value)
    try:
        content = safe_regular_file(path, field=label)
        payload = strict_json_object(content, label)
    except ValueError as exc:
        raise IssuerCheckpointV2Error(str(exc)) from exc
    return payload, content


def _root_identity(path: Path) -> tuple[int, int, int]:
    metadata = os.lstat(path)
    return metadata.st_dev, metadata.st_ino, metadata.st_mode


def _fencing_token(
    checkpoint_id: str, security_code: str, generation: int, owner_run_id: str
) -> str:
    return hash_json(
        {
            "checkpoint_id": checkpoint_id,
            "security_code": security_code,
            "generation": generation,
            "owner_run_id": owner_run_id,
        }
    )


def _state_digest(value: Mapping[str, Any]) -> str:
    return hash_json(
        {key: item for key, item in value.items() if key != "checkpoint_digest"}
    )


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return hash_json(
        {key: item for key, item in value.items() if key != "manifest_sha256"}
    )


def _receipt_digest(value: Mapping[str, Any]) -> str:
    return hash_json(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


def _reconciliation_digest(value: Mapping[str, Any]) -> str:
    return hash_json(
        {key: item for key, item in value.items() if key != "reconciliation_sha256"}
    )


def _canonical_authentication_bytes(payload: Mapping[str, Any]) -> bytes:
    authentication = payload.get("authentication")
    if not isinstance(authentication, Mapping):
        raise IssuerCheckpointV2Error("terminal seal authentication must be an object")
    return canonical_json_bytes(
        {
            "document": {
                key: value for key, value in payload.items() if key != "authentication"
            },
            "algorithm": authentication.get("algorithm"),
            "key_id": authentication.get("key_id"),
        }
    )


def _hmac_key(value: Any) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise IssuerCheckpointV2Error(
            "terminal seal HMAC key must contain at least 32 injected bytes"
        )
    return value


def _write_exclusive(path: Path, content: bytes, *, label: str) -> None:
    if not isinstance(content, bytes):
        raise IssuerCheckpointV2Error(f"{label} content must be bytes")
    try:
        parent = require_real_directory(path.parent, field=f"{label} parent")
    except ValueError as exc:
        raise IssuerCheckpointV2Error(str(exc)) from exc
    target = parent / path.name
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(target, flags, 0o600)
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("write made no progress")
            offset += written
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise IssuerCheckpointV2Error(
                f"{label} must be a private non-hard-linked regular file"
            )
    except FileExistsError as exc:
        raise IssuerCheckpointV2Error(f"refusing to overwrite existing {label}") from exc
    except OSError as exc:
        raise IssuerCheckpointV2Error(f"failed to create {label} exclusively") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_descriptor: int | None = None
    try:
        directory_descriptor = os.open(parent, directory_flags)
        os.fsync(directory_descriptor)
    except OSError as exc:
        raise IssuerCheckpointV2Error(f"failed to durably publish {label}") from exc
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)


def _write_exclusive_json(path: Path, payload: Mapping[str, Any], *, label: str) -> None:
    _write_exclusive(path, canonical_json_bytes(dict(payload)), label=label)


@contextmanager
def _locked_guard(root_descriptor: int) -> Iterator[None]:
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(
            ".checkpoint-v2.guard", flags, 0o600, dir_fd=root_descriptor
        )
    except OSError as exc:
        raise IssuerCheckpointV2Error("cannot open checkpoint guard safely") from exc
    try:
        def verify_guard_identity() -> None:
            try:
                anchored = os.fstat(descriptor)
                current = os.stat(
                    ".checkpoint-v2.guard",
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise IssuerCheckpointV2Error(
                    "checkpoint guard identity changed"
                ) from exc
            anchored_identity = (
                anchored.st_dev,
                anchored.st_ino,
                anchored.st_mode,
                anchored.st_nlink,
            )
            current_identity = (
                current.st_dev,
                current.st_ino,
                current.st_mode,
                current.st_nlink,
            )
            if (
                anchored_identity != current_identity
                or not stat.S_ISREG(anchored.st_mode)
                or anchored.st_nlink != 1
            ):
                raise IssuerCheckpointV2Error(
                    "checkpoint guard must retain one regular-file identity"
                )

        try:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except (ImportError, OSError) as exc:
            raise IssuerCheckpointV2Error("checkpoint locking is unavailable") from exc
        verify_guard_identity()
        try:
            yield
        except BaseException:
            raise
        else:
            verify_guard_identity()
    finally:
        try:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        os.close(descriptor)


def _validate_state(value: Mapping[str, Any]) -> dict[str, Any]:
    row = _exact(value, _STATE_FIELDS, "checkpoint state")
    if row["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
        raise IssuerCheckpointV2Error("unsupported checkpoint state schema")
    if row["market"] != "BOURSA_KUWAIT":
        raise IssuerCheckpointV2Error("checkpoint market must remain BOURSA_KUWAIT")
    _identifier(row["checkpoint_id"], "checkpoint_id")
    _identifier(row["run_id"], "run_id")
    _identifier(row["issuer_id"], "issuer_id")
    _security_code(row["security_code"])
    _positive_int(row["selected_queue_ordinal"], "selected_queue_ordinal")
    _identifier(row["plan_id"], "plan_id")
    for field in (
        "plan_sha256",
        "plan_content_sha256",
        "issuer_universe_sha256",
        "universe_content_sha256",
        "identity_sha256",
        "source_plan_sha256",
        "fencing_token",
        "prior_checkpoint_digest",
        "checkpoint_digest",
    ):
        try:
            require_sha256(row[field], field)
        except ValueError as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
    previous_security_seal = row["previous_security_terminal_seal_sha256"]
    if previous_security_seal is not None:
        try:
            require_sha256(
                previous_security_seal,
                "previous_security_terminal_seal_sha256",
            )
        except ValueError as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
    if (row["selected_queue_ordinal"] == 1) != (previous_security_seal is None):
        raise IssuerCheckpointV2Error(
            "checkpoint predecessor seal binding differs from queue position"
        )
    if row["expected_source_count"] != EXPECTED_SOURCE_COUNT:
        raise IssuerCheckpointV2Error("checkpoint source denominator is not 29")
    if row["expected_wave_count"] != EXPECTED_WAVE_COUNT:
        raise IssuerCheckpointV2Error("checkpoint wave denominator is not seven")
    generation = _positive_int(row["generation"], "generation")
    revision = _positive_int(row["revision"], "revision")
    owner = _identifier(row["owner_run_id"], "owner_run_id")
    if row["fencing_token"] != _fencing_token(
        row["checkpoint_id"], row["security_code"], generation, owner
    ):
        raise IssuerCheckpointV2Error("checkpoint fencing token is invalid")
    count = _nonnegative_int(row["terminal_receipt_count"], "terminal_receipt_count")
    if count > EXPECTED_SOURCE_COUNT:
        raise IssuerCheckpointV2Error("checkpoint has more than 29 terminal receipts")
    digests = row["terminal_receipt_sha256s"]
    if not isinstance(digests, list) or len(digests) != count:
        raise IssuerCheckpointV2Error("terminal receipt digest count is inconsistent")
    for index, digest in enumerate(digests):
        try:
            require_sha256(digest, f"terminal_receipt_sha256s[{index}]")
        except ValueError as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
    active = row["active_source_ordinal"]
    if active is not None and (
        not isinstance(active, int)
        or isinstance(active, bool)
        or active != count + 1
        or not 1 <= active <= EXPECTED_SOURCE_COUNT
    ):
        raise IssuerCheckpointV2Error("checkpoint active source is not the next ordinal")
    expected_next = count + 1
    if row["next_source_ordinal"] != expected_next:
        raise IssuerCheckpointV2Error("checkpoint next source ordinal is inconsistent")
    status = row["status"]
    if status not in {"RUNNING", "PREEMPTED", "RECONCILED", "SEALED"}:
        raise IssuerCheckpointV2Error("checkpoint status is invalid")
    event = row["event_type"]
    if event not in {
        "CREATED",
        "SOURCE_STARTED",
        "SOURCE_TERMINAL",
        "PREEMPTED",
        "RESUMED",
        "RECONCILED",
        "SEALED",
    }:
        raise IssuerCheckpointV2Error("checkpoint event_type is invalid")
    if status != "RUNNING" and active is not None:
        raise IssuerCheckpointV2Error("a stopped checkpoint cannot retain an active source")
    reconciliation = row["reconciliation_sha256"]
    seal = row["terminal_seal_sha256"]
    for value, label in ((reconciliation, "reconciliation_sha256"), (seal, "terminal_seal_sha256")):
        if value is not None:
            try:
                require_sha256(value, label)
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
    if status in {"RECONCILED", "SEALED"}:
        if count != EXPECTED_SOURCE_COUNT or reconciliation is None:
            raise IssuerCheckpointV2Error("terminal checkpoint lacks exact reconciliation")
    elif reconciliation is not None:
        raise IssuerCheckpointV2Error("non-reconciled checkpoint asserts reconciliation")
    if status == "SEALED":
        if seal is None or event != "SEALED":
            raise IssuerCheckpointV2Error("sealed checkpoint lacks terminal seal")
    elif seal is not None:
        raise IssuerCheckpointV2Error("unsealed checkpoint asserts terminal seal")
    created = _instant(row["created_at"], "created_at")
    updated = _instant(row["updated_at"], "updated_at")
    if updated < created:
        raise IssuerCheckpointV2Error("checkpoint updated_at precedes created_at")
    if row["claim_boundaries"] != _claim_boundaries():
        raise IssuerCheckpointV2Error("checkpoint claim boundaries changed")
    if row["checkpoint_digest"] != _state_digest(row):
        raise IssuerCheckpointV2Error("checkpoint digest mismatch")
    # Keep locals intentionally evaluated above for strict type validation.
    _ = revision
    return row


def _validate_transition(previous: dict[str, Any] | None, current: dict[str, Any]) -> None:
    if previous is None:
        if (
            current["revision"] != 1
            or current["generation"] != 1
            or current["event_type"] != "CREATED"
            or current["status"] != "RUNNING"
            or current["prior_checkpoint_digest"] != ZERO_DIGEST
            or current["terminal_receipt_count"] != 0
            or current["active_source_ordinal"] is not None
        ):
            raise IssuerCheckpointV2Error("initial checkpoint journal entry is invalid")
        return
    static_fields = (
        "checkpoint_id",
        "run_id",
        "market",
        "issuer_id",
        "security_code",
        "selected_queue_ordinal",
        "plan_id",
        "plan_sha256",
        "plan_content_sha256",
        "issuer_universe_sha256",
        "universe_content_sha256",
        "identity_sha256",
        "source_plan_sha256",
        "previous_security_terminal_seal_sha256",
        "expected_source_count",
        "expected_wave_count",
        "created_at",
        "claim_boundaries",
    )
    if any(current[field] != previous[field] for field in static_fields):
        raise IssuerCheckpointV2Error("checkpoint immutable binding changed")
    if current["revision"] != previous["revision"] + 1:
        raise IssuerCheckpointV2Error("checkpoint revisions are not contiguous")
    if current["prior_checkpoint_digest"] != previous["checkpoint_digest"]:
        raise IssuerCheckpointV2Error("checkpoint prior digest chain is broken")
    if _instant(current["updated_at"], "updated_at") < _instant(
        previous["updated_at"], "previous updated_at"
    ):
        raise IssuerCheckpointV2Error("checkpoint time moved backwards")
    event = current["event_type"]
    if previous["status"] == "SEALED":
        raise IssuerCheckpointV2Error("sealed checkpoint has a later journal mutation")
    if event == "SOURCE_STARTED":
        valid = (
            previous["status"] == "RUNNING"
            and previous["active_source_ordinal"] is None
            and previous["terminal_receipt_count"] < EXPECTED_SOURCE_COUNT
            and current["status"] == "RUNNING"
            and current["active_source_ordinal"]
            == previous["terminal_receipt_count"] + 1
            and current["terminal_receipt_count"]
            == previous["terminal_receipt_count"]
            and current["terminal_receipt_sha256s"]
            == previous["terminal_receipt_sha256s"]
            and current["generation"] == previous["generation"]
            and current["owner_run_id"] == previous["owner_run_id"]
        )
    elif event == "SOURCE_TERMINAL":
        valid = (
            previous["status"] == "RUNNING"
            and previous["active_source_ordinal"]
            == previous["terminal_receipt_count"] + 1
            and current["status"] == "RUNNING"
            and current["active_source_ordinal"] is None
            and current["terminal_receipt_count"]
            == previous["terminal_receipt_count"] + 1
            and current["terminal_receipt_sha256s"][:-1]
            == previous["terminal_receipt_sha256s"]
            and current["generation"] == previous["generation"]
            and current["owner_run_id"] == previous["owner_run_id"]
        )
    elif event == "PREEMPTED":
        valid = (
            previous["status"] == "RUNNING"
            and previous["terminal_receipt_count"] < EXPECTED_SOURCE_COUNT
            and current["status"] == "PREEMPTED"
            and current["active_source_ordinal"] is None
            and current["terminal_receipt_count"]
            == previous["terminal_receipt_count"]
            and current["terminal_receipt_sha256s"]
            == previous["terminal_receipt_sha256s"]
            and current["generation"] == previous["generation"]
            and current["owner_run_id"] == previous["owner_run_id"]
        )
    elif event == "RESUMED":
        valid = (
            previous["status"] == "PREEMPTED"
            and previous["terminal_receipt_count"] < EXPECTED_SOURCE_COUNT
            and current["status"] == "RUNNING"
            and current["active_source_ordinal"] is None
            and current["terminal_receipt_count"]
            == previous["terminal_receipt_count"]
            and current["terminal_receipt_sha256s"]
            == previous["terminal_receipt_sha256s"]
            and current["generation"] == previous["generation"] + 1
        )
    elif event == "RECONCILED":
        valid = (
            previous["status"] == "RUNNING"
            and previous["terminal_receipt_count"] == EXPECTED_SOURCE_COUNT
            and previous["active_source_ordinal"] is None
            and current["status"] == "RECONCILED"
            and current["terminal_receipt_sha256s"]
            == previous["terminal_receipt_sha256s"]
            and current["generation"] == previous["generation"]
            and current["owner_run_id"] == previous["owner_run_id"]
            and current["reconciliation_sha256"] is not None
        )
    elif event == "SEALED":
        valid = (
            previous["status"] == "RECONCILED"
            and current["status"] == "SEALED"
            and current["terminal_receipt_sha256s"]
            == previous["terminal_receipt_sha256s"]
            and current["generation"] == previous["generation"]
            and current["owner_run_id"] == previous["owner_run_id"]
            and current["reconciliation_sha256"]
            == previous["reconciliation_sha256"]
            and current["terminal_seal_sha256"] is not None
        )
    else:
        valid = False
    if not valid:
        raise IssuerCheckpointV2Error(f"invalid checkpoint transition: {event}")


def _inventory(rows: Mapping[str, bytes], paths: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "path": path,
            "sha256": sha256_bytes(rows[path]),
            "size_bytes": len(rows[path]),
        }
        for path in sorted(paths)
    ]


class IssuerCheckpointV2Store:
    """Append-only checkpoint store for one generated security fixture."""

    def __init__(self, root: Path | str, *, project_root: Path | str) -> None:
        self.root = Path(os.path.abspath(Path(root)))
        self.project_root = Path(os.path.abspath(Path(project_root)))
        try:
            require_real_directory(self.root, field="issuer checkpoint root")
        except ValueError as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
        root_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            self._root_descriptor = os.open(self.root, root_flags)
        except OSError as exc:
            raise IssuerCheckpointV2Error(
                "issuer checkpoint root cannot be anchored safely"
            ) from exc
        metadata = os.fstat(self._root_descriptor)
        self._identity = (metadata.st_dev, metadata.st_ino, metadata.st_mode)
        self._check_root()

    def close(self) -> None:
        descriptor = getattr(self, "_root_descriptor", -1)
        if descriptor >= 0:
            os.close(descriptor)
            self._root_descriptor = -1

    def __del__(self) -> None:  # pragma: no cover - deterministic callers use close().
        try:
            self.close()
        except OSError:
            pass

    @classmethod
    def create(
        cls,
        root: Path | str,
        *,
        plan: Path | str | Mapping[str, Any],
        issuer_universe: Path | str | Mapping[str, Any],
        project_root: Path | str,
        security_code: str,
        owner_run_id: str,
        created_at: str | datetime,
        prior_checkpoint_root: Path | str | None = None,
        prior_hmac_key: bytes | None = None,
        prior_expected_key_id: str | None = None,
    ) -> "IssuerCheckpointV2Store":
        code = _security_code(security_code)
        owner = _identifier(owner_run_id, "owner_run_id")
        instant = _timestamp(created_at, "created_at")
        plan_payload, plan_content = _document_bytes(plan, "sequential collection plan")
        universe_payload, universe_content = _document_bytes(
            issuer_universe, "issuer universe authority"
        )
        try:
            validate_issuer_sequential_collection_plan(
                plan_payload,
                issuer_universe=universe_payload,
                project_root=project_root,
            )
        except (IssuerSequentialCollectionError, ValueError) as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
        if _instant(instant, "created_at") < _instant(
            plan_payload.get("generated_at"), "plan generated_at"
        ):
            raise IssuerCheckpointV2Error(
                "checkpoint created_at precedes the bound plan generated_at"
            )
        matches = [row for row in plan_payload.get("queue", []) if row.get("security_code") == code]
        if len(matches) != 1:
            raise IssuerCheckpointV2Error(
                "execution selection must resolve to exactly one planned security_code"
            )
        selected = dict(matches[0])
        queue_ordinal = _positive_int(selected.get("ordinal"), "selected queue ordinal")
        queue = plan_payload["queue"]
        previous_security_seal_sha256: str | None = None
        if queue_ordinal > 1:
            if (
                prior_checkpoint_root is None
                or prior_hmac_key is None
                or prior_expected_key_id is None
            ):
                raise IssuerCheckpointV2Error(
                    "a later security requires the prior security terminal seal"
                )
            previous_code = str(queue[queue_ordinal - 2]["security_code"])
            prior = cls(prior_checkpoint_root, project_root=project_root)
            try:
                prior_report = prior.validate_terminal_seal(
                    key=prior_hmac_key,
                    expected_key_id=prior_expected_key_id,
                )
            finally:
                prior.close()
            if (
                prior_report["security_code"] != previous_code
                or prior_report["plan_sha256"] != plan_payload["plan_sha256"]
            ):
                raise IssuerCheckpointV2Error(
                    "prior terminal seal does not bind the immediately preceding security"
                )
            if _instant(instant, "created_at") < _instant(
                prior_report["issued_at"], "prior terminal seal issued_at"
            ):
                raise IssuerCheckpointV2Error(
                    "later checkpoint created_at precedes the authenticated predecessor seal"
                )
            previous_security_seal_sha256 = str(
                prior_report["terminal_seal_sha256"]
            )
        sources = selected.get("source_plan")
        if not isinstance(sources, list) or len(sources) != EXPECTED_SOURCE_COUNT:
            raise IssuerCheckpointV2Error("selected security must freeze exactly 29 sources")
        expected_sources = [source for wave in SOURCE_WAVE_SOURCES for source in wave]
        for ordinal, source in enumerate(sources, start=1):
            expected_wave = next(
                wave
                for wave, wave_sources in enumerate(SOURCE_WAVE_SOURCES, start=1)
                if expected_sources[ordinal - 1] in wave_sources
            )
            if (
                source.get("source_ordinal") != ordinal
                or source.get("source_id") != expected_sources[ordinal - 1]
                or source.get("wave_ordinal") != expected_wave
                or source.get("wave_id") != SOURCE_WAVE_IDS[expected_wave - 1]
            ):
                raise IssuerCheckpointV2Error(
                    "selected security source plan is not the locked 29-source/seven-wave order"
                )
        output = Path(os.path.abspath(Path(root)))
        try:
            prepare_output_root(output, label="issuer checkpoint root")
        except ValueError as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
        store = cls(output, project_root=project_root)
        with _locked_guard(store._root_descriptor):
            checkpoint_id = "CHK2-" + hashlib.sha256(
                canonical_json_bytes(
                    {"plan_sha256": plan_payload["plan_sha256"], "security_code": code}
                )
            ).hexdigest()[:24].upper()
            state: dict[str, Any] = {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "checkpoint_id": checkpoint_id,
                "run_id": str(plan_payload["run_id"]),
                "market": "BOURSA_KUWAIT",
                "issuer_id": str(selected["issuer_id"]),
                "security_code": code,
                "selected_queue_ordinal": queue_ordinal,
                "plan_id": str(plan_payload["plan_id"]),
                "plan_sha256": str(plan_payload["plan_sha256"]),
                "plan_content_sha256": sha256_bytes(plan_content),
                "issuer_universe_sha256": str(plan_payload["issuer_universe_sha256"]),
                "universe_content_sha256": sha256_bytes(universe_content),
                "identity_sha256": str(selected["identity_sha256"]),
                "source_plan_sha256": hash_json(sources),
                "previous_security_terminal_seal_sha256": previous_security_seal_sha256,
                "expected_source_count": EXPECTED_SOURCE_COUNT,
                "expected_wave_count": EXPECTED_WAVE_COUNT,
                "status": "RUNNING",
                "event_type": "CREATED",
                "generation": 1,
                "revision": 1,
                "owner_run_id": owner,
                "fencing_token": _fencing_token(checkpoint_id, code, 1, owner),
                "prior_checkpoint_digest": ZERO_DIGEST,
                "next_source_ordinal": 1,
                "active_source_ordinal": None,
                "terminal_receipt_count": 0,
                "terminal_receipt_sha256s": [],
                "reconciliation_sha256": None,
                "terminal_seal_sha256": None,
                "created_at": instant,
                "updated_at": instant,
                "claim_boundaries": _claim_boundaries(),
                "checkpoint_digest": "",
            }
            state["checkpoint_digest"] = _state_digest(state)
            validated = _validate_state(state)
            _validate_transition(None, validated)
            store._stage_transaction(
                previous=None,
                next_state=validated,
                payloads={
                    "bindings/issuer-universe.json": universe_content,
                    "bindings/collection-plan.json": plan_content,
                },
            )
        # Reopen the complete generated bundle before reporting creation.
        store.load()
        return store

    def _check_root(self) -> None:
        try:
            anchored = os.fstat(self._root_descriptor)
            current = _root_identity(self.root)
        except OSError as exc:
            raise IssuerCheckpointV2Error("checkpoint root changed or disappeared") from exc
        anchored_identity = (anchored.st_dev, anchored.st_ino, anchored.st_mode)
        if (
            anchored_identity != self._identity
            or current != self._identity
            or stat.S_ISLNK(current[2])
            or not stat.S_ISDIR(current[2])
        ):
            raise IssuerCheckpointV2Error("checkpoint root identity changed")

    def _open_directory_descriptor(self, relative: str, *, create: bool) -> int:
        """Walk below the anchored root without following path components."""

        if relative == "":
            return os.dup(self._root_descriptor)
        canonical = _relative_path(relative, "checkpoint directory")
        descriptor = os.dup(self._root_descriptor)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            for component in PurePosixPath(canonical).parts:
                if create:
                    try:
                        os.mkdir(component, mode=0o700, dir_fd=descriptor)
                        os.fsync(descriptor)
                    except FileExistsError:
                        pass
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                metadata = os.fstat(next_descriptor)
                if not stat.S_ISDIR(metadata.st_mode):
                    os.close(next_descriptor)
                    raise IssuerCheckpointV2Error(
                        "checkpoint directory component is not real"
                    )
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except OSError as exc:
            os.close(descriptor)
            raise IssuerCheckpointV2Error(
                "checkpoint directory cannot be traversed safely"
            ) from exc
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def _directory_descriptor_identity(descriptor: int) -> tuple[int, int, int]:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise IssuerCheckpointV2Error(
                "checkpoint target parent is no longer a directory"
            )
        return metadata.st_dev, metadata.st_ino, metadata.st_mode

    def _verify_directory_identity(
        self, relative: str, expected: tuple[int, int, int]
    ) -> None:
        self._check_root()
        reopened = self._open_directory_descriptor(relative, create=False)
        try:
            if self._directory_descriptor_identity(reopened) != expected:
                raise IssuerCheckpointV2Error(
                    "checkpoint target parent identity changed during commit"
                )
        finally:
            os.close(reopened)

    def _verify_directory_descriptor(self, relative: str, descriptor: int) -> None:
        self._verify_directory_identity(
            relative, self._directory_descriptor_identity(descriptor)
        )

    @staticmethod
    def _read_descriptor_file(
        directory_descriptor: int,
        name: str,
        *,
        label: str,
        max_bytes: int = 64 * 1024 * 1024,
        allow_link_count_two: bool = False,
    ) -> tuple[bytes, os.stat_result]:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(name, flags, dir_fd=directory_descriptor)
        except OSError as exc:
            raise IssuerCheckpointV2Error(f"{label} cannot be opened safely") from exc
        try:
            before = os.fstat(descriptor)
            allowed_links = {1, 2} if allow_link_count_two else {1}
            if not stat.S_ISREG(before.st_mode) or before.st_nlink not in allowed_links:
                raise IssuerCheckpointV2Error(
                    f"{label} must be a non-hard-linked regular file"
                )
            if before.st_size > max_bytes:
                raise IssuerCheckpointV2Error(f"{label} exceeds its byte budget")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise IssuerCheckpointV2Error(f"{label} exceeds its byte budget")
            after = os.fstat(descriptor)
            if (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise IssuerCheckpointV2Error(f"{label} changed while being read")
            return b"".join(chunks), after
        finally:
            os.close(descriptor)

    def _current_journal_state_anchored(self) -> dict[str, Any] | None:
        journal_descriptor = self._open_directory_descriptor("journal", create=True)
        try:
            names = sorted(os.listdir(journal_descriptor))
            if not names:
                return None
            if any(re.fullmatch(r"[0-9]{8}\.json", name) is None for name in names):
                raise IssuerCheckpointV2Error("checkpoint journal contains an unsafe entry")
            for index, name in enumerate(names, start=1):
                if name != f"{index:08d}.json":
                    raise IssuerCheckpointV2Error(
                        "checkpoint journal revisions are not contiguous"
                    )
            content, _metadata = self._read_descriptor_file(
                journal_descriptor,
                names[-1],
                label="checkpoint journal head",
            )
            try:
                payload = strict_json_object(content, "checkpoint journal head")
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            if content != canonical_json_bytes(payload):
                raise IssuerCheckpointV2Error(
                    "checkpoint journal head is not canonical JSON"
                )
            return _validate_state(payload)
        finally:
            os.close(journal_descriptor)

    def _journal_state_at_revision_anchored(
        self, revision: int
    ) -> dict[str, Any]:
        canonical_revision = _positive_int(revision, "journal revision")
        journal_descriptor = self._open_directory_descriptor(
            "journal", create=False
        )
        try:
            name = f"{canonical_revision:08d}.json"
            content, _metadata = self._read_descriptor_file(
                journal_descriptor,
                name,
                label=f"checkpoint journal revision {canonical_revision}",
                allow_link_count_two=True,
            )
            try:
                payload = strict_json_object(
                    content, f"checkpoint journal revision {canonical_revision}"
                )
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            if content != canonical_json_bytes(payload):
                raise IssuerCheckpointV2Error(
                    "checkpoint journal revision is not canonical JSON"
                )
            state = _validate_state(payload)
            if state["revision"] != canonical_revision:
                raise IssuerCheckpointV2Error(
                    "checkpoint journal filename differs from its revision"
                )
            return state
        finally:
            os.close(journal_descriptor)

    def _read_anchored_file(self, relative: str, *, label: str) -> bytes:
        canonical = _relative_path(relative, label)
        parts = PurePosixPath(canonical).parts
        parent_descriptor = self._open_directory_descriptor(
            "/".join(parts[:-1]), create=False
        )
        try:
            content, _metadata = self._read_descriptor_file(
                parent_descriptor, parts[-1], label=label
            )
            return content
        finally:
            os.close(parent_descriptor)

    def _validated_staged_terminal_seal(
        self,
        *,
        content: bytes,
        previous_state: Mapping[str, Any],
        next_state: Mapping[str, Any],
        preseal_files: Mapping[str, bytes],
        recovery_hmac_key: bytes | None,
        recovery_expected_key_id: str | None,
    ) -> dict[str, Any]:
        """Authenticate a staged seal completely before publishing any byte."""

        if recovery_hmac_key is None or recovery_expected_key_id is None:
            raise IssuerCheckpointV2Error(
                "pending terminal seal recovery requires authenticated HMAC key"
            )
        secret = _hmac_key(recovery_hmac_key)
        key_id = _identifier(
            recovery_expected_key_id, "recovery terminal seal key_id"
        )
        try:
            seal = _exact(
                strict_json_object(content, "staged terminal seal"),
                _SEAL_FIELDS,
                "staged terminal seal",
            )
        except ValueError as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
        if content != canonical_json_bytes(seal):
            raise IssuerCheckpointV2Error(
                "staged terminal seal is not canonical JSON"
            )
        authentication = _exact(
            seal.get("authentication"), _AUTH_FIELDS, "staged seal authentication"
        )
        tag = authentication.get("tag")
        if (
            authentication.get("algorithm") != SEAL_ALGORITHM
            or authentication.get("key_id") != key_id
            or not isinstance(tag, str)
            or re.fullmatch(r"[0-9a-f]{64}", tag) is None
        ):
            raise IssuerCheckpointV2Error(
                "staged terminal seal authentication metadata is invalid"
            )
        calculated = hmac.new(
            secret, _canonical_authentication_bytes(seal), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(calculated, tag):
            raise IssuerCheckpointV2Error(
                "staged terminal seal authentication failed"
            )
        expected_bindings = {
            "schema_version": SEAL_SCHEMA_VERSION,
            "audience": SEAL_AUDIENCE,
            "seal_id": f"SEAL-{previous_state['checkpoint_id']}",
            "checkpoint_id": previous_state["checkpoint_id"],
            "run_id": previous_state["run_id"],
            "market": "BOURSA_KUWAIT",
            "issuer_id": previous_state["issuer_id"],
            "security_code": previous_state["security_code"],
            "identity_sha256": previous_state["identity_sha256"],
            "plan_sha256": previous_state["plan_sha256"],
            "issuer_universe_sha256": previous_state["issuer_universe_sha256"],
            "source_plan_sha256": previous_state["source_plan_sha256"],
            "generation": previous_state["generation"],
            "revision": previous_state["revision"],
            "owner_run_id": previous_state["owner_run_id"],
            "fencing_token": previous_state["fencing_token"],
            "terminal_checkpoint_digest": previous_state["checkpoint_digest"],
            "reconciliation_sha256": previous_state["reconciliation_sha256"],
            "terminal_receipt_count": EXPECTED_SOURCE_COUNT,
            "wave_count": EXPECTED_WAVE_COUNT,
            "previous_security_terminal_seal_sha256": previous_state[
                "previous_security_terminal_seal_sha256"
            ],
            "claim_boundaries": _claim_boundaries(),
        }
        if any(seal.get(field) != value for field, value in expected_bindings.items()):
            raise IssuerCheckpointV2Error(
                "staged terminal seal binding differs from checkpoint"
            )
        _identifier(seal.get("key_issuer_id"), "staged seal key_issuer_id")
        _instant(seal.get("issued_at"), "staged seal issued_at")
        inventory = seal.get("bundle_inventory")
        if not isinstance(inventory, list):
            raise IssuerCheckpointV2Error(
                "staged terminal seal inventory must be a list"
            )
        normalized_inventory: list[dict[str, Any]] = []
        for index, item in enumerate(inventory):
            entry = _exact(item, _INVENTORY_FIELDS, f"staged seal inventory {index}")
            _relative_path(entry.get("path"), "staged seal inventory path")
            try:
                require_sha256(entry.get("sha256"), "staged seal inventory sha256")
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            _nonnegative_int(entry.get("size_bytes"), "staged seal inventory size_bytes")
            normalized_inventory.append(entry)
        expected_inventory = _inventory(preseal_files, set(preseal_files))
        if normalized_inventory != expected_inventory:
            raise IssuerCheckpointV2Error(
                "staged terminal seal inventory differs from reopened bytes"
            )
        if seal.get("bundle_root_sha256") != hash_json(expected_inventory):
            raise IssuerCheckpointV2Error(
                "staged terminal seal bundle root digest mismatch"
            )
        seal_sha256 = sha256_bytes(content)
        expected_final_state = dict(previous_state)
        expected_final_state["event_type"] = "SEALED"
        expected_final_state["revision"] = previous_state["revision"] + 1
        expected_final_state["prior_checkpoint_digest"] = previous_state[
            "checkpoint_digest"
        ]
        expected_final_state["updated_at"] = seal["issued_at"]
        expected_final_state["status"] = "SEALED"
        expected_final_state["terminal_seal_sha256"] = seal_sha256
        expected_final_state["checkpoint_digest"] = _state_digest(
            expected_final_state
        )
        _validate_transition(
            dict(previous_state), _validate_state(expected_final_state)
        )
        if dict(next_state) != expected_final_state:
            raise IssuerCheckpointV2Error(
                "staged final state differs from authenticated seal derivation"
            )
        return seal

    def _validate_transaction_target_contract(
        self,
        *,
        previous_state: Mapping[str, Any] | None,
        next_state: Mapping[str, Any],
        payload_by_target: Mapping[str, bytes],
        journal_target: str,
        recovery_hmac_key: bytes | None = None,
        recovery_expected_key_id: str | None = None,
    ) -> None:
        """Derive every legal payload path from the state event and payload bytes."""

        event = next_state["event_type"]
        actual_targets = set(payload_by_target)
        if event == "CREATED":
            expected_targets = {
                "bindings/issuer-universe.json",
                "bindings/collection-plan.json",
                journal_target,
            }
            if actual_targets != expected_targets:
                raise IssuerCheckpointV2Error(
                    "created transaction target set differs from its event contract"
                )
            plan_content = payload_by_target["bindings/collection-plan.json"]
            universe_content = payload_by_target["bindings/issuer-universe.json"]
            try:
                plan = strict_json_object(plan_content, "staged collection plan")
                universe = strict_json_object(
                    universe_content, "staged issuer universe"
                )
                validate_issuer_sequential_collection_plan(
                    plan,
                    issuer_universe=universe,
                    project_root=self.project_root,
                )
            except (ValueError, IssuerSequentialCollectionError) as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            if (
                sha256_bytes(plan_content) != next_state["plan_content_sha256"]
                or sha256_bytes(universe_content)
                != next_state["universe_content_sha256"]
                or plan.get("plan_sha256") != next_state["plan_sha256"]
                or plan.get("issuer_universe_sha256")
                != next_state["issuer_universe_sha256"]
            ):
                raise IssuerCheckpointV2Error(
                    "created transaction authorities differ from checkpoint state"
                )
            selected_rows = [
                row
                for row in plan["queue"]
                if row.get("security_code") == next_state["security_code"]
            ]
            if len(selected_rows) != 1:
                raise IssuerCheckpointV2Error(
                    "created transaction does not select exactly one security"
                )
            selected = selected_rows[0]
            expected_checkpoint_id = "CHK2-" + hashlib.sha256(
                canonical_json_bytes(
                    {
                        "plan_sha256": plan["plan_sha256"],
                        "security_code": next_state["security_code"],
                    }
                )
            ).hexdigest()[:24].upper()
            if (
                next_state["checkpoint_id"] != expected_checkpoint_id
                or next_state["run_id"] != plan["run_id"]
                or next_state["plan_id"] != plan["plan_id"]
                or next_state["selected_queue_ordinal"] != selected["ordinal"]
                or next_state["issuer_id"] != selected["issuer_id"]
                or next_state["identity_sha256"] != selected["identity_sha256"]
                or next_state["source_plan_sha256"]
                != hash_json(selected["source_plan"])
            ):
                raise IssuerCheckpointV2Error(
                    "created transaction selection differs from frozen authorities"
                )
            return
        if next_state["revision"] <= 1:
            raise IssuerCheckpointV2Error(
                "non-created transaction lacks a committed predecessor"
            )
        if previous_state is None:
            raise IssuerCheckpointV2Error(
                "non-created transaction predecessor cannot be reopened"
            )
        if event in {"SOURCE_STARTED", "PREEMPTED", "RESUMED"}:
            if actual_targets != {journal_target}:
                raise IssuerCheckpointV2Error(
                    "journal-only transaction contains an illegal payload target"
                )
            return
        if event == "RECONCILED":
            if actual_targets != {"reconciliation.json", journal_target}:
                raise IssuerCheckpointV2Error(
                    "reconciliation transaction target set differs"
                )
            content = payload_by_target["reconciliation.json"]
            try:
                payload = _exact(
                    strict_json_object(content, "staged reconciliation"),
                    _RECONCILIATION_FIELDS,
                    "staged reconciliation",
                )
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            pretransaction_files = self._anchored_snapshot_once(
                skip_staging=True,
                allow_hardlinked_paths=frozenset(payload_by_target),
            )
            for target in payload_by_target:
                pretransaction_files.pop(target, None)
            try:
                plan = strict_json_object(
                    pretransaction_files["bindings/collection-plan.json"],
                    "bound collection plan",
                )
                universe = strict_json_object(
                    pretransaction_files["bindings/issuer-universe.json"],
                    "bound issuer universe",
                )
                validate_issuer_sequential_collection_plan(
                    plan,
                    issuer_universe=universe,
                    project_root=self.project_root,
                )
            except (KeyError, ValueError, IssuerSequentialCollectionError) as exc:
                raise IssuerCheckpointV2Error(
                    "staged reconciliation authorities cannot be reopened"
                ) from exc
            selected = plan["queue"][previous_state["selected_queue_ordinal"] - 1]
            receipts, _receipt_paths = self._validated_receipts(
                pretransaction_files, previous_state, selected
            )
            validated_reconciliation = self._validated_reconciliation(
                payload, state_before=previous_state, receipts=receipts
            )
            if (
                content != canonical_json_bytes(payload)
                or validated_reconciliation["reconciliation_sha256"]
                != next_state["reconciliation_sha256"]
                or validated_reconciliation["reconciled_at"]
                != next_state["updated_at"]
            ):
                raise IssuerCheckpointV2Error(
                    "staged reconciliation differs from checkpoint state"
                )
            return
        if event == "SEALED":
            if actual_targets != {"terminal-seal.json", journal_target}:
                raise IssuerCheckpointV2Error(
                    "seal transaction target set differs"
                )
            content = payload_by_target["terminal-seal.json"]
            preseal_files = self._anchored_snapshot_once(
                skip_staging=True,
                allow_hardlinked_paths=frozenset(payload_by_target),
            )
            for target in payload_by_target:
                preseal_files.pop(target, None)
            self._validated_staged_terminal_seal(
                content=content,
                previous_state=previous_state,
                next_state=next_state,
                preseal_files=preseal_files,
                recovery_hmac_key=recovery_hmac_key,
                recovery_expected_key_id=recovery_expected_key_id,
            )
            if sha256_bytes(content) != next_state["terminal_seal_sha256"]:
                raise IssuerCheckpointV2Error(
                    "staged terminal seal differs from checkpoint state"
                )
            return
        if event != "SOURCE_TERMINAL":
            raise IssuerCheckpointV2Error(
                "transaction event has no payload target contract"
            )

        plan_content = self._read_anchored_file(
            "bindings/collection-plan.json", label="bound collection plan"
        )
        universe_content = self._read_anchored_file(
            "bindings/issuer-universe.json", label="bound issuer universe"
        )
        try:
            plan = strict_json_object(plan_content, "bound collection plan")
            universe = strict_json_object(universe_content, "bound issuer universe")
            validate_issuer_sequential_collection_plan(
                plan, issuer_universe=universe, project_root=self.project_root
            )
        except (ValueError, IssuerSequentialCollectionError) as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
        if (
            sha256_bytes(plan_content) != next_state["plan_content_sha256"]
            or sha256_bytes(universe_content)
            != next_state["universe_content_sha256"]
        ):
            raise IssuerCheckpointV2Error(
                "bound transaction authorities differ from checkpoint state"
            )
        selected = plan["queue"][next_state["selected_queue_ordinal"] - 1]
        pretransaction_files = self._anchored_snapshot_once(
            skip_staging=True,
            allow_hardlinked_paths=frozenset(payload_by_target),
        )
        for target in payload_by_target:
            pretransaction_files.pop(target, None)
        prior_receipts, _prior_receipt_paths = self._validated_receipts(
            pretransaction_files, previous_state, selected
        )
        ordinal = next_state["terminal_receipt_count"]
        source = selected["source_plan"][ordinal - 1]
        package = f"receipts/{ordinal:03d}-{source['source_id']}"
        manifest_target = f"{package}/manifest.json"
        receipt_target = f"{package}/receipt.json"
        if manifest_target not in payload_by_target or receipt_target not in payload_by_target:
            raise IssuerCheckpointV2Error(
                "terminal source transaction lacks its manifest or receipt"
            )
        manifest_content = payload_by_target[manifest_target]
        receipt_content = payload_by_target[receipt_target]
        try:
            manifest = _exact(
                strict_json_object(manifest_content, "staged source manifest"),
                _MANIFEST_FIELDS,
                "staged source manifest",
            )
            receipt = _exact(
                strict_json_object(receipt_content, "staged source receipt"),
                _RECEIPT_FIELDS,
                "staged source receipt",
            )
        except ValueError as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
        if (
            manifest_content != canonical_json_bytes(manifest)
            or receipt_content != canonical_json_bytes(receipt)
        ):
            raise IssuerCheckpointV2Error(
                "terminal source transaction documents are not canonical JSON"
            )
        _positive_int(manifest.get("source_ordinal"), "manifest source_ordinal")
        _positive_int(manifest.get("wave_ordinal"), "manifest wave_ordinal")
        _positive_int(receipt.get("source_ordinal"), "receipt source_ordinal")
        _positive_int(receipt.get("wave_ordinal"), "receipt wave_ordinal")
        expected_bindings = {
            "checkpoint_id": next_state["checkpoint_id"],
            "security_code": next_state["security_code"],
            "source_ordinal": ordinal,
            "wave_ordinal": source["wave_ordinal"],
            "wave_id": source["wave_id"],
            "source_id": source["source_id"],
        }
        if (
            manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
            or any(
                manifest.get(field) != value
                for field, value in expected_bindings.items()
            )
            or manifest.get("manifest_sha256") != _manifest_digest(manifest)
        ):
            raise IssuerCheckpointV2Error(
                "staged source manifest differs from frozen plan"
            )
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) > MAX_RAW_FILES_PER_SOURCE:
            raise IssuerCheckpointV2Error(
                "staged source manifest artifact count is invalid"
            )
        artifact_paths: list[str] = []
        raw_size = 0
        expected_targets = {manifest_target, receipt_target, journal_target}
        for index, value in enumerate(artifacts):
            artifact = _exact(
                value, _ARTIFACT_FIELDS, f"staged source artifact {index}"
            )
            relative = _relative_path(artifact["path"], "staged raw artifact path")
            if not relative.startswith("raw/"):
                raise IssuerCheckpointV2Error(
                    "staged source artifact must remain below raw/"
                )
            target = f"{package}/{relative}"
            if target not in payload_by_target:
                raise IssuerCheckpointV2Error(
                    "staged source raw artifact target is missing"
                )
            content = payload_by_target[target]
            _nonnegative_int(
                artifact.get("size_bytes"), "staged artifact size_bytes"
            )
            if (
                len(content) > MAX_RAW_FILE_BYTES
                or artifact.get("sha256") != sha256_bytes(content)
                or artifact.get("size_bytes") != len(content)
            ):
                raise IssuerCheckpointV2Error(
                    "staged source raw artifact digest, size, or budget differs"
                )
            artifact_paths.append(relative)
            raw_size += len(content)
            expected_targets.add(target)
        if (
            artifact_paths != sorted(set(artifact_paths))
            or raw_size > MAX_RAW_BYTES_PER_SOURCE
            or sum(row["artifact_count"] for row in prior_receipts)
            + len(artifacts)
            > MAX_CHECKPOINT_RAW_FILES
            or sum(row["raw_size_bytes"] for row in prior_receipts) + raw_size
            > MAX_CHECKPOINT_RAW_BYTES
            or actual_targets != expected_targets
        ):
            raise IssuerCheckpointV2Error(
                "terminal source transaction target set or raw budget differs"
            )
        expected_receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "receipt_id": f"{next_state['checkpoint_id']}:{ordinal:03d}",
            "checkpoint_id": next_state["checkpoint_id"],
            "run_id": next_state["run_id"],
            "plan_sha256": next_state["plan_sha256"],
            "identity_sha256": next_state["identity_sha256"],
            "issuer_id": next_state["issuer_id"],
            "security_code": next_state["security_code"],
            "source_ordinal": ordinal,
            "wave_ordinal": source["wave_ordinal"],
            "wave_id": source["wave_id"],
            "source_id": source["source_id"],
            "artifact_count": len(artifacts),
            "artifact_manifest_path": manifest_target,
            "artifact_manifest_sha256": manifest["manifest_sha256"],
            "raw_size_bytes": raw_size,
            "previous_terminal_receipt_sha256": (
                None
                if ordinal == 1
                else next_state["terminal_receipt_sha256s"][-2]
            ),
        }
        if any(receipt.get(field) != value for field, value in expected_receipt.items()):
            raise IssuerCheckpointV2Error(
                "staged source receipt differs from checkpoint state"
            )
        _nonnegative_int(receipt.get("artifact_count"), "receipt artifact_count")
        _nonnegative_int(receipt.get("raw_size_bytes"), "receipt raw_size_bytes")
        attempted = _instant(receipt.get("attempted_at"), "receipt attempted_at")
        completed = _instant(receipt.get("completed_at"), "receipt completed_at")
        observations = _nonnegative_int(
            receipt.get("observation_count"), "observation_count"
        )
        limitation = receipt.get("limitation")
        digest = _receipt_digest(receipt)
        if (
            receipt.get("terminal_status") not in TERMINAL_SOURCE_STATUSES
            or completed < attempted
            or attempted
            < _instant(previous_state["updated_at"], "source-start updated_at")
            or completed
            > _instant(next_state["updated_at"], "source-terminal updated_at")
            or (receipt["terminal_status"] != "COLLECTED" and observations)
            or (
                receipt["terminal_status"] in _NON_BLOCKING_TERMINAL_STATUSES
                and not artifacts
            )
            or not isinstance(limitation, str)
            or limitation != limitation.strip()
            or len(limitation) > 2000
            or receipt.get("receipt_sha256") != digest
            or digest != next_state["terminal_receipt_sha256s"][-1]
        ):
            raise IssuerCheckpointV2Error(
                "staged source receipt terminal contract differs"
            )

    def _stage_transaction(
        self,
        *,
        previous: Mapping[str, Any] | None,
        next_state: dict[str, Any],
        payloads: Mapping[str, bytes],
        recovery_hmac_key: bytes | None = None,
        recovery_expected_key_id: str | None = None,
    ) -> None:
        """Publish a complete immutable transaction to a recoverable stage."""

        next_state["checkpoint_digest"] = _state_digest(next_state)
        validated = _validate_state(next_state)
        _validate_transition(dict(previous) if previous is not None else None, validated)
        journal_target = f"journal/{validated['revision']:08d}.json"
        canonical_payloads = dict(payloads)
        canonical_payloads[journal_target] = canonical_json_bytes(validated)
        if len(canonical_payloads) != len(set(canonical_payloads)):
            raise IssuerCheckpointV2Error("transaction contains duplicate targets")
        targets: list[dict[str, Any]] = []
        ordered_targets = sorted(path for path in canonical_payloads if path != journal_target)
        ordered_targets.append(journal_target)
        for index, target in enumerate(ordered_targets):
            canonical_target = _relative_path(target, "transaction target")
            content = canonical_payloads[target]
            if not isinstance(content, bytes):
                raise IssuerCheckpointV2Error("transaction payload must be bytes")
            targets.append(
                {
                    "staged_name": f"payload-{index:04d}.bin",
                    "target": canonical_target,
                    "sha256": sha256_bytes(content),
                    "size_bytes": len(content),
                    "is_commit_marker": canonical_target == journal_target,
                }
            )
        transaction: dict[str, Any] = {
            "schema_version": "issuer-checkpoint-transaction-v2",
            "checkpoint_id": validated["checkpoint_id"],
            "revision": validated["revision"],
            "prior_revision": 0 if previous is None else previous["revision"],
            "prior_checkpoint_digest": (
                ZERO_DIGEST if previous is None else previous["checkpoint_digest"]
            ),
            "resulting_checkpoint_digest": validated["checkpoint_digest"],
            "targets": targets,
            "transaction_sha256": "",
        }
        transaction["transaction_sha256"] = hash_json(
            {
                key: value
                for key, value in transaction.items()
                if key != "transaction_sha256"
            }
        )
        parent = require_real_directory(
            self.root.parent, field="checkpoint transaction parent"
        )
        temporary: Path | None = Path(
            tempfile.mkdtemp(
                prefix=f".{self.root.name}.txn-{validated['revision']:08d}-",
                dir=parent,
            )
        )
        temporary_descriptor = -1
        temporary_identity: tuple[int, int, int] | None = None
        allowed_temporary_names = {
            "transaction.json",
            *(row["staged_name"] for row in targets),
        }
        try:
            temporary_descriptor = os.open(
                temporary,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            temporary_identity = self._directory_descriptor_identity(
                temporary_descriptor
            )

            def write_staged(name: str, content: bytes) -> None:
                descriptor = -1
                try:
                    descriptor = os.open(
                        name,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_CLOEXEC", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=temporary_descriptor,
                    )
                    offset = 0
                    while offset < len(content):
                        written = os.write(descriptor, content[offset:])
                        if written <= 0:
                            raise OSError("staged transaction write made no progress")
                        offset += written
                    os.fsync(descriptor)
                    metadata = os.fstat(descriptor)
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                        raise IssuerCheckpointV2Error(
                            "staged transaction payload identity is unsafe"
                        )
                except OSError as exc:
                    raise IssuerCheckpointV2Error(
                        "failed to write staged checkpoint transaction"
                    ) from exc
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)

            for target, row in zip(ordered_targets, targets):
                write_staged(row["staged_name"], canonical_payloads[target])
            write_staged(
                "transaction.json", canonical_json_bytes(transaction)
            )
            if set(os.listdir(temporary_descriptor)) != allowed_temporary_names:
                raise IssuerCheckpointV2Error(
                    "uncommitted transaction staging contains unexpected bytes"
                )
            os.fsync(temporary_descriptor)
            staging_descriptor = self._open_directory_descriptor(
                ".staging", create=True
            )
            parent_descriptor = -1
            try:
                self._verify_directory_descriptor(
                    ".staging", staging_descriptor
                )
                parent_descriptor = os.open(
                    parent,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                temporary_entry = os.stat(
                    temporary.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                assert temporary_identity is not None
                if (
                    temporary_entry.st_dev,
                    temporary_entry.st_ino,
                    temporary_entry.st_mode,
                ) != temporary_identity:
                    raise IssuerCheckpointV2Error(
                        "uncommitted transaction staging identity changed"
                    )
                stage_name = f"{validated['revision']:08d}"
                try:
                    os.stat(stage_name, dir_fd=staging_descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise IssuerCheckpointV2Error(
                        "checkpoint transaction revision is already staged"
                    )
                os.rename(
                    temporary.name,
                    stage_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=staging_descriptor,
                )
                moved_entry = os.stat(
                    stage_name,
                    dir_fd=staging_descriptor,
                    follow_symlinks=False,
                )
                assert temporary_identity is not None
                if (
                    moved_entry.st_dev,
                    moved_entry.st_ino,
                    moved_entry.st_mode,
                ) != temporary_identity:
                    # The pathname was swapped after the pre-rename identity
                    # check.  Move the replacement back out of the checkpoint
                    # without deleting a byte; the genuine transaction remains
                    # reachable only through its held descriptor and is cleaned
                    # below.
                    try:
                        os.stat(
                            temporary.name,
                            dir_fd=parent_descriptor,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        try:
                            os.rename(
                                stage_name,
                                temporary.name,
                                src_dir_fd=staging_descriptor,
                                dst_dir_fd=parent_descriptor,
                            )
                            os.fsync(staging_descriptor)
                            os.fsync(parent_descriptor)
                        except OSError as exc:
                            raise IssuerCheckpointV2Error(
                                "swapped transaction staging could not be evacuated safely"
                            ) from exc
                    else:
                        raise IssuerCheckpointV2Error(
                            "swapped transaction staging destination is occupied"
                        )
                    raise IssuerCheckpointV2Error(
                        "uncommitted transaction staging changed during rename"
                    )
                # The transaction is now owned by the anchored checkpoint even
                # if a later fsync or identity check is interrupted.
                temporary = None
                os.fsync(staging_descriptor)
                try:
                    self._verify_directory_descriptor(
                        ".staging", staging_descriptor
                    )
                except IssuerCheckpointV2Error:
                    # A replacement of the checkpoint root itself is never a
                    # staging-directory race and must retain the primary,
                    # fail-closed root-identity error.
                    self._check_root()
                    # The stage was durably moved, but the directory name was
                    # swapped during rename.  Move the transaction from the
                    # still-open detached directory into the currently
                    # authoritative anchored staging directory.
                    canonical_staging = self._open_directory_descriptor(
                        ".staging", create=True
                    )
                    try:
                        try:
                            os.stat(
                                stage_name,
                                dir_fd=canonical_staging,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            pass
                        else:
                            raise IssuerCheckpointV2Error(
                                "replacement staging directory already contains this revision"
                            )
                        os.rename(
                            stage_name,
                            stage_name,
                            src_dir_fd=staging_descriptor,
                            dst_dir_fd=canonical_staging,
                        )
                        os.fsync(staging_descriptor)
                        os.fsync(canonical_staging)
                        self._verify_directory_descriptor(
                            ".staging", canonical_staging
                        )
                    finally:
                        os.close(canonical_staging)
                # Consume the transaction through the exact staging directory
                # descriptor used for publication.  Closing and reopening the
                # path here would reintroduce a rename/swap gap.
                self._recover_transactions(
                    staging_descriptor=staging_descriptor,
                    recovery_hmac_key=recovery_hmac_key,
                    recovery_expected_key_id=recovery_expected_key_id,
                )
            finally:
                if parent_descriptor >= 0:
                    os.close(parent_descriptor)
                os.close(staging_descriptor)
        finally:
            cleanup_error: OSError | IssuerCheckpointV2Error | None = None
            if temporary is not None and temporary_descriptor >= 0:
                try:
                    names = set(os.listdir(temporary_descriptor))
                    if not names <= allowed_temporary_names:
                        raise IssuerCheckpointV2Error(
                            "refusing to clean changed transaction staging"
                        )
                    for name in sorted(names):
                        os.unlink(name, dir_fd=temporary_descriptor)
                    os.fsync(temporary_descriptor)
                    cleanup_parent = os.open(
                        parent,
                        os.O_RDONLY
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_CLOEXEC", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                    )
                    try:
                        try:
                            current_entry = os.stat(
                                temporary.name,
                                dir_fd=cleanup_parent,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            pass
                        else:
                            assert temporary_identity is not None
                            if (
                                current_entry.st_dev,
                                current_entry.st_ino,
                                current_entry.st_mode,
                            ) == temporary_identity:
                                os.rmdir(temporary.name, dir_fd=cleanup_parent)
                                os.fsync(cleanup_parent)
                    finally:
                        os.close(cleanup_parent)
                except (OSError, IssuerCheckpointV2Error) as exc:
                    cleanup_error = exc
            if temporary_descriptor >= 0:
                os.close(temporary_descriptor)
            if cleanup_error is not None:
                    raise IssuerCheckpointV2Error(
                        "failed to clean uncommitted transaction staging"
                    ) from cleanup_error
        self._check_root()

    def _recover_transactions(
        self,
        *,
        staging_descriptor: int | None = None,
        recovery_hmac_key: bytes | None = None,
        recovery_expected_key_id: str | None = None,
    ) -> None:
        """Idempotently finish staged transactions; journal is published last."""

        active_staging_descriptor = (
            self._open_directory_descriptor(".staging", create=True)
            if staging_descriptor is None
            else os.dup(staging_descriptor)
        )
        try:
            stage_names = sorted(os.listdir(active_staging_descriptor))
            if any(re.fullmatch(r"[0-9]{8}", name) is None for name in stage_names):
                raise IssuerCheckpointV2Error(
                    "checkpoint contains an unrecognized staged transaction"
                )
            for stage_name in stage_names:
                stage_descriptor = os.open(
                    stage_name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=active_staging_descriptor,
                )
                try:
                    manifest_content, _metadata = self._read_descriptor_file(
                        stage_descriptor,
                        "transaction.json",
                        label="checkpoint transaction manifest",
                    )
                    try:
                        transaction = strict_json_object(
                            manifest_content, "checkpoint transaction manifest"
                        )
                    except ValueError as exc:
                        raise IssuerCheckpointV2Error(str(exc)) from exc
                    if manifest_content != canonical_json_bytes(transaction):
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction manifest is not canonical JSON"
                        )
                    expected_transaction_fields = {
                        "schema_version",
                        "checkpoint_id",
                        "revision",
                        "prior_revision",
                        "prior_checkpoint_digest",
                        "resulting_checkpoint_digest",
                        "targets",
                        "transaction_sha256",
                    }
                    if set(transaction) != expected_transaction_fields:
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction manifest fields differ"
                        )
                    if transaction["schema_version"] != "issuer-checkpoint-transaction-v2":
                        raise IssuerCheckpointV2Error(
                            "unsupported checkpoint transaction schema"
                        )
                    revision = _positive_int(transaction["revision"], "transaction revision")
                    prior_revision = _nonnegative_int(
                        transaction["prior_revision"], "transaction prior_revision"
                    )
                    checkpoint_id = _identifier(
                        transaction["checkpoint_id"], "transaction checkpoint_id"
                    )
                    try:
                        require_sha256(
                            transaction["prior_checkpoint_digest"],
                            "transaction prior_checkpoint_digest",
                        )
                        require_sha256(
                            transaction["resulting_checkpoint_digest"],
                            "transaction resulting_checkpoint_digest",
                        )
                    except ValueError as exc:
                        raise IssuerCheckpointV2Error(str(exc)) from exc
                    if (prior_revision == 0) != (
                        transaction["prior_checkpoint_digest"] == ZERO_DIGEST
                    ):
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction initial predecessor binding differs"
                        )
                    if stage_name != f"{revision:08d}":
                        raise IssuerCheckpointV2Error(
                            "staged transaction revision differs from its directory"
                        )
                    if transaction["transaction_sha256"] != hash_json(
                        {
                            key: value
                            for key, value in transaction.items()
                            if key != "transaction_sha256"
                        }
                    ):
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction manifest digest mismatch"
                        )
                    targets = transaction["targets"]
                    if not isinstance(targets, list) or not targets:
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction targets are empty"
                        )
                    normalized_targets: list[dict[str, Any]] = []
                    seen_targets: set[str] = set()
                    for index, row in enumerate(targets):
                        if not isinstance(row, dict) or set(row) != {
                            "staged_name",
                            "target",
                            "sha256",
                            "size_bytes",
                            "is_commit_marker",
                        }:
                            raise IssuerCheckpointV2Error(
                                "checkpoint transaction target fields differ"
                            )
                        staged_name = row["staged_name"]
                        if staged_name != f"payload-{index:04d}.bin":
                            raise IssuerCheckpointV2Error(
                                "checkpoint transaction staged name is invalid"
                            )
                        target = _relative_path(row["target"], "transaction target")
                        if target in seen_targets:
                            raise IssuerCheckpointV2Error(
                                "checkpoint transaction contains duplicate targets"
                            )
                        seen_targets.add(target)
                        try:
                            require_sha256(row["sha256"], "transaction target sha256")
                        except ValueError as exc:
                            raise IssuerCheckpointV2Error(str(exc)) from exc
                        size = _nonnegative_int(
                            row["size_bytes"], "transaction target size_bytes"
                        )
                        if not isinstance(row["is_commit_marker"], bool):
                            raise IssuerCheckpointV2Error(
                                "transaction commit marker flag must be boolean"
                            )
                        normalized_targets.append(
                            {
                                "staged_name": staged_name,
                                "target": target,
                                "sha256": row["sha256"],
                                "size_bytes": size,
                                "is_commit_marker": row["is_commit_marker"],
                            }
                        )
                    targets = normalized_targets
                    commit_targets = [
                        row for row in targets if row.get("is_commit_marker") is True
                    ]
                    if len(commit_targets) != 1 or targets[-1] is not commit_targets[0]:
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction journal marker must be last"
                        )
                    commit = commit_targets[0]
                    if commit["target"] != f"journal/{revision:08d}.json":
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction commit target differs from revision"
                        )
                    stage_inventory = set(os.listdir(stage_descriptor))
                    allowed_stage_names = {
                        "transaction.json",
                        *(row["staged_name"] for row in targets),
                    }
                    if (
                        "transaction.json" not in stage_inventory
                        or not stage_inventory <= allowed_stage_names
                    ):
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction contains unlisted staged bytes"
                        )
                    preflight_payloads: dict[str, bytes] = {}
                    for row in targets:
                        staged_name = row["staged_name"]
                        staged_exists = staged_name in stage_inventory
                        staged_content = b""
                        staged_metadata: os.stat_result | None = None
                        if staged_exists:
                            staged_content, staged_metadata = (
                                self._read_descriptor_file(
                                    stage_descriptor,
                                    staged_name,
                                    label="staged checkpoint transaction payload",
                                    allow_link_count_two=True,
                                )
                            )
                        target_parts = PurePosixPath(row["target"]).parts
                        target_parent_relative = "/".join(target_parts[:-1])
                        target_exists = False
                        target_content = b""
                        target_metadata: os.stat_result | None = None
                        try:
                            target_parent = self._open_directory_descriptor(
                                target_parent_relative, create=False
                            )
                        except IssuerCheckpointV2Error as exc:
                            if not isinstance(exc.__cause__, FileNotFoundError):
                                raise
                        else:
                            try:
                                try:
                                    os.stat(
                                        target_parts[-1],
                                        dir_fd=target_parent,
                                        follow_symlinks=False,
                                    )
                                except FileNotFoundError:
                                    pass
                                else:
                                    target_exists = True
                                    target_content, target_metadata = (
                                        self._read_descriptor_file(
                                            target_parent,
                                            target_parts[-1],
                                            label="published checkpoint transaction target",
                                            allow_link_count_two=True,
                                        )
                                    )
                            finally:
                                os.close(target_parent)
                        expected = (row["sha256"], row["size_bytes"])
                        if staged_exists and (
                            sha256_bytes(staged_content), len(staged_content)
                        ) != expected:
                            raise IssuerCheckpointV2Error(
                                "staged transaction payload differs from manifest"
                            )
                        if target_exists and (
                            sha256_bytes(target_content), len(target_content)
                        ) != expected:
                            raise IssuerCheckpointV2Error(
                                "existing transaction target differs from staged manifest"
                            )
                        if not staged_exists and not target_exists:
                            raise IssuerCheckpointV2Error(
                                "transaction target and staged payload are both missing"
                            )
                        if staged_exists and target_exists:
                            assert staged_metadata is not None
                            assert target_metadata is not None
                            if (
                                staged_metadata.st_dev,
                                staged_metadata.st_ino,
                                staged_metadata.st_nlink,
                            ) != (
                                target_metadata.st_dev,
                                target_metadata.st_ino,
                                2,
                            ):
                                raise IssuerCheckpointV2Error(
                                    "staged and published transaction payload identities differ"
                                )
                        elif staged_exists:
                            assert staged_metadata is not None
                            if staged_metadata.st_nlink != 1:
                                raise IssuerCheckpointV2Error(
                                    "unpublished staged payload is unexpectedly hard-linked"
                                )
                        else:
                            assert target_metadata is not None
                            if target_metadata.st_nlink != 1:
                                raise IssuerCheckpointV2Error(
                                    "published transaction target retains an unsafe hard link"
                                )
                        preflight_payloads[staged_name] = (
                            staged_content if staged_exists else target_content
                        )
                    commit_content = preflight_payloads[commit["staged_name"]]
                    try:
                        next_payload = strict_json_object(
                            commit_content, "staged checkpoint state"
                        )
                    except ValueError as exc:
                        raise IssuerCheckpointV2Error(str(exc)) from exc
                    if commit_content != canonical_json_bytes(next_payload):
                        raise IssuerCheckpointV2Error(
                            "staged checkpoint journal marker is not canonical JSON"
                        )
                    next_state = _validate_state(next_payload)
                    if (
                        next_state["revision"] != revision
                        or next_state["checkpoint_id"] != checkpoint_id
                        or prior_revision != revision - 1
                        or next_state["prior_checkpoint_digest"]
                        != transaction["prior_checkpoint_digest"]
                        or next_state["checkpoint_digest"]
                        != transaction["resulting_checkpoint_digest"]
                        or sha256_bytes(commit_content) != commit["sha256"]
                        or len(commit_content) != commit["size_bytes"]
                    ):
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction manifest differs from resulting state"
                        )
                    current = self._current_journal_state_anchored()
                    previous_state: dict[str, Any] | None
                    if current is None:
                        if prior_revision != 0:
                            raise IssuerCheckpointV2Error(
                                "checkpoint transaction predecessor is missing"
                            )
                        previous_state = None
                        _validate_transition(None, next_state)
                    elif current["revision"] == revision:
                        if current["checkpoint_digest"] != next_state["checkpoint_digest"]:
                            raise IssuerCheckpointV2Error(
                                "committed transaction differs from staged state"
                            )
                        previous_state = (
                            None
                            if revision == 1
                            else self._journal_state_at_revision_anchored(
                                revision - 1
                            )
                        )
                        _validate_transition(previous_state, next_state)
                    else:
                        if (
                            current["revision"] != transaction["prior_revision"]
                            or current["checkpoint_digest"]
                            != transaction["prior_checkpoint_digest"]
                        ):
                            raise IssuerCheckpointV2Error(
                                "checkpoint transaction prior CAS does not match journal"
                            )
                        previous_state = current
                        _validate_transition(current, next_state)
                    self._validate_transaction_target_contract(
                        previous_state=previous_state,
                        next_state=next_state,
                        payload_by_target={
                            row["target"]: preflight_payloads[row["staged_name"]]
                            for row in targets
                        },
                        journal_target=commit["target"],
                        recovery_hmac_key=recovery_hmac_key,
                        recovery_expected_key_id=recovery_expected_key_id,
                    )
                    published_directories: dict[str, tuple[int, int, int]] = {}
                    commit_linked_now = False
                    for row in targets:
                        staged_name = row["staged_name"]
                        target = row["target"]
                        size = row["size_bytes"]
                        target_parts = PurePosixPath(target).parts
                        target_parent_relative = "/".join(target_parts[:-1])
                        if row["is_commit_marker"]:
                            for relative, expected_identity in published_directories.items():
                                self._verify_directory_identity(
                                    relative, expected_identity
                                )
                        target_parent_descriptor = self._open_directory_descriptor(
                            target_parent_relative, create=True
                        )
                        linked_now = False
                        try:
                            target_exists = True
                            try:
                                target_content, target_metadata = self._read_descriptor_file(
                                    target_parent_descriptor,
                                    target_parts[-1],
                                    label="checkpoint transaction target",
                                    allow_link_count_two=True,
                                )
                            except IssuerCheckpointV2Error as exc:
                                if isinstance(exc.__cause__, FileNotFoundError):
                                    target_exists = False
                                    target_content = b""
                                    target_metadata = None
                                else:
                                    # Distinguish a genuinely missing target using stat.
                                    try:
                                        os.stat(
                                            target_parts[-1],
                                            dir_fd=target_parent_descriptor,
                                            follow_symlinks=False,
                                        )
                                    except FileNotFoundError:
                                        target_exists = False
                                        target_content = b""
                                        target_metadata = None
                                    else:
                                        raise
                            staged_exists = True
                            try:
                                staged_content, staged_metadata = self._read_descriptor_file(
                                    stage_descriptor,
                                    staged_name,
                                    label="staged checkpoint transaction payload",
                                    allow_link_count_two=True,
                                )
                            except IssuerCheckpointV2Error:
                                try:
                                    os.stat(
                                        staged_name,
                                        dir_fd=stage_descriptor,
                                        follow_symlinks=False,
                                    )
                                except FileNotFoundError:
                                    staged_exists = False
                                    staged_content = b""
                                    staged_metadata = None
                                else:
                                    raise
                            expected = (row["sha256"], size)
                            if target_exists and (
                                sha256_bytes(target_content), len(target_content)
                            ) != expected:
                                raise IssuerCheckpointV2Error(
                                    "existing transaction target differs from staged manifest"
                                )
                            if staged_exists and (
                                sha256_bytes(staged_content), len(staged_content)
                            ) != expected:
                                raise IssuerCheckpointV2Error(
                                    "staged transaction payload differs from manifest"
                                )
                            if not target_exists:
                                if not staged_exists:
                                    raise IssuerCheckpointV2Error(
                                        "transaction target and staged payload are both missing"
                                    )
                                try:
                                    os.link(
                                        staged_name,
                                        target_parts[-1],
                                        src_dir_fd=stage_descriptor,
                                        dst_dir_fd=target_parent_descriptor,
                                        follow_symlinks=False,
                                    )
                                    linked_now = True
                                except OSError as exc:
                                    raise IssuerCheckpointV2Error(
                                        "checkpoint transaction publish was interrupted"
                                    ) from exc
                            if staged_exists:
                                try:
                                    # This is required even when the target was
                                    # linked by an earlier process that crashed
                                    # before its directory fsync completed.
                                    os.fsync(target_parent_descriptor)
                                except OSError as exc:
                                    raise IssuerCheckpointV2Error(
                                        "checkpoint transaction target fsync was interrupted"
                                    ) from exc
                            try:
                                self._verify_directory_descriptor(
                                    target_parent_relative,
                                    target_parent_descriptor,
                                )
                            except IssuerCheckpointV2Error:
                                if linked_now:
                                    try:
                                        os.unlink(
                                            target_parts[-1],
                                            dir_fd=target_parent_descriptor,
                                        )
                                        os.fsync(target_parent_descriptor)
                                    except OSError as cleanup_exc:
                                        raise IssuerCheckpointV2Error(
                                            "checkpoint target parent changed and linked-byte cleanup failed"
                                        ) from cleanup_exc
                                raise
                            published_directories[target_parent_relative] = (
                                self._directory_descriptor_identity(
                                    target_parent_descriptor
                                )
                            )
                            if row["is_commit_marker"]:
                                commit_linked_now = linked_now
                        finally:
                            os.close(target_parent_descriptor)
                    try:
                        for relative, expected_identity in published_directories.items():
                            self._verify_directory_identity(
                                relative, expected_identity
                            )
                        for row in targets:
                            target_parts = PurePosixPath(row["target"]).parts
                            parent_relative = "/".join(target_parts[:-1])
                            parent_descriptor = self._open_directory_descriptor(
                                parent_relative, create=False
                            )
                            try:
                                content, _metadata = self._read_descriptor_file(
                                    parent_descriptor,
                                    target_parts[-1],
                                    label="published checkpoint transaction target",
                                    allow_link_count_two=True,
                                )
                                if (
                                    sha256_bytes(content), len(content)
                                ) != (row["sha256"], row["size_bytes"]):
                                    raise IssuerCheckpointV2Error(
                                        "published transaction target changed before commit"
                                    )
                                self._verify_directory_descriptor(
                                    parent_relative, parent_descriptor
                                )
                            finally:
                                os.close(parent_descriptor)
                    except IssuerCheckpointV2Error:
                        if commit_linked_now:
                            commit_parts = PurePosixPath(commit["target"]).parts
                            commit_parent_relative = "/".join(commit_parts[:-1])
                            commit_parent = self._open_directory_descriptor(
                                commit_parent_relative, create=False
                            )
                            try:
                                os.unlink(commit_parts[-1], dir_fd=commit_parent)
                                os.fsync(commit_parent)
                            except OSError as cleanup_exc:
                                raise IssuerCheckpointV2Error(
                                    "transaction validation failed and journal rollback failed"
                                ) from cleanup_exc
                            finally:
                                os.close(commit_parent)
                        raise
                    for row in targets:
                        staged_name = row["staged_name"]
                        try:
                            os.stat(
                                staged_name,
                                dir_fd=stage_descriptor,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            continue
                        try:
                            os.unlink(staged_name, dir_fd=stage_descriptor)
                            os.fsync(stage_descriptor)
                        except OSError as exc:
                            raise IssuerCheckpointV2Error(
                                "checkpoint transaction stage cleanup was interrupted"
                            ) from exc
                    for relative, expected_identity in published_directories.items():
                        self._verify_directory_identity(relative, expected_identity)
                    remaining = sorted(os.listdir(stage_descriptor))
                    if remaining != ["transaction.json"]:
                        raise IssuerCheckpointV2Error(
                            "checkpoint transaction contains unlisted staged bytes"
                        )
                    committed_stage_identity = self._directory_descriptor_identity(
                        stage_descriptor
                    )
                finally:
                    os.close(stage_descriptor)
                self._retire_committed_stage(
                    active_staging_descriptor,
                    stage_name=stage_name,
                    transaction_sha256=transaction["transaction_sha256"],
                    expected_stage_identity=committed_stage_identity,
                )
        finally:
            os.close(active_staging_descriptor)
        self._check_root()

    def _retire_committed_stage(
        self,
        staging_descriptor: int,
        *,
        stage_name: str,
        transaction_sha256: str,
        expected_stage_identity: tuple[int, int, int],
    ) -> None:
        """Atomically remove a committed stage from the authoritative root.

        The stage still contains its transaction manifest.  Renaming the whole
        directory out of ``.staging`` is the cleanup commit: a crash either
        leaves a recoverable in-root transaction or an irrelevant parent-level
        manifest orphan, never an empty numeric stage that blocks recovery.
        """

        self._check_root()
        parent = require_real_directory(
            self.root.parent, field="checkpoint transaction parent"
        )
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_descriptor = os.open(parent, flags)
        cleanup_name = (
            f".{self.root.name}.committed-{stage_name}-"
            f"{transaction_sha256[:12]}-{os.urandom(8).hex()}"
        )
        committed_descriptor = -1
        try:
            committed_descriptor = os.open(
                stage_name, flags, dir_fd=staging_descriptor
            )
            committed_identity = self._directory_descriptor_identity(
                committed_descriptor
            )
            if committed_identity != expected_stage_identity:
                raise IssuerCheckpointV2Error(
                    "committed transaction stage identity changed before retirement"
                )
            os.rename(
                stage_name,
                cleanup_name,
                src_dir_fd=staging_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            moved_entry = os.stat(
                cleanup_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                moved_entry.st_dev,
                moved_entry.st_ino,
                moved_entry.st_mode,
            ) != expected_stage_identity:
                try:
                    os.stat(
                        stage_name,
                        dir_fd=staging_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    try:
                        os.rename(
                            cleanup_name,
                            stage_name,
                            src_dir_fd=parent_descriptor,
                            dst_dir_fd=staging_descriptor,
                        )
                        os.fsync(parent_descriptor)
                        os.fsync(staging_descriptor)
                    except OSError as exc:
                        raise IssuerCheckpointV2Error(
                            "swapped committed stage could not be restored safely"
                        ) from exc
                else:
                    raise IssuerCheckpointV2Error(
                        "swapped committed stage destination is occupied"
                    )
                raise IssuerCheckpointV2Error(
                    "committed transaction stage changed during retirement"
                )
            os.fsync(staging_descriptor)
            os.fsync(parent_descriptor)
            self._check_root()
            # Best-effort deletion is outside the authoritative root.  At this
            # point the only retained byte is the transaction manifest.
            try:
                if sorted(os.listdir(committed_descriptor)) != ["transaction.json"]:
                    return
                os.unlink("transaction.json", dir_fd=committed_descriptor)
                os.fsync(committed_descriptor)
                try:
                    current_entry = os.stat(
                        cleanup_name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    pass
                else:
                    if (
                        current_entry.st_dev,
                        current_entry.st_ino,
                        current_entry.st_mode,
                    ) == committed_identity:
                        os.rmdir(cleanup_name, dir_fd=parent_descriptor)
                        os.fsync(parent_descriptor)
            except OSError:
                # A parent-level cleanup orphan cannot affect load/recovery.
                pass
        finally:
            if committed_descriptor >= 0:
                os.close(committed_descriptor)
            os.close(parent_descriptor)

    def _snapshot(self) -> dict[str, bytes]:
        self._check_root()
        first = self._anchored_snapshot_once()
        second = self._anchored_snapshot_once()
        first_inventory = [
            (path, sha256_bytes(content), len(content))
            for path, content in first.items()
        ]
        second_inventory = [
            (path, sha256_bytes(content), len(content))
            for path, content in second.items()
        ]
        if first_inventory != second_inventory:
            raise IssuerCheckpointV2Error(
                "issuer checkpoint bundle changed while being snapshotted"
            )
        self._check_root()
        return second

    def _anchored_snapshot_once(
        self,
        *,
        skip_staging: bool = False,
        allow_hardlinked_paths: frozenset[str] = frozenset(),
    ) -> dict[str, bytes]:
        """Read the tree only through descriptors anchored at construction."""

        rows: dict[str, bytes] = {}
        total_entries = 0
        total_bytes = 0
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )

        def identity(metadata: os.stat_result) -> tuple[int, ...]:
            return (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_nlink,
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            )

        def is_reparse(metadata: os.stat_result) -> bool:
            attributes = getattr(metadata, "st_file_attributes", 0)
            marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            return bool(attributes & marker)

        def visit(
            directory_descriptor: int,
            relative_parts: tuple[str, ...],
            depth: int,
        ) -> None:
            nonlocal total_entries, total_bytes
            if depth > 16:
                raise IssuerCheckpointV2Error(
                    "issuer checkpoint bundle exceeds maximum depth"
                )
            before_directory = os.fstat(directory_descriptor)
            if not stat.S_ISDIR(before_directory.st_mode) or is_reparse(
                before_directory
            ):
                raise IssuerCheckpointV2Error(
                    "issuer checkpoint directory identity is unsafe"
                )
            names = sorted(os.listdir(directory_descriptor))
            for name in names:
                if not relative_parts and skip_staging and name == ".staging":
                    continue
                total_entries += 1
                if total_entries > 1024:
                    raise IssuerCheckpointV2Error(
                        "issuer checkpoint bundle exceeds 1024 entries"
                    )
                _relative_path(name, "checkpoint path component")
                relative = (*relative_parts, name)
                path_text = "/".join(relative)
                before = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                if stat.S_ISLNK(before.st_mode) or is_reparse(before):
                    raise IssuerCheckpointV2Error(
                        "issuer checkpoint bundle contains a symlink or reparse point"
                    )
                if stat.S_ISDIR(before.st_mode):
                    child_descriptor = os.open(
                        name, directory_flags, dir_fd=directory_descriptor
                    )
                    try:
                        opened = os.fstat(child_descriptor)
                        if (
                            identity(before)[:3] != identity(opened)[:3]
                            or not stat.S_ISDIR(opened.st_mode)
                        ):
                            raise IssuerCheckpointV2Error(
                                "issuer checkpoint directory changed during traversal"
                            )
                        visit(child_descriptor, relative, depth + 1)
                        after_opened = os.fstat(child_descriptor)
                        after_entry = os.stat(
                            name,
                            dir_fd=directory_descriptor,
                            follow_symlinks=False,
                        )
                        if (
                            identity(after_opened)[:3] != identity(after_entry)[:3]
                            or stat.S_ISLNK(after_entry.st_mode)
                            or is_reparse(after_entry)
                        ):
                            raise IssuerCheckpointV2Error(
                                "issuer checkpoint directory changed during traversal"
                            )
                    finally:
                        os.close(child_descriptor)
                    continue
                allowed_links = (
                    {1, 2} if path_text in allow_hardlinked_paths else {1}
                )
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_nlink not in allowed_links
                ):
                    raise IssuerCheckpointV2Error(
                        "issuer checkpoint bundle must contain only non-hard-linked regular files"
                    )
                if len(rows) >= MAX_CHECKPOINT_FILES:
                    raise IssuerCheckpointV2Error(
                        f"issuer checkpoint bundle exceeds {MAX_CHECKPOINT_FILES} files"
                    )
                content, opened = self._read_descriptor_file(
                    directory_descriptor,
                    name,
                    label=f"issuer checkpoint file {path_text}",
                    max_bytes=64 * 1024 * 1024,
                    allow_link_count_two=path_text in allow_hardlinked_paths,
                )
                after_entry = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                if identity(before) != identity(opened) or identity(opened) != identity(
                    after_entry
                ):
                    raise IssuerCheckpointV2Error(
                        "issuer checkpoint file changed during traversal"
                    )
                total_bytes += len(content)
                if total_bytes > MAX_CHECKPOINT_BYTES:
                    raise IssuerCheckpointV2Error(
                        f"issuer checkpoint bundle exceeds {MAX_CHECKPOINT_BYTES} bytes"
                    )
                rows[path_text] = content
            after_directory = os.fstat(directory_descriptor)
            if identity(before_directory) != identity(after_directory):
                raise IssuerCheckpointV2Error(
                    "issuer checkpoint directory changed during traversal"
                )

        root_descriptor = os.dup(self._root_descriptor)
        try:
            visit(root_descriptor, (), 0)
        except OSError as exc:
            raise IssuerCheckpointV2Error(
                "issuer checkpoint bundle cannot be traversed safely"
            ) from exc
        finally:
            os.close(root_descriptor)
        return dict(sorted(rows.items()))

    def _validated_receipts(
        self,
        files: Mapping[str, bytes],
        state: Mapping[str, Any],
        selected: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], set[str]]:
        receipts: list[dict[str, Any]] = []
        expected_paths: set[str] = set()
        previous_digest: str | None = None
        checkpoint_raw_file_count = 0
        checkpoint_raw_size = 0
        source_plan = selected["source_plan"]
        for ordinal, expected_digest in enumerate(
            state["terminal_receipt_sha256s"], start=1
        ):
            source = source_plan[ordinal - 1]
            package = f"receipts/{ordinal:03d}-{source['source_id']}"
            receipt_path = f"{package}/receipt.json"
            manifest_path = f"{package}/manifest.json"
            if receipt_path not in files or manifest_path not in files:
                raise IssuerCheckpointV2Error("terminal receipt package is incomplete")
            expected_paths.update({receipt_path, manifest_path})
            try:
                receipt = _exact(
                    strict_json_object(files[receipt_path], f"source receipt {ordinal}"),
                    _RECEIPT_FIELDS,
                    f"source receipt {ordinal}",
                )
                manifest = _exact(
                    strict_json_object(files[manifest_path], f"source manifest {ordinal}"),
                    _MANIFEST_FIELDS,
                    f"source manifest {ordinal}",
                )
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            if files[receipt_path] != canonical_json_bytes(receipt):
                raise IssuerCheckpointV2Error("source receipt is not canonical JSON")
            if files[manifest_path] != canonical_json_bytes(manifest):
                raise IssuerCheckpointV2Error("source manifest is not canonical JSON")
            bindings = {
                "checkpoint_id": state["checkpoint_id"],
                "security_code": state["security_code"],
                "source_ordinal": ordinal,
                "wave_ordinal": source["wave_ordinal"],
                "wave_id": source["wave_id"],
                "source_id": source["source_id"],
            }
            if any(manifest.get(field) != value for field, value in bindings.items()):
                raise IssuerCheckpointV2Error("source manifest differs from frozen plan")
            if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
                raise IssuerCheckpointV2Error("unsupported source manifest schema")
            _positive_int(manifest.get("source_ordinal"), "manifest source_ordinal")
            _positive_int(manifest.get("wave_ordinal"), "manifest wave_ordinal")
            artifacts = manifest.get("artifacts")
            if not isinstance(artifacts, list):
                raise IssuerCheckpointV2Error("source manifest artifacts must be a list")
            if len(artifacts) > MAX_RAW_FILES_PER_SOURCE:
                raise IssuerCheckpointV2Error(
                    "source manifest exceeds its raw artifact count budget"
                )
            artifact_paths: list[str] = []
            raw_size = 0
            for index, raw_artifact in enumerate(artifacts):
                artifact = _exact(
                    raw_artifact,
                    _ARTIFACT_FIELDS,
                    f"source manifest artifact {index}",
                )
                relative = _relative_path(artifact["path"], "raw artifact path")
                if not relative.startswith("raw/"):
                    raise IssuerCheckpointV2Error("raw artifact must remain below raw/")
                global_path = f"{package}/{relative}"
                if global_path not in files:
                    raise IssuerCheckpointV2Error("source manifest raw artifact is missing")
                expected_paths.add(global_path)
                content = files[global_path]
                _nonnegative_int(
                    artifact.get("size_bytes"), "manifest artifact size_bytes"
                )
                if len(content) > MAX_RAW_FILE_BYTES:
                    raise IssuerCheckpointV2Error(
                        "source manifest raw artifact exceeds its byte budget"
                    )
                if (
                    artifact["sha256"] != sha256_bytes(content)
                    or artifact["size_bytes"] != len(content)
                ):
                    raise IssuerCheckpointV2Error("raw artifact digest or size mismatch")
                artifact_paths.append(relative)
                raw_size += len(content)
            if raw_size > MAX_RAW_BYTES_PER_SOURCE:
                raise IssuerCheckpointV2Error(
                    "source manifest exceeds its aggregate raw byte budget"
                )
            checkpoint_raw_file_count += len(artifacts)
            checkpoint_raw_size += raw_size
            if checkpoint_raw_file_count > MAX_CHECKPOINT_RAW_FILES:
                raise IssuerCheckpointV2Error(
                    "checkpoint exceeds its raw artifact count budget"
                )
            if checkpoint_raw_size > MAX_CHECKPOINT_RAW_BYTES:
                raise IssuerCheckpointV2Error(
                    "checkpoint exceeds its aggregate raw byte budget"
                )
            if artifact_paths != sorted(set(artifact_paths)):
                raise IssuerCheckpointV2Error("source manifest paths are not sorted and unique")
            if manifest["manifest_sha256"] != _manifest_digest(manifest):
                raise IssuerCheckpointV2Error("source manifest digest mismatch")
            expected_receipt = {
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "receipt_id": f"{state['checkpoint_id']}:{ordinal:03d}",
                "checkpoint_id": state["checkpoint_id"],
                "run_id": state["run_id"],
                "plan_sha256": state["plan_sha256"],
                "identity_sha256": state["identity_sha256"],
                "issuer_id": state["issuer_id"],
                "security_code": state["security_code"],
                "source_ordinal": ordinal,
                "wave_ordinal": source["wave_ordinal"],
                "wave_id": source["wave_id"],
                "source_id": source["source_id"],
                "artifact_count": len(artifacts),
                "artifact_manifest_path": manifest_path,
                "artifact_manifest_sha256": manifest["manifest_sha256"],
                "raw_size_bytes": raw_size,
                "previous_terminal_receipt_sha256": previous_digest,
            }
            if any(receipt.get(field) != value for field, value in expected_receipt.items()):
                raise IssuerCheckpointV2Error("source receipt differs from its frozen binding")
            _positive_int(receipt.get("source_ordinal"), "receipt source_ordinal")
            _positive_int(receipt.get("wave_ordinal"), "receipt wave_ordinal")
            _nonnegative_int(receipt.get("artifact_count"), "receipt artifact_count")
            _nonnegative_int(receipt.get("raw_size_bytes"), "receipt raw_size_bytes")
            if receipt.get("terminal_status") not in TERMINAL_SOURCE_STATUSES:
                raise IssuerCheckpointV2Error("source receipt terminal status is invalid")
            attempted = _instant(receipt.get("attempted_at"), "receipt attempted_at")
            completed = _instant(receipt.get("completed_at"), "receipt completed_at")
            if completed < attempted:
                raise IssuerCheckpointV2Error("source receipt completed before attempted_at")
            observations = _nonnegative_int(
                receipt.get("observation_count"), "observation_count"
            )
            if receipt["terminal_status"] != "COLLECTED" and observations:
                raise IssuerCheckpointV2Error(
                    "only COLLECTED receipts may report observations"
                )
            if receipt["terminal_status"] in _NON_BLOCKING_TERMINAL_STATUSES and not artifacts:
                raise IssuerCheckpointV2Error(
                    "non-blocking terminal receipt must retain a generated raw fixture"
                )
            limitation = receipt.get("limitation")
            if (
                not isinstance(limitation, str)
                or limitation != limitation.strip()
                or len(limitation) > 2000
            ):
                raise IssuerCheckpointV2Error("source receipt limitation is invalid")
            digest = _receipt_digest(receipt)
            if receipt.get("receipt_sha256") != digest or digest != expected_digest:
                raise IssuerCheckpointV2Error("source receipt digest mismatch")
            previous_digest = digest
            receipts.append(receipt)
        return receipts, expected_paths

    def _validated_reconciliation(
        self,
        payload: Mapping[str, Any],
        *,
        state_before: Mapping[str, Any],
        receipts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        row = _exact(payload, _RECONCILIATION_FIELDS, "checkpoint reconciliation")
        expected = {
            "schema_version": RECONCILIATION_SCHEMA_VERSION,
            "checkpoint_id": state_before["checkpoint_id"],
            "run_id": state_before["run_id"],
            "issuer_id": state_before["issuer_id"],
            "security_code": state_before["security_code"],
            "plan_sha256": state_before["plan_sha256"],
            "issuer_universe_sha256": state_before["issuer_universe_sha256"],
            "identity_sha256": state_before["identity_sha256"],
            "source_plan_sha256": state_before["source_plan_sha256"],
            "evidence_class": "SYNTHETIC_FIXTURE",
            "status": "EXACT_29_SOURCES_7_WAVES",
            "expected_source_count": EXPECTED_SOURCE_COUNT,
            "terminal_source_count": EXPECTED_SOURCE_COUNT,
            "expected_wave_count": EXPECTED_WAVE_COUNT,
            "reconciled_wave_count": EXPECTED_WAVE_COUNT,
            "retained_manifest_count": EXPECTED_SOURCE_COUNT,
            "reopened_manifest_count": EXPECTED_SOURCE_COUNT,
            "reconciled_checkpoint_digest": state_before["checkpoint_digest"],
            "claim_boundaries": _claim_boundaries(),
        }
        if any(row.get(field) != value for field, value in expected.items()):
            raise IssuerCheckpointV2Error("checkpoint reconciliation binding is invalid")
        reconciled_instant = _instant(row.get("reconciled_at"), "reconciled_at")
        latest_evidence_instant = max(
            [
                _instant(state_before["updated_at"], "pre-reconciliation updated_at"),
                *(
                    _instant(receipt["completed_at"], "receipt completed_at")
                    for receipt in receipts
                ),
            ]
        )
        if reconciled_instant < latest_evidence_instant:
            raise IssuerCheckpointV2Error(
                "reconciled_at precedes retained terminal evidence"
            )
        inventory = row.get("receipt_inventory")
        if not isinstance(inventory, list) or len(inventory) != EXPECTED_SOURCE_COUNT:
            raise IssuerCheckpointV2Error("reconciliation must inventory exactly 29 receipts")
        for ordinal, (item, receipt) in enumerate(zip(inventory, receipts), start=1):
            entry = _exact(
                item,
                _RECONCILIATION_RECEIPT_FIELDS,
                f"reconciliation receipt {ordinal}",
            )
            expected_entry = {
                "source_ordinal": ordinal,
                "wave_ordinal": receipt["wave_ordinal"],
                "wave_id": receipt["wave_id"],
                "source_id": receipt["source_id"],
                "terminal_status": receipt["terminal_status"],
                "receipt_sha256": receipt["receipt_sha256"],
                "manifest_sha256": receipt["artifact_manifest_sha256"],
            }
            if entry != expected_entry:
                raise IssuerCheckpointV2Error("reconciliation receipt inventory changed")
        waves = row.get("wave_reconciliation")
        if not isinstance(waves, list) or len(waves) != EXPECTED_WAVE_COUNT:
            raise IssuerCheckpointV2Error("reconciliation must contain all seven waves")
        cursor = 1
        for wave_ordinal, (wave, source_ids) in enumerate(
            zip(waves, SOURCE_WAVE_SOURCES), start=1
        ):
            entry = _exact(
                wave,
                _WAVE_RECONCILIATION_FIELDS,
                f"wave reconciliation {wave_ordinal}",
            )
            ordinals = list(range(cursor, cursor + len(source_ids)))
            expected_wave = {
                "wave_ordinal": wave_ordinal,
                "wave_id": SOURCE_WAVE_IDS[wave_ordinal - 1],
                "expected_source_ordinals": ordinals,
                "terminal_source_ordinals": ordinals,
                "status": "EXACT",
            }
            if entry != expected_wave:
                raise IssuerCheckpointV2Error("reconciliation wave order or denominator changed")
            cursor += len(source_ids)
        status_counts: dict[str, int] = {}
        for receipt in receipts:
            status_counts[receipt["terminal_status"]] = (
                status_counts.get(receipt["terminal_status"], 0) + 1
            )
        if row.get("terminal_status_counts") != dict(sorted(status_counts.items())):
            raise IssuerCheckpointV2Error("reconciliation terminal status counts changed")
        artifact_count = sum(receipt["artifact_count"] for receipt in receipts)
        raw_size = sum(receipt["raw_size_bytes"] for receipt in receipts)
        if (
            row.get("raw_artifact_count") != artifact_count
            or row.get("reopened_raw_artifact_count") != artifact_count
            or row.get("raw_size_bytes") != raw_size
        ):
            raise IssuerCheckpointV2Error("reconciliation raw artifact counts changed")
        if row.get("reconciliation_sha256") != _reconciliation_digest(row):
            raise IssuerCheckpointV2Error("reconciliation digest mismatch")
        return row

    def _load(
        self,
        *,
        recovery_hmac_key: bytes | None = None,
        recovery_expected_key_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any], list[dict[str, Any]]]:
        self._recover_transactions(
            recovery_hmac_key=recovery_hmac_key,
            recovery_expected_key_id=recovery_expected_key_id,
        )
        files = self._snapshot()
        required_bindings = {
            ".checkpoint-v2.guard",
            "bindings/issuer-universe.json",
            "bindings/collection-plan.json",
        }
        if not required_bindings <= set(files):
            raise IssuerCheckpointV2Error("checkpoint bindings or guard are missing")
        if files[".checkpoint-v2.guard"] != b"":
            raise IssuerCheckpointV2Error("checkpoint guard bytes changed")
        try:
            plan = strict_json_object(
                files["bindings/collection-plan.json"], "bound collection plan"
            )
            universe = strict_json_object(
                files["bindings/issuer-universe.json"], "bound issuer universe"
            )
            validate_issuer_sequential_collection_plan(
                plan,
                issuer_universe=universe,
                project_root=self.project_root,
            )
        except (ValueError, IssuerSequentialCollectionError) as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
        journal_paths = sorted(
            path for path in files if re.fullmatch(r"journal/[0-9]{8}\.json", path)
        )
        if not journal_paths:
            raise IssuerCheckpointV2Error("checkpoint journal is empty")
        states: list[dict[str, Any]] = []
        previous: dict[str, Any] | None = None
        for ordinal, path in enumerate(journal_paths, start=1):
            if path != f"journal/{ordinal:08d}.json":
                raise IssuerCheckpointV2Error("checkpoint journal revisions are not contiguous")
            try:
                payload = strict_json_object(files[path], f"checkpoint journal {ordinal}")
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            if files[path] != canonical_json_bytes(payload):
                raise IssuerCheckpointV2Error("checkpoint journal entry is not canonical JSON")
            state = _validate_state(payload)
            _validate_transition(previous, state)
            states.append(state)
            previous = state
        assert previous is not None
        state = previous
        if state["revision"] != len(states):
            raise IssuerCheckpointV2Error("checkpoint revision differs from journal length")
        if state["plan_content_sha256"] != sha256_bytes(
            files["bindings/collection-plan.json"]
        ) or state["universe_content_sha256"] != sha256_bytes(
            files["bindings/issuer-universe.json"]
        ):
            raise IssuerCheckpointV2Error("checkpoint bound authority bytes changed")
        if (
            state["plan_sha256"] != plan.get("plan_sha256")
            or state["issuer_universe_sha256"] != plan.get("issuer_universe_sha256")
        ):
            raise IssuerCheckpointV2Error("checkpoint state differs from bound plan")
        selected_rows = [
            row for row in plan["queue"] if row.get("security_code") == state["security_code"]
        ]
        if len(selected_rows) != 1:
            raise IssuerCheckpointV2Error("bound plan no longer selects exactly one security")
        selected = selected_rows[0]
        if (
            selected.get("ordinal") != state["selected_queue_ordinal"]
            or selected.get("issuer_id") != state["issuer_id"]
            or selected.get("identity_sha256") != state["identity_sha256"]
            or hash_json(selected.get("source_plan")) != state["source_plan_sha256"]
        ):
            raise IssuerCheckpointV2Error("checkpoint selected security binding changed")
        receipts, receipt_paths = self._validated_receipts(files, state, selected)
        source_starts: dict[int, dict[str, Any]] = {}
        source_terminals: dict[int, dict[str, Any]] = {}
        for journal_state in states:
            if journal_state["event_type"] == "SOURCE_STARTED":
                active = journal_state["active_source_ordinal"]
                if active is None:
                    raise IssuerCheckpointV2Error(
                        "source start journal lacks an active source ordinal"
                    )
                source_starts[active] = journal_state
            elif journal_state["event_type"] == "SOURCE_TERMINAL":
                ordinal = journal_state["terminal_receipt_count"]
                if ordinal in source_terminals:
                    raise IssuerCheckpointV2Error(
                        "journal contains duplicate terminal source ordinals"
                    )
                source_terminals[ordinal] = journal_state
        if set(source_terminals) != set(range(1, len(receipts) + 1)):
            raise IssuerCheckpointV2Error(
                "journal terminal events differ from retained receipts"
            )
        for receipt in receipts:
            ordinal = receipt["source_ordinal"]
            started = source_starts.get(ordinal)
            terminal = source_terminals.get(ordinal)
            if started is None or terminal is None:
                raise IssuerCheckpointV2Error(
                    "receipt lacks its source-start or source-terminal journal event"
                )
            if _instant(receipt["attempted_at"], "receipt attempted_at") < _instant(
                started["updated_at"], "source-start updated_at"
            ) or _instant(receipt["completed_at"], "receipt completed_at") > _instant(
                terminal["updated_at"], "source-terminal updated_at"
            ):
                raise IssuerCheckpointV2Error(
                    "receipt timestamps fall outside their journal event interval"
                )
        expected_paths = set(required_bindings) | set(journal_paths) | receipt_paths
        reconciliation_path = "reconciliation.json"
        reconciliation: dict[str, Any] | None = None
        if state["reconciliation_sha256"] is not None:
            if reconciliation_path not in files:
                raise IssuerCheckpointV2Error("checkpoint reconciliation file is missing")
            expected_paths.add(reconciliation_path)
            before_index = next(
                index
                for index, item in enumerate(states)
                if item["event_type"] == "RECONCILED"
            )
            if before_index == 0:
                raise IssuerCheckpointV2Error("reconciliation lacks a prior checkpoint")
            before = states[before_index - 1]
            try:
                payload = strict_json_object(
                    files[reconciliation_path], "checkpoint reconciliation"
                )
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            if files[reconciliation_path] != canonical_json_bytes(payload):
                raise IssuerCheckpointV2Error("reconciliation is not canonical JSON")
            reconciliation = self._validated_reconciliation(
                payload, state_before=before, receipts=receipts
            )
            reconciled_state = states[before_index]
            if reconciled_state["updated_at"] != reconciliation["reconciled_at"]:
                raise IssuerCheckpointV2Error(
                    "reconciliation timestamp differs from its journal event"
                )
            if reconciliation["reconciliation_sha256"] != state["reconciliation_sha256"]:
                raise IssuerCheckpointV2Error("state reconciliation digest mismatch")
        if state["terminal_seal_sha256"] is not None:
            expected_paths.add("terminal-seal.json")
            if "terminal-seal.json" not in files:
                raise IssuerCheckpointV2Error("terminal seal file is missing")
            if sha256_bytes(files["terminal-seal.json"]) != state["terminal_seal_sha256"]:
                raise IssuerCheckpointV2Error("terminal seal content digest mismatch")
        if set(files) != expected_paths:
            extras = sorted(set(files) - expected_paths)
            missing = sorted(expected_paths - set(files))
            raise IssuerCheckpointV2Error(
                f"checkpoint bundle contains unlisted or missing bytes: extras={extras} missing={missing}"
            )
        return state, files, plan, receipts

    def load(self) -> dict[str, Any]:
        with _locked_guard(self._root_descriptor):
            state, _files, _plan, _receipts = self._load()
            return dict(state)

    def _cas(
        self,
        state: Mapping[str, Any],
        *,
        expected_generation: int,
        expected_revision: int,
        expected_fencing_token: str,
        expected_owner_run_id: str,
        expected_prior_checkpoint_digest: str,
    ) -> None:
        if state["generation"] != expected_generation:
            raise IssuerCheckpointV2CasError("checkpoint generation CAS mismatch")
        if state["revision"] != expected_revision:
            raise IssuerCheckpointV2CasError("checkpoint revision CAS mismatch")
        if state["owner_run_id"] != expected_owner_run_id:
            raise IssuerCheckpointV2CasError("checkpoint owner CAS mismatch")
        if state["checkpoint_digest"] != expected_prior_checkpoint_digest:
            raise IssuerCheckpointV2CasError("checkpoint prior digest CAS mismatch")
        if state["fencing_token"] != expected_fencing_token:
            raise IssuerCheckpointV2FencingError("checkpoint fencing token is stale")

    def _append_state(
        self,
        state: dict[str, Any],
        *,
        previous: Mapping[str, Any],
        payloads: Mapping[str, bytes] | None = None,
        recovery_hmac_key: bytes | None = None,
        recovery_expected_key_id: str | None = None,
    ) -> dict[str, Any]:
        self._check_root()
        state["checkpoint_digest"] = _state_digest(state)
        validated = _validate_state(state)
        _validate_transition(dict(previous), validated)
        self._stage_transaction(
            previous=previous,
            next_state=validated,
            payloads={} if payloads is None else payloads,
            recovery_hmac_key=recovery_hmac_key,
            recovery_expected_key_id=recovery_expected_key_id,
        )
        return validated

    def _next_state(
        self,
        previous: Mapping[str, Any],
        *,
        event_type: str,
        updated_at: str | datetime,
    ) -> dict[str, Any]:
        row = dict(previous)
        row["event_type"] = event_type
        row["revision"] = previous["revision"] + 1
        row["prior_checkpoint_digest"] = previous["checkpoint_digest"]
        row["updated_at"] = _timestamp(updated_at, "updated_at")
        row["checkpoint_digest"] = ""
        return row

    def begin_next_source(
        self,
        *,
        security_code: str,
        source_ordinal: int,
        source_id: str,
        wave_ordinal: int,
        wave_id: str,
        updated_at: str | datetime,
        expected_generation: int,
        expected_revision: int,
        expected_fencing_token: str,
        expected_owner_run_id: str,
        expected_prior_checkpoint_digest: str,
    ) -> dict[str, Any]:
        source_ordinal = _positive_int(source_ordinal, "source_ordinal")
        wave_ordinal = _positive_int(wave_ordinal, "wave_ordinal")
        with _locked_guard(self._root_descriptor):
            state, _files, plan, _receipts = self._load()
            self._cas(
                state,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                expected_fencing_token=expected_fencing_token,
                expected_owner_run_id=expected_owner_run_id,
                expected_prior_checkpoint_digest=expected_prior_checkpoint_digest,
            )
            if state["status"] != "RUNNING" or state["active_source_ordinal"] is not None:
                raise IssuerCheckpointV2Error("checkpoint cannot begin another active source")
            if _security_code(security_code) != state["security_code"]:
                raise IssuerCheckpointV2Error("cross-security source start is prohibited")
            expected_ordinal = state["terminal_receipt_count"] + 1
            if expected_ordinal > EXPECTED_SOURCE_COUNT:
                raise IssuerCheckpointV2Error(
                    "all 29 source ordinals are already terminal; reconcile next"
                )
            if source_ordinal != expected_ordinal:
                raise IssuerCheckpointV2Error("only the next expected source ordinal may begin")
            selected = plan["queue"][state["selected_queue_ordinal"] - 1]
            source = selected["source_plan"][expected_ordinal - 1]
            supplied = (source_id, wave_ordinal, wave_id)
            expected = (source["source_id"], source["wave_ordinal"], source["wave_id"])
            if supplied != expected:
                raise IssuerCheckpointV2Error("source id, order, or wave differs from frozen plan")
            row = self._next_state(state, event_type="SOURCE_STARTED", updated_at=updated_at)
            row["active_source_ordinal"] = expected_ordinal
            validated = self._append_state(row, previous=state)
        self.load()
        return validated

    def complete_active_source(
        self,
        *,
        security_code: str,
        source_ordinal: int,
        source_id: str,
        wave_ordinal: int,
        wave_id: str,
        terminal_status: str,
        attempted_at: str | datetime,
        completed_at: str | datetime,
        raw_artifacts: Mapping[str, bytes],
        observation_count: int = 0,
        limitation: str = "Synthetic generated checkpoint fixture.",
        updated_at: str | datetime,
        expected_generation: int,
        expected_revision: int,
        expected_fencing_token: str,
        expected_owner_run_id: str,
        expected_prior_checkpoint_digest: str,
    ) -> dict[str, Any]:
        source_ordinal = _positive_int(source_ordinal, "source_ordinal")
        wave_ordinal = _positive_int(wave_ordinal, "wave_ordinal")
        with _locked_guard(self._root_descriptor):
            state, _files, plan, receipts = self._load()
            self._cas(
                state,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                expected_fencing_token=expected_fencing_token,
                expected_owner_run_id=expected_owner_run_id,
                expected_prior_checkpoint_digest=expected_prior_checkpoint_digest,
            )
            if state["status"] != "RUNNING" or state["active_source_ordinal"] != source_ordinal:
                raise IssuerCheckpointV2Error("only the active source may complete")
            if _security_code(security_code) != state["security_code"]:
                raise IssuerCheckpointV2Error("cross-security source receipt is prohibited")
            selected = plan["queue"][state["selected_queue_ordinal"] - 1]
            source = selected["source_plan"][source_ordinal - 1]
            if (source_id, wave_ordinal, wave_id) != (
                source["source_id"],
                source["wave_ordinal"],
                source["wave_id"],
            ):
                raise IssuerCheckpointV2Error("source receipt order or wave differs from frozen plan")
            if terminal_status not in TERMINAL_SOURCE_STATUSES:
                raise IssuerCheckpointV2Error("source result is not a terminal status")
            attempted = _timestamp(attempted_at, "attempted_at")
            completed = _timestamp(completed_at, "completed_at")
            attempted_instant = _instant(attempted, "attempted_at")
            completed_instant = _instant(completed, "completed_at")
            updated_instant = _instant(updated_at, "updated_at")
            if attempted_instant < _instant(
                state["updated_at"], "active source started_at"
            ):
                raise IssuerCheckpointV2Error(
                    "source attempted_at precedes the active source start"
                )
            if completed_instant < attempted_instant:
                raise IssuerCheckpointV2Error("source completed_at precedes attempted_at")
            if updated_instant < completed_instant:
                raise IssuerCheckpointV2Error(
                    "checkpoint updated_at precedes source completed_at"
                )
            observations = _nonnegative_int(observation_count, "observation_count")
            if terminal_status != "COLLECTED" and observations:
                raise IssuerCheckpointV2Error(
                    "only COLLECTED source receipts may report observations"
                )
            if not isinstance(raw_artifacts, Mapping):
                raise IssuerCheckpointV2Error("raw_artifacts must be a mapping")
            normalized_raw: list[tuple[str, bytes]] = []
            for raw_path, content in raw_artifacts.items():
                relative = _relative_path(raw_path, "raw artifact path")
                if not isinstance(content, bytes):
                    raise IssuerCheckpointV2Error("raw artifact content must be bytes")
                normalized_raw.append((relative, content))
            normalized_raw.sort(key=lambda item: item[0])
            if len({path for path, _ in normalized_raw}) != len(normalized_raw):
                raise IssuerCheckpointV2Error("raw artifact paths must be unique")
            if len(normalized_raw) > MAX_RAW_FILES_PER_SOURCE:
                raise IssuerCheckpointV2Error(
                    f"raw artifact count exceeds {MAX_RAW_FILES_PER_SOURCE}"
                )
            if any(len(content) > MAX_RAW_FILE_BYTES for _, content in normalized_raw):
                raise IssuerCheckpointV2Error(
                    f"a raw artifact exceeds {MAX_RAW_FILE_BYTES} bytes"
                )
            raw_size_bytes = sum(len(content) for _, content in normalized_raw)
            if raw_size_bytes > MAX_RAW_BYTES_PER_SOURCE:
                raise IssuerCheckpointV2Error(
                    f"raw artifact total exceeds {MAX_RAW_BYTES_PER_SOURCE} bytes"
                )
            prior_raw_file_count = sum(
                receipt["artifact_count"] for receipt in receipts
            )
            prior_raw_size_bytes = sum(
                receipt["raw_size_bytes"] for receipt in receipts
            )
            if (
                prior_raw_file_count + len(normalized_raw)
                > MAX_CHECKPOINT_RAW_FILES
            ):
                raise IssuerCheckpointV2Error(
                    "checkpoint raw artifact count budget would be exceeded"
                )
            if prior_raw_size_bytes + raw_size_bytes > MAX_CHECKPOINT_RAW_BYTES:
                raise IssuerCheckpointV2Error(
                    "checkpoint raw artifact byte budget would be exceeded"
                )
            if terminal_status in _NON_BLOCKING_TERMINAL_STATUSES and not normalized_raw:
                raise IssuerCheckpointV2Error(
                    "non-blocking terminal source requires a retained generated raw fixture"
                )
            if (
                not isinstance(limitation, str)
                or limitation != limitation.strip()
                or len(limitation) > 2000
            ):
                raise IssuerCheckpointV2Error("limitation must be bounded text")
            package_relative = f"receipts/{source_ordinal:03d}-{source_id}"
            artifacts: list[dict[str, Any]] = []
            transaction_payloads: dict[str, bytes] = {}
            for relative, content in normalized_raw:
                target = f"{package_relative}/raw/{relative}"
                transaction_payloads[target] = content
                artifacts.append(
                    {
                        "path": f"raw/{relative}",
                        "sha256": sha256_bytes(content),
                        "size_bytes": len(content),
                    }
                )
            manifest: dict[str, Any] = {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "checkpoint_id": state["checkpoint_id"],
                "security_code": state["security_code"],
                "source_ordinal": source_ordinal,
                "wave_ordinal": wave_ordinal,
                "wave_id": wave_id,
                "source_id": source_id,
                "artifacts": artifacts,
                "manifest_sha256": "",
            }
            manifest["manifest_sha256"] = _manifest_digest(manifest)
            transaction_payloads[f"{package_relative}/manifest.json"] = canonical_json_bytes(
                manifest
            )
            previous_receipt = receipts[-1]["receipt_sha256"] if receipts else None
            receipt: dict[str, Any] = {
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "receipt_id": f"{state['checkpoint_id']}:{source_ordinal:03d}",
                "checkpoint_id": state["checkpoint_id"],
                "run_id": state["run_id"],
                "plan_sha256": state["plan_sha256"],
                "identity_sha256": state["identity_sha256"],
                "issuer_id": state["issuer_id"],
                "security_code": state["security_code"],
                "source_ordinal": source_ordinal,
                "wave_ordinal": wave_ordinal,
                "wave_id": wave_id,
                "source_id": source_id,
                "terminal_status": terminal_status,
                "attempted_at": attempted,
                "completed_at": completed,
                "artifact_count": len(artifacts),
                "observation_count": observations,
                "artifact_manifest_path": f"{package_relative}/manifest.json",
                "artifact_manifest_sha256": manifest["manifest_sha256"],
                "raw_size_bytes": raw_size_bytes,
                "limitation": limitation,
                "previous_terminal_receipt_sha256": previous_receipt,
                "receipt_sha256": "",
            }
            receipt["receipt_sha256"] = _receipt_digest(receipt)
            transaction_payloads[f"{package_relative}/receipt.json"] = canonical_json_bytes(
                receipt
            )
            row = self._next_state(state, event_type="SOURCE_TERMINAL", updated_at=updated_at)
            row["active_source_ordinal"] = None
            row["terminal_receipt_count"] = state["terminal_receipt_count"] + 1
            row["next_source_ordinal"] = row["terminal_receipt_count"] + 1
            row["terminal_receipt_sha256s"] = [
                *state["terminal_receipt_sha256s"],
                receipt["receipt_sha256"],
            ]
            validated = self._append_state(
                row,
                previous=state,
                payloads=transaction_payloads,
            )
        self.load()
        return validated

    def preempt(
        self,
        *,
        updated_at: str | datetime,
        expected_generation: int,
        expected_revision: int,
        expected_fencing_token: str,
        expected_owner_run_id: str,
        expected_prior_checkpoint_digest: str,
    ) -> dict[str, Any]:
        with _locked_guard(self._root_descriptor):
            state, _files, _plan, _receipts = self._load()
            self._cas(
                state,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                expected_fencing_token=expected_fencing_token,
                expected_owner_run_id=expected_owner_run_id,
                expected_prior_checkpoint_digest=expected_prior_checkpoint_digest,
            )
            if state["status"] != "RUNNING" or state["terminal_receipt_count"] >= EXPECTED_SOURCE_COUNT:
                raise IssuerCheckpointV2Error("only an incomplete running fixture may be preempted")
            row = self._next_state(state, event_type="PREEMPTED", updated_at=updated_at)
            row["status"] = "PREEMPTED"
            row["active_source_ordinal"] = None
            validated = self._append_state(row, previous=state)
        self.load()
        return validated

    def resume(
        self,
        *,
        new_owner_run_id: str,
        updated_at: str | datetime,
        expected_generation: int,
        expected_revision: int,
        expected_fencing_token: str,
        expected_owner_run_id: str,
        expected_prior_checkpoint_digest: str,
    ) -> dict[str, Any]:
        owner = _identifier(new_owner_run_id, "new_owner_run_id")
        with _locked_guard(self._root_descriptor):
            state, _files, _plan, _receipts = self._load()
            self._cas(
                state,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                expected_fencing_token=expected_fencing_token,
                expected_owner_run_id=expected_owner_run_id,
                expected_prior_checkpoint_digest=expected_prior_checkpoint_digest,
            )
            if state["status"] != "PREEMPTED" or state["terminal_receipt_count"] >= EXPECTED_SOURCE_COUNT:
                raise IssuerCheckpointV2Error("only a preempted incomplete fixture may resume")
            row = self._next_state(state, event_type="RESUMED", updated_at=updated_at)
            row["status"] = "RUNNING"
            row["generation"] = state["generation"] + 1
            row["owner_run_id"] = owner
            row["fencing_token"] = _fencing_token(
                state["checkpoint_id"], state["security_code"], row["generation"], owner
            )
            validated = self._append_state(row, previous=state)
        self.load()
        return validated

    def reconcile(
        self,
        *,
        reconciled_at: str | datetime,
        expected_generation: int,
        expected_revision: int,
        expected_fencing_token: str,
        expected_owner_run_id: str,
        expected_prior_checkpoint_digest: str,
    ) -> dict[str, Any]:
        with _locked_guard(self._root_descriptor):
            state, _files, _plan, receipts = self._load()
            self._cas(
                state,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                expected_fencing_token=expected_fencing_token,
                expected_owner_run_id=expected_owner_run_id,
                expected_prior_checkpoint_digest=expected_prior_checkpoint_digest,
            )
            if (
                state["status"] != "RUNNING"
                or state["active_source_ordinal"] is not None
                or len(receipts) != EXPECTED_SOURCE_COUNT
            ):
                raise IssuerCheckpointV2Error(
                    "reconciliation requires all 29 terminal receipts and no active source"
                )
            inventory = [
                {
                    "source_ordinal": receipt["source_ordinal"],
                    "wave_ordinal": receipt["wave_ordinal"],
                    "wave_id": receipt["wave_id"],
                    "source_id": receipt["source_id"],
                    "terminal_status": receipt["terminal_status"],
                    "receipt_sha256": receipt["receipt_sha256"],
                    "manifest_sha256": receipt["artifact_manifest_sha256"],
                }
                for receipt in receipts
            ]
            waves: list[dict[str, Any]] = []
            cursor = 1
            for wave_ordinal, source_ids in enumerate(SOURCE_WAVE_SOURCES, start=1):
                ordinals = list(range(cursor, cursor + len(source_ids)))
                waves.append(
                    {
                        "wave_ordinal": wave_ordinal,
                        "wave_id": SOURCE_WAVE_IDS[wave_ordinal - 1],
                        "expected_source_ordinals": ordinals,
                        "terminal_source_ordinals": ordinals,
                        "status": "EXACT",
                    }
                )
                cursor += len(source_ids)
            status_counts: dict[str, int] = {}
            for receipt in receipts:
                status_counts[receipt["terminal_status"]] = (
                    status_counts.get(receipt["terminal_status"], 0) + 1
                )
            reconciliation: dict[str, Any] = {
                "schema_version": RECONCILIATION_SCHEMA_VERSION,
                "checkpoint_id": state["checkpoint_id"],
                "run_id": state["run_id"],
                "issuer_id": state["issuer_id"],
                "security_code": state["security_code"],
                "plan_sha256": state["plan_sha256"],
                "issuer_universe_sha256": state["issuer_universe_sha256"],
                "identity_sha256": state["identity_sha256"],
                "source_plan_sha256": state["source_plan_sha256"],
                "reconciled_at": _timestamp(reconciled_at, "reconciled_at"),
                "evidence_class": "SYNTHETIC_FIXTURE",
                "status": "EXACT_29_SOURCES_7_WAVES",
                "expected_source_count": EXPECTED_SOURCE_COUNT,
                "terminal_source_count": EXPECTED_SOURCE_COUNT,
                "expected_wave_count": EXPECTED_WAVE_COUNT,
                "reconciled_wave_count": EXPECTED_WAVE_COUNT,
                "receipt_inventory": inventory,
                "wave_reconciliation": waves,
                "terminal_status_counts": dict(sorted(status_counts.items())),
                "retained_manifest_count": EXPECTED_SOURCE_COUNT,
                "reopened_manifest_count": EXPECTED_SOURCE_COUNT,
                "raw_artifact_count": sum(receipt["artifact_count"] for receipt in receipts),
                "reopened_raw_artifact_count": sum(
                    receipt["artifact_count"] for receipt in receipts
                ),
                "raw_size_bytes": sum(receipt["raw_size_bytes"] for receipt in receipts),
                "reconciled_checkpoint_digest": state["checkpoint_digest"],
                "claim_boundaries": _claim_boundaries(),
                "reconciliation_sha256": "",
            }
            reconciliation["reconciliation_sha256"] = _reconciliation_digest(
                reconciliation
            )
            self._validated_reconciliation(
                reconciliation, state_before=state, receipts=receipts
            )
            row = self._next_state(
                state, event_type="RECONCILED", updated_at=reconciled_at
            )
            row["status"] = "RECONCILED"
            row["reconciliation_sha256"] = reconciliation["reconciliation_sha256"]
            validated = self._append_state(
                row,
                previous=state,
                payloads={
                    "reconciliation.json": canonical_json_bytes(reconciliation)
                },
            )
        self.load()
        return validated

    def seal(
        self,
        *,
        key: bytes,
        key_id: str,
        key_issuer_id: str,
        issued_at: str | datetime,
        expected_generation: int,
        expected_revision: int,
        expected_fencing_token: str,
        expected_owner_run_id: str,
        expected_prior_checkpoint_digest: str,
        previous_security_terminal_seal_sha256: str | None = None,
    ) -> dict[str, Any]:
        secret = _hmac_key(key)
        canonical_key_id = _identifier(key_id, "key_id")
        canonical_key_issuer = _identifier(key_issuer_id, "key_issuer_id")
        if previous_security_terminal_seal_sha256 is not None:
            try:
                require_sha256(
                    previous_security_terminal_seal_sha256,
                    "previous_security_terminal_seal_sha256",
                )
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
        with _locked_guard(self._root_descriptor):
            state, files, _plan, _receipts = self._load(
                recovery_hmac_key=secret,
                recovery_expected_key_id=canonical_key_id,
            )
            self._cas(
                state,
                expected_generation=expected_generation,
                expected_revision=expected_revision,
                expected_fencing_token=expected_fencing_token,
                expected_owner_run_id=expected_owner_run_id,
                expected_prior_checkpoint_digest=expected_prior_checkpoint_digest,
            )
            if state["status"] != "RECONCILED":
                raise IssuerCheckpointV2Error(
                    "terminal sealing requires exact 29-source reconciliation"
                )
            bound_previous_seal = state[
                "previous_security_terminal_seal_sha256"
            ]
            if previous_security_terminal_seal_sha256 is None:
                previous_security_terminal_seal_sha256 = bound_previous_seal
            elif previous_security_terminal_seal_sha256 != bound_previous_seal:
                raise IssuerCheckpointV2Error(
                    "terminal seal predecessor differs from checkpoint authority"
                )
            preseal_paths = set(files)
            inventory = _inventory(files, preseal_paths)
            bundle_root_sha256 = hash_json(inventory)
            seal: dict[str, Any] = {
                "schema_version": SEAL_SCHEMA_VERSION,
                "audience": SEAL_AUDIENCE,
                "seal_id": f"SEAL-{state['checkpoint_id']}",
                "key_issuer_id": canonical_key_issuer,
                "issued_at": _timestamp(issued_at, "issued_at"),
                "checkpoint_id": state["checkpoint_id"],
                "run_id": state["run_id"],
                "market": state["market"],
                "issuer_id": state["issuer_id"],
                "security_code": state["security_code"],
                "identity_sha256": state["identity_sha256"],
                "plan_sha256": state["plan_sha256"],
                "issuer_universe_sha256": state["issuer_universe_sha256"],
                "source_plan_sha256": state["source_plan_sha256"],
                "generation": state["generation"],
                "revision": state["revision"],
                "owner_run_id": state["owner_run_id"],
                "fencing_token": state["fencing_token"],
                "terminal_checkpoint_digest": state["checkpoint_digest"],
                "reconciliation_sha256": state["reconciliation_sha256"],
                "terminal_receipt_count": EXPECTED_SOURCE_COUNT,
                "wave_count": EXPECTED_WAVE_COUNT,
                "bundle_inventory": inventory,
                "bundle_root_sha256": bundle_root_sha256,
                "previous_security_terminal_seal_sha256": previous_security_terminal_seal_sha256,
                "claim_boundaries": _claim_boundaries(),
                "authentication": {
                    "algorithm": SEAL_ALGORITHM,
                    "key_id": canonical_key_id,
                    "tag": "0" * 64,
                },
            }
            seal["authentication"]["tag"] = hmac.new(
                secret, _canonical_authentication_bytes(seal), hashlib.sha256
            ).hexdigest()
            seal_content = canonical_json_bytes(seal)
            seal_sha256 = sha256_bytes(seal_content)
            row = self._next_state(state, event_type="SEALED", updated_at=issued_at)
            row["status"] = "SEALED"
            row["terminal_seal_sha256"] = seal_sha256
            self._append_state(
                row,
                previous=state,
                payloads={"terminal-seal.json": seal_content},
                recovery_hmac_key=secret,
                recovery_expected_key_id=canonical_key_id,
            )
        return self.validate_terminal_seal(
            key=secret, expected_key_id=canonical_key_id
        )

    def validate_terminal_seal(
        self, *, key: bytes, expected_key_id: str
    ) -> dict[str, Any]:
        with _locked_guard(self._root_descriptor):
            return self._validate_terminal_seal_locked(
                key=key, expected_key_id=expected_key_id
            )

    def _validate_terminal_seal_locked(
        self, *, key: bytes, expected_key_id: str
    ) -> dict[str, Any]:
        secret = _hmac_key(key)
        key_id = _identifier(expected_key_id, "expected_key_id")
        state, files, _plan, receipts = self._load(
            recovery_hmac_key=secret,
            recovery_expected_key_id=key_id,
        )
        if state["status"] != "SEALED" or len(receipts) != EXPECTED_SOURCE_COUNT:
            raise IssuerCheckpointV2Error("checkpoint has no terminal one-security seal")
        try:
            seal = _exact(
                strict_json_object(files["terminal-seal.json"], "terminal seal"),
                _SEAL_FIELDS,
                "terminal seal",
            )
        except ValueError as exc:
            raise IssuerCheckpointV2Error(str(exc)) from exc
        if files["terminal-seal.json"] != canonical_json_bytes(seal):
            raise IssuerCheckpointV2Error("terminal seal is not canonical JSON")
        authentication = _exact(seal["authentication"], _AUTH_FIELDS, "seal authentication")
        if authentication["algorithm"] != SEAL_ALGORITHM:
            raise IssuerCheckpointV2Error("unsupported terminal seal algorithm")
        if authentication["key_id"] != key_id:
            raise IssuerCheckpointV2Error("terminal seal key_id mismatch")
        tag = authentication["tag"]
        if not isinstance(tag, str) or re.fullmatch(r"[0-9a-f]{64}", tag) is None:
            raise IssuerCheckpointV2Error("terminal seal authentication tag is invalid")
        calculated = hmac.new(
            secret, _canonical_authentication_bytes(seal), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(calculated, tag):
            raise IssuerCheckpointV2Error("terminal seal authentication failed")
        penultimate_path = f"journal/{state['revision'] - 1:08d}.json"
        penultimate = _validate_state(
            strict_json_object(files[penultimate_path], "pre-seal checkpoint state")
        )
        expected_bindings = {
            "schema_version": SEAL_SCHEMA_VERSION,
            "audience": SEAL_AUDIENCE,
            "checkpoint_id": state["checkpoint_id"],
            "run_id": state["run_id"],
            "market": "BOURSA_KUWAIT",
            "issuer_id": state["issuer_id"],
            "security_code": state["security_code"],
            "identity_sha256": state["identity_sha256"],
            "plan_sha256": state["plan_sha256"],
            "issuer_universe_sha256": state["issuer_universe_sha256"],
            "source_plan_sha256": state["source_plan_sha256"],
            "generation": penultimate["generation"],
            "revision": penultimate["revision"],
            "owner_run_id": penultimate["owner_run_id"],
            "fencing_token": penultimate["fencing_token"],
            "terminal_checkpoint_digest": penultimate["checkpoint_digest"],
            "reconciliation_sha256": penultimate["reconciliation_sha256"],
            "terminal_receipt_count": EXPECTED_SOURCE_COUNT,
            "wave_count": EXPECTED_WAVE_COUNT,
            "claim_boundaries": _claim_boundaries(),
        }
        if any(seal.get(field) != value for field, value in expected_bindings.items()):
            raise IssuerCheckpointV2Error("terminal seal binding differs from checkpoint")
        _identifier(seal.get("seal_id"), "seal_id")
        _identifier(seal.get("key_issuer_id"), "key_issuer_id")
        _instant(seal.get("issued_at"), "issued_at")
        previous_seal = seal.get("previous_security_terminal_seal_sha256")
        if previous_seal is not None:
            try:
                require_sha256(previous_seal, "previous_security_terminal_seal_sha256")
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
        if previous_seal != state["previous_security_terminal_seal_sha256"]:
            raise IssuerCheckpointV2Error(
                "terminal seal predecessor differs from immutable checkpoint binding"
            )
        inventory = seal.get("bundle_inventory")
        if not isinstance(inventory, list):
            raise IssuerCheckpointV2Error("terminal seal inventory must be a list")
        expected_preseal_paths = set(files) - {
            "terminal-seal.json",
            f"journal/{state['revision']:08d}.json",
        }
        expected_inventory = _inventory(files, expected_preseal_paths)
        normalized_inventory: list[dict[str, Any]] = []
        for index, item in enumerate(inventory):
            entry = _exact(item, _INVENTORY_FIELDS, f"seal inventory {index}")
            _relative_path(entry["path"], "seal inventory path")
            try:
                require_sha256(entry["sha256"], "seal inventory sha256")
            except ValueError as exc:
                raise IssuerCheckpointV2Error(str(exc)) from exc
            _nonnegative_int(entry["size_bytes"], "seal inventory size_bytes")
            normalized_inventory.append(entry)
        if normalized_inventory != expected_inventory:
            raise IssuerCheckpointV2Error("terminal seal inventory differs from reopened bytes")
        if seal.get("bundle_root_sha256") != hash_json(expected_inventory):
            raise IssuerCheckpointV2Error("terminal seal bundle root digest mismatch")
        if sha256_bytes(files["terminal-seal.json"]) != state["terminal_seal_sha256"]:
            raise IssuerCheckpointV2Error("terminal seal file digest differs from final state")
        expected_final_state = dict(penultimate)
        expected_final_state["event_type"] = "SEALED"
        expected_final_state["revision"] = penultimate["revision"] + 1
        expected_final_state["prior_checkpoint_digest"] = penultimate[
            "checkpoint_digest"
        ]
        expected_final_state["updated_at"] = seal["issued_at"]
        expected_final_state["status"] = "SEALED"
        expected_final_state["terminal_seal_sha256"] = sha256_bytes(
            files["terminal-seal.json"]
        )
        expected_final_state["checkpoint_digest"] = _state_digest(
            expected_final_state
        )
        _validate_transition(penultimate, _validate_state(expected_final_state))
        if state != expected_final_state:
            raise IssuerCheckpointV2Error(
                "final checkpoint state differs from the authenticated seal derivation"
            )
        return {
            "status": "PASS_SYNTHETIC_ONE_SECURITY_TERMINAL_SEAL",
            "checkpoint_id": state["checkpoint_id"],
            "security_code": state["security_code"],
            "plan_sha256": state["plan_sha256"],
            "generation": state["generation"],
            "revision": state["revision"],
            "terminal_receipt_count": len(receipts),
            "wave_count": EXPECTED_WAVE_COUNT,
            "reconciliation_sha256": state["reconciliation_sha256"],
            "terminal_seal_sha256": state["terminal_seal_sha256"],
            "previous_security_terminal_seal_sha256": state[
                "previous_security_terminal_seal_sha256"
            ],
            "authenticated_key_id": key_id,
            "issued_at": seal["issued_at"],
            "claim_boundaries": _claim_boundaries(),
        }


__all__ = [
    "CHECKPOINT_SCHEMA_VERSION",
    "EXPECTED_SOURCE_COUNT",
    "EXPECTED_WAVE_COUNT",
    "IssuerCheckpointV2CasError",
    "IssuerCheckpointV2Error",
    "IssuerCheckpointV2FencingError",
    "IssuerCheckpointV2Store",
]
