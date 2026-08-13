from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from .atomic_output import run_atomic_output
from .foundation_io import (
    load_strict_json_object,
    nonnegative_int,
    positive_int,
    prepare_output_root,
    read_csv_bytes,
    require_real_directory,
    safe_regular_file,
    write_csv,
)
from .hashing import canonical_json_bytes, sha256_bytes
from .official_eod_workspace import (
    CAPTURE_MODES,
    EVIDENCE_CLASSIFICATIONS,
    MARKET_TOTALS_AVAILABILITY,
    OFFICIAL_EOD_MANIFEST_SCHEMA_VERSION,
    PRICE_BASES,
    PROVIDER_AVAILABILITY,
    RAW_DAILY_MARKET_TOTAL_HEADERS,
    RAW_OFFICIAL_EOD_HEADERS,
    RIGHTS_STATUSES,
    SOURCE_CLASSES,
    SUPPLIED_FIELD_GROUPS,
    TRADING_STATES,
    UpstreamContext,
    identity_for,
    load_eod_upstreams,
    status_for,
)
from .runtime_trust import RuntimeTrustError, RuntimeTrustRegistry
from .strict import contains_placeholder, https_url, parse_aware, parse_iso_date, require_sha256
from .tri_security_admission import (
    BoundaryAdmissionRequest,
    admit_boundary,
    build_boundary_operation_binding,
)


def _validated_imported_at(value: Any) -> datetime:
    parsed = parse_aware(value, "imported_at")
    if parsed > datetime.now(timezone.utc):
        raise ValueError("official EOD imported_at must not be in the future")
    return parsed


OFFICIAL_DAILY_EOD_HEADERS = (
    "trade_date",
    "security_code",
    "ticker",
    "board",
    "currency",
    "price_unit",
    "value_unit",
    "price_basis",
    "trading_state",
    "open_fils",
    "high_fils",
    "low_fils",
    "close_fils",
    "volume",
    "value_traded_kwd",
    "trade_count",
    "reference_price_fils",
    "available_official_fields",
    "field_origin",
    "provider_id",
    "source_id",
    "source_url",
    "observed_at",
    "raw_sha256",
    "supporting_raw_sha256s",
    "evidence_classification",
    "rights_status",
)
DAILY_MARKET_TOTALS_HEADERS = (
    "trade_date",
    "board",
    "scope",
    "currency",
    "value_unit",
    "traded_security_count",
    "total_volume",
    "total_value_kwd",
    "total_trade_count",
    "provider_id",
    "source_id",
    "source_url",
    "observed_at",
    "raw_sha256",
    "evidence_classification",
    "rights_status",
)
QUARANTINE_HEADERS = (
    "trade_date",
    "security_code",
    "reason",
    "provider_ids",
    "raw_sha256s",
)

_PROVIDER_FIELDS = frozenset(
    {
        "provider_id",
        "source_id",
        "source_url",
        "source_class",
        "capture_mode",
        "availability_status",
        "file_name",
        "file_sha256",
        "observed_at",
        "captured_by",
        "review_status",
        "supplied_fields",
        "field_origin",
        "price_basis",
        "evidence_classification",
        "rights_status",
        "pages_declared",
        "pages_received",
        "result_count_declared",
        "rows_normalized",
        "zero_result",
        "subject_id",
        "entitlement_id",
    }
)
_TOTALS_FIELDS = frozenset(
    {
        "provider_id",
        "source_id",
        "source_url",
        "source_class",
        "capture_mode",
        "availability_status",
        "file_name",
        "file_sha256",
        "observed_at",
        "captured_by",
        "review_status",
        "scope",
        "board",
        "evidence_classification",
        "rights_status",
        "pages_declared",
        "pages_received",
        "result_count_declared",
        "rows_normalized",
        "zero_result",
        "subject_id",
        "entitlement_id",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "window_from",
        "window_to",
        "upstream",
        "providers",
        "market_totals",
    }
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}\.csv$")
_UNSIGNED_INT_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")
_UNSIGNED_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_OFFICIAL_DOMAINS = frozenset({"boursakuwait.com.kw", "cma.gov.kw"})
_FIELD_ORDER = (
    "TRADING_STATE",
    "OHLC",
    "VOLUME",
    "VALUE_TRADED_KWD",
    "TRADE_COUNT",
    "REFERENCE_PRICE",
)
_COMPLETE_EOD_FIELD_GROUPS = frozenset(
    {"TRADING_STATE", "OHLC", "VOLUME", "VALUE_TRADED_KWD", "TRADE_COUNT"}
)


@dataclass(frozen=True)
class ProviderCapture:
    row: dict[str, Any]
    content: bytes | None
    raw_rows: tuple[dict[str, str], ...]
    effective_classification: str
    trust_receipt: dict[str, Any] | None


@dataclass(frozen=True)
class Evaluation:
    normalized_rows: tuple[dict[str, Any], ...]
    totals_rows: tuple[dict[str, Any], ...]
    quarantine_rows: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    denominator_status: str
    price_evidence_status: str
    market_totals_status: str
    query_and_pagination_status: str
    status: str
    evidence_classification: str
    rights_status: str
    missing_pair_count: int


