from __future__ import annotations

from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import http.client
import ipaddress
import math
import mimetypes
import os
import re
import secrets
import socket
import ssl
import stat
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol
from urllib import error, request, robotparser
from urllib.parse import parse_qsl, urljoin, urlparse, urlsplit, urlunsplit

from . import __version__
from .foundation_io import require_real_directory
from .hashing import canonical_json_bytes, sha256_bytes
from .strict import sensitive_query_key


DEFAULT_USER_AGENT = f"KU-BOResearchBot/{__version__} (public research capture; no authentication)"
MAX_CAPTURE_BYTES = 50 * 1024 * 1024
MAX_ROBOTS_BYTES = 256 * 1024
MAX_ROBOTS_REDIRECTS = 5
MAX_ROBOTS_CACHE_HOURS = 24
CAPTURE_KINDS = frozenset(
    {"RAW_PAGE", "RAW_DOWNLOAD", "USER_EXPORT", "ACCESS_RECEIPT", "ARCHIVE_CAPTURE"}
)
ACCESS_MODES = frozenset(
    {
        "PUBLIC_PAGE",
        "PUBLIC_DOWNLOAD",
        "USER_EXPORT",
        "AUTHORIZED_BROWSER",
        "AUTHORIZED_ACCOUNT",
    }
)
CAPTURE_STATES = frozenset(
    {"AVAILABLE", "PARTIAL", "BLOCKED", "ERROR", "AUTH_REQUIRED", "UNTESTED"}
)
QUERY_STATUSES = frozenset(
    {
        "QUALIFIED",
        "ZERO_RESULT",
        "BLOCKED",
        "ERROR",
        "AUTH_REQUIRED",
        "PARSER_DRIFT",
        "DATA_QUALITY_REJECTED",
    }
)

_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_CAPTCHA_MARKERS = (
    'class="g-recaptcha"',
    "class='g-recaptcha'",
    "hcaptcha",
    "cf-chl-",
    "challenge-platform",
    "verify you are human",
    "/recaptcha/",
)
_PAYWALL_MARKERS = (
    'id="paywall"',
    "id='paywall'",
    'class="paywall"',
    "class='paywall'",
    "subscribe to continue",
    "subscription required",
    "purchase a subscription",
)
_AUTH_MARKERS = (
    'type="password"',
    "type='password'",
    "authentication required",
    "login required",
    "sign in required",
    "<title>sign in",
    "<title>login",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _normalize_domain(value: str) -> str:
    candidate = str(value).strip().rstrip(".").lower()
    if not candidate or "://" in candidate or "/" in candidate or "@" in candidate or "*" in candidate:
        raise ValueError("allowlisted domains must be host names without schemes, ports, or wildcards")
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("allowlisted domain is not valid IDNA") from exc
    labels = candidate.split(".")
    if len(candidate) > 253 or any(not _DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        raise ValueError("allowlisted domain is invalid")
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        raise ValueError("IP literals are not public-domain allowlist entries")
    if candidate == "localhost" or candidate.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local or internal domains are forbidden")
    return candidate


def _host_allowed(host: str, allowed_domains: tuple[str, ...]) -> bool:
    normalized = host.rstrip(".").lower()
    return any(normalized == allowed or normalized.endswith("." + allowed) for allowed in allowed_domains)


def _validate_public_url(value: str, allowed_domains: tuple[str, ...]) -> str:
    url = str(value)
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("source_url has an invalid port or host") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("source_url must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source_url must not contain credentials")
    if parsed.fragment:
        raise ValueError("source_url must not contain a fragment")
    if port not in (None, 443):
        raise ValueError("source_url must use the standard HTTPS port")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if not _host_allowed(host, allowed_domains):
        raise ValueError("source_url is outside the domain allowlist")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if sensitive_query_key(key):
            raise ValueError("credential-bearing query parameters are forbidden")
    return url


def _validate_user_agent(value: str) -> str:
    user_agent = str(value).strip()
    if not user_agent or len(user_agent) > 256 or "\r" in user_agent or "\n" in user_agent:
        raise ValueError("user_agent must be a single non-empty header value")
    return user_agent


def _provenance_url(value: str) -> str:
    """Preserve origin/path while replacing all query values with one safe digest."""

    parsed = urlsplit(value)
    if not parsed.query:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    digest = sha256_bytes(parsed.query.encode("utf-8"))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, f"__kubo_query_sha256={digest}", "")
    )


def _sanitized_trace_url(value: str, *, fallback: str) -> str:
    """Keep redirect provenance while removing credentials and raw query values."""

    try:
        parsed = urlsplit(str(value))
        port = parsed.port
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        return _provenance_url(fallback)
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        return _provenance_url(fallback)
    netloc = host if port in (None, 443) else f"{host}:{port}"
    clean = urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
    return _provenance_url(clean)


def _retry_after_seconds(headers, attempted_at: datetime) -> float | None:
    """Parse Retry-After without shortening the server's requested delay.

    The orchestrator owns the wall-time budget decision.  The connector must
    preserve a valid server delay so the caller can defer instead of retrying
    early.  Invalid negative or non-finite values are treated as absent.
    """

    raw = str(headers.get("Retry-After", "")).strip() if headers is not None else ""
    if not raw:
        return None
    try:
        integer_seconds = int(raw)
        if integer_seconds < 0:
            return None
        seconds = float(integer_seconds)
    except (ValueError, OverflowError):
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = max(0.0, (retry_at - attempted_at).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


@dataclass(frozen=True)
class CaptureRequest:
    """A bounded request to capture public bytes without qualifying market evidence."""

    source_id: str
    source_url: str
    allowed_domains: tuple[str, ...]
    roles_observed: tuple[str, ...]
    access_mode: str = "PUBLIC_PAGE"
    capture_kind: str = "RAW_PAGE"
    resource_path: str | None = None
    timeout_seconds: float = 15.0
    max_bytes: int = 5 * 1024 * 1024
    user_agent: str = DEFAULT_USER_AGENT

    def __post_init__(self) -> None:
        source_id = str(self.source_id).strip()
        if not _SOURCE_ID_RE.fullmatch(source_id):
            raise ValueError("source_id contains unsupported characters")
        domains = tuple(sorted({_normalize_domain(item) for item in self.allowed_domains}))
        if not domains:
            raise ValueError("allowed_domains must be non-empty")
        roles = tuple(sorted({str(item).strip() for item in self.roles_observed if str(item).strip()}))
        if not roles:
            raise ValueError("roles_observed must be non-empty")
        access_mode = str(self.access_mode)
        capture_kind = str(self.capture_kind)
        if access_mode not in ACCESS_MODES:
            raise ValueError("unsupported access_mode")
        if capture_kind not in CAPTURE_KINDS or capture_kind == "ACCESS_RECEIPT":
            raise ValueError("CaptureRequest must request a raw evidence kind, not ACCESS_RECEIPT")
        if isinstance(self.max_bytes, bool) or not isinstance(self.max_bytes, int):
            raise ValueError("max_bytes must be an integer")
        if self.max_bytes <= 0 or self.max_bytes > MAX_CAPTURE_BYTES:
            raise ValueError(f"max_bytes must be between 1 and {MAX_CAPTURE_BYTES}")
        timeout = float(self.timeout_seconds)
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 60:
            raise ValueError("timeout_seconds must be finite and between 0 and 60")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "allowed_domains", domains)
        object.__setattr__(self, "roles_observed", roles)
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "source_url", _validate_public_url(self.source_url, domains))
        object.__setattr__(self, "user_agent", _validate_user_agent(self.user_agent))


