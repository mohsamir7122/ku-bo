"""Rights-aware Kuwait 90-day package construction and validation.

The initial package audits existing real source-attempt receipts. It does not
turn an access receipt into collection, parse market facts, release a training
dataset, train a model, unlock strict forecasting, or update Champion.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from .atomic_output import run_atomic_output
from .foundation_io import (
    load_strict_json_object,
    safe_regular_file,
    snapshot_regular_tree,
    strict_json_object,
)
from .hashing import canonical_json_bytes, sha256_bytes
from .priority_runtime import (
    BlockedCheckpointStore,
    require_production_checkpoint_store,
    validate_priority_policy,
)
from .recovery import load_recovery_policy
from .research_network import (
    resolve_trusted_source,
    validate_research_source_registry,
)
from .source_access_recipes import (
    SourceAccessRecipeCatalog,
    validate_access_probe_against_plan,
)
from .source_network import SourceNetworkCatalog
from .strict import parse_aware, require_sha256, safe_relative_path


POLICY_PATH = Path("config/rights-aware-backfill-policy.json")
POLICY_SHA256 = "247d3c7977a5e5ca7cdd1e6e22f289b05aa95b0c938e0662304129d8676619f9"
PACKAGE_NAME = "INCOMPLETE_RIGHTS_AWARE_RESEARCH_CONTEXT"
WINDOW_FROM = date(2026, 5, 30)
WINDOW_TO = date(2026, 8, 27)
WINDOW_DAY_COUNT = 90
REQUIRED_FILES = (
    "run-manifest.json",
    "source-attempts.jsonl",
    "provenance-records.jsonl",
    "events-unique.jsonl",
    "research-context-90d.jsonl",
    "training-candidates.jsonl",
    "blocked-records.jsonl",
    "contradictions.jsonl",
    "coverage-report.json",
    "coverage-report.md",
)
JSONL_FILES = (
    "source-attempts.jsonl",
    "provenance-records.jsonl",
    "events-unique.jsonl",
    "research-context-90d.jsonl",
    "training-candidates.jsonl",
    "blocked-records.jsonl",
    "contradictions.jsonl",
)
CLASSIFICATIONS = (
    "ADMITTED_RESEARCH_CONTEXT",
    "ADMITTED_TRAINING",
    "BLOCKED_RIGHTS",
    "BLOCKED_ROBOTS",
    "BLOCKED_ACCESS",
    "MISSING",
    "UNVERIFIED",
)
FALLBACK_ORDER = (
    "official_documented_api_or_export",
    "alternate_official_page_or_repository",
    "issuer_official_disclosures",
    "regulator_official_records",
    "user_supplied_authorized_export",
    "secondary_discovery_only",
)
SOURCE_ATTEMPT_BOUNDARIES = {
    "market_observation_created": False,
    "source_access_admitted": False,
    "training_record_created": False,
    "publish_allowed": False,
}
MANIFEST_BOUNDARIES = {
    "package_is_complete_training_dataset": False,
    "market_data_collected": False,
    "training_allowed": False,
    "strict_forecast_unlocked": False,
    "champion_update_allowed": False,
    "saudi_training_or_promotion_allowed": False,
    "schedule_active": False,
    "trade_submission_allowed": False,
}
COVERAGE_BOUNDARIES = {
    "real_market_data_collected": False,
    "complete_training_dataset": False,
    "training_executed": False,
    "blind_test_executed": False,
    "forecast_generated": False,
    "schedule_active": False,
    "trade_submission_allowed": False,
}
GATES = {
    "rights": "BLOCKED",
    "provenance": "NOT_RUN_NO_OBSERVATIONS",
    "publication_event_availability_timestamps": "NOT_RUN_NO_OBSERVATIONS",
    "immutable_hash": "PASS_SOURCE_RECEIPTS_ONLY",
    "point_in_time_availability": "NOT_RUN_NO_OBSERVATIONS",
    "temporal_leakage_test": "PASS_EMPTY_NO_ADMITTED_ROWS",
    "temporal_split": "NOT_RUN_NO_ADMITTED_ROWS",
    "dataset_release": "BLOCKED",
    "strict_forecast": "LOCKED",
}
TRAINING_CYCLE = {
    "status": "BLOCKED_DATASET_RELEASE",
    "current_step": "DATASET_RELEASE",
    "champion_update_allowed": False,
    "saudi_training_or_promotion_allowed": False,
}
VALIDATOR = {
    "validator_id": (
        "kubo.source_access_recipes.validate_access_probe_against_plan@1.0"
    ),
    "status": "PASS_ACCESS_ONLY",
    "access_receipt_proves_collection": False,
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CODE_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_TERMINAL_CODES = (
    "ROBOTS_REDIRECT_OUTSIDE_ALLOWLIST",
    "ROBOTS_POLICY_UNAVAILABLE",
    "ROBOTS_REDIRECT_BLOCKED",
    "ROBOTS_POLICY_TOO_LARGE",
    "ROBOTS_UNREACHABLE",
    "ROBOTS_DISALLOWED",
    "AUTHENTICATED_ACCESS_FORBIDDEN",
    "REDIRECT_OUTSIDE_ALLOWLIST",
    "HTTP_RESOURCE_NOT_FOUND",
    "CONNECTOR_INTERNAL_ERROR",
    "HTTP_TRANSPORT_ERROR",
    "HTTP_AUTH_REQUIRED",
    "HTTP_RATE_LIMITED",
    "HTTP_SERVER_ERROR",
    "CAPTCHA_DETECTED",
    "PAYWALL_DETECTED",
    "AUTH_REQUIRED_PAGE",
    "HTTP_FORBIDDEN",
    "HTTP_DNS_ERROR",
    "HTTP_TIMEOUT",
)
_SOURCE_ATTEMPT_KEYS = frozenset(
    {
        "schema_version",
        "record_id",
        "record_type",
        "classification",
        "market",
        "run_id",
        "source_id",
        "source_role",
        "source_independence_group",
        "rights_status",
        "plan_id",
        "probe_id",
        "plan_path",
        "probe_path",
        "plan_sha256",
        "probe_sha256",
        "canonical_url",
        "access_method",
        "attempted_at",
        "observed_at",
        "http_status",
        "source_state",
        "terminal_code",
        "artifact",
        "data_quality_flags",
        "validator",
        "claim_boundaries",
        "record_digest",
    }
)
_BLOCKED_KEYS = frozenset(
    {
        "schema_version",
        "record_id",
        "record_type",
        "classification",
        "market",
        "source_attempt_id",
        "source_id",
        "source_role",
        "rights_status",
        "partition_from",
        "partition_to",
        "partition_day_count",
        "blocked_at",
        "blocker_code",
        "retry_allowed_in_same_run",
        "health_probe_later_allowed",
        "fallback_order",
        "required_user_action",
        "publish_allowed",
        "record_digest",
    }
)


class RightsAwareBackfillError(ValueError):
    """Raised when a package, source receipt, or admission boundary is invalid."""


def _exact(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RightsAwareBackfillError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise RightsAwareBackfillError(
            f"{field} has missing={sorted(keys - actual)} unknown={sorted(actual - keys)}"
        )
    return value


def _identifier(value: Any, field: str) -> str:
    text = str(value or "")
    if not _ID_RE.fullmatch(text):
        raise RightsAwareBackfillError(f"{field} must be a canonical identifier")
    return text


def _utc(value: datetime | str, field: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else parse_aware(value, field)
    except ValueError as exc:
        raise RightsAwareBackfillError(str(exc)) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RightsAwareBackfillError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _digest(value: Mapping[str, Any], field: str) -> str:
    material = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def _stable_id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(canonical_json_bytes(value)).hexdigest()[:24].upper()


def _strict_object(
    path: Path,
    field: str,
    max_bytes: int = 4 * 1024 * 1024,
) -> tuple[dict[str, Any], bytes]:
    try:
        content = safe_regular_file(path, field=field, max_bytes=max_bytes)
        return strict_json_object(content, field), content
    except ValueError as exc:
        raise RightsAwareBackfillError(str(exc)) from exc


def _policy(project_root: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload, content = load_strict_json_object(
            project_root / POLICY_PATH,
            field="rights-aware backfill policy",
            max_bytes=512 * 1024,
        )
    except ValueError as exc:
        raise RightsAwareBackfillError(str(exc)) from exc
    if sha256_bytes(content) != POLICY_SHA256:
        raise RightsAwareBackfillError("rights-aware backfill policy digest changed")
    return payload, content


def _source_denominator(
    project_root: Path, policy: Mapping[str, Any]
) -> tuple[list[dict[str, str]], str]:
    registry_report = validate_research_source_registry(project_root)
    registry, _content = load_strict_json_object(
        project_root / str(policy["source_denominator"]["registry_path"]),
        field="trusted research source registry",
        max_bytes=512 * 1024,
    )
    named = registry["required_named_sources"]
    if not isinstance(named, list):
        raise RightsAwareBackfillError("trusted source denominator is invalid")
    rows: list[dict[str, str]] = []
    for raw in named:
        source_id = _identifier(raw["source_id"], "denominator.source_id")
        trusted = resolve_trusted_source(project_root, source_id)
        if raw["source_role"] != trusted.source_role:
            raise RightsAwareBackfillError("source denominator role differs from registry")
        rows.append(
            {
                "source_id": source_id,
                "source_role": trusted.source_role,
                "source_independence_group": trusted.independence_group,
            }
        )
    rows.sort(key=lambda item: item["source_id"])
    groups = {item["source_independence_group"] for item in rows}
    expected = policy["source_denominator"]
    if len(rows) != expected["expected_source_count"] or len(groups) != expected[
        "expected_independence_group_count"
    ]:
        raise RightsAwareBackfillError("source denominator count differs from policy")
    return rows, str(registry_report["registry_sha256"])


def validate_backfill_policy(project_root: Path | str) -> dict[str, Any]:
    root = Path(project_root).resolve()
    policy, content = _policy(root)
    if (
        policy.get("schema_version") != "1.0"
        or policy.get("policy_id") != "ku-bo-kuwait-rights-aware-backfill-v1"
        or policy.get("status") != "FAIL_CLOSED"
        or policy.get("package_name") != PACKAGE_NAME
        or policy.get("market") != "KUWAIT"
        or tuple(policy.get("required_files", ())) != REQUIRED_FILES
        or tuple(policy.get("classifications", ())) != CLASSIFICATIONS
        or policy.get("window")
        != {
            "inclusive_from": WINDOW_FROM.isoformat(),
            "inclusive_to": WINDOW_TO.isoformat(),
            "day_count": WINDOW_DAY_COUNT,
        }
    ):
        raise RightsAwareBackfillError("rights-aware backfill policy identity changed")
    recovery, _ = load_recovery_policy(root)
    if tuple(recovery["source_fallback_order"]) != FALLBACK_ORDER:
        raise RightsAwareBackfillError("recovery source fallback order changed")
    denominator, registry_sha = _source_denominator(root, policy)
    priority = validate_priority_policy(root)
    if priority["production_checkpoint_store_status"] != "BLOCKED_CHECKPOINT_STORE":
        raise RightsAwareBackfillError("checkpoint-store claim differs from trusted policy")
    return {
        "schema_version": "1.0",
        "status": "PASS_FAIL_CLOSED_BACKFILL_POLICY",
        "policy_sha256": sha256_bytes(content),
        "source_registry_sha256": registry_sha,
        "required_source_count": len(denominator),
        "required_independence_group_count": len(
            {item["source_independence_group"] for item in denominator}
        ),
        "window_day_count": WINDOW_DAY_COUNT,
        "planned_date_shard_count": len(denominator) * WINDOW_DAY_COUNT,
        "production_checkpoint_store_status": "BLOCKED_CHECKPOINT_STORE",
        "package_name": PACKAGE_NAME,
        "training_cycle_status": "BLOCKED_DATASET_RELEASE",
    }


def _terminal_code(observation: Any) -> str | None:
    text = str(observation or "")
    found = [code for code in _TERMINAL_CODES if code in text]
    if len(found) > 1:
        raise RightsAwareBackfillError("source receipt contains ambiguous terminal codes")
    return found[0] if found else None


def _classify_source_row(row: Mapping[str, Any], terminal_code: str | None) -> str:
    if terminal_code is not None and terminal_code.startswith("ROBOTS_"):
        return "BLOCKED_ROBOTS"
    if terminal_code in {
        "AUTHENTICATED_ACCESS_FORBIDDEN",
        "REDIRECT_OUTSIDE_ALLOWLIST",
        "HTTP_AUTH_REQUIRED",
        "CAPTCHA_DETECTED",
        "PAYWALL_DETECTED",
        "AUTH_REQUIRED_PAGE",
        "HTTP_FORBIDDEN",
    }:
        return "BLOCKED_ACCESS"
    if row.get("state") in {"BLOCKED", "AUTH_REQUIRED", "ERROR"}:
        return "BLOCKED_ACCESS"
    if row.get("artifact") is None:
        return "MISSING"
    return "UNVERIFIED"


def _safe_https_url(value: Any, trusted_domains: Sequence[str]) -> str:
    url = str(value or "")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise RightsAwareBackfillError("source attempt canonical_url is malformed") from exc
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
        or not any(
            host == domain.casefold() or host.endswith("." + domain.casefold())
            for domain in trusted_domains
        )
    ):
        raise RightsAwareBackfillError("source attempt URL is outside trusted domains")
    return url


def _artifact_metadata(
    probe_path: Path,
    raw: Any,
    *,
    destination_root: Path | None = None,
) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or frozenset(raw) != {
        "path",
        "sha256",
        "size_bytes",
        "content_type",
        "capture_kind",
    }:
        raise RightsAwareBackfillError("source receipt artifact is invalid")
    try:
        relative = safe_relative_path(raw["path"], "source receipt artifact path")
        content = safe_regular_file(
            Path(os.path.abspath(probe_path.parent)) / relative,
            field="source receipt raw artifact",
            max_bytes=64 * 1024 * 1024,
        )
        digest = require_sha256(raw["sha256"], "artifact.sha256")
    except ValueError as exc:
        raise RightsAwareBackfillError(str(exc)) from exc
    if digest != sha256_bytes(content) or raw["size_bytes"] != len(content):
        raise RightsAwareBackfillError("source receipt artifact digest or size mismatch")
    if destination_root is not None:
        _write_exclusive(destination_root / relative, content)
    return {
        "sha256": digest,
        "size_bytes": len(content),
        "content_type": str(raw["content_type"]),
        "capture_kind": str(raw["capture_kind"]),
    }


def _attempt_record(
    project_root: Path,
    *,
    run_id: str,
    plan_path: Path,
    probe_path: Path,
    known_at: datetime,
    receipt_destination: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, bytes, bytes]:
    plan, plan_content = _strict_object(plan_path, "source probe plan")
    probe, probe_content = _strict_object(probe_path, "source access probe")
    observed = _utc(probe.get("observed_at"), "probe.observed_at")
    if observed > known_at:
        raise RightsAwareBackfillError("TEMPORAL_LEAKAGE:PROBE_AFTER_KNOWN_AT")
    network = SourceNetworkCatalog(project_root / "config")
    recipes = SourceAccessRecipeCatalog(
        project_root / "config/source_access_recipes.json", network
    )
    report = validate_access_probe_against_plan(
        probe_path=probe_path,
        plan_path=plan_path,
        recipes=recipes,
        source_catalog=network,
        now=observed,
    )
    _plan_after, plan_content_after = _strict_object(
        plan_path,
        "source probe plan after validation",
    )
    _probe_after, probe_content_after = _strict_object(
        probe_path,
        "source access probe after validation",
    )
    if plan_content_after != plan_content or probe_content_after != probe_content:
        raise RightsAwareBackfillError(
            "source receipt changed during canonical validation"
        )
    if report.get("status") != "PASS_ACCESS_ONLY":
        raise RightsAwareBackfillError("canonical source receipt validator did not pass")
    sources = report.get("sources")
    tasks = plan.get("tasks")
    if not isinstance(sources, list) or len(sources) != 1:
        raise RightsAwareBackfillError("each receipt binding must contain exactly one source")
    if not isinstance(tasks, list) or len(tasks) != 1:
        raise RightsAwareBackfillError("each receipt plan must contain exactly one task")
    source_row = sources[0]
    task = tasks[0]
    source_id = _identifier(source_row.get("source_id"), "source_id")
    if task.get("source_id") != source_id or task.get("capture_method") != "HTTP_GET":
        raise RightsAwareBackfillError("source receipt differs from its canonical task")
    trusted = resolve_trusted_source(project_root, source_id)
    attempted = _utc(source_row.get("attempted_at"), "attempted_at")
    if attempted > observed:
        raise RightsAwareBackfillError("source attempt occurred after receipt observation")
    terminal = _terminal_code(source_row.get("observation"))
    classification = _classify_source_row(source_row, terminal)
    plan_sha = sha256_bytes(plan_content)
    probe_sha = sha256_bytes(probe_content)
    record_id = _stable_id(
        "SRCATT-",
        {
            "run_id": run_id,
            "source_id": source_id,
            "plan_sha256": plan_sha,
            "probe_sha256": probe_sha,
            "attempted_at": _timestamp(attempted),
        },
    )
    receipt_prefix = Path("receipts") / record_id
    artifact = _artifact_metadata(
        probe_path,
        source_row.get("artifact"),
        destination_root=(
            None if receipt_destination is None else receipt_destination / receipt_prefix
        ),
    )
    if receipt_destination is not None:
        _write_exclusive(receipt_destination / receipt_prefix / "plan.json", plan_content)
        _write_exclusive(
            receipt_destination / receipt_prefix / "access-probe.json", probe_content
        )
    canonical_url = _safe_https_url(source_row.get("tested_url"), trusted.domains)
    flags = source_row.get("data_quality_flags")
    if (
        not isinstance(flags, list)
        or any(not isinstance(flag, str) or not _ID_RE.fullmatch(flag) for flag in flags)
        or flags != sorted(set(flags))
    ):
        raise RightsAwareBackfillError("source attempt data-quality flags are not canonical")
    http_status = source_row.get("http_status")
    if http_status is not None and (
        type(http_status) is not int or not 100 <= http_status <= 599
    ):
        raise RightsAwareBackfillError("source attempt HTTP status is invalid")
    attempt = {
        "schema_version": "1.0",
        "record_id": record_id,
        "record_type": "SOURCE_ATTEMPT",
        "classification": classification,
        "market": "KUWAIT",
        "run_id": run_id,
        "source_id": source_id,
        "source_role": trusted.source_role,
        "source_independence_group": trusted.independence_group,
        "rights_status": trusted.rights_status,
        "plan_id": _identifier(report.get("plan_id"), "plan_id"),
        "probe_id": _identifier(report.get("probe_id"), "probe_id"),
        "plan_path": (receipt_prefix / "plan.json").as_posix(),
        "probe_path": (receipt_prefix / "access-probe.json").as_posix(),
        "plan_sha256": plan_sha,
        "probe_sha256": probe_sha,
        "canonical_url": canonical_url,
        "access_method": "HTTP_GET",
        "attempted_at": _timestamp(attempted),
        "observed_at": _timestamp(observed),
        "http_status": http_status,
        "source_state": str(source_row.get("state")),
        "terminal_code": terminal,
        "artifact": artifact,
        "data_quality_flags": flags,
        "validator": dict(VALIDATOR),
        "claim_boundaries": dict(SOURCE_ATTEMPT_BOUNDARIES),
        "record_digest": "",
    }
    attempt["record_digest"] = _digest(attempt, "record_digest")
    blocked = _blocked_record(attempt) if classification.startswith("BLOCKED_") else None
    return attempt, blocked, plan_content, probe_content


def _blocked_record(attempt: Mapping[str, Any]) -> dict[str, Any]:
    classification = str(attempt["classification"])
    if classification not in {"BLOCKED_RIGHTS", "BLOCKED_ROBOTS", "BLOCKED_ACCESS"}:
        raise RightsAwareBackfillError("non-blocked source attempt cannot create blocker")
    blocker = str(attempt.get("terminal_code") or classification)
    record_id = _stable_id(
        "BLOCK-",
        {
            "source_attempt_id": attempt["record_id"],
            "classification": classification,
            "blocker_code": blocker,
            "window_from": WINDOW_FROM.isoformat(),
            "window_to": WINDOW_TO.isoformat(),
        },
    )
    action = {
        "BLOCKED_ROBOTS": (
            "Use only a documented official export, alternate official surface, "
            "or user-authorized export; do not bypass robots controls."
        ),
        "BLOCKED_ACCESS": (
            "Provide an authorized route or required permission; do not bypass "
            "authentication, paywall, CAPTCHA, or access controls."
        ),
        "BLOCKED_RIGHTS": (
            "Provide a documented license, Terms approval, or authorized export "
            "before any content admission."
        ),
    }[classification]
    row = {
        "schema_version": "1.0",
        "record_id": record_id,
        "record_type": "SOURCE_RANGE_BLOCK",
        "classification": classification,
        "market": "KUWAIT",
        "source_attempt_id": attempt["record_id"],
        "source_id": attempt["source_id"],
        "source_role": attempt["source_role"],
        "rights_status": attempt["rights_status"],
        "partition_from": WINDOW_FROM.isoformat(),
        "partition_to": WINDOW_TO.isoformat(),
        "partition_day_count": WINDOW_DAY_COUNT,
        "blocked_at": attempt["observed_at"],
        "blocker_code": _identifier(blocker, "blocker_code"),
        "retry_allowed_in_same_run": False,
        "health_probe_later_allowed": classification == "BLOCKED_ROBOTS",
        "fallback_order": list(FALLBACK_ORDER),
        "required_user_action": action,
        "publish_allowed": False,
        "record_digest": "",
    }
    row["record_digest"] = _digest(row, "record_digest")
    return row


def _coverage(
    denominator: Sequence[Mapping[str, str]],
    attempts: Sequence[Mapping[str, Any]],
    blocked: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    required_groups = {
        item["source_independence_group"]: item["source_id"] for item in denominator
    }
    attempted_groups = {
        str(row["source_independence_group"]) for row in attempts
    }
    if attempted_groups - set(required_groups):
        raise RightsAwareBackfillError(
            "source attempt is outside the trusted denominator"
        )
    attempts_by_group: dict[str, list[Mapping[str, Any]]] = {}
    for row in attempts:
        group = str(row["source_independence_group"])
        if group in required_groups:
            attempts_by_group.setdefault(group, []).append(row)
    blocked_groups: set[str] = set()
    unverified_groups: set[str] = set()
    for group, rows in attempts_by_group.items():
        if rows and all(str(row["classification"]).startswith("BLOCKED_") for row in rows):
            blocked_groups.add(group)
        else:
            unverified_groups.add(group)
    unattempted_groups = set(required_groups) - set(attempts_by_group)
    unattempted_source_ids = sorted(required_groups[group] for group in unattempted_groups)
    classification_counts = {key: 0 for key in CLASSIFICATIONS}
    for row in [*attempts, *blocked]:
        classification_counts[str(row["classification"])] += 1
    counts = {
        "required_source_denominator": len(denominator),
        "attempted_denominator_sources": len(attempts_by_group),
        "unattempted_denominator_sources": len(unattempted_groups),
        "source_attempts": len(attempts),
        "blocked_sources": len(blocked),
        "planned_date_shards": len(denominator) * WINDOW_DAY_COUNT,
        "blocked_before_fetch_date_shards": len(blocked_groups) * WINDOW_DAY_COUNT,
        "unattempted_date_shards": len(unattempted_groups) * WINDOW_DAY_COUNT,
        "unverified_date_shards": len(unverified_groups) * WINDOW_DAY_COUNT,
        "completed_date_shards": 0,
        "readable_raw_artifacts": sum(row["artifact"] is not None for row in attempts),
        "real_observations": 0,
        "provenance_records": 0,
        "unique_events": 0,
        "research_context_records": 0,
        "training_candidates": 0,
        "contradictions": 0,
    }
    shard_total = (
        counts["blocked_before_fetch_date_shards"]
        + counts["unattempted_date_shards"]
        + counts["unverified_date_shards"]
        + counts["completed_date_shards"]
    )
    if shard_total != counts["planned_date_shards"]:
        raise RightsAwareBackfillError("date-shard denominator does not reconcile")
    report = {
        "schema_version": "1.0",
        "status": PACKAGE_NAME,
        "package_name": PACKAGE_NAME,
        "market": "KUWAIT",
        "window": {
            "inclusive_from": WINDOW_FROM.isoformat(),
            "inclusive_to": WINDOW_TO.isoformat(),
            "day_count": WINDOW_DAY_COUNT,
        },
        "counts": counts,
        "attempted_source_ids": sorted(str(row["source_id"]) for row in attempts),
        "blocked_sources": sorted(
            (
                {
                    "source_id": str(row["source_id"]),
                    "classification": str(row["classification"]),
                    "blocker_code": str(row["blocker_code"]),
                }
                for row in blocked
            ),
            key=lambda item: (item["source_id"], item["blocker_code"]),
        ),
        "unattempted_denominator_source_ids": unattempted_source_ids,
        "classification_counts": classification_counts,
        "gates": dict(GATES),
        "training_cycle": dict(TRAINING_CYCLE),
        "claim_boundaries": dict(COVERAGE_BOUNDARIES),
        "report_digest": "",
    }
    report["report_digest"] = _digest(report, "report_digest")
    return report


def _coverage_markdown(report: Mapping[str, Any]) -> bytes:
    counts = report["counts"]
    blocked_rows = report["blocked_sources"]
    blocked_lines = (
        [
            f"| {row['source_id']} | {row['classification']} | {row['blocker_code']} |"
            for row in blocked_rows
        ]
        or ["| none | none | none |"]
    )
    lines = [
        "# Kuwait 90-day rights-aware coverage",
        "",
        f"Package: `{PACKAGE_NAME}`",
        "",
        "This package contains real source-attempt metadata only. It is not a "
        "complete training dataset and does not unlock training or forecasting.",
        "",
        "## Counts",
        "",
        f"- Source attempts: {counts['source_attempts']}",
        f"- Real observations: {counts['real_observations']}",
        f"- Unique events: {counts['unique_events']}",
        f"- Training candidates: {counts['training_candidates']}",
        f"- Blocked sources: {counts['blocked_sources']}",
        f"- Planned date shards: {counts['planned_date_shards']}",
        f"- Blocked-before-fetch date shards: {counts['blocked_before_fetch_date_shards']}",
        f"- Unattempted date shards: {counts['unattempted_date_shards']}",
        f"- Unverified date shards: {counts['unverified_date_shards']}",
        "",
        "## Blocked sources",
        "",
        "| Source | Classification | Reason |",
        "| --- | --- | --- |",
        *blocked_lines,
        "",
        "Training cycle status: `BLOCKED_DATASET_RELEASE`.",
        "Strict forecast status: `LOCKED`.",
        "Schedules active: `false`.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _write_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RightsAwareBackfillError("cannot create package file exclusively") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RightsAwareBackfillError("package output must be a regular file")
        offset = 0
        while offset < len(content):
            offset += os.write(descriptor, content[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(dict(row)) for row in rows)


def _parse_jsonl(content: bytes, field: str) -> list[dict[str, Any]]:
    if not content:
        return []
    if not content.endswith(b"\n"):
        raise RightsAwareBackfillError(f"{field} must end with LF")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(content.splitlines()):
        if not line:
            raise RightsAwareBackfillError(f"{field} contains a blank line")
        try:
            rows.append(strict_json_object(line, f"{field}[{index}]"))
        except ValueError as exc:
            raise RightsAwareBackfillError(str(exc)) from exc
    return rows


def _inventory_record_count(path: str, content: bytes) -> int:
    if path.endswith(".jsonl"):
        return len(_parse_jsonl(content, path))
    if path.endswith(".json"):
        return 1
    return 0


def _validate_source_attempt(
    project_root: Path,
    bundle_root: Path,
    row: Mapping[str, Any],
    *,
    known_at: datetime,
) -> dict[str, Any]:
    attempt = dict(_exact(row, _SOURCE_ATTEMPT_KEYS, "source attempt"))
    if attempt["schema_version"] != "1.0" or attempt["record_type"] != "SOURCE_ATTEMPT":
        raise RightsAwareBackfillError("source attempt identity is invalid")
    if attempt["market"] != "KUWAIT" or attempt["claim_boundaries"] != SOURCE_ATTEMPT_BOUNDARIES:
        raise RightsAwareBackfillError("source attempt claim boundary was weakened")
    record_id = _identifier(attempt["record_id"], "record_id")
    if not re.fullmatch(r"SRCATT-[A-F0-9]{24}", record_id):
        raise RightsAwareBackfillError("source attempt record_id is invalid")
    try:
        plan_relative = safe_relative_path(attempt["plan_path"], "plan_path")
        probe_relative = safe_relative_path(attempt["probe_path"], "probe_path")
    except ValueError as exc:
        raise RightsAwareBackfillError(str(exc)) from exc
    prefix = Path("receipts") / record_id
    if plan_relative != prefix / "plan.json" or probe_relative != prefix / "access-probe.json":
        raise RightsAwareBackfillError("source receipt paths differ from record identity")
    expected, _blocked, _plan, _probe = _attempt_record(
        project_root,
        run_id=_identifier(attempt["run_id"], "run_id"),
        plan_path=bundle_root / plan_relative,
        probe_path=bundle_root / probe_relative,
        known_at=known_at,
    )
    if canonical_json_bytes(expected) != canonical_json_bytes(attempt):
        raise RightsAwareBackfillError("source attempt does not recompute from receipts")
    return attempt


def _validate_blocked_record(
    row: Mapping[str, Any], attempts: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    blocked = dict(_exact(row, _BLOCKED_KEYS, "blocked record"))
    attempt = attempts.get(str(blocked["source_attempt_id"]))
    if attempt is None:
        raise RightsAwareBackfillError("blocked record source attempt is missing")
    expected = _blocked_record(attempt)
    if canonical_json_bytes(expected) != canonical_json_bytes(blocked):
        raise RightsAwareBackfillError("blocked record does not recompute")
    return blocked


def validate_rights_aware_bundle(
    project_root: Path | str, bundle_root: Path | str
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    policy_report = validate_backfill_policy(root)
    try:
        snapshot = snapshot_regular_tree(
            Path(bundle_root),
            field="rights-aware backfill bundle",
            max_files=200,
            max_entries=300,
            max_depth=8,
            max_file_bytes=64 * 1024 * 1024,
            max_total_bytes=256 * 1024 * 1024,
        )
    except ValueError as exc:
        raise RightsAwareBackfillError(str(exc)) from exc
    files = snapshot.by_path()
    missing = sorted(set(REQUIRED_FILES) - set(files))
    if missing:
        raise RightsAwareBackfillError("bundle lacks required files: " + ",".join(missing))
    try:
        manifest = strict_json_object(
            files["run-manifest.json"].content,
            "run manifest",
        )
    except ValueError as exc:
        raise RightsAwareBackfillError(str(exc)) from exc
    if manifest.get("manifest_digest") != _digest(manifest, "manifest_digest"):
        raise RightsAwareBackfillError("run manifest digest mismatch")
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("package_name") != PACKAGE_NAME
        or manifest.get("package_status") != PACKAGE_NAME
        or manifest.get("execution_mode") != "AUDIT_EXISTING_REAL_RECEIPTS"
        or manifest.get("evidence_class") != "REAL_SOURCE_ATTEMPT_METADATA"
        or manifest.get("market") != "KUWAIT"
        or manifest.get("claim_boundaries") != MANIFEST_BOUNDARIES
        or manifest.get("training_cycle_status") != "BLOCKED_DATASET_RELEASE"
        or manifest.get("policy_sha256") != policy_report["policy_sha256"]
        or manifest.get("source_registry_sha256")
        != policy_report["source_registry_sha256"]
        or manifest.get("production_checkpoint_store_status")
        != "BLOCKED_CHECKPOINT_STORE"
    ):
        raise RightsAwareBackfillError("run manifest identity or claim boundary changed")
    if manifest.get("window") != {
        "inclusive_from": WINDOW_FROM.isoformat(),
        "inclusive_to": WINDOW_TO.isoformat(),
        "day_count": WINDOW_DAY_COUNT,
    }:
        raise RightsAwareBackfillError("run manifest backfill window changed")
    code_sha = str(manifest.get("code_sha") or "")
    if not _CODE_SHA_RE.fullmatch(code_sha):
        raise RightsAwareBackfillError("run manifest code_sha is invalid")
    scheduled = _utc(manifest.get("scheduled_at"), "scheduled_at")
    started = _utc(manifest.get("actual_started_at"), "actual_started_at")
    finished = _utc(manifest.get("finished_at"), "finished_at")
    if not scheduled <= started <= finished:
        raise RightsAwareBackfillError("run manifest timestamps are inconsistent")
    inventory = manifest.get("files")
    if not isinstance(inventory, list):
        raise RightsAwareBackfillError("run manifest inventory is invalid")
    inventory_paths = [str(item.get("path")) for item in inventory if isinstance(item, Mapping)]
    if inventory_paths != sorted(inventory_paths) or len(inventory_paths) != len(
        set(inventory_paths)
    ):
        raise RightsAwareBackfillError("run manifest inventory must be sorted and unique")
    expected_paths = sorted(set(files) - {"run-manifest.json"})
    if inventory_paths != expected_paths:
        raise RightsAwareBackfillError("run manifest inventory differs from bundle tree")
    for item in inventory:
        path = str(item["path"])
        snapshot_file = files[path]
        if item != {
            "path": path,
            "sha256": snapshot_file.sha256,
            "size_bytes": snapshot_file.size_bytes,
            "record_count": _inventory_record_count(path, snapshot_file.content),
        }:
            raise RightsAwareBackfillError("run manifest file inventory mismatch")

    attempts_raw = _parse_jsonl(files["source-attempts.jsonl"].content, "source-attempts")
    attempts = [
        _validate_source_attempt(root, snapshot.root, row, known_at=finished)
        for row in attempts_raw
    ]
    attempt_ids = [str(row["record_id"]) for row in attempts]
    source_ids = [str(row["source_id"]) for row in attempts]
    if len(attempt_ids) != len(set(attempt_ids)) or len(source_ids) != len(set(source_ids)):
        raise RightsAwareBackfillError("source attempts contain duplicate identity")
    if attempts != sorted(attempts, key=lambda row: (row["source_id"], row["record_id"])):
        raise RightsAwareBackfillError("source attempts are not canonical sorted")
    blocked_raw = _parse_jsonl(files["blocked-records.jsonl"].content, "blocked-records")
    attempts_by_id = {str(row["record_id"]): row for row in attempts}
    blocked = [_validate_blocked_record(row, attempts_by_id) for row in blocked_raw]
    if blocked != sorted(blocked, key=lambda row: (row["source_id"], row["record_id"])):
        raise RightsAwareBackfillError("blocked records are not canonical sorted")
    for name in (
        "provenance-records.jsonl",
        "events-unique.jsonl",
        "research-context-90d.jsonl",
        "training-candidates.jsonl",
        "contradictions.jsonl",
    ):
        if _parse_jsonl(files[name].content, name):
            raise RightsAwareBackfillError(
                f"{name} cannot be populated before real observation admission"
            )
    policy, _ = _policy(root)
    denominator, _registry_sha = _source_denominator(root, policy)
    expected_coverage = _coverage(denominator, attempts, blocked)
    try:
        coverage = strict_json_object(
            files["coverage-report.json"].content,
            "coverage report",
        )
    except ValueError as exc:
        raise RightsAwareBackfillError(str(exc)) from exc
    if canonical_json_bytes(coverage) != canonical_json_bytes(expected_coverage):
        raise RightsAwareBackfillError("coverage report does not recompute")
    if files["coverage-report.md"].content != _coverage_markdown(coverage):
        raise RightsAwareBackfillError("coverage Markdown does not recompute")
    if manifest.get("counts") != coverage["counts"]:
        raise RightsAwareBackfillError("manifest counts differ from coverage report")
    if manifest.get("coverage_report_digest") != coverage["report_digest"]:
        raise RightsAwareBackfillError("manifest coverage digest differs")
    return {
        "schema_version": "1.0",
        "status": "PASS_INCOMPLETE_RIGHTS_AWARE_BUNDLE",
        "package_name": PACKAGE_NAME,
        "market": "KUWAIT",
        "run_id": manifest["run_id"],
        "code_sha": code_sha,
        "manifest_digest": manifest["manifest_digest"],
        "counts": dict(coverage["counts"]),
        "attempted_source_ids": list(coverage["attempted_source_ids"]),
        "blocked_sources": list(coverage["blocked_sources"]),
        "training_cycle_status": "BLOCKED_DATASET_RELEASE",
        "research_network_status": "SOFTWARE_OPERATIONAL_ABSTAIN",
        "strict_forecast_status": "LOCKED",
        "production_checkpoint_store_status": "BLOCKED_CHECKPOINT_STORE",
        "scheduled_workflows_active": False,
        "claim_boundaries": dict(MANIFEST_BOUNDARIES),
    }


def build_rights_aware_bundle(
    project_root: Path | str,
    output_root: Path | str,
    *,
    run_id: Any,
    code_sha: Any,
    scheduled_at: datetime | str,
    actual_started_at: datetime | str,
    finished_at: datetime | str,
    receipt_bindings: Sequence[tuple[Path | str, Path | str]],
    production: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    policy_report = validate_backfill_policy(root)
    if production:
        try:
            require_production_checkpoint_store(root)
        except BlockedCheckpointStore:
            raise
        raise RightsAwareBackfillError("production bundle mode is not implemented")
    checked_run = _identifier(run_id, "run_id")
    checked_sha = str(code_sha or "")
    if not _CODE_SHA_RE.fullmatch(checked_sha):
        raise RightsAwareBackfillError("code_sha must be a lowercase Git SHA")
    scheduled = _utc(scheduled_at, "scheduled_at")
    started = _utc(actual_started_at, "actual_started_at")
    finished = _utc(finished_at, "finished_at")
    if not scheduled <= started <= finished:
        raise RightsAwareBackfillError("bundle timestamps are inconsistent")
    bindings = [(Path(plan), Path(probe)) for plan, probe in receipt_bindings]
    if len(bindings) > 64:
        raise RightsAwareBackfillError("receipt binding count exceeds safety budget")
    policy, _ = _policy(root)
    denominator, registry_sha = _source_denominator(root, policy)

    def worker(staging: Path) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for plan_path, probe_path in bindings:
            attempt, blocker, _plan, _probe = _attempt_record(
                root,
                run_id=checked_run,
                plan_path=plan_path,
                probe_path=probe_path,
                known_at=finished,
                receipt_destination=staging,
            )
            attempts.append(attempt)
            if blocker is not None:
                blocked.append(blocker)
        attempts.sort(key=lambda row: (row["source_id"], row["record_id"]))
        blocked.sort(key=lambda row: (row["source_id"], row["record_id"]))
        source_ids = [row["source_id"] for row in attempts]
        if len(source_ids) != len(set(source_ids)):
            raise RightsAwareBackfillError("receipt bindings contain a duplicate source_id")
        payloads: dict[str, bytes] = {
            "source-attempts.jsonl": _jsonl(attempts),
            "provenance-records.jsonl": b"",
            "events-unique.jsonl": b"",
            "research-context-90d.jsonl": b"",
            "training-candidates.jsonl": b"",
            "blocked-records.jsonl": _jsonl(blocked),
            "contradictions.jsonl": b"",
        }
        coverage = _coverage(denominator, attempts, blocked)
        payloads["coverage-report.json"] = canonical_json_bytes(coverage)
        payloads["coverage-report.md"] = _coverage_markdown(coverage)
        for name, content in payloads.items():
            _write_exclusive(staging / name, content)
        pre_manifest = snapshot_regular_tree(
            staging,
            field="staged rights-aware backfill bundle",
            max_files=199,
            max_entries=299,
            max_depth=8,
            max_file_bytes=64 * 1024 * 1024,
            max_total_bytes=256 * 1024 * 1024,
        )
        inventory = [
            {
                "path": item.path,
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
                "record_count": _inventory_record_count(item.path, item.content),
            }
            for item in pre_manifest.files
        ]
        manifest = {
            "schema_version": "1.0",
            "package_name": PACKAGE_NAME,
            "package_status": PACKAGE_NAME,
            "execution_mode": "AUDIT_EXISTING_REAL_RECEIPTS",
            "evidence_class": "REAL_SOURCE_ATTEMPT_METADATA",
            "market": "KUWAIT",
            "run_id": checked_run,
            "code_sha": checked_sha,
            "window": {
                "inclusive_from": WINDOW_FROM.isoformat(),
                "inclusive_to": WINDOW_TO.isoformat(),
                "day_count": WINDOW_DAY_COUNT,
            },
            "scheduled_at": _timestamp(scheduled),
            "actual_started_at": _timestamp(started),
            "finished_at": _timestamp(finished),
            "policy_sha256": policy_report["policy_sha256"],
            "source_registry_sha256": registry_sha,
            "production_checkpoint_store_status": "BLOCKED_CHECKPOINT_STORE",
            "counts": dict(coverage["counts"]),
            "files": inventory,
            "coverage_report_digest": coverage["report_digest"],
            "training_cycle_status": "BLOCKED_DATASET_RELEASE",
            "claim_boundaries": dict(MANIFEST_BOUNDARIES),
            "manifest_digest": "",
        }
        manifest["manifest_digest"] = _digest(manifest, "manifest_digest")
        _write_exclusive(staging / "run-manifest.json", canonical_json_bytes(manifest))
        return validate_rights_aware_bundle(root, staging)

    return run_atomic_output(Path(output_root), worker)


__all__ = [
    "CLASSIFICATIONS",
    "PACKAGE_NAME",
    "POLICY_PATH",
    "REQUIRED_FILES",
    "RightsAwareBackfillError",
    "WINDOW_DAY_COUNT",
    "WINDOW_FROM",
    "WINDOW_TO",
    "build_rights_aware_bundle",
    "validate_backfill_policy",
    "validate_rights_aware_bundle",
]
