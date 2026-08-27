from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import math
import os
from pathlib import Path
import random
import stat
import time
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from .foundation_io import (
    load_strict_json_object,
    require_real_directory,
    safe_regular_file,
    strict_json_object,
)
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .ingestion import CaptureConnector, CapturePacketWriter, CaptureRequest, CaptureResult
from .source_network import SourceNetworkCatalog
from .source_resilience import (
    SourceResilienceController,
    classify_source_result,
    source_attempt_idempotency_key,
)
from .strict import https_url, parse_aware


ZERO_HASH = "0" * 64
KUWAIT_TIMEZONE_NAME = "Asia/Kuwait"
KUWAIT_TIMEZONE = ZoneInfo(KUWAIT_TIMEZONE_NAME)
TRANSIENT_STATES = frozenset({"ERROR"})
HARD_STOP_STATES = frozenset({"BLOCKED", "AUTH_REQUIRED"})
QUALIFIED_QUERY_STATUSES = frozenset({"QUALIFIED", "ZERO_RESULT"})
EVIDENCE_CLASSES = frozenset(
    {
        "PRIMARY_OFFICIAL",
        "PRIMARY_ISSUER",
        "STRUCTURED_SECONDARY",
        "EDITORIAL",
        "COMMUNITY",
        "WEB_ARCHIVE",
    }
)
_MULTI_LABEL_PUBLIC_SUFFIXES = frozenset(
    {
        "ac.uk",
        "co.in",
        "co.jp",
        "co.nz",
        "co.uk",
        "com.au",
        "com.bh",
        "com.cn",
        "com.kw",
        "com.om",
        "com.qa",
        "com.sa",
        "com.tr",
        "edu.kw",
        "gov.kw",
        "net.kw",
        "org.kw",
        "org.uk",
    }
)
_ATTEMPT_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "attempt_id",
        "idempotency_key",
        "sequence",
        "previous_attempt_hash",
        "event_type",
        "wave_id",
        "source_id",
        "route_id",
        "strategy_id",
        "strategy_ordinal",
        "attempt_ordinal",
        "window_from",
        "window_to",
        "requested_url",
        "final_url",
        "registrable_domain",
        "access_mode",
        "capture_kind",
        "attempted_at",
        "completed_at",
        "state",
        "query_status",
        "qualified_items",
        "zero_result",
        "http_status",
        "error_code",
        "retry_after_seconds",
        "material_query_route_proof_sha256",
        "content_sha256",
        "content_bytes",
        "artifact_path",
        "data_quality_flags",
        "limitations",
        "retry_disposition",
        "retry_delay_seconds",
        "attempt_hash",
    }
)
MAX_ATTEMPT_LEDGER_BYTES = 16 * 1024 * 1024
_SOURCE_SEARCH_RUN_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "workflow_id",
        "timezone",
        "decision_at",
        "window_from",
        "window_to",
        "status",
        "limitations",
        "waves",
        "sources",
        "attempt_ledger",
        "domain_coverage",
        "budget",
        "watermarks",
        "claim_boundaries",
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _kuwait_time(value: datetime, field: str) -> datetime:
    """Normalize an aware instant to the frozen Asia/Kuwait (+03:00) contract."""

    return _aware(value, field).astimezone(KUWAIT_TIMEZONE)


def registrable_domain(value: str) -> str:
    """Return a dependency-free conservative registrable-domain approximation.

    The result intentionally counts platform domains (for example ``t.me``)
    once, not once per channel.  The run receipt records the algorithm ID so a
    future Public Suffix List implementation cannot silently change history.
    """

    raw = str(value).strip()
    host = (urlsplit(raw).hostname if "://" in raw else raw).strip(".").casefold()
    if not host:
        raise ValueError("registrable-domain input has no host")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("registrable-domain input is not valid IDNA") from exc
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    labels = host.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        raise ValueError("registrable-domain input is not a qualified host")
    suffix = ".".join(labels[-2:])
    return ".".join(labels[-3:]) if len(labels) >= 3 and suffix in _MULTI_LABEL_PUBLIC_SUFFIXES else suffix


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    ordinal: int
    query_params: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class WaveSpec:
    wave_id: str
    ordinal: int
    minimum_distinct_domains: int
    source_classes: frozenset[str]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class OrchestratorPolicy:
    workflow_id: str
    context_days: int
    target_distinct_registrable_domains: int
    max_distinct_registrable_domains: int
    max_requests: int
    max_wall_seconds: int
    max_transient_attempts: int
    retry_delays_seconds: tuple[float, ...]
    transient_error_codes: frozenset[str]
    empty_result_error_codes: frozenset[str]
    strategies: tuple[StrategySpec, ...]
    waves: tuple[WaveSpec, ...]


class _BudgetStop(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RouteResult:
    route_id: str
    source_id: str
    status: str
    strategies_attempted: tuple[str, ...]
    attempt_count: int
    coverage_complete: bool
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class SourceResult:
    source_id: str
    wave_id: str
    status: str
    route_count: int
    completed_route_count: int
    attempt_count: int
    strategies_attempted: tuple[str, ...]
    window_from: str
    window_to: str
    watermark_before: str | None
    watermark_after: str | None
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "strategies_attempted": list(self.strategies_attempted),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class WaveResult:
    wave_id: str
    ordinal: int
    status: str
    source_ids: tuple[str, ...]
    attempt_count: int
    degraded_source_ids: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "source_ids": list(self.source_ids),
            "degraded_source_ids": list(self.degraded_source_ids),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class SourceSearchRun:
    run_id: str
    workflow_id: str
    decision_at: str
    window_from: str
    window_to: str
    status: str
    waves: tuple[WaveResult, ...]
    sources: tuple[SourceResult, ...]
    attempt_log_path: str
    attempt_log_sha256: str
    attempt_count: int
    ledger_event_count: int
    first_attempt_hash: str | None
    last_attempt_hash: str | None
    catalog_registrable_domains: tuple[str, ...]
    attempted_registrable_domains: tuple[str, ...]
    initial_watermarks: tuple[tuple[str, str], ...]
    final_watermarks: tuple[tuple[str, str], ...]
    target_distinct_registrable_domains: int
    max_distinct_registrable_domains: int
    max_requests: int
    max_wall_seconds: int
    elapsed_wall_seconds: float
    budget_stop_reason: str | None
    selection_mode: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "timezone": KUWAIT_TIMEZONE_NAME,
            "decision_at": self.decision_at,
            "window_from": self.window_from,
            "window_to": self.window_to,
            "status": self.status,
            "limitations": list(self.limitations),
            "waves": [item.to_dict() for item in self.waves],
            "sources": [item.to_dict() for item in self.sources],
            "attempt_ledger": {
                "path": self.attempt_log_path,
                "sha256": self.attempt_log_sha256,
                "row_count": self.ledger_event_count,
                "network_attempt_count": self.attempt_count,
                "first_attempt_hash": self.first_attempt_hash,
                "last_attempt_hash": self.last_attempt_hash,
            },
            "domain_coverage": {
                "algorithm": "CONSERVATIVE_SUFFIX_TABLE_V1",
                "catalog_registrable_domains": list(self.catalog_registrable_domains),
                "catalog_registrable_domain_count": len(self.catalog_registrable_domains),
                "attempted_registrable_domains": list(self.attempted_registrable_domains),
                "attempted_registrable_domain_count": len(self.attempted_registrable_domains),
                "selection_mode": self.selection_mode,
                "global_target_applicable": self.selection_mode == "DEFAULT_FAIR_NETWORK",
                "global_target_met": (
                    len(self.attempted_registrable_domains)
                    >= self.target_distinct_registrable_domains
                    if self.selection_mode == "DEFAULT_FAIR_NETWORK"
                    else None
                ),
            },
            "budget": {
                "target_distinct_registrable_domains": self.target_distinct_registrable_domains,
                "max_distinct_registrable_domains": self.max_distinct_registrable_domains,
                "max_requests": self.max_requests,
                "max_wall_seconds": self.max_wall_seconds,
                "usage_distinct_registrable_domains": len(self.attempted_registrable_domains),
                "usage_requests": self.attempt_count,
                "usage_wall_seconds": self.elapsed_wall_seconds,
                "stop_reason": self.budget_stop_reason,
            },
            "watermarks": {
                "context_days": 120,
                "timezone": KUWAIT_TIMEZONE_NAME,
                "initial": dict(self.initial_watermarks),
                "final": dict(self.final_watermarks),
            },
            "claim_boundaries": {
                "attempt_is_qualified_finding": False,
                "raw_capture_is_qualified_finding": False,
                "zero_result_is_negative_market_evidence": False,
                "attempt_count_proves_source_completeness": False,
                "attempt_ledger_hash_chain_is_external_seal": False,
                "registrable_domain_count_is_independent_evidence_count": False,
                "watermark_is_market_truth": False,
                "capture_timestamp_is_point_in_time_evidence": False,
                "low_level_http_requests_are_metered": False,
                "explicit_subset_satisfies_default_domain_target": False,
                "live_operational_claim": False,
                "probability_generated": False,
                "recommendation_generated": False,
            },
        }


@dataclass(frozen=True)
class SourceSearchRunValidation:
    """Reverified persisted run, ledger events, and raw-artifact digests."""

    report: dict[str, Any]
    attempt_rows: tuple[dict[str, Any], ...]
    artifact_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _ReconciledRoute:
    source_id: str
    wave_id: str
    route_id: str
    route_ordinal: int
    status: str
    coverage_complete: bool
    network_attempt_count: int
    strategies_attempted: tuple[str, ...]
    strategy_pairs: tuple[tuple[int, str], ...]
    terminal_disposition: str