@dataclass(frozen=True)
class RobotsAccessGrant:
    """Trusted registry grant required before treating a 404/410 as no policy.

    The grant is deliberately supplied to ``PublicHttpConnector`` rather than
    accepted from ``CaptureRequest``.  Production callers therefore fail
    closed unless a separately reviewed registry has established all three
    gates for the exact source.
    """

    source_id: str
    registry_id: str
    registry_sha256: str
    rights_status: str
    terms_status: str
    public_access_status: str
    reviewed_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not _SOURCE_ID_RE.fullmatch(str(self.source_id)):
            raise ValueError("robots access grant source_id is invalid")
        if not _SOURCE_ID_RE.fullmatch(str(self.registry_id)):
            raise ValueError("robots access grant registry_id is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(self.registry_sha256)):
            raise ValueError("robots access grant registry_sha256 is invalid")
        if self.rights_status != "PERMITTED":
            raise ValueError("robots access grant requires PERMITTED rights")
        if self.terms_status != "REVIEWED_PERMITTED":
            raise ValueError("robots access grant requires reviewed permitted terms")
        if self.public_access_status != "CONFIRMED_PUBLIC":
            raise ValueError("robots access grant requires confirmed public access")
        reviewed = _aware(self.reviewed_at, "robots grant reviewed_at")
        expires = _aware(self.expires_at, "robots grant expires_at")
        if expires <= reviewed:
            raise ValueError("robots access grant must expire after review")

    def permits(self, source_id: str, at: datetime) -> bool:
        moment = _aware(at, "robots grant evaluation time")
        return self.source_id == source_id and self.reviewed_at <= moment < self.expires_at


@dataclass(frozen=True)
class RobotsPolicyReceipt:
    """Sanitized, hash-addressed evidence of one robots policy decision."""

    source_id: str
    origin: str
    robots_url: str
    final_url: str
    http_status: int | None
    redirect_chain: tuple[str, ...]
    fetched_at: datetime
    evaluated_at: datetime
    cache_expires_at: datetime
    cache_hit: bool
    decision: str
    access_gates: tuple[str, ...]
    access_registry_id: str | None = None
    access_registry_sha256: str | None = None
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if not _SOURCE_ID_RE.fullmatch(str(self.source_id)):
            raise ValueError("robots receipt source_id is invalid")
        for value, field_name in (
            (self.origin, "origin"),
            (self.robots_url, "robots_url"),
            (self.final_url, "final_url"),
        ):
            parsed = urlsplit(str(value))
            allowed_schemes = (
                {"https", "http"}
                if field_name == "final_url" and self.decision == "ROBOTS_REDIRECT_BLOCKED"
                else {"https"}
            )
            if (
                parsed.scheme not in allowed_schemes
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError(f"robots receipt {field_name} must be sanitized HTTPS")
        if self.http_status is not None and (
            type(self.http_status) is not int or not 100 <= self.http_status <= 599
        ):
            raise ValueError("robots receipt http_status is invalid")
        if (
            not self.redirect_chain
            or len(self.redirect_chain) > MAX_ROBOTS_REDIRECTS + 2
            or self.redirect_chain[0] != self.robots_url
            or self.redirect_chain[-1] != self.final_url
        ):
            raise ValueError("robots receipt redirect chain is invalid")
        for index, value in enumerate(self.redirect_chain):
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or (
                    parsed.scheme == "http"
                    and self.decision != "ROBOTS_REDIRECT_BLOCKED"
                )
            ):
                raise ValueError(f"robots receipt redirect_chain[{index}] is unsafe")
            if parsed.query and not re.fullmatch(
                r"__kubo_query_sha256=[0-9a-f]{64}", parsed.query
            ):
                raise ValueError("robots receipt contains an unhashed query")
        if (
            len(self.redirect_chain) != len(set(self.redirect_chain))
            and self.decision != "ROBOTS_REDIRECT_BLOCKED"
        ):
            raise ValueError("robots receipt redirect chain contains a loop")
        fetched = _aware(self.fetched_at, "robots receipt fetched_at")
        evaluated = _aware(self.evaluated_at, "robots receipt evaluated_at")
        expires = _aware(self.cache_expires_at, "robots receipt cache_expires_at")
        if evaluated < fetched or expires < fetched:
            raise ValueError("robots receipt timestamps are inconsistent")
        if expires > fetched + timedelta(hours=MAX_ROBOTS_CACHE_HOURS):
            raise ValueError("robots receipt cache exceeds the maximum policy")
        if type(self.cache_hit) is not bool:
            raise ValueError("robots receipt cache_hit must be boolean")
        if self.cache_hit and evaluated >= expires:
            raise ValueError("robots receipt cannot use an expired cache entry")
        if not _CODE_RE.fullmatch(str(self.decision)):
            raise ValueError("robots receipt decision is invalid")
        if len(self.access_gates) != len(set(self.access_gates)):
            raise ValueError("robots receipt access gates must be unique")
        if (self.access_registry_id is None) != (self.access_registry_sha256 is None):
            raise ValueError("robots receipt access registry identity is incomplete")
        if self.access_registry_id is not None:
            if not _SOURCE_ID_RE.fullmatch(self.access_registry_id):
                raise ValueError("robots receipt access_registry_id is invalid")
            if not re.fullmatch(r"[0-9a-f]{64}", str(self.access_registry_sha256)):
                raise ValueError("robots receipt access_registry_sha256 is invalid")
        if self.retry_after_seconds is not None and (
            isinstance(self.retry_after_seconds, bool)
            or not isinstance(self.retry_after_seconds, (int, float))
            or not math.isfinite(float(self.retry_after_seconds))
            or float(self.retry_after_seconds) < 0
        ):
            raise ValueError("robots receipt retry_after_seconds is invalid")
        if self.retry_after_seconds is not None and self.decision != "RETRYABLE_RATE_LIMIT":
            raise ValueError("robots receipt retry delay requires RETRYABLE_RATE_LIMIT")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "source_id": self.source_id,
            "origin": self.origin,
            "robots_url": self.robots_url,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "redirect_chain": list(self.redirect_chain),
            "fetched_at": self.fetched_at.astimezone(timezone.utc).isoformat(),
            "evaluated_at": self.evaluated_at.astimezone(timezone.utc).isoformat(),
            "cache_expires_at": self.cache_expires_at.astimezone(timezone.utc).isoformat(),
            "cache_hit": self.cache_hit,
            "decision": self.decision,
            "access_gates": list(self.access_gates),
            "access_registry_id": self.access_registry_id,
            "access_registry_sha256": self.access_registry_sha256,
            "retry_after_seconds": self.retry_after_seconds,
            "access_receipt_proves_collection": False,
        }
        payload["receipt_sha256"] = sha256_bytes(canonical_json_bytes(payload))
        return payload


