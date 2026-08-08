from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .hashing import canonical_json_bytes, sha256_bytes
from .ingestion import (
    CapturePacketWriter,
    CaptureRequest,
    FileConnector,
    PublicHttpConnector,
    capture_sources,
)
from .parser_materialization import materialize_parser_run
from .source_network import SourceNetworkCatalog, validate_live_probe
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
BINDING_FIELDS = {"security_code", "ticker", "isin", "valid_from", "valid_to"}


def _load_plan(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
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
    if not isinstance(value, dict) or set(value) != CAPTURE_FIELDS:
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
        "resource_path": value.get("resource_path"),
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


def _write_access_probe(run_root: Path, results: tuple[Any, ...], artifacts: dict[str, dict[str, Any]]) -> Path:
    observed_values = [item.observed_at for item in results if item.observed_at is not None]
    attempted_values = [item.attempted_at for item in results]
    observed_at = max(observed_values or attempted_values)
    sources: list[dict[str, Any]] = []
    for item in sorted(results, key=lambda result: result.source_id):
        artifact_row = artifacts.get(item.source_id)
        artifact = None
        if artifact_row is not None:
            artifact = {
                "path": artifact_row["path"],
                "sha256": artifact_row["sha256"],
                "size_bytes": artifact_row["size_bytes"],
                "content_type": (item.content_type or "application/octet-stream").lower(),
                "capture_kind": artifact_row["capture_kind"],
            }
        flags = sorted(set(item.data_quality_flags))
        http_status = item.http_status
        if artifact is not None and http_status is None and item.access_mode == "USER_EXPORT":
            http_status = 200
            flags = sorted({*flags, "STAGED_USER_EXPORT_FIXTURE"})
        sources.append(
            {
                "source_id": item.source_id,
                "state": item.state,
                "tested_url": item.source_url,
                "final_url": item.final_url,
                "attempted_at": item.attempted_at.isoformat(),
                "http_status": http_status,
                "observation": (
                    "Staged limited capture receipt. This proves bounded access/capture only; "
                    "market facts require parser materialization and network validation."
                ),
                "data_quality_flags": flags,
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
    delay_minutes = _positive_int(plan.get("decision_delay_minutes"), "decision_delay_minutes")
    if delay_minutes > 60:
        raise ValueError("decision_delay_minutes cannot exceed 60")
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
    if budget["max_requests"] < 2:
        raise ValueError("budget.max_requests must permit the two staged captures")
    if official["max_bytes"] + secondary["max_bytes"] > budget["max_raw_bytes"]:
        raise ValueError("capture task byte ceilings exceed budget.max_raw_bytes")
    if int(float(official["timeout_seconds"]) + float(secondary["timeout_seconds"])) > budget["max_wall_seconds"]:
        raise ValueError("capture task timeout ceilings exceed budget.max_wall_seconds")

    output_root = Path(output_root).resolve()
    if output_root == Path(output_root.anchor):
        raise ValueError("output_root must not be a filesystem root")
    file_connector = FileConnector(fixture_root) if fixture_root is not None else None
    public_connector = PublicHttpConnector()
    tasks = []
    for task in (official, secondary):
        request = _capture_request(task, catalog, user_agent)
        if task["connector"] == "file":
            if file_connector is None:
                raise ValueError("file connector requires --fixture-root")
            connector = file_connector
        else:
            connector = public_connector
        tasks.append((connector, request))
    batch = capture_sources(tasks)
    write = CapturePacketWriter(output_root).write(batch.results)
    artifacts = _artifact_by_source(output_root)
    probe_path = _write_access_probe(output_root, batch.results, artifacts)
    probe_report = validate_live_probe(probe_path, catalog)
    if batch.status != "COMPLETE" or write.status != "COMPLETE" or probe_report["status"] != "PASS":
        return {
            "status": "CAPTURE_DEGRADED",
            "capture": batch.to_dict(),
            "write": write.to_dict(),
            "access_probe": probe_report,
            "materialized": None,
            "claim_boundaries": _claim_boundaries(),
        }

    observed = max(item.observed_at for item in batch.results if item.observed_at is not None)
    decision_at = max(datetime.now(timezone.utc), observed) + timedelta(minutes=delay_minutes)
    parser_plan = {
        "schema_version": "1.0",
        "run_id": run_id,
        "product_id": product_id,
        "decision_at": decision_at.isoformat(),
        "scope": scope,
        "budget": budget,
        "usage_wall_seconds": int(max(1, time.monotonic() - started)),
        "bindings": [
            {
                **binding,
                "official_artifact_sha256": artifacts["boursa_current"]["sha256"],
                "secondary_artifact_sha256": artifacts["investing_history"]["sha256"],
            }
        ],
        "parser_tasks": [
            {
                "parser_id": "boursa_identity_html_v1",
                "artifact_sha256": artifacts["boursa_current"]["sha256"],
            },
            {
                "parser_id": "investing_history_html_v1",
                "artifact_sha256": artifacts["investing_history"]["sha256"],
            },
        ],
    }
    parser_plan_path = output_root / "parser_plan.json"
    parser_plan_path.write_bytes(canonical_json_bytes(parser_plan))
    materialized = materialize_parser_run(
        capture_root=output_root,
        parser_plan_path=parser_plan_path,
        catalog=catalog,
    )
    return {
        "status": "PASS",
        "capture": batch.to_dict(),
        "write": write.to_dict(),
        "access_probe": probe_report,
        "parser_plan": str(parser_plan_path),
        "materialized": materialized,
        "claim_boundaries": _claim_boundaries(),
    }


def _claim_boundaries() -> dict[str, bool]:
    return {
        "staged_run_upgrades_sources_to_live_operational": False,
        "capture_success_is_market_evidence": False,
        "secondary_price_is_execution_price": False,
        "forecast_or_recommendation_performed": False,
        "external_source_availability_is_guaranteed": False,
    }


__all__ = ["stage_limited_live_run"]