def _exact_object(value: Any, fields: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{field} has unknown or missing fields")
    return value


def _non_negative_integer(value: Any, field: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} exceeds {maximum}")
    return value


def _unique_strings(value: Any, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must contain unique values")
    return tuple(value)


def _canonical_kuwait_timestamp(value: Any, field: str) -> datetime:
    parsed = parse_aware(value, field)
    normalized = _kuwait_time(parsed, field)
    if str(value) != normalized.isoformat() or not str(value).endswith("+03:00"):
        raise ValueError(f"{field} must be canonical Asia/Kuwait (+03:00) time")
    return normalized


def _validate_declared_source_schemas(schema_root: Path) -> None:
    root = Path(os.path.abspath(schema_root))
    require_real_directory(root, field="source schema root")
    run_schema, _ = load_strict_json_object(
        root / "source-search-run.schema.json",
        field="source search run schema",
        max_bytes=1024 * 1024,
    )
    attempt_schema, _ = load_strict_json_object(
        root / "source-attempt.schema.json",
        field="source attempt schema",
        max_bytes=1024 * 1024,
    )
    if set(run_schema.get("required", ())) != _SOURCE_SEARCH_RUN_FIELDS:
        raise ValueError("source search run schema required fields diverge from runtime")
    if set(attempt_schema.get("required", ())) != _ATTEMPT_FIELDS:
        raise ValueError("source attempt schema required fields diverge from runtime")


def validate_source_search_report(
    report: Mapping[str, Any],
    *,
    schema_root: Path | None = None,
) -> dict[str, Any]:
    """Validate the closed source-search report contract without trusting its hashes."""

    if schema_root is not None:
        _validate_declared_source_schemas(schema_root)
    top = _exact_object(report, _SOURCE_SEARCH_RUN_FIELDS, "source search run")
    if top["schema_version"] != "1.0":
        raise ValueError("unsupported source search run schema_version")
    if top["workflow_id"] != "KUWAIT_120D_NEXT_SESSION_RESEARCH":
        raise ValueError("unexpected source search workflow_id")
    if top["timezone"] != KUWAIT_TIMEZONE_NAME:
        raise ValueError("source search run timezone must be Asia/Kuwait")
    if not isinstance(top["run_id"], str) or not top["run_id"].strip():
        raise ValueError("source search run_id is required")
    if top["status"] not in {"COMPLETE", "DEGRADED", "FAILED"}:
        raise ValueError("source search status is invalid")
    decision = _canonical_kuwait_timestamp(top["decision_at"], "decision_at")
    window_from = _canonical_kuwait_timestamp(top["window_from"], "window_from")
    window_to = _canonical_kuwait_timestamp(top["window_to"], "window_to")
    if window_to != decision or window_from != decision - timedelta(days=120):
        raise ValueError("source search run window does not match the 120-day decision window")
    _unique_strings(top["limitations"], "limitations")

    wave_fields = frozenset(
        {"wave_id", "ordinal", "status", "source_ids", "attempt_count", "degraded_source_ids", "limitations"}
    )
    if not isinstance(top["waves"], list) or not top["waves"]:
        raise ValueError("source search waves must be non-empty")
    wave_attempts = 0
    wave_ids: set[str] = set()
    for ordinal, raw_wave in enumerate(top["waves"], start=1):
        wave = _exact_object(raw_wave, wave_fields, f"waves[{ordinal}]")
        if wave["ordinal"] != ordinal or not isinstance(wave["wave_id"], str) or not wave["wave_id"]:
            raise ValueError("source search wave order/id is invalid")
        if wave["wave_id"] in wave_ids or wave["status"] not in {"COMPLETE", "DEGRADED", "EMPTY", "BUDGET_STOPPED"}:
            raise ValueError("source search wave identity/status is invalid")
        wave_ids.add(wave["wave_id"])
        source_ids = _unique_strings(wave["source_ids"], f"waves[{ordinal}].source_ids")
        degraded = _unique_strings(wave["degraded_source_ids"], f"waves[{ordinal}].degraded_source_ids")
        if not set(degraded) <= set(source_ids):
            raise ValueError("degraded source ids must belong to their wave")
        wave_attempts += _non_negative_integer(wave["attempt_count"], f"waves[{ordinal}].attempt_count")
        _unique_strings(wave["limitations"], f"waves[{ordinal}].limitations")

    source_fields = frozenset(
        {
            "source_id", "wave_id", "status", "route_count", "completed_route_count",
            "attempt_count", "strategies_attempted", "window_from", "window_to",
            "watermark_before", "watermark_after", "limitations",
        }
    )
    if not isinstance(top["sources"], list):
        raise ValueError("source search sources must be an array")
    source_attempts = 0
    seen_sources: set[str] = set()
    for index, raw_source in enumerate(top["sources"]):
        source = _exact_object(raw_source, source_fields, f"sources[{index}]")
        source_id = source["source_id"]
        if not isinstance(source_id, str) or not source_id or source_id in seen_sources:
            raise ValueError("source search source_id is invalid or duplicated")
        seen_sources.add(source_id)
        if source["wave_id"] not in wave_ids:
            raise ValueError("source search source references an unknown wave")
        if source["status"] not in {"QUALIFIED", "ZERO_RESULT", "CAPTURED_PENDING_PARSER", "BLOCKED", "AUTH_REQUIRED", "ERROR"}:
            raise ValueError("source search source status is invalid")
        route_count = _non_negative_integer(source["route_count"], f"sources[{index}].route_count")
        completed_routes = _non_negative_integer(source["completed_route_count"], f"sources[{index}].completed_route_count")
        if route_count < 1 or completed_routes > route_count:
            raise ValueError("source search route counts are invalid")
        source_attempts += _non_negative_integer(source["attempt_count"], f"sources[{index}].attempt_count")
        if not isinstance(source["strategies_attempted"], list) or any(
            not isinstance(item, str) or not item for item in source["strategies_attempted"]
        ):
            raise ValueError("source search strategies_attempted is invalid")
        _canonical_kuwait_timestamp(source["window_from"], f"sources[{index}].window_from")
        if _canonical_kuwait_timestamp(source["window_to"], f"sources[{index}].window_to") != decision:
            raise ValueError("source search source window_to must equal decision_at")
        for key in ("watermark_before", "watermark_after"):
            if source[key] is not None:
                stamp = _canonical_kuwait_timestamp(source[key], f"sources[{index}].{key}")
                if stamp > decision:
                    raise ValueError("source watermark cannot be after decision_at")
        _unique_strings(source["limitations"], f"sources[{index}].limitations")

    ledger = _exact_object(
        top["attempt_ledger"],
        frozenset({"path", "sha256", "row_count", "network_attempt_count", "first_attempt_hash", "last_attempt_hash"}),
        "attempt_ledger",
    )
    ledger_path = Path(str(ledger["path"]))
    if ledger_path.is_absolute() or len(ledger_path.parts) != 1 or ledger_path.name in {"", ".", ".."}:
        raise ValueError("attempt ledger path must be a safe run-root filename")
    if not isinstance(ledger["sha256"], str) or len(ledger["sha256"]) != 64:
        raise ValueError("attempt ledger sha256 is invalid")
    row_count = _non_negative_integer(ledger["row_count"], "attempt_ledger.row_count")
    network_attempts = _non_negative_integer(
        ledger["network_attempt_count"], "attempt_ledger.network_attempt_count", maximum=600
    )
    for key in ("first_attempt_hash", "last_attempt_hash"):
        if ledger[key] is not None and (not isinstance(ledger[key], str) or len(ledger[key]) != 64):
            raise ValueError(f"attempt_ledger.{key} is invalid")
    if (row_count == 0) != (ledger["first_attempt_hash"] is None and ledger["last_attempt_hash"] is None):
        raise ValueError("attempt ledger empty/hash state is inconsistent")
    if source_attempts != network_attempts or wave_attempts != network_attempts:
        raise ValueError("source/wave network attempt counts do not reconcile")

    coverage = _exact_object(
        top["domain_coverage"],
        frozenset(
            {
                "algorithm", "catalog_registrable_domains", "catalog_registrable_domain_count",
                "attempted_registrable_domains", "attempted_registrable_domain_count",
                "selection_mode", "global_target_applicable", "global_target_met",
            }
        ),
        "domain_coverage",
    )
    if coverage["algorithm"] != "CONSERVATIVE_SUFFIX_TABLE_V1":
        raise ValueError("domain coverage algorithm is invalid")
    catalog_domains = _unique_strings(coverage["catalog_registrable_domains"], "domain_coverage.catalog_registrable_domains")
    attempted_domains = _unique_strings(coverage["attempted_registrable_domains"], "domain_coverage.attempted_registrable_domains")
    if coverage["catalog_registrable_domain_count"] != len(catalog_domains) or coverage["attempted_registrable_domain_count"] != len(attempted_domains):
        raise ValueError("domain coverage counts do not match their arrays")
    if len(attempted_domains) > 50 or not set(attempted_domains) <= set(catalog_domains):
        raise ValueError("attempted domain coverage is invalid")
    if coverage["selection_mode"] == "DEFAULT_FAIR_NETWORK":
        if coverage["global_target_applicable"] is not True or coverage["global_target_met"] != (len(attempted_domains) >= 50):
            raise ValueError("default domain target semantics are invalid")
    elif coverage["selection_mode"] == "EXPLICIT_SOURCE_SUBSET":
        if coverage["global_target_applicable"] is not False or coverage["global_target_met"] is not None:
            raise ValueError("explicit subset domain target semantics are invalid")
    else:
        raise ValueError("domain coverage selection_mode is invalid")

    budget = _exact_object(
        top["budget"],
        frozenset(
            {
                "target_distinct_registrable_domains", "max_distinct_registrable_domains",
                "max_requests", "max_wall_seconds", "usage_distinct_registrable_domains",
                "usage_requests", "usage_wall_seconds", "stop_reason",
            }
        ),
        "budget",
    )
    if tuple(budget[key] for key in ("target_distinct_registrable_domains", "max_distinct_registrable_domains", "max_requests", "max_wall_seconds")) != (50, 50, 600, 1800):
        raise ValueError("source search frozen budget is invalid")
    if budget["usage_distinct_registrable_domains"] != len(attempted_domains) or budget["usage_requests"] != network_attempts:
        raise ValueError("source search budget usage does not reconcile")
    if isinstance(budget["usage_wall_seconds"], bool) or not isinstance(budget["usage_wall_seconds"], (int, float)) or budget["usage_wall_seconds"] < 0:
        raise ValueError("source search wall usage is invalid")
    if budget["stop_reason"] is not None and (not isinstance(budget["stop_reason"], str) or not budget["stop_reason"]):
        raise ValueError("source search budget stop_reason is invalid")

    watermarks = _exact_object(
        top["watermarks"],
        frozenset({"context_days", "timezone", "initial", "final"}),
        "watermarks",
    )
    if watermarks["context_days"] != 120 or watermarks["timezone"] != KUWAIT_TIMEZONE_NAME:
        raise ValueError("source search watermark context/timezone is invalid")
    if not isinstance(watermarks["initial"], dict) or not isinstance(watermarks["final"], dict):
        raise ValueError("source search watermarks must be objects")
    if not set(watermarks["initial"]) <= set(watermarks["final"]):
        raise ValueError("final watermarks must retain every initial watermark")
    for group in ("initial", "final"):
        for source_id, value in watermarks[group].items():
            if not isinstance(source_id, str) or not source_id:
                raise ValueError("source watermark key is invalid")
            if _canonical_kuwait_timestamp(value, f"watermarks.{group}.{source_id}") > decision:
                raise ValueError("source watermark cannot be after decision_at")
    for source_id, initial in watermarks["initial"].items():
        if parse_aware(watermarks["final"][source_id], "final watermark") < parse_aware(initial, "initial watermark"):
            raise ValueError("source final watermark cannot move backward")

    boundaries = top["claim_boundaries"]
    if not isinstance(boundaries, dict) or not boundaries or any(value is not False for value in boundaries.values()):
        raise ValueError("source search claim boundaries must be explicit false values")
    return dict(top)


def _route_ordinal(source_id: str, route_id: Any) -> int:
    prefix = f"{source_id}:route-"
    value = str(route_id)
    suffix = value[len(prefix) :] if value.startswith(prefix) else ""
    if not suffix.isdigit() or int(suffix) <= 0:
        raise ValueError("source attempt route_id does not bind to its source")
    return int(suffix)


def _has_persisted_content(row: Mapping[str, Any]) -> bool:
    return (
        isinstance(row.get("artifact_path"), str)
        and bool(row["artifact_path"])
        and isinstance(row.get("content_sha256"), str)
        and len(row["content_sha256"]) == 64
        and isinstance(row.get("content_bytes"), int)
        and not isinstance(row.get("content_bytes"), bool)
        and row["content_bytes"] >= 0
    )


def _validate_capture_attempt_disposition(row: Mapping[str, Any], *, line: int) -> None:
    """Reject a self-rehashed ledger whose disposition contradicts its capture state."""

    disposition = row.get("retry_disposition")
    allowed = {
        "RETRY_TRANSIENT",
        "NEXT_EMPTY_STRATEGY",
        "STOP_QUALIFIED",
        "STOP_HARD_BLOCK",
        "STOP_CAPTURE_PENDING_PARSER",
        "STOP_ADAPTER_QUARANTINED",
        "STOP_TRANSIENT_SOURCE_FAILOVER",
        "STOP_RATE_LIMITED",
        "STOP_RETRY_BUDGET",
        "NEXT_REJECTED_STRATEGY",
        "STOP_STRATEGIES_EXHAUSTED",
    }
    if disposition not in allowed:
        raise ValueError(f"source capture disposition is invalid at line {line}")
    for field, maximum in (("strategy_ordinal", 4), ("attempt_ordinal", 2)):
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
            raise ValueError(f"source capture {field} is invalid at line {line}")
    if not isinstance(row.get("strategy_id"), str) or not row["strategy_id"]:
        raise ValueError(f"source capture strategy_id is invalid at line {line}")
    if row.get("registrable_domain") != registrable_domain(str(row.get("requested_url", ""))):
        raise ValueError(f"source capture registrable domain is inconsistent at line {line}")
    flags = row.get("data_quality_flags")
    if not isinstance(flags, list) or any(not isinstance(item, str) or not item for item in flags):
        raise ValueError(f"source capture data-quality flags are invalid at line {line}")
    if len(flags) != len(set(flags)):
        raise ValueError(f"source capture data-quality flags are duplicated at line {line}")
    retry_delay = row.get("retry_delay_seconds")
    if (
        isinstance(retry_delay, bool)
        or not isinstance(retry_delay, (int, float))
        or retry_delay < 0
    ):
        raise ValueError(f"source capture retry delay is invalid at line {line}")
    if disposition != "RETRY_TRANSIENT" and retry_delay != 0:
        raise ValueError(f"terminal source capture cannot retain a retry delay at line {line}")

    state = row.get("state")
    query_status = row.get("query_status")
    error_code = row.get("error_code")
    has_content = _has_persisted_content(row)
    if query_status == "ZERO_RESULT" and row.get("material_query_route_proof_sha256") is not None:
        if row["material_query_route_proof_sha256"] != row.get("content_sha256"):
            raise ValueError(f"zero-result proof does not bind to raw bytes at line {line}")
    if disposition == "STOP_QUALIFIED":
        if not (
            state == "AVAILABLE"
            and query_status == "QUALIFIED"
            and isinstance(row.get("qualified_items"), int)
            and not isinstance(row.get("qualified_items"), bool)
            and row["qualified_items"] > 0
            and row.get("zero_result") is False
            and has_content
            and not flags
        ):
            raise ValueError(f"STOP_QUALIFIED contradicts capture state at line {line}")
    elif disposition == "STOP_HARD_BLOCK":
        policy_block = (
            (state, query_status) == ("ERROR", "ERROR")
            and error_code
            in {
                "MISSING_SECRET",
                "ROBOTS_POLICY_UNAVAILABLE",
                "TERMS_NOT_PERMITTED",
                "TERMS_REVIEW_REQUIRED",
                "TOS_NOT_PERMITTED",
                "TOS_REVIEW_REQUIRED",
            }
        )
        if (
            (state, query_status)
            not in {("BLOCKED", "BLOCKED"), ("AUTH_REQUIRED", "AUTH_REQUIRED")}
            and not policy_block
        ) or has_content:
            raise ValueError(f"STOP_HARD_BLOCK contradicts capture state at line {line}")
    elif disposition == "STOP_CAPTURE_PENDING_PARSER":
        if state in HARD_STOP_STATES or not has_content:
            raise ValueError(
                f"STOP_CAPTURE_PENDING_PARSER contradicts capture state at line {line}"
            )
    elif disposition == "STOP_ADAPTER_QUARANTINED":
        if query_status != "PARSER_DRIFT" and not any(
            "PARSER" in flag or "SCHEMA" in flag for flag in flags
        ):
            raise ValueError(f"adapter quarantine lacks parser/schema failure at line {line}")
    elif disposition == "STOP_RATE_LIMITED":
        if error_code != "HTTP_RATE_LIMITED" or state != "BLOCKED" or has_content:
            raise ValueError(f"STOP_RATE_LIMITED contradicts capture state at line {line}")
    elif disposition in {"RETRY_TRANSIENT", "STOP_RETRY_BUDGET"}:
        if not (state == "ERROR" or error_code == "HTTP_RATE_LIMITED") or has_content:
            raise ValueError(f"retry disposition contradicts capture state at line {line}")
    elif disposition == "STOP_TRANSIENT_SOURCE_FAILOVER":
        if state != "ERROR" or has_content:
            raise ValueError(f"transient exhaustion contradicts capture state at line {line}")
    elif disposition == "NEXT_EMPTY_STRATEGY":
        explicit_empty = (
            query_status == "ZERO_RESULT"
            or error_code in {"EMPTY_RESPONSE_BODY", "HTTP_RESOURCE_NOT_FOUND"}
            or "EMPTY_RESPONSE_BODY" in flags
        )
        if not explicit_empty:
            raise ValueError(f"empty-strategy disposition lacks an empty result at line {line}")


def _reconcile_route(
    events: tuple[Mapping[str, Any], ...],
    *,
    allow_budget_interruption: bool,
) -> _ReconciledRoute:
    network = tuple(row for row in events if row["event_type"] == "CAPTURE_ATTEMPT")
    if not network:
        raise ValueError("source route has no capture attempt")
    source_id = str(network[0]["source_id"])
    wave_id = str(network[0]["wave_id"])
    route_id = str(network[0]["route_id"])
    route_ordinal = _route_ordinal(source_id, route_id)
    strategy_names: dict[int, str] = {}
    strategies_attempted: list[str] = []
    for position, row in enumerate(network):
        ordinal = int(row["strategy_ordinal"])
        strategy_id = str(row["strategy_id"])
        existing = strategy_names.setdefault(ordinal, strategy_id)
        if existing != strategy_id:
            raise ValueError("source route reuses a strategy ordinal with a different id")
        if position == 0:
            if ordinal != 1 or row["attempt_ordinal"] != 1:
                raise ValueError("source route must begin at strategy/attempt ordinal one")
            strategies_attempted.append(strategy_id)
            continue
        previous = network[position - 1]
        if ordinal == previous["strategy_ordinal"]:
            if (
                previous["retry_disposition"] != "RETRY_TRANSIENT"
                or row["attempt_ordinal"] != previous["attempt_ordinal"] + 1
            ):
                raise ValueError("source retry sequence contradicts its disposition")
        elif ordinal == previous["strategy_ordinal"] + 1:
            if (
                previous["retry_disposition"]
                not in {
                    "NEXT_EMPTY_STRATEGY",
                    "NEXT_REJECTED_STRATEGY",
                }
                or row["attempt_ordinal"] != 1
            ):
                raise ValueError("source strategy transition contradicts its disposition")
            strategies_attempted.append(strategy_id)
        else:
            raise ValueError("source strategy ordinals are not contiguous")

    control = events[-1] if events[-1]["event_type"] == "RETRY_CONTROL_EVENT" else None
    last = network[-1]
    if control is not None:
        terminal = "STOP_SLEEPER_FAILURE"
        status = "BLOCKED" if last["error_code"] == "HTTP_RATE_LIMITED" else "ERROR"
        coverage_complete = False
    else:
        terminal = str(last["retry_disposition"])
        last_by_strategy = {
            int(row["strategy_ordinal"]): row
            for row in network
        }
        zero_rows = tuple(last_by_strategy.get(index) for index in range(1, 5))
        zero_complete = all(row is not None for row in zero_rows) and all(
            row["retry_disposition"] == "NEXT_EMPTY_STRATEGY"
            and row["state"] == "AVAILABLE"
            and row["query_status"] == "ZERO_RESULT"
            and row["zero_result"] is True
            and row["qualified_items"] == 0
            and _has_persisted_content(row)
            and not row["data_quality_flags"]
            and row["material_query_route_proof_sha256"] == row["content_sha256"]
            for row in zero_rows
        )
        if zero_complete:
            proofs = {str(row["material_query_route_proof_sha256"]) for row in zero_rows}
            final_urls = {str(row["final_url"]) for row in zero_rows}
            zero_complete = len(proofs) == 4 and len(final_urls) == 4
        if zero_complete:
            status, coverage_complete = "ZERO_RESULT", True
        elif terminal == "STOP_QUALIFIED":
            status, coverage_complete = "QUALIFIED", True
        elif terminal == "STOP_CAPTURE_PENDING_PARSER":
            status, coverage_complete = "CAPTURED_PENDING_PARSER", False
        elif terminal == "STOP_ADAPTER_QUARANTINED":
            status = "CAPTURED_PENDING_PARSER" if _has_persisted_content(last) else "ERROR"
            coverage_complete = False
        elif terminal == "STOP_HARD_BLOCK":
            status, coverage_complete = str(last["state"]), False
        elif terminal in {"STOP_RATE_LIMITED", "STOP_RETRY_BUDGET"} and last["error_code"] == "HTTP_RATE_LIMITED":
            status, coverage_complete = "BLOCKED", False
        else:
            status, coverage_complete = "ERROR", False

    unfinished = last["retry_disposition"] == "RETRY_TRANSIENT" or (
        last["retry_disposition"]
        in {
            "NEXT_EMPTY_STRATEGY",
            "NEXT_REJECTED_STRATEGY",
        }
        and last["strategy_ordinal"] < 4
    )
    if control is None and unfinished and not allow_budget_interruption:
        raise ValueError("source route ended on a non-terminal disposition")
    return _ReconciledRoute(
        source_id=source_id,
        wave_id=wave_id,
        route_id=route_id,
        route_ordinal=route_ordinal,
        status=status,
        coverage_complete=coverage_complete,
        network_attempt_count=len(network),
        strategies_attempted=tuple(strategies_attempted),
        strategy_pairs=tuple(sorted(strategy_names.items())),
        terminal_disposition=terminal,
    )


def _reconcile_report_with_attempt_ledger(
    report: Mapping[str, Any],
    rows: tuple[dict[str, Any], ...],
) -> None:
    """Recompute all status-bearing source/wave/run fields from ledger events."""

    waves = tuple(report["waves"])
    sources = tuple(report["sources"])
    wave_by_id = {str(wave["wave_id"]): wave for wave in waves}
    source_by_id = {str(source["source_id"]): source for source in sources}
    wave_ordinal = {str(wave["wave_id"]): int(wave["ordinal"]) for wave in waves}
    planned_wave_by_source: dict[str, str] = {}
    for wave in waves:
        for source_id in wave["source_ids"]:
            if source_id in planned_wave_by_source:
                raise ValueError("source search plan assigns one source to multiple waves")
            planned_wave_by_source[source_id] = wave["wave_id"]
    for source_id, source in source_by_id.items():
        if planned_wave_by_source.get(source_id) != source["wave_id"]:
            raise ValueError("source report wave does not match planned wave membership")

    stop_reason = report["budget"]["stop_reason"]
    budget_wave_indexes = [
        index for index, wave in enumerate(waves) if wave["status"] == "BUDGET_STOPPED"
    ]
    if budget_wave_indexes and budget_wave_indexes != list(
        range(budget_wave_indexes[0], len(waves))
    ):
        raise ValueError("budget-stopped waves must form one terminal suffix")
    budget_source_candidates = [
        source
        for source in sources
        if stop_reason is not None and source["limitations"] == [stop_reason]
    ]
    budget_source_id: str | None = None
    if budget_wave_indexes:
        if stop_reason is None or len(budget_source_candidates) != 1:
            raise ValueError("budget-stopped run must identify exactly one interrupted source")
        budget_source = budget_source_candidates[0]
        budget_source_id = str(budget_source["source_id"])
        first_budget_wave = waves[budget_wave_indexes[0]]
        if (
            budget_source["wave_id"] != first_budget_wave["wave_id"]
            or budget_source["status"] != "ERROR"
            or budget_source["completed_route_count"] != 0
            or budget_source["strategies_attempted"] != []
        ):
            raise ValueError("interrupted budget source report has an invalid terminal shape")
    elif budget_source_candidates:
        raise ValueError("source report claims a budget interruption absent from wave state")
    elif stop_reason is not None and not (
        stop_reason == "MAX_WALL_SECONDS_EXHAUSTED"
        and report["budget"]["usage_wall_seconds"] >= report["budget"]["max_wall_seconds"]
    ):
        raise ValueError("budget stop reason is not evidenced by waves or wall usage")

    route_events: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    network_by_source: dict[str, int] = {}
    network_by_wave: dict[str, int] = {}
    current_source: str | None = None
    closed_sources: set[str] = set()
    current_route: tuple[str, str] | None = None
    closed_routes: set[tuple[str, str]] = set()
    last_wave_ordinal = 0
    for index, row in enumerate(rows, start=1):
        source_id = str(row["source_id"])
        wave_id = str(row["wave_id"])
        route_id = str(row["route_id"])
        source = source_by_id.get(source_id)
        if source is None:
            raise ValueError(f"source attempt references an unreported source at line {index}")
        if source["wave_id"] != wave_id or planned_wave_by_source.get(source_id) != wave_id:
            raise ValueError(f"source attempt wave does not match its report at line {index}")
        ordinal = wave_ordinal.get(wave_id)
        if ordinal is None or ordinal < last_wave_ordinal:
            raise ValueError(f"source attempt wave order moved backward at line {index}")
        last_wave_ordinal = ordinal
        if row["window_from"] != source["window_from"] or row["window_to"] != source["window_to"]:
            raise ValueError(f"source attempt window does not match its report at line {index}")
        _route_ordinal(source_id, route_id)
        if current_source != source_id:
            if current_source is not None:
                closed_sources.add(current_source)
            if source_id in closed_sources:
                raise ValueError("source attempt rows are not contiguous")
            current_source = source_id
        route_key = (source_id, route_id)
        if current_route != route_key:
            if current_route is not None:
                closed_routes.add(current_route)
            if route_key in closed_routes:
                raise ValueError("source route rows are not contiguous")
            current_route = route_key
        if row["event_type"] == "CAPTURE_ATTEMPT":
            _validate_capture_attempt_disposition(row, line=index)
            network_by_source[source_id] = network_by_source.get(source_id, 0) + 1
            network_by_wave[wave_id] = network_by_wave.get(wave_id, 0) + 1
        else:
            if index == 1:
                raise ValueError("retry control event has no preceding capture attempt")
            previous = rows[index - 2]
            identity_fields = (
                "wave_id", "source_id", "route_id", "strategy_id",
                "strategy_ordinal", "attempt_ordinal", "window_from", "window_to",
                "requested_url", "final_url", "registrable_domain", "access_mode",
                "capture_kind",
            )
            if (
                previous["event_type"] != "CAPTURE_ATTEMPT"
                or previous["retry_disposition"] != "RETRY_TRANSIENT"
                or any(previous[field] != row[field] for field in identity_fields)
            ):
                raise ValueError("retry control event does not bind to its preceding attempt")
        route_events.setdefault(route_key, []).append(row)

    outcomes_by_source: dict[str, list[_ReconciledRoute]] = {}
    strategy_ids: dict[int, str] = {}
    for route_key, event_list in route_events.items():
        outcome = _reconcile_route(
            tuple(event_list),
            allow_budget_interruption=route_key[0] == budget_source_id,
        )
        for ordinal, strategy_id in outcome.strategy_pairs:
            existing = strategy_ids.setdefault(ordinal, strategy_id)
            if existing != strategy_id:
                raise ValueError("strategy ordinal changes identity across source routes")
        outcomes_by_source.setdefault(outcome.source_id, []).append(outcome)

    initial_watermarks = report["watermarks"]["initial"]
    expected_final_watermarks = dict(initial_watermarks)
    for source_id, source in source_by_id.items():
        expected_attempts = network_by_source.get(source_id, 0)
        if source["attempt_count"] != expected_attempts:
            raise ValueError("source report attempt_count does not match its ledger rows")
        outcomes = sorted(
            outcomes_by_source.get(source_id, []), key=lambda item: item.route_ordinal
        )
        route_ordinals = [item.route_ordinal for item in outcomes]
        if route_ordinals and route_ordinals != list(range(1, max(route_ordinals) + 1)):
            raise ValueError("source report route ordinals are not contiguous")
        if source_id == budget_source_id:
            if source["route_count"] < len(outcomes):
                raise ValueError("budget-interrupted source route_count understates ledger routes")
            coverage_complete = False
        else:
            if not outcomes or source["route_count"] != len(outcomes):
                raise ValueError("source report route_count does not match ledger routes")
            expected_completed = sum(item.coverage_complete for item in outcomes)
            if source["completed_route_count"] != expected_completed:
                raise ValueError("source completed_route_count does not match ledger outcomes")
            expected_strategies = [
                strategy
                for outcome in outcomes
                for strategy in outcome.strategies_attempted
            ]
            if source["strategies_attempted"] != expected_strategies:
                raise ValueError("source strategies_attempted does not match ledger transitions")
            statuses = {item.status for item in outcomes}
            coverage_complete = bool(outcomes) and all(
                item.coverage_complete for item in outcomes
            )
            if coverage_complete:
                expected_status = "QUALIFIED" if "QUALIFIED" in statuses else "ZERO_RESULT"
            elif "CAPTURED_PENDING_PARSER" in statuses:
                expected_status = "CAPTURED_PENDING_PARSER"
            elif "AUTH_REQUIRED" in statuses:
                expected_status = "AUTH_REQUIRED"
            elif "BLOCKED" in statuses:
                expected_status = "BLOCKED"
            else:
                expected_status = "ERROR"
            if source["status"] != expected_status:
                raise ValueError("source final status contradicts ledger terminal dispositions")
        expected_before = initial_watermarks.get(source_id)
        if source["watermark_before"] != expected_before:
            raise ValueError("source watermark_before does not match run initial watermark")
        expected_after = (
            report["decision_at"]
            if coverage_complete
            else expected_before
            if source_id == budget_source_id
            else None
        )
        if source["watermark_after"] != expected_after:
            raise ValueError("source watermark_after contradicts ledger coverage")
        if coverage_complete:
            expected_final_watermarks[source_id] = report["decision_at"]
    if report["watermarks"]["final"] != expected_final_watermarks:
        raise ValueError("final watermarks do not reconcile to source ledger coverage")

    reported_by_wave: dict[str, set[str]] = {wave_id: set() for wave_id in wave_by_id}
    for source_id, source in source_by_id.items():
        reported_by_wave[source["wave_id"]].add(source_id)
    first_budget_index = budget_wave_indexes[0] if budget_wave_indexes else None
    for index, wave in enumerate(waves):
        wave_id = str(wave["wave_id"])
        planned = set(wave["source_ids"])
        reported = reported_by_wave[wave_id]
        if wave["attempt_count"] != network_by_wave.get(wave_id, 0):
            raise ValueError("wave attempt_count does not match ledger rows")
        if first_budget_index is None or index < first_budget_index:
            if reported != planned:
                raise ValueError("wave source_ids do not reconcile to reported sources")
            expected_degraded = {
                source_id
                for source_id in reported
                if source_by_id[source_id]["status"] not in {"QUALIFIED", "ZERO_RESULT"}
            }
            expected_status = (
                "COMPLETE"
                if planned and not expected_degraded
                else "DEGRADED"
                if planned
                else "EMPTY"
            )
        elif index == first_budget_index:
            if not reported <= planned or budget_source_id not in reported:
                raise ValueError("budget wave does not contain its interrupted source")
            expected_degraded = {
                source_id
                for source_id in reported
                if source_by_id[source_id]["status"] not in {"QUALIFIED", "ZERO_RESULT"}
            }
            expected_status = "BUDGET_STOPPED"
        else:
            if reported or network_by_wave.get(wave_id, 0):
                raise ValueError("source work appears after a budget-stopped wave")
            expected_degraded = planned
            expected_status = "BUDGET_STOPPED"
        if set(wave["degraded_source_ids"]) != expected_degraded:
            raise ValueError("wave degraded_source_ids contradict source outcomes")
        if wave["status"] != expected_status:
            raise ValueError("wave final status contradicts source/ledger outcomes")

    source_statuses = {source["status"] for source in sources}
    target_met = (
        report["domain_coverage"]["selection_mode"] == "EXPLICIT_SOURCE_SUBSET"
        or len(report["domain_coverage"]["attempted_registrable_domains"]) >= 50
    )
    expected_run_status = (
        "COMPLETE"
        if sources
        and source_statuses <= {"QUALIFIED", "ZERO_RESULT"}
        and stop_reason is None
        and target_met
        else "DEGRADED"
        if sources and rows
        else "FAILED"
    )
    if report["status"] != expected_run_status:
        raise ValueError("run final status contradicts reconciled source/ledger outcomes")


def validate_source_search_run(
    run_root: Path,
    *,
    schema_root: Path | None = None,
) -> SourceSearchRunValidation:
    """Reopen and rehash a persisted source-search report, ledger, and raw bytes."""

    root = Path(os.path.abspath(run_root))
    require_real_directory(root, field="source search run root")
    report, _ = load_strict_json_object(
        root / "source_search_run.json",
        field="source search run report",
        max_bytes=16 * 1024 * 1024,
    )
    validated = validate_source_search_report(report, schema_root=schema_root)
    receipt = validated["attempt_ledger"]
    ledger_path = root / receipt["path"]
    ledger = AppendOnlyAttemptLedger.open_for_verify(ledger_path, validated["run_id"])
    rows = ledger.verify()
    ledger_bytes = safe_regular_file(
        ledger_path,
        field="source attempt ledger",
        max_bytes=MAX_ATTEMPT_LEDGER_BYTES,
    )
    if sha256_bytes(ledger_bytes) != receipt["sha256"]:
        raise ValueError("source attempt ledger file hash does not match the run report")
    if len(rows) != receipt["row_count"]:
        raise ValueError("source attempt ledger row count does not match the run report")
    network_rows = tuple(row for row in rows if row["event_type"] == "CAPTURE_ATTEMPT")
    if len(network_rows) != receipt["network_attempt_count"]:
        raise ValueError("source attempt ledger network count does not match the run report")
    first_hash = rows[0]["attempt_hash"] if rows else None
    last_hash = rows[-1]["attempt_hash"] if rows else None
    if first_hash != receipt["first_attempt_hash"] or last_hash != receipt["last_attempt_hash"]:
        raise ValueError("source attempt ledger endpoint hashes do not match the run report")
    attempted_domains = sorted({row["registrable_domain"] for row in network_rows})
    if attempted_domains != validated["domain_coverage"]["attempted_registrable_domains"]:
        raise ValueError("source attempt ledger domains do not match the run report")
    decision = validated["decision_at"]
    decision_time = _canonical_kuwait_timestamp(decision, "decision_at")
    latest_completed: datetime | None = None
    earliest_attempted: datetime | None = None
    for index, row in enumerate(rows, start=1):
        if row["window_to"] != decision:
            raise ValueError(f"source attempt window_to differs from decision_at at line {index}")
        _canonical_kuwait_timestamp(row["window_from"], f"attempt[{index}].window_from")
        _canonical_kuwait_timestamp(row["window_to"], f"attempt[{index}].window_to")
        attempted = parse_aware(
            row["attempted_at"], f"attempt[{index}].attempted_at"
        )
        completed = parse_aware(
            row["completed_at"], f"attempt[{index}].completed_at"
        )
        if completed < attempted:
            raise ValueError(f"source attempt completes before it starts at line {index}")
        if latest_completed is not None and attempted < latest_completed:
            raise ValueError(f"source attempt time moves backward at line {index}")
        if completed - attempted > timedelta(seconds=validated["budget"]["max_wall_seconds"]):
            raise ValueError(f"source attempt exceeds the run wall budget at line {index}")
        earliest_attempted = attempted if earliest_attempted is None else earliest_attempted
        latest_completed = completed
    if earliest_attempted is not None and latest_completed is not None:
        measured_span = max(0.0, (latest_completed - earliest_attempted).total_seconds())
        declared_wall = float(validated["budget"]["usage_wall_seconds"])
        if measured_span > declared_wall + 1e-9:
            raise ValueError("source attempt timestamps exceed declared wall usage")
        if earliest_attempted < decision_time - timedelta(days=120):
            raise ValueError("source attempt predates the declared research window")
    artifact_hashes = tuple(
        sorted(
            (str(row["artifact_path"]), str(row["content_sha256"]))
            for row in rows
            if row["artifact_path"] is not None
        )
    )
    if len({path for path, _digest in artifact_hashes}) != len(artifact_hashes):
        raise ValueError("source attempt ledger reuses a raw artifact path")
    _reconcile_report_with_attempt_ledger(validated, rows)
    return SourceSearchRunValidation(validated, rows, artifact_hashes)


def load_orchestrator_policy(path: Path) -> OrchestratorPolicy:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("source query strategy config must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("source query strategy config must be an object")
    allowed = {
        "schema_version",
        "workflow_id",
        "context_days",
        "target_distinct_registrable_domains",
        "max_distinct_registrable_domains",
        "max_requests",
        "max_wall_seconds",
        "max_transient_attempts",
        "retry_delays_seconds",
        "transient_error_codes",
        "empty_result_error_codes",
        "strategies",
        "waves",
        "claim_boundaries",
    }
    if set(payload) != allowed or payload.get("schema_version") != "1.0":
        raise ValueError("source query strategy config has unknown/missing fields or version")
    if payload.get("context_days") != 120:
        raise ValueError("source query strategy context_days must remain 120")
    if payload.get("max_transient_attempts") != 2:
        raise ValueError("source query strategy max_transient_attempts must remain 2")
    for field, expected in (
        ("target_distinct_registrable_domains", 50),
        ("max_distinct_registrable_domains", 50),
        ("max_requests", 600),
        ("max_wall_seconds", 1800),
    ):
        if payload.get(field) != expected:
            raise ValueError(f"source query strategy {field} must remain {expected}")
    delays = payload.get("retry_delays_seconds")
    if not isinstance(delays, list) or len(delays) != 1 or any(
        isinstance(item, bool) or not isinstance(item, (int, float)) or item < 0 for item in delays
    ):
        raise ValueError("retry_delays_seconds must contain one non-negative jitter ceiling")
    boundaries = payload.get("claim_boundaries")
    if not isinstance(boundaries, dict) or not boundaries or any(value is not False for value in boundaries.values()):
        raise ValueError("source strategy claim boundaries must be explicit false values")

    strategy_rows = payload.get("strategies")
    if not isinstance(strategy_rows, list) or len(strategy_rows) != 4:
        raise ValueError("exactly four distinct empty-result strategies are required")
    strategies: list[StrategySpec] = []
    strategy_ids: set[str] = set()
    for index, row in enumerate(strategy_rows, start=1):
        if not isinstance(row, dict) or set(row) != {"strategy_id", "ordinal", "query_params"}:
            raise ValueError("strategy rows must have exact fields")
        strategy_id = str(row.get("strategy_id", "")).strip()
        if not strategy_id or strategy_id in strategy_ids or row.get("ordinal") != index:
            raise ValueError("strategy ids and ordinals must be unique and ordered")
        params = row.get("query_params")
        if not isinstance(params, dict) or any(not str(key).strip() or not isinstance(value, str) for key, value in params.items()):
            raise ValueError("strategy query_params must be a string map")
        strategies.append(StrategySpec(strategy_id, index, tuple(sorted((str(key), value) for key, value in params.items()))))
        strategy_ids.add(strategy_id)
    if len({item.query_params for item in strategies}) != 4:
        raise ValueError("empty-result strategies must have distinct query shapes")

    wave_rows = payload.get("waves")
    if not isinstance(wave_rows, list) or not wave_rows:
        raise ValueError("at least one wave is required")
    waves: list[WaveSpec] = []
    used_classes: set[str] = set()
    for index, row in enumerate(wave_rows, start=1):
        if not isinstance(row, dict) or set(row) != {
            "wave_id",
            "ordinal",
            "minimum_distinct_domains",
            "source_classes",
            "limitations",
        }:
            raise ValueError("wave rows must have exact fields")
        wave_id = str(row.get("wave_id", "")).strip()
        classes = row.get("source_classes")
        limitations = row.get("limitations")
        if (
            not wave_id
            or row.get("ordinal") != index
            or isinstance(row.get("minimum_distinct_domains"), bool)
            or not isinstance(row.get("minimum_distinct_domains"), int)
            or row["minimum_distinct_domains"] < 0
            or not isinstance(classes, list)
            or not classes
            or any(str(item) not in EVIDENCE_CLASSES for item in classes)
            or used_classes & set(classes)
            or not isinstance(limitations, list)
            or any(not isinstance(item, str) or not item for item in limitations)
        ):
            raise ValueError("waves must be ordered and assign evidence source classes once")
        used_classes.update(str(item) for item in classes)
        waves.append(
            WaveSpec(
                wave_id,
                index,
                row["minimum_distinct_domains"],
                frozenset(str(item) for item in classes),
                tuple(str(item) for item in limitations),
            )
        )
    expected_waves = (
        "OFFICIAL_AND_REGULATORY",
        "ISSUER_AND_GOVERNMENT",
        "STRUCTURED_AND_EDITORIAL",
        "COMMUNITY_ARCHIVE_AND_ROUTING",
    )
    if tuple(item.wave_id for item in waves) != expected_waves:
        raise ValueError("source strategy waves do not match the frozen workflow order")
    if sum(item.minimum_distinct_domains for item in waves) > payload["max_distinct_registrable_domains"]:
        raise ValueError("minimum wave domain reserves exceed the global domain budget")

    transient = payload.get("transient_error_codes")
    empty_codes = payload.get("empty_result_error_codes")
    if not isinstance(transient, list) or not transient or not isinstance(empty_codes, list) or not empty_codes:
        raise ValueError("transient and empty-result error codes must be non-empty lists")
    return OrchestratorPolicy(
        workflow_id=str(payload.get("workflow_id", "")).strip(),
        context_days=120,
        target_distinct_registrable_domains=50,
        max_distinct_registrable_domains=50,
        max_requests=600,
        max_wall_seconds=1800,
        max_transient_attempts=2,
        retry_delays_seconds=tuple(float(item) for item in delays),
        transient_error_codes=frozenset(str(item) for item in transient),
        empty_result_error_codes=frozenset(str(item) for item in empty_codes),
        strategies=tuple(strategies),
        waves=tuple(waves),
    )


class AppendOnlyAttemptLedger:
    """One-run O_APPEND JSONL ledger with an exact SHA-256 hash chain."""

    def __init__(self, path: Path, run_id: str):
        self.path = Path(os.path.abspath(path))
        self.run_id = str(run_id).strip()
        if not self.run_id:
            raise ValueError("run_id is required")
        require_real_directory(self.path.parent, field="attempt ledger parent")
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileExistsError as exc:
            raise ValueError("attempt ledger path must be new; append-only logs are never overwritten") from exc
        else:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                os.close(descriptor)
                raise ValueError("attempt ledger must be a single regular file")
            self._file_identity = (metadata.st_dev, metadata.st_ino)
            os.close(descriptor)
        self.rows: list[dict[str, Any]] = []

    @property
    def network_attempt_count(self) -> int:
        return sum(row.get("event_type") == "CAPTURE_ATTEMPT" for row in self.rows)

    def append(self, values: dict[str, Any]) -> dict[str, Any]:
        if "idempotency_key" in values:
            raise ValueError("source attempt idempotency key is derived, not caller supplied")
        sequence = len(self.rows) + 1
        previous = self.rows[-1]["attempt_hash"] if self.rows else ZERO_HASH
        row = {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "attempt_id": f"{self.run_id}:{sequence:08d}",
            "sequence": sequence,
            "previous_attempt_hash": previous,
            **values,
        }
        row["idempotency_key"] = source_attempt_idempotency_key(
            run_id=self.run_id,
            event_type=row["event_type"],
            source_id=row["source_id"],
            route_id=row["route_id"],
            strategy_id=row["strategy_id"],
            attempt_ordinal=row["attempt_ordinal"],
            requested_url=row["requested_url"],
            window_from=row["window_from"],
            window_to=row["window_to"],
        )
        if any(existing["idempotency_key"] == row["idempotency_key"] for existing in self.rows):
            raise ValueError("duplicate source attempt idempotency key")
        row["attempt_hash"] = hash_json(row)
        if set(row) != _ATTEMPT_FIELDS:
            raise ValueError("source attempt row has unknown or missing fields")
        _validate_attempt_event(row)
        data = canonical_json_bytes(row)
        require_real_directory(self.path.parent, field="attempt ledger parent")
        flags = (
            os.O_WRONLY
            | os.O_APPEND
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor = os.open(self.path, flags)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or (metadata.st_dev, metadata.st_ino) != self._file_identity
            ):
                raise ValueError("attempt ledger changed before append")
            offset = 0
            while offset < len(data):
                written = os.write(descriptor, data[offset:])
                if written <= 0:
                    raise OSError("short source-attempt append")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.rows.append(row)
        return row

    @classmethod
    def open_for_verify(cls, path: Path, run_id: str) -> "AppendOnlyAttemptLedger":
        instance = object.__new__(cls)
        instance.path = Path(path)
        instance.run_id = str(run_id).strip()
        try:
            instance.rows = [
                strict_json_object(line, f"attempt ledger line {index}")
                for index, line in enumerate(
                    safe_regular_file(
                        instance.path,
                        field="attempt ledger",
                        max_bytes=MAX_ATTEMPT_LEDGER_BYTES,
                    ).splitlines(),
                    start=1,
                )
            ]
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError("attempt ledger is unreadable") from exc
        return instance

    def persist_content(self, *, source_id: str, content: bytes) -> str:
        """Persist attempt-owned bytes without following links or overwriting."""

        if not isinstance(content, bytes):
            raise TypeError("attempt content must be bytes")
        digest = sha256_bytes(content)
        relative = Path("raw") / source_id / f"{len(self.rows) + 1:08d}-{digest}.bin"
        CapturePacketWriter(self.path.parent).write_content_addressed_artifact(
            relative,
            content,
        )
        return relative.as_posix()

    def verify(self) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        previous = ZERO_HASH
        idempotency_keys: set[str] = set()
        try:
            lines = safe_regular_file(
                self.path,
                field="attempt ledger",
                max_bytes=MAX_ATTEMPT_LEDGER_BYTES,
            ).splitlines()
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError("attempt ledger is unreadable") from exc
        for index, line in enumerate(lines, start=1):
            try:
                row = strict_json_object(line, f"attempt ledger line {index}")
            except ValueError as exc:
                raise ValueError(f"attempt ledger line {index} is invalid JSON") from exc
            if not isinstance(row, dict) or set(row) != _ATTEMPT_FIELDS:
                raise ValueError(f"attempt ledger line {index} has an invalid shape")
            supplied = row.get("attempt_hash")
            unhashed = dict(row)
            unhashed.pop("attempt_hash", None)
            if (
                row.get("run_id") != self.run_id
                or row.get("sequence") != index
                or row.get("attempt_id") != f"{self.run_id}:{index:08d}"
                or row.get("previous_attempt_hash") != previous
                or supplied != hash_json(unhashed)
            ):
                raise ValueError(f"attempt ledger hash chain failed at line {index}")
            expected_idempotency_key = source_attempt_idempotency_key(
                run_id=self.run_id,
                event_type=row.get("event_type"),
                source_id=row.get("source_id"),
                route_id=row.get("route_id"),
                strategy_id=row.get("strategy_id"),
                attempt_ordinal=row.get("attempt_ordinal"),
                requested_url=row.get("requested_url"),
                window_from=row.get("window_from"),
                window_to=row.get("window_to"),
            )
            if row.get("idempotency_key") != expected_idempotency_key:
                raise ValueError(f"attempt ledger idempotency key failed at line {index}")
            if expected_idempotency_key in idempotency_keys:
                raise ValueError(f"attempt ledger repeats an idempotency key at line {index}")
            idempotency_keys.add(expected_idempotency_key)
            _validate_attempt_event(row, line=index)
            artifact_path = row.get("artifact_path")
            if artifact_path is None:
                if row.get("content_sha256") is not None or row.get("content_bytes") != 0:
                    raise ValueError(f"attempt ledger content is not persisted at line {index}")
            else:
                relative = Path(str(artifact_path))
                if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "raw":
                    raise ValueError(f"attempt ledger artifact path escapes raw at line {index}")
                candidate = self.path.parent
                for part in relative.parts:
                    candidate = candidate / part
                    if candidate.is_symlink():
                        raise ValueError(f"attempt ledger artifact contains a symlink at line {index}")
                try:
                    resolved = candidate.resolve(strict=True)
                except OSError as exc:
                    raise ValueError(f"attempt ledger artifact is missing at line {index}") from exc
                root = self.path.parent.resolve()
                if root not in resolved.parents or not resolved.is_file():
                    raise ValueError(f"attempt ledger artifact is unsafe at line {index}")
                expected_bytes = row.get("content_bytes")
                if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool):
                    raise ValueError(f"attempt ledger content size is invalid at line {index}")
                content = safe_regular_file(
                    resolved,
                    field=f"attempt artifact line {index}",
                    max_bytes=max(1, expected_bytes),
                )
                if len(content) != expected_bytes or sha256_bytes(content) != row.get("content_sha256"):
                    raise ValueError(f"attempt ledger artifact bytes mismatch at line {index}")
            previous = str(supplied)
            rows.append(row)
        if rows != self.rows:
            raise ValueError("attempt ledger bytes differ from in-memory append sequence")
        return tuple(rows)


def _validate_attempt_event(row: Mapping[str, Any], *, line: int | None = None) -> None:
    """Enforce the semantic split between network attempts and control events."""

    suffix = f" at line {line}" if line is not None else ""
    event_type = row.get("event_type")
    if event_type not in {"CAPTURE_ATTEMPT", "RETRY_CONTROL_EVENT"}:
        raise ValueError(f"source ledger event_type is invalid{suffix}")
    if event_type == "CAPTURE_ATTEMPT":
        if row.get("retry_disposition") == "STOP_SLEEPER_FAILURE":
            raise ValueError(f"capture attempt cannot claim a sleeper failure{suffix}")
        return
    required = {
        "state": "ERROR",
        "query_status": "ERROR",
        "qualified_items": 0,
        "zero_result": False,
        "http_status": None,
        "error_code": "SLEEPER_FAILURE",
        "retry_after_seconds": None,
        "material_query_route_proof_sha256": None,
        "content_sha256": None,
        "content_bytes": 0,
        "artifact_path": None,
        "data_quality_flags": [],
        "retry_disposition": "STOP_SLEEPER_FAILURE",
    }
    if any(row.get(key) != value for key, value in required.items()):
        raise ValueError(f"retry control event has an invalid terminal shape{suffix}")
    limitations = row.get("limitations")
    if not isinstance(limitations, list) or "SLEEPER_FAILURE_STOPPED_RETRY" not in limitations:
        raise ValueError(f"retry control event is missing its terminal limitation{suffix}")


def _render_url(base_url: str, strategy: StrategySpec, values: Mapping[str, str]) -> str:
    parsed = urlsplit(https_url(base_url, "base_url"))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, template in strategy.query_params:
        query[key] = template.format_map(values)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(sorted(query.items())), ""))