@dataclass(frozen=True)
class CaptureResult:
    """The outcome of one capture attempt; operational failures are data, not exceptions."""

    source_id: str
    source_url: str
    final_url: str
    access_mode: str
    capture_kind: str
    roles_observed: tuple[str, ...]
    attempted_at: datetime
    observed_at: datetime | None
    state: str
    query_status: str
    qualified_items: int
    zero_result: bool
    content: bytes | None = field(repr=False)
    content_type: str
    http_status: int | None
    error_code: str
    data_quality_flags: tuple[str, ...]
    limitations: tuple[str, ...]
    retry_after_seconds: float | None = None
    material_query_route_proof_sha256: str | None = None
    robots_policy_receipt: RobotsPolicyReceipt | None = None

    def __post_init__(self) -> None:
        if not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise ValueError("invalid result source_id")
        _aware(self.attempted_at, "attempted_at")
        if self.observed_at is not None:
            _aware(self.observed_at, "observed_at")
            if self.observed_at < self.attempted_at:
                raise ValueError("observed_at cannot precede attempted_at")
        if self.state not in CAPTURE_STATES or self.query_status not in QUERY_STATUSES:
            raise ValueError("invalid capture state or query status")
        if self.access_mode not in ACCESS_MODES or self.capture_kind not in CAPTURE_KINDS:
            raise ValueError("invalid result access mode or capture kind")
        if not self.roles_observed:
            raise ValueError("result roles_observed must be non-empty")
        if self.qualified_items < 0:
            raise ValueError("qualified_items must be non-negative")
        if self.query_status == "QUALIFIED" and self.qualified_items <= 0:
            raise ValueError("QUALIFIED requires at least one item")
        if self.query_status == "ZERO_RESULT" and (self.qualified_items != 0 or not self.zero_result):
            raise ValueError("ZERO_RESULT must be explicit and empty")
        if self.query_status != "ZERO_RESULT" and self.zero_result:
            raise ValueError("zero_result is valid only with ZERO_RESULT")
        if self.content is not None and not isinstance(self.content, bytes):
            raise TypeError("captured content must be bytes")
        if (self.content is None) != (self.observed_at is None):
            raise ValueError("content and observed_at must either both exist or both be absent")
        if self.error_code and not _CODE_RE.fullmatch(self.error_code):
            raise ValueError("error_code must be a stable uppercase code")
        retry_after = self.retry_after_seconds
        if retry_after is not None:
            if (
                isinstance(retry_after, bool)
                or not isinstance(retry_after, (int, float))
                or not math.isfinite(float(retry_after))
                or float(retry_after) < 0
            ):
                raise ValueError("retry_after_seconds must be a non-negative finite number")
            if self.error_code != "HTTP_RATE_LIMITED":
                raise ValueError("retry_after_seconds is valid only for HTTP_RATE_LIMITED")
            object.__setattr__(self, "retry_after_seconds", float(retry_after))
        route_proof = self.material_query_route_proof_sha256
        if route_proof is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", str(route_proof)):
                raise ValueError("material_query_route_proof_sha256 must be a lowercase SHA-256")
            if self.query_status != "ZERO_RESULT":
                raise ValueError("material query route proof is valid only for ZERO_RESULT")
            if self.content is None or route_proof != sha256_bytes(self.content):
                raise ValueError(
                    "material query route proof must hash the persisted zero-result bytes"
                )
        if self.robots_policy_receipt is not None:
            if not isinstance(self.robots_policy_receipt, RobotsPolicyReceipt):
                raise TypeError("robots_policy_receipt must be a RobotsPolicyReceipt")
            if self.robots_policy_receipt.source_id != self.source_id:
                raise ValueError("robots receipt source_id differs from capture result")

    @property
    def captured(self) -> bool:
        return self.content is not None

    @property
    def degraded(self) -> bool:
        return self.state != "AVAILABLE" or self.content is None


def _failure(
    capture_request: CaptureRequest,
    attempted_at: datetime,
    *,
    state: str,
    query_status: str,
    error_code: str,
    http_status: int | None = None,
    flags: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    final_url: str | None = None,
    retry_after_seconds: float | None = None,
) -> CaptureResult:
    return CaptureResult(
        source_id=capture_request.source_id,
        source_url=_provenance_url(capture_request.source_url),
        final_url=_provenance_url(final_url or capture_request.source_url),
        access_mode=capture_request.access_mode,
        capture_kind=capture_request.capture_kind,
        roles_observed=capture_request.roles_observed,
        attempted_at=attempted_at,
        observed_at=None,
        state=state,
        query_status=query_status,
        qualified_items=0,
        zero_result=False,
        content=None,
        content_type="",
        http_status=http_status,
        error_code=error_code,
        data_quality_flags=tuple(sorted(set(flags))),
        limitations=tuple(sorted(set(limitations))),
        retry_after_seconds=retry_after_seconds,
    )


def _raw_capture(
    capture_request: CaptureRequest,
    attempted_at: datetime,
    observed_at: datetime,
    content: bytes,
    *,
    content_type: str,
    final_url: str,
    http_status: int | None,
) -> CaptureResult:
    flags = ["RAW_CAPTURE_PENDING_PARSER_VALIDATION"]
    state = "AVAILABLE"
    if not content:
        flags.append("EMPTY_RESPONSE_BODY")
        state = "PARTIAL"
    return CaptureResult(
        source_id=capture_request.source_id,
        source_url=_provenance_url(capture_request.source_url),
        final_url=_provenance_url(final_url),
        access_mode=capture_request.access_mode,
        capture_kind=capture_request.capture_kind,
        roles_observed=capture_request.roles_observed,
        attempted_at=attempted_at,
        observed_at=observed_at,
        state=state,
        query_status="DATA_QUALITY_REJECTED",
        qualified_items=0,
        zero_result=False,
        content=content,
        content_type=content_type,
        http_status=http_status,
        error_code="",
        data_quality_flags=tuple(flags),
        limitations=("CAPTURE_ONLY_REQUIRES_PARSER_VALIDATION",),
    )


class CaptureConnector(Protocol):
    def capture(self, capture_request: CaptureRequest) -> CaptureResult: ...


class FixtureFileConnector:
    """Read bounded fixture or user-export bytes from one explicitly scoped directory."""

    def __init__(self, root: Path, *, clock: Callable[[], datetime] = _utc_now):
        resolved = Path(root).resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("fixture root must be a directory")
        self.root = resolved
        self._clock = clock

    def capture(self, capture_request: CaptureRequest) -> CaptureResult:
        attempted_at = _aware(self._clock(), "clock")
        if capture_request.resource_path in (None, ""):
            return _failure(
                capture_request,
                attempted_at,
                state="ERROR",
                query_status="ERROR",
                error_code="LOCAL_RESOURCE_REQUIRED",
            )
        relative = Path(str(capture_request.resource_path))
        if relative.is_absolute() or ".." in relative.parts:
            return _failure(
                capture_request,
                attempted_at,
                state="BLOCKED",
                query_status="BLOCKED",
                error_code="LOCAL_PATH_OUTSIDE_FIXTURE_ROOT",
            )
        try:
            candidate = (self.root / relative).resolve(strict=True)
            if candidate == self.root or self.root not in candidate.parents or not candidate.is_file():
                return _failure(
                    capture_request,
                    attempted_at,
                    state="BLOCKED",
                    query_status="BLOCKED",
                    error_code="LOCAL_PATH_OUTSIDE_FIXTURE_ROOT",
                )
            if candidate.stat().st_size > capture_request.max_bytes:
                return _failure(
                    capture_request,
                    attempted_at,
                    state="PARTIAL",
                    query_status="DATA_QUALITY_REJECTED",
                    error_code="MAX_BYTES_EXCEEDED",
                    flags=("MAX_BYTES_EXCEEDED",),
                )
            with candidate.open("rb") as handle:
                content = handle.read(capture_request.max_bytes + 1)
            if len(content) > capture_request.max_bytes:
                return _failure(
                    capture_request,
                    attempted_at,
                    state="PARTIAL",
                    query_status="DATA_QUALITY_REJECTED",
                    error_code="MAX_BYTES_EXCEEDED",
                    flags=("MAX_BYTES_EXCEEDED",),
                )
        except FileNotFoundError:
            return _failure(
                capture_request,
                attempted_at,
                state="ERROR",
                query_status="ERROR",
                error_code="LOCAL_RESOURCE_NOT_FOUND",
            )
        except PermissionError:
            return _failure(
                capture_request,
                attempted_at,
                state="BLOCKED",
                query_status="BLOCKED",
                error_code="LOCAL_RESOURCE_PERMISSION_DENIED",
            )
        except OSError:
            return _failure(
                capture_request,
                attempted_at,
                state="ERROR",
                query_status="ERROR",
                error_code="LOCAL_RESOURCE_IO_ERROR",
            )
        observed_at = _aware(self._clock(), "clock")
        guessed_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        return _raw_capture(
            capture_request,
            attempted_at,
            observed_at,
            content,
            content_type=guessed_type,
            final_url=capture_request.source_url,
            http_status=None,
        )


FileConnector = FixtureFileConnector
FixtureConnector = FixtureFileConnector


class _UnsafeRedirectError(RuntimeError):
    pass


class _RedirectPolicyError(_UnsafeRedirectError):
    def __init__(self, reason: str, chain: tuple[str, ...]):
        super().__init__(reason)
        self.reason = reason
        self.chain = chain


class _UnsafeNetworkTargetError(RuntimeError):
    pass


class _DnsResolutionError(RuntimeError):
    pass


