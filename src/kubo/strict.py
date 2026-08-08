from __future__ import annotations

import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "apikey",
        "api_key",
        "auth",
        "authorization",
        "awsaccesskeyid",
        "bearer",
        "client_secret",
        "code",
        "cookie",
        "googleaccessid",
        "jwt",
        "oauth_token",
        "password",
        "passwd",
        "session",
        "sessionid",
        "sig",
        "signature",
        "token",
    }
)
_SENSITIVE_QUERY_KEYS_COLLAPSED = frozenset(key.replace("_", "") for key in _SENSITIVE_QUERY_KEYS)


def sensitive_query_key(value: Any) -> bool:
    """Return whether a query key can carry a credential or signed-URL proof."""

    normalized = str(value).strip().casefold().replace("-", "_")
    collapsed = normalized.replace("_", "")
    return (
        normalized in _SENSITIVE_QUERY_KEYS
        or collapsed in _SENSITIVE_QUERY_KEYS_COLLAPSED
        or collapsed.startswith(("xamz", "xgoog"))
        or normalized.startswith(("x_amz_", "x_goog_"))
        or normalized.endswith(("_token", "_secret", "_credential", "_signature"))
        or any(marker in normalized for marker in ("access_token", "client_secret"))
    )


def parse_aware(value: Any, field: str) -> datetime:
    if value in (None, ""):
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def parse_iso_date(value: Any, field: str) -> date:
    if value in (None, ""):
        raise ValueError(f"{field} is required")
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date: {value}") from exc


def strict_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be a JSON boolean")
    return value


def finite_number(value: Any, field: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError(f"{field} must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{field} must be <= {maximum}")
    return parsed


def require_sha256(value: Any, field: str) -> str:
    digest = str(value or "").lower()
    if not SHA256_RE.fullmatch(digest):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return digest


def safe_relative_path(value: Any, field: str = "path") -> Path:
    path = Path(str(value or ""))
    if not str(path) or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must remain inside the pack")
    return path


def resolved_regular_file(root: Path, relative: Path, field: str = "path") -> Path:
    """Resolve a required regular file without following any symlink component."""

    root = root.resolve()
    candidate = root
    for component in relative.parts:
        candidate = candidate / component
        if candidate.is_symlink():
            raise ValueError(f"{field} must not contain symlinks")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{field} is missing") from exc
    if root not in resolved.parents or not resolved.is_file():
        raise ValueError(f"{field} must resolve to a regular file inside the pack")
    return resolved


def https_url(value: Any, field: str) -> str:
    url = str(value or "")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field} has an invalid host or port") from exc
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field} must not contain userinfo credentials")
    if parsed.fragment:
        raise ValueError(f"{field} must not contain a fragment")
    if port not in (None, 443):
        raise ValueError(f"{field} must use the standard HTTPS port")
    if any(sensitive_query_key(key) for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError(f"{field} must not contain credential or signed-URL query parameters")
    return url


def domain_matches(url: str, allowed_urls: tuple[str, ...]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    for base in allowed_urls:
        allowed = (urlsplit(base).hostname or "").lower()
        if host == allowed or (allowed and host.endswith("." + allowed)):
            return True
    return False


def contains_placeholder(value: Any) -> bool:
    text = str(value)
    return "{{" in text or "${" in text or "<%" in text


__all__ = [
    "contains_placeholder",
    "domain_matches",
    "finite_number",
    "https_url",
    "parse_aware",
    "parse_iso_date",
    "require_sha256",
    "resolved_regular_file",
    "safe_relative_path",
    "sensitive_query_key",
    "strict_bool",
]
