from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterator

from .ingestion import (
    CapturePacketWriter,
    CaptureRequest,
    FileConnector,
    PublicHttpConnector,
    capture_sources,
)
from .source_network import SourceNetworkCatalog


MAX_CAPTURE_PLAN_TASKS = 32
MAX_CAPTURE_PLAN_BYTES = 128 * 1024 * 1024
MAX_CAPTURE_PLAN_TIMEOUT_SECONDS = 300.0
DEFAULT_CAPTURE_TASK_BYTES = 5 * 1024 * 1024
DEFAULT_CAPTURE_TASK_TIMEOUT_SECONDS = 15.0
_OUTPUT_RESERVATION_NAME = ".kubo-capture-plan-reservation"


@dataclass(frozen=True)
class _ReservedOutputRoot:
    path: Path
    fd: int
    parent_fd: int
    final_component: str
    device: int
    inode: int

    def assert_named_identity(self) -> None:
        try:
            held = os.fstat(self.fd)
            named = os.stat(
                self.final_component,
                dir_fd=self.parent_fd,
                follow_symlinks=False,
            )
            marker = os.stat(
                _OUTPUT_RESERVATION_NAME,
                dir_fd=self.fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError("output_root identity changed during capture") from exc
        expected = (self.device, self.inode)
        if (
            not stat.S_ISDIR(held.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or not stat.S_ISREG(marker.st_mode)
            or (held.st_dev, held.st_ino) != expected
            or (named.st_dev, named.st_ino) != expected
        ):
            raise ValueError("output_root identity changed during capture")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("capture plan must be a JSON object")
    if "max_requests" in value or "budget" in value:
        raise ValueError(
            "capture plan does not accept max_requests budgets; "
            "the task limit is not a network-transport request budget"
        )
    unknown = sorted(set(value) - {"schema_version", "tasks"})
    if unknown:
        raise ValueError("unknown capture-plan fields: " + ",".join(unknown))
    if value.get("schema_version") != "1.0":
        raise ValueError("capture plan schema_version must be 1.0")
    if not isinstance(value.get("tasks"), list) or not value["tasks"]:
        raise ValueError("capture plan tasks must be a non-empty list")
    if len(value["tasks"]) > MAX_CAPTURE_PLAN_TASKS:
        raise ValueError(
            f"capture plan exceeds task limit of {MAX_CAPTURE_PLAN_TASKS}"
        )
    return value


@contextmanager
def _reserve_output_root(output_root: Path) -> Iterator[_ReservedOutputRoot]:
    """Reserve one new/empty output directory for this invocation only.

    The exclusive marker closes the common check-then-use race between two
    capture-plan processes.  A crashed process deliberately leaves either the
    marker or partial output behind, so a later invocation fails closed rather
    than replacing evidence from the earlier attempt.
    """

    requested = Path(output_root)
    if requested.is_absolute():
        start = Path(requested.anchor)
        components = requested.parts[1:]
    else:
        start = Path.cwd()
        components = requested.parts
    if (
        not components
        or any(component in {"", ".", ".."} for component in components)
    ):
        raise ValueError("output_root must identify a dedicated directory")
    required_dirfd_functions = (os.open, os.mkdir, os.unlink, os.rmdir)
    if not (
        os.name == "posix"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and all(function in os.supports_dir_fd for function in required_dirfd_functions)
        and os.listdir in os.supports_fd
    ):
        raise RuntimeError(
            "secure output_root reservation requires dir_fd and no-follow support"
        )

    directory_flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    marker_flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    parent_fd = os.open(start, directory_flags)
    root_fd = -1
    marker_fd = -1
    final_component = components[-1]
    created = False
    reservation_created = False
    root_identity: tuple[int, int] | None = None
    try:
        for component in components[:-1]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
            try:
                next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            except OSError as exc:
                raise ValueError(
                    "output_root parent contains a symlink or non-directory"
                ) from exc
            os.close(parent_fd)
            parent_fd = next_fd

        try:
            os.mkdir(final_component, mode=0o700, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            pass
        try:
            root_fd = os.open(final_component, directory_flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ValueError("output_root must be a new or empty directory") from exc
        if os.listdir(root_fd):
            raise ValueError("output_root must be empty")

        try:
            marker_fd = os.open(
                _OUTPUT_RESERVATION_NAME,
                marker_flags,
                0o600,
                dir_fd=root_fd,
            )
        except FileExistsError as exc:
            raise ValueError("output_root is already reserved") from exc
        except OSError as exc:
            raise ValueError("output_root cannot be reserved safely") from exc
        reservation_created = True
        os.close(marker_fd)
        marker_fd = -1

        if os.listdir(root_fd) != [_OUTPUT_RESERVATION_NAME]:
            raise ValueError("output_root changed while it was being reserved")

        identity = os.fstat(root_fd)
        root_identity = (identity.st_dev, identity.st_ino)
        logical_root = start.joinpath(*components)
        yield _ReservedOutputRoot(
            path=logical_root,
            fd=root_fd,
            parent_fd=parent_fd,
            final_component=final_component,
            device=identity.st_dev,
            inode=identity.st_ino,
        )
    finally:
        if marker_fd >= 0:
            os.close(marker_fd)
        if reservation_created:
            try:
                os.unlink(_OUTPUT_RESERVATION_NAME, dir_fd=root_fd)
            except FileNotFoundError:
                pass
        if root_fd >= 0:
            os.close(root_fd)
        if created and _named_directory_matches(
            parent_fd,
            final_component,
            identity=root_identity,
        ):
            try:
                os.rmdir(final_component, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


def _named_directory_matches(
    parent_fd: int,
    name: str,
    *,
    identity: tuple[int, int] | None,
) -> bool:
    if identity is None:
        return False
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISDIR(metadata.st_mode) and (
        metadata.st_dev,
        metadata.st_ino,
    ) == identity


def execute_capture_plan(
    *,
    plan_path: Path,
    output_root: Path,
    catalog: SourceNetworkCatalog,
    fixture_root: Path | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    value = _load(plan_path)
    planned_requests: list[tuple[str, CaptureRequest]] = []
    total_max_bytes = 0
    total_timeout_seconds = 0.0
    allowed_fields = {
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
    for index, row in enumerate(value["tasks"]):
        if not isinstance(row, dict):
            raise ValueError(f"capture task {index} must be an object")
        unknown = sorted(set(row) - allowed_fields)
        if unknown:
            raise ValueError(f"capture task {index} has unknown fields: " + ",".join(unknown))
        source_id = str(row.get("source_id", ""))
        source = catalog.sources.get(source_id)
        if source is None:
            raise ValueError(f"capture task {index} references an unknown source")
        if not source.enabled_by_default:
            raise ValueError(f"capture task {index} source is disabled until runtime authorization")
        if not source.domains:
            raise ValueError(f"capture task {index} source has no static domain allowlist")
        roles = tuple(str(item) for item in row.get("roles_observed", []))
        if not roles or set(roles) - set(source.roles):
            raise ValueError(f"capture task {index} requests roles outside the source contract")
        access_mode = str(row.get("access_mode", "PUBLIC_PAGE"))
        if access_mode not in source.access_modes:
            raise ValueError(f"capture task {index} requests an unsupported access mode")
        connector_kind = str(row.get("connector", ""))
        if connector_kind == "public_http":
            if access_mode not in {"PUBLIC_PAGE", "PUBLIC_DOWNLOAD"}:
                raise ValueError(f"capture task {index} public_http cannot use authenticated access")
        elif connector_kind == "file":
            if fixture_root is None:
                raise ValueError("file capture tasks require --fixture-root")
        else:
            raise ValueError(f"capture task {index} has unsupported connector")
        capture_kind = str(
            row.get(
                "capture_kind",
                "RAW_DOWNLOAD" if access_mode == "PUBLIC_DOWNLOAD" else "RAW_PAGE",
            )
        )
        request_values: dict[str, Any] = {
            "source_id": source_id,
            "source_url": row.get("source_url"),
            "allowed_domains": source.domains,
            "roles_observed": roles,
            "access_mode": access_mode,
            "capture_kind": capture_kind,
            "resource_path": row.get("resource_path"),
            "timeout_seconds": row.get(
                "timeout_seconds", DEFAULT_CAPTURE_TASK_TIMEOUT_SECONDS
            ),
            "max_bytes": row.get("max_bytes", DEFAULT_CAPTURE_TASK_BYTES),
        }
        if user_agent:
            request_values["user_agent"] = user_agent
        capture_request = CaptureRequest(**request_values)
        planned_requests.append((connector_kind, capture_request))
        total_max_bytes += capture_request.max_bytes
        total_timeout_seconds += capture_request.timeout_seconds

    # Plan-wide budgets are checked before connector construction, capture, or
    # output creation.  Per-task bounds alone permit an otherwise valid plan to
    # multiply memory, disk, and wall-time exposure without limit.
    if total_max_bytes > MAX_CAPTURE_PLAN_BYTES:
        raise ValueError(
            "capture plan max_bytes total exceeds "
            f"{MAX_CAPTURE_PLAN_BYTES} bytes"
        )
    if total_timeout_seconds > MAX_CAPTURE_PLAN_TIMEOUT_SECONDS:
        raise ValueError(
            "capture plan timeout_seconds total exceeds "
            f"{MAX_CAPTURE_PLAN_TIMEOUT_SECONDS:g} seconds"
        )

    with _reserve_output_root(output_root) as reserved_output_root:
        file_connector = FileConnector(fixture_root) if fixture_root is not None else None
        public_connector = PublicHttpConnector()
        tasks = [
            (
                public_connector if connector_kind == "public_http" else file_connector,
                capture_request,
            )
            for connector_kind, capture_request in planned_requests
        ]
        batch = capture_sources(tasks)
        if len(batch.results) != len(planned_requests):
            raise RuntimeError("capture executor result count does not match planned tasks")
        with CapturePacketWriter(
            reserved_output_root.path,
            run_root_fd=reserved_output_root.fd,
        ) as writer:
            write = writer.write(batch.results)
        reserved_output_root.assert_named_identity()
    return {
        "status": batch.status,
        "capture": batch.to_dict(),
        "write": write.to_dict(),
        "capture_accounting": {
            "max_tasks": MAX_CAPTURE_PLAN_TASKS,
            "planned_tasks": len(planned_requests),
            "capture_results": len(batch.results),
            "public_http_tasks": sum(
                connector_kind == "public_http"
                for connector_kind, _ in planned_requests
            ),
            "file_tasks": sum(
                connector_kind == "file"
                for connector_kind, _ in planned_requests
            ),
        },
        "claim_boundaries": {
            "raw_capture_is_qualified_finding": False,
            "parser_validation_required": True,
            "source_failure_blocks_other_sources": False,
            "capture_task_limit_is_network_request_budget": False,
            "network_request_budget_enforced": False,
        },
    }


__all__ = [
    "DEFAULT_CAPTURE_TASK_BYTES",
    "DEFAULT_CAPTURE_TASK_TIMEOUT_SECONDS",
    "MAX_CAPTURE_PLAN_BYTES",
    "MAX_CAPTURE_PLAN_TASKS",
    "MAX_CAPTURE_PLAN_TIMEOUT_SECONDS",
    "execute_capture_plan",
]