def _resolve_public_addresses(
    host: str,
    port: int = 443,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> tuple[str, ...]:
    """Resolve once and reject every non-public result before a pinned connect."""

    try:
        rows = resolver(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (OSError, socket.gaierror) as exc:
        raise _DnsResolutionError("DNS resolution failed") from exc
    addresses: set[str] = set()
    for row in rows:
        try:
            address = str(row[4][0])
            if "%" in address:
                raise ValueError("scoped IPv6 addresses are forbidden")
            parsed = ipaddress.ip_address(address)
        except (IndexError, TypeError, ValueError) as exc:
            raise _UnsafeNetworkTargetError("DNS returned an invalid address") from exc
        if not parsed.is_global:
            raise _UnsafeNetworkTargetError("DNS returned a non-public address")
        addresses.add(parsed.compressed)
    if not addresses:
        raise _UnsafeNetworkTargetError("DNS returned no usable public address")
    return tuple(sorted(addresses))


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Direct HTTPS connection pinned to already-vetted IPs while retaining SNI."""

    def __init__(self, host: str, *, pinned_addresses: tuple[str, ...], **kwargs):
        super().__init__(host, **kwargs)
        self._pinned_addresses = pinned_addresses

    def connect(self) -> None:
        if self._tunnel_host:
            raise _UnsafeNetworkTargetError("HTTP tunneling is disabled for public capture")
        last_error: OSError | None = None
        for address in self._pinned_addresses:
            raw_socket = None
            try:
                raw_socket = self._create_connection(
                    (address, self.port),
                    self.timeout,
                    self.source_address,
                )
                if self._context.check_hostname and not self._context.verify_mode:
                    raise _UnsafeNetworkTargetError("TLS hostname verification is disabled")
                self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
                return
            except OSError as exc:
                last_error = exc
                if raw_socket is not None:
                    raw_socket.close()
        if last_error is not None:
            raise last_error
        raise _UnsafeNetworkTargetError("no pinned public address is available")


class _PinnedHTTPSHandler(request.HTTPSHandler):
    def __init__(
        self,
        allowed_domains: tuple[str, ...],
        *,
        resolver: Callable[..., list[tuple]],
        context: ssl.SSLContext,
    ):
        # ``ssl.create_default_context`` already enables certificate and
        # hostname verification.  Python 3.12 removed the legacy
        # ``check_hostname`` keyword from ``HTTPSConnection``; forwarding it
        # through ``AbstractHTTPHandler.do_open`` fails before any request.
        super().__init__(context=context)
        self.allowed_domains = allowed_domains
        self.resolver = resolver

    def https_open(self, req):  # noqa: ANN001
        validated = _validate_public_url(req.full_url, self.allowed_domains)
        parsed = urlsplit(validated)
        addresses = _resolve_public_addresses(
            parsed.hostname or "",
            parsed.port or 443,
            resolver=self.resolver,
        )

        def connection_factory(host: str, **kwargs):
            return _PinnedHTTPSConnection(host, pinned_addresses=addresses, **kwargs)

        return self.do_open(
            connection_factory,
            req,
            context=self._context,
        )


class _AllowlistRedirectHandler(request.HTTPRedirectHandler):
    max_redirections = MAX_ROBOTS_REDIRECTS
    max_repeats = 1

    def __init__(self, allowed_domains: tuple[str, ...]):
        super().__init__()
        self.allowed_domains = allowed_domains
        self.last_redirect_chain: tuple[str, ...] = ()

    def reset_trace(self, initial_url: str) -> None:
        self.last_redirect_chain = (_provenance_url(initial_url),)

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        target = urljoin(req.full_url, newurl)
        raw_chain = tuple(getattr(req, "_kubo_redirect_chain", (req.full_url,)))
        safe_chain = tuple(_provenance_url(item) for item in raw_chain)
        safe_target = _provenance_url(target)
        if target in raw_chain:
            chain = (*safe_chain, safe_target)
            raise _RedirectPolicyError("REDIRECT_LOOP", chain)
        if len(raw_chain) > MAX_ROBOTS_REDIRECTS:
            chain = (*safe_chain, safe_target)
            raise _RedirectPolicyError("REDIRECT_LIMIT_EXCEEDED", chain)
        try:
            _validate_public_url(target, self.allowed_domains)
        except ValueError as exc:
            chain = (*safe_chain, safe_target)
            raise _RedirectPolicyError("UNREGISTERED_REDIRECT_DOMAIN", chain) from exc
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected is None:
            return None
        chain = (*raw_chain, target)
        setattr(redirected, "_kubo_redirect_chain", chain)
        self.last_redirect_chain = tuple(_provenance_url(item) for item in chain)
        return redirected


def _redirect_handler(opener) -> _AllowlistRedirectHandler | None:
    for handler in getattr(opener, "handlers", ()):
        if isinstance(handler, _AllowlistRedirectHandler):
            return handler
    return None


def _begin_redirect_trace(opener, initial_url: str) -> None:
    handler = _redirect_handler(opener)
    if handler is not None:
        handler.reset_trace(initial_url)


def _observed_redirect_chain(opener, initial_url: str, final_url: str) -> tuple[str, ...]:
    initial = _provenance_url(initial_url)
    final = _provenance_url(final_url)
    handler = _redirect_handler(opener)
    if handler is not None and handler.last_redirect_chain:
        chain = handler.last_redirect_chain
        if chain[0] == initial:
            if chain[-1] != final:
                chain = (*chain, final)
            return chain
    return (initial,) if initial == final else (initial, final)


def _build_public_opener(
    allowed_domains: tuple[str, ...],
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
):
    # An empty ProxyHandler prevents ambient proxy credentials from entering a public capture.
    tls_context = ssl.create_default_context()
    return request.build_opener(
        request.ProxyHandler({}),
        _AllowlistRedirectHandler(allowed_domains),
        _PinnedHTTPSHandler(allowed_domains, resolver=resolver, context=tls_context),
    )


@dataclass(frozen=True)
class _RobotsDecision:
    allowed: bool
    code: str
    receipt: RobotsPolicyReceipt
    retry_after_seconds: float | None = None


class PublicHttpConnector:
    """Bounded HTTPS GET capture that never supplies credentials or solves access challenges."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utc_now,
        opener=None,
        resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
        robots_access_grants: Mapping[str, RobotsAccessGrant] | None = None,
        robots_cache_ttl: timedelta = timedelta(hours=MAX_ROBOTS_CACHE_HOURS),
    ):
        self._clock = clock
        self._opener = opener
        self._resolver = resolver
        grants = dict(robots_access_grants or {})
        for source_id, grant in grants.items():
            if not isinstance(grant, RobotsAccessGrant) or source_id != grant.source_id:
                raise ValueError("robots access grants must be keyed by their trusted source_id")
        if not isinstance(robots_cache_ttl, timedelta):
            raise TypeError("robots_cache_ttl must be a timedelta")
        ttl_seconds = robots_cache_ttl.total_seconds()
        if not 0 < ttl_seconds <= timedelta(hours=MAX_ROBOTS_CACHE_HOURS).total_seconds():
            raise ValueError("robots cache TTL must be positive and no greater than 24 hours")
        self._robots_access_grants = grants
        self._robots_cache_ttl = robots_cache_ttl
        self._robots_cache: dict[tuple[str, str], _RobotsDecision] = {}

    def capture(self, capture_request: CaptureRequest) -> CaptureResult:
        attempted_at = _aware(self._clock(), "clock")
        if capture_request.access_mode not in {"PUBLIC_PAGE", "PUBLIC_DOWNLOAD"}:
            return _failure(
                capture_request,
                attempted_at,
                state="AUTH_REQUIRED",
                query_status="AUTH_REQUIRED",
                error_code="AUTHENTICATED_ACCESS_FORBIDDEN",
            )
        expected_kind = "RAW_PAGE" if capture_request.access_mode == "PUBLIC_PAGE" else "RAW_DOWNLOAD"
        if capture_request.capture_kind != expected_kind:
            return _failure(
                capture_request,
                attempted_at,
                state="BLOCKED",
                query_status="BLOCKED",
                error_code="ACCESS_MODE_CAPTURE_KIND_MISMATCH",
            )

        opener = self._opener or _build_public_opener(
            capture_request.allowed_domains,
            resolver=self._resolver,
        )
        robots_decision = self._robots_allowed(opener, capture_request, attempted_at)
        def finalize(result: CaptureResult) -> CaptureResult:
            return replace(result, robots_policy_receipt=robots_decision.receipt)

        if not robots_decision.allowed:
            if robots_decision.code == "RETRYABLE_RATE_LIMIT":
                return finalize(_failure(
                    capture_request,
                    attempted_at,
                    state="BLOCKED",
                    query_status="BLOCKED",
                    error_code="HTTP_RATE_LIMITED",
                    limitations=(
                        "ROBOTS_ENDPOINT_RATE_LIMITED",
                        "ROBOTS_POLICY_NOT_BYPASSED",
                    ),
                    retry_after_seconds=robots_decision.retry_after_seconds,
                ))
            transient_robots = robots_decision.code == "ROBOTS_UNREACHABLE"
            return finalize(_failure(
                capture_request,
                attempted_at,
                state="ERROR" if transient_robots else "BLOCKED",
                query_status="ERROR" if transient_robots else "BLOCKED",
                error_code=robots_decision.code,
                limitations=("ROBOTS_POLICY_NOT_BYPASSED",),
            ))

        public_request = request.Request(
            capture_request.source_url,
            headers={
                "User-Agent": capture_request.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*;q=0.1",
            },
            method="GET",
        )
        try:
            response = opener.open(public_request, timeout=capture_request.timeout_seconds)
            return finalize(self._read_response(response, capture_request, attempted_at))
        except _UnsafeRedirectError:
            return finalize(_failure(
                capture_request,
                attempted_at,
                state="BLOCKED",
                query_status="BLOCKED",
                error_code="REDIRECT_OUTSIDE_ALLOWLIST",
            ))
        except _DnsResolutionError:
            return finalize(_failure(
                capture_request,
                attempted_at,
                state="ERROR",
                query_status="ERROR",
                error_code="HTTP_DNS_ERROR",
            ))
        except _UnsafeNetworkTargetError:
            return finalize(_failure(
                capture_request,
                attempted_at,
                state="BLOCKED",
                query_status="BLOCKED",
                error_code="NON_PUBLIC_NETWORK_TARGET",
            ))
        except error.HTTPError as exc:
            try:
                final_url = str(exc.geturl() or capture_request.source_url)
                try:
                    _validate_public_url(final_url, capture_request.allowed_domains)
                except ValueError:
                    return finalize(_failure(
                        capture_request,
                        attempted_at,
                        state="BLOCKED",
                        query_status="BLOCKED",
                        error_code="REDIRECT_OUTSIDE_ALLOWLIST",
                    ))
                return finalize(self._http_failure(
                    capture_request,
                    attempted_at,
                    int(exc.code),
                    final_url=final_url,
                    headers=exc.headers,
                ))
            finally:
                exc.close()
        except (TimeoutError, socket.timeout):
            return finalize(_failure(
                capture_request,
                attempted_at,
                state="ERROR",
                query_status="ERROR",
                error_code="HTTP_TIMEOUT",
            ))
        except error.URLError as exc:
            code = "HTTP_TIMEOUT" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "HTTP_TRANSPORT_ERROR"
            return finalize(_failure(
                capture_request,
                attempted_at,
                state="ERROR",
                query_status="ERROR",
                error_code=code,
            ))
        except (OSError, ValueError):
            return finalize(_failure(
                capture_request,
                attempted_at,
                state="ERROR",
                query_status="ERROR",
                error_code="HTTP_TRANSPORT_ERROR",
            ))

    def _robots_allowed(
        self,
        opener,
        capture_request: CaptureRequest,
        attempted_at: datetime,
    ) -> _RobotsDecision:
        parsed = urlparse(capture_request.source_url)
        origin = urlunsplit(("https", parsed.netloc, "", "", ""))
        cache_key = (capture_request.source_url, capture_request.user_agent)
        robots_url = urlunsplit(("https", parsed.netloc, "/robots.txt", "", ""))

        cached = self._robots_cache.get(cache_key)
        if cached is not None:
            if attempted_at < cached.receipt.cache_expires_at:
                receipt = replace(
                    cached.receipt,
                    evaluated_at=attempted_at,
                    cache_hit=True,
                )
                return replace(cached, receipt=receipt)
            self._robots_cache.pop(cache_key, None)

        def decide(
            allowed: bool,
            code: str,
            *,
            status: int | None = None,
            final_url: str | None = None,
            chain: tuple[str, ...] | None = None,
            gates: tuple[str, ...] = (),
            grant: RobotsAccessGrant | None = None,
            retry_after: float | None = None,
            cacheable: bool = False,
        ) -> _RobotsDecision:
            safe_robots = _sanitized_trace_url(robots_url, fallback=robots_url)
            safe_final = _sanitized_trace_url(final_url or robots_url, fallback=robots_url)
            observed_chain = chain or _observed_redirect_chain(
                opener, robots_url, final_url or robots_url
            )
            safe_chain = tuple(
                _sanitized_trace_url(item, fallback=robots_url) for item in observed_chain
            )
            if not safe_chain or safe_chain[0] != safe_robots:
                safe_chain = (safe_robots, *safe_chain)
            if safe_chain[-1] != safe_final:
                safe_chain = (*safe_chain, safe_final)
            expires = attempted_at + self._robots_cache_ttl if cacheable else attempted_at
            receipt = RobotsPolicyReceipt(
                source_id=capture_request.source_id,
                origin=_sanitized_trace_url(origin, fallback=robots_url),
                robots_url=safe_robots,
                final_url=safe_final,
                http_status=status,
                redirect_chain=safe_chain,
                fetched_at=attempted_at,
                evaluated_at=attempted_at,
                cache_expires_at=expires,
                cache_hit=False,
                decision=code,
                access_gates=tuple(gates),
                access_registry_id=grant.registry_id if grant is not None else None,
                access_registry_sha256=(
                    grant.registry_sha256 if grant is not None else None
                ),
                retry_after_seconds=retry_after,
            )
            decision = _RobotsDecision(allowed, code, receipt, retry_after)
            if cacheable:
                self._robots_cache[cache_key] = decision
            return decision

        def not_published(
            status: int,
            final_url: str,
            chain: tuple[str, ...],
        ) -> _RobotsDecision:
            grant = self._robots_access_grants.get(capture_request.source_id)
            if grant is not None and grant.permits(capture_request.source_id, attempted_at):
                return decide(
                    True,
                    "ROBOTS_NOT_PUBLISHED",
                    status=status,
                    final_url=final_url,
                    chain=chain,
                    gates=(
                        "RIGHTS_PERMITTED",
                        "TERMS_REVIEWED_PERMITTED",
                        "PUBLIC_ACCESS_CONFIRMED",
                    ),
                    grant=grant,
                    cacheable=True,
                )
            gates = (
                ("ACCESS_GRANT_EXPIRED",)
                if grant is not None
                else (
                    "RIGHTS_STATUS_UNVERIFIED",
                    "TERMS_STATUS_UNVERIFIED",
                    "PUBLIC_ACCESS_UNVERIFIED",
                )
            )
            return decide(
                False,
                "ACCESS_REVIEW_REQUIRED",
                status=status,
                final_url=final_url,
                chain=chain,
                gates=gates,
                cacheable=True,
            )

        def classify_status(
            status: int,
            final_url: str,
            headers,
            chain: tuple[str, ...],
        ) -> _RobotsDecision | None:
            if status in {404, 410}:
                return not_published(status, final_url, chain)
            if status in {401, 403}:
                return decide(
                    False,
                    "ACCESS_REVIEW_REQUIRED",
                    status=status,
                    final_url=final_url,
                    chain=chain,
                    gates=("AUTHENTICATION_OR_PERMISSION_NOT_BYPASSED",),
                    cacheable=True,
                )
            if status == 429:
                retry_after = _retry_after_seconds(headers, attempted_at)
                return decide(
                    False,
                    "RETRYABLE_RATE_LIMIT",
                    status=status,
                    final_url=final_url,
                    chain=chain,
                    gates=("RETRY_AFTER_RESPECTED",),
                    retry_after=retry_after,
                )
            if status >= 500:
                return decide(
                    False,
                    "ROBOTS_UNREACHABLE",
                    status=status,
                    final_url=final_url,
                    chain=chain,
                    gates=("TEMPORARY_COLLECTION_BLOCK", "HEALTH_PROBE_REQUIRED"),
                )
            if 300 <= status < 400:
                return decide(
                    False,
                    "ROBOTS_REDIRECT_BLOCKED",
                    status=status,
                    final_url=final_url,
                    chain=chain,
                    gates=("UNRESOLVED_REDIRECT",),
                    cacheable=True,
                )
            if status < 200 or status >= 300:
                return decide(
                    False,
                    "ACCESS_REVIEW_REQUIRED",
                    status=status,
                    final_url=final_url,
                    chain=chain,
                    gates=("UNRECOGNIZED_ROBOTS_STATUS",),
                    cacheable=True,
                )
            return None

        robots_request = request.Request(
            robots_url,
            headers={"User-Agent": capture_request.user_agent, "Accept": "text/plain,*/*;q=0.1"},
            method="GET",
        )
        _begin_redirect_trace(opener, robots_url)
        try:
            response = opener.open(robots_request, timeout=capture_request.timeout_seconds)
            try:
                status = int(getattr(response, "status", response.getcode()))
                final_url = str(response.geturl() or robots_url)
                chain = _observed_redirect_chain(opener, robots_url, final_url)
                try:
                    _validate_public_url(final_url, capture_request.allowed_domains)
                except ValueError:
                    return decide(
                        False,
                        "ROBOTS_REDIRECT_BLOCKED",
                        status=status,
                        final_url=final_url,
                        chain=chain,
                        gates=("UNREGISTERED_REDIRECT_DOMAIN",),
                        cacheable=True,
                    )
                classified = classify_status(status, final_url, response.headers, chain)
                if classified is not None:
                    return classified
                body = response.read(MAX_ROBOTS_BYTES + 1)
            finally:
                response.close()
            if len(body) > MAX_ROBOTS_BYTES:
                return decide(
                    False,
                    "ROBOTS_POLICY_TOO_LARGE",
                    status=status,
                    final_url=final_url,
                    chain=chain,
                    gates=("POLICY_BODY_LIMIT_ENFORCED",),
                    cacheable=True,
                )
            policy = robotparser.RobotFileParser()
            policy.set_url(robots_url)
            policy.parse(body.decode("utf-8", errors="replace").splitlines())
            allowed = policy.can_fetch(capture_request.user_agent, capture_request.source_url)
            return decide(
                allowed,
                "ROBOTS_ALLOWED" if allowed else "ROBOTS_DISALLOWED",
                status=status,
                final_url=final_url,
                chain=chain,
                gates=("ROBOTS_POLICY_PARSED",),
                cacheable=True,
            )
        except _RedirectPolicyError as exc:
            return decide(
                False,
                "ROBOTS_REDIRECT_BLOCKED",
                final_url=exc.chain[-1] if exc.chain else robots_url,
                chain=exc.chain or (robots_url,),
                gates=(exc.reason,),
                cacheable=True,
            )
        except _UnsafeRedirectError:
            return decide(
                False,
                "ROBOTS_REDIRECT_BLOCKED",
                gates=("REDIRECT_POLICY_REJECTED",),
                cacheable=True,
            )
        except _DnsResolutionError:
            return decide(
                False,
                "ROBOTS_UNREACHABLE",
                gates=("DNS_FAILURE", "TEMPORARY_COLLECTION_BLOCK", "HEALTH_PROBE_REQUIRED"),
            )
        except _UnsafeNetworkTargetError:
            return decide(
                False,
                "ROBOTS_NON_PUBLIC_NETWORK_TARGET",
                gates=("NON_PUBLIC_NETWORK_TARGET_REJECTED",),
                cacheable=True,
            )
        except error.HTTPError as exc:
            try:
                status = int(exc.code)
                final_url = str(exc.geturl() or robots_url)
                chain = _observed_redirect_chain(opener, robots_url, final_url)
                try:
                    _validate_public_url(final_url, capture_request.allowed_domains)
                except ValueError:
                    return decide(
                        False,
                        "ROBOTS_REDIRECT_BLOCKED",
                        status=status,
                        final_url=final_url,
                        chain=chain,
                        gates=("UNREGISTERED_REDIRECT_DOMAIN",),
                        cacheable=True,
                    )
                classified = classify_status(status, final_url, exc.headers, chain)
                if classified is not None:
                    return classified
                return decide(
                    False,
                    "ROBOTS_UNREACHABLE",
                    status=status,
                    final_url=final_url,
                    chain=chain,
                    gates=("UNEXPECTED_HTTP_ERROR", "HEALTH_PROBE_REQUIRED"),
                )
            finally:
                exc.close()
        except (TimeoutError, socket.timeout, error.URLError, ssl.SSLError, OSError, ValueError):
            return decide(
                False,
                "ROBOTS_UNREACHABLE",
                gates=("NETWORK_OR_TLS_FAILURE", "TEMPORARY_COLLECTION_BLOCK", "HEALTH_PROBE_REQUIRED"),
            )

    def _read_response(
        self,
        response,
        capture_request: CaptureRequest,
        attempted_at: datetime,
    ) -> CaptureResult:
        try:
            status = int(getattr(response, "status", response.getcode()))
            final_url = str(response.geturl() or capture_request.source_url)
            try:
                _validate_public_url(final_url, capture_request.allowed_domains)
            except ValueError:
                return _failure(
                    capture_request,
                    attempted_at,
                    state="BLOCKED",
                    query_status="BLOCKED",
                    error_code="REDIRECT_OUTSIDE_ALLOWLIST",
                    http_status=status,
                )
            if status < 200 or status >= 300:
                return self._http_failure(
                    capture_request,
                    attempted_at,
                    status,
                    final_url=final_url,
                    headers=response.headers,
                )
            if status == 206 or response.headers.get("Content-Range"):
                return _failure(
                    capture_request,
                    attempted_at,
                    state="PARTIAL",
                    query_status="DATA_QUALITY_REJECTED",
                    error_code="UNEXPECTED_PARTIAL_RESPONSE",
                    http_status=status,
                    flags=("UNEXPECTED_PARTIAL_RESPONSE",),
                    final_url=final_url,
                )
            raw_length = response.headers.get("Content-Length")
            if raw_length not in (None, ""):
                try:
                    content_length = int(raw_length)
                except (TypeError, ValueError):
                    return _failure(
                        capture_request,
                        attempted_at,
                        state="PARTIAL",
                        query_status="DATA_QUALITY_REJECTED",
                        error_code="INVALID_CONTENT_LENGTH",
                        http_status=status,
                        flags=("INVALID_CONTENT_LENGTH",),
                        final_url=final_url,
                    )
                if content_length < 0 or content_length > capture_request.max_bytes:
                    return _failure(
                        capture_request,
                        attempted_at,
                        state="PARTIAL",
                        query_status="DATA_QUALITY_REJECTED",
                        error_code="MAX_BYTES_EXCEEDED",
                        http_status=status,
                        flags=("MAX_BYTES_EXCEEDED",),
                        final_url=final_url,
                    )
            content = response.read(capture_request.max_bytes + 1)
            if len(content) > capture_request.max_bytes:
                return _failure(
                    capture_request,
                    attempted_at,
                    state="PARTIAL",
                    query_status="DATA_QUALITY_REJECTED",
                    error_code="MAX_BYTES_EXCEEDED",
                    http_status=status,
                    flags=("MAX_BYTES_EXCEEDED",),
                    final_url=final_url,
                )
            content_type = str(response.headers.get("Content-Type") or "application/octet-stream")
            content_type = content_type.split(";", 1)[0].strip().lower()
            blocker = self._detect_access_blocker(content, content_type, response.headers)
            if blocker == "CAPTCHA_DETECTED":
                return _failure(
                    capture_request,
                    attempted_at,
                    state="BLOCKED",
                    query_status="BLOCKED",
                    error_code=blocker,
                    http_status=status,
                    limitations=("CAPTCHA_NOT_BYPASSED",),
                    final_url=final_url,
                )
            if blocker in {"AUTH_REQUIRED_PAGE", "PAYWALL_DETECTED"}:
                return _failure(
                    capture_request,
                    attempted_at,
                    state="AUTH_REQUIRED",
                    query_status="AUTH_REQUIRED",
                    error_code=blocker,
                    http_status=status,
                    limitations=("AUTHENTICATION_OR_PAYWALL_NOT_BYPASSED",),
                    final_url=final_url,
                )
            observed_at = _aware(self._clock(), "clock")
            return _raw_capture(
                capture_request,
                attempted_at,
                observed_at,
                content,
                content_type=content_type,
                final_url=final_url,
                http_status=status,
            )
        finally:
            response.close()

    @staticmethod
    def _detect_access_blocker(content: bytes, content_type: str, headers) -> str:
        if headers.get("WWW-Authenticate"):
            return "AUTH_REQUIRED_PAGE"
        if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
            return ""
        text = content[: 256 * 1024].decode("utf-8", errors="replace").casefold()
        if any(marker in text for marker in _CAPTCHA_MARKERS):
            return "CAPTCHA_DETECTED"
        if any(marker in text for marker in _PAYWALL_MARKERS):
            return "PAYWALL_DETECTED"
        if any(marker in text for marker in _AUTH_MARKERS):
            return "AUTH_REQUIRED_PAGE"
        return ""

    @staticmethod
    def _http_failure(
        capture_request: CaptureRequest,
        attempted_at: datetime,
        status: int,
        *,
        final_url: str | None = None,
        headers=None,
    ) -> CaptureResult:
        if status in {401, 407}:
            state, query_status, code = "AUTH_REQUIRED", "AUTH_REQUIRED", "HTTP_AUTH_REQUIRED"
        elif status == 402:
            state, query_status, code = "AUTH_REQUIRED", "AUTH_REQUIRED", "PAYWALL_DETECTED"
        elif status == 403:
            state, query_status, code = "BLOCKED", "BLOCKED", "HTTP_FORBIDDEN"
        elif status == 429:
            state, query_status, code = "BLOCKED", "BLOCKED", "HTTP_RATE_LIMITED"
        elif status in {404, 410}:
            state, query_status, code = "PARTIAL", "DATA_QUALITY_REJECTED", "HTTP_RESOURCE_NOT_FOUND"
        elif status >= 500:
            state, query_status, code = "ERROR", "ERROR", "HTTP_SERVER_ERROR"
        else:
            state, query_status, code = "ERROR", "ERROR", "HTTP_STATUS_REJECTED"
        return _failure(
            capture_request,
            attempted_at,
            state=state,
            query_status=query_status,
            error_code=code,
            http_status=status,
            final_url=final_url,
            retry_after_seconds=(
                _retry_after_seconds(headers, attempted_at)
                if code == "HTTP_RATE_LIMITED"
                else None
            ),
        )


@dataclass(frozen=True)
class CaptureBatchResult:
    status: str
    results: tuple[CaptureResult, ...]
    source_states: tuple[tuple[str, str], ...]
    degraded_source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "result_count": len(self.results),
            "source_states": dict(self.source_states),
            "degraded_source_ids": list(self.degraded_source_ids),
        }