def _access_contract(source: Any) -> tuple[str, str] | None:
    if "PUBLIC_PAGE" in source.access_modes:
        return "PUBLIC_PAGE", "RAW_PAGE"
    if "PUBLIC_DOWNLOAD" in source.access_modes:
        return "PUBLIC_DOWNLOAD", "RAW_DOWNLOAD"
    return None


def _connector_error(request: CaptureRequest, attempted_at: datetime, code: str) -> CaptureResult:
    return CaptureResult(
        source_id=request.source_id,
        source_url=request.source_url,
        final_url=request.source_url,
        access_mode=request.access_mode,
        capture_kind=request.capture_kind,
        roles_observed=request.roles_observed,
        attempted_at=attempted_at,
        observed_at=None,
        state="ERROR",
        query_status="ERROR",
        qualified_items=0,
        zero_result=False,
        content=None,
        content_type="",
        http_status=None,
        error_code=code,
        data_quality_flags=(),
        limitations=("CONNECTOR_FAILURE_ISOLATED",),
    )


def _validate_connector_result(
    request: CaptureRequest,
    result: CaptureResult,
) -> None:
    """Enforce the injectable connector boundary before bytes are persisted."""

    if not isinstance(result, CaptureResult):
        raise TypeError("connector must return CaptureResult")
    if result.source_id != request.source_id:
        raise ValueError("connector returned a different source_id")
    if result.access_mode != request.access_mode:
        raise ValueError("connector returned a different access_mode")
    if result.capture_kind != request.capture_kind:
        raise ValueError("connector returned a different capture_kind")
    if tuple(sorted(set(result.roles_observed))) != request.roles_observed:
        raise ValueError("connector returned different roles_observed")
    if result.content is not None and len(result.content) > request.max_bytes:
        raise ValueError("connector content exceeded request max_bytes")
    final_host = (
        urlsplit(https_url(result.final_url, "result.final_url")).hostname or ""
    ).casefold()
    if not any(
        final_host == domain or final_host.endswith("." + domain)
        for domain in request.allowed_domains
    ):
        raise ValueError("connector final_url escaped source domains")


