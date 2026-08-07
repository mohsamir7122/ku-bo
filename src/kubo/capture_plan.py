from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("capture plan must be a JSON object")
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
    write = CapturePacketWriter(output_root).write(batch.results)
    return {
        "status": batch.status,
        "capture": batch.to_dict(),
        "write": write.to_dict(),
        "claim_boundaries": {
            "raw_capture_is_qualified_finding": False,
            "parser_validation_required": True,
            "source_failure_blocks_other_sources": False,
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
