from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import urlsplit

PRODUCT_ID = "HUMANSOFT_EVENT_FACTOR_PANEL_V1"
PRE_EVENT_SESSIONS = 20
POST_EVENT_SESSIONS = 20
MATERIAL_RETURN_THRESHOLD_PCT = 4.0

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_FACTOR_TOKENS = (
    "future",
    "forward_return",
    "post_event",
    "outcome",
    "target",
    "label",
    "return_after",
)

_PACKET_FIELDS = {
    "schema_version",
    "packet_id",
    "product_id",
    "timezone",
    "created_at",
    "evidence_classification",
    "rights_status",
    "policy",
    "event",
    "factor_snapshot",
    "pre_sessions",
    "post_sessions",
    "evidence_receipts",
    "independent_authority_receipt",
}
_POLICY_FIELDS = {
    "pre_event_sessions",
    "post_event_sessions",
    "entry_rule",
    "price_basis",
    "benchmark_rule",
    "corporate_action_rule",
    "material_return_threshold_pct",
    "event_cluster_rule",
    "feature_cutoff_rule",
    "overlap_rule",
}
_EVENT_FIELDS = {
    "event_id",
    "security_code",
    "canonical_cluster_id",
    "event_type",
    "published_at",
    "available_at",
    "source_url",
    "evidence_sha256",
    "duplicate_of",
}
_SNAPSHOT_FIELDS = {"snapshot_id", "snapshot_at", "evidence_sha256", "factors"}
_FACTOR_FIELDS = {"factor_id", "state", "value", "available_at", "evidence_sha256"}
_SESSION_FIELDS = {
    "trade_date",
    "session_close_at",
    "observed_at",
    "stock_total_return_index",
    "market_total_return_index",
    "sector_total_return_index",
    "volume",
    "calendar_evidence_sha256",
    "price_evidence_sha256",
    "market_benchmark_evidence_sha256",
    "sector_benchmark_evidence_sha256",
    "corporate_action_evidence_sha256",
}
_RECEIPT_FIELDS = {
    "event_ledger_sha256",
    "factor_snapshot_sha256",
    "trading_calendar_sha256",
    "price_history_sha256",
    "market_benchmark_sha256",
    "sector_benchmark_sha256",
    "corporate_actions_sha256",
}
_RETRO_FIELDS = {
    "decision_id",
    "decision_at",
    "model_horizon_sessions",
    "audited_horizon_sessions",
    "score",
    "action",
    "relative_return_pct",
}


class EventFactorPanelError(ValueError):
    """A frozen event-factor contract was violated."""


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EventFactorPanelError(f"{field} must be an object")
    return value


def _fields(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "-"
        unknown = ",".join(sorted(actual - expected)) or "-"
        raise EventFactorPanelError(
            f"{field} fields mismatch; missing={missing}; unknown={unknown}"
        )


def _text(value: Any, field: str, maximum: int = 256) -> str:
    text = str(value or "").strip()
    if not text:
        raise EventFactorPanelError(f"{field} is required")
    if len(text) > maximum:
        raise EventFactorPanelError(f"{field} exceeds {maximum} characters")
    return text


def _aware(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, field).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventFactorPanelError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventFactorPanelError(f"{field} must be timezone-aware")
    return parsed


def _number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or value in (None, ""):
        raise EventFactorPanelError(f"{field} must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise EventFactorPanelError(f"{field} must be a finite number") from exc
    if not math.isfinite(parsed):
        raise EventFactorPanelError(f"{field} must be finite")
    if minimum is not None and parsed < minimum:
        raise EventFactorPanelError(f"{field} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise EventFactorPanelError(f"{field} must be <= {maximum}")
    return parsed


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EventFactorPanelError(f"{field} must be a positive integer")
    return value


def _sha(value: Any, field: str) -> str:
    digest = str(value or "").strip().lower()
    if not _SHA_RE.fullmatch(digest):
        raise EventFactorPanelError(f"{field} must be a lowercase SHA-256")
    return digest


def _url(value: Any, field: str) -> str:
    text = _text(value, field, 2048)
    parsed = urlsplit(text)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise EventFactorPanelError(
            f"{field} must be an absolute credential-free HTTPS URL"
        )
    return text


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

