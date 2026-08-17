from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

PRODUCT_ID = "HUMANSOFT_DISCLOSURE_REACTION_V1"
PRE_SESSIONS = 20
POST_SESSIONS = 20
IMMEDIATE_POST_SESSIONS = 2

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "code",
    "cookie",
    "jwt",
    "oauth_token",
    "password",
    "session",
    "sig",
    "signature",
    "token",
}

_PACKET_FIELDS = {
    "schema_version",
    "packet_id",
    "product_id",
    "timezone",
    "created_at",
    "disclosure",
    "policy",
    "pre_sessions",
    "post_sessions",
    "public_opinion",
    "evidence_receipts",
}
_POLICY_FIELDS = {
    "pre_sessions",
    "post_sessions",
    "immediate_post_sessions",
    "movement_threshold_pct",
    "price_basis",
    "benchmark_rule",
    "corporate_action_rule",
    "public_opinion_rule",
    "numeric_output_rule",
    "causality_rule",
}
_DISCLOSURE_FIELDS = {
    "disclosure_id",
    "security_code",
    "canonical_cluster_id",
    "disclosure_type",
    "headline",
    "published_at",
    "available_at",
    "official_source_url",
    "official_evidence_sha256",
    "duplicate_of",
}
_SESSION_FIELDS = {
    "trade_date",
    "session_close_at",
    "observed_at",
    "stock_total_return_index",
    "market_total_return_index",
    "sector_total_return_index",
    "calendar_evidence_sha256",
    "price_evidence_sha256",
    "market_benchmark_evidence_sha256",
    "sector_benchmark_evidence_sha256",
    "corporate_action_evidence_sha256",
}
_OPINION_FIELDS = {
    "opinion_id",
    "published_at",
    "source_kind",
    "source_group",
    "source_url",
    "stance",
    "relevance",
    "evidence_sha256",
}
_RECEIPT_FIELDS = {
    "official_disclosure_sha256",
    "trading_calendar_sha256",
    "price_history_sha256",
    "market_benchmark_sha256",
    "sector_benchmark_sha256",
    "corporate_actions_sha256",
    "public_opinion_archive_sha256",
}

_SOURCE_KINDS = {
    "NEWSPAPER",
    "FINANCIAL_MEDIA",
    "SOCIAL_MEDIA",
    "ANALYST_COMMENTARY",
    "FORUM",
}
_STANCES = {"POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"}
_RELEVANCE = {
    "DIRECT_DISCLOSURE_REACTION",
    "COMPANY_CONTEXT",
    "RUMOR_OR_SPECULATION",
}


class DisclosureReactionError(ValueError):
    """The qualitative disclosure-reaction contract was violated."""


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DisclosureReactionError(f"{field} must be an object")
    return value


def _fields(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "-"
        unknown = ",".join(sorted(actual - expected)) or "-"
        raise DisclosureReactionError(
            f"{field} fields mismatch; missing={missing}; unknown={unknown}"
        )


def _text(value: Any, field: str, maximum: int = 512) -> str:
    text = str(value or "").strip()
    if not text:
        raise DisclosureReactionError(f"{field} is required")
    if len(text) > maximum:
        raise DisclosureReactionError(f"{field} exceeds {maximum} characters")
    return text


def _aware(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, field).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DisclosureReactionError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DisclosureReactionError(f"{field} must be timezone-aware")
    return parsed


def _number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or value in (None, ""):
        raise DisclosureReactionError(f"{field} must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise DisclosureReactionError(f"{field} must be a finite number") from exc
    if not math.isfinite(parsed):
        raise DisclosureReactionError(f"{field} must be finite")
    if minimum is not None and parsed < minimum:
        raise DisclosureReactionError(f"{field} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise DisclosureReactionError(f"{field} must be <= {maximum}")
    return parsed


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DisclosureReactionError(f"{field} must be a positive integer")
    return value


def _sha(value: Any, field: str) -> str:
    digest = str(value or "").strip().lower()
    if not _SHA_RE.fullmatch(digest):
        raise DisclosureReactionError(f"{field} must be a lowercase SHA-256")
    return digest


def _url(value: Any, field: str) -> str:
    text = _text(value, field, 2048)
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as exc:
        raise DisclosureReactionError(f"{field} has an invalid host or port") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or port not in (None, 443)
    ):
        raise DisclosureReactionError(
            f"{field} must be an absolute credential-free HTTPS URL"
        )
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        normalized = key.strip().casefold().replace("-", "_")
        collapsed = normalized.replace("_", "")
        if (
            normalized in _SENSITIVE_QUERY_KEYS
            or collapsed in {item.replace("_", "") for item in _SENSITIVE_QUERY_KEYS}
            or normalized.endswith(("_token", "_secret", "_signature"))
        ):
            raise DisclosureReactionError(
                f"{field} must not contain credential or signed-URL parameters"
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


