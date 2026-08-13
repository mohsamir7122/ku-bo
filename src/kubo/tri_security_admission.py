from __future__ import annotations

from dataclasses import dataclass
import ctypes
import errno
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .foundation_io import (
    TreeSnapshotChangedError,
    load_strict_json_object,
    safe_regular_file,
    snapshot_regular_tree,
)
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .strict import parse_aware, require_sha256
from .tri_security_receipts import (
    RECEIPT_CLAIM_BOUNDARY,
    VerifiedTriSecurityRunReceipt,
    verify_tri_security_run_receipt,
    verify_tri_security_stage_binding,
)


SEMANTIC_ADMISSION_SCHEMA_VERSION = "2.0"
SEMANTIC_ADMISSION_AUDIENCE = "kubo-tri-security-boundary-admission"
SEMANTIC_ADMISSION_ALGORITHM = "HMAC-SHA256"
SEMANTIC_ADMISSION_CLAIM_BOUNDARY = (
    "AUTHENTICATED_SEMANTIC_BOUNDARY_BINDING_NOT_MARKET_EVIDENCE"
)
SEMANTIC_ADMISSION_FILE = "tri_security_semantic_admission.json"
OPERATION_BINDING_SCHEMA_VERSION = "1.0"
RUN_AUTHORITY_ROOT = "RUN_AUTHORITY_ROOT"
PENDING_GATE_ORDER = (
    "POINT_IN_TIME_IDENTITY",
    "TRADING_CALENDAR",
    "SECURITY_STATUS_HISTORY",
    "PRICE_DENOMINATOR",
    "PRICE_EVIDENCE",
    "PRICE_CORPORATE_ACTION_QA",
    "BENCHMARK_HISTORY",
    "BENCHMARK_EVIDENCE",
    "MARKET_TOTAL_RECONCILIATION",
    "QUERY_AND_PAGINATION_COMPLETENESS",
    "RUNTIME_SECRET_GUARD",
    "CLAIM_BOUNDARIES",
)

BOUNDARY_STAGE_MAP: Mapping[str, str] = MappingProxyType(
    {
        "import_user_price_exports": "RESEARCH_PRICE_HISTORY",
        "import_official_foundation": "OFFICIAL_FOUNDATION",
        "import_status_corporate": "STATUS_CORPORATE",
        "import_ca_enrichment": "CA_ENRICHMENT",
        "import_status_history": "STATUS_HISTORY",
        "import_benchmark_history": "BENCHMARK_HISTORY",
        "import_official_eod": "OFFICIAL_EOD",
        "build_data_foundation_packet": "FINAL_DATA_FOUNDATION_RECONCILIATION",
    }
)

BOUNDARY_INPUT_ROLES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "import_user_price_exports": ("config_dir", "input_dir"),
        "import_official_foundation": ("config_dir", "workspace"),
        "import_status_corporate": ("official_foundation_root", "workspace"),
        "import_ca_enrichment": ("status_corporate_root", "workspace"),
        "import_status_history": ("status_corporate_root", "workspace"),
        "import_benchmark_history": (
            "config_dir",
            "official_foundation_root",
            "workspace",
        ),
        "import_official_eod": (
            "workspace_root",
            "official_foundation_root",
            "status_history_root",
        ),
        "build_data_foundation_packet": (
            "official_foundation_root",
            "status_history_root",
            "ca_enrichment_root",
            "research_price_history_root",
            "benchmark_root",
            "official_eod_root",
            "project_root",
            "outcome_session_policy_path",
        ),
    }
)

OPERATION_ARGUMENT_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "import_user_price_exports": ("observed_at",),
        "import_official_foundation": (),
        "import_status_corporate": (),
        "import_ca_enrichment": (),
        "import_status_history": (),
        "import_benchmark_history": ("imported_at",),
        "import_official_eod": ("run_id", "imported_at", "runtime_trust"),
        "build_data_foundation_packet": (),
    }
)

STAGE_PREDECESSORS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "RESEARCH_PRICE_HISTORY": (RUN_AUTHORITY_ROOT,),
        "OFFICIAL_FOUNDATION": (RUN_AUTHORITY_ROOT,),
        "STATUS_CORPORATE": ("OFFICIAL_FOUNDATION",),
        "CA_ENRICHMENT": ("STATUS_CORPORATE",),
        "STATUS_HISTORY": ("STATUS_CORPORATE",),
        "BENCHMARK_HISTORY": ("OFFICIAL_FOUNDATION",),
        "OFFICIAL_EOD": ("OFFICIAL_FOUNDATION", "STATUS_HISTORY"),
        "FINAL_DATA_FOUNDATION_RECONCILIATION": (
            "OFFICIAL_FOUNDATION",
            "STATUS_HISTORY",
            "CA_ENRICHMENT",
            "RESEARCH_PRICE_HISTORY",
            "BENCHMARK_HISTORY",
            "OFFICIAL_EOD",
        ),
    }
)

_PREDECESSOR_ROOT_ROLES: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "STATUS_CORPORATE": MappingProxyType(
            {"OFFICIAL_FOUNDATION": "official_foundation_root"}
        ),
        "CA_ENRICHMENT": MappingProxyType(
            {"STATUS_CORPORATE": "status_corporate_root"}
        ),
        "STATUS_HISTORY": MappingProxyType(
            {"STATUS_CORPORATE": "status_corporate_root"}
        ),
        "BENCHMARK_HISTORY": MappingProxyType(
            {"OFFICIAL_FOUNDATION": "official_foundation_root"}
        ),
        "OFFICIAL_EOD": MappingProxyType(
            {
                "OFFICIAL_FOUNDATION": "official_foundation_root",
                "STATUS_HISTORY": "status_history_root",
            }
        ),
        "FINAL_DATA_FOUNDATION_RECONCILIATION": MappingProxyType(
            {
                "OFFICIAL_FOUNDATION": "official_foundation_root",
                "STATUS_HISTORY": "status_history_root",
                "CA_ENRICHMENT": "ca_enrichment_root",
                "RESEARCH_PRICE_HISTORY": "research_price_history_root",
                "BENCHMARK_HISTORY": "benchmark_root",
                "OFFICIAL_EOD": "official_eod_root",
            }
        ),
    }
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004


class BoundaryAdmissionError(ValueError):
    """Stable fail-closed rejection raised by a boundary admission gate."""

    def __init__(self, code: str, phase: str, message: str = "") -> None:
        super().__init__(f"{code}:{phase}" + (f":{message}" if message else ""))
        self.code = code
        self.phase = phase
        self.failure_code = code
        self.failure_phase = phase
        self.message = message


def _reject(code: str, phase: str, message: str = "") -> None:
    raise BoundaryAdmissionError(code, phase, message)


def _reject_snapshot_error(exc: BaseException, *, phase: str) -> None:
    if isinstance(exc, TreeSnapshotChangedError):
        _reject("STAGE_TREE_CHANGED_DURING_VERIFICATION", phase, str(exc))
    message = str(exc)
    unsafe_markers = (
        "symlink",
        "reparse",
        "only regular files",
        "unsafe path",
        "reserved path",
        "hard-linked",
        "exceeds maximum",
        "exceeds ",
    )
    if phase == "PRE_COMMIT_RECHECK" and not any(
        marker in message.lower() for marker in unsafe_markers
    ):
        _reject("STAGE_TREE_CHANGED_DURING_VERIFICATION", phase, message)
    _reject("UNSAFE_STAGE_ENTRY", phase, message)