def _aggregate_source_state(results: list[CaptureResult]) -> str:
    if results and all(item.state == "AVAILABLE" and item.captured for item in results):
        return "AVAILABLE"
    if any(item.captured for item in results):
        return "PARTIAL"
    states = {item.state for item in results}
    for candidate in ("AUTH_REQUIRED", "BLOCKED", "ERROR", "UNTESTED", "PARTIAL"):
        if candidate in states:
            return candidate
    return "ERROR"


def capture_sources(
    tasks: Iterable[tuple[CaptureConnector, CaptureRequest]],
    *,
    clock: Callable[[], datetime] = _utc_now,
) -> CaptureBatchResult:
    """Capture every source independently; one connector failure never aborts the batch."""

    results: list[CaptureResult] = []
    for connector, capture_request in tasks:
        try:
            result = connector.capture(capture_request)
            if result.source_id != capture_request.source_id:
                raise ValueError("connector returned a result for a different source")
        except Exception:  # A plugin connector is an isolation boundary.
            result = _failure(
                capture_request,
                _aware(clock(), "clock"),
                state="ERROR",
                query_status="ERROR",
                error_code="CONNECTOR_INTERNAL_ERROR",
            )
        results.append(result)

    by_source: dict[str, list[CaptureResult]] = {}
    for result in results:
        by_source.setdefault(result.source_id, []).append(result)
    states = tuple(
        (source_id, _aggregate_source_state(source_results))
        for source_id, source_results in sorted(by_source.items())
    )
    degraded = tuple(source_id for source_id, state in states if state != "AVAILABLE")
    if not results or not any(item.captured for item in results):
        status = "FAILED"
    elif degraded:
        status = "DEGRADED"
    else:
        status = "COMPLETE"
    return CaptureBatchResult(status, tuple(results), states, degraded)