def _exact_object(value: Any, fields: frozenset[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{field} has unknown or missing fields")
    return value


def _identifier(value: Any, field: str, *, optional: bool = False) -> str:
    if optional and value == "":
        return ""
    if not isinstance(value, str) or value != value.strip() or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field} must be a canonical identifier")
    return value


def _file_name(value: Any, field: str, *, optional: bool = False) -> str:
    if optional and value == "":
        return ""
    if not isinstance(value, str) or value != value.strip() or not _FILE_NAME_RE.fullmatch(value):
        raise ValueError(f"{field} must be a canonical CSV basename")
    return value


def _strict_json_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be a JSON boolean")
    return value


def _optional_count(value: Any, field: str) -> int | None:
    if value == "":
        return None
    return nonnegative_int(value, field)


def _integer(value: Any, field: str, *, positive: bool = False) -> int:
    text = str(value or "")
    if not _UNSIGNED_INT_RE.fullmatch(text):
        raise ValueError(f"{field} must be a canonical non-negative integer")
    parsed = int(text)
    if positive and parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    text = str(value or "")
    if not _UNSIGNED_DECIMAL_RE.fullmatch(text):
        raise ValueError(f"{field} must be a canonical non-negative decimal")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        requirement = "positive" if positive else "finite and non-negative"
        raise ValueError(f"{field} must be {requirement}")
    return parsed


def _host_is_official(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in _OFFICIAL_DOMAINS)


def _classification(values: Iterable[str], *, fallback: str = "PARTIAL") -> str:
    collected = set(values)
    precedence = (
        "BLOCKED",
        "SYNTHETIC_ONLY",
        "LICENSED_FEED_DEPENDENT",
        "LIVE_DEPENDENT",
        "PARTIAL",
        "RECORDED_AUTHORIZED_FIXTURE",
        "PROVEN_REAL_EVIDENCE",
    )
    return next((value for value in precedence if value in collected), fallback)


def _rights(values: Iterable[str]) -> str:
    collected = set(values)
    for value in ("RESTRICTED", "UNKNOWN", "FIXTURE_ONLY", "RESEARCH_USE_AUTHORIZED"):
        if value in collected:
            return value
    return "UNKNOWN"


def _source_trust(
    row: dict[str, Any],
    *,
    imported_at: datetime,
    security_codes: tuple[str, ...],
    runtime_trust_registry: RuntimeTrustRegistry | None,
    field: str,
) -> tuple[str, dict[str, Any] | None]:
    source_class = row["source_class"]
    capture_mode = row["capture_mode"]
    source_url = row["source_url"]
    evidence = row["evidence_classification"]
    rights = row["rights_status"]
    if capture_mode not in CAPTURE_MODES:
        raise ValueError(f"{field}.capture_mode is unsupported")
    if capture_mode == "RECORDED_AUTHORIZED_FIXTURE" and (
        evidence != "RECORDED_AUTHORIZED_FIXTURE" or rights != "FIXTURE_ONLY"
    ):
        raise ValueError(f"{field} recorded fixture capture metadata conflicts")
    if capture_mode == "SYNTHETIC_GENERATED" and (
        evidence != "SYNTHETIC_ONLY" or rights != "FIXTURE_ONLY"
    ):
        raise ValueError(f"{field} synthetic capture metadata conflicts")
    if source_class == "OFFICIAL":
        if capture_mode == "LICENSED_VENDOR_EXPORT":
            raise ValueError(f"{field} official source cannot claim licensed capture")
        if row["entitlement_id"]:
            raise ValueError(f"{field} official sources must not declare entitlement IDs")
        if evidence == "PROVEN_REAL_EVIDENCE":
            if capture_mode not in {
                "PUBLIC_OFFICIAL_DOWNLOAD",
                "USER_PROVIDED_OFFICIAL_EXPORT",
            }:
                raise ValueError(f"{field} real official evidence lacks official capture provenance")
            if not _host_is_official(source_url):
                raise ValueError(f"{field} real official evidence is outside the authority allowlist")
            if rights != "RESEARCH_USE_AUTHORIZED":
                raise ValueError(f"{field} real official evidence lacks authorized research rights")
            if runtime_trust_registry is None:
                return "LIVE_DEPENDENT", None
            subject_id = _identifier(row["subject_id"], f"{field}.subject_id")
            domain = (urlsplit(source_url).hostname or "").lower()
            try:
                for code in security_codes:
                    runtime_trust_registry.require_authority(
                        source_id=row["source_id"],
                        subject_id=subject_id,
                        domain=domain,
                        decision_at=imported_at,
                        security_code=code,
                    )
            except RuntimeTrustError as exc:
                raise ValueError(f"{field} runtime authority failed: {exc}") from exc
            return "LIVE_DEPENDENT", {
                "registry_id": runtime_trust_registry.registry_id,
                "registry_sha256": runtime_trust_registry.content_sha256,
                "authenticated_key_id": runtime_trust_registry.authenticated_key_id,
            }
        if row["subject_id"]:
            raise ValueError(
                f"{field} non-real official evidence must not declare runtime authority IDs"
            )
        return evidence, None
    if source_class != "LICENSED":
        raise ValueError(f"{field}.source_class is unsupported")
    if capture_mode != "LICENSED_VENDOR_EXPORT":
        raise ValueError(f"{field} licensed source must declare LICENSED_VENDOR_EXPORT")
    subject_id = _identifier(row["subject_id"], f"{field}.subject_id")
    entitlement_id = _identifier(row["entitlement_id"], f"{field}.entitlement_id")
    if runtime_trust_registry is None:
        return "LICENSED_FEED_DEPENDENT", None
    domain = (urlsplit(source_url).hostname or "").lower()
    try:
        for code in security_codes:
            runtime_trust_registry.require_authority(
                source_id=row["source_id"],
                subject_id=subject_id,
                domain=domain,
                decision_at=imported_at,
                security_code=code,
            )
            runtime_trust_registry.require_entitlement(
                source_id=row["source_id"],
                entitlement_id=entitlement_id,
                decision_at=imported_at,
                security_code=code,
            )
    except RuntimeTrustError as exc:
        raise ValueError(f"{field} runtime trust failed: {exc}") from exc
    if rights != "RESEARCH_USE_AUTHORIZED":
        raise ValueError(f"{field} licensed evidence lacks authorized research rights")
    return "LICENSED_FEED_DEPENDENT", {
        "registry_id": runtime_trust_registry.registry_id,
        "registry_sha256": runtime_trust_registry.content_sha256,
        "authenticated_key_id": runtime_trust_registry.authenticated_key_id,
    }


def _validate_observed_after_session_close(
    rows: list[dict[str, str]],
    *,
    observed_at: datetime,
    context: UpstreamContext,
    field: str,
) -> None:
    """Reject a daily-close artifact observed before any represented session ended."""

    for index, row in enumerate(rows):
        day = parse_iso_date(row.get("trade_date"), f"{field} row {index}.trade_date")
        calendar_row = context.calendar.get(day)
        if calendar_row is None or calendar_row.get("is_trading_day", "").casefold() != "true":
            raise ValueError(f"{field} row {index} is not an official trading session")
        close_time = str(calendar_row.get("trade_at_last_end", ""))
        try:
            session_close = parse_aware(
                f"{day.isoformat()}T{close_time}+03:00",
                f"{field} row {index}.session_close",
            )
        except ValueError as exc:
            raise ValueError(
                f"{field} row {index} lacks a valid official session close"
            ) from exc
        if observed_at < session_close:
            raise ValueError(
                f"{field}.observed_at precedes official session close: {day.isoformat()}"
            )


def _validate_query_receipt(
    row: dict[str, Any],
    *,
    availability: str,
    actual_rows: int,
    field: str,
) -> dict[str, Any]:
    pages_declared = _optional_count(row["pages_declared"], f"{field}.pages_declared")
    pages_received = _optional_count(row["pages_received"], f"{field}.pages_received")
    result_count = _optional_count(
        row["result_count_declared"], f"{field}.result_count_declared"
    )
    rows_normalized = _optional_count(row["rows_normalized"], f"{field}.rows_normalized")
    zero_result = _strict_json_bool(row["zero_result"], f"{field}.zero_result")
    if availability in {"UNAVAILABLE", "NOT_AVAILABLE_FROM_SOURCE"}:
        if any(value is not None for value in (pages_declared, pages_received, result_count, rows_normalized)):
            raise ValueError(f"{field} unavailable receipt must leave query counts blank")
        if zero_result:
            raise ValueError(f"{field} unavailable receipt is not an observed zero result")
        return {
            "pages_declared": None,
            "pages_received": None,
            "result_count_declared": None,
            "rows_normalized": None,
            "zero_result": False,
            "complete": False,
        }
    if any(value is None for value in (pages_declared, pages_received, result_count, rows_normalized)):
        raise ValueError(f"{field} captured receipt requires all query counts")
    assert pages_declared is not None and pages_received is not None
    assert result_count is not None and rows_normalized is not None
    if pages_declared <= 0 or pages_received > pages_declared:
        raise ValueError(f"{field} has impossible pagination counts")
    if rows_normalized != actual_rows:
        raise ValueError(f"{field}.rows_normalized does not match the captured CSV")
    if availability == "AVAILABLE":
        if pages_declared != pages_received or result_count != actual_rows or zero_result or actual_rows == 0:
            raise ValueError(f"{field} AVAILABLE receipt is incomplete")
    elif availability == "ZERO_RESULT":
        if pages_declared != pages_received or result_count != 0 or actual_rows != 0 or not zero_result:
            raise ValueError(f"{field} ZERO_RESULT receipt does not prove zero")
    elif availability == "PARTIAL":
        if zero_result:
            raise ValueError(f"{field} PARTIAL receipt must not claim a complete zero result")
        if result_count < actual_rows:
            raise ValueError(f"{field} declared result count is smaller than captured rows")
    else:
        raise ValueError(f"{field} has unsupported availability_status")
    return {
        "pages_declared": pages_declared,
        "pages_received": pages_received,
        "result_count_declared": result_count,
        "rows_normalized": rows_normalized,
        "zero_result": zero_result,
        "complete": availability == "AVAILABLE",
    }


def _load_manifest(
    root: Path,
    *,
    context: UpstreamContext,
) -> tuple[dict[str, Any], bytes, date, date]:
    manifest, manifest_bytes = load_strict_json_object(
        root / "manifests" / "official_eod_manifest.json",
        field="official EOD manifest",
    )
    _exact_object(manifest, _MANIFEST_FIELDS, "official EOD manifest")
    if manifest["schema_version"] != OFFICIAL_EOD_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported official EOD manifest schema_version")
    _identifier(manifest["run_id"], "official EOD manifest.run_id")
    start = parse_iso_date(manifest["window_from"], "official EOD manifest.window_from")
    end = parse_iso_date(manifest["window_to"], "official EOD manifest.window_to")
    if start > end:
        raise ValueError("official EOD manifest window is reversed")
    if manifest["upstream"] != context.receipt:
        raise ValueError("official EOD workspace has stale or substituted upstream receipts")
    providers = manifest["providers"]
    if not isinstance(providers, list):
        raise ValueError("official EOD manifest.providers must be an array")
    _exact_object(manifest["market_totals"], _TOTALS_FIELDS, "official EOD manifest.market_totals")
    return manifest, manifest_bytes, start, end


def _load_provider_captures(
    root: Path,
    *,
    providers: list[Any],
    context: UpstreamContext,
    imported_at: datetime,
    runtime_trust_registry: RuntimeTrustRegistry | None,
    raw_directory: Path,
) -> tuple[list[ProviderCapture], list[dict[str, Any]]]:
    captures: list[ProviderCapture] = []
    receipts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_file_names: set[str] = set()
    for index, value in enumerate(providers):
        field = f"providers[{index}]"
        row = _exact_object(value, _PROVIDER_FIELDS, field)
        provider_id = _identifier(row["provider_id"], f"{field}.provider_id")
        if provider_id in seen_ids:
            raise ValueError("official EOD manifest contains duplicate provider_id")
        seen_ids.add(provider_id)
        _identifier(row["source_id"], f"{field}.source_id")
        source_url = https_url(row["source_url"], f"{field}.source_url")
        if row["source_class"] not in SOURCE_CLASSES:
            raise ValueError(f"{field}.source_class is unsupported")
        availability = row["availability_status"]
        if availability not in PROVIDER_AVAILABILITY:
            raise ValueError(f"{field}.availability_status is unsupported")
        if row["price_basis"] not in PRICE_BASES:
            raise ValueError(f"{field}.price_basis is unsupported")
        fields = row["supplied_fields"]
        if not isinstance(fields, list) or len(fields) != len(set(fields)) or any(item not in SUPPLIED_FIELD_GROUPS for item in fields):
            raise ValueError(f"{field}.supplied_fields is not a unique canonical list")
        expected_origin = (
            "OFFICIAL_SOURCE_FIELDS"
            if row["source_class"] == "OFFICIAL"
            else "LICENSED_SOURCE_FIELDS"
        )
        if row["field_origin"] != expected_origin:
            raise ValueError(f"{field}.field_origin must prove direct source fields")
        if row["evidence_classification"] not in EVIDENCE_CLASSIFICATIONS:
            raise ValueError(f"{field}.evidence_classification is unsupported")
        if row["rights_status"] not in RIGHTS_STATUSES:
            raise ValueError(f"{field}.rights_status is unsupported")
        file_name = _file_name(
            row["file_name"], f"{field}.file_name", optional=availability == "UNAVAILABLE"
        )
        content: bytes | None = None
        raw_rows: list[dict[str, str]] = []
        digest = ""
        observed_at: datetime | None = None
        if availability != "UNAVAILABLE":
            if file_name in seen_file_names:
                raise ValueError("official EOD providers must use unique artifact file names")
            seen_file_names.add(file_name)
            digest = require_sha256(row["file_sha256"], f"{field}.file_sha256")
            observed_at = parse_aware(row["observed_at"], f"{field}.observed_at")
            if observed_at > imported_at:
                raise ValueError(f"{field}.observed_at is after imported_at")
            _identifier(row["captured_by"], f"{field}.captured_by")
            if row["review_status"] != "ACCEPTED":
                raise ValueError(f"{field} captured evidence is not accepted")
            content = safe_regular_file(
                raw_directory / file_name,
                field=f"official EOD provider artifact {provider_id}",
            )
            if sha256_bytes(content) != digest:
                raise ValueError(f"official EOD provider artifact hash mismatch: {provider_id}")
            _, raw_rows = read_csv_bytes(
                content,
                field=f"official EOD provider artifact {provider_id}",
                exact_headers=RAW_OFFICIAL_EOD_HEADERS,
            )
            _validate_observed_after_session_close(
                raw_rows,
                observed_at=observed_at,
                context=context,
                field=f"official EOD provider artifact {provider_id}",
            )
        else:
            if (
                row["file_sha256"]
                or row["observed_at"]
                or row["capture_mode"]
                or row["review_status"] == "ACCEPTED"
            ):
                raise ValueError(f"{field} UNAVAILABLE entry must not claim captured evidence")
        query = _validate_query_receipt(
            row, availability=availability, actual_rows=len(raw_rows), field=field
        )
        if raw_rows and "TRADING_STATE" not in fields:
            raise ValueError(f"{field} rows require explicit TRADING_STATE source availability")
        effective, trust_receipt = (
            _source_trust(
                row,
                imported_at=imported_at,
                security_codes=context.security_codes,
                runtime_trust_registry=runtime_trust_registry,
                field=field,
            )
            if availability != "UNAVAILABLE"
            else (row["evidence_classification"], None)
        )
        captures.append(
            ProviderCapture(
                row={**row, "source_url": source_url},
                content=content,
                raw_rows=tuple(raw_rows),
                effective_classification=effective,
                trust_receipt=trust_receipt,
            )
        )
        receipts.append(
            {
                "provider_id": provider_id,
                "source_id": row["source_id"],
                "source_url": source_url,
                "source_class": row["source_class"],
                "capture_mode": row["capture_mode"],
                "availability_status": availability,
                "artifact_path": (
                    f"raw/providers/{file_name}" if content is not None else None
                ),
                "artifact_sha256": digest or None,
                "observed_at": observed_at.isoformat() if observed_at else None,
                "supplied_fields": list(fields),
                "field_origin": row["field_origin"],
                "price_basis": row["price_basis"],
                "evidence_classification": effective,
                "rights_status": row["rights_status"],
                **query,
                "runtime_trust": trust_receipt,
            }
        )
    return captures, receipts


def _zero_or_blank(value: str, field: str, *, decimal: bool = False) -> None:
    if value == "":
        return
    parsed = _decimal(value, field) if decimal else _integer(value, field)
    if parsed != 0:
        raise ValueError(f"{field} must be blank or zero on a non-traded row")


def _parse_provider_row(
    row: dict[str, str],
    *,
    capture: ProviderCapture,
    context: UpstreamContext,
    row_index: int,
) -> tuple[tuple[date, str], dict[str, Any]]:
    provider = capture.row
    provider_id = provider["provider_id"]
    if any(contains_placeholder(value) for value in row.values()):
        raise ValueError("template placeholder is forbidden")
    day = parse_iso_date(row["trade_date"], f"{provider_id} row {row_index}.trade_date")
    if day not in context.sessions:
        raise ValueError("row is not on an official trading session")
    code = row["security_code"]
    if code not in context.security_codes:
        raise ValueError("row security_code is outside the declared pilot")
    identity = identity_for(context, security_code=code, day=day)
    status = status_for(context, security_code=code, day=day)
    ticker = row["ticker"]
    if ticker != identity["ticker"] or ticker != status["ticker"]:
        raise ValueError("row ticker does not match effective identity and status")
    state = row["trading_state"]
    if state not in TRADING_STATES:
        raise ValueError("row trading_state is unsupported")
    allowed_by_status = {
        "TRADING": {"TRADED", "NO_TRADE", "HALTED"},
        "SUSPENDED": {"SUSPENDED", "TRADED_THEN_SUSPENDED"},
        "DELISTED": {"NOT_LISTED_OR_NOT_ELIGIBLE"},
    }
    if state not in allowed_by_status[status["status"]]:
        raise ValueError("row trading_state conflicts with effective historical status")
    if identity["listing_status"] == "DELISTED" and state != "NOT_LISTED_OR_NOT_ELIGIBLE":
        raise ValueError("delisted effective identity requires NOT_LISTED_OR_NOT_ELIGIBLE")
    if state == "NOT_LISTED_OR_NOT_ELIGIBLE" and not (
        status["status"] == "DELISTED" or identity["listing_status"] == "DELISTED"
    ):
        raise ValueError("NOT_LISTED_OR_NOT_ELIGIBLE lacks affirmative effective evidence")

    supplied = set(provider["supplied_fields"])
    raw_fields = {
        "OHLC": ("open_fils", "high_fils", "low_fils", "close_fils"),
        "VOLUME": ("volume",),
        "VALUE_TRADED_KWD": ("value_traded_kwd",),
        "TRADE_COUNT": ("trade_count",),
        "REFERENCE_PRICE": ("reference_price_fils",),
    }
    for group, names in raw_fields.items():
        if group not in supplied and any(row[name] != "" for name in names):
            raise ValueError(f"fields are populated although {group} is unavailable")
    traded = state in {"TRADED", "TRADED_THEN_SUSPENDED"}
    if traded:
        if "OHLC" in supplied:
            prices = {
                name: _integer(row[name], name, positive=True)
                for name in raw_fields["OHLC"]
            }
            if prices["high_fils"] < max(prices.values()):
                raise ValueError("OHLC high constraint failed")
            if prices["low_fils"] > min(prices.values()):
                raise ValueError("OHLC low constraint failed")
        if "VOLUME" in supplied:
            _integer(row["volume"], "volume", positive=True)
        if "VALUE_TRADED_KWD" in supplied:
            _decimal(row["value_traded_kwd"], "value_traded_kwd", positive=True)
        if "TRADE_COUNT" in supplied:
            _integer(row["trade_count"], "trade_count", positive=True)
        if "REFERENCE_PRICE" in supplied and row["reference_price_fils"]:
            _integer(row["reference_price_fils"], "reference_price_fils", positive=True)
    else:
        if any(row[name] for name in raw_fields["OHLC"]):
            raise ValueError("non-traded row contains synthetic OHLC")
        if "VOLUME" in supplied:
            _zero_or_blank(row["volume"], "volume")
        if "VALUE_TRADED_KWD" in supplied:
            _zero_or_blank(row["value_traded_kwd"], "value_traded_kwd", decimal=True)
        if "TRADE_COUNT" in supplied:
            _zero_or_blank(row["trade_count"], "trade_count")
        if "REFERENCE_PRICE" in supplied and row["reference_price_fils"]:
            _integer(row["reference_price_fils"], "reference_price_fils", positive=True)
    ordered_fields = [item for item in _FIELD_ORDER if item in supplied]
    normalized = {
        "trade_date": day.isoformat(),
        "security_code": code,
        "ticker": ticker,
        "board": "cash",
        "currency": "KWD",
        "price_unit": "FILS",
        "value_unit": "KWD",
        "price_basis": provider["price_basis"],
        "trading_state": state,
        "open_fils": row["open_fils"],
        "high_fils": row["high_fils"],
        "low_fils": row["low_fils"],
        "close_fils": row["close_fils"],
        "volume": row["volume"],
        "value_traded_kwd": row["value_traded_kwd"],
        "trade_count": row["trade_count"],
        "reference_price_fils": row["reference_price_fils"],
        "available_official_fields": "|".join(ordered_fields),
        "field_origin": provider["field_origin"],
        "provider_id": provider_id,
        "source_id": provider["source_id"],
        "source_url": provider["source_url"],
        "observed_at": parse_aware(provider["observed_at"], "observed_at").isoformat(),
        "raw_sha256": provider["file_sha256"],
        "supporting_raw_sha256s": "",
        "evidence_classification": capture.effective_classification,
        "rights_status": provider["rights_status"],
    }
    return (day, code), normalized


def _semantic_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        row[field]
        for field in (
            "trade_date",
            "security_code",
            "ticker",
            "board",
            "currency",
            "price_unit",
            "value_unit",
            "price_basis",
            "trading_state",
            "open_fils",
            "high_fils",
            "low_fils",
            "close_fils",
            "volume",
            "value_traded_kwd",
            "trade_count",
            "reference_price_fils",
            "available_official_fields",
        )
    )


