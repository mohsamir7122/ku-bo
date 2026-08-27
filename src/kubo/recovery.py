"""Fail-closed recovery, retry, alert, and lease primitives for KU-BO.

This module deliberately contains no GitHub or market-network client.  It
validates incidents and makes deterministic decisions that an external
controller may execute with narrowly scoped credentials.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
from typing import Any, Callable, Iterator, Mapping, Sequence
from urllib.parse import urlsplit

from .foundation_io import load_strict_json_object, safe_regular_file, strict_json_object
from .strict import https_url, parse_aware, require_sha256, sensitive_query_key, strict_bool


POLICY_PATH = Path("config/recovery-policy.json")
SCHEMA_PATH = Path("schemas/recovery-incident.schema.json")
ERROR_CLASSES = frozenset(
    {
        "transient_network",
        "transient_source",
        "github_infrastructure",
        "source_access_blocked",
        "robots_unavailable",
        "robots_unreachable",
        "rate_limited",
        "missing_secret",
        "permission_required",
        "quota_or_billing",
        "data_quality",
        "provenance_failure",
        "temporal_leakage",
        "deterministic_code",
        "security",
        "terminal_unknown",
    }
)
MARKETS = frozenset({"KUWAIT", "SAUDI_ARABIA"})
INCIDENT_STATUSES = frozenset(
    {"OPEN", "RETRY_SCHEDULED", "PROBE_ONLY", "BLOCKED", "EXHAUSTED", "RESOLVED"}
)
ACTIVE_RUN_STATES = frozenset({"queued", "in_progress"})
SOURCE_FALLBACK_ORDER = (
    "official_documented_api_or_export",
    "alternate_official_page_or_repository",
    "issuer_official_disclosures",
    "regulator_official_records",
    "user_supplied_authorized_export",
    "secondary_discovery_only",
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CODE_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_INCIDENT_KEYS = frozenset(
    {
        "schema_version",
        "incident_id",
        "fingerprint",
        "idempotency_key",
        "fingerprint_basis",
        "market",
        "stage",
        "error_class",
        "retriable",
        "first_seen_at",
        "last_seen_at",
        "retry_after",
        "attempt_count",
        "max_attempts",
        "code_sha",
        "failed_run_id",
        "run_url",
        "checkpoint_id",
        "fallbacks_tried",
        "publish_allowed",
        "sanitized_summary",
        "required_user_action",
        "alert_sent_at",
        "status",
    }
)
_BASIS_KEYS = frozenset({"market", "stage", "error_class", "component", "failure_code"})
_LEASE_KEYS = frozenset(
    {
        "schema_version",
        "fingerprint",
        "run_id",
        "owner_run_id",
        "owner",
        "process_identity",
        "priority",
        "generation",
        "fencing_token",
        "checkpoint_id",
        "created_at",
        "expires_at",
        "heartbeat",
        "heartbeat_at",
        "preempt_requested",
        "preempt_requested_by_run_id",
        "preempt_requested_priority",
        "preempt_requested_at",
        "lease_digest",
    }
)
_ROOT_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "policy_id",
        "status",
        "market",
        "classifications",
        "retry",
        "lease",
        "alerts",
        "controller",
        "robots",
        "source_fallback_order",
        "claim_boundaries",
    }
)
_CLASSIFICATION_KEYS = frozenset(
    {"category", "automatic_retry", "health_probe_only", "immediate_alert"}
)
_REDACTED = "[REDACTED]"
_SENSITIVE_HEADER_RE = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie)\s*[:=]\s*[^\r\n;]+"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:access_token|api_key|apikey|auth|authorization|code|credential|"
    r"jwt|oauth_token|session|sessionid|sig|signature|token|x-amz-[a-z0-9_-]+|"
    r"x-goog-[a-z0-9_-]+)=)[^&#\s]+"
)
_ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|client_secret|private_key|sessionid|api_key|access_token)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_TOKEN_SHAPE_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{10,}\."
    r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
)


class RecoveryError(ValueError):
    """Raised when recovery input weakens or violates the locked contract."""


class LeaseError(RecoveryError):
    """Base class for recovery lease failures."""


class ActiveLeaseError(LeaseError):
    """Raised when a live lease or process must not be displaced."""


class LeaseRecoveryBlockedError(LeaseError):
    """Raised when an expired lease cannot be proven safe to recover."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise RecoveryError("value cannot be represented as canonical JSON") from exc