@dataclass(frozen=True)
class CaptureWriteReport:
    status: str
    artifact_count: int
    source_count: int
    source_states: tuple[tuple[str, str], ...]
    degraded_source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "artifact_count": self.artifact_count,
            "source_count": self.source_count,
            "source_states": dict(self.source_states),
            "degraded_source_ids": list(self.degraded_source_ids),
        }


class CapturePacketWriter:
    """Write content-addressed raw files and deterministic V3 manifest/observations."""

    def __init__(self, run_root: Path):
        self.run_root = Path(os.path.abspath(run_root))
        if self.run_root == Path(self.run_root.anchor):
            raise ValueError("run_root must not be a filesystem root")
        require_real_directory(self.run_root.parent, field="run_root parent")
        if self.run_root.exists() or self.run_root.is_symlink():
            require_real_directory(self.run_root, field="run_root")
        else:
            try:
                self.run_root.mkdir(mode=0o700)
            except OSError as exc:
                raise ValueError("run_root cannot be created safely") from exc
            require_real_directory(self.run_root, field="run_root")

    def write(self, results: Iterable[CaptureResult]) -> CaptureWriteReport:
        result_rows = tuple(results)
        if not result_rows:
            raise ValueError("at least one CaptureResult is required")
        artifact_by_path: dict[str, dict[str, object]] = {}
        digest_by_result: dict[int, str] = {}
        for index, result in enumerate(result_rows):
            if result.content is None:
                continue
            digest = sha256_bytes(result.content)
            digest_by_result[index] = digest
            url_key = sha256_bytes((result.final_url + "\0" + result.capture_kind).encode("utf-8"))[:16]
            relative = Path("raw") / result.source_id / f"{url_key}-{digest}.bin"
            target = self.run_root / relative
            self._write_raw_once(target, result.content)
            row = {
                "path": relative.as_posix(),
                "sha256": digest,
                "size_bytes": len(result.content),
                "source_id": result.source_id,
                "source_url": result.final_url,
                "observed_at": result.observed_at.isoformat(),
                "capture_kind": result.capture_kind,
            }
            existing = artifact_by_path.get(relative.as_posix())
            if existing is None or str(row["observed_at"]) < str(existing["observed_at"]):
                artifact_by_path[relative.as_posix()] = row

        artifacts = sorted(
            artifact_by_path.values(),
            key=lambda item: (str(item["source_id"]), str(item["source_url"]), str(item["path"])),
        )
        by_source: dict[str, list[tuple[int, CaptureResult]]] = {}
        for index, result in enumerate(result_rows):
            by_source.setdefault(result.source_id, []).append((index, result))
        observations: list[dict[str, object]] = []
        source_states: list[tuple[str, str]] = []
        for source_id, indexed_results in sorted(by_source.items()):
            source_results = [item for _, item in indexed_results]
            access_modes = {item.access_mode for item in source_results}
            if len(access_modes) != 1:
                raise ValueError(f"source {source_id} mixes access modes in one observation")
            state = _aggregate_source_state(source_results)
            source_states.append((source_id, state))
            hashes = sorted(
                {digest_by_result[index] for index, _ in indexed_results if index in digest_by_result}
            )
            if hashes:
                query_status = "DATA_QUALITY_REJECTED"
            elif "AUTH_REQUIRED" in {item.query_status for item in source_results}:
                query_status = "AUTH_REQUIRED"
            elif "BLOCKED" in {item.query_status for item in source_results}:
                query_status = "BLOCKED"
            else:
                query_status = "ERROR"
            flags = sorted({flag for item in source_results for flag in item.data_quality_flags})
            limitations = sorted({value for item in source_results for value in item.limitations})
            if hashes and "RAW_CAPTURE_PENDING_PARSER_VALIDATION" not in flags:
                flags.append("RAW_CAPTURE_PENDING_PARSER_VALIDATION")
                flags.sort()
            if len(source_results) > 1 and state == "PARTIAL":
                limitations = sorted({*limitations, "SOME_CAPTURE_ATTEMPTS_FAILED"})
            observations.append(
                {
                    "source_id": source_id,
                    "state": state,
                    "access_mode": next(iter(access_modes)),
                    "attempted_at": max(item.attempted_at for item in source_results).isoformat(),
                    "query_status": query_status,
                    "roles_observed": sorted(
                        {role for item in source_results for role in item.roles_observed}
                    ),
                    "qualified_items": 0,
                    "zero_result": False,
                    "raw_sha256s": hashes,
                    "data_quality_flags": flags,
                    "limitations": limitations,
                    "entitlement_id": "",
                }
            )

        self._atomic_write(
            self.run_root / "manifest.json",
            canonical_json_bytes({"schema_version": "3.0", "artifacts": artifacts}),
        )
        self._atomic_write(
            self.run_root / "source_observations.json",
            canonical_json_bytes({"schema_version": "3.0", "sources": observations}),
        )
        robots_receipts: dict[str, dict[str, object]] = {}
        for result in result_rows:
            if result.robots_policy_receipt is None:
                continue
            row = result.robots_policy_receipt.to_dict()
            robots_receipts[str(row["receipt_sha256"])] = row
        if robots_receipts:
            self._atomic_write(
                self.run_root / "robots-policy-receipts.json",
                canonical_json_bytes(
                    {
                        "schema_version": "1.0",
                        "receipts": [robots_receipts[key] for key in sorted(robots_receipts)],
                        "claim_boundaries": {
                            "access_receipt_proves_collection": False,
                            "robots_policy_may_bypass_access_control": False,
                        },
                    }
                ),
            )
        degraded = tuple(source_id for source_id, state in source_states if state != "AVAILABLE")
        status = "COMPLETE" if not degraded else "DEGRADED" if artifacts else "FAILED"
        return CaptureWriteReport(
            status=status,
            artifact_count=len(artifacts),
            source_count=len(source_states),
            source_states=tuple(source_states),
            degraded_source_ids=degraded,
        )

    def _write_raw_once(self, path: Path, content: bytes) -> None:
        relative = self._relative_target(path)
        if self._dirfd_supported():
            with self._secure_parent_fd(relative.parent) as parent_fd:
                assert parent_fd is not None
                flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
                try:
                    descriptor = os.open(relative.name, flags, dir_fd=parent_fd)
                except FileNotFoundError:
                    self._atomic_write_at(parent_fd, relative.name, content)
                    return
                except OSError as exc:
                    raise ValueError("unsafe or unreadable raw artifact target") from exc
                try:
                    metadata = os.fstat(descriptor)
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != len(content):
                        raise ValueError("content-addressed raw artifact collision")
                    chunks: list[bytes] = []
                    while True:
                        chunk = os.read(descriptor, 1024 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    if b"".join(chunks) != content:
                        raise ValueError("content-addressed raw artifact collision")
                finally:
                    os.close(descriptor)
                return

        self._assert_safe_fallback_path(relative)
        target = self.run_root / relative
        if target.exists():
            if target.is_symlink() or not target.is_file() or target.stat().st_size != len(content) or target.read_bytes() != content:
                raise ValueError("content-addressed raw artifact collision")
            return
        self._atomic_write(path, content)

    def write_content_addressed_artifact(self, relative: Path, content: bytes) -> None:
        """Write one raw content-addressed artifact through the secure dirfd path."""

        candidate = Path(relative)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or len(candidate.parts) < 3
            or candidate.parts[0] != "raw"
            or not isinstance(content, bytes)
            or sha256_bytes(content) not in candidate.name
        ):
            raise ValueError("content-addressed artifact path is invalid")
        self._write_raw_once(self.run_root / candidate, content)

    def _atomic_write(self, path: Path, content: bytes) -> None:
        relative = self._relative_target(path)
        if self._dirfd_supported():
            with self._secure_parent_fd(relative.parent) as parent_fd:
                assert parent_fd is not None
                self._atomic_write_at(parent_fd, relative.name, content)
            return

        self._assert_safe_fallback_path(relative)
        target = self.run_root / relative
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if target.is_symlink():
                raise ValueError("output target must not be a symlink")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _relative_target(self, path: Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.run_root / candidate
        try:
            relative = candidate.relative_to(self.run_root)
        except ValueError as exc:
            raise ValueError("output target escapes run_root") from exc
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("output target escapes run_root")
        return relative

    @staticmethod
    def _dirfd_supported() -> bool:
        return (
            os.name == "posix"
            and hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and os.open in os.supports_dir_fd
            and os.mkdir in os.supports_dir_fd
            and os.rename in os.supports_dir_fd
        )

    @contextmanager
    def _secure_parent_fd(self, relative_parent: Path):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(self.run_root, flags)
        try:
            for component in relative_parent.parts:
                if component in {"", ".", ".."}:
                    raise ValueError("unsafe output directory component")
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                try:
                    next_descriptor = os.open(component, flags, dir_fd=descriptor)
                except OSError as exc:
                    raise ValueError("output directory contains a symlink or non-directory") from exc
                os.close(descriptor)
                descriptor = next_descriptor
            yield descriptor
        finally:
            os.close(descriptor)

    @staticmethod
    def _atomic_write_at(parent_fd: int, name: str, content: bytes) -> None:
        if not name or name in {".", ".."} or "/" in name:
            raise ValueError("unsafe output filename")
        try:
            existing = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise ValueError("output target must be a regular file")

        temporary_name = f".{name}.{secrets.token_hex(12)}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            descriptor = -1
            os.rename(
                temporary_name,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.fsync(parent_fd)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass

    def _assert_safe_fallback_path(self, relative: Path) -> None:
        current = self.run_root
        for component in relative.parts[:-1]:
            current = current / component
            if current.exists() and current.is_symlink():
                raise ValueError("output directory contains a symlink")
            current.mkdir(mode=0o700, exist_ok=True)
            if current.is_symlink() or not current.is_dir():
                raise ValueError("output directory contains a symlink or non-directory")


__all__ = [
    "ACCESS_MODES",
    "CAPTURE_KINDS",
    "CAPTURE_STATES",
    "CaptureBatchResult",
    "CaptureConnector",
    "CapturePacketWriter",
    "CaptureRequest",
    "CaptureResult",
    "CaptureWriteReport",
    "DEFAULT_USER_AGENT",
    "FileConnector",
    "FixtureConnector",
    "FixtureFileConnector",
    "MAX_CAPTURE_BYTES",
    "MAX_ROBOTS_CACHE_HOURS",
    "MAX_ROBOTS_REDIRECTS",
    "PublicHttpConnector",
    "QUERY_STATUSES",
    "RobotsAccessGrant",
    "RobotsPolicyReceipt",
    "capture_sources",
]
