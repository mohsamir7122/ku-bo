from __future__ import annotations

from contextlib import contextmanager
import json
import math
import os
import secrets
import signal
import stat
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import request as urllib_request

from .hashing import canonical_json_bytes, sha256_bytes
from .ingestion import (
    CapturePacketWriter,
    CaptureRequest,
    FileConnector,
    PublicHttpConnector,
    _build_public_opener,
    capture_sources,
)
from .parser_materialization import materialize_parser_run
from .source_network import (
    SourceNetworkCatalog,
    SourceNetworkRunValidator,
    validate_live_probe,
)
from .strict import parse_iso_date


STAGED_LIVE_PLAN_FIELDS = {
    "schema_version",
    "run_id",
    "product_id",
    "scope",
    "decision_delay_minutes",
    "budget",
    "binding",
    "official_capture",
    "secondary_capture",
}
CAPTURE_FIELDS = {
    "connector",
    "source_id",
    "source_url",
    "roles_observed",
    "access_mode",
    "capture_kind",
    "resource_path",
    "timeout_seconds",
    "max_bytes",
}
CAPTURE_REQUIRED_FIELDS = CAPTURE_FIELDS - {"resource_path"}
BINDING_FIELDS = {"security_code", "ticker", "isin", "valid_from", "valid_to"}
_MINIMUM_HTTP_REQUESTS_PER_CAPTURE = 2  # robots.txt followed by the requested resource
_MAX_STAGED_LIVE_PLAN_BYTES = 1024 * 1024