def _exact_mapping(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecoveryError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise RecoveryError(
            f"{field} has missing={sorted(keys - actual)} unknown={sorted(actual - keys)}"
        )
    return value


def _identifier(value: Any, field: str) -> str:
    text = str(value or "")
    if not _ID_RE.fullmatch(text):
        raise RecoveryError(f"{field} must be a safe identifier")
    return text


def _utc(value: datetime | str, field: str) -> datetime:
    parsed = value if isinstance(value, datetime) else parse_aware(value, field)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecoveryError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _strict_boolean(value: Any, field: str) -> bool:
    try:
        return strict_bool(value, field)
    except ValueError as exc:
        raise RecoveryError(str(exc)) from exc


def _sensitive_field_name(value: Any) -> bool:
    normalized = str(value).strip().casefold().replace("-", "_")
    if normalized.endswith(("_name", "_present", "_status", "_class")):
        return False
    return sensitive_query_key(normalized) or normalized in {
        "authorization",
        "proxy_authorization",
        "set_cookie",
        "raw_authorization_headers",
    }


def sanitize_text(value: Any, *, max_length: int = 2000) -> str:
    """Return a bounded, single-line diagnostic string with credentials removed."""

    text = str(value).replace("\x00", "")
    text = _SENSITIVE_HEADER_RE.sub(lambda match: f"{match.group(1)}: {_REDACTED}", text)
    text = _BEARER_RE.sub(f"Bearer {_REDACTED}", text)
    text = _QUERY_SECRET_RE.sub(lambda match: f"{match.group(1)}{_REDACTED}", text)
    text = _ASSIGNMENT_SECRET_RE.sub(
        lambda match: f"{match.group(1)}={_REDACTED}", text
    )
    text = _TOKEN_SHAPE_RE.sub(_REDACTED, text)
    text = " ".join(text.split())
    if not text:
        text = "UNSPECIFIED_FAILURE"
    return text[:max_length]


def sanitize_diagnostics(value: Any) -> Any:
    """Recursively redact diagnostics without retaining credential-bearing objects."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = sanitize_text(raw_key, max_length=128)
            result[key] = _REDACTED if _sensitive_field_name(raw_key) else sanitize_diagnostics(item)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_diagnostics(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(value, max_length=4000)


def _expected_policy() -> dict[str, Any]:
    return {
        "retry": {
            "initial_delay_seconds": 0,
            "max_automatic_attempts": 2,
            "window_hours": 24,
            "active_run_states": ["queued", "in_progress"],
            "require_relevant_commit_for_deterministic": True,
            "require_ci_and_smoke_for_fixed_code_resume": True,
            "rerun_scope": "FAILED_JOBS_ONLY",
            "watchdog_may_delay_first_attempt": False,
            "idempotency_scope": "FINGERPRINT_CODE_SHA_RUN_ATTEMPT",
        },
        "lease": {
            "duration_seconds": 900,
            "heartbeat_interval_seconds": 60,
            "require_active_run_probe_for_expired_recovery": True,
        },
        "alerts": {
            "primary_channel": "GITHUB_ISSUE",
            "issue_title": "[URGENT][KUWAIT MARKET] Pipeline blocked",
            "labels": ["automation-blocked", "recovery-exhausted", "no-trade"],
            "assignee": "mohsamir7122",
            "duplicate_suppression_hours": 6,
            "direct_email_status": "DIRECT_EMAIL_NOT_CONFIGURED",
        },
        "controller": {
            "schedule_cron": "2,7,12,17,22,27,32,37,42,47,52,57 * * * *",
            "dispatch_event": "market-recovery-request",
            "allowed_repository_dispatch_actions": ["retry", "resume", "probe"],
            "pipeline_workflow": "kuwait-market-pipeline.yml",
            "concurrency_group": "kubo-kuwait-market-ai",
            "may_modify_default_branch": False,
            "watchdog_mode": "MISSED_EVENTS_ONLY",
            "missed_event_grace_seconds": 300,
            "critical_path_wait_seconds": 0,
        },
        "robots": {
            "maximum_redirects": 5,
            "maximum_cache_hours": 24,
            "not_found_requires_rights_terms_and_public_access": True,
            "access_receipt_proves_collection": False,
        },
        "source_fallback_order": list(SOURCE_FALLBACK_ORDER),
        "claim_boundaries": {
            "recovery_may_disable_safety_gate": False,
            "recovery_may_bypass_access_control": False,
            "recovery_may_publish_while_blocked": False,
            "recovery_may_submit_trade": False,
            "controller_may_merge_or_modify_main": False,
        },
    }


def load_recovery_policy(project_root: Path | str) -> tuple[dict[str, Any], bytes]:
    root = Path(project_root).resolve()
    try:
        payload, content = load_strict_json_object(
            root / POLICY_PATH, field="recovery policy", max_bytes=512 * 1024
        )
    except ValueError as exc:
        raise RecoveryError(str(exc)) from exc
    _exact_mapping(payload, _ROOT_POLICY_KEYS, "recovery policy")
    if (
        payload["schema_version"] != "1.0"
        or payload["policy_id"] != "ku-bo-recovery-and-resume-v1"
        or payload["status"] != "FAIL_CLOSED"
        or payload["market"] != "KUWAIT"
    ):
        raise RecoveryError("recovery policy identity or status changed")
    classifications = payload["classifications"]
    if not isinstance(classifications, Mapping) or frozenset(classifications) != ERROR_CLASSES:
        raise RecoveryError("recovery classifications must be exact and complete")
    for error_class, raw in classifications.items():
        row = _exact_mapping(raw, _CLASSIFICATION_KEYS, f"classifications.{error_class}")
        if row["category"] not in {
            "TRANSIENT",
            "POLICY",
            "PERMISSION",
            "DETERMINISTIC",
            "SECURITY",
            "TERMINAL",
        }:
            raise RecoveryError(f"classifications.{error_class}.category is invalid")
        for key in ("automatic_retry", "health_probe_only", "immediate_alert"):
            _strict_boolean(row[key], f"classifications.{error_class}.{key}")
        if row["automatic_retry"] and row["category"] != "TRANSIENT":
            raise RecoveryError("only transient failures may retry automatically")
        if row["category"] == "SECURITY" and not row["immediate_alert"]:
            raise RecoveryError("security failures require an immediate alert")
    expected = _expected_policy()
    for key, value in expected.items():
        if payload[key] != value:
            raise RecoveryError(f"recovery policy {key} was weakened or changed")
    return payload, content


def validate_recovery_policy(project_root: Path | str) -> dict[str, Any]:
    payload, content = load_recovery_policy(project_root)
    return {
        "schema_version": "1.0",
        "status": "PASS_FAIL_CLOSED_RECOVERY_POLICY",
        "policy_id": payload["policy_id"],
        "classification_count": len(payload["classifications"]),
        "policy_sha256": hashlib.sha256(content).hexdigest(),
        "maximum_automatic_attempts": payload["retry"]["max_automatic_attempts"],
        "direct_email_status": payload["alerts"]["direct_email_status"],
        "publish_allowed_while_blocked": False,
    }


def next_source_fallback(
    policy: Mapping[str, Any], fallbacks_tried: Sequence[str]
) -> str | None:
    """Return only the next legal fallback in the locked primary-first order."""

    configured = policy.get("source_fallback_order")
    if configured != list(SOURCE_FALLBACK_ORDER):
        raise RecoveryError("source fallback order differs from trusted policy")
    attempted = tuple(str(item) for item in fallbacks_tried)
    if len(attempted) > len(SOURCE_FALLBACK_ORDER):
        raise RecoveryError("source fallback attempts exceed the trusted chain")
    if attempted != SOURCE_FALLBACK_ORDER[: len(attempted)]:
        raise RecoveryError("source fallbacks must be an ordered prefix of the trusted chain")
    return (
        SOURCE_FALLBACK_ORDER[len(attempted)]
        if len(attempted) < len(SOURCE_FALLBACK_ORDER)
        else None
    )


def fingerprint_basis(
    *, market: Any, stage: Any, error_class: Any, component: Any, failure_code: Any
) -> dict[str, str]:
    normalized_market = str(market or "").upper()
    if normalized_market not in MARKETS:
        raise RecoveryError("market is not admitted")
    normalized_error = str(error_class or "").casefold()
    if normalized_error not in ERROR_CLASSES:
        raise RecoveryError("error_class is not admitted")
    return {
        "market": normalized_market,
        "stage": _identifier(str(stage or "").casefold(), "stage"),
        "error_class": normalized_error,
        "component": _identifier(str(component or "").casefold(), "component"),
        "failure_code": _identifier(str(failure_code or "").upper(), "failure_code"),
    }


def stable_fingerprint(
    *, market: Any, stage: Any, error_class: Any, component: Any, failure_code: Any
) -> str:
    basis = fingerprint_basis(
        market=market,
        stage=stage,
        error_class=error_class,
        component=component,
        failure_code=failure_code,
    )
    return hashlib.sha256(_canonical_json(basis)).hexdigest()


def _validated_code_sha(value: Any) -> str:
    code_sha = str(value or "").casefold()
    if not _CODE_SHA_RE.fullmatch(code_sha):
        raise RecoveryError("code_sha must be a lowercase 40- or 64-character SHA")
    return code_sha


def _validated_run_url(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        url = https_url(value, "run_url")
    except ValueError as exc:
        raise RecoveryError(str(exc)) from exc
    if (urlsplit(url).hostname or "").casefold() != "github.com":
        raise RecoveryError("run_url must use github.com")
    return url


def recovery_idempotency_key(
    *, fingerprint: Any, code_sha: Any, failed_run_id: Any, attempt_count: Any
) -> str:
    """Derive the retry identity from validated incident state.

    Callers cannot choose this value: validation recomputes it from the stable
    failure fingerprint, exact code revision, failed run, and bounded attempt.
    """

    try:
        normalized_fingerprint = require_sha256(fingerprint, "fingerprint")
    except ValueError as exc:
        raise RecoveryError(str(exc)) from exc
    normalized_code_sha = _validated_code_sha(code_sha)
    normalized_run_id = _identifier(failed_run_id, "failed_run_id")
    if type(attempt_count) is not int or attempt_count < 0:
        raise RecoveryError("attempt_count must be a non-negative integer")
    basis = {
        "fingerprint": normalized_fingerprint,
        "code_sha": normalized_code_sha,
        "failed_run_id": normalized_run_id,
        "attempt_count": attempt_count,
    }
    return hashlib.sha256(_canonical_json(basis)).hexdigest()


def build_incident(
    project_root: Path | str,
    *,
    market: Any,
    stage: Any,
    error_class: Any,
    component: Any,
    failure_code: Any,
    code_sha: Any,
    failed_run_id: Any,
    summary: Any,
    now: datetime,
    run_url: Any = None,
    checkpoint_id: Any = None,
    fallbacks_tried: Sequence[Any] = (),
    required_user_action: Any = None,
) -> dict[str, Any]:
    policy, _ = load_recovery_policy(project_root)
    observed_at = _utc(now, "now")
    basis = fingerprint_basis(
        market=market,
        stage=stage,
        error_class=error_class,
        component=component,
        failure_code=failure_code,
    )
    fingerprint = hashlib.sha256(_canonical_json(basis)).hexdigest()
    normalized_code_sha = _validated_code_sha(code_sha)
    normalized_run_id = _identifier(failed_run_id, "failed_run_id")
    classification = policy["classifications"][basis["error_class"]]
    retriable = bool(classification["automatic_retry"])
    if retriable:
        status = "RETRY_SCHEDULED"
        retry_after = _timestamp(
            observed_at + timedelta(seconds=policy["retry"]["initial_delay_seconds"])
        )
    elif classification["health_probe_only"]:
        status = "PROBE_ONLY"
        retry_after = None
    else:
        status = "BLOCKED"
        retry_after = None
    checkpoint = None if checkpoint_id in (None, "") else _identifier(checkpoint_id, "checkpoint_id")
    action = (
        None
        if required_user_action in (None, "")
        else sanitize_text(required_user_action, max_length=1000)
    )
    incident = {
        "schema_version": "1.0",
        "incident_id": f"INC-{fingerprint[:20].upper()}",
        "fingerprint": fingerprint,
        "idempotency_key": recovery_idempotency_key(
            fingerprint=fingerprint,
            code_sha=normalized_code_sha,
            failed_run_id=normalized_run_id,
            attempt_count=0,
        ),
        "fingerprint_basis": basis,
        "market": basis["market"],
        "stage": basis["stage"],
        "error_class": basis["error_class"],
        "retriable": retriable,
        "first_seen_at": _timestamp(observed_at),
        "last_seen_at": _timestamp(observed_at),
        "retry_after": retry_after,
        "attempt_count": 0,
        "max_attempts": policy["retry"]["max_automatic_attempts"],
        "code_sha": normalized_code_sha,
        "failed_run_id": normalized_run_id,
        "run_url": _validated_run_url(run_url),
        "checkpoint_id": checkpoint,
        "fallbacks_tried": [
            _identifier(item, f"fallbacks_tried[{index}]")
            for index, item in enumerate(fallbacks_tried)
        ],
        "publish_allowed": False,
        "sanitized_summary": sanitize_text(summary),
        "required_user_action": action,
        "alert_sent_at": None,
        "status": status,
    }
    return validate_incident(incident, policy=policy)


def _incident(value: Path | str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        payload, _ = load_strict_json_object(
            Path(value), field="recovery incident", max_bytes=1024 * 1024
        )
    except ValueError as exc:
        raise RecoveryError(str(exc)) from exc
    return payload


def validate_incident(
    value: Path | str | Mapping[str, Any],
    *,
    project_root: Path | str | None = None,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _incident(value)
    _exact_mapping(payload, _INCIDENT_KEYS, "recovery incident")
    if policy is None:
        if project_root is None:
            raise RecoveryError("project_root or validated policy is required")
        policy, _ = load_recovery_policy(project_root)
    if payload["schema_version"] != "1.0":
        raise RecoveryError("incident schema_version must be 1.0")
    basis = _exact_mapping(payload["fingerprint_basis"], _BASIS_KEYS, "fingerprint_basis")
    canonical_basis = fingerprint_basis(**dict(basis))
    fingerprint = hashlib.sha256(_canonical_json(canonical_basis)).hexdigest()
    try:
        submitted = require_sha256(payload["fingerprint"], "fingerprint")
    except ValueError as exc:
        raise RecoveryError(str(exc)) from exc
    if submitted != fingerprint:
        raise RecoveryError("incident fingerprint does not match its canonical basis")
    if payload["incident_id"] != f"INC-{fingerprint[:20].upper()}":
        raise RecoveryError("incident_id does not match fingerprint")
    if payload["market"] != canonical_basis["market"]:
        raise RecoveryError("incident market differs from fingerprint basis")
    if payload["stage"] != canonical_basis["stage"]:
        raise RecoveryError("incident stage differs from fingerprint basis")
    if payload["error_class"] != canonical_basis["error_class"]:
        raise RecoveryError("incident error_class differs from fingerprint basis")
    classification = policy["classifications"][payload["error_class"]]
    retriable = _strict_boolean(payload["retriable"], "retriable")
    if retriable is not classification["automatic_retry"]:
        raise RecoveryError("incident retriable flag conflicts with trusted policy")
    first_seen = _utc(payload["first_seen_at"], "first_seen_at")
    last_seen = _utc(payload["last_seen_at"], "last_seen_at")
    if last_seen < first_seen:
        raise RecoveryError("last_seen_at precedes first_seen_at")
    attempts = payload["attempt_count"]
    maximum = payload["max_attempts"]
    if type(attempts) is not int or attempts < 0:
        raise RecoveryError("attempt_count must be a non-negative integer")
    if type(maximum) is not int or maximum != policy["retry"]["max_automatic_attempts"]:
        raise RecoveryError("max_attempts differs from trusted policy")
    if attempts > maximum:
        raise RecoveryError("attempt_count exceeds max_attempts")
    expected_idempotency_key = recovery_idempotency_key(
        fingerprint=submitted,
        code_sha=payload["code_sha"],
        failed_run_id=payload["failed_run_id"],
        attempt_count=attempts,
    )
    try:
        submitted_idempotency_key = require_sha256(
            payload["idempotency_key"], "idempotency_key"
        )
    except ValueError as exc:
        raise RecoveryError(str(exc)) from exc
    if submitted_idempotency_key != expected_idempotency_key:
        raise RecoveryError("incident idempotency_key does not match canonical retry state")
    retry_after = payload["retry_after"]
    if retry_after is not None:
        due = _utc(retry_after, "retry_after")
        if due < last_seen:
            raise RecoveryError("retry_after precedes last_seen_at")
        if retriable and attempts < maximum and due != last_seen:
            raise RecoveryError("automatic workflow retry must be immediately due")
    if retriable and attempts < maximum and payload["status"] != "RESOLVED" and retry_after is None:
        raise RecoveryError("retriable incident requires retry_after")
    if (not retriable or attempts >= maximum or payload["status"] == "RESOLVED") and retry_after is not None:
        raise RecoveryError("blocked, exhausted, or resolved incident cannot retain retry_after")
    _validated_code_sha(payload["code_sha"])
    _identifier(payload["failed_run_id"], "failed_run_id")
    _validated_run_url(payload["run_url"])
    if payload["checkpoint_id"] is not None:
        _identifier(payload["checkpoint_id"], "checkpoint_id")
    fallbacks = payload["fallbacks_tried"]
    if not isinstance(fallbacks, list) or len(fallbacks) > 64:
        raise RecoveryError("fallbacks_tried must be a bounded list")
    checked_fallbacks = [
        _identifier(item, f"fallbacks_tried[{index}]") for index, item in enumerate(fallbacks)
    ]
    if len(checked_fallbacks) != len(set(checked_fallbacks)):
        raise RecoveryError("fallbacks_tried must be unique")
    if payload["publish_allowed"] is not False:
        raise RecoveryError("incident must fail closed with publish_allowed=false")
    summary = payload["sanitized_summary"]
    if not isinstance(summary, str) or not summary or len(summary) > 2000:
        raise RecoveryError("sanitized_summary must be a bounded non-empty string")
    if sanitize_text(summary) != summary:
        raise RecoveryError("sanitized_summary still contains sensitive material")
    action = payload["required_user_action"]
    if action is not None:
        if not isinstance(action, str) or not action or len(action) > 1000:
            raise RecoveryError("required_user_action must be null or a bounded string")
        if sanitize_text(action, max_length=1000) != action:
            raise RecoveryError("required_user_action still contains sensitive material")
    if payload["alert_sent_at"] is not None:
        alert_at = _utc(payload["alert_sent_at"], "alert_sent_at")
        if alert_at < first_seen:
            raise RecoveryError("alert_sent_at precedes first_seen_at")
    status = payload["status"]
    if status not in INCIDENT_STATUSES:
        raise RecoveryError("incident status is invalid")
    if attempts >= maximum and status not in {"EXHAUSTED", "RESOLVED"}:
        raise RecoveryError("incident at the attempt cap must be exhausted or resolved")
    if classification["category"] == "SECURITY" and status not in {"BLOCKED", "RESOLVED"}:
        raise RecoveryError("security incidents must remain blocked")
    if classification["health_probe_only"] and status not in {"PROBE_ONLY", "BLOCKED", "RESOLVED"}:
        raise RecoveryError("health-probe-only incident has an unsafe status")
    return payload


def _has_active_market_run(
    incident: Mapping[str, Any], active_runs: Sequence[Mapping[str, Any]], policy: Mapping[str, Any]
) -> bool:
    active_states = frozenset(policy["retry"]["active_run_states"])
    for row in active_runs:
        if row.get("market") == incident["market"] and row.get("status") in active_states:
            return True
    return False


def alert_due(
    incident: Mapping[str, Any], *, now: datetime, policy: Mapping[str, Any]
) -> bool:
    validated = validate_incident(incident, policy=policy)
    if validated["alert_sent_at"] is None:
        return True
    sent = _utc(validated["alert_sent_at"], "alert_sent_at")
    current = _utc(now, "now")
    return current >= sent + timedelta(hours=policy["alerts"]["duplicate_suppression_hours"])


def recovery_decision(
    incident: Mapping[str, Any],
    *,
    now: datetime,
    policy: Mapping[str, Any],
    active_runs: Sequence[Mapping[str, Any]] = (),
    required_secret_available: bool | None = None,
    current_code_sha: str | None = None,
    relevant_code_change: bool = False,
    ci_passed: bool = False,
    smoke_passed: bool = False,
) -> dict[str, Any]:
    row = validate_incident(incident, policy=policy)
    current = _utc(now, "now")
    classification = policy["classifications"][row["error_class"]]
    wants_alert = bool(classification["immediate_alert"]) and alert_due(
        row, now=current, policy=policy
    )
    base = {
        "schema_version": "1.0",
        "incident_id": row["incident_id"],
        "fingerprint": row["fingerprint"],
        "publish_allowed": False,
        "alert_due": wants_alert,
    }
    if row["status"] == "RESOLVED":
        return {**base, "action": "NO_ACTION_RESOLVED", "dispatch_allowed": False}
    if classification["category"] == "SECURITY":
        return {**base, "action": "BLOCK_SECURITY", "dispatch_allowed": False, "alert_due": alert_due(row, now=current, policy=policy)}
    if row["error_class"] == "missing_secret":
        if required_secret_available is not True:
            return {**base, "action": "HEALTH_PROBE_ONLY", "dispatch_allowed": False}
        if _has_active_market_run(row, active_runs, policy):
            return {**base, "action": "SUPPRESS_ACTIVE_RUN", "dispatch_allowed": False}
        return {**base, "action": "DISPATCH_RESUME_AFTER_SECRET", "dispatch_allowed": True}
    if row["error_class"] == "deterministic_code":
        changed = current_code_sha is not None and _validated_code_sha(current_code_sha) != row["code_sha"]
        gates = relevant_code_change and ci_passed and smoke_passed
        if not (changed and gates):
            return {**base, "action": "NO_RETRY_DETERMINISTIC", "dispatch_allowed": False}
        if _has_active_market_run(row, active_runs, policy):
            return {**base, "action": "SUPPRESS_ACTIVE_RUN", "dispatch_allowed": False}
        return {**base, "action": "DISPATCH_RESUME_AFTER_VALIDATED_FIX", "dispatch_allowed": True}
    if not row["retriable"]:
        return {**base, "action": "NO_RETRY_BLOCKED", "dispatch_allowed": False}
    if _has_active_market_run(row, active_runs, policy):
        return {**base, "action": "SUPPRESS_ACTIVE_RUN", "dispatch_allowed": False}
    if row["attempt_count"] >= row["max_attempts"]:
        return {
            **base,
            "action": "RETRY_EXHAUSTED",
            "dispatch_allowed": False,
            "alert_due": alert_due(row, now=current, policy=policy),
        }
    first_seen = _utc(row["first_seen_at"], "first_seen_at")
    if current > first_seen + timedelta(hours=policy["retry"]["window_hours"]):
        return {
            **base,
            "action": "RETRY_WINDOW_EXPIRED",
            "dispatch_allowed": False,
            "alert_due": alert_due(row, now=current, policy=policy),
        }
    due = _utc(row["retry_after"], "retry_after")
    if current < due:
        return {
            **base,
            "action": "WAIT_RETRY_NOT_DUE",
            "dispatch_allowed": False,
            "retry_after": row["retry_after"],
        }
    return {**base, "action": "DISPATCH_RETRY", "dispatch_allowed": True}


def record_retry_attempt(
    incident: Mapping[str, Any], *, now: datetime, policy: Mapping[str, Any]
) -> dict[str, Any]:
    row = dict(validate_incident(incident, policy=policy))
    if not row["retriable"] or row["status"] == "RESOLVED":
        raise RecoveryError("incident is not eligible for an automatic retry")
    if row["attempt_count"] >= row["max_attempts"]:
        raise RecoveryError("automatic retry cap is exhausted")
    current = _utc(now, "now")
    due = _utc(row["retry_after"], "retry_after")
    if current < due:
        raise RecoveryError("automatic retry is not due")
    first_seen = _utc(row["first_seen_at"], "first_seen_at")
    if current > first_seen + timedelta(hours=policy["retry"]["window_hours"]):
        raise RecoveryError("automatic retry window is expired")
    row["attempt_count"] += 1
    row["last_seen_at"] = _timestamp(current)
    row["idempotency_key"] = recovery_idempotency_key(
        fingerprint=row["fingerprint"],
        code_sha=row["code_sha"],
        failed_run_id=row["failed_run_id"],
        attempt_count=row["attempt_count"],
    )
    if row["attempt_count"] >= row["max_attempts"]:
        row["retry_after"] = None
        row["status"] = "EXHAUSTED"
    else:
        row["retry_after"] = _timestamp(current)
        row["status"] = "RETRY_SCHEDULED"
    return validate_incident(row, policy=policy)


def mark_alert_sent(
    incident: Mapping[str, Any], *, now: datetime, policy: Mapping[str, Any]
) -> dict[str, Any]:
    row = dict(validate_incident(incident, policy=policy))
    current = _utc(now, "now")
    if current < _utc(row["first_seen_at"], "first_seen_at"):
        raise RecoveryError("cannot record an alert before first_seen_at")
    row["alert_sent_at"] = _timestamp(current)
    return validate_incident(row, policy=policy)


def resolve_incident(
    incident: Mapping[str, Any], *, now: datetime, policy: Mapping[str, Any]
) -> dict[str, Any]:
    row = dict(validate_incident(incident, policy=policy))
    current = _utc(now, "now")
    if current < _utc(row["last_seen_at"], "last_seen_at"):
        raise RecoveryError("resolution timestamp precedes last_seen_at")
    row["last_seen_at"] = _timestamp(current)
    row["retry_after"] = None
    row["status"] = "RESOLVED"
    row["publish_allowed"] = False
    return validate_incident(row, policy=policy)


def validate_dispatch_inputs(
    *, mode: Any, incident_id: Any = None, checkpoint: Any = None
) -> dict[str, str | None]:
    normalized_mode = str(mode or "")
    if normalized_mode not in {"normal", "retry", "resume"}:
        raise RecoveryError("mode must be normal, retry, or resume")
    normalized_incident = None
    if incident_id not in (None, ""):
        normalized_incident = str(incident_id)
        if not re.fullmatch(r"INC-[0-9A-F]{20}", normalized_incident):
            raise RecoveryError("incident_id is invalid")
    normalized_checkpoint = None
    if checkpoint not in (None, ""):
        normalized_checkpoint = _identifier(checkpoint, "checkpoint")
    if normalized_mode in {"retry", "resume"} and normalized_incident is None:
        raise RecoveryError("retry and resume require incident_id")
    if normalized_mode == "normal" and (normalized_incident or normalized_checkpoint):
        raise RecoveryError("normal mode cannot accept incident or checkpoint overrides")
    if normalized_mode == "retry" and normalized_checkpoint is not None:
        raise RecoveryError("retry mode cannot accept a checkpoint")
    return {
        "mode": normalized_mode,
        "incident_id": normalized_incident,
        "checkpoint": normalized_checkpoint,
    }


def current_process_identity() -> str:
    pid = os.getpid()
    start = "unknown"
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
        start = fields[21]
    except (OSError, UnicodeError, IndexError):
        pass
    host = re.sub(r"[^A-Za-z0-9._-]", "_", socket.gethostname())[:63] or "unknown"
    return f"local:{host}:{pid}:{start}"


def _local_process_active(identity: str) -> bool:
    match = re.fullmatch(r"local:([A-Za-z0-9._-]+):([0-9]+):([A-Za-z0-9._-]+)", identity)
    if not match:
        return False
    host, raw_pid, expected_start = match.groups()
    current_host = re.sub(r"[^A-Za-z0-9._-]", "_", socket.gethostname())[:63] or "unknown"
    if host != current_host:
        return False
    pid = int(raw_pid)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
    except (OSError, UnicodeError, ValueError):
        # Some constrained runtimes hide the caller from /proc. The current
        # interpreter is nevertheless definitive proof that its own PID is
        # alive; treating an unknown self lease as recoverable would violate
        # the fail-closed lease rule.
        return pid == os.getpid()
    if expected_start == "unknown":
        return pid == os.getpid()
    return len(fields) > 21 and fields[21] == expected_start


def _safe_lease_root(root: Path) -> Path:
    absolute = Path(os.path.abspath(root))
    existing = absolute
    while not existing.exists():
        if existing.parent == existing:
            break
        existing = existing.parent
    if existing.is_symlink():
        raise LeaseError("lease root must not traverse a symlink")
    absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode):
            raise LeaseError("lease root must not traverse a symlink")
        if current == absolute and not stat.S_ISDIR(metadata.st_mode):
            raise LeaseError("lease root must be a directory")
    return absolute


def _lease_paths(root: Path, fingerprint: str) -> tuple[Path, Path]:
    try:
        checked = require_sha256(fingerprint, "fingerprint")
    except ValueError as exc:
        raise LeaseError(str(exc)) from exc
    safe_root = _safe_lease_root(root)
    return safe_root / f"{checked}.lease.json", safe_root / f"{checked}.guard"


@contextmanager
def _guard(path: Path) -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise LeaseError("cannot open lease guard safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LeaseError("lease guard must be a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _lease_digest(payload: Mapping[str, Any]) -> str:
    material = {key: value for key, value in payload.items() if key != "lease_digest"}
    return hashlib.sha256(_canonical_json(material)).hexdigest()


def _lease_priority(value: Any, field: str = "priority") -> int:
    if type(value) is not int or not 0 <= value <= 100:
        raise LeaseError(f"{field} must be an integer from 0 through 100")
    return value


def _lease_generation(value: Any, field: str = "generation") -> int:
    if type(value) is not int or value < 1:
        raise LeaseError(f"{field} must be a positive integer")
    return value


def lease_fencing_token(
    *, fingerprint: Any, owner_run_id: Any, generation: Any, created_at: Any
) -> str:
    try:
        checked_fingerprint = require_sha256(fingerprint, "fingerprint")
    except ValueError as exc:
        raise LeaseError(str(exc)) from exc
    basis = {
        "fingerprint": checked_fingerprint,
        "owner_run_id": _identifier(owner_run_id, "owner_run_id"),
        "generation": _lease_generation(generation),
        "created_at": _timestamp(_utc(created_at, "created_at")),
    }
    return hashlib.sha256(_canonical_json(basis)).hexdigest()


def _validate_lease(payload: Mapping[str, Any], *, fingerprint: str) -> dict[str, Any]:
    row = dict(_exact_mapping(payload, _LEASE_KEYS, "recovery lease"))
    if row["schema_version"] != "2.0" or row["fingerprint"] != fingerprint:
        raise LeaseError("lease identity differs from its trusted path")
    for key in ("run_id", "owner_run_id", "owner"):
        _identifier(row[key], f"lease.{key}")
    if row["run_id"] != row["owner_run_id"]:
        raise LeaseError("lease run_id and owner_run_id must match")
    identity = str(row["process_identity"] or "")
    if not identity or len(identity) > 256 or any(ord(char) < 32 for char in identity):
        raise LeaseError("lease.process_identity is invalid")
    created = _utc(row["created_at"], "lease.created_at")
    heartbeat = _utc(row["heartbeat"], "lease.heartbeat")
    heartbeat_at = _utc(row["heartbeat_at"], "lease.heartbeat_at")
    expires = _utc(row["expires_at"], "lease.expires_at")
    if heartbeat != heartbeat_at or heartbeat < created or expires <= heartbeat:
        raise LeaseError("lease timestamps are inconsistent")
    priority = _lease_priority(row["priority"], "lease.priority")
    generation = _lease_generation(row["generation"], "lease.generation")
    try:
        fencing_token = require_sha256(row["fencing_token"], "lease.fencing_token")
    except ValueError as exc:
        raise LeaseError(str(exc)) from exc
    if fencing_token != lease_fencing_token(
        fingerprint=fingerprint,
        owner_run_id=row["owner_run_id"],
        generation=generation,
        created_at=created,
    ):
        raise LeaseError("lease fencing_token does not match canonical lease state")
    if row["checkpoint_id"] is not None:
        _identifier(row["checkpoint_id"], "lease.checkpoint_id")
    preempt_requested = _strict_boolean(
        row["preempt_requested"], "lease.preempt_requested"
    )
    preempt_fields = (
        row["preempt_requested_by_run_id"],
        row["preempt_requested_priority"],
        row["preempt_requested_at"],
    )
    if preempt_requested:
        _identifier(preempt_fields[0], "lease.preempt_requested_by_run_id")
        requested_priority = _lease_priority(
            preempt_fields[1], "lease.preempt_requested_priority"
        )
        requested_at = _utc(preempt_fields[2], "lease.preempt_requested_at")
        if requested_priority <= priority or requested_at < created:
            raise LeaseError("lease preemption request is not a valid priority upgrade")
    elif preempt_fields != (None, None, None):
        raise LeaseError("lease has preemption details without a request")
    try:
        submitted = require_sha256(row["lease_digest"], "lease.lease_digest")
    except ValueError as exc:
        raise LeaseError(str(exc)) from exc
    if submitted != _lease_digest(row):
        raise LeaseError("lease digest mismatch")
    return row


def _read_lease(path: Path, *, fingerprint: str) -> dict[str, Any] | None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LeaseError("cannot inspect recovery lease safely") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise LeaseError("recovery lease must be a real regular file")
    try:
        content = safe_regular_file(path, field="recovery lease", max_bytes=64 * 1024)
        payload = strict_json_object(content, "recovery lease")
    except ValueError as exc:
        raise LeaseError(str(exc)) from exc
    return _validate_lease(payload, fingerprint=fingerprint)


def _write_lease(path: Path, payload: Mapping[str, Any]) -> None:
    content = _canonical_json(payload) + b"\n"
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise LeaseError("cannot inspect lease target safely") from exc
    if existing is not None and (
        stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)
    ):
        raise LeaseError("lease target must be a real regular file")
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        try:
            descriptor = os.open(temporary, flags, 0o600)
        except OSError as exc:
            raise LeaseError("cannot write lease safely") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise LeaseError("lease target must be a regular file")
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(content):
                offset += os.write(descriptor, content[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        directory = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except (OSError, LeaseError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, LeaseError):
            raise
        raise LeaseError("cannot publish lease atomically") from exc


def acquire_recovery_lease(
    lease_root: Path | str,
    *,
    fingerprint: str,
    run_id: Any,
    owner: Any,
    process_identity: str | None = None,
    now: datetime,
    policy: Mapping[str, Any],
    active_run_probe: Callable[[str], bool] | None = None,
    priority: int = 90,
    generation: int = 1,
    checkpoint_id: Any = None,
    expected_generation: int | None = None,
) -> dict[str, Any]:
    lease_path, guard_path = _lease_paths(Path(lease_root), fingerprint)
    current = _utc(now, "now")
    identity = process_identity or current_process_identity()
    checked_run = _identifier(run_id, "run_id")
    checked_owner = _identifier(owner, "owner")
    checked_priority = _lease_priority(priority)
    checked_generation = _lease_generation(generation)
    checked_checkpoint = (
        None
        if checkpoint_id in (None, "")
        else _identifier(checkpoint_id, "checkpoint_id")
    )
    if expected_generation is not None and (
        type(expected_generation) is not int or expected_generation < 0
    ):
        raise LeaseError("expected_generation must be a non-negative integer")
    with _guard(guard_path):
        existing = _read_lease(lease_path, fingerprint=fingerprint)
        if existing is not None:
            if expected_generation is not None and existing["generation"] != expected_generation:
                raise LeaseRecoveryBlockedError("lease generation CAS mismatch")
            expires = _utc(existing["expires_at"], "lease.expires_at")
            if expires > current:
                raise ActiveLeaseError("active lease must not be replaced")
            if _local_process_active(existing["process_identity"]):
                raise ActiveLeaseError("expired lease owner process is still active")
            if policy["lease"]["require_active_run_probe_for_expired_recovery"]:
                if active_run_probe is None:
                    raise LeaseRecoveryBlockedError(
                        "expired lease recovery requires an active-run probe"
                    )
                try:
                    active = active_run_probe(fingerprint)
                except Exception as exc:  # external probe must fail closed
                    raise LeaseRecoveryBlockedError("active-run probe failed") from exc
                if type(active) is not bool:
                    raise LeaseRecoveryBlockedError("active-run probe returned a non-boolean")
                if active:
                    raise ActiveLeaseError("an active run exists for the lease fingerprint")
            if generation == 1 and expected_generation is None:
                checked_generation = existing["generation"] + 1
            if checked_generation <= existing["generation"]:
                raise LeaseRecoveryBlockedError(
                    "recovered lease generation must increase monotonically"
                )
        elif expected_generation not in (None, 0):
            raise LeaseRecoveryBlockedError("new lease generation CAS mismatch")
        duration = policy["lease"]["duration_seconds"]
        created_at = _timestamp(current)
        lease = {
            "schema_version": "2.0",
            "fingerprint": fingerprint,
            "run_id": checked_run,
            "owner_run_id": checked_run,
            "owner": checked_owner,
            "process_identity": identity,
            "priority": checked_priority,
            "generation": checked_generation,
            "fencing_token": lease_fencing_token(
                fingerprint=fingerprint,
                owner_run_id=checked_run,
                generation=checked_generation,
                created_at=created_at,
            ),
            "checkpoint_id": checked_checkpoint,
            "created_at": created_at,
            "expires_at": _timestamp(current + timedelta(seconds=duration)),
            "heartbeat": _timestamp(current),
            "heartbeat_at": _timestamp(current),
            "preempt_requested": False,
            "preempt_requested_by_run_id": None,
            "preempt_requested_priority": None,
            "preempt_requested_at": None,
            "lease_digest": "",
        }
        lease["lease_digest"] = _lease_digest(lease)
        validated = _validate_lease(lease, fingerprint=fingerprint)
        _write_lease(lease_path, validated)
        return validated


def heartbeat_recovery_lease(
    lease_root: Path | str,
    *,
    fingerprint: str,
    run_id: Any,
    owner: Any,
    process_identity: str,
    now: datetime,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    lease_path, guard_path = _lease_paths(Path(lease_root), fingerprint)
    current = _utc(now, "now")
    with _guard(guard_path):
        row = _read_lease(lease_path, fingerprint=fingerprint)
        if row is None:
            raise LeaseError("cannot heartbeat a missing lease")
        if (
            row["run_id"] != _identifier(run_id, "run_id")
            or row["owner"] != _identifier(owner, "owner")
            or row["process_identity"] != process_identity
        ):
            raise ActiveLeaseError("only the current lease owner may heartbeat")
        if _utc(row["expires_at"], "lease.expires_at") <= current:
            raise LeaseError("expired lease cannot be renewed without safe recovery")
        if current < _utc(row["heartbeat"], "lease.heartbeat"):
            raise LeaseError("heartbeat timestamp cannot move backwards")
        row["heartbeat"] = _timestamp(current)
        row["heartbeat_at"] = _timestamp(current)
        row["expires_at"] = _timestamp(
            current + timedelta(seconds=policy["lease"]["duration_seconds"])
        )
        row["lease_digest"] = _lease_digest(row)
        validated = _validate_lease(row, fingerprint=fingerprint)
        _write_lease(lease_path, validated)
        return validated


def request_recovery_lease_preemption(
    lease_root: Path | str,
    *,
    fingerprint: str,
    requester_run_id: Any,
    requester_priority: int,
    expected_generation: int,
    now: datetime,
) -> dict[str, Any]:
    """CAS-mark an active lower-priority lease for cooperative preemption."""

    lease_path, guard_path = _lease_paths(Path(lease_root), fingerprint)
    current = _utc(now, "now")
    checked_requester = _identifier(requester_run_id, "requester_run_id")
    checked_priority = _lease_priority(requester_priority, "requester_priority")
    checked_generation = _lease_generation(expected_generation, "expected_generation")
    with _guard(guard_path):
        row = _read_lease(lease_path, fingerprint=fingerprint)
        if row is None:
            raise LeaseRecoveryBlockedError("cannot preempt a missing lease")
        if row["generation"] != checked_generation:
            raise LeaseRecoveryBlockedError("lease generation CAS mismatch")
        if _utc(row["expires_at"], "lease.expires_at") <= current:
            raise LeaseRecoveryBlockedError("expired lease requires safe recovery, not preemption")
        if checked_priority <= row["priority"]:
            raise LeaseRecoveryBlockedError("preemption requires strictly higher priority")
        if row["preempt_requested"]:
            if (
                row["preempt_requested_by_run_id"] == checked_requester
                and row["preempt_requested_priority"] == checked_priority
            ):
                return row
            raise LeaseRecoveryBlockedError("a different preemption request already exists")
        row["preempt_requested"] = True
        row["preempt_requested_by_run_id"] = checked_requester
        row["preempt_requested_priority"] = checked_priority
        row["preempt_requested_at"] = _timestamp(current)
        row["lease_digest"] = _lease_digest(row)
        validated = _validate_lease(row, fingerprint=fingerprint)
        _write_lease(lease_path, validated)
        return validated


def release_recovery_lease(
    lease_root: Path | str,
    *,
    fingerprint: str,
    run_id: Any,
    owner: Any,
    process_identity: str,
) -> None:
    lease_path, guard_path = _lease_paths(Path(lease_root), fingerprint)
    with _guard(guard_path):
        row = _read_lease(lease_path, fingerprint=fingerprint)
        if row is None:
            return
        if (
            row["run_id"] != _identifier(run_id, "run_id")
            or row["owner"] != _identifier(owner, "owner")
            or row["process_identity"] != process_identity
        ):
            raise ActiveLeaseError("only the current lease owner may release it")
        try:
            lease_path.unlink()
        except OSError as exc:
            raise LeaseError("cannot release owned lease") from exc


def read_recovery_lease(
    lease_root: Path | str, *, fingerprint: str
) -> dict[str, Any] | None:
    lease_path, guard_path = _lease_paths(Path(lease_root), fingerprint)
    with _guard(guard_path):
        return _read_lease(lease_path, fingerprint=fingerprint)


__all__ = [
    "ACTIVE_RUN_STATES",
    "ActiveLeaseError",
    "ERROR_CLASSES",
    "LeaseError",
    "LeaseRecoveryBlockedError",
    "RecoveryError",
    "SCHEMA_PATH",
    "acquire_recovery_lease",
    "alert_due",
    "build_incident",
    "current_process_identity",
    "fingerprint_basis",
    "heartbeat_recovery_lease",
    "lease_fencing_token",
    "load_recovery_policy",
    "next_source_fallback",
    "mark_alert_sent",
    "read_recovery_lease",
    "record_retry_attempt",
    "request_recovery_lease_preemption",
    "recovery_decision",
    "release_recovery_lease",
    "resolve_incident",
    "sanitize_diagnostics",
    "sanitize_text",
    "stable_fingerprint",
    "validate_dispatch_inputs",
    "validate_incident",
    "validate_recovery_policy",
]