def _normalize_providers(
    captures: Iterable[ProviderCapture],
    *,
    context: UpstreamContext,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    by_key: dict[tuple[date, str], list[dict[str, Any]]] = {}
    quarantine: list[dict[str, Any]] = []
    errors: list[str] = []
    for capture in captures:
        provider_id = capture.row["provider_id"]
        seen: set[tuple[date, str]] = set()
        for index, row in enumerate(capture.raw_rows):
            try:
                key, parsed = _parse_provider_row(
                    row, capture=capture, context=context, row_index=index
                )
                if key in seen:
                    raise ValueError("duplicate provider security-session key")
                seen.add(key)
                by_key.setdefault(key, []).append(parsed)
            except ValueError as exc:
                errors.append(f"PROVIDER_ROW_INVALID:{provider_id}:{index}:{exc}")
                quarantine.append(
                    {
                        "trade_date": row.get("trade_date", ""),
                        "security_code": row.get("security_code", ""),
                        "reason": f"ROW_INVALID:{exc}",
                        "provider_ids": provider_id,
                        "raw_sha256s": capture.row.get("file_sha256", ""),
                    }
                )
    normalized: list[dict[str, Any]] = []
    for key, rows in sorted(by_key.items(), key=lambda item: (item[0][0], int(item[0][1]))):
        signatures = {_semantic_signature(row) for row in rows}
        if len(signatures) != 1:
            provider_ids = sorted(row["provider_id"] for row in rows)
            hashes = sorted({row["raw_sha256"] for row in rows})
            errors.append(
                f"PROVIDER_DISAGREEMENT:{key[0].isoformat()}:{key[1]}:{','.join(provider_ids)}"
            )
            quarantine.append(
                {
                    "trade_date": key[0].isoformat(),
                    "security_code": key[1],
                    "reason": "PROVIDER_DISAGREEMENT",
                    "provider_ids": "|".join(provider_ids),
                    "raw_sha256s": "|".join(hashes),
                }
            )
            continue
        primary = min(rows, key=lambda item: item["provider_id"])
        supporting = sorted(
            {row["raw_sha256"] for row in rows if row["raw_sha256"] != primary["raw_sha256"]}
        )
        primary = {
            **primary,
            "supporting_raw_sha256s": "|".join(supporting),
            "evidence_classification": _classification(
                row["evidence_classification"] for row in rows
            ),
            "rights_status": _rights(row["rights_status"] for row in rows),
        }
        normalized.append(primary)
    return normalized, quarantine, errors


def _load_totals_capture(
    root: Path,
    *,
    value: dict[str, Any],
    context: UpstreamContext,
    imported_at: datetime,
    runtime_trust_registry: RuntimeTrustRegistry | None,
    raw_directory: Path,
) -> tuple[ProviderCapture, dict[str, Any]]:
    row = _exact_object(value, _TOTALS_FIELDS, "market_totals")
    availability = row["availability_status"]
    if availability not in MARKET_TOTALS_AVAILABILITY:
        raise ValueError("market_totals.availability_status is unsupported")
    if row["source_class"] not in SOURCE_CLASSES:
        raise ValueError("market_totals.source_class is unsupported")
    if row["scope"] != "DECLARED_PILOT" or row["board"] != "cash":
        raise ValueError("market totals must use the cash DECLARED_PILOT scope")
    if row["evidence_classification"] not in EVIDENCE_CLASSIFICATIONS:
        raise ValueError("market_totals.evidence_classification is unsupported")
    if row["rights_status"] not in RIGHTS_STATUSES:
        raise ValueError("market_totals.rights_status is unsupported")
    unavailable = availability == "NOT_AVAILABLE_FROM_SOURCE"
    provider_id = _identifier(row["provider_id"], "market_totals.provider_id", optional=unavailable)
    content: bytes | None = None
    raw_rows: list[dict[str, str]] = []
    digest = ""
    observed: datetime | None = None
    source_url = ""
    if unavailable:
        if any(
            row[field]
            for field in (
                "source_id",
                "source_url",
                "file_name",
                "file_sha256",
                "observed_at",
                "capture_mode",
            )
        ):
            raise ValueError("unavailable market totals must not claim a captured artifact")
        if row["review_status"] == "ACCEPTED":
            raise ValueError("unavailable market totals must not claim accepted evidence")
    else:
        _identifier(row["source_id"], "market_totals.source_id")
        source_url = https_url(row["source_url"], "market_totals.source_url")
        file_name = _file_name(row["file_name"], "market_totals.file_name")
        digest = require_sha256(row["file_sha256"], "market_totals.file_sha256")
        observed = parse_aware(row["observed_at"], "market_totals.observed_at")
        if observed > imported_at:
            raise ValueError("market_totals.observed_at is after imported_at")
        _identifier(row["captured_by"], "market_totals.captured_by")
        if row["review_status"] != "ACCEPTED":
            raise ValueError("captured market totals are not accepted")
        content = safe_regular_file(
            raw_directory / file_name,
            field="daily market totals artifact",
        )
        if sha256_bytes(content) != digest:
            raise ValueError("daily market totals artifact hash mismatch")
        _, raw_rows = read_csv_bytes(
            content,
            field="daily market totals artifact",
            exact_headers=RAW_DAILY_MARKET_TOTAL_HEADERS,
        )
        _validate_observed_after_session_close(
            raw_rows,
            observed_at=observed,
            context=context,
            field="daily market totals artifact",
        )
    query = _validate_query_receipt(
        row, availability=availability, actual_rows=len(raw_rows), field="market_totals"
    )
    effective, trust_receipt = (
        _source_trust(
            row,
            imported_at=imported_at,
            security_codes=context.security_codes,
            runtime_trust_registry=runtime_trust_registry,
            field="market_totals",
        )
        if not unavailable
        else (row["evidence_classification"], None)
    )
    capture = ProviderCapture(
        row={**row, "provider_id": provider_id, "source_url": source_url},
        content=content,
        raw_rows=tuple(raw_rows),
        effective_classification=effective,
        trust_receipt=trust_receipt,
    )
    receipt = {
        "provider_id": provider_id or None,
        "source_id": row["source_id"] or None,
        "source_url": source_url or None,
        "source_class": row["source_class"],
        "capture_mode": row["capture_mode"],
        "availability_status": availability,
        "scope": row["scope"],
        "board": row["board"],
        "artifact_path": (
            f"raw/market_totals/{row['file_name']}" if content is not None else None
        ),
        "artifact_sha256": digest or None,
        "observed_at": observed.isoformat() if observed else None,
        "evidence_classification": effective,
        "rights_status": row["rights_status"],
        **query,
        "runtime_trust": trust_receipt,
    }
    return capture, receipt


def _normalize_totals(
    capture: ProviderCapture,
    *,
    context: UpstreamContext,
    eod_rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, list[str], list[str]]:
    availability = capture.row["availability_status"]
    if availability == "NOT_AVAILABLE_FROM_SOURCE":
        return [], "NOT_AVAILABLE_FROM_SOURCE", [], ["MARKET_TOTALS_NOT_AVAILABLE_FROM_SOURCE"]
    if availability == "ZERO_RESULT":
        return [], "PARTIAL", [], ["MARKET_TOTALS_ZERO_RESULT"]
    errors: list[str] = []
    warnings: list[str] = []
    parsed: dict[date, dict[str, Any]] = {}
    for index, row in enumerate(capture.raw_rows):
        try:
            if any(contains_placeholder(value) for value in row.values()):
                raise ValueError("template placeholder is forbidden")
            day = parse_iso_date(row["trade_date"], f"market totals row {index}.trade_date")
            if day not in context.sessions or day in parsed:
                raise ValueError("date is not a unique official trading session")
            if row["board"] != "cash" or row["scope"] != "DECLARED_PILOT":
                raise ValueError("market total scope differs from the declared pilot")
            _integer(row["traded_security_count"], "traded_security_count")
            _integer(row["total_volume"], "total_volume")
            _decimal(row["total_value_kwd"], "total_value_kwd")
            _integer(row["total_trade_count"], "total_trade_count")
            parsed[day] = {
                "trade_date": day.isoformat(),
                "board": "cash",
                "scope": "DECLARED_PILOT",
                "currency": "KWD",
                "value_unit": "KWD",
                "traded_security_count": row["traded_security_count"],
                "total_volume": row["total_volume"],
                "total_value_kwd": row["total_value_kwd"],
                "total_trade_count": row["total_trade_count"],
                "provider_id": capture.row["provider_id"],
                "source_id": capture.row["source_id"],
                "source_url": capture.row["source_url"],
                "observed_at": parse_aware(capture.row["observed_at"], "observed_at").isoformat(),
                "raw_sha256": capture.row["file_sha256"],
                "evidence_classification": capture.effective_classification,
                "rights_status": capture.row["rights_status"],
            }
        except ValueError as exc:
            errors.append(f"MARKET_TOTAL_ROW_INVALID:{index}:{exc}")
    if availability == "AVAILABLE" and set(parsed) != set(context.sessions):
        errors.append("MARKET_TOTAL_DENOMINATOR_MISMATCH")
    elif availability == "PARTIAL" and set(parsed) != set(context.sessions):
        warnings.append("MARKET_TOTAL_DENOMINATOR_PARTIAL")

    eod_by_day: dict[date, list[dict[str, Any]]] = {}
    for row in eod_rows:
        eod_by_day.setdefault(parse_iso_date(row["trade_date"], "trade_date"), []).append(row)
    for day, total in parsed.items():
        daily = eod_by_day.get(day, [])
        traded = [
            row
            for row in daily
            if row["trading_state"] in {"TRADED", "TRADED_THEN_SUSPENDED"}
        ]
        expected_count = len(traded)
        if _integer(total["traded_security_count"], "traded_security_count") != expected_count:
            errors.append(f"MARKET_TOTAL_TRADED_COUNT_MISMATCH:{day.isoformat()}")
        if len(daily) != len(context.security_codes):
            warnings.append(f"MARKET_TOTAL_EOD_DENOMINATOR_INCOMPLETE:{day.isoformat()}")
            continue
        comparisons = (
            ("volume", "total_volume", _integer),
            ("value_traded_kwd", "total_value_kwd", _decimal),
            ("trade_count", "total_trade_count", _integer),
        )
        for row_field, total_field, parser in comparisons:
            if any(row[row_field] == "" for row in traded):
                warnings.append(
                    f"MARKET_TOTAL_FIELD_NOT_RECONCILABLE:{day.isoformat()}:{row_field}"
                )
                continue
            expected = sum((parser(row[row_field], row_field) for row in traded), start=0)
            supplied = parser(total[total_field], total_field)
            if expected != supplied:
                errors.append(
                    f"MARKET_TOTAL_MISMATCH:{day.isoformat()}:{total_field}"
                )
    status = "BLOCKED" if errors else ("PARTIAL" if warnings or availability != "AVAILABLE" else "PASS")
    return [parsed[day] for day in sorted(parsed)], status, errors, warnings


def _evaluate(
    *,
    captures: list[ProviderCapture],
    provider_receipts: list[dict[str, Any]],
    totals_capture: ProviderCapture,
    totals_receipt: dict[str, Any],
    context: UpstreamContext,
) -> Evaluation:
    normalized, quarantine, provider_errors = _normalize_providers(captures, context=context)
    expected = {(day, code) for day in context.sessions for code in context.security_codes}
    actual = {
        (parse_iso_date(row["trade_date"], "trade_date"), row["security_code"])
        for row in normalized
    }
    missing = expected - actual
    errors = list(provider_errors)
    warnings: list[str] = []
    if any(
        capture.row["evidence_classification"] == "PROVEN_REAL_EVIDENCE"
        and capture.effective_classification
        in {"LIVE_DEPENDENT", "LICENSED_FEED_DEPENDENT"}
        for capture in captures
    ):
        warnings.append("OFFICIAL_EOD_ARTIFACT_BOUND_CAPTURE_AUTHORITY_REQUIRED")
    denominator_status = "BLOCKED" if errors else ("PARTIAL" if missing else "PASS")
    if missing:
        warnings.append(f"OFFICIAL_EOD_DENOMINATOR_MISSING:{len(missing)}")
    provider_queries_complete = bool(provider_receipts) and all(
        receipt["availability_status"] == "AVAILABLE" and receipt["complete"]
        for receipt in provider_receipts
    )
    totals_query_complete = (
        totals_receipt["availability_status"] == "NOT_AVAILABLE_FROM_SOURCE"
        or (
            totals_receipt["availability_status"] == "AVAILABLE"
            and totals_receipt["complete"]
        )
    )
    query_complete = provider_queries_complete and totals_query_complete
    query_status = "BLOCKED" if errors else ("PASS" if query_complete else "PARTIAL")
    if not query_complete:
        warnings.append("OFFICIAL_EOD_QUERY_OR_PAGINATION_INCOMPLETE")
    row_classes = [row["evidence_classification"] for row in normalized]
    row_rights = [row["rights_status"] for row in normalized]
    complete_field_evidence = bool(normalized) and all(
        _COMPLETE_EOD_FIELD_GROUPS
        <= frozenset(str(row["available_official_fields"]).split("|"))
        for row in normalized
    )
    if normalized and not complete_field_evidence:
        warnings.append("OFFICIAL_EOD_COMPLETE_FIELD_SET_UNAVAILABLE")
    real_price_evidence = bool(normalized) and all(
        row["evidence_classification"] == "PROVEN_REAL_EVIDENCE"
        and row["rights_status"] == "RESEARCH_USE_AUTHORIZED"
        for row in normalized
    ) and complete_field_evidence
    price_status = (
        "BLOCKED"
        if errors
        else (
            "PASS"
            if denominator_status == "PASS" and query_status == "PASS" and real_price_evidence
            else "PARTIAL"
        )
    )
    totals_rows, totals_status, totals_errors, totals_warnings = _normalize_totals(
        totals_capture, context=context, eod_rows=normalized
    )
    errors.extend(totals_errors)
    warnings.extend(totals_warnings)
    if errors:
        denominator_status = "BLOCKED" if provider_errors else denominator_status
        if totals_errors:
            totals_status = "BLOCKED"
    all_classes = [*row_classes]
    all_rights = [*row_rights]
    if totals_capture.content is not None:
        all_classes.append(totals_capture.effective_classification)
        all_rights.append(totals_capture.row["rights_status"])
    evidence = (
        "BLOCKED"
        if errors
        else "PARTIAL"
        if missing or query_status != "PASS"
        else _classification(all_classes)
    )
    rights = _rights(all_rights)
    complete_real = (
        not errors
        and denominator_status == "PASS"
        and price_status == "PASS"
        and query_status == "PASS"
        and totals_status in {"PASS", "NOT_AVAILABLE_FROM_SOURCE"}
        and evidence == "PROVEN_REAL_EVIDENCE"
        and rights == "RESEARCH_USE_AUTHORIZED"
    )
    status = (
        "BLOCKED"
        if errors
        else "OFFICIAL_COMPLETE_EOD_READY"
        if complete_real
        else "PARTIAL"
    )
    return Evaluation(
        normalized_rows=tuple(normalized),
        totals_rows=tuple(totals_rows),
        quarantine_rows=tuple(quarantine),
        errors=tuple(sorted(set(errors))),
        warnings=tuple(sorted(set(warnings))),
        denominator_status=denominator_status,
        price_evidence_status=("BLOCKED" if provider_errors else price_status),
        market_totals_status=totals_status,
        query_and_pagination_status=query_status,
        status=status,
        evidence_classification=evidence,
        rights_status=rights,
        missing_pair_count=len(missing),
    )


def _artifact(
    *,
    path: str,
    capture: ProviderCapture,
    role: str,
) -> dict[str, Any]:
    assert capture.content is not None
    return {
        "path": path,
        "sha256": sha256_bytes(capture.content),
        "size_bytes": len(capture.content),
        "source_id": capture.row["source_id"],
        "source_url": capture.row["source_url"],
        "observed_at": parse_aware(capture.row["observed_at"], "observed_at").isoformat(),
        "capture_kind": {
            "PUBLIC_OFFICIAL_DOWNLOAD": "RAW_DOWNLOAD",
            "USER_PROVIDED_OFFICIAL_EXPORT": "USER_EXPORT",
            "LICENSED_VENDOR_EXPORT": "USER_EXPORT",
            "RECORDED_AUTHORIZED_FIXTURE": "RECORDED_AUTHORIZED_FIXTURE",
            "SYNTHETIC_GENERATED": "SYNTHETIC_GENERATED",
        }[capture.row["capture_mode"]],
        "artifact_role": role,
        "provider_id": capture.row["provider_id"],
        "evidence_classification": capture.effective_classification,
        "rights_status": capture.row["rights_status"],
    }


def _report(
    *,
    output: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    imported_at: datetime,
    context: UpstreamContext,
    evaluation: Evaluation,
    provider_receipts: list[dict[str, Any]],
    totals_receipt: dict[str, Any],
    eod_bytes: bytes,
    totals_bytes: bytes | None,
    quarantine_bytes: bytes | None,
) -> dict[str, Any]:
    eod_artifact = {
        "path": "normalized/official_daily_eod.csv",
        "sha256": sha256_bytes(eod_bytes),
        "rows": len(evaluation.normalized_rows),
    }
    totals_artifact = (
        None
        if totals_bytes is None
        else {
            "path": "normalized/daily_market_totals.csv",
            "sha256": sha256_bytes(totals_bytes),
            "rows": len(evaluation.totals_rows),
        }
    )
    quarantine_artifact = (
        None
        if quarantine_bytes is None
        else {
            "path": "quarantine/provider_disagreements.csv",
            "sha256": sha256_bytes(quarantine_bytes),
            "rows": len(evaluation.quarantine_rows),
        }
    )
    return {
        "schema_version": "1.0",
        "status": evaluation.status,
        "run_id": manifest["run_id"],
        "imported_at": imported_at.isoformat(),
        "output_root": str(output),
        "window_from": manifest["window_from"],
        "window_to": manifest["window_to"],
        "security_codes": list(context.security_codes),
        "official_session_count": len(context.sessions),
        "expected_pair_count": len(context.sessions) * len(context.security_codes),
        "normalized_row_count": len(evaluation.normalized_rows),
        "missing_pair_count": evaluation.missing_pair_count,
        "quarantine_count": len(evaluation.quarantine_rows),
        "denominator_status": evaluation.denominator_status,
        "price_evidence_status": evaluation.price_evidence_status,
        "market_totals_status": evaluation.market_totals_status,
        "query_and_pagination_status": evaluation.query_and_pagination_status,
        "evidence_classification": evaluation.evidence_classification,
        "rights_status": evaluation.rights_status,
        "official_daily_eod": eod_artifact,
        "daily_market_totals": totals_artifact,
        "quarantine": quarantine_artifact,
        "official_eod_manifest_sha256": manifest_sha256,
        "upstream": context.receipt,
        "providers": provider_receipts,
        "market_totals_receipt": totals_receipt,
        "errors": list(evaluation.errors),
        "warnings": list(evaluation.warnings),
        "claim_boundaries": {
            "recorded_fixture_is_real_evidence": False,
            "synthetic_fixture_promotes_readiness": False,
            "research_price_history_is_official_eod": False,
            "current_snapshot_backfills_history": False,
            "official_complete_eod_ready": evaluation.status == "OFFICIAL_COMPLETE_EOD_READY",
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }


def import_official_daily_eod(
    *,
    workspace_root: str | Path,
    official_foundation_root: str | Path,
    status_history_root: str | Path,
    output_root: str | Path,
    run_id: str,
    imported_at: str,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
    admission_request: BoundaryAdmissionRequest,
) -> dict[str, Any]:
    requested_output = Path(os.path.abspath(output_root))
    operation_binding = build_boundary_operation_binding(
        "import_official_eod",
        decision_at=admission_request.decision_at,
        run_id=run_id,
        imported_at=imported_at,
        runtime_trust_registry=runtime_trust_registry,
    )
    token = admit_boundary(
        admission_request,
        boundary_id="import_official_eod",
        output_root=requested_output,
        boundary_inputs={
            "workspace_root": Path(workspace_root),
            "official_foundation_root": Path(official_foundation_root),
            "status_history_root": Path(status_history_root),
        },
        operation_binding=operation_binding,
    )

    def worker(staging: Path) -> dict[str, Any]:
        report = _import_official_daily_eod_unchecked(
            workspace_root=workspace_root,
            official_foundation_root=official_foundation_root,
            status_history_root=status_history_root,
            output_root=staging,
            run_id=run_id,
            imported_at=imported_at,
            runtime_trust_registry=runtime_trust_registry,
            logical_output_root=requested_output,
        )
        token.materialize_receipt(staging)
        token.materialize_lineage(staging)
        return report

    return run_atomic_output(
        requested_output,
        worker,
        before_commit=lambda _staging: token.revalidate_before_commit(),
    )


def _import_official_daily_eod_unchecked(
    *,
    workspace_root: str | Path,
    official_foundation_root: str | Path,
    status_history_root: str | Path,
    output_root: str | Path,
    run_id: str,
    imported_at: str,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
    logical_output_root: Path | None = None,
) -> dict[str, Any]:
    workspace = require_real_directory(Path(workspace_root), field="workspace_root")
    decision_at = _validated_imported_at(imported_at)
    provisional_manifest, _ = load_strict_json_object(
        workspace / "manifests" / "official_eod_manifest.json",
        field="official EOD manifest",
    )
    start = parse_iso_date(provisional_manifest.get("window_from"), "window_from")
    end = parse_iso_date(provisional_manifest.get("window_to"), "window_to")
    context = load_eod_upstreams(
        official_foundation_root=Path(official_foundation_root),
        status_history_root=Path(status_history_root),
        window_from=start,
        window_to=end,
    )
    manifest, manifest_bytes, _, _ = _load_manifest(workspace, context=context)
    if manifest["run_id"] != run_id:
        raise ValueError("run_id does not match the official EOD manifest")
    captures, provider_receipts = _load_provider_captures(
        workspace,
        providers=manifest["providers"],
        context=context,
        imported_at=decision_at,
        runtime_trust_registry=runtime_trust_registry,
        raw_directory=workspace / "raw_exports" / "providers",
    )
    totals_capture, totals_receipt = _load_totals_capture(
        workspace,
        value=manifest["market_totals"],
        context=context,
        imported_at=decision_at,
        runtime_trust_registry=runtime_trust_registry,
        raw_directory=workspace / "raw_exports" / "market_totals",
    )
    evaluation = _evaluate(
        captures=captures,
        provider_receipts=provider_receipts,
        totals_capture=totals_capture,
        totals_receipt=totals_receipt,
        context=context,
    )

    output = prepare_output_root(Path(output_root), label="official EOD output")
    raw_providers = output / "raw" / "providers"
    raw_totals = output / "raw" / "market_totals"
    normalized_dir = output / "normalized"
    reports_dir = output / "reports"
    quarantine_dir = output / "quarantine"
    for directory in (raw_providers, raw_totals, normalized_dir, reports_dir, quarantine_dir):
        directory.mkdir(parents=True, exist_ok=False)
    artifacts: list[dict[str, Any]] = []
    for capture in captures:
        if capture.content is None:
            continue
        target = raw_providers / capture.row["file_name"]
        target.write_bytes(capture.content)
        artifacts.append(
            _artifact(
                path=target.relative_to(output).as_posix(),
                capture=capture,
                role="OFFICIAL_DAILY_EOD_PROVIDER_EXPORT",
            )
        )
    if totals_capture.content is not None:
        target = raw_totals / totals_capture.row["file_name"]
        target.write_bytes(totals_capture.content)
        artifacts.append(
            _artifact(
                path=target.relative_to(output).as_posix(),
                capture=totals_capture,
                role="DAILY_MARKET_TOTALS_EXPORT",
            )
        )
    evidence_manifest = {
        "schema_version": "3.0",
        "artifacts": sorted(artifacts, key=lambda item: (item["path"], item["sha256"])),
    }
    (output / "manifest.json").write_bytes(canonical_json_bytes(evidence_manifest))
    (output / "official_eod_manifest.json").write_bytes(manifest_bytes)
    eod_path = normalized_dir / "official_daily_eod.csv"
    write_csv(eod_path, headers=OFFICIAL_DAILY_EOD_HEADERS, rows=evaluation.normalized_rows)
    eod_bytes = safe_regular_file(eod_path, field="normalized official_daily_eod.csv")
    totals_bytes: bytes | None = None
    if totals_capture.content is not None:
        totals_path = normalized_dir / "daily_market_totals.csv"
        write_csv(
            totals_path,
            headers=DAILY_MARKET_TOTALS_HEADERS,
            rows=evaluation.totals_rows,
        )
        totals_bytes = safe_regular_file(totals_path, field="normalized daily_market_totals.csv")
    quarantine_bytes: bytes | None = None
    if evaluation.quarantine_rows:
        quarantine_path = quarantine_dir / "provider_disagreements.csv"
        write_csv(
            quarantine_path,
            headers=QUARANTINE_HEADERS,
            rows=evaluation.quarantine_rows,
        )
        quarantine_bytes = safe_regular_file(
            quarantine_path, field="official EOD quarantine ledger"
        )
    report = _report(
        output=(
            Path(os.path.abspath(logical_output_root))
            if logical_output_root is not None
            else output
        ),
        manifest=manifest,
        manifest_sha256=sha256_bytes(manifest_bytes),
        imported_at=decision_at,
        context=context,
        evaluation=evaluation,
        provider_receipts=provider_receipts,
        totals_receipt=totals_receipt,
        eod_bytes=eod_bytes,
        totals_bytes=totals_bytes,
        quarantine_bytes=quarantine_bytes,
    )
    (reports_dir / "official_eod_import_report.json").write_bytes(
        canonical_json_bytes(report)
    )
    return report


def _verify_output_manifest(root: Path) -> tuple[dict[str, Any], frozenset[str]]:
    manifest, _ = load_strict_json_object(root / "manifest.json", field="official EOD evidence manifest")
    if set(manifest) != {"schema_version", "artifacts"} or manifest["schema_version"] != "3.0":
        raise ValueError("official EOD evidence manifest contract mismatch")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list):
        raise ValueError("official EOD evidence manifest artifacts must be an array")
    expected_fields = {
        "path",
        "sha256",
        "size_bytes",
        "source_id",
        "source_url",
        "observed_at",
        "capture_kind",
        "artifact_role",
        "provider_id",
        "evidence_classification",
        "rights_status",
    }
    hashes: set[str] = set()
    seen: set[str] = set()
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise ValueError(f"official EOD evidence artifact {index} contract mismatch")
        path = Path(str(row["path"]))
        if path.is_absolute() or ".." in path.parts or path.as_posix() in seen:
            raise ValueError("official EOD evidence artifact path is unsafe or duplicated")
        seen.add(path.as_posix())
        content = safe_regular_file(root / path, field=f"official EOD artifact {path.as_posix()}")
        digest = require_sha256(row["sha256"], f"artifacts[{index}].sha256")
        if sha256_bytes(content) != digest or nonnegative_int(row["size_bytes"], "size_bytes") != len(content):
            raise ValueError(f"official EOD evidence artifact integrity mismatch: {path.as_posix()}")
        if row["evidence_classification"] not in EVIDENCE_CLASSIFICATIONS or row["rights_status"] not in RIGHTS_STATUSES:
            raise ValueError("official EOD evidence artifact classification is invalid")
        hashes.add(digest)
    return manifest, frozenset(hashes)


def validate_official_eod_output(
    *,
    official_eod_root: str | Path,
    official_foundation_root: str | Path,
    status_history_root: str | Path,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    root = require_real_directory(Path(official_eod_root), field="official_eod_root")
    saved_report, _ = load_strict_json_object(
        root / "reports" / "official_eod_import_report.json",
        field="official EOD import report",
    )
    start = parse_iso_date(saved_report.get("window_from"), "window_from")
    end = parse_iso_date(saved_report.get("window_to"), "window_to")
    imported_at = _validated_imported_at(saved_report.get("imported_at"))
    context = load_eod_upstreams(
        official_foundation_root=Path(official_foundation_root),
        status_history_root=Path(status_history_root),
        window_from=start,
        window_to=end,
    )
    preserved_manifest, preserved_bytes = load_strict_json_object(
        root / "official_eod_manifest.json",
        field="preserved official EOD manifest",
    )
    if _exact_object(preserved_manifest, _MANIFEST_FIELDS, "preserved official EOD manifest")["upstream"] != context.receipt:
        raise ValueError("official EOD output is bound to stale or substituted upstreams")
    if sha256_bytes(preserved_bytes) != saved_report.get("official_eod_manifest_sha256"):
        raise ValueError("preserved official EOD manifest hash differs from the report")
    saved_evidence_manifest, _ = _verify_output_manifest(root)
    captures, provider_receipts = _load_provider_captures(
        root,
        providers=preserved_manifest["providers"],
        context=context,
        imported_at=imported_at,
        runtime_trust_registry=runtime_trust_registry,
        raw_directory=root / "raw" / "providers",
    )
    totals_capture, totals_receipt = _load_totals_capture(
        root,
        value=preserved_manifest["market_totals"],
        context=context,
        imported_at=imported_at,
        runtime_trust_registry=runtime_trust_registry,
        raw_directory=root / "raw" / "market_totals",
    )
    evaluation = _evaluate(
        captures=captures,
        provider_receipts=provider_receipts,
        totals_capture=totals_capture,
        totals_receipt=totals_receipt,
        context=context,
    )
    errors: list[str] = []
    expected_artifacts = [
        _artifact(
            path=f"raw/providers/{capture.row['file_name']}",
            capture=capture,
            role="OFFICIAL_DAILY_EOD_PROVIDER_EXPORT",
        )
        for capture in captures
        if capture.content is not None
    ]
    if totals_capture.content is not None:
        expected_artifacts.append(
            _artifact(
                path=f"raw/market_totals/{totals_capture.row['file_name']}",
                capture=totals_capture,
                role="DAILY_MARKET_TOTALS_EXPORT",
            )
        )
    expected_evidence_manifest = {
        "schema_version": "3.0",
        "artifacts": sorted(
            expected_artifacts, key=lambda item: (item["path"], item["sha256"])
        ),
    }
    if saved_evidence_manifest != expected_evidence_manifest:
        errors.append("OFFICIAL_EOD_EVIDENCE_MANIFEST_DIFFERS_FROM_RECOMPUTATION")
    eod_bytes = safe_regular_file(
        root / "normalized" / "official_daily_eod.csv",
        field="normalized official_daily_eod.csv",
    )
    _, actual_eod = read_csv_bytes(
        eod_bytes,
        field="normalized official_daily_eod.csv",
        exact_headers=OFFICIAL_DAILY_EOD_HEADERS,
    )
    expected_eod = [
        {header: str(row.get(header, "")) for header in OFFICIAL_DAILY_EOD_HEADERS}
        for row in evaluation.normalized_rows
    ]
    if actual_eod != expected_eod:
        errors.append("NORMALIZED_OFFICIAL_EOD_DIFFERS_FROM_RECOMPUTATION")
    report_eod = saved_report.get("official_daily_eod")
    if not isinstance(report_eod, dict) or report_eod.get("sha256") != sha256_bytes(eod_bytes) or report_eod.get("rows") != len(actual_eod):
        errors.append("OFFICIAL_EOD_REPORT_RECEIPT_MISMATCH")
    totals_bytes: bytes | None = None
    totals_path = root / "normalized" / "daily_market_totals.csv"
    if totals_capture.content is not None:
        totals_bytes = safe_regular_file(totals_path, field="normalized daily_market_totals.csv")
        _, actual_totals = read_csv_bytes(
            totals_bytes,
            field="normalized daily_market_totals.csv",
            exact_headers=DAILY_MARKET_TOTALS_HEADERS,
        )
        expected_totals = [
            {header: str(row.get(header, "")) for header in DAILY_MARKET_TOTALS_HEADERS}
            for row in evaluation.totals_rows
        ]
        if actual_totals != expected_totals:
            errors.append("NORMALIZED_MARKET_TOTALS_DIFFERS_FROM_RECOMPUTATION")
        report_totals = saved_report.get("daily_market_totals")
        if not isinstance(report_totals, dict) or report_totals.get("sha256") != sha256_bytes(totals_bytes) or report_totals.get("rows") != len(actual_totals):
            errors.append("MARKET_TOTALS_REPORT_RECEIPT_MISMATCH")
    elif totals_path.exists() or saved_report.get("daily_market_totals") is not None:
        errors.append("UNDECLARED_MARKET_TOTALS_OUTPUT")
    quarantine_path = root / "quarantine" / "provider_disagreements.csv"
    quarantine_bytes: bytes | None = None
    if evaluation.quarantine_rows:
        quarantine_bytes = safe_regular_file(
            quarantine_path, field="official EOD quarantine ledger"
        )
        _, actual_quarantine = read_csv_bytes(
            quarantine_bytes,
            field="official EOD quarantine ledger",
            exact_headers=QUARANTINE_HEADERS,
        )
        expected_quarantine = [
            {header: str(row.get(header, "")) for header in QUARANTINE_HEADERS}
            for row in evaluation.quarantine_rows
        ]
        if actual_quarantine != expected_quarantine:
            errors.append("OFFICIAL_EOD_QUARANTINE_DIFFERS_FROM_RECOMPUTATION")
        report_quarantine = saved_report.get("quarantine")
        if (
            not isinstance(report_quarantine, dict)
            or report_quarantine.get("sha256") != sha256_bytes(quarantine_bytes)
            or report_quarantine.get("rows") != len(actual_quarantine)
        ):
            errors.append("OFFICIAL_EOD_QUARANTINE_REPORT_RECEIPT_MISMATCH")
    elif quarantine_path.exists() or saved_report.get("quarantine") is not None:
        errors.append("UNDECLARED_OFFICIAL_EOD_QUARANTINE")
    expected_saved_report = _report(
        output=root,
        manifest=preserved_manifest,
        manifest_sha256=sha256_bytes(preserved_bytes),
        imported_at=imported_at,
        context=context,
        evaluation=evaluation,
        provider_receipts=provider_receipts,
        totals_receipt=totals_receipt,
        eod_bytes=eod_bytes,
        totals_bytes=totals_bytes,
        quarantine_bytes=quarantine_bytes,
    )
    if saved_report != expected_saved_report:
        errors.append("OFFICIAL_EOD_SAVED_REPORT_CONTRACT_OR_RECEIPT_MISMATCH")
    critical_saved = {
        "status": saved_report.get("status"),
        "denominator_status": saved_report.get("denominator_status"),
        "price_evidence_status": saved_report.get("price_evidence_status"),
        "market_totals_status": saved_report.get("market_totals_status"),
        "query_and_pagination_status": saved_report.get("query_and_pagination_status"),
        "expected_pair_count": saved_report.get("expected_pair_count"),
        "normalized_row_count": saved_report.get("normalized_row_count"),
        "missing_pair_count": saved_report.get("missing_pair_count"),
        "evidence_classification": saved_report.get("evidence_classification"),
        "rights_status": saved_report.get("rights_status"),
        "upstream": saved_report.get("upstream"),
        "providers": saved_report.get("providers"),
        "market_totals_receipt": saved_report.get("market_totals_receipt"),
        "security_codes": saved_report.get("security_codes"),
        "official_session_count": saved_report.get("official_session_count"),
        "quarantine_count": saved_report.get("quarantine_count"),
        "errors": saved_report.get("errors"),
        "warnings": saved_report.get("warnings"),
        "claim_boundaries": saved_report.get("claim_boundaries"),
    }
    critical_recomputed = {
        "status": evaluation.status,
        "denominator_status": evaluation.denominator_status,
        "price_evidence_status": evaluation.price_evidence_status,
        "market_totals_status": evaluation.market_totals_status,
        "query_and_pagination_status": evaluation.query_and_pagination_status,
        "expected_pair_count": len(context.sessions) * len(context.security_codes),
        "normalized_row_count": len(evaluation.normalized_rows),
        "missing_pair_count": evaluation.missing_pair_count,
        "evidence_classification": evaluation.evidence_classification,
        "rights_status": evaluation.rights_status,
        "upstream": context.receipt,
        "providers": provider_receipts,
        "market_totals_receipt": totals_receipt,
        "security_codes": list(context.security_codes),
        "official_session_count": len(context.sessions),
        "quarantine_count": len(evaluation.quarantine_rows),
        "errors": list(evaluation.errors),
        "warnings": list(evaluation.warnings),
        "claim_boundaries": {
            "recorded_fixture_is_real_evidence": False,
            "synthetic_fixture_promotes_readiness": False,
            "research_price_history_is_official_eod": False,
            "current_snapshot_backfills_history": False,
            "official_complete_eod_ready": evaluation.status
            == "OFFICIAL_COMPLETE_EOD_READY",
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }
    if critical_saved != critical_recomputed:
        errors.append("OFFICIAL_EOD_REPORT_DIFFERS_FROM_RECOMPUTATION")
    return {
        "schema_version": "1.0",
        "validation_status": "BLOCKED" if errors else "PASS",
        **critical_recomputed,
        "errors": sorted(set([*errors, *evaluation.errors])),
        "warnings": list(evaluation.warnings),
        "claim_boundaries": {
            "saved_report_was_trusted_without_recomputation": False,
            "raw_artifacts_rehashed": True,
            "normalized_outputs_recomputed": True,
            "upstream_receipts_rehashed": True,
            "data_foundation_ready": False,
            "backtest_ready": False,
        },
    }


__all__ = [
    "DAILY_MARKET_TOTALS_HEADERS",
    "OFFICIAL_DAILY_EOD_HEADERS",
    "QUARANTINE_HEADERS",
    "import_official_daily_eod",
    "validate_official_eod_output",
]
