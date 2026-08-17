from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

PRODUCT_ID = "HUMANSOFT_DISCLOSURE_REACTION_V2"
PRE_SESSIONS = 20
POST_SESSIONS = 20
IMMEDIATE_POST_SESSIONS = 2

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_QUERY_KEYS = {
    "access_token", "api_key", "apikey", "authorization", "bearer",
    "client_secret", "code", "cookie", "jwt", "oauth_token", "password",
    "session", "sig", "signature", "token",
}


class DisclosureReactionError(ValueError):
    """A strict disclosure-reaction or data-domain contract was violated."""


def mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DisclosureReactionError(f"{field} must be an object")
    return value


def exact_fields(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "-"
        unknown = ",".join(sorted(actual - expected)) or "-"
        raise DisclosureReactionError(
            f"{field} fields mismatch; missing={missing}; unknown={unknown}"
        )


def text(value: Any, field: str, maximum: int = 512) -> str:
    result = str(value or "").strip()
    if not result:
        raise DisclosureReactionError(f"{field} is required")
    if len(result) > maximum:
        raise DisclosureReactionError(f"{field} exceeds {maximum} characters")
    return result


def aware(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(text(value, field).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DisclosureReactionError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DisclosureReactionError(f"{field} must be timezone-aware")
    return parsed


def day(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(text(value, field, 10))
    except ValueError as exc:
        raise DisclosureReactionError(f"{field} must be YYYY-MM-DD") from exc


def number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or value in (None, ""):
        raise DisclosureReactionError(f"{field} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DisclosureReactionError(f"{field} must be a finite number") from exc
    if not math.isfinite(result):
        raise DisclosureReactionError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise DisclosureReactionError(f"{field} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise DisclosureReactionError(f"{field} must be <= {maximum}")
    return result


def positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DisclosureReactionError(f"{field} must be a positive integer")
    return value


def sha256(value: Any, field: str) -> str:
    result = str(value or "").strip().lower()
    if not _SHA_RE.fullmatch(result):
        raise DisclosureReactionError(f"{field} must be a lowercase SHA-256")
    return result


def safe_https_url(value: Any, field: str) -> str:
    result = text(value, field, 2048)
    try:
        parsed = urlsplit(result)
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
    collapsed = {key.replace("-", "_").casefold().replace("_", "") for key in _SENSITIVE_QUERY_KEYS}
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        normalized = key.replace("-", "_").casefold()
        if (
            normalized in _SENSITIVE_QUERY_KEYS
            or normalized.replace("_", "") in collapsed
            or normalized.endswith(("_token", "_secret", "_signature"))
        ):
            raise DisclosureReactionError(
                f"{field} must not contain credential or signed-URL parameters"
            )
    return result


def digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
