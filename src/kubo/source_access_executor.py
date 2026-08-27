"""Execute narrowly scoped public source-access probes.

This module deliberately stops at capability access.  It never parses market
facts, creates findings, upgrades source capabilities, or bypasses access
controls.  Only hash-bound ``HTTP_GET`` tasks from a validated one-off probe
plan are executable here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Callable, Mapping

from .foundation_io import load_strict_json_object, prepare_output_root
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .ingestion import (
    CapturePacketWriter,
    CaptureRequest,
    CaptureResult,
    PublicHttpConnector,
    capture_sources,
)
from .source_access_recipes import (
    SourceAccessRecipeCatalog,
    validate_access_probe_against_plan,
    validate_source_probe_plan,
)
from .source_network import SourceNetworkCatalog
from .strict import parse_aware


PROBE_VERSION = "source-access-executor-v1"
PROBE_PURPOSE = (
    "One-off capability access receipt only; raw bytes are unparsed and are not "
    "market evidence, historical coverage, a forecast, or a recommendation."
)

_ERROR_REASON_MAP = {
    "ACCESS_MODE_CAPTURE_KIND_MISMATCH": "DATA_QUALITY_REJECTED",
    "AUTHENTICATED_ACCESS_FORBIDDEN": "AUTHORIZATION_MISSING",
    "ACCESS_REVIEW_REQUIRED": "HTTP_BLOCKED",
    "AUTH_REQUIRED_PAGE": "LOGIN_REQUIRED",
    "CAPTCHA_DETECTED": "CAPTCHA_PRESENT",
    "CONNECTOR_INTERNAL_ERROR": "NETWORK_ERROR",
    "HTTP_AUTH_REQUIRED": "LOGIN_REQUIRED",
    "HTTP_DNS_ERROR": "NETWORK_ERROR",
    "HTTP_FORBIDDEN": "HTTP_BLOCKED",
    "HTTP_RATE_LIMITED": "RATE_LIMITED",
    "HTTP_RESOURCE_NOT_FOUND": "DATA_QUALITY_REJECTED",
    "HTTP_SERVER_ERROR": "NETWORK_ERROR",
    "HTTP_STATUS_REJECTED": "HTTP_BLOCKED",
    "HTTP_TIMEOUT": "NETWORK_ERROR",
    "HTTP_TRANSPORT_ERROR": "NETWORK_ERROR",
    "INVALID_CONTENT_LENGTH": "DATA_QUALITY_REJECTED",
    "MAX_BYTES_EXCEEDED": "DATA_QUALITY_REJECTED",
    "NON_PUBLIC_NETWORK_TARGET": "NETWORK_ERROR",
    "PAYWALL_DETECTED": "PAYWALL",
    "REDIRECT_OUTSIDE_ALLOWLIST": "HTTP_BLOCKED",
    "ROBOTS_DNS_ERROR": "NETWORK_ERROR",
    "ROBOTS_DISALLOWED": "ROBOTS_DENIED",
    "ROBOTS_NON_PUBLIC_NETWORK_TARGET": "NETWORK_ERROR",
    "ROBOTS_POLICY_TOO_LARGE": "ROBOTS_DENIED",
    "ROBOTS_POLICY_UNAVAILABLE": "NETWORK_ERROR",
    "ROBOTS_REDIRECT_BLOCKED": "ROBOTS_DENIED",
    "ROBOTS_REDIRECT_OUTSIDE_ALLOWLIST": "ROBOTS_DENIED",
    "ROBOTS_UNREACHABLE": "NETWORK_ERROR",
    "UNEXPECTED_PARTIAL_RESPONSE": "DATA_QUALITY_REJECTED",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _terminal_reason(result: CaptureResult, task: Mapping[str, object]) -> str:
    reason = _ERROR_REASON_MAP.get(result.error_code)
    if result.content == b"":
        reason = "EMPTY_RESPONSE"
    if reason is None:
        reason = {
            "AUTH_REQUIRED": "AUTHORIZATION_MISSING",
            "BLOCKED": "HTTP_BLOCKED",
            "ERROR": "NETWORK_ERROR",
            "PARTIAL": "DATA_QUALITY_REJECTED",
            "UNTESTED": "AUTHORIZATION_MISSING",
        }.get(result.state, "DATA_QUALITY_REJECTED")
    allowed = {str(value) for value in task["terminal_reason_codes"]}
    if reason not in allowed:
        for fallback in (
            "DATA_QUALITY_REJECTED",
            "NETWORK_ERROR",
            "HTTP_BLOCKED",
            "AUTHORIZATION_MISSING",
        ):
            if fallback in allowed:
                return fallback
        raise ValueError(f"probe task has no safe terminal reason for {result.source_id}")
    return reason


def _probe_row(
    *,
    task: Mapping[str, object],
    result: CaptureResult,
    writer: CapturePacketWriter,
) -> dict[str, object]:
    artifact = None
    flags = set(result.data_quality_flags)
    state = result.state
    if result.content is not None:
        digest = sha256_bytes(result.content)
        relative = Path("raw") / result.source_id / f"{digest}.bin"
        writer.write_content_addressed_artifact(relative, result.content)
        artifact = {
            "path": relative.as_posix(),
            "sha256": digest,
            "size_bytes": len(result.content),
            "content_type": result.content_type or "application/octet-stream",
            "capture_kind": result.capture_kind,
        }
        if result.content == b"":
            flags.add(_terminal_reason(result, task))
        observation = (
            "Bounded public HTTPS capture completed; raw bytes remain unparsed "
            "and access-only."
        )
    else:
        # The access-probe contract permits PARTIAL only with a raw artifact.
        # Preserve the connector's code, but make an absent body an explicit
        # terminal error instead of fabricating an artifact.
        if state == "PARTIAL":
            state = "ERROR"
        flags.add(_terminal_reason(result, task))
        observation = (
            "Bounded public HTTPS capture produced no readable artifact; the "
            f"controlled connector code was {result.error_code or 'UNSPECIFIED'}."
        )
    return {
        "source_id": result.source_id,
        "state": state,
        "tested_url": str(task["tested_url"]),
        "final_url": result.final_url,
        "attempted_at": result.attempted_at.isoformat(),
        "http_status": result.http_status,
        "observation": observation,
        "data_quality_flags": sorted(flags),
        "artifact": artifact,
    }


def execute_public_source_probe(
    *,
    plan_path: Path,
    output_root: Path,
    recipes: SourceAccessRecipeCatalog,
    source_catalog: SourceNetworkCatalog,
    connector: PublicHttpConnector | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> dict[str, object]:
    """Execute a validated all-public HTTP probe plan exactly once.

    The output directory must be absent or empty.  Every readable response is
    persisted content-addressed under ``raw/`` and the generated receipt is
    immediately reopened through the existing plan/probe validator.
    """

    plan_report = validate_source_probe_plan(plan_path, recipes, source_catalog)
    if plan_report["status"] != "PASS_CONTRACT":
        return {
            "status": "BLOCKED",
            "errors": list(plan_report["errors"]),
            "claim_boundaries": {
                "access_probe_is_market_evidence": False,
                "access_probe_is_historical_coverage": False,
                "access_probe_is_forecast": False,
                "access_probe_authorizes_bypass": False,
            },
        }
    plan, _ = load_strict_json_object(
        plan_path, field="source access probe plan"
    )
    tasks = plan["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("source access probe plan has no tasks")
    for task in tasks:
        if (
            not isinstance(task, Mapping)
            or task.get("capture_method") != "HTTP_GET"
            or task.get("access_mode") not in {"PUBLIC_PAGE", "PUBLIC_DOWNLOAD"}
            or task.get("rights_status") != "PUBLIC_ACCESS_ONLY"
            or task.get("collection_frequency") != "ONE_OFF"
        ):
            raise ValueError(
                "executor accepts only one-off PUBLIC_ACCESS_ONLY HTTP_GET tasks"
            )

    started_at = clock()
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("clock must return timezone-aware datetimes")
    planned_at = parse_aware(plan["planned_at"], "planned_at")
    plan_expires_at = parse_aware(plan["expires_at"], "expires_at")
    if not planned_at <= started_at < plan_expires_at:
        raise ValueError("probe execution is outside the validated plan window")

    # Reserve a fresh destination before making any network request.  A stale
    # or non-empty output path must never cause a probe to execute without a
    # place to preserve its receipt.
    root = prepare_output_root(output_root, label="source access probe output")
    writer = CapturePacketWriter(root)
    http = connector or PublicHttpConnector(clock=clock)
    results: list[tuple[Mapping[str, object], CaptureResult]] = []
    for task in tasks:
        source_id = str(task["source_id"])
        source = source_catalog.sources[source_id]
        access_mode = str(task["access_mode"])
        capture_request = CaptureRequest(
            source_id=source_id,
            source_url=str(task["tested_url"]),
            allowed_domains=source.domains,
            roles_observed=tuple(sorted(source.roles)),
            access_mode=access_mode,
            capture_kind=(
                "RAW_PAGE" if access_mode == "PUBLIC_PAGE" else "RAW_DOWNLOAD"
            ),
            timeout_seconds=float(task["budget"]["timeout_seconds"]),
            max_bytes=int(task["budget"]["max_bytes"]),
        )
        result = capture_sources(
            ((http, capture_request),), clock=clock
        ).results[0]
        results.append((task, result))

    observed_at = clock()
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("clock must return timezone-aware datetimes")
    if observed_at < started_at or observed_at >= plan_expires_at:
        raise ValueError("probe execution did not finish inside the plan window")

    rows = [
        _probe_row(task=task, result=result, writer=writer)
        for task, result in results
    ]
    expires_at = min(plan_expires_at, observed_at + timedelta(hours=24))
    unsigned = {
        "schema_version": "3.1-access-probe",
        "probe_id": "",
        "probe_version": PROBE_VERSION,
        "observed_at": observed_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "purpose": PROBE_PURPOSE,
        "sources": rows,
    }
    unsigned["probe_id"] = "public-access-probe-" + hash_json(unsigned)[:24]
    probe_path = root / "access-probe.json"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(probe_path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(canonical_json_bytes(unsigned))
            handle.flush()
            os.fsync(handle.fileno())
        descriptor = -1
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    validation = validate_access_probe_against_plan(
        probe_path=probe_path,
        plan_path=plan_path,
        recipes=recipes,
        source_catalog=source_catalog,
        now=observed_at,
    )
    return {
        **validation,
        "output_root": str(root),
        "probe_path": str(probe_path),
        "network_access_attempted": True,
        "network_access_executed": any(
            result.error_code != "CONNECTOR_INTERNAL_ERROR"
            for _, result in results
        ),
        "market_data_collected": False,
        "market_evidence_created": False,
        "parser_executed": False,
        "forecast_or_recommendation_created": False,
    }


__all__ = ["PROBE_PURPOSE", "PROBE_VERSION", "execute_public_source_probe"]