def _key(value: bytes, *, code: str, phase: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        _reject(code, phase, "authority key must contain at least 32 bytes")
    return value


def _identifier(value: Any, *, code: str, phase: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not _IDENTIFIER.fullmatch(value):
        _reject(code, phase, "invalid canonical identifier")
    return value


def _exact(value: Any, fields: set[str], *, code: str, phase: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _reject(code, phase, "unknown or missing fields")
    return value


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _deep_freeze(value: Any) -> Any:
    """Return an immutable recursive view of already validated JSON-like data."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _canonical_instant(value: Any, *, field: str, phase: str) -> str:
    if not isinstance(value, str):
        _reject("OPERATION_BINDING_MISMATCH", phase, f"{field} must be a string")
    try:
        instant = parse_aware(value, field)
    except ValueError as exc:
        _reject("OPERATION_BINDING_MISMATCH", phase, str(exc))
    canonical = instant.isoformat()
    if value != canonical:
        _reject(
            "OPERATION_BINDING_MISMATCH",
            phase,
            f"{field} must be canonical ISO-8601",
        )
    return canonical


def _runtime_trust_operation_binding(value: Any, *, phase: str) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        entries = []
        for entry in value.entries:
            entries.append(
                {
                    "source_id": str(entry.source_id),
                    "subject_id": str(entry.subject_id),
                    "domains": sorted(str(item) for item in entry.domains),
                    "security_codes": sorted(str(item) for item in entry.security_codes),
                    "activation_id": entry.activation_id,
                    "entitlement_id": entry.entitlement_id,
                    "valid_from": entry.valid_from.isoformat(),
                    "valid_until": entry.valid_until.isoformat(),
                }
            )
        semantics = {
            "registry_id": str(value.registry_id),
            "issued_at": value.issued_at.isoformat(),
            "expires_at": value.expires_at.isoformat(),
            "entries": sorted(
                entries,
                key=lambda item: (
                    item["source_id"],
                    item["subject_id"],
                    item["activation_id"] or "",
                    item["entitlement_id"] or "",
                ),
            ),
        }
        registry_id = _identifier(
            value.registry_id,
            code="OPERATION_BINDING_MISMATCH",
            phase=phase,
        )
        key_id = _identifier(
            value.authenticated_key_id,
            code="OPERATION_BINDING_MISMATCH",
            phase=phase,
        )
        content_sha256 = require_sha256(
            value.content_sha256,
            "runtime trust content_sha256",
        )
    except (AttributeError, TypeError, ValueError) as exc:
        _reject("OPERATION_BINDING_MISMATCH", phase, str(exc))
    return {
        "registry_id": registry_id,
        "content_sha256": content_sha256,
        "authenticated_key_id": key_id,
        "semantics_sha256": hash_json(semantics),
    }


def build_boundary_operation_binding(
    boundary_id: str,
    *,
    decision_at: str,
    observed_at: str | None = None,
    imported_at: str | None = None,
    run_id: str | None = None,
    runtime_trust_registry: Any = None,
) -> dict[str, Any]:
    """Canonicalize the behavior-affecting scalar arguments of one boundary."""

    phase = "ENTRY_PRE_WRITE"
    if boundary_id not in BOUNDARY_STAGE_MAP:
        _reject("STAGE_BINDING_STAGE_ID_MISMATCH", phase)
    decision = _canonical_instant(
        decision_at,
        field="operation decision_at",
        phase=phase,
    )
    arguments: dict[str, Any]
    if boundary_id == "import_user_price_exports":
        observed = _canonical_instant(
            observed_at,
            field="operation observed_at",
            phase=phase,
        )
        if parse_aware(observed, "observed_at") > parse_aware(decision, "decision_at"):
            _reject(
                "OPERATION_BINDING_MISMATCH",
                phase,
                "observed_at must not be after decision_at",
            )
        arguments = {"observed_at": observed}
    elif boundary_id == "import_benchmark_history":
        arguments = {
            "imported_at": _canonical_instant(
                imported_at,
                field="operation imported_at",
                phase=phase,
            )
        }
    elif boundary_id == "import_official_eod":
        arguments = {
            "run_id": _identifier(
                run_id,
                code="OPERATION_BINDING_MISMATCH",
                phase=phase,
            ),
            "imported_at": _canonical_instant(
                imported_at,
                field="operation imported_at",
                phase=phase,
            ),
            "runtime_trust": _runtime_trust_operation_binding(
                runtime_trust_registry,
                phase=phase,
            ),
        }
    else:
        arguments = {}
    supplied = {
        "observed_at": observed_at,
        "imported_at": imported_at,
        "run_id": run_id,
        "runtime_trust_registry": runtime_trust_registry,
    }
    allowed = {
        "import_user_price_exports": {"observed_at"},
        "import_benchmark_history": {"imported_at"},
        "import_official_eod": {"imported_at", "run_id", "runtime_trust_registry"},
    }.get(boundary_id, set())
    unexpected = sorted(
        field for field, item in supplied.items() if field not in allowed and item is not None
    )
    if unexpected:
        _reject(
            "OPERATION_BINDING_MISMATCH",
            phase,
            f"unexpected operation arguments: {','.join(unexpected)}",
        )
    return {
        "schema_version": OPERATION_BINDING_SCHEMA_VERSION,
        "decision_at": decision,
        "arguments": arguments,
    }


def _normalize_operation_binding(
    boundary_id: str,
    value: Any,
    *,
    phase: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _reject("OPERATION_BINDING_MISMATCH", phase, "operation binding must be an object")
    binding = dict(value)
    if set(binding) != {"schema_version", "decision_at", "arguments"}:
        _reject("OPERATION_BINDING_MISMATCH", phase, "operation binding fields mismatch")
    if binding["schema_version"] != OPERATION_BINDING_SCHEMA_VERSION:
        _reject("OPERATION_BINDING_MISMATCH", phase, "operation binding version mismatch")
    decision = _canonical_instant(
        binding["decision_at"],
        field="operation decision_at",
        phase=phase,
    )
    arguments_value = binding["arguments"]
    if not isinstance(arguments_value, Mapping):
        _reject("OPERATION_BINDING_MISMATCH", phase, "operation arguments must be an object")
    arguments = dict(arguments_value)
    if set(arguments) != set(OPERATION_ARGUMENT_FIELDS[boundary_id]):
        _reject("OPERATION_BINDING_MISMATCH", phase, "operation argument fields mismatch")
    if boundary_id == "import_user_price_exports":
        observed = _canonical_instant(
            arguments["observed_at"],
            field="operation observed_at",
            phase=phase,
        )
        if parse_aware(observed, "observed_at") > parse_aware(decision, "decision_at"):
            _reject("OPERATION_BINDING_MISMATCH", phase, "observed_at is after decision_at")
        arguments = {"observed_at": observed}
    elif boundary_id == "import_benchmark_history":
        arguments = {
            "imported_at": _canonical_instant(
                arguments["imported_at"],
                field="operation imported_at",
                phase=phase,
            )
        }
    elif boundary_id == "import_official_eod":
        run_id = _identifier(
            arguments["run_id"],
            code="OPERATION_BINDING_MISMATCH",
            phase=phase,
        )
        imported = _canonical_instant(
            arguments["imported_at"],
            field="operation imported_at",
            phase=phase,
        )
        trust = arguments["runtime_trust"]
        if trust is not None:
            if not isinstance(trust, Mapping):
                _reject("OPERATION_BINDING_MISMATCH", phase, "runtime trust binding invalid")
            trust = dict(trust)
            if set(trust) != {
                "registry_id",
                "content_sha256",
                "authenticated_key_id",
                "semantics_sha256",
            }:
                _reject("OPERATION_BINDING_MISMATCH", phase, "runtime trust fields mismatch")
            try:
                trust = {
                    "registry_id": _identifier(
                        trust["registry_id"],
                        code="OPERATION_BINDING_MISMATCH",
                        phase=phase,
                    ),
                    "content_sha256": require_sha256(
                        trust["content_sha256"],
                        "runtime trust content_sha256",
                    ),
                    "authenticated_key_id": _identifier(
                        trust["authenticated_key_id"],
                        code="OPERATION_BINDING_MISMATCH",
                        phase=phase,
                    ),
                    "semantics_sha256": require_sha256(
                        trust["semantics_sha256"],
                        "runtime trust semantics_sha256",
                    ),
                }
            except ValueError as exc:
                _reject("OPERATION_BINDING_MISMATCH", phase, str(exc))
        arguments = {"run_id": run_id, "imported_at": imported, "runtime_trust": trust}
    return {
        "schema_version": OPERATION_BINDING_SCHEMA_VERSION,
        "decision_at": decision,
        "arguments": arguments,
    }


def _overlap(left: Path, right: Path) -> bool:
    left = _absolute(left)
    right = _absolute(right)
    return left == right or left in right.parents or right in left.parents


def _safe_tree_component(value: str, *, field: str, phase: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or value != value.strip()
        or value.endswith((".", " "))
        or ":" in value
        or "\\" in value
        or "/" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or value.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
    ):
        _reject("UNSAFE_STAGE_ENTRY", phase, f"{field} has an unsafe name")
    return value


def _directory_inventory_once(
    root: Path,
    *,
    field: str,
    phase: str,
    max_entries: int = 8192,
    max_depth: int = 64,
) -> tuple[str, ...]:
    rows: list[str] = []
    entry_count = 0

    def visit(directory: Path, relative: tuple[str, ...], depth: int) -> None:
        nonlocal entry_count
        if depth > max_depth:
            _reject("UNSAFE_STAGE_ENTRY", phase, f"{field} exceeds maximum depth")
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError as exc:
            _reject_snapshot_error(
                ValueError(f"{field} cannot be enumerated"),
                phase=phase,
            )
        for entry in entries:
            entry_count += 1
            if entry_count > max_entries:
                _reject("UNSAFE_STAGE_ENTRY", phase, f"{field} has too many entries")
            name = _safe_tree_component(entry.name, field=field, phase=phase)
            parts = (*relative, name)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                _reject_snapshot_error(
                    ValueError(f"{field} changed during enumeration"),
                    phase=phase,
                )
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
                _reject("UNSAFE_STAGE_ENTRY", phase, f"{field} contains an unsafe alias")
            if stat.S_ISDIR(metadata.st_mode):
                rows.append("/".join(parts))
                visit(Path(entry.path), parts, depth + 1)
            elif not stat.S_ISREG(metadata.st_mode):
                _reject("UNSAFE_STAGE_ENTRY", phase, f"{field} contains a special entry")

    visit(_absolute(root), (), 0)
    return tuple(rows)


def _is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _directory_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_mode


@dataclass(frozen=True, slots=True)
class _IssueParentGuard:
    path: Path
    snapshots: tuple[tuple[Path, tuple[int, int, int]], ...]
    descriptor: int


def _open_issue_parent(path: Path, *, phase: str) -> _IssueParentGuard:
    """Pin an existing real parent directory for one no-overwrite file issue."""

    if not path.name or path == path.parent:
        _reject("UNSAFE_STAGE_ENTRY", phase, "admission output must name one file")
    parent = path.parent
    anchor = Path(parent.anchor)
    if not parent.is_absolute() or not parent.anchor:
        _reject("UNSAFE_STAGE_ENTRY", phase, "admission output must be absolute")
    chain = [anchor]
    current = anchor
    for component in parent.parts[1:]:
        current /= component
        chain.append(current)
    snapshots: list[tuple[Path, tuple[int, int, int]]] = []
    for component in chain:
        try:
            metadata = os.lstat(component)
        except OSError as exc:
            _reject(
                "UNSAFE_STAGE_ENTRY",
                phase,
                "admission output parent must already exist",
            )
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse_point(metadata)
            or not stat.S_ISDIR(metadata.st_mode)
        ):
            _reject(
                "UNSAFE_STAGE_ENTRY",
                phase,
                "admission output parent must be a real directory",
            )
        snapshots.append((component, _directory_identity(metadata)))
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        _reject(
            "UNSAFE_STAGE_ENTRY",
            phase,
            "safe directory-relative file creation is unavailable",
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(parent, flags)
    except OSError as exc:
        _reject("UNSAFE_STAGE_ENTRY", phase, "admission output parent is unsafe")
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _directory_identity(opened) != snapshots[-1][1]
    ):
        os.close(descriptor)
        _reject("UNSAFE_STAGE_ENTRY", phase, "admission output parent changed")
    return _IssueParentGuard(
        path=parent,
        snapshots=tuple(snapshots),
        descriptor=descriptor,
    )


def _recheck_issue_parent(guard: _IssueParentGuard, *, phase: str) -> None:
    for path, expected in guard.snapshots:
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            _reject("UNSAFE_STAGE_ENTRY", phase, "admission output parent changed")
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse_point(metadata)
            or not stat.S_ISDIR(metadata.st_mode)
            or _directory_identity(metadata) != expected
        ):
            _reject("UNSAFE_STAGE_ENTRY", phase, "admission output parent changed")
    opened = os.fstat(guard.descriptor)
    if _directory_identity(opened) != guard.snapshots[-1][1]:
        _reject("UNSAFE_STAGE_ENTRY", phase, "admission output parent changed")


def _issue_target_metadata(
    guard: _IssueParentGuard,
    name: str,
    *,
    phase: str,
) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=guard.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None
        _reject("UNSAFE_STAGE_ENTRY", phase, "admission output cannot be inspected")


def _require_issue_target_absent(
    guard: _IssueParentGuard,
    name: str,
    *,
    phase: str,
) -> None:
    if _issue_target_metadata(guard, name, phase=phase) is not None:
        _reject("OUTPUT_ROOT_ALREADY_EXISTS", phase)


def _cleanup_issue_entry(
    guard: _IssueParentGuard,
    name: str,
    identity: tuple[int, int, int],
) -> None:
    """Best-effort cleanup, but never unlink an entry that was replaced."""

    try:
        current = os.stat(name, dir_fd=guard.descriptor, follow_symlinks=False)
        if _directory_identity(current) == identity:
            os.unlink(name, dir_fd=guard.descriptor)
    except OSError:
        pass


def _issue_temp_name(target_name: str) -> str:
    fragment = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in target_name
    )[:48]
    return f".{fragment or 'admission'}.staging-{secrets.token_hex(12)}"


def _linux_rename_file_noreplace(
    source_name: str,
    target_name: str,
    parent_descriptor: int,
) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    function = getattr(library, "renameat2", None)
    if function is None:
        raise OSError(errno.ENOTSUP, "renameat2 is unavailable")
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = function(
        parent_descriptor,
        os.fsencode(source_name),
        parent_descriptor,
        os.fsencode(target_name),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno() or errno.EIO
        raise OSError(error, os.strerror(error), target_name)


def _darwin_rename_file_noreplace(
    source_name: str,
    target_name: str,
    parent_descriptor: int,
) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    function = getattr(library, "renameatx_np", None)
    if function is None:
        raise OSError(errno.ENOTSUP, "renameatx_np is unavailable")
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = function(
        parent_descriptor,
        os.fsencode(source_name),
        parent_descriptor,
        os.fsencode(target_name),
        _RENAME_EXCL,
    )
    if result != 0:
        error = ctypes.get_errno() or errno.EIO
        raise OSError(error, os.strerror(error), target_name)


def _rename_issue_noreplace(
    guard: _IssueParentGuard,
    source_name: str,
    target_name: str,
    *,
    phase: str,
) -> None:
    try:
        if sys.platform.startswith("linux"):
            _linux_rename_file_noreplace(
                source_name,
                target_name,
                guard.descriptor,
            )
        elif sys.platform == "darwin":
            _darwin_rename_file_noreplace(
                source_name,
                target_name,
                guard.descriptor,
            )
        elif os.name == "nt":
            # Windows rename does not replace an existing destination.
            os.rename(guard.path / source_name, guard.path / target_name)
        else:
            raise OSError(errno.ENOTSUP, "safe no-overwrite rename is unavailable")
    except OSError as exc:
        if exc.errno in {errno.EEXIST, errno.ENOTEMPTY}:
            _reject("OUTPUT_ROOT_ALREADY_EXISTS", phase)
        _reject("UNSAFE_STAGE_ENTRY", phase, "admission output cannot be published safely")


def _publish_issued_file(
    guard: _IssueParentGuard,
    name: str,
    content: bytes,
    *,
    phase: str,
) -> None:
    _recheck_issue_parent(guard, phase=phase)
    _require_issue_target_absent(guard, name, phase=phase)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    temp_name: str | None = None
    identity: tuple[int, int, int] | None = None
    published = False
    try:
        for _ in range(128):
            candidate = _issue_temp_name(name)
            try:
                descriptor = os.open(candidate, flags, 0o600, dir_fd=guard.descriptor)
            except FileExistsError:
                continue
            except OSError as exc:
                _reject("UNSAFE_STAGE_ENTRY", phase, "admission staging cannot be created safely")
            temp_name = candidate
            break
        if descriptor is None or temp_name is None:
            _reject("UNSAFE_STAGE_ENTRY", phase, "unique admission staging cannot be allocated")
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size != 0
        ):
            _reject("UNSAFE_STAGE_ENTRY", phase, "admission staging is not a new regular file")
        identity = _directory_identity(opened)
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                _reject("UNSAFE_STAGE_ENTRY", phase, "admission output write failed")
            offset += written
        os.fsync(descriptor)
        final = os.fstat(descriptor)
        if (
            _directory_identity(final) != identity
            or final.st_nlink != 1
            or final.st_size != len(content)
        ):
            _reject("UNSAFE_STAGE_ENTRY", phase, "admission staging changed while written")
        staged = _issue_target_metadata(guard, temp_name, phase=phase)
        if (
            staged is None
            or _directory_identity(staged) != identity
            or staged.st_nlink != 1
            or staged.st_size != len(content)
        ):
            _reject("UNSAFE_STAGE_ENTRY", phase, "admission staging changed before publish")
        _recheck_issue_parent(guard, phase=phase)
        _require_issue_target_absent(guard, name, phase=phase)
        _rename_issue_noreplace(
            guard,
            temp_name,
            name,
            phase=phase,
        )
        published = True
        final_entry = _issue_target_metadata(guard, name, phase=phase)
        if (
            final_entry is None
            or _directory_identity(final_entry) != identity
            or final_entry.st_nlink != 1
            or final_entry.st_size != len(content)
        ):
            _reject("UNSAFE_STAGE_ENTRY", phase, "admission output changed before publish")
        os.fsync(guard.descriptor)
    except BaseException:
        if identity is not None and temp_name is not None and not published:
            _cleanup_issue_entry(guard, temp_name, identity)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _auth_bytes(payload: Mapping[str, Any]) -> bytes:
    authentication = payload["authentication"]
    return canonical_json_bytes(
        {
            "document": {
                key: value for key, value in payload.items() if key != "authentication"
            },
            "algorithm": authentication["algorithm"],
            "key_id": authentication["key_id"],
        }
    )


def _sign(payload: dict[str, Any], *, key: bytes, key_id: str) -> dict[str, Any]:
    secret = _key(
        key,
        code="STAGE_BINDING_AUTHENTICATION_FAILED",
        phase="ENTRY_PRE_WRITE",
    )
    canonical_id = _identifier(
        key_id,
        code="STAGE_BINDING_KEY_ID_MISMATCH",
        phase="ENTRY_PRE_WRITE",
    )
    payload["authentication"] = {
        "algorithm": SEMANTIC_ADMISSION_ALGORITHM,
        "key_id": canonical_id,
        "tag": "0" * 64,
    }
    payload["authentication"]["tag"] = hmac.new(
        secret, _auth_bytes(payload), hashlib.sha256
    ).hexdigest()
    return payload


def _tree_binding(root: Path, *, phase: str) -> tuple[dict[str, Any], Mapping[str, bytes]]:
    before_directories = _directory_inventory_once(
        root,
        field="semantic admission input tree",
        phase=phase,
    )
    try:
        snapshot = snapshot_regular_tree(root, field="semantic admission input tree")
    except ValueError as exc:
        _reject_snapshot_error(exc, phase=phase)
    after_directories = _directory_inventory_once(
        root,
        field="semantic admission input tree",
        phase=phase,
    )
    if before_directories != after_directories:
        _reject(
            "STAGE_TREE_CHANGED_DURING_VERIFICATION",
            phase,
            "directory inventory changed while snapshotted",
        )
    inventory = snapshot.inventory()
    by_path = snapshot.by_path()
    manifest = by_path.get("manifest.json")
    if manifest is None:
        _reject("STAGE_MANIFEST_HASH_MISMATCH", phase, "manifest.json is required")
    binding = {
        "root_role": "BOUNDARY_INPUT_TREE",
        "manifest_sha256": manifest.sha256,
        "file_count": len(inventory),
        "size_bytes": sum(row["size_bytes"] for row in inventory),
        "inventory_sha256": hash_json(inventory),
        "inventory": inventory,
        "directory_count": len(after_directories),
        "directory_inventory_sha256": hash_json(list(after_directories)),
        "directories": list(after_directories),
    }
    return binding, MappingProxyType(
        {path: item.content for path, item in by_path.items()}
    )


def _inventory_paths(value: Any) -> dict[str, Mapping[str, Any]] | None:
    if not isinstance(value, list):
        return None
    rows: dict[str, Mapping[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            return None
        path = item.get("path")
        if not isinstance(path, str) or not path or path in rows:
            return None
        rows[path] = item
    return rows


def _reject_tree_difference(
    expected: Any,
    current: Mapping[str, Any],
    *,
    phase: str,
) -> None:
    """Classify a signed-vs-live tree difference without adapter relabeling."""

    if expected == dict(current):
        return
    if not isinstance(expected, Mapping):
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, "input_tree must be an object")
    expected_files = _inventory_paths(expected.get("inventory"))
    current_files = _inventory_paths(current.get("inventory"))
    if expected_files is None or current_files is None:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, "input_tree inventory is invalid")
    expected_paths = set(expected_files)
    current_paths = set(current_files)
    if current_paths - expected_paths:
        _reject("STAGE_TREE_ADDITION_DETECTED", phase)
    if expected_paths - current_paths:
        _reject("STAGE_TREE_DELETION_DETECTED", phase)
    if any(expected_files[path] != current_files[path] for path in expected_paths):
        _reject("STAGE_TREE_HASH_MISMATCH", phase)

    expected_directories = expected.get("directories")
    current_directories = current.get("directories")
    if isinstance(expected_directories, list) and isinstance(current_directories, list):
        expected_directory_set = set(expected_directories)
        current_directory_set = set(current_directories)
        if current_directory_set - expected_directory_set:
            _reject("STAGE_TREE_ADDITION_DETECTED", phase)
        if expected_directory_set - current_directory_set:
            _reject("STAGE_TREE_DELETION_DETECTED", phase)
    _reject("STAGE_ARTIFACT_INVENTORY_MISMATCH", phase)


def _boundary_input_binding(
    boundary_id: str,
    boundary_inputs: Mapping[str, Path],
    *,
    phase: str,
) -> list[dict[str, Any]]:
    expected = BOUNDARY_INPUT_ROLES[boundary_id]
    if not isinstance(boundary_inputs, Mapping) or set(boundary_inputs) != set(expected):
        _reject("STAGE_ARTIFACT_INVENTORY_MISMATCH", phase, "boundary input roles mismatch")
    rows: list[dict[str, Any]] = []
    for role in expected:
        path = Path(boundary_inputs[role])
        try:
            if path.is_dir() and not path.is_symlink():
                before_directories = _directory_inventory_once(
                    path,
                    field=f"boundary input {role}",
                    phase=phase,
                )
                snapshot = snapshot_regular_tree(
                    path,
                    field=f"boundary input {role}",
                )
                after_directories = _directory_inventory_once(
                    path,
                    field=f"boundary input {role}",
                    phase=phase,
                )
                if before_directories != after_directories:
                    _reject(
                        "STAGE_TREE_CHANGED_DURING_VERIFICATION",
                        phase,
                        f"boundary input {role} directory inventory changed",
                    )
                inventory = snapshot.inventory()
                rows.append(
                    {
                        "role": role,
                        "kind": "REGULAR_TREE",
                        "file_count": len(inventory),
                        "size_bytes": sum(item["size_bytes"] for item in inventory),
                        "inventory_sha256": hash_json(inventory),
                        "directory_count": len(after_directories),
                        "directory_inventory_sha256": hash_json(
                            list(after_directories)
                        ),
                    }
                )
            else:
                content = safe_regular_file(path, field=f"boundary input {role}")
                rows.append(
                    {
                        "role": role,
                        "kind": "REGULAR_FILE",
                        "file_count": 1,
                        "size_bytes": len(content),
                        "inventory_sha256": sha256_bytes(content),
                    }
                )
        except (OSError, ValueError) as exc:
            _reject_snapshot_error(exc, phase=phase)
    return rows


def _run_semantics(receipt: VerifiedTriSecurityRunReceipt) -> dict[str, Any]:
    binding = receipt.binding
    gates = {gate: "PENDING_EXTERNAL_EVIDENCE" for gate in PENDING_GATE_ORDER}
    return {
        "run_id": binding["run_id"],
        "batch_id": binding["batch_id"],
        "batch_sequence": binding["batch_sequence"],
        "batch_plan_sha256": binding["batch_plan"]["sha256"],
        "scoped_manifest_sha256": binding["scoped_configuration"]["manifest_sha256"],
        "qualification_window": binding["qualification_window"],
        "cohort": binding["cohort"],
        "pending_gate_state": gates,
    }


def _claims() -> dict[str, Any]:
    return {
        "denominator": "NAMED_TRI_SECURITY_COHORT",
        "security_count": 3,
        "full_market": False,
        "benchmark_status": "CONFIGURED_SERIES_INCOMPATIBLE_WITH_TRI_COHORT",
        "benchmark_fallback_allowed": False,
        "outcome_session_policy": "UNFROZEN_KU_BO_008_D01_OPEN",
        "legacy_july": "UNTRUSTED_LEGACY_CLAIM_QUARANTINED",
        "market_evidence_claimed": False,
        "backtest_ready": False,
        "forecast_allowed": False,
        "recommendation_allowed": False,
    }


def _fixed_predecessor_paths(
    stage_id: str,
    boundary_inputs: Mapping[str, Path],
    *,
    phase: str,
) -> tuple[Path, ...]:
    expected_stages = STAGE_PREDECESSORS[stage_id]
    if expected_stages == (RUN_AUTHORITY_ROOT,):
        return ()
    roles = _PREDECESSOR_ROOT_ROLES.get(stage_id)
    if roles is None or set(roles) != set(expected_stages):
        _reject(
            "PREDECESSOR_STAGE_MISMATCH",
            phase,
            "installed predecessor root-role mapping is incomplete",
        )
    paths: list[Path] = []
    for predecessor_stage in expected_stages:
        role = roles[predecessor_stage]
        root = boundary_inputs.get(role)
        if root is None:
            _reject(
                "PREDECESSOR_BINDING_REQUIRED",
                phase,
                f"bound upstream role is missing: {role}",
            )
        paths.append(_absolute(Path(root)) / SEMANTIC_ADMISSION_FILE)
    return tuple(paths)


def _predecessor_rows(
    *,
    stage_id: str,
    run_binding: Mapping[str, Any],
    root_receipt_sha256: str,
    predecessors: Sequence["VerifiedBoundaryAdmission"],
    boundary_inputs: Mapping[str, Path],
    semantic_key: bytes,
    semantic_key_id: str,
    phase: str,
) -> list[dict[str, str]]:
    expected = STAGE_PREDECESSORS[stage_id]
    run_id = str(run_binding["run_id"])
    if expected == (RUN_AUTHORITY_ROOT,):
        if predecessors:
            _reject("PREDECESSOR_STAGE_MISMATCH", phase)
        return [
            {
                "stage_id": RUN_AUTHORITY_ROOT,
                "run_id": run_id,
                "admission_sha256": root_receipt_sha256,
            }
        ]
    tokens: list[VerifiedBoundaryAdmission] = []
    for predecessor in predecessors:
        if not isinstance(predecessor, VerifiedBoundaryAdmission):
            _reject(
                "PREDECESSOR_STAGE_MISMATCH",
                phase,
                "predecessor token was not produced by admission",
            )
        tokens.append(predecessor)
    fixed_paths = _fixed_predecessor_paths(
        stage_id,
        boundary_inputs,
        phase=phase,
    )
    rows = _predecessor_rows_from_paths(
        stage_id=stage_id,
        run_binding=run_binding,
        root_receipt_sha256=root_receipt_sha256,
        paths=fixed_paths,
        boundary_inputs=boundary_inputs,
        semantic_key=semantic_key,
        semantic_key_id=semantic_key_id,
        phase=phase,
    )
    tokens_by_stage: dict[str, VerifiedBoundaryAdmission] = {}
    for token in tokens:
        if token.stage_id in tokens_by_stage:
            _reject("PREDECESSOR_BINDING_REPLAYED", phase)
        tokens_by_stage[token.stage_id] = token
    for row in rows:
        token = tokens_by_stage.get(row["stage_id"])
        if (
            token is None
            or token.run_id != row["run_id"]
            or token.admission_sha256 != row["admission_sha256"]
            or BOUNDARY_STAGE_MAP.get(token.boundary_id) != row["stage_id"]
        ):
            _reject(
                "PREDECESSOR_BINDING_REPLAYED",
                phase,
                "predecessor token metadata does not match authenticated bytes",
            )
    return rows


def _verify_document_signature(
    payload: dict[str, Any],
    *,
    key: bytes,
    expected_key_id: str,
    phase: str,
) -> None:
    secret = _key(key, code="STAGE_BINDING_AUTHENTICATION_FAILED", phase=phase)
    authentication = _exact(
        payload.get("authentication"),
        {"algorithm", "key_id", "tag"},
        code="STAGE_BINDING_SCHEMA_INVALID",
        phase=phase,
    )
    if authentication["algorithm"] != SEMANTIC_ADMISSION_ALGORITHM:
        _reject("STAGE_BINDING_AUTHENTICATION_FAILED", phase)
    if authentication["key_id"] != expected_key_id:
        _reject("STAGE_BINDING_KEY_ID_MISMATCH", phase)
    tag = authentication["tag"]
    if not isinstance(tag, str) or not re.fullmatch(r"[0-9a-f]{64}", tag):
        _reject("STAGE_BINDING_AUTHENTICATION_FAILED", phase)
    expected = hmac.new(secret, _auth_bytes(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, tag):
        _reject("STAGE_BINDING_AUTHENTICATION_FAILED", phase)


def _validate_v1_references(value: Any, *, phase: str) -> dict[str, str]:
    references = _exact(
        value,
        {"claim_boundary", "run_receipt_sha256", "stage_binding_sha256"},
        code="STAGE_BINDING_SCHEMA_INVALID",
        phase=phase,
    )
    if references["claim_boundary"] != RECEIPT_CLAIM_BOUNDARY:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    try:
        require_sha256(references["run_receipt_sha256"], "run_receipt_sha256")
        require_sha256(references["stage_binding_sha256"], "stage_binding_sha256")
    except ValueError as exc:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, str(exc))
    return references


def _predecessor_rows_from_paths(
    *,
    stage_id: str,
    run_binding: Mapping[str, Any],
    root_receipt_sha256: str,
    paths: Sequence[Path],
    boundary_inputs: Mapping[str, Path],
    semantic_key: bytes,
    semantic_key_id: str,
    phase: str,
) -> list[dict[str, str]]:
    expected = STAGE_PREDECESSORS[stage_id]
    if expected == (RUN_AUTHORITY_ROOT,):
        if paths:
            _reject("PREDECESSOR_STAGE_MISMATCH", phase)
        return [
            {
                "stage_id": RUN_AUTHORITY_ROOT,
                "run_id": str(run_binding["run_id"]),
                "admission_sha256": root_receipt_sha256,
            }
        ]
    if not paths:
        _reject("PREDECESSOR_BINDING_REQUIRED", phase)
    fixed_paths = _fixed_predecessor_paths(
        stage_id,
        boundary_inputs,
        phase=phase,
    )
    fixed_stage_by_path = {
        _absolute(path): predecessor_stage
        for predecessor_stage, path in zip(expected, fixed_paths)
    }
    supplied_paths = [_absolute(Path(path)) for path in paths]
    if len(set(supplied_paths)) != len(supplied_paths):
        _reject("PREDECESSOR_BINDING_REPLAYED", phase)
    supplied_set = set(supplied_paths)
    fixed_set = set(fixed_stage_by_path)
    if supplied_set != fixed_set:
        code = (
            "PREDECESSOR_BINDING_REQUIRED"
            if supplied_set < fixed_set
            else "PREDECESSOR_STAGE_MISMATCH"
        )
        _reject(
            code,
            phase,
            "predecessor admissions must be fixed sidecars of bound upstream roots",
        )
    rows_by_stage: dict[str, dict[str, str]] = {}
    seen_hashes: set[str] = set()
    for path in supplied_paths:
        payload, content = _load_admission(path, phase=phase)
        _verify_document_signature(
            payload,
            key=semantic_key,
            expected_key_id=semantic_key_id,
            phase=phase,
        )
        predecessor_stage = payload.get("stage_id")
        predecessor_boundary = payload.get("boundary_id")
        if BOUNDARY_STAGE_MAP.get(str(predecessor_boundary)) != predecessor_stage:
            _reject("PREDECESSOR_STAGE_MISMATCH", phase)
        if fixed_stage_by_path[path] != predecessor_stage:
            _reject(
                "PREDECESSOR_STAGE_MISMATCH",
                phase,
                "upstream sidecar stage does not match its bound root role",
            )
        digest = sha256_bytes(content)
        if predecessor_stage in rows_by_stage or digest in seen_hashes:
            _reject("PREDECESSOR_BINDING_REPLAYED", phase)
        if payload.get("run_binding") != dict(run_binding):
            _reject("PREDECESSOR_BINDING_REPLAYED", phase)
        references = _validate_v1_references(payload.get("v1_references"), phase=phase)
        if (
            not isinstance(references, dict)
            or references.get("run_receipt_sha256") != root_receipt_sha256
        ):
            _reject("PREDECESSOR_BINDING_REPLAYED", phase)
        _validate_claims(payload.get("claims"), phase=phase)
        rows_by_stage[str(predecessor_stage)] = {
            "stage_id": str(predecessor_stage),
            "run_id": str(run_binding["run_id"]),
            "admission_sha256": digest,
        }
        seen_hashes.add(digest)
    if set(rows_by_stage) != set(expected):
        code = (
            "PREDECESSOR_BINDING_REQUIRED"
            if set(rows_by_stage) < set(expected)
            else "PREDECESSOR_STAGE_MISMATCH"
        )
        _reject(code, phase)
    return [rows_by_stage[item] for item in expected]


def build_semantic_boundary_admission(
    *,
    boundary_id: str,
    verified_receipt: VerifiedTriSecurityRunReceipt,
    v1_stage_report: Mapping[str, Any],
    v1_stage_binding_sha256: str,
    input_root: Path,
    boundary_inputs: Mapping[str, Path],
    operation_binding: Mapping[str, Any],
    predecessor_admissions: Sequence["VerifiedBoundaryAdmission"] = (),
    predecessor_admission_paths: Sequence[Path] = (),
    admission_id: str,
    issued_at: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any]:
    if boundary_id not in BOUNDARY_STAGE_MAP:
        _reject("STAGE_BINDING_STAGE_ID_MISMATCH", "ENTRY_PRE_WRITE")
    stage_id = BOUNDARY_STAGE_MAP[boundary_id]
    if v1_stage_report.get("stage_id") != stage_id:
        _reject("STAGE_BINDING_STAGE_ID_MISMATCH", "ENTRY_PRE_WRITE")
    if v1_stage_report.get("run_id") != verified_receipt.binding["run_id"]:
        _reject("STAGE_BINDING_RUN_ID_MISMATCH", "ENTRY_PRE_WRITE")
    tree, _ = _tree_binding(input_root, phase="ENTRY_PRE_WRITE")
    bound_inputs = _boundary_input_binding(
        boundary_id,
        boundary_inputs,
        phase="ENTRY_PRE_WRITE",
    )
    bound_operation = _normalize_operation_binding(
        boundary_id,
        operation_binding,
        phase="ENTRY_PRE_WRITE",
    )
    if tree["manifest_sha256"] != v1_stage_report.get("stage_manifest_sha256"):
        _reject("STAGE_MANIFEST_HASH_MISMATCH", "ENTRY_PRE_WRITE")
    receipt_sha = require_sha256(verified_receipt.receipt_sha256, "receipt_sha256")
    if predecessor_admissions and predecessor_admission_paths:
        _reject("PREDECESSOR_BINDING_REPLAYED", "ENTRY_PRE_WRITE")
    if predecessor_admission_paths:
        predecessor_rows = _predecessor_rows_from_paths(
            stage_id=stage_id,
            run_binding=_run_semantics(verified_receipt),
            root_receipt_sha256=receipt_sha,
            paths=predecessor_admission_paths,
            boundary_inputs=boundary_inputs,
            semantic_key=key,
            semantic_key_id=key_id,
            phase="ENTRY_PRE_WRITE",
        )
    else:
        predecessor_rows = _predecessor_rows(
            stage_id=stage_id,
            run_binding=_run_semantics(verified_receipt),
            root_receipt_sha256=receipt_sha,
            predecessors=predecessor_admissions,
            boundary_inputs=boundary_inputs,
            semantic_key=key,
            semantic_key_id=key_id,
            phase="ENTRY_PRE_WRITE",
        )
    issued = parse_aware(issued_at, "issued_at")
    operation_decision = parse_aware(
        bound_operation["decision_at"],
        "operation decision_at",
    )
    if issued > operation_decision:
        _reject(
            "OPERATION_BINDING_MISMATCH",
            "ENTRY_PRE_WRITE",
            "operation decision_at precedes admission issuance",
        )
    if boundary_id in {"import_benchmark_history", "import_official_eod"}:
        imported = parse_aware(
            bound_operation["arguments"]["imported_at"],
            "operation imported_at",
        )
        if not issued <= imported <= operation_decision:
            _reject(
                "OPERATION_BINDING_MISMATCH",
                "ENTRY_PRE_WRITE",
                "imported_at must be between admission issuance and decision_at",
            )
    if (
        boundary_id == "import_official_eod"
        and bound_operation["arguments"]["run_id"]
        != verified_receipt.binding["run_id"]
    ):
        _reject(
            "OPERATION_BINDING_MISMATCH",
            "ENTRY_PRE_WRITE",
            "operation run_id differs from authenticated run",
        )
    payload = {
        "schema_version": SEMANTIC_ADMISSION_SCHEMA_VERSION,
        "audience": SEMANTIC_ADMISSION_AUDIENCE,
        "admission_id": _identifier(
            admission_id,
            code="STAGE_BINDING_SCHEMA_INVALID",
            phase="ENTRY_PRE_WRITE",
        ),
        "issued_at": issued.isoformat(),
        "boundary_id": boundary_id,
        "stage_id": stage_id,
        "v1_references": {
            "claim_boundary": RECEIPT_CLAIM_BOUNDARY,
            "run_receipt_sha256": receipt_sha,
            "stage_binding_sha256": require_sha256(
                v1_stage_binding_sha256, "v1_stage_binding_sha256"
            ),
        },
        "run_binding": _run_semantics(verified_receipt),
        "input_tree": tree,
        "boundary_inputs": bound_inputs,
        "operation_binding": bound_operation,
        "predecessor_bindings": predecessor_rows,
        "claims": _claims(),
        "claim_boundary": SEMANTIC_ADMISSION_CLAIM_BOUNDARY,
    }
    return _sign(payload, key=key, key_id=key_id)


def issue_semantic_boundary_admission(
    *,
    output_path: Path,
    **arguments: Any,
) -> dict[str, Any]:
    phase = "ENTRY_PRE_WRITE"
    path = _absolute(output_path)
    protected_roots: list[Path] = []
    receipt = arguments.get("verified_receipt")
    if isinstance(receipt, VerifiedTriSecurityRunReceipt):
        protected_roots.append(receipt.workspace_root)
    input_root = arguments.get("input_root")
    if input_root is not None:
        protected_roots.append(Path(input_root))
    boundary_inputs = arguments.get("boundary_inputs")
    if isinstance(boundary_inputs, Mapping):
        protected_roots.extend(Path(value) for value in boundary_inputs.values())
    if any(_overlap(path, protected) for protected in protected_roots):
        _reject("STAGE_ROOT_NOT_DISJOINT", phase)

    guard = _open_issue_parent(path, phase=phase)
    try:
        _recheck_issue_parent(guard, phase=phase)
        _require_issue_target_absent(guard, path.name, phase=phase)
        payload = build_semantic_boundary_admission(**arguments)
        content = canonical_json_bytes(payload)
        _publish_issued_file(guard, path.name, content, phase=phase)
    finally:
        os.close(guard.descriptor)
    return {
        "status": "PASS",
        "admission_sha256": sha256_bytes(content),
        "boundary_id": payload["boundary_id"],
        "stage_id": payload["stage_id"],
        "claim_boundary": SEMANTIC_ADMISSION_CLAIM_BOUNDARY,
    }


@dataclass(frozen=True, slots=True)
class BoundaryAdmissionRequest:
    admission_path: Path
    receipt_path: Path | None
    stage_binding_path: Path | None
    workspace_root: Path
    input_root: Path
    expected_batch_plan_sha256: str
    expected_scoped_config_manifest_sha256: str
    expected_stage_manifest_sha256: str
    decision_at: str
    expected_run_id: str
    expected_batch_id: str
    run_key: bytes
    run_key_id: str
    v1_stage_key: bytes
    v1_stage_key_id: str
    semantic_key: bytes
    semantic_key_id: str
    boundary_inputs: Mapping[str, Path]
    operation_binding: Mapping[str, Any]
    predecessor_admissions: tuple["VerifiedBoundaryAdmission", ...] = ()
    predecessor_admission_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "boundary_inputs",
            MappingProxyType(
                {str(role): Path(path) for role, path in self.boundary_inputs.items()}
            ),
        )
        object.__setattr__(
            self,
            "operation_binding",
            _deep_freeze(self.operation_binding),
        )
        object.__setattr__(
            self,
            "predecessor_admissions",
            tuple(self.predecessor_admissions),
        )
        object.__setattr__(
            self,
            "predecessor_admission_paths",
            tuple(Path(path) for path in self.predecessor_admission_paths),
        )


@dataclass(frozen=True, slots=True)
class VerifiedBoundaryAdmission:
    request: BoundaryAdmissionRequest
    boundary_id: str
    stage_id: str
    run_id: str
    batch_id: str
    admission_sha256: str
    payload: Mapping[str, Any]
    input_files: Mapping[str, bytes]
    _output_root: Path
    _input_tree_binding: Mapping[str, Any]
    _boundary_input_binding: tuple[Mapping[str, Any], ...]
    _operation_binding: Mapping[str, Any]
    _admission_bytes: bytes

    def report(self) -> dict[str, Any]:
        return {
            "schema_version": SEMANTIC_ADMISSION_SCHEMA_VERSION,
            "status": "PASS",
            "boundary_id": self.boundary_id,
            "stage_id": self.stage_id,
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "admission_sha256": self.admission_sha256,
            "claim_boundary": SEMANTIC_ADMISSION_CLAIM_BOUNDARY,
        }

    def materialize_receipt(self, staging_root: Path) -> Path:
        """Write the exact authenticated admission as a fixed output sidecar.

        The caller must provide its private atomic staging directory. The
        sidecar is created once and is never reconstructed from public token
        fields, so the next stage can bind the exact verified bytes.
        """

        root = _absolute(staging_root)
        try:
            metadata = os.lstat(root)
        except OSError as exc:
            _reject(
                "UNSAFE_STAGE_ENTRY",
                "PRE_COMMIT_RECHECK",
                "staging root must already exist",
            )
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse_point(metadata)
            or not stat.S_ISDIR(metadata.st_mode)
        ):
            _reject(
                "UNSAFE_STAGE_ENTRY",
                "PRE_COMMIT_RECHECK",
                "staging root must be a real directory",
            )
        path = root / SEMANTIC_ADMISSION_FILE
        guard = _open_issue_parent(path, phase="PRE_COMMIT_RECHECK")
        try:
            _publish_issued_file(
                guard,
                path.name,
                self._admission_bytes,
                phase="PRE_COMMIT_RECHECK",
            )
        finally:
            os.close(guard.descriptor)
        return path

    def materialize_lineage(self, staging_root: Path) -> Path:
        """Persist the signed output-lineage view of these exact verified bytes."""

        from .tri_security_lineage import materialize_boundary_lineage

        return materialize_boundary_lineage(self, staging_root)

    def revalidate_before_commit(self) -> "VerifiedBoundaryAdmission":
        if self._output_root.exists() or self._output_root.is_symlink():
            _reject("OUTPUT_ROOT_CHANGED_DURING_COMMIT", "PRE_COMMIT_RECHECK")
        refreshed = _admit(
            self.request,
            boundary_id=self.boundary_id,
            output_root=self._output_root,
            boundary_inputs=self.request.boundary_inputs,
            operation_binding=self.request.operation_binding,
            phase="PRE_COMMIT_RECHECK",
        )
        if refreshed._admission_bytes != self._admission_bytes:
            _reject(
                "STAGE_TREE_CHANGED_DURING_VERIFICATION",
                "PRE_COMMIT_RECHECK",
                "authenticated admission identity changed after initial validation",
            )
        return refreshed


def _validate_claims(claims: Any, *, phase: str) -> None:
    if not isinstance(claims, dict):
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    if claims.get("security_count") != 3 or claims.get("denominator") != "NAMED_TRI_SECURITY_COHORT":
        _reject("FIVE_SECURITY_DENOMINATOR_FORBIDDEN", phase)
    if claims.get("full_market") is not False:
        _reject("FULL_MARKET_CLAIM_FORBIDDEN", phase)
    if (
        claims.get("benchmark_status")
        != "CONFIGURED_SERIES_INCOMPATIBLE_WITH_TRI_COHORT"
        or claims.get("benchmark_fallback_allowed") is not False
    ):
        _reject("BENCHMARK_FALLBACK_FORBIDDEN", phase)
    if claims.get("outcome_session_policy") != "UNFROZEN_KU_BO_008_D01_OPEN":
        _reject("KU_BO_008_D01_OPEN", phase)
    if claims.get("legacy_july") != "UNTRUSTED_LEGACY_CLAIM_QUARANTINED":
        _reject("UNTRUSTED_LEGACY_CLAIM_QUARANTINED", phase)
    if claims != _claims():
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)


def _load_admission(path: Path, *, phase: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload, content = load_strict_json_object(path, field="semantic boundary admission")
    except ValueError as exc:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, str(exc))
    if content != canonical_json_bytes(payload):
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, "non-canonical JSON")
    _exact(
        payload,
        {
            "schema_version", "audience", "admission_id", "issued_at",
            "boundary_id", "stage_id", "v1_references", "run_binding",
            "input_tree", "boundary_inputs", "operation_binding",
            "predecessor_bindings", "claims", "claim_boundary",
            "authentication",
        },
        code="STAGE_BINDING_SCHEMA_INVALID",
        phase=phase,
    )
    if payload["schema_version"] != SEMANTIC_ADMISSION_SCHEMA_VERSION:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    if payload["audience"] != SEMANTIC_ADMISSION_AUDIENCE:
        _reject("STAGE_BINDING_AUDIENCE_MISMATCH", phase)
    if payload["claim_boundary"] != SEMANTIC_ADMISSION_CLAIM_BOUNDARY:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    _identifier(
        payload["admission_id"],
        code="STAGE_BINDING_SCHEMA_INVALID",
        phase=phase,
    )
    try:
        parse_aware(payload["issued_at"], "semantic admission issued_at")
    except ValueError as exc:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, str(exc))
    return payload, content


def _verify_semantic_authentication(
    payload: dict[str, Any], request: BoundaryAdmissionRequest, *, phase: str
) -> None:
    run_secret = _key(request.run_key, code="RUN_RECEIPT_AUTHENTICATION_FAILED", phase=phase)
    v1_secret = _key(request.v1_stage_key, code="STAGE_BINDING_AUTHENTICATION_FAILED", phase=phase)
    semantic_secret = _key(request.semantic_key, code="STAGE_BINDING_AUTHENTICATION_FAILED", phase=phase)
    if (
        hmac.compare_digest(run_secret, v1_secret)
        or hmac.compare_digest(run_secret, semantic_secret)
        or hmac.compare_digest(v1_secret, semantic_secret)
        or len({request.run_key_id, request.v1_stage_key_id, request.semantic_key_id}) != 3
    ):
        _reject("AUTHORITY_KEYS_NOT_INDEPENDENT", phase)
    _verify_document_signature(
        payload,
        key=semantic_secret,
        expected_key_id=request.semantic_key_id,
        phase=phase,
    )


def _ensure_authorities_independent(
    request: BoundaryAdmissionRequest,
    *,
    phase: str,
) -> None:
    run_secret = _key(request.run_key, code="RUN_RECEIPT_AUTHENTICATION_FAILED", phase=phase)
    v1_secret = _key(request.v1_stage_key, code="STAGE_BINDING_AUTHENTICATION_FAILED", phase=phase)
    semantic_secret = _key(request.semantic_key, code="STAGE_BINDING_AUTHENTICATION_FAILED", phase=phase)
    if (
        hmac.compare_digest(run_secret, v1_secret)
        or hmac.compare_digest(run_secret, semantic_secret)
        or hmac.compare_digest(v1_secret, semantic_secret)
        or len({request.run_key_id, request.v1_stage_key_id, request.semantic_key_id}) != 3
    ):
        _reject("AUTHORITY_KEYS_NOT_INDEPENDENT", phase)


def _admit(
    request: BoundaryAdmissionRequest,
    *,
    boundary_id: str,
    output_root: Path,
    boundary_inputs: Mapping[str, Path],
    operation_binding: Mapping[str, Any],
    phase: str,
) -> VerifiedBoundaryAdmission:
    if request is None:
        _reject("RUN_RECEIPT_REQUIRED", phase)
    if boundary_id not in BOUNDARY_STAGE_MAP:
        _reject("STAGE_BINDING_STAGE_ID_MISMATCH", phase)
    _ensure_authorities_independent(request, phase=phase)
    supplied_inputs = {
        str(role): _absolute(Path(path)) for role, path in boundary_inputs.items()
    }
    requested_inputs = {
        str(role): _absolute(Path(path))
        for role, path in request.boundary_inputs.items()
    }
    if supplied_inputs != requested_inputs:
        _reject("STAGE_ARTIFACT_INVENTORY_MISMATCH", phase)
    supplied_operation = _normalize_operation_binding(
        boundary_id,
        operation_binding,
        phase=phase,
    )
    requested_operation = _normalize_operation_binding(
        boundary_id,
        request.operation_binding,
        phase=phase,
    )
    if supplied_operation != requested_operation:
        _reject("OPERATION_BINDING_MISMATCH", phase)
    try:
        request_decision = parse_aware(request.decision_at, "decision_at").isoformat()
    except ValueError as exc:
        _reject("OPERATION_BINDING_MISMATCH", phase, str(exc))
    if requested_operation["decision_at"] != request_decision:
        _reject("OPERATION_BINDING_MISMATCH", phase, "decision_at differs from request")
    output = _absolute(output_root)
    if output.exists() or output.is_symlink():
        _reject(
            "OUTPUT_ROOT_ALREADY_EXISTS" if phase != "PRE_COMMIT_RECHECK" else "OUTPUT_ROOT_CHANGED_DURING_COMMIT",
            phase,
        )
    for protected in (request.workspace_root, request.input_root):
        if _overlap(output, protected):
            _reject("STAGE_ROOT_NOT_DISJOINT", phase)
    for protected in request.boundary_inputs.values():
        if _overlap(output, protected):
            _reject("STAGE_ROOT_NOT_DISJOINT", phase)
    receipt_path = Path(request.receipt_path) if request.receipt_path else None
    if (
        receipt_path is None
        or not receipt_path.exists()
        or receipt_path.is_symlink()
        or not receipt_path.is_file()
    ):
        _reject("RUN_RECEIPT_REQUIRED", phase)
    stage_binding_path = (
        Path(request.stage_binding_path) if request.stage_binding_path else None
    )
    admission_path = Path(request.admission_path) if request.admission_path else None
    if (
        stage_binding_path is None
        or admission_path is None
        or not stage_binding_path.exists()
        or stage_binding_path.is_symlink()
        or not stage_binding_path.is_file()
        or not admission_path.exists()
        or admission_path.is_symlink()
        or not admission_path.is_file()
    ):
        _reject("STAGE_BINDING_REQUIRED", phase)
    try:
        receipt = verify_tri_security_run_receipt(
            receipt_path=request.receipt_path,
            workspace_root=request.workspace_root,
            expected_batch_plan_sha256=request.expected_batch_plan_sha256,
            expected_scoped_config_manifest_sha256=request.expected_scoped_config_manifest_sha256,
            decision_at=request.decision_at,
            key=request.run_key,
            expected_key_id=request.run_key_id,
            expected_run_id=request.expected_run_id,
            expected_batch_id=request.expected_batch_id,
        )
    except ValueError as exc:
        text = str(exc)
        code = "RUN_RECEIPT_SCHEMA_INVALID"
        if "authentication key_id" in text:
            code = "RUN_RECEIPT_KEY_ID_MISMATCH"
        elif "authentication failed" in text:
            code = "RUN_RECEIPT_AUTHENTICATION_FAILED"
        elif "not valid at" in text:
            issued = None
            try:
                payload, _ = load_strict_json_object(request.receipt_path, field="run receipt")
                issued = parse_aware(payload.get("issued_at"), "issued_at")
            except ValueError:
                pass
            decision = parse_aware(request.decision_at, "decision_at")
            code = "RUN_RECEIPT_NOT_YET_VALID" if issued and decision < issued else "RUN_RECEIPT_EXPIRED"
        elif "expected_run_id" in text:
            code = "RUN_RECEIPT_RUN_ID_MISMATCH"
        elif "expected_batch_id" in text:
            code = "RUN_RECEIPT_BATCH_MISMATCH"
        elif "audience" in text:
            code = "RUN_RECEIPT_AUDIENCE_MISMATCH"
        elif "batch plan" in text:
            code = "RUN_RECEIPT_BATCH_PLAN_HASH_MISMATCH"
        elif "scoped manifest" in text:
            code = "RUN_RECEIPT_MANIFEST_HASH_MISMATCH"
        _reject(code, phase, text)
    stage_id = BOUNDARY_STAGE_MAP[boundary_id]
    payload, admission_bytes = _load_admission(request.admission_path, phase=phase)
    _verify_semantic_authentication(payload, request, phase=phase)
    if payload["boundary_id"] != boundary_id or payload["stage_id"] != stage_id:
        _reject("STAGE_BINDING_STAGE_ID_MISMATCH", phase)
    signed_operation = _normalize_operation_binding(
        boundary_id,
        payload.get("operation_binding"),
        phase=phase,
    )
    if signed_operation != requested_operation:
        _reject("OPERATION_BINDING_MISMATCH", phase)
    tree, files = _tree_binding(request.input_root, phase=phase)
    _reject_tree_difference(payload.get("input_tree"), tree, phase=phase)
    try:
        stage = verify_tri_security_stage_binding(
            binding_path=request.stage_binding_path,
            receipt_path=request.receipt_path,
            workspace_root=request.workspace_root,
            stage_root=request.input_root,
            expected_batch_plan_sha256=request.expected_batch_plan_sha256,
            expected_scoped_config_manifest_sha256=request.expected_scoped_config_manifest_sha256,
            expected_stage_manifest_sha256=request.expected_stage_manifest_sha256,
            decision_at=request.decision_at,
            key=request.v1_stage_key,
            expected_key_id=request.v1_stage_key_id,
            receipt_key=request.run_key,
            expected_receipt_key_id=request.run_key_id,
            expected_stage_id=stage_id,
            expected_run_id=request.expected_run_id,
            expected_batch_id=request.expected_batch_id,
        )
    except ValueError as exc:
        text = str(exc)
        code = "STAGE_BINDING_SCHEMA_INVALID"
        if "authentication key_id" in text:
            code = "STAGE_BINDING_KEY_ID_MISMATCH"
        elif "authentication failed" in text:
            code = "STAGE_BINDING_AUTHENTICATION_FAILED"
        elif "expected_stage_id" in text:
            code = "STAGE_BINDING_STAGE_ID_MISMATCH"
        elif "mixes a different" in text:
            code = "STAGE_BINDING_RUN_ID_MISMATCH"
        elif "manifest SHA-256" in text:
            code = "STAGE_MANIFEST_HASH_MISMATCH"
        elif "outside" in text:
            code = "STAGE_ROOT_NOT_DISJOINT"
        elif "artifacts changed" in text:
            code = "STAGE_ARTIFACT_INVENTORY_MISMATCH"
        _reject(code, phase, text)
    run = payload["run_binding"]
    expected_run = _run_semantics(receipt)
    if (
        boundary_id == "import_official_eod"
        and requested_operation["arguments"]["run_id"] != expected_run["run_id"]
    ):
        _reject(
            "OPERATION_BINDING_MISMATCH",
            phase,
            "operation run_id differs from authenticated run",
        )
    if not isinstance(run, dict):
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    if set(run) != set(expected_run):
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase)
    for field, code in (
        ("run_id", "RUN_RECEIPT_RUN_ID_MISMATCH"),
        ("batch_id", "RUN_RECEIPT_BATCH_MISMATCH"),
        ("batch_plan_sha256", "RUN_RECEIPT_BATCH_PLAN_HASH_MISMATCH"),
        ("scoped_manifest_sha256", "RUN_RECEIPT_MANIFEST_HASH_MISMATCH"),
        ("qualification_window", "RUN_RECEIPT_WINDOW_MISMATCH"),
        ("cohort", "RUN_RECEIPT_COHORT_MISMATCH"),
        ("pending_gate_state", "RUN_RECEIPT_GATE_STATE_MISMATCH"),
    ):
        if run.get(field) != expected_run[field]:
            _reject(code, phase)
    try:
        semantic_issued = parse_aware(
            payload["issued_at"],
            "semantic admission issued_at",
        )
        decision = parse_aware(request.decision_at, "decision_at")
        receipt_issued = parse_aware(receipt.payload["issued_at"], "receipt issued_at")
        receipt_expires = parse_aware(receipt.payload["expires_at"], "receipt expires_at")
    except ValueError as exc:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, str(exc))
    if not receipt_issued <= semantic_issued <= decision < receipt_expires:
        _reject("STAGE_BINDING_SCHEMA_INVALID", phase, "semantic admission time invalid")
    if boundary_id in {"import_benchmark_history", "import_official_eod"}:
        imported = parse_aware(
            requested_operation["arguments"]["imported_at"],
            "operation imported_at",
        )
        if not semantic_issued <= imported <= decision:
            _reject(
                "OPERATION_BINDING_MISMATCH",
                phase,
                "imported_at must be between admission issuance and decision_at",
            )
    references = _validate_v1_references(payload.get("v1_references"), phase=phase)
    expected_refs = {
        "claim_boundary": RECEIPT_CLAIM_BOUNDARY,
        "run_receipt_sha256": receipt.receipt_sha256,
        "stage_binding_sha256": stage.report()["binding_sha256"],
    }
    if references != expected_refs:
        _reject("STAGE_BINDING_RUN_ID_MISMATCH", phase)
    boundary_input_binding = _boundary_input_binding(
        boundary_id,
        request.boundary_inputs,
        phase=phase,
    )
    if payload.get("boundary_inputs") != boundary_input_binding:
        _reject("STAGE_ARTIFACT_INVENTORY_MISMATCH", phase)
    if request.predecessor_admissions and request.predecessor_admission_paths:
        _reject("PREDECESSOR_BINDING_REPLAYED", phase)
    if request.predecessor_admission_paths:
        expected_rows = _predecessor_rows_from_paths(
            stage_id=stage_id,
            run_binding=expected_run,
            root_receipt_sha256=receipt.receipt_sha256,
            paths=request.predecessor_admission_paths,
            boundary_inputs=request.boundary_inputs,
            semantic_key=request.semantic_key,
            semantic_key_id=request.semantic_key_id,
            phase=phase,
        )
    else:
        expected_rows = _predecessor_rows(
            stage_id=stage_id,
            run_binding=expected_run,
            root_receipt_sha256=receipt.receipt_sha256,
            predecessors=request.predecessor_admissions,
            boundary_inputs=request.boundary_inputs,
            semantic_key=request.semantic_key,
            semantic_key_id=request.semantic_key_id,
            phase=phase,
        )
    rows = payload.get("predecessor_bindings")
    if not isinstance(rows, list) or not rows:
        _reject("PREDECESSOR_BINDING_REQUIRED", phase)
    if len({row.get("admission_sha256") for row in rows if isinstance(row, dict)}) != len(rows):
        _reject("PREDECESSOR_BINDING_REPLAYED", phase)
    if rows != expected_rows:
        actual_stages = {row.get("stage_id") for row in rows if isinstance(row, dict)}
        expected_stages = {row["stage_id"] for row in expected_rows}
        code = "PREDECESSOR_BINDING_REQUIRED" if actual_stages < expected_stages else "PREDECESSOR_STAGE_MISMATCH"
        _reject(code, phase)
    _validate_claims(payload.get("claims"), phase=phase)
    return VerifiedBoundaryAdmission(
        request=request,
        boundary_id=boundary_id,
        stage_id=stage_id,
        run_id=receipt.binding["run_id"],
        batch_id=receipt.binding["batch_id"],
        admission_sha256=sha256_bytes(admission_bytes),
        payload=_deep_freeze(payload),
        input_files=_deep_freeze(files),
        _output_root=output,
        _input_tree_binding=_deep_freeze(tree),
        _boundary_input_binding=tuple(
            _deep_freeze(item) for item in boundary_input_binding
        ),
        _operation_binding=_deep_freeze(requested_operation),
        _admission_bytes=admission_bytes,
    )


def admit_boundary(
    request: BoundaryAdmissionRequest,
    *,
    boundary_id: str,
    output_root: Path,
    boundary_inputs: Mapping[str, Path],
    operation_binding: Mapping[str, Any],
) -> VerifiedBoundaryAdmission:
    """Authenticate and semantically admit one exact boundary before any write."""

    return _admit(
        request,
        boundary_id=boundary_id,
        output_root=output_root,
        boundary_inputs=boundary_inputs,
        operation_binding=operation_binding,
        phase="ENTRY_PRE_WRITE",
    )


def admit_serialized_boundary(
    request: BoundaryAdmissionRequest,
    *,
    boundary_id: str,
    output_root: Path,
    boundary_inputs: Mapping[str, Path],
    operation_binding: Mapping[str, Any],
) -> VerifiedBoundaryAdmission:
    """Admit an installed serialized-artifact request before any output write.

    CLI or queue ingestion layers call this entry after materializing their
    serialized request artifacts. It performs the same authenticated checks as
    :func:`admit_boundary`, while retaining the distinct locked failure phase
    for artifact-parse attacks.
    """

    return _admit(
        request,
        boundary_id=boundary_id,
        output_root=output_root,
        boundary_inputs=boundary_inputs,
        operation_binding=operation_binding,
        phase="ARTIFACT_VALIDATION_PRE_WRITE",
    )


__all__ = [
    "BOUNDARY_STAGE_MAP",
    "OPERATION_ARGUMENT_FIELDS",
    "OPERATION_BINDING_SCHEMA_VERSION",
    "RUN_AUTHORITY_ROOT",
    "SEMANTIC_ADMISSION_ALGORITHM",
    "SEMANTIC_ADMISSION_AUDIENCE",
    "SEMANTIC_ADMISSION_CLAIM_BOUNDARY",
    "SEMANTIC_ADMISSION_FILE",
    "SEMANTIC_ADMISSION_SCHEMA_VERSION",
    "STAGE_PREDECESSORS",
    "BoundaryAdmissionError",
    "BoundaryAdmissionRequest",
    "VerifiedBoundaryAdmission",
    "admit_boundary",
    "admit_serialized_boundary",
    "build_boundary_operation_binding",
    "build_semantic_boundary_admission",
    "issue_semantic_boundary_admission",
]