class _CaptureBudgetExceeded(BaseException):
    """Escape connector isolation when a run-wide request or wall budget is exhausted."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _HttpRequestBudget:
    """Count and deadline-bound every HTTPS attempt, including redirects."""

    def __init__(self, *, max_requests: int, deadline: float):
        self.max_requests = max_requests
        self.deadline = deadline
        self.requests = 0
        self._lock = threading.Lock()

    def claim(self, req: Any) -> Any:
        with self._lock:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise _CaptureBudgetExceeded("WALL_BUDGET_EXCEEDED")
            if self.requests >= self.max_requests:
                raise _CaptureBudgetExceeded("REQUEST_BUDGET_EXCEEDED")
            self.requests += 1
            try:
                requested_timeout = float(req.timeout)
            except (AttributeError, TypeError, ValueError):
                requested_timeout = remaining
            req.timeout = max(0.001, min(requested_timeout, remaining))
            return req


class _BudgetedHttpsRequestHandler(urllib_request.BaseHandler):
    """urllib request processor invoked for originals and recursive redirects."""

    def __init__(self, budget: _HttpRequestBudget):
        self._budget = budget

    def https_request(self, req: Any) -> Any:
        return self._budget.claim(req)


def _load_plan(path: Path) -> dict[str, Any]:
    required_flags = ("O_NOFOLLOW", "O_NONBLOCK")
    if any(not hasattr(os, name) for name in required_flags):
        raise ValueError(
            "staged live plan requires regular-file no-follow support"
        )
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | os.O_NONBLOCK
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(
            "staged live plan must be a readable regular non-symlink file"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(
                "staged live plan must be a readable regular non-symlink file"
            )
        if metadata.st_size > _MAX_STAGED_LIVE_PLAN_BYTES:
            raise ValueError(
                "staged live plan exceeds the bounded file-size limit"
            )
        chunks: list[bytes] = []
        remaining = _MAX_STAGED_LIVE_PLAN_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > _MAX_STAGED_LIVE_PLAN_BYTES:
            raise ValueError(
                "staged live plan exceeds the bounded file-size limit"
            )
    except OSError as exc:
        raise ValueError("staged live plan cannot be read safely") from exc
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("staged live plan must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("staged live plan must be a JSON object")
    if set(payload) != STAGED_LIVE_PLAN_FIELDS or payload.get("schema_version") != "1.0":
        raise ValueError("staged live plan has unknown/missing fields or unsupported schema_version")
    return payload


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _validate_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != BINDING_FIELDS:
        raise ValueError("binding has unknown or missing fields")
    security_code = str(value.get("security_code", "")).strip()
    ticker = str(value.get("ticker", "")).upper()
    isin = str(value.get("isin", "")).upper()
    if not security_code.isdigit():
        raise ValueError("binding.security_code must be an official numeric code")
    if not 1 <= len(ticker) <= 32 or any(not (character.isalnum() or character in "._-") for character in ticker):
        raise ValueError("binding.ticker must contain 1..32 alphanumeric or ._- characters")
    if len(isin) != 12 or not isin[:2].isalpha() or not isin[2:].isalnum() or not isin[-1].isdigit():
        raise ValueError("binding.isin must be a 12-character ISIN")
    valid_from = parse_iso_date(value.get("valid_from"), "binding.valid_from").isoformat()
    valid_to_value = value.get("valid_to")
    valid_to = None if valid_to_value is None else parse_iso_date(valid_to_value, "binding.valid_to").isoformat()
    if valid_to is not None and valid_to < valid_from:
        raise ValueError("binding.valid_to precedes valid_from")
    return {
        "security_code": security_code,
        "ticker": ticker,
        "isin": isin,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }


def _validate_capture_task(value: Any, catalog: SourceNetworkCatalog, *, expected_source: str, expected_parser: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{expected_source} capture must be an object")
    unknown = set(value) - CAPTURE_FIELDS
    missing = CAPTURE_REQUIRED_FIELDS - set(value)
    if unknown or missing:
        raise ValueError(f"{expected_source} capture has unknown or missing fields")
    if str(value.get("source_id", "")) != expected_source:
        raise ValueError(f"staged live v1 requires {expected_source} for this source slot")
    capability = catalog.capabilities[expected_source]
    if expected_parser not in capability.parser_ids:
        raise ValueError(f"{expected_source} lacks the required parser capability")
    source = catalog.sources[expected_source]
    if not source.enabled_by_default:
        raise ValueError(f"{expected_source} is not enabled by default")
    connector = str(value.get("connector", ""))
    if connector not in {"public_http", "file"}:
        raise ValueError("capture.connector must be public_http or file")
    access_mode = str(value.get("access_mode", ""))
    if access_mode not in source.access_modes:
        raise ValueError(f"{expected_source} access_mode is outside the source contract")
    if connector == "public_http" and access_mode not in {"PUBLIC_PAGE", "PUBLIC_DOWNLOAD"}:
        raise ValueError("public_http cannot use authenticated or user-export access")
    if connector == "file" and access_mode != "USER_EXPORT":
        raise ValueError("file connector in staged live v1 must use USER_EXPORT")
    resource_path = value.get("resource_path")
    if connector == "file":
        if not isinstance(resource_path, str) or not resource_path.strip():
            raise ValueError("file connector requires a non-empty resource_path")
        resource_path = resource_path.strip()
    elif resource_path not in (None, ""):
        raise ValueError("public_http resource_path must be omitted or null")
    else:
        resource_path = None
    roles = tuple(str(item) for item in value.get("roles_observed", []))
    if not roles or set(roles) - set(source.roles):
        raise ValueError(f"{expected_source} roles_observed are outside the source contract")
    timeout_seconds = value.get("timeout_seconds")
    max_bytes = value.get("max_bytes")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("capture.max_bytes must be a positive integer")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        raise ValueError("capture.timeout_seconds must be a positive number")
    return {
        "connector": connector,
        "source_id": expected_source,
        "source_url": value.get("source_url"),
        "roles_observed": roles,
        "access_mode": access_mode,
        "capture_kind": str(value.get("capture_kind", "")),
        "resource_path": resource_path,
        "timeout_seconds": timeout_seconds,
        "max_bytes": max_bytes,
    }


def _capture_request(task: dict[str, Any], catalog: SourceNetworkCatalog, user_agent: str | None) -> CaptureRequest:
    source = catalog.sources[task["source_id"]]
    values = {
        "source_id": task["source_id"],
        "source_url": task["source_url"],
        "allowed_domains": source.domains,
        "roles_observed": task["roles_observed"],
        "access_mode": task["access_mode"],
        "capture_kind": task["capture_kind"],
        "resource_path": task["resource_path"],
        "timeout_seconds": task["timeout_seconds"],
        "max_bytes": task["max_bytes"],
    }
    if user_agent:
        values["user_agent"] = user_agent
    return CaptureRequest(**values)


def _capture_tasks(
    *,
    official: dict[str, Any],
    secondary: dict[str, Any],
    catalog: SourceNetworkCatalog,
    fixture_root: Path | None,
    user_agent: str | None,
    http_budget: _HttpRequestBudget,
) -> list[tuple[Any, CaptureRequest]]:
    file_connector = FileConnector(fixture_root) if fixture_root is not None else None
    tasks: list[tuple[Any, CaptureRequest]] = []
    for task in (official, secondary):
        capture_request = _capture_request(task, catalog, user_agent)
        if task["connector"] == "file":
            if file_connector is None:
                raise ValueError("file connector requires --fixture-root")
            connector = file_connector
        else:
            opener = _build_public_opener(capture_request.allowed_domains)
            opener.add_handler(_BudgetedHttpsRequestHandler(http_budget))
            connector = PublicHttpConnector(opener=opener)
        tasks.append((connector, capture_request))
    return tasks


def _artifact_by_source(run_root: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("capture manifest artifacts must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in artifacts:
        if not isinstance(row, dict):
            raise ValueError("capture manifest artifact must be an object")
        source_id = str(row.get("source_id", ""))
        if source_id in result:
            raise ValueError("staged live v1 expects exactly one artifact per source")
        result[source_id] = row
    return result


def _artifact_receipt(
    item: Any,
    artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    artifact_row = artifacts.get(item.source_id)
    if artifact_row is None:
        return None
    return {
        "path": artifact_row["path"],
        "sha256": artifact_row["sha256"],
        "size_bytes": artifact_row["size_bytes"],
        "content_type": (item.content_type or "application/octet-stream").lower(),
        "capture_kind": artifact_row["capture_kind"],
    }


def _write_access_probe(run_root: Path, results: tuple[Any, ...], artifacts: dict[str, dict[str, Any]]) -> Path:
    observed_values = [item.observed_at for item in results if item.observed_at is not None]
    attempted_values = [item.attempted_at for item in results]
    observed_at = max(observed_values or attempted_values)
    sources: list[dict[str, Any]] = []
    for item in sorted(results, key=lambda result: result.source_id):
        artifact = _artifact_receipt(item, artifacts)
        sources.append(
            {
                "source_id": item.source_id,
                "state": item.state,
                "tested_url": item.source_url,
                "final_url": item.final_url,
                "attempted_at": item.attempted_at.isoformat(),
                "http_status": item.http_status,
                "observation": (
                    "Staged limited capture receipt. This proves bounded access/capture only; "
                    "market facts require parser materialization and network validation."
                ),
                "data_quality_flags": sorted(set(item.data_quality_flags)),
                "artifact": artifact,
            }
        )
    payload = {
        "schema_version": "3.1-access-probe",
        "probe_id": f"staged-limited-{sha256_bytes((run_root.as_posix() + observed_at.isoformat()).encode('utf-8'))[:16]}",
        "probe_version": "staged-limited-v1",
        "observed_at": observed_at.isoformat(),
        "expires_at": (observed_at + timedelta(hours=24)).isoformat(),
        "purpose": "Limited staged live access/capture receipt for one official source and one secondary source.",
        "sources": sources,
    }
    path = run_root / "access_probe.json"
    path.write_bytes(canonical_json_bytes(payload))
    return path


def _write_fixture_receipt(
    run_root: Path,
    results: tuple[Any, ...],
    artifacts: dict[str, dict[str, Any]],
    *,
    capture_status: str,
) -> Path:
    """Write a non-live receipt for deterministic fixture plumbing.

    A fixture read has no HTTP response and therefore must not be encoded as a
    live access probe or assigned a synthetic HTTP status.  This separate
    receipt is intentionally machine-readable but has no validity window and
    cannot be passed to ``validate_live_probe``.
    """

    observed_values = [item.observed_at for item in results if item.observed_at is not None]
    attempted_values = [item.attempted_at for item in results]
    observed_at = max(observed_values or attempted_values)
    sources = []
    for item in sorted(results, key=lambda result: result.source_id):
        sources.append(
            {
                "source_id": item.source_id,
                "state": item.state,
                "source_url": item.source_url,
                "attempted_at": item.attempted_at.isoformat(),
                "observed_at": None
                if item.observed_at is None
                else item.observed_at.isoformat(),
                "http_status": item.http_status,
                "data_quality_flags": sorted(
                    {*item.data_quality_flags, "FIXTURE_INPUT"}
                ),
                "artifact": _artifact_receipt(item, artifacts),
            }
        )
    payload = {
        "schema_version": "1.0-fixture-plumbing-receipt",
        "receipt_id": (
            "fixture-plumbing-"
            + sha256_bytes(
                (run_root.as_posix() + observed_at.isoformat()).encode("utf-8")
            )[:16]
        ),
        "receipt_type": "FIXTURE_PLUMBING",
        "status": "PLUMBING_CAPTURED"
        if capture_status == "COMPLETE"
        else "PLUMBING_DEGRADED",
        "observed_at": observed_at.isoformat(),
        "sources": sources,
        "claim_boundaries": {
            "fixture_receipt_is_live_access_probe": False,
            "fixture_receipt_proves_http_access": False,
            "fixture_receipt_is_market_evidence": False,
        },
    }
    path = run_root / "fixture_plumbing_receipt.json"
    path.write_bytes(canonical_json_bytes(payload))
    return path


def _same_inode(metadata: os.stat_result, expected: tuple[int, int]) -> bool:
    return (metadata.st_dev, metadata.st_ino) == expected


def _secure_directory_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise ValueError("secure output transaction requires directory no-follow support")
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _lexical_output_root(path: Path) -> Path:
    raw = Path(path)
    if raw.name in {"", ".", ".."} or ".." in raw.parts:
        raise ValueError("output_root must identify a dedicated directory")
    absolute = Path(os.path.abspath(raw if raw.is_absolute() else Path.cwd() / raw))
    if absolute == Path(absolute.anchor):
        raise ValueError("output_root must not be a filesystem root")
    return absolute


def _open_parent_dirfd(path: Path, *, create: bool) -> tuple[Path, int]:
    """Walk the lexical parent with openat/O_NOFOLLOW and return its held fd."""

    absolute = _lexical_output_root(path)
    flags = _secure_directory_flags()
    try:
        current_fd = os.open(absolute.anchor, flags)
    except OSError as exc:
        raise ValueError("output_root anchor cannot be opened safely") from exc
    try:
        for component in absolute.parent.parts[1:]:
            try:
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except FileNotFoundError:
                if not create:
                    raise ValueError("output_root parent changed before publish")
                try:
                    os.mkdir(component, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise ValueError(
                        "output_root parent cannot be created safely"
                    ) from exc
                try:
                    next_fd = os.open(component, flags, dir_fd=current_fd)
                except OSError as exc:
                    raise ValueError(
                        "output_root parent cannot be opened safely"
                    ) from exc
            except OSError as exc:
                try:
                    metadata = os.stat(
                        component,
                        dir_fd=current_fd,
                        follow_symlinks=False,
                    )
                except OSError:
                    metadata = None
                if metadata is not None and stat.S_ISLNK(metadata.st_mode):
                    raise ValueError(
                        "output_root parent contains a symlink component"
                    ) from exc
                raise ValueError("output_root parent cannot be opened safely") from exc
            os.close(current_fd)
            current_fd = next_fd
        return absolute, current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _entry_metadata(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("output transaction entry cannot be inspected safely") from exc


def _clear_directory_fd(directory_fd: int) -> None:
    """Delete only descendants of the already-open owned directory inode."""

    flags = _secure_directory_flags()
    for name in os.listdir(directory_fd):
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(name, flags, dir_fd=directory_fd)
            try:
                if not _same_inode(os.fstat(child_fd), (metadata.st_dev, metadata.st_ino)):
                    raise ValueError("staging child changed during cleanup")
                _clear_directory_fd(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


@contextmanager
def _defer_sigalrm_for_identity() -> Any:
    """Defer the wall signal only while a new inode gains an owned identity."""

    required = ("pthread_sigmask", "SIG_BLOCK", "SIG_SETMASK", "SIGALRM")
    if any(not hasattr(signal, name) for name in required):
        raise ValueError(
            "secure output transaction requires SIGALRM mask support"
        )
    previous_mask = signal.pthread_sigmask(
        signal.SIG_BLOCK,
        {signal.SIGALRM},
    )
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


class _OutputTransaction:
    """Dirfd-anchored staging with inode-bound cleanup and atomic publish."""

    def __init__(
        self,
        output_root: Path,
        *,
        before_teardown: Callable[[], None] | None = None,
    ):
        # Deliberately no filesystem inspection before __enter__; the secure
        # walk and the first identity snapshot occur under the hard wall.
        self.requested_output_root = Path(output_root)
        self._before_teardown = before_teardown
        self._teardown_prepared = False
        self.output_root: Path | None = None
        self.output_name = ""
        self.lock_name = ""
        self.work_name = ""
        self.work_root: Path | None = None
        self.parent_fd: int | None = None
        self.work_fd: int | None = None
        self._parent_identity: tuple[int, int] | None = None
        self._lock_identity: tuple[int, int] | None = None
        self._work_identity: tuple[int, int] | None = None
        self.published = False
        self.committed = False

    def __enter__(self) -> _OutputTransaction:
        try:
            absolute, parent_fd = _open_parent_dirfd(
                self.requested_output_root,
                create=True,
            )
            self.output_root = absolute
            self.output_name = absolute.name
            self.parent_fd = parent_fd
            parent_metadata = os.fstat(parent_fd)
            self._parent_identity = (
                parent_metadata.st_dev,
                parent_metadata.st_ino,
            )
            existing_output = _entry_metadata(parent_fd, self.output_name)
            if existing_output is not None:
                if stat.S_ISLNK(existing_output.st_mode):
                    raise ValueError("output_root itself must not be a symlink")
                raise ValueError(
                    "output_root must not exist; staged runs publish by atomic rename"
                )

            digest = sha256_bytes(os.fsencode(str(absolute)))[:16]
            self.lock_name = f".kubo-stage-live-limited-{digest}.lock"
            self.work_name = (
                f".kubo-stage-live-limited-{digest}-{secrets.token_hex(8)}"
            )
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
            )
            with _defer_sigalrm_for_identity():
                try:
                    descriptor = os.open(
                        self.lock_name,
                        flags,
                        0o600,
                        dir_fd=parent_fd,
                    )
                except FileExistsError as exc:
                    raise ValueError(
                        "output_root is reserved by another staged invocation"
                    ) from exc
                except OSError as exc:
                    raise ValueError(
                        "output_root cannot be reserved safely"
                    ) from exc
                try:
                    lock_metadata = os.fstat(descriptor)
                    self._lock_identity = (
                        lock_metadata.st_dev,
                        lock_metadata.st_ino,
                    )
                finally:
                    os.close(descriptor)

            if _entry_metadata(parent_fd, self.output_name) is not None:
                raise ValueError("output_root appeared while it was being reserved")
            with _defer_sigalrm_for_identity():
                os.mkdir(self.work_name, 0o700, dir_fd=parent_fd)
                created_metadata = _entry_metadata(parent_fd, self.work_name)
                if created_metadata is None or not stat.S_ISDIR(
                    created_metadata.st_mode
                ):
                    raise ValueError(
                        "staging directory creation could not be verified"
                    )
                self._work_identity = (
                    created_metadata.st_dev,
                    created_metadata.st_ino,
                )
            work_fd = os.open(
                self.work_name,
                _secure_directory_flags(),
                dir_fd=parent_fd,
            )
            self.work_fd = work_fd
            work_metadata = os.fstat(work_fd)
            if not _same_inode(work_metadata, self._work_identity):
                raise ValueError("staging directory changed while it was opened")
            self.work_root = Path(f"/proc/self/fd/{work_fd}")
            if not self.work_root.is_dir():
                raise ValueError("fd-backed staging path is unavailable")
            return self
        except BaseException:
            try:
                self._prepare_teardown()
            finally:
                self._abort()
            raise

    def publish(self) -> None:
        if (
            self.published
            or self.parent_fd is None
            or self.work_fd is None
            or self._work_identity is None
            or self.output_root is None
        ):
            raise ValueError("staged output transaction is not publishable")
        self._revalidate_parent_path()
        if _entry_metadata(self.parent_fd, self.output_name) is not None:
            raise ValueError("output_root appeared before atomic publish")
        work_metadata = _entry_metadata(self.parent_fd, self.work_name)
        if work_metadata is None or not _same_inode(
            work_metadata,
            self._work_identity,
        ):
            raise ValueError("staging directory changed before atomic publish")
        if not _same_inode(os.fstat(self.work_fd), self._work_identity):
            raise ValueError("staging directory descriptor changed unexpectedly")
        os.rename(
            self.work_name,
            self.output_name,
            src_dir_fd=self.parent_fd,
            dst_dir_fd=self.parent_fd,
        )
        published_metadata = _entry_metadata(self.parent_fd, self.output_name)
        if published_metadata is None or not _same_inode(
            published_metadata,
            self._work_identity,
        ):
            raise ValueError("atomic publish identity verification failed")
        self._revalidate_parent_path()
        self.published = True

    def commit(self) -> None:
        """Keep a published inode only after the caller completes its cutoff."""

        if (
            not self.published
            or self.parent_fd is None
            or self.work_fd is None
            or self._work_identity is None
        ):
            raise ValueError("staged output transaction is not published")
        self._revalidate_parent_path()
        published_metadata = _entry_metadata(self.parent_fd, self.output_name)
        if published_metadata is None or not _same_inode(
            published_metadata,
            self._work_identity,
        ):
            raise ValueError("published output changed before commit")
        if not _same_inode(os.fstat(self.work_fd), self._work_identity):
            raise ValueError("published output descriptor changed before commit")
        self.committed = True

    def __exit__(self, exc_type: Any, _exc: Any, _traceback: Any) -> bool:
        try:
            self._prepare_teardown()
        except BaseException:
            self._abort()
            raise
        keep_published = exc_type is None and self.published and self.committed
        if keep_published:
            try:
                self._close_work()
                self._release_lock()
                self._close_parent()
            except BaseException:
                self._abort()
                raise
        else:
            self._abort()
        if exc_type is None and self.published and not self.committed:
            raise ValueError(
                "published output was not committed after the hard-wall cutoff"
            )
        return False

    def _prepare_teardown(self) -> None:
        if self._teardown_prepared:
            return
        if self._before_teardown is not None:
            self._before_teardown()
        self._teardown_prepared = True

    def _revalidate_parent_path(self) -> None:
        if self.parent_fd is None or self._parent_identity is None:
            raise ValueError("output parent descriptor is unavailable")
        absolute, fresh_fd = _open_parent_dirfd(
            self.requested_output_root,
            create=False,
        )
        try:
            fresh_metadata = os.fstat(fresh_fd)
            if self.output_root != absolute or not _same_inode(
                fresh_metadata,
                self._parent_identity,
            ):
                raise ValueError("output_root parent changed before publish")
        finally:
            os.close(fresh_fd)

    def _abort(self) -> None:
        if (
            self.work_fd is None
            and self.parent_fd is not None
            and self._work_identity is not None
        ):
            for name in (self.work_name, self.output_name):
                metadata = _entry_metadata(self.parent_fd, name) if name else None
                if metadata is None or not _same_inode(
                    metadata,
                    self._work_identity,
                ):
                    continue
                candidate_fd = os.open(
                    name,
                    _secure_directory_flags(),
                    dir_fd=self.parent_fd,
                )
                if not _same_inode(os.fstat(candidate_fd), self._work_identity):
                    os.close(candidate_fd)
                    raise ValueError("owned staging inode changed during abort")
                self.work_fd = candidate_fd
                break
        if self.work_fd is not None:
            _clear_directory_fd(self.work_fd)
        if self.parent_fd is not None and self._work_identity is not None:
            for name in (self.work_name, self.output_name):
                metadata = _entry_metadata(self.parent_fd, name) if name else None
                if metadata is not None and _same_inode(
                    metadata,
                    self._work_identity,
                ):
                    os.rmdir(name, dir_fd=self.parent_fd)
        self._close_work()
        self._release_lock()
        self._close_parent()

    def _close_work(self) -> None:
        if self.work_fd is None:
            return
        os.close(self.work_fd)
        self.work_fd = None

    def _release_lock(self) -> None:
        if self.parent_fd is None or self._lock_identity is None:
            return
        metadata = _entry_metadata(self.parent_fd, self.lock_name)
        if metadata is not None and stat.S_ISREG(metadata.st_mode) and _same_inode(
            metadata, self._lock_identity
        ):
            os.unlink(self.lock_name, dir_fd=self.parent_fd)
        self._lock_identity = None

    def _close_parent(self) -> None:
        if self.parent_fd is None:
            return
        os.close(self.parent_fd)
        self.parent_fd = None


class _HardWall:
    """One-shot wall whose explicit cutoff precedes unmetered teardown."""

    def __init__(self, deadline: float):
        self.deadline = deadline
        self._previous_handler: Any = None
        self._armed = False
        self._handler_installed = False
        self._stopped_at: float | None = None
        self.cutoff_complete = False

    def arm(self) -> None:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise _CaptureBudgetExceeded("WALL_BUDGET_EXCEEDED")
        required_signal_support = (
            "SIGALRM",
            "ITIMER_REAL",
            "pthread_sigmask",
            "SIG_BLOCK",
            "SIG_SETMASK",
        )
        if any(not hasattr(signal, name) for name in required_signal_support):
            raise ValueError(
                "hard wall requires SIGALRM, ITIMER_REAL, and signal-mask support"
            )
        if threading.current_thread() is not threading.main_thread():
            raise ValueError("hard wall requires execution on the main thread")
        if threading.active_count() != 1:
            raise ValueError(
                "hard wall requires a single-threaded invocation for signal safety"
            )
        if signal.getitimer(signal.ITIMER_REAL)[0] > 0:
            raise ValueError(
                "hard wall refuses to replace an existing real-time timer"
            )

        self._previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self._deadline_reached)
        self._handler_installed = True
        self._armed = True
        try:
            signal.setitimer(signal.ITIMER_REAL, remaining)
        except BaseException:
            self.disarm()
            raise

    def _deadline_reached(self, _signum: int, _frame: Any) -> None:
        # Disarm and restore the caller's handler before stack unwinding can
        # enter transaction abort/teardown code.
        self.disarm()
        raise _CaptureBudgetExceeded("WALL_BUDGET_EXCEEDED")

    def disarm(self, *, stopped_at: float | None = None) -> None:
        if self._stopped_at is None:
            self._stopped_at = (
                time.monotonic() if stopped_at is None else stopped_at
            )
        if self._armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            self._armed = False
        if self._handler_installed:
            signal.signal(signal.SIGALRM, self._previous_handler)
            self._handler_installed = False

    def cutoff(
        self,
        *,
        started: float | None = None,
        expected_usage: int | None = None,
    ) -> int | None:
        """Check the deadline/usage and disarm at the publish-complete cutoff."""

        checked_at = time.monotonic()
        actual_usage = (
            None
            if started is None
            else int(math.ceil(max(1.0, checked_at - started)))
        )
        if checked_at >= self.deadline:
            self.disarm(stopped_at=checked_at)
            raise _CaptureBudgetExceeded("WALL_BUDGET_EXCEEDED")
        if expected_usage is not None and actual_usage != expected_usage:
            self.disarm(stopped_at=checked_at)
            raise _CaptureBudgetExceeded("WALL_USAGE_UNSTABLE")
        self.disarm(stopped_at=checked_at)
        self.cutoff_complete = True
        return actual_usage

    def elapsed_seconds(self, started: float) -> int:
        endpoint = self._stopped_at
        if endpoint is None:
            endpoint = time.monotonic()
        return int(math.ceil(max(1.0, endpoint - started)))


@contextmanager
def _hard_wall(deadline: float):
    """Arm a fail-closed wall and restore signal state before exit."""

    wall = _HardWall(deadline)
    wall.arm()
    try:
        yield wall
    except BaseException:
        wall.disarm()
        raise
    else:
        if not wall.cutoff_complete:
            wall.cutoff()
    finally:
        wall.disarm()


def _budget_exceeded_report(
    *,
    fixture_mode: bool,
    reason_code: str,
    usage_http_requests: int,
    usage_wall_seconds: int,
    batch: Any | None = None,
) -> dict[str, Any]:
    return {
        "status": "CAPTURE_DEGRADED",
        "reason_code": reason_code,
        "execution_mode": "FIXTURE_PLUMBING" if fixture_mode else "PUBLIC_HTTP",
        "usage_http_requests": usage_http_requests,
        "usage_wall_seconds": usage_wall_seconds,
        "capture": None if batch is None else batch.to_dict(),
        "write": None,
        "access_probe": None,
        "fixture_receipt": None,
        "materialized": None,
        "claim_boundaries": _claim_boundaries(),
    }


def _finalize_materialized_usage(
    *,
    run_root: Path,
    parser_plan: dict[str, Any],
    parser_plan_path: Path,
    materialized: dict[str, Any],
    catalog: SourceNetworkCatalog,
    product_id: str,
    started: float,
    usage_http_requests: int,
) -> tuple[int, dict[str, Any]]:
    """Converge post-validation usage and its parser-plan hash binding."""

    budget = parser_plan["budget"]
    if usage_http_requests > budget["max_requests"]:
        raise _CaptureBudgetExceeded("REQUEST_BUDGET_EXCEEDED")

    observations_path = run_root / "source_observations.json"
    research_run_path = run_root / "research_run.json"
    try:
        observations = json.loads(observations_path.read_text(encoding="utf-8"))
        research_run = json.loads(research_run_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("materialized usage files must be valid UTF-8 JSON") from exc
    if not isinstance(observations, dict) or not isinstance(
        observations.get("sources"), list
    ):
        raise ValueError("materialized source observations are invalid")
    if not isinstance(research_run, dict) or not isinstance(
        research_run.get("usage"), dict
    ):
        raise ValueError("materialized research usage is invalid")

    finalized = dict(materialized)
    old_plan_hash = str(finalized["parser_plan_sha256"])
    for _attempt in range(8):
        usage_wall_seconds = int(
            math.ceil(max(1.0, time.monotonic() - started))
        )
        if usage_wall_seconds > budget["max_wall_seconds"]:
            raise _CaptureBudgetExceeded("WALL_BUDGET_EXCEEDED")

        parser_plan["usage_wall_seconds"] = usage_wall_seconds
        parser_plan_bytes = canonical_json_bytes(parser_plan)
        new_plan_hash = sha256_bytes(parser_plan_bytes)
        old_limitation = f"PARSER_PLAN_SHA256:{old_plan_hash}"
        new_limitation = f"PARSER_PLAN_SHA256:{new_plan_hash}"
        replacements = 0
        for source in observations["sources"]:
            if not isinstance(source, dict) or not isinstance(
                source.get("limitations"), list
            ):
                raise ValueError("materialized source limitations are invalid")
            rewritten = []
            for limitation in source["limitations"]:
                if limitation == old_limitation:
                    rewritten.append(new_limitation)
                    replacements += 1
                else:
                    rewritten.append(limitation)
            source["limitations"] = sorted(set(rewritten))
        if replacements == 0 and new_plan_hash != old_plan_hash:
            raise ValueError("materialized parser-plan hash binding is missing")

        research_run["usage"]["requests"] = usage_http_requests
        research_run["usage"]["wall_seconds"] = usage_wall_seconds
        parser_plan_path.write_bytes(parser_plan_bytes)
        observations_path.write_bytes(canonical_json_bytes(observations))
        research_run_path.write_bytes(canonical_json_bytes(research_run))

        validation = SourceNetworkRunValidator(run_root, catalog, product_id).validate()
        if validation.status == "BLOCKED":
            raise ValueError(
                "finalized staged run failed network validation: "
                + ";".join(validation.structural_errors)
            )
        finalized["parser_plan_sha256"] = new_plan_hash
        finalized["network_validation"] = validation.to_dict()
        measured_after_validation = int(
            math.ceil(max(1.0, time.monotonic() - started))
        )
        if measured_after_validation == usage_wall_seconds:
            return usage_wall_seconds, finalized
        old_plan_hash = new_plan_hash

    raise _CaptureBudgetExceeded("WALL_USAGE_UNSTABLE")


def stage_limited_live_run(
    *,
    plan_path: Path,
    output_root: Path,
    catalog: SourceNetworkCatalog,
    fixture_root: Path | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Run a bounded official+secondary capture, then materialize through existing parsers.

    Version 1 is deliberately narrow: one official Boursa identity artifact,
    one Investing history artifact, and one named security binding. It stages
    live plumbing without upgrading any source to live-operational status.
    Wall usage ends only after atomic publish and its final usage check. The
    timer is disarmed before abort or committed-output teardown, so cleanup is
    never interrupted and is not included in reported wall usage.
    """

    started = time.monotonic()
    plan = _load_plan(plan_path)
    run_id = str(plan.get("run_id", "")).strip()
    product_id = str(plan.get("product_id", "")).strip()
    scope = str(plan.get("scope", ""))
    if not run_id or product_id not in catalog.product_to_policy:
        raise ValueError("run_id/product_id is invalid")
    if scope != "NAMED_SECURITIES":
        raise ValueError("staged live v1 supports NAMED_SECURITIES only")
    decision_delay_minutes = _non_negative_int(
        plan.get("decision_delay_minutes"), "decision_delay_minutes"
    )
    if decision_delay_minutes > 60:
        raise ValueError("decision_delay_minutes cannot exceed 60")
    decision_delay_seconds = decision_delay_minutes * 60
    budget = plan.get("budget")
    if not isinstance(budget, dict) or set(budget) != {"max_requests", "max_raw_bytes", "max_wall_seconds"}:
        raise ValueError("budget is invalid")
    budget = {key: _positive_int(value, f"budget.{key}") for key, value in budget.items()}
    binding = _validate_binding(plan.get("binding"))
    official = _validate_capture_task(
        plan.get("official_capture"),
        catalog,
        expected_source="boursa_current",
        expected_parser="boursa_identity_html_v1",
    )
    secondary = _validate_capture_task(
        plan.get("secondary_capture"),
        catalog,
        expected_source="investing_history",
        expected_parser="investing_history_html_v1",
    )
    connectors = {official["connector"], secondary["connector"]}
    if len(connectors) != 1:
        raise ValueError("staged live v1 cannot mix fixture and public_http connectors")
    fixture_mode = connectors == {"file"}
    minimum_http_requests = (
        0
        if fixture_mode
        else _MINIMUM_HTTP_REQUESTS_PER_CAPTURE * 2
    )
    if budget["max_requests"] < minimum_http_requests:
        raise ValueError(
            "budget.max_requests cannot cover robots.txt and resource requests "
            "for both public captures"
        )
    if official["max_bytes"] + secondary["max_bytes"] > budget["max_raw_bytes"]:
        raise ValueError("capture task byte ceilings exceed budget.max_raw_bytes")
    planned_wall_seconds = (
        decision_delay_seconds
        + float(official["timeout_seconds"])
        + float(secondary["timeout_seconds"])
    )
    if planned_wall_seconds > budget["max_wall_seconds"]:
        raise ValueError(
            "decision delay and capture task timeout ceilings exceed "
            "budget.max_wall_seconds"
        )

    deadline = started + budget["max_wall_seconds"]
    http_budget = _HttpRequestBudget(
        max_requests=budget["max_requests"],
        deadline=deadline,
    )

    batch = None
    hard_wall: _HardWall | None = None
    try:
        with _hard_wall(deadline) as hard_wall:
            tasks = _capture_tasks(
                official=official,
                secondary=secondary,
                catalog=catalog,
                fixture_root=fixture_root,
                user_agent=user_agent,
                http_budget=http_budget,
            )
            with _OutputTransaction(
                output_root,
                before_teardown=hard_wall.disarm,
            ) as transaction:
                work_root = transaction.work_root
                if work_root is None or transaction.work_fd is None:
                    raise ValueError("secure staging directory is unavailable")
                batch = capture_sources(tasks)
                with CapturePacketWriter(
                    work_root,
                    run_root_fd=transaction.work_fd,
                ) as writer:
                    write = writer.write(batch.results)
                artifacts = _artifact_by_source(work_root)
                if fixture_mode:
                    _write_fixture_receipt(
                        work_root,
                        batch.results,
                        artifacts,
                        capture_status=batch.status,
                    )
                    fixture_receipt = {
                        "status": "PLUMBING_CAPTURED"
                        if batch.status == "COMPLETE"
                        else "PLUMBING_DEGRADED",
                        "path": str(
                            transaction.output_root / "fixture_plumbing_receipt.json"
                        ),
                    }
                    probe_report = None
                else:
                    probe_path = _write_access_probe(
                        work_root, batch.results, artifacts
                    )
                    probe_report = validate_live_probe(probe_path, catalog)
                    fixture_receipt = None

                if (
                    batch.status != "COMPLETE"
                    or write.status != "COMPLETE"
                    or (
                        probe_report is not None
                        and probe_report["status"] != "PASS"
                    )
                ):
                    usage_wall_seconds = int(
                        math.ceil(max(1.0, time.monotonic() - started))
                    )
                    report = {
                        "status": "CAPTURE_DEGRADED",
                        "execution_mode": (
                            "FIXTURE_PLUMBING" if fixture_mode else "PUBLIC_HTTP"
                        ),
                        "usage_http_requests": http_budget.requests,
                        "usage_wall_seconds": usage_wall_seconds,
                        "capture": batch.to_dict(),
                        "write": write.to_dict(),
                        "access_probe": probe_report,
                        "fixture_receipt": fixture_receipt,
                        "materialized": None,
                        "claim_boundaries": _claim_boundaries(),
                    }
                    transaction.publish()
                    report["usage_wall_seconds"] = hard_wall.cutoff(
                        started=started,
                    )
                    transaction.commit()
                    return report

                if decision_delay_seconds:
                    time.sleep(decision_delay_seconds)
                observed = max(
                    item.observed_at
                    for item in batch.results
                    if item.observed_at is not None
                )
                decision_at = datetime.now(timezone.utc)
                if observed > decision_at:
                    report = {
                        "status": "CAPTURE_DEGRADED",
                        "reason_code": "FUTURE_CAPTURE_TIMESTAMP",
                        "execution_mode": (
                            "FIXTURE_PLUMBING" if fixture_mode else "PUBLIC_HTTP"
                        ),
                        "usage_http_requests": http_budget.requests,
                        "usage_wall_seconds": int(
                            math.ceil(max(1.0, time.monotonic() - started))
                        ),
                        "capture": batch.to_dict(),
                        "write": write.to_dict(),
                        "access_probe": probe_report,
                        "fixture_receipt": fixture_receipt,
                        "materialized": None,
                        "claim_boundaries": _claim_boundaries(),
                    }
                    transaction.publish()
                    report["usage_wall_seconds"] = hard_wall.cutoff(
                        started=started,
                    )
                    transaction.commit()
                    return report

                parser_plan = {
                    "schema_version": "1.0",
                    "run_id": run_id,
                    "product_id": product_id,
                    "decision_at": decision_at.isoformat(),
                    "scope": scope,
                    "budget": budget,
                    "usage_wall_seconds": 0,
                    "bindings": [
                        {
                            **binding,
                            "official_artifact_sha256": artifacts["boursa_current"][
                                "sha256"
                            ],
                            "secondary_artifact_sha256": artifacts[
                                "investing_history"
                            ]["sha256"],
                        }
                    ],
                    "parser_tasks": [
                        {
                            "parser_id": "boursa_identity_html_v1",
                            "artifact_sha256": artifacts["boursa_current"]["sha256"],
                        },
                        {
                            "parser_id": "investing_history_html_v1",
                            "artifact_sha256": artifacts["investing_history"][
                                "sha256"
                            ],
                        },
                    ],
                }
                parser_plan_path = work_root / "parser_plan.json"
                parser_plan_path.write_bytes(canonical_json_bytes(parser_plan))
                materialized = materialize_parser_run(
                    capture_root=work_root,
                    parser_plan_path=parser_plan_path,
                    catalog=catalog,
                )
                usage_wall_seconds, materialized = _finalize_materialized_usage(
                    run_root=work_root,
                    parser_plan=parser_plan,
                    parser_plan_path=parser_plan_path,
                    materialized=materialized,
                    catalog=catalog,
                    product_id=product_id,
                    started=started,
                    usage_http_requests=http_budget.requests,
                )
                materialized["materialized_run"] = str(transaction.output_root)
                report = {
                    "status": "PLUMBING_PASS",
                    "execution_mode": (
                        "FIXTURE_PLUMBING" if fixture_mode else "PUBLIC_HTTP"
                    ),
                    "usage_http_requests": http_budget.requests,
                    "usage_wall_seconds": usage_wall_seconds,
                    "capture": batch.to_dict(),
                    "write": write.to_dict(),
                    "access_probe": probe_report,
                    "fixture_receipt": fixture_receipt,
                    "parser_plan": str(
                        transaction.output_root / "parser_plan.json"
                    ),
                    "materialized": materialized,
                    "claim_boundaries": _claim_boundaries(),
                }
                transaction.publish()
                hard_wall.cutoff(
                    started=started,
                    expected_usage=usage_wall_seconds,
                )
                transaction.commit()
                return report
    except _CaptureBudgetExceeded as exc:
        return _budget_exceeded_report(
            fixture_mode=fixture_mode,
            reason_code=exc.reason_code,
            usage_http_requests=http_budget.requests,
            usage_wall_seconds=(
                hard_wall.elapsed_seconds(started)
                if hard_wall is not None
                else int(math.ceil(max(1.0, time.monotonic() - started)))
            ),
            batch=batch,
        )


def _claim_boundaries() -> dict[str, bool]:
    return {
        "staged_run_upgrades_sources_to_live_operational": False,
        "capture_success_is_market_evidence": False,
        "secondary_price_is_execution_price": False,
        "forecast_or_recommendation_performed": False,
        "external_source_availability_is_guaranteed": False,
    }


__all__ = ["stage_limited_live_run"]