class SourceSearchOrchestrator:
    def __init__(
        self,
        *,
        catalog: SourceNetworkCatalog,
        strategy_path: Path,
        connector: CaptureConnector,
        clock: Callable[[], datetime] = _utc_now,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] | None = None,
    ):
        self.catalog = catalog
        self.policy = load_orchestrator_policy(strategy_path)
        self.connector = connector
        self.clock = clock
        self.sleeper = sleeper
        system_random = random.SystemRandom()
        self.jitter = jitter or (lambda ceiling: system_random.uniform(0.0, ceiling))
        self.resilience = SourceResilienceController(
            max_attempts=self.policy.max_transient_attempts
        )

    @property
    def circuit_breakers(self) -> tuple[dict[str, Any], ...]:
        return self.resilience.snapshot()

    def run(
        self,
        *,
        run_id: str,
        decision_at: datetime,
        attempt_log_path: Path,
        query_text: str = "بورصة الكويت",
        source_ids: Iterable[str] | None = None,
        watermarks: Mapping[str, datetime | str] | None = None,
    ) -> SourceSearchRun:
        decision = _kuwait_time(decision_at, "decision_at")
        if not str(run_id).strip() or not str(query_text).strip():
            raise ValueError("run_id and query_text are required")
        selected = None if source_ids is None else frozenset(str(item) for item in source_ids)
        if selected is not None and (not selected or selected - set(self.catalog.sources)):
            raise ValueError("source_ids must be a non-empty subset of the source catalog")
        self.resilience = SourceResilienceController(
            max_attempts=self.policy.max_transient_attempts
        )
        parsed_watermarks: dict[str, datetime] = {}
        for source_id, value in (watermarks or {}).items():
            if source_id not in self.catalog.sources:
                raise ValueError(f"unknown watermark source: {source_id}")
            parsed = value if isinstance(value, datetime) else parse_aware(value, f"watermark.{source_id}")
            parsed = _kuwait_time(parsed, f"watermark.{source_id}")
            if parsed > decision:
                raise ValueError(f"watermark is after decision_at: {source_id}")
            parsed_watermarks[source_id] = parsed

        assignments = self._assign_sources(selected)
        ledger = AppendOnlyAttemptLedger(attempt_log_path, str(run_id))
        run_started = _aware(self.clock(), "clock")
        context_start = decision - timedelta(days=self.policy.context_days)
        source_results: list[SourceResult] = []
        wave_results: list[WaveResult] = []
        attempted_domains: set[str] = set()
        final_watermarks = dict(parsed_watermarks)
        budget_stop_reason: str | None = None
        selection_mode = (
            "DEFAULT_FAIR_NETWORK" if selected is None else "EXPLICIT_SOURCE_SUBSET"
        )
        run_limitations = {
            "ATTEMPT_LEDGER_HASH_CHAIN_IS_NOT_AN_EXTERNAL_SEAL",
            "CAPTURE_TIMESTAMP_IS_NOT_EVIDENCE_TIMESTAMP",
            "LOW_LEVEL_HTTP_REQUESTS_NOT_METERED_SEPARATELY",
            "PARSER_MUST_ENFORCE_POINT_IN_TIME_PUBLICATION_CUTOFF",
            "ZERO_RESULT_REQUIRES_UNIQUE_MATERIAL_QUERY_ROUTE_PROOFS",
        }
        if selected is not None:
            run_limitations.add(
                "EXPLICIT_SOURCE_SUBSET_GLOBAL_DOMAIN_TARGET_NOT_APPLICABLE"
            )
        for wave in self.policy.waves:
            wave_sources = assignments.get(wave.wave_id, ())
            wave_result_start = ledger.network_attempt_count
            degraded: list[str] = []
            if budget_stop_reason is not None:
                wave_results.append(
                    WaveResult(
                        wave.wave_id,
                        wave.ordinal,
                        "BUDGET_STOPPED",
                        tuple(wave_sources),
                        0,
                        tuple(wave_sources),
                        tuple(sorted({*wave.limitations, "NOT_RUN_AFTER_BUDGET_STOP"})),
                    )
                )
                continue
            for source_id in wave_sources:
                source = self.catalog.sources[source_id]
                before = parsed_watermarks.get(source_id)
                source_start = max(context_start, before) if before is not None else context_start
                source_attempt_start = ledger.network_attempt_count
                try:
                    result, routes = self._run_source(
                        ledger=ledger,
                        wave=wave,
                        source=source,
                        decision=decision,
                        window_from=source_start,
                        watermark_before=before,
                        query_text=str(query_text).strip(),
                        attempted_domains=attempted_domains,
                        run_started=run_started,
                    )
                except _BudgetStop as exc:
                    budget_stop_reason = exc.code
                    degraded.append(source_id)
                    source_results.append(
                        SourceResult(
                            source_id=source_id,
                            wave_id=wave.wave_id,
                            status="ERROR",
                            route_count=len(source.start_urls),
                            completed_route_count=0,
                            attempt_count=ledger.network_attempt_count - source_attempt_start,
                            strategies_attempted=(),
                            window_from=source_start.isoformat(),
                            window_to=decision.isoformat(),
                            watermark_before=before.isoformat() if before else None,
                            watermark_after=before.isoformat() if before else None,
                            limitations=(exc.code,),
                        )
                    )
                    break
                if routes and all(route.coverage_complete for route in routes):
                    final_watermarks[source_id] = decision
                    result = SourceResult(
                        **{**asdict(result), "watermark_after": decision.isoformat()}
                    )
                else:
                    if result.status not in {"QUALIFIED", "ZERO_RESULT"}:
                        degraded.append(source_id)
                source_results.append(result)
            wave_status = (
                "BUDGET_STOPPED"
                if budget_stop_reason is not None
                else "COMPLETE"
                if wave_sources and not degraded
                else "DEGRADED"
                if wave_sources
                else "EMPTY"
            )
            wave_results.append(
                WaveResult(
                    wave.wave_id,
                    wave.ordinal,
                    wave_status,
                    tuple(wave_sources),
                    ledger.network_attempt_count - wave_result_start,
                    tuple(sorted(degraded)),
                    tuple(
                        sorted(
                            {
                                *wave.limitations,
                                *(
                                    (budget_stop_reason,)
                                    if budget_stop_reason is not None
                                    else ()
                                ),
                            }
                        )
                    ),
                )
            )

        verified = ledger.verify()
        catalog_domains = sorted(
            {
                registrable_domain(domain)
                for source_ids_in_wave in assignments.values()
                for source_id in source_ids_in_wave
                for domain in self.catalog.sources[source_id].domains
            }
        )
        completed_at = _aware(self.clock(), "clock")
        elapsed_wall_seconds = max(0.0, (completed_at - run_started).total_seconds())
        if elapsed_wall_seconds >= self.policy.max_wall_seconds and budget_stop_reason is None:
            budget_stop_reason = "MAX_WALL_SECONDS_EXHAUSTED"
        statuses = {item.status for item in source_results}
        default_target_met = (
            selected is not None
            or len(attempted_domains)
            >= self.policy.target_distinct_registrable_domains
        )
        if selected is None and not default_target_met:
            run_limitations.add("DEFAULT_NETWORK_DOMAIN_TARGET_NOT_MET")
        status = (
            "COMPLETE"
            if source_results
            and statuses <= {"QUALIFIED", "ZERO_RESULT"}
            and budget_stop_reason is None
            and default_target_met
            else "DEGRADED"
            if source_results and verified
            else "FAILED"
        )
        return SourceSearchRun(
            run_id=str(run_id),
            workflow_id=self.policy.workflow_id,
            decision_at=decision.isoformat(),
            window_from=context_start.isoformat(),
            window_to=decision.isoformat(),
            status=status,
            waves=tuple(wave_results),
            sources=tuple(source_results),
            attempt_log_path=ledger.path.name,
            attempt_log_sha256=sha256_bytes(
                safe_regular_file(
                    ledger.path,
                    field="attempt ledger",
                    max_bytes=MAX_ATTEMPT_LEDGER_BYTES,
                )
            ),
            attempt_count=ledger.network_attempt_count,
            ledger_event_count=len(verified),
            first_attempt_hash=verified[0]["attempt_hash"] if verified else None,
            last_attempt_hash=verified[-1]["attempt_hash"] if verified else None,
            catalog_registrable_domains=tuple(catalog_domains),
            attempted_registrable_domains=tuple(sorted(attempted_domains)),
            initial_watermarks=tuple(sorted((key, value.isoformat()) for key, value in parsed_watermarks.items())),
            final_watermarks=tuple(sorted((key, value.isoformat()) for key, value in final_watermarks.items())),
            target_distinct_registrable_domains=self.policy.target_distinct_registrable_domains,
            max_distinct_registrable_domains=self.policy.max_distinct_registrable_domains,
            max_requests=self.policy.max_requests,
            max_wall_seconds=self.policy.max_wall_seconds,
            elapsed_wall_seconds=elapsed_wall_seconds,
            budget_stop_reason=budget_stop_reason,
            selection_mode=selection_mode,
            limitations=tuple(sorted(run_limitations)),
        )

    def _assign_sources(self, selected: frozenset[str] | None) -> dict[str, tuple[str, ...]]:
        result: dict[str, tuple[str, ...]] = {}
        assigned: set[str] = set()
        for wave in self.policy.waves:
            rows = []
            for source_id, source in self.catalog.sources.items():
                if selected is not None and source_id not in selected:
                    continue
                if (
                    source_id in assigned
                    or not source.enabled_by_default
                    or source.source_class not in wave.source_classes
                    or not source.start_urls
                    or not source.domains
                    or _access_contract(source) is None
                ):
                    continue
                rows.append(source_id)
                assigned.add(source_id)
            result[wave.wave_id] = tuple(sorted(rows))
        if selected is not None and assigned != set(selected):
            missing = ",".join(sorted(set(selected) - assigned))
            raise ValueError("selected sources are not enabled public evidence sources: " + missing)
        if selected is None:
            result = self._apply_default_wave_domain_reserves(result)
        return result

    def _apply_default_wave_domain_reserves(
        self,
        assignments: Mapping[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        """Choose a fair default plan before executing official-first waves.

        The global fifty-domain cap must not be consumed entirely by the first
        three waves.  Reserves guarantee that community/archive routing is
        actually attempted while execution order remains official-first.
        """

        chosen: dict[str, list[str]] = {wave.wave_id: [] for wave in self.policy.waves}
        deferred: list[tuple[str, str]] = []
        domains: set[str] = set()
        for index, wave in enumerate(self.policy.waves):
            later_reserve = sum(
                later.minimum_distinct_domains
                for later in self.policy.waves[index + 1 :]
            )
            ceiling = self.policy.max_distinct_registrable_domains - later_reserve
            for source_id in assignments.get(wave.wave_id, ()):
                source_domains = {
                    registrable_domain(url) for url in self.catalog.sources[source_id].start_urls
                }
                new_domains = source_domains - domains
                if len(domains) + len(new_domains) <= ceiling:
                    chosen[wave.wave_id].append(source_id)
                    domains.update(new_domains)
                else:
                    deferred.append((wave.wave_id, source_id))

        # If a later wave had fewer usable domains than reserved, fill the
        # remaining capacity deterministically with previously deferred rows.
        for wave_id, source_id in deferred:
            source_domains = {
                registrable_domain(url) for url in self.catalog.sources[source_id].start_urls
            }
            new_domains = source_domains - domains
            if len(domains) + len(new_domains) <= self.policy.max_distinct_registrable_domains:
                chosen[wave_id].append(source_id)
                domains.update(new_domains)
        return {key: tuple(value) for key, value in chosen.items()}

    def _run_source(
        self,
        *,
        ledger: AppendOnlyAttemptLedger,
        wave: WaveSpec,
        source: Any,
        decision: datetime,
        window_from: datetime,
        watermark_before: datetime | None,
        query_text: str,
        attempted_domains: set[str],
        run_started: datetime,
    ) -> tuple[SourceResult, tuple[RouteResult, ...]]:
        access = _access_contract(source)
        assert access is not None
        route_results: list[RouteResult] = []
        source_attempt_start = ledger.network_attempt_count
        strategies_attempted: list[str] = []
        for route_ordinal, base_url in enumerate(source.start_urls, start=1):
            route_id = f"{source.source_id}:route-{route_ordinal:02d}"
            route = self._run_route(
                ledger=ledger,
                wave=wave,
                source=source,
                route_id=route_id,
                base_url=base_url,
                access=access,
                decision=decision,
                window_from=window_from,
                query_text=query_text,
                attempted_domains=attempted_domains,
                run_started=run_started,
            )
            route_results.append(route)
            strategies_attempted.extend(route.strategies_attempted)
            if not self.resilience.adapter_available(source.source_id):
                break
        route_statuses = {item.status for item in route_results}
        if route_results and all(item.coverage_complete for item in route_results):
            status = "QUALIFIED" if "QUALIFIED" in route_statuses else "ZERO_RESULT"
        elif "CAPTURED_PENDING_PARSER" in route_statuses:
            status = "CAPTURED_PENDING_PARSER"
        elif "AUTH_REQUIRED" in route_statuses:
            status = "AUTH_REQUIRED"
        elif "BLOCKED" in route_statuses:
            status = "BLOCKED"
        else:
            status = "ERROR"
        limitations = sorted({value for item in route_results for value in item.limitations})
        return (
            SourceResult(
                source_id=source.source_id,
                wave_id=wave.wave_id,
                status=status,
                route_count=len(route_results),
                completed_route_count=sum(item.coverage_complete for item in route_results),
                attempt_count=ledger.network_attempt_count - source_attempt_start,
                strategies_attempted=tuple(strategies_attempted),
                window_from=window_from.isoformat(),
                window_to=decision.isoformat(),
                watermark_before=watermark_before.isoformat() if watermark_before else None,
                watermark_after=None,
                limitations=tuple(limitations),
            ),
            tuple(route_results),
        )

    def _run_route(
        self,
        *,
        ledger: AppendOnlyAttemptLedger,
        wave: WaveSpec,
        source: Any,
        route_id: str,
        base_url: str,
        access: tuple[str, str],
        decision: datetime,
        window_from: datetime,
        query_text: str,
        attempted_domains: set[str],
        run_started: datetime,
    ) -> RouteResult:
        route_start = ledger.network_attempt_count
        strategies_attempted: list[str] = []
        seen_urls: set[str] = set()
        limitations: set[str] = set()
        zero_route_proofs: set[str] = set()
        zero_effective_routes: set[str] = set()
        for strategy in self.policy.strategies:
            values = {
                "window_from": window_from.date().isoformat(),
                "window_to": decision.date().isoformat(),
                "query": query_text,
            }
            requested_url = _render_url(base_url, strategy, values)
            if requested_url in seen_urls:
                raise ValueError("empty-result strategies resolved to duplicate URLs")
            seen_urls.add(requested_url)
            strategies_attempted.append(strategy.strategy_id)
            requested_domain = registrable_domain(requested_url)
            if (
                requested_domain not in attempted_domains
                and len(attempted_domains) >= self.policy.max_distinct_registrable_domains
            ):
                raise _BudgetStop("MAX_DISTINCT_REGISTRABLE_DOMAINS_EXHAUSTED")
            request = CaptureRequest(
                source_id=source.source_id,
                source_url=requested_url,
                allowed_domains=source.domains,
                roles_observed=tuple(sorted(source.roles)),
                access_mode=access[0],
                capture_kind=access[1],
            )
            for attempt_ordinal in range(1, self.policy.max_transient_attempts + 1):
                if ledger.network_attempt_count >= self.policy.max_requests:
                    raise _BudgetStop("MAX_REQUESTS_EXHAUSTED")
                budget_clock = _aware(self.clock(), "clock")
                if (budget_clock - run_started).total_seconds() >= self.policy.max_wall_seconds:
                    raise _BudgetStop("MAX_WALL_SECONDS_EXHAUSTED")
                started = _aware(self.clock(), "clock")
                attempted_domains.add(requested_domain)
                idempotency_key = source_attempt_idempotency_key(
                    run_id=ledger.run_id,
                    event_type="CAPTURE_ATTEMPT",
                    source_id=source.source_id,
                    route_id=route_id,
                    strategy_id=strategy.strategy_id,
                    attempt_ordinal=attempt_ordinal,
                    requested_url=request.source_url,
                    window_from=window_from.isoformat(),
                    window_to=decision.isoformat(),
                )
                self.resilience.reserve(
                    idempotency_key,
                    attempt_ordinal=attempt_ordinal,
                )
                try:
                    result = self.connector.capture(request)
                    _validate_connector_result(request, result)
                except Exception:
                    result = _connector_error(request, started, "CONNECTOR_INTERNAL_ERROR")
                completed = _aware(self.clock(), "clock")
                disposition, delay = self._disposition(
                    result,
                    attempt_ordinal=attempt_ordinal,
                    strategy_ordinal=strategy.ordinal,
                )
                attempt_limitations = set(result.limitations)
                if result.content is not None:
                    attempt_limitations.add(
                        "CAPTURE_TIMESTAMP_REQUIRES_PARSER_POINT_IN_TIME_VALIDATION"
                    )
                elapsed_after_attempt = max(
                    0.0,
                    (completed - run_started).total_seconds(),
                )
                remaining_wall_seconds = max(
                    0.0,
                    self.policy.max_wall_seconds - elapsed_after_attempt,
                )
                if (
                    disposition == "RETRY_TRANSIENT"
                    and delay >= remaining_wall_seconds
                ):
                    disposition = "STOP_RETRY_BUDGET"
                    delay = 0.0
                    attempt_limitations.add(
                        "RETRY_DELAY_EXCEEDS_REMAINING_WALL_BUDGET"
                    )
                content_sha = sha256_bytes(result.content) if result.content is not None else None
                try:
                    artifact_path = (
                        ledger.persist_content(
                            source_id=source.source_id,
                            content=result.content,
                        )
                        if result.content is not None
                        else None
                    )
                except (OSError, TypeError, ValueError):
                    result = _connector_error(request, started, "CAPTURE_NOT_PERSISTED")
                    disposition = "NEXT_REJECTED_STRATEGY"
                    delay = 0.0
                    content_sha = None
                    artifact_path = None
                    attempt_limitations = set(result.limitations)
                if (
                    result.error_code == "HTTP_RATE_LIMITED"
                    and result.retry_after_seconds is None
                ):
                    attempt_limitations.add("RATE_LIMIT_RETRY_AFTER_UNAVAILABLE")
                classification = classify_source_result(result)
                if disposition in {
                    "STOP_RATE_LIMITED",
                    "STOP_HARD_BLOCK",
                    "STOP_ADAPTER_QUARANTINED",
                    "STOP_TRANSIENT_SOURCE_FAILOVER",
                }:
                    circuit = self.resilience.open_circuit(
                        source_id=source.source_id,
                        error_code=result.error_code or classification,
                        registrable_domain=requested_domain,
                        classification=classification,
                        opened_at=completed,
                        attempt_count=attempt_ordinal,
                        retry_after_seconds=result.retry_after_seconds,
                    )
                    attempt_limitations.add("IMMEDIATE_SOURCE_FAILOVER")
                    attempt_limitations.add(f"ADAPTER_{circuit.state}")
                    if circuit.retry_after_at is not None:
                        attempt_limitations.add("CIRCUIT_RETRY_AFTER_RECORDED")
                ledger.append(
                    {
                        "event_type": "CAPTURE_ATTEMPT",
                        "wave_id": wave.wave_id,
                        "source_id": source.source_id,
                        "route_id": route_id,
                        "strategy_id": strategy.strategy_id,
                        "strategy_ordinal": strategy.ordinal,
                        "attempt_ordinal": attempt_ordinal,
                        "window_from": window_from.isoformat(),
                        "window_to": decision.isoformat(),
                        "requested_url": request.source_url,
                        "final_url": result.final_url,
                        "registrable_domain": registrable_domain(request.source_url),
                        "access_mode": request.access_mode,
                        "capture_kind": request.capture_kind,
                        "attempted_at": result.attempted_at.isoformat(),
                        "completed_at": completed.isoformat(),
                        "state": result.state,
                        "query_status": result.query_status,
                        "qualified_items": result.qualified_items,
                        "zero_result": result.zero_result,
                        "http_status": result.http_status,
                        "error_code": result.error_code,
                        "retry_after_seconds": result.retry_after_seconds,
                        "material_query_route_proof_sha256": (
                            result.material_query_route_proof_sha256
                        ),
                        "content_sha256": content_sha,
                        "content_bytes": len(result.content) if result.content is not None else 0,
                        "artifact_path": artifact_path,
                        "data_quality_flags": list(result.data_quality_flags),
                        "limitations": sorted(attempt_limitations),
                        "retry_disposition": disposition,
                        "retry_delay_seconds": delay,
                    }
                )
                limitations.update(attempt_limitations)
                if disposition == "RETRY_TRANSIENT":
                    try:
                        self.sleeper(delay)
                    except Exception:
                        terminal_limitations = sorted(
                            {
                                *limitations,
                                "SLEEPER_FAILURE_STOPPED_RETRY",
                            }
                        )
                        ledger.append(
                            {
                                "event_type": "RETRY_CONTROL_EVENT",
                                "wave_id": wave.wave_id,
                                "source_id": source.source_id,
                                "route_id": route_id,
                                "strategy_id": strategy.strategy_id,
                                "strategy_ordinal": strategy.ordinal,
                                "attempt_ordinal": attempt_ordinal,
                                "window_from": window_from.isoformat(),
                                "window_to": decision.isoformat(),
                                "requested_url": request.source_url,
                                "final_url": result.final_url,
                                "registrable_domain": requested_domain,
                                "access_mode": request.access_mode,
                                "capture_kind": request.capture_kind,
                                "attempted_at": completed.isoformat(),
                                "completed_at": completed.isoformat(),
                                "state": "ERROR",
                                "query_status": "ERROR",
                                "qualified_items": 0,
                                "zero_result": False,
                                "http_status": None,
                                "error_code": "SLEEPER_FAILURE",
                                "retry_after_seconds": None,
                                "material_query_route_proof_sha256": None,
                                "content_sha256": None,
                                "content_bytes": 0,
                                "artifact_path": None,
                                "data_quality_flags": [],
                                "limitations": terminal_limitations,
                                "retry_disposition": "STOP_SLEEPER_FAILURE",
                                "retry_delay_seconds": delay,
                            }
                        )
                        return RouteResult(
                            route_id,
                            source.source_id,
                            "BLOCKED"
                            if result.error_code == "HTTP_RATE_LIMITED"
                            else "ERROR",
                            tuple(strategies_attempted),
                            ledger.network_attempt_count - route_start,
                            False,
                            tuple(terminal_limitations),
                        )
                    continue
                if disposition == "STOP_RETRY_BUDGET":
                    return RouteResult(
                        route_id,
                        source.source_id,
                        "BLOCKED"
                        if result.error_code == "HTTP_RATE_LIMITED"
                        else "ERROR",
                        tuple(strategies_attempted),
                        ledger.network_attempt_count - route_start,
                        False,
                        tuple(sorted(limitations)),
                    )
                if disposition == "STOP_RATE_LIMITED":
                    return RouteResult(
                        route_id,
                        source.source_id,
                        "BLOCKED",
                        tuple(strategies_attempted),
                        ledger.network_attempt_count - route_start,
                        False,
                        tuple(
                            sorted(
                                {
                                    *limitations,
                                    "RATE_LIMIT_CIRCUIT_OPEN",
                                    "IMMEDIATE_SOURCE_FAILOVER",
                                }
                            )
                        ),
                    )
                if disposition == "STOP_TRANSIENT_SOURCE_FAILOVER":
                    return RouteResult(
                        route_id,
                        source.source_id,
                        "ERROR",
                        tuple(strategies_attempted),
                        ledger.network_attempt_count - route_start,
                        False,
                        tuple(
                            sorted(
                                {
                                    *limitations,
                                    "TRANSIENT_ATTEMPT_BUDGET_EXHAUSTED",
                                    "IMMEDIATE_SOURCE_FAILOVER",
                                }
                            )
                        ),
                    )
                if disposition == "STOP_QUALIFIED":
                    return RouteResult(
                        route_id,
                        source.source_id,
                        "QUALIFIED",
                        tuple(strategies_attempted),
                        ledger.network_attempt_count - route_start,
                        True,
                        tuple(sorted(limitations)),
                    )
                if disposition == "NEXT_EMPTY_STRATEGY":
                    if (
                        result.state == "AVAILABLE"
                        and result.query_status == "ZERO_RESULT"
                        and result.content is not None
                        and not result.data_quality_flags
                    ):
                        proof = result.material_query_route_proof_sha256
                        effective_route = result.final_url
                        if proof is None:
                            limitations.add(
                                "ZERO_RESULT_MATERIAL_QUERY_ROUTE_PROOF_MISSING"
                            )
                        elif proof in zero_route_proofs:
                            limitations.add(
                                "ZERO_RESULT_MATERIAL_QUERY_ROUTE_PROOF_DUPLICATE"
                            )
                        elif effective_route in zero_effective_routes:
                            limitations.add(
                                "ZERO_RESULT_EFFECTIVE_ROUTE_NOT_DISTINCT"
                            )
                        else:
                            zero_route_proofs.add(proof)
                            zero_effective_routes.add(effective_route)
                    break
                if disposition == "STOP_CAPTURE_PENDING_PARSER":
                    return RouteResult(
                        route_id,
                        source.source_id,
                        "CAPTURED_PENDING_PARSER",
                        tuple(strategies_attempted),
                        ledger.network_attempt_count - route_start,
                        False,
                        tuple(sorted({*limitations, "RAW_CAPTURE_REQUIRES_PARSER"})),
                    )
                if disposition == "STOP_ADAPTER_QUARANTINED":
                    return RouteResult(
                        route_id,
                        source.source_id,
                        "CAPTURED_PENDING_PARSER"
                        if result.content is not None
                        else "ERROR",
                        tuple(strategies_attempted),
                        ledger.network_attempt_count - route_start,
                        False,
                        tuple(
                            sorted(
                                {
                                    *limitations,
                                    "PARSER_SCHEMA_DATA_QUARANTINED",
                                    "IMMEDIATE_SOURCE_FAILOVER",
                                }
                            )
                        ),
                    )
                if disposition == "STOP_HARD_BLOCK":
                    return RouteResult(
                        route_id,
                        source.source_id,
                        result.state,
                        tuple(strategies_attempted),
                        ledger.network_attempt_count - route_start,
                        False,
                        tuple(sorted(limitations)),
                    )
                # Transient exhaustion or a rejected response moves to the next
                # distinct route strategy; it never becomes evidence.
                break
        if len(zero_route_proofs) == len(self.policy.strategies):
            return RouteResult(
                route_id,
                source.source_id,
                "ZERO_RESULT",
                tuple(strategies_attempted),
                ledger.network_attempt_count - route_start,
                True,
                tuple(sorted({*limitations, "FOUR_DISTINCT_ZERO_RESULT_STRATEGIES"})),
            )
        return RouteResult(
            route_id,
            source.source_id,
            "ERROR",
            tuple(strategies_attempted),
            ledger.network_attempt_count - route_start,
            False,
            tuple(sorted({*limitations, "SEARCH_STRATEGIES_EXHAUSTED_WITHOUT_QUALIFIED_RESULT"})),
        )

    def _disposition(
        self,
        result: CaptureResult,
        *,
        attempt_ordinal: int,
        strategy_ordinal: int,
    ) -> tuple[str, float]:
        classification = classify_source_result(result)
        if classification == "RATE_LIMITED":
            return "STOP_RATE_LIMITED", 0.0
        if classification == "HARD_BLOCK":
            return "STOP_HARD_BLOCK", 0.0
        if classification == "QUARANTINE":
            return "STOP_ADAPTER_QUARANTINED", 0.0
        if (
            result.state == "AVAILABLE"
            and result.query_status == "QUALIFIED"
            and result.content is not None
            and not result.data_quality_flags
        ):
            return "STOP_QUALIFIED", 0.0
        explicit_empty = (
            result.query_status == "ZERO_RESULT"
            or result.error_code in self.policy.empty_result_error_codes
            or "EMPTY_RESPONSE_BODY" in result.data_quality_flags
        )
        if explicit_empty:
            return "NEXT_EMPTY_STRATEGY", 0.0
        transient = classification == "TRANSIENT" and (
            result.error_code in self.policy.transient_error_codes
            or result.error_code == "CONNECTOR_INTERNAL_ERROR"
        )
        if transient and attempt_ordinal < self.policy.max_transient_attempts:
            ceiling = self.policy.retry_delays_seconds[attempt_ordinal - 1]
            delay = self.jitter(ceiling)
            if (
                isinstance(delay, bool)
                or not isinstance(delay, (int, float))
                or delay < 0
                or delay > ceiling
                or not math.isfinite(float(delay))
            ):
                return "STOP_RETRY_BUDGET", 0.0
            return "RETRY_TRANSIENT", float(delay)
        if transient:
            return "STOP_TRANSIENT_SOURCE_FAILOVER", 0.0
        if result.content is not None:
            return "STOP_CAPTURE_PENDING_PARSER", 0.0
        return (
            "STOP_STRATEGIES_EXHAUSTED"
            if strategy_ordinal == len(self.policy.strategies)
            else "NEXT_REJECTED_STRATEGY",
            0.0,
        )


__all__ = [
    "AppendOnlyAttemptLedger",
    "OrchestratorPolicy",
    "SourceSearchOrchestrator",
    "SourceSearchRun",
    "SourceSearchRunValidation",
    "load_orchestrator_policy",
    "registrable_domain",
    "validate_source_search_report",
    "validate_source_search_run",
]
