from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .hashing import canonical_json_bytes, hash_json
from .source_evidence_lifecycle import load_source_evidence_document
from .strict import https_url, parse_aware, parse_iso_date, require_sha256


UNIVERSE_SCHEMA_VERSION = "issuer-universe-v1"
DOSSIER_SCHEMA_VERSION = "company-dossier-v1"
REPORT_SCHEMA_VERSION = "company-dossier-validation-report-v1"

EVIDENCE_CLASSES = frozenset(
    {"SYNTHETIC_FIXTURE", "RECORDED_AUTHORIZED_FIXTURE", "PROVEN_REAL_EVIDENCE"}
)
CAPTURE_MODES = frozenset({"PROSPECTIVE", "HISTORICAL_POINT_IN_TIME"})
UNIVERSE_STATUSES = frozenset({"EXACT", "PARTIAL"})
SOURCE_GRADES = frozenset({"A", "B", "C", "D"})
FACT_STATUSES = frozenset({"confirmed", "unverified", "inferred"})
EVIDENCE_ROLES = frozenset(
    {
        "EXCHANGE_OFFICIAL",
        "REGULATOR_OFFICIAL",
        "CLEARING_OFFICIAL",
        "ISSUER_PRIMARY",
        "FINANCIAL_CONTEXT",
        "NEWS_CONTEXT",
        "SOCIAL_CONTEXT_LEAD_ONLY",
        "ROUTING_ONLY",
    }
)
PRIMARY_FACT_ROLES = frozenset(
    {
        "EXCHANGE_OFFICIAL",
        "REGULATOR_OFFICIAL",
        "CLEARING_OFFICIAL",
        "ISSUER_PRIMARY",
    }
)
RIGHTS_STATUSES = frozenset({"PERMITTED", "USER_AUTHORIZED"})
ROBOTS_STATUSES = frozenset({"ALLOWED", "NOT_APPLICABLE"})
AVAILABILITY_STATUSES = frozenset({"CAPTURED_BEFORE_CUTOFF", "VERIFIED_ARCHIVE"})
LISTING_STATUSES = frozenset(
    {"ACTIVE", "LISTED", "TRADING", "SUSPENDED", "HALTED", "DELISTED"}
)
GAP_REASONS = frozenset(
    {
        "SOURCE_UNAVAILABLE",
        "NOT_DISCLOSED",
        "RIGHTS_BLOCKED",
        "PARSER_DRIFT",
        "OUTSIDE_POINT_IN_TIME",
        "NOT_APPLICABLE",
        "UNRESOLVED_CONFLICT",
        "NOT_COLLECTED",
    }
)
ACCESS_STATUSES = frozenset(
    {
        "AVAILABLE",
        "EMPTY",
        "BLOCKED_ACCESS",
        "ROBOTS_DENIED",
        "PAYWALL",
        "RATE_LIMITED",
        "NETWORK_ERROR",
        "PARSER_DRIFT",
        "NOT_CHECKED",
    }
)
SECTION_NAMES = (
    "basic",
    "business",
    "financials",
    "market",
    "disclosures",
    "corporate_actions",
    "governance_ownership",
    "risks",
)
REQUIRED_EXPECTED_FIELDS: Mapping[str, frozenset[str]] = {
    "basic": frozenset(
        {"legal_name_ar", "legal_name_en", "listing_status", "official_registration_id"}
    ),
    "business": frozenset({"sector", "primary_activity"}),
    "financials": frozenset(
        {"reporting_period", "revenue", "net_profit_loss", "total_assets", "total_equity"}
    ),
    "market": frozenset(
        {"reference_price", "reference_price_at", "liquidity", "volatility"}
    ),
    "disclosures": frozenset({"latest_material_disclosure"}),
    "corporate_actions": frozenset({"dividend_history", "capital_action_history"}),
    "governance_ownership": frozenset({"management_coverage", "ownership_coverage"}),
    "risks": frozenset({"principal_risks"}),
}
REQUIRED_CRITICAL_FIELDS: Mapping[str, frozenset[str]] = {
    "basic": frozenset({"legal_name_ar", "legal_name_en", "listing_status"}),
    "business": frozenset({"sector", "primary_activity"}),
    "financials": frozenset({"reporting_period"}),
    "market": frozenset({"reference_price", "reference_price_at"}),
    "disclosures": frozenset(),
    "corporate_actions": frozenset(),
    "governance_ownership": frozenset(),
    "risks": frozenset({"principal_risks"}),
}

UNIVERSE_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_class",
        "capture_mode",
        "market",
        "jurisdiction",
        "currency",
        "as_of",
        "universe_status",
        "expected_security_codes",
        "membership_evidence_id",
        "evidence",
        "issuers",
    }
)
EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "source_id",
        "publisher",
        "source_url",
        "published_at",
        "event_at",
        "missing_date_fields",
        "available_at",
        "accessed_at",
        "availability_evidence_status",
        "raw_sha256",
        "reconciliation_report_sha256",
        "fact_status",
        "source_grade",
        "evidence_role",
        "rights_status",
        "robots_status",
    }
)
ISSUER_FIELDS = frozenset(
    {
        "issuer_id",
        "official_registration_id",
        "legal_name_ar",
        "legal_name_en",
        "security_identities",
        "evidence_ids",
        "identity_gaps",
    }
)
IDENTITY_FIELDS = frozenset(
    {
        "security_code",
        "ticker",
        "isin",
        "board",
        "market_segment",
        "currency",
        "valid_from",
        "valid_to",
        "listing_status",
        "evidence_ids",
    }
)
IDENTITY_GAP_FIELDS = frozenset({"field_name", "reason_code", "detail"})
DOSSIER_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_class",
        "capture_mode",
        "as_of",
        "last_updated_at",
        "issuer_id",
        "security_codes",
        "evidence",
        "sections",
        "source_quality",
        "data_gaps",
        "claim_boundaries",
    }
)
SECTION_FIELDS = frozenset({"expected_fields", "critical_fields", "facts"})
FACT_FIELDS = frozenset(
    {
        "field_name",
        "value",
        "unit",
        "effective_at",
        "published_at",
        "available_at",
        "fact_status",
        "evidence_ids",
        "missing_reason",
    }
)
GAP_FIELDS = frozenset(
    {"section", "field_name", "reason_code", "detail", "last_attempted_at", "source_ids"}
)
SOURCE_QUALITY_FIELDS = frozenset(
    {
        "source_id",
        "publisher",
        "source_url",
        "source_grade",
        "rights_status",
        "robots_status",
        "access_status",
        "expected_fields",
        "resolved_fields",
        "last_checked_at",
        "limitations",
    }
)
CLAIM_BOUNDARY_FIELDS = frozenset(
    {
        "real_collection_complete",
        "company_universe_complete",
        "training_permitted",
        "backtest_permitted",
        "recommendation_permitted",
        "financial_execution_permitted",
    }
)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
SECURITY_CODE_RE = re.compile(r"^[0-9]+$")
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,127}$")


class CompanyDossierError(ValueError):
    """Raised when an issuer-universe or company-dossier contract is invalid."""


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CompanyDossierError(f"{label} must be an object")
    actual = set(value)
    if actual != fields:
        raise CompanyDossierError(
            f"{label} fields differ: missing_count={len(fields - actual)} "
            f"extra_count={len(actual - fields)}"
        )
    return dict(value)


def _text(value: Any, label: str, *, maximum: int = 65_536) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\x00" in value
        or len(value) > maximum
    ):
        raise CompanyDossierError(f"{label} must be a bounded trimmed string")
    return value


def _optional_text(value: Any, label: str, *, maximum: int = 65_536) -> str | None:
    if value is None:
        return None
    return _text(value, label, maximum=maximum)


def _enum(value: Any, allowed: Iterable[str], label: str) -> str:
    result = _text(value, label)
    if result not in allowed:
        raise CompanyDossierError(f"{label} has an unsupported value")
    return result


def _aware(value: Any, label: str) -> datetime:
    try:
        return parse_aware(value, label)
    except ValueError as exc:
        raise CompanyDossierError(str(exc)) from exc


def _optional_aware(value: Any, label: str) -> datetime | None:
    return None if value is None else _aware(value, label)


def _day(value: Any, label: str) -> date:
    try:
        return parse_iso_date(value, label)
    except ValueError as exc:
        raise CompanyDossierError(str(exc)) from exc


def _optional_day(value: Any, label: str) -> date | None:
    return None if value is None else _day(value, label)


def _hash(value: Any, label: str) -> str:
    try:
        return require_sha256(value, label)
    except ValueError as exc:
        raise CompanyDossierError(str(exc)) from exc


def _url(value: Any, label: str) -> str:
    try:
        return https_url(value, label)
    except ValueError as exc:
        raise CompanyDossierError(str(exc)) from exc


def _string_list(
    value: Any,
    label: str,
    *,
    allow_empty: bool,
    pattern: re.Pattern[str] | None = None,
) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise CompanyDossierError(f"{label} must be a list with the required cardinality")
    result = [_text(item, f"{label}[]", maximum=512) for item in value]
    if len(result) != len(set(result)):
        raise CompanyDossierError(f"{label} contains duplicates")
    if pattern is not None and any(pattern.fullmatch(item) is None for item in result):
        raise CompanyDossierError(f"{label} contains an invalid identifier")
    return result


def _finite_scalar(value: Any, label: str) -> str | int | float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _text(value, label)
    if type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise CompanyDossierError(f"{label} must be a finite scalar")


def _overlap(
    start_a: date,
    end_a: date | None,
    start_b: date,
    end_b: date | None,
) -> bool:
    return start_a <= (end_b or date.max) and start_b <= (end_a or date.max)


def _validate_evidence(
    value: Any,
    *,
    capture_mode: str,
    as_of: datetime,
    label: str,
) -> dict[str, Any]:
    row = _exact(value, EVIDENCE_FIELDS, label)
    for field in ("evidence_id", "source_id", "publisher"):
        row[field] = _text(row[field], f"{label}.{field}", maximum=512)
    row["source_url"] = _url(row["source_url"], f"{label}.source_url")
    missing_dates = _string_list(
        row["missing_date_fields"],
        f"{label}.missing_date_fields",
        allow_empty=True,
    )
    if any(item not in {"published_at", "event_at"} for item in missing_dates):
        raise CompanyDossierError(f"{label}.missing_date_fields is invalid")
    published = _optional_aware(row["published_at"], f"{label}.published_at")
    event_at = _optional_aware(row["event_at"], f"{label}.event_at")
    actual_missing = {
        field
        for field, parsed in (("published_at", published), ("event_at", event_at))
        if parsed is None
    }
    if actual_missing != set(missing_dates):
        raise CompanyDossierError(f"{label} date gaps are not explicit")
    available = _aware(row["available_at"], f"{label}.available_at")
    accessed = _aware(row["accessed_at"], f"{label}.accessed_at")
    if published is not None and available < published:
        raise CompanyDossierError(f"{label}.available_at precedes published_at")
    if accessed < available:
        raise CompanyDossierError(f"{label}.accessed_at precedes available_at")
    if available > as_of or (event_at is not None and event_at > as_of):
        raise CompanyDossierError(f"{label} contains post-cutoff evidence")
    availability_status = _enum(
        row["availability_evidence_status"],
        AVAILABILITY_STATUSES,
        f"{label}.availability_evidence_status",
    )
    if capture_mode == "PROSPECTIVE":
        if accessed > as_of or availability_status != "CAPTURED_BEFORE_CUTOFF":
            raise CompanyDossierError(f"{label} violates prospective point-in-time capture")
    elif accessed > as_of and availability_status != "VERIFIED_ARCHIVE":
        raise CompanyDossierError(f"{label} late retrieval requires VERIFIED_ARCHIVE")

    row["raw_sha256"] = _hash(row["raw_sha256"], f"{label}.raw_sha256")
    row["reconciliation_report_sha256"] = _hash(
        row["reconciliation_report_sha256"],
        f"{label}.reconciliation_report_sha256",
    )
    row["fact_status"] = _enum(row["fact_status"], FACT_STATUSES, f"{label}.fact_status")
    row["source_grade"] = _enum(
        row["source_grade"], SOURCE_GRADES, f"{label}.source_grade"
    )
    row["evidence_role"] = _enum(
        row["evidence_role"], EVIDENCE_ROLES, f"{label}.evidence_role"
    )
    row["rights_status"] = _enum(
        row["rights_status"], RIGHTS_STATUSES, f"{label}.rights_status"
    )
    row["robots_status"] = _enum(
        row["robots_status"], ROBOTS_STATUSES, f"{label}.robots_status"
    )
    if availability_status == "VERIFIED_ARCHIVE" and (
        row["fact_status"] != "confirmed" or row["source_grade"] not in {"A", "B"}
    ):
        raise CompanyDossierError(
            f"{label} VERIFIED_ARCHIVE requires confirmed grade A/B evidence"
        )
    row["published_at"] = None if published is None else published.isoformat()
    row["event_at"] = None if event_at is None else event_at.isoformat()
    row["missing_date_fields"] = sorted(missing_dates)
    row["available_at"] = available.isoformat()
    row["accessed_at"] = accessed.isoformat()
    row["availability_evidence_status"] = availability_status
    row["_available"] = available
    row["_accessed"] = accessed
    return row


def _official_identity_evidence(rows: Iterable[Mapping[str, Any]]) -> bool:
    return any(
        row["fact_status"] == "confirmed"
        and row["source_grade"] in {"A", "B"}
        and row["evidence_role"] in PRIMARY_FACT_ROLES
        for row in rows
    )


def validate_issuer_universe(document: Any) -> dict[str, Any]:
    root = _exact(document, UNIVERSE_FIELDS, "issuer universe")
    if root["schema_version"] != UNIVERSE_SCHEMA_VERSION:
        raise CompanyDossierError("unsupported issuer-universe schema_version")
    evidence_class = _enum(root["evidence_class"], EVIDENCE_CLASSES, "evidence_class")
    capture_mode = _enum(root["capture_mode"], CAPTURE_MODES, "capture_mode")
    if root["market"] != "BOURSA_KUWAIT" or root["jurisdiction"] != "KW":
        raise CompanyDossierError("issuer universe must remain Kuwait-only")
    if root["currency"] != "KWD":
        raise CompanyDossierError("issuer universe currency must be KWD")
    as_of = _aware(root["as_of"], "issuer universe.as_of")
    universe_status = _enum(
        root["universe_status"], UNIVERSE_STATUSES, "universe_status"
    )
    expected_codes = _string_list(
        root["expected_security_codes"],
        "expected_security_codes",
        allow_empty=False,
        pattern=SECURITY_CODE_RE,
    )
    if not isinstance(root["evidence"], list) or not root["evidence"]:
        raise CompanyDossierError("issuer universe evidence must be a non-empty list")
    evidence: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(root["evidence"]):
        row = _validate_evidence(
            raw,
            capture_mode=capture_mode,
            as_of=as_of,
            label=f"issuer universe.evidence[{index}]",
        )
        if row["evidence_id"] in evidence:
            raise CompanyDossierError("issuer universe contains duplicate evidence_id")
        evidence[row["evidence_id"]] = row
    membership_id = _text(
        root["membership_evidence_id"], "membership_evidence_id", maximum=512
    )
    if membership_id not in evidence or not _official_identity_evidence([evidence[membership_id]]):
        raise CompanyDossierError("membership evidence must be confirmed official evidence")
    if not isinstance(root["issuers"], list) or not root["issuers"]:
        raise CompanyDossierError("issuer universe issuers must be a non-empty list")

    issuers: dict[str, dict[str, Any]] = {}
    all_identities: list[dict[str, Any]] = []
    used_evidence_ids = {membership_id}
    for issuer_index, raw_issuer in enumerate(root["issuers"]):
        issuer = _exact(raw_issuer, ISSUER_FIELDS, f"issuer[{issuer_index}]")
        issuer_id = _text(issuer["issuer_id"], "issuer.issuer_id", maximum=256)
        if issuer_id in issuers:
            raise CompanyDossierError("issuer universe contains duplicate issuer_id")
        issuer["official_registration_id"] = _optional_text(
            issuer["official_registration_id"],
            "issuer.official_registration_id",
            maximum=256,
        )
        issuer["legal_name_ar"] = _text(issuer["legal_name_ar"], "issuer.legal_name_ar")
        issuer["legal_name_en"] = _text(issuer["legal_name_en"], "issuer.legal_name_en")
        issuer_evidence_ids = _string_list(
            issuer["evidence_ids"], "issuer.evidence_ids", allow_empty=False
        )
        if any(item not in evidence for item in issuer_evidence_ids):
            raise CompanyDossierError("issuer references unknown evidence")
        if not _official_identity_evidence(evidence[item] for item in issuer_evidence_ids):
            raise CompanyDossierError("issuer identity lacks confirmed official evidence")
        used_evidence_ids.update(issuer_evidence_ids)

        if not isinstance(issuer["identity_gaps"], list):
            raise CompanyDossierError("issuer.identity_gaps must be a list")
        gaps: dict[str, dict[str, Any]] = {}
        for gap_index, raw_gap in enumerate(issuer["identity_gaps"]):
            gap = _exact(
                raw_gap,
                IDENTITY_GAP_FIELDS,
                f"issuer.identity_gaps[{gap_index}]",
            )
            field_name = _enum(
                gap["field_name"],
                {"official_registration_id"},
                "issuer identity gap.field_name",
            )
            gap["reason_code"] = _enum(
                gap["reason_code"], GAP_REASONS, "issuer identity gap.reason_code"
            )
            gap["detail"] = _text(gap["detail"], "issuer identity gap.detail")
            if field_name in gaps:
                raise CompanyDossierError("issuer contains duplicate identity gap")
            gaps[field_name] = gap
        registration_missing = issuer["official_registration_id"] is None
        if registration_missing != ("official_registration_id" in gaps):
            raise CompanyDossierError("issuer registration gap is not explicit")

        if not isinstance(issuer["security_identities"], list) or not issuer["security_identities"]:
            raise CompanyDossierError("issuer requires security identities")
        identities: list[dict[str, Any]] = []
        for identity_index, raw_identity in enumerate(issuer["security_identities"]):
            identity = _exact(
                raw_identity,
                IDENTITY_FIELDS,
                f"issuer.security_identities[{identity_index}]",
            )
            code = _text(identity["security_code"], "identity.security_code", maximum=64)
            if SECURITY_CODE_RE.fullmatch(code) is None:
                raise CompanyDossierError("identity.security_code is invalid")
            identity["security_code"] = code
            identity["ticker"] = _text(identity["ticker"], "identity.ticker", maximum=64).upper()
            isin = _optional_text(identity["isin"], "identity.isin", maximum=32)
            if isin is not None:
                isin = isin.upper()
                if ISIN_RE.fullmatch(isin) is None:
                    raise CompanyDossierError("identity.isin is invalid")
            identity["isin"] = isin
            identity["board"] = _enum(identity["board"], {"cash"}, "identity.board")
            identity["market_segment"] = _text(
                identity["market_segment"], "identity.market_segment", maximum=128
            )
            if identity["currency"] != "KWD":
                raise CompanyDossierError("identity.currency must be KWD")
            start = _day(identity["valid_from"], "identity.valid_from")
            end = _optional_day(identity["valid_to"], "identity.valid_to")
            if end is not None and end < start:
                raise CompanyDossierError("identity interval is reversed")
            identity["listing_status"] = _enum(
                identity["listing_status"], LISTING_STATUSES, "identity.listing_status"
            )
            identity_evidence_ids = _string_list(
                identity["evidence_ids"], "identity.evidence_ids", allow_empty=False
            )
            if any(item not in evidence for item in identity_evidence_ids):
                raise CompanyDossierError("security identity references unknown evidence")
            if not _official_identity_evidence(
                evidence[item] for item in identity_evidence_ids
            ):
                raise CompanyDossierError("security identity lacks confirmed official evidence")
            used_evidence_ids.update(identity_evidence_ids)
            identity["valid_from"] = start.isoformat()
            identity["valid_to"] = None if end is None else end.isoformat()
            identity["evidence_ids"] = sorted(identity_evidence_ids)
            identity["_start"] = start
            identity["_end"] = end
            identity["_issuer_id"] = issuer_id
            identities.append(identity)
            all_identities.append(identity)
        issuer["evidence_ids"] = sorted(issuer_evidence_ids)
        issuer["identity_gaps"] = list(gaps.values())
        issuer["security_identities"] = identities
        issuers[issuer_id] = issuer

    by_code_board: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for identity in all_identities:
        by_code_board[(identity["security_code"], identity["board"])].append(identity)
    for rows in by_code_board.values():
        ordered = sorted(rows, key=lambda item: item["_start"])
        for previous, current in zip(ordered, ordered[1:]):
            if _overlap(previous["_start"], previous["_end"], current["_start"], current["_end"]):
                raise CompanyDossierError("security identity intervals overlap")

    for index, left in enumerate(all_identities):
        for right in all_identities[index + 1 :]:
            if left["board"] != right["board"] or not _overlap(
                left["_start"], left["_end"], right["_start"], right["_end"]
            ):
                continue
            if (
                left["isin"] is not None
                and left["isin"] == right["isin"]
                and left["security_code"] != right["security_code"]
            ):
                raise CompanyDossierError("overlapping identities contain an ISIN collision")
            if (
                left["ticker"] == right["ticker"]
                and left["security_code"] != right["security_code"]
            ):
                raise CompanyDossierError("overlapping identities contain a ticker collision")

    active_identities = [
        row
        for row in all_identities
        if row["_start"] <= as_of.date()
        and (row["_end"] is None or as_of.date() <= row["_end"])
        and row["listing_status"] != "DELISTED"
    ]
    active_codes = {row["security_code"] for row in active_identities}
    if len(active_codes) != len(active_identities):
        raise CompanyDossierError("active security identity is ambiguous")
    missing_codes = sorted(set(expected_codes) - active_codes)
    extra_codes = sorted(active_codes - set(expected_codes))
    if extra_codes:
        raise CompanyDossierError("active identities fall outside the expected denominator")
    if universe_status == "EXACT" and missing_codes:
        raise CompanyDossierError("EXACT universe is missing expected securities")
    if universe_status == "PARTIAL" and not missing_codes:
        raise CompanyDossierError("PARTIAL universe must preserve a real denominator gap")
    if set(evidence) - used_evidence_ids:
        raise CompanyDossierError("issuer universe contains unused evidence")

    active_codes_by_issuer: dict[str, list[str]] = defaultdict(list)
    for identity in active_identities:
        active_codes_by_issuer[identity["_issuer_id"]].append(identity["security_code"])
    if any(not active_codes_by_issuer.get(issuer_id) for issuer_id in issuers):
        raise CompanyDossierError("issuer has no active security at universe as_of")
    return {
        "schema_version": UNIVERSE_SCHEMA_VERSION,
        "evidence_class": evidence_class,
        "capture_mode": capture_mode,
        "as_of": as_of,
        "universe_status": universe_status,
        "expected_security_codes": tuple(sorted(expected_codes)),
        "active_security_codes": tuple(sorted(active_codes)),
        "missing_security_codes": tuple(missing_codes),
        "issuers": issuers,
        "active_codes_by_issuer": {
            key: tuple(sorted(value)) for key, value in active_codes_by_issuer.items()
        },
        "identity_gap_count": sum(len(item["identity_gaps"]) for item in issuers.values()),
        "evidence_count": len(evidence),
    }


def _validate_fact(
    raw: Any,
    *,
    section_name: str,
    critical_fields: set[str],
    evidence: Mapping[str, Mapping[str, Any]],
    as_of: datetime,
) -> dict[str, Any]:
    fact = _exact(raw, FACT_FIELDS, f"section {section_name} fact")
    field_name = _text(fact["field_name"], "fact.field_name", maximum=128)
    if FIELD_KEY_RE.fullmatch(field_name) is None:
        raise CompanyDossierError("fact.field_name is invalid")
    fact["field_name"] = field_name
    fact["evidence_ids"] = _string_list(
        fact["evidence_ids"], "fact.evidence_ids", allow_empty=True
    )
    if fact["value"] is None:
        if any(
            fact[field] is not None
            for field in ("unit", "effective_at", "published_at", "available_at", "fact_status")
        ):
            raise CompanyDossierError("missing fact must keep value metadata null")
        if fact["evidence_ids"]:
            raise CompanyDossierError("missing fact cannot bind accepted evidence")
        fact["missing_reason"] = _enum(
            fact["missing_reason"], GAP_REASONS, "fact.missing_reason"
        )
        fact["_missing"] = True
        return fact

    fact["value"] = _finite_scalar(fact["value"], "fact.value")
    fact["unit"] = _optional_text(fact["unit"], "fact.unit", maximum=64)
    effective = _aware(fact["effective_at"], "fact.effective_at")
    published = _optional_aware(fact["published_at"], "fact.published_at")
    available = _aware(fact["available_at"], "fact.available_at")
    if effective > as_of or available > as_of:
        raise CompanyDossierError("fact contains post-cutoff information")
    if published is not None and available < published:
        raise CompanyDossierError("fact.available_at precedes published_at")
    fact_status = _enum(fact["fact_status"], FACT_STATUSES, "fact.fact_status")
    if not fact["evidence_ids"] or any(item not in evidence for item in fact["evidence_ids"]):
        raise CompanyDossierError("resolved fact requires known evidence")
    bound_evidence = [evidence[item] for item in fact["evidence_ids"]]
    if fact_status == "confirmed" and not any(
        item["fact_status"] == "confirmed" for item in bound_evidence
    ):
        raise CompanyDossierError("confirmed fact lacks confirmed evidence")
    if field_name in critical_fields and not _official_identity_evidence(bound_evidence):
        raise CompanyDossierError("critical fact lacks confirmed grade A/B primary evidence")
    if fact["missing_reason"] is not None:
        raise CompanyDossierError("resolved fact cannot carry missing_reason")
    fact["effective_at"] = effective.isoformat()
    fact["published_at"] = None if published is None else published.isoformat()
    fact["available_at"] = available.isoformat()
    fact["fact_status"] = fact_status
    fact["_missing"] = False
    return fact


def validate_company_dossier(
    document: Any,
    *,
    universe: Mapping[str, Any],
) -> dict[str, Any]:
    root = _exact(document, DOSSIER_FIELDS, "company dossier")
    if root["schema_version"] != DOSSIER_SCHEMA_VERSION:
        raise CompanyDossierError("unsupported company-dossier schema_version")
    evidence_class = _enum(root["evidence_class"], EVIDENCE_CLASSES, "evidence_class")
    capture_mode = _enum(root["capture_mode"], CAPTURE_MODES, "capture_mode")
    as_of = _aware(root["as_of"], "company dossier.as_of")
    if (
        evidence_class != universe["evidence_class"]
        or capture_mode != universe["capture_mode"]
        or as_of != universe["as_of"]
    ):
        raise CompanyDossierError("dossier run identity differs from issuer universe")
    last_updated = _aware(root["last_updated_at"], "company dossier.last_updated_at")
    if last_updated < as_of:
        raise CompanyDossierError("last_updated_at precedes dossier as_of")
    if capture_mode == "PROSPECTIVE" and last_updated > as_of:
        raise CompanyDossierError("prospective last_updated_at exceeds dossier as_of")
    issuer_id = _text(root["issuer_id"], "company dossier.issuer_id", maximum=256)
    if issuer_id not in universe["issuers"]:
        raise CompanyDossierError("dossier references an unknown issuer")
    security_codes = _string_list(
        root["security_codes"],
        "company dossier.security_codes",
        allow_empty=False,
        pattern=SECURITY_CODE_RE,
    )
    if set(security_codes) != set(universe["active_codes_by_issuer"][issuer_id]):
        raise CompanyDossierError("dossier security codes do not match point-in-time identity")

    if not isinstance(root["evidence"], list) or not root["evidence"]:
        raise CompanyDossierError("company dossier evidence must be non-empty")
    evidence: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(root["evidence"]):
        row = _validate_evidence(
            raw,
            capture_mode=capture_mode,
            as_of=as_of,
            label=f"company dossier.evidence[{index}]",
        )
        if row["evidence_id"] in evidence:
            raise CompanyDossierError("company dossier contains duplicate evidence_id")
        evidence[row["evidence_id"]] = row

    sections_raw = root["sections"]
    if not isinstance(sections_raw, dict) or set(sections_raw) != set(SECTION_NAMES):
        raise CompanyDossierError("company dossier sections differ from the frozen contract")
    facts_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    missing_keys: set[tuple[str, str]] = set()
    critical_missing_keys: set[tuple[str, str]] = set()
    used_evidence_ids: set[str] = set()
    expected_keys: set[str] = set()
    resolved_keys: set[str] = set()
    for section_name in SECTION_NAMES:
        section = _exact(sections_raw[section_name], SECTION_FIELDS, f"section {section_name}")
        expected_fields = _string_list(
            section["expected_fields"],
            f"section {section_name}.expected_fields",
            allow_empty=False,
            pattern=FIELD_KEY_RE,
        )
        critical_fields = _string_list(
            section["critical_fields"],
            f"section {section_name}.critical_fields",
            allow_empty=True,
            pattern=FIELD_KEY_RE,
        )
        if not REQUIRED_EXPECTED_FIELDS[section_name].issubset(expected_fields):
            raise CompanyDossierError(f"section {section_name} omits required expected fields")
        if not set(critical_fields).issubset(expected_fields):
            raise CompanyDossierError(f"section {section_name} critical fields exceed denominator")
        if not REQUIRED_CRITICAL_FIELDS[section_name].issubset(critical_fields):
            raise CompanyDossierError(f"section {section_name} weakens required critical fields")
        if not isinstance(section["facts"], list):
            raise CompanyDossierError(f"section {section_name}.facts must be a list")
        section_facts: dict[str, dict[str, Any]] = {}
        for raw_fact in section["facts"]:
            fact = _validate_fact(
                raw_fact,
                section_name=section_name,
                critical_fields=set(critical_fields),
                evidence=evidence,
                as_of=as_of,
            )
            if fact["field_name"] in section_facts:
                raise CompanyDossierError(f"section {section_name} contains duplicate fact")
            section_facts[fact["field_name"]] = fact
            key = (section_name, fact["field_name"])
            facts_by_key[key] = fact
            expected_keys.add(f"{section_name}.{fact['field_name']}")
            if fact["_missing"]:
                missing_keys.add(key)
                if fact["field_name"] in critical_fields:
                    critical_missing_keys.add(key)
            else:
                resolved_keys.add(f"{section_name}.{fact['field_name']}")
                used_evidence_ids.update(fact["evidence_ids"])
        if set(section_facts) != set(expected_fields):
            raise CompanyDossierError(f"section {section_name} facts differ from denominator")

    if not isinstance(root["data_gaps"], list):
        raise CompanyDossierError("data_gaps must be a list")
    gaps: dict[tuple[str, str], dict[str, Any]] = {}
    gap_source_ids: set[str] = set()
    for index, raw_gap in enumerate(root["data_gaps"]):
        gap = _exact(raw_gap, GAP_FIELDS, f"data_gaps[{index}]")
        section_name = _enum(gap["section"], SECTION_NAMES, "data gap.section")
        field_name = _text(gap["field_name"], "data gap.field_name", maximum=128)
        key = (section_name, field_name)
        if key in gaps:
            raise CompanyDossierError("data_gaps contains a duplicate cell")
        gap["reason_code"] = _enum(gap["reason_code"], GAP_REASONS, "data gap.reason_code")
        gap["detail"] = _text(gap["detail"], "data gap.detail")
        attempted = _optional_aware(gap["last_attempted_at"], "data gap.last_attempted_at")
        if attempted is not None and attempted > last_updated:
            raise CompanyDossierError("data gap attempt occurs after last_updated_at")
        gap["last_attempted_at"] = None if attempted is None else attempted.isoformat()
        gap["source_ids"] = _string_list(
            gap["source_ids"], "data gap.source_ids", allow_empty=True
        )
        gap_source_ids.update(gap["source_ids"])
        gaps[key] = gap
    if set(gaps) != missing_keys:
        raise CompanyDossierError("data_gaps must match missing facts exactly")
    for key, gap in gaps.items():
        if facts_by_key[key]["missing_reason"] != gap["reason_code"]:
            raise CompanyDossierError("data gap reason disagrees with missing fact")

    if not isinstance(root["source_quality"], list) or not root["source_quality"]:
        raise CompanyDossierError("source_quality must be a non-empty list")
    quality: dict[str, dict[str, Any]] = {}
    for index, raw_quality in enumerate(root["source_quality"]):
        row = _exact(raw_quality, SOURCE_QUALITY_FIELDS, f"source_quality[{index}]")
        source_id = _text(row["source_id"], "source quality.source_id", maximum=512)
        if source_id in quality:
            raise CompanyDossierError("source_quality contains duplicate source_id")
        row["publisher"] = _text(row["publisher"], "source quality.publisher")
        row["source_url"] = _url(row["source_url"], "source quality.source_url")
        row["source_grade"] = _enum(
            row["source_grade"], SOURCE_GRADES, "source quality.source_grade"
        )
        row["rights_status"] = _enum(
            row["rights_status"],
            RIGHTS_STATUSES | {"UNKNOWN", "FORBIDDEN"},
            "source quality.rights_status",
        )
        row["robots_status"] = _enum(
            row["robots_status"],
            ROBOTS_STATUSES | {"UNKNOWN", "DISALLOWED"},
            "source quality.robots_status",
        )
        row["access_status"] = _enum(
            row["access_status"], ACCESS_STATUSES, "source quality.access_status"
        )
        row["expected_fields"] = _string_list(
            row["expected_fields"], "source quality.expected_fields", allow_empty=True
        )
        row["resolved_fields"] = _string_list(
            row["resolved_fields"], "source quality.resolved_fields", allow_empty=True
        )
        if not set(row["resolved_fields"]).issubset(row["expected_fields"]):
            raise CompanyDossierError("source quality resolved fields exceed expected fields")
        if any(item not in expected_keys for item in row["expected_fields"]):
            raise CompanyDossierError("source quality references a field outside the denominator")
        checked = _aware(row["last_checked_at"], "source quality.last_checked_at")
        if checked > last_updated:
            raise CompanyDossierError("source quality check occurs after last_updated_at")
        row["last_checked_at"] = checked.isoformat()
        if not isinstance(row["limitations"], list):
            raise CompanyDossierError("source quality limitations must be a list")
        row["limitations"] = [
            _text(item, "source quality.limitations[]") for item in row["limitations"]
        ]
        quality[source_id] = row

    required_quality_sources = {row["source_id"] for row in evidence.values()} | gap_source_ids
    if set(quality) != required_quality_sources:
        raise CompanyDossierError("source_quality must cover evidence and gap sources exactly")
    for source_id, evidence_rows in _group_evidence_by_source(evidence.values()).items():
        quality_row = quality[source_id]
        if quality_row["access_status"] != "AVAILABLE":
            raise CompanyDossierError("admitted evidence source must remain AVAILABLE")
        for evidence_row in evidence_rows:
            for field in (
                "publisher",
                "source_url",
                "source_grade",
                "rights_status",
                "robots_status",
            ):
                if quality_row[field] != evidence_row[field]:
                    raise CompanyDossierError("source quality disagrees with admitted evidence")
    for key, fact in facts_by_key.items():
        if fact["_missing"]:
            for source_id in gaps[key]["source_ids"]:
                if f"{key[0]}.{key[1]}" not in quality[source_id]["expected_fields"]:
                    raise CompanyDossierError("gap source did not declare the missing field")
        else:
            fact_key = f"{key[0]}.{key[1]}"
            for evidence_id in fact["evidence_ids"]:
                source_id = evidence[evidence_id]["source_id"]
                if fact_key not in quality[source_id]["resolved_fields"]:
                    raise CompanyDossierError("source quality omits a resolved evidence field")
    actual_resolved_by_source: dict[str, set[str]] = defaultdict(set)
    for (section_name, field_name), fact in facts_by_key.items():
        if fact["_missing"]:
            continue
        for evidence_id in fact["evidence_ids"]:
            actual_resolved_by_source[evidence[evidence_id]["source_id"]].add(
                f"{section_name}.{field_name}"
            )
    for source_id, quality_row in quality.items():
        if set(quality_row["resolved_fields"]) != actual_resolved_by_source[source_id]:
            raise CompanyDossierError("source quality resolved fields are not evidence-derived")
    if set(evidence) != used_evidence_ids:
        raise CompanyDossierError("company dossier contains unused evidence")
    if any(item not in quality for item in gap_source_ids):
        raise CompanyDossierError("data gap references unknown source quality")

    boundaries = _exact(root["claim_boundaries"], CLAIM_BOUNDARY_FIELDS, "claim_boundaries")
    if any(value is not False for value in boundaries.values()):
        raise CompanyDossierError("company dossier cannot enable operational claims")
    return {
        "issuer_id": issuer_id,
        "security_codes": sorted(security_codes),
        "expected_field_count": len(facts_by_key),
        "resolved_field_count": len(facts_by_key) - len(missing_keys),
        "missing_field_count": len(missing_keys),
        "missing_critical_field_count": len(critical_missing_keys),
        "source_count": len(quality),
        "evidence_count": len(evidence),
        "last_updated_at": last_updated.isoformat(),
    }


def _group_evidence_by_source(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["source_id"])].append(row)
    return grouped


def validate_company_research_bundle(
    universe_document: Any,
    dossier_documents: Sequence[Any],
) -> dict[str, Any]:
    universe = validate_issuer_universe(universe_document)
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    seen_issuers: set[str] = set()
    for index, dossier in enumerate(dossier_documents):
        try:
            result = validate_company_dossier(dossier, universe=universe)
            if result["issuer_id"] in seen_issuers:
                raise CompanyDossierError("bundle contains duplicate issuer dossier")
            seen_issuers.add(result["issuer_id"])
            results.append(result)
        except CompanyDossierError as exc:
            errors.append(f"DOSSIER_INVALID:{index}:{exc}")
    expected_issuers = set(universe["issuers"])
    if seen_issuers != expected_issuers:
        errors.append(
            "DOSSIER_DENOMINATOR_MISMATCH:"
            f"missing={len(expected_issuers - seen_issuers)}:"
            f"extra={len(seen_issuers - expected_issuers)}"
        )
    if universe["missing_security_codes"]:
        errors.append(
            f"UNIVERSE_SECURITY_GAPS:{len(universe['missing_security_codes'])}"
        )
    missing_critical = sum(item["missing_critical_field_count"] for item in results)
    missing_fields = sum(item["missing_field_count"] for item in results)
    if errors or missing_critical:
        status = "BLOCKED"
    elif missing_fields or universe["identity_gap_count"]:
        status = "STRUCTURE_VALID_ONLY_WITH_EXPLICIT_GAPS"
    else:
        status = "STRUCTURE_VALID_ONLY"
    expected_fields = sum(item["expected_field_count"] for item in results)
    resolved_fields = sum(item["resolved_field_count"] for item in results)
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": status,
        "evidence_class": universe["evidence_class"],
        "as_of": universe["as_of"].isoformat(),
        "universe_summary": {
            "universe_status": universe["universe_status"],
            "expected_security_count": len(universe["expected_security_codes"]),
            "active_security_count": len(universe["active_security_codes"]),
            "missing_security_count": len(universe["missing_security_codes"]),
            "issuer_count": len(universe["issuers"]),
            "identity_gap_count": universe["identity_gap_count"],
            "evidence_count": universe["evidence_count"],
        },
        "dossier_summary": {
            "submitted_dossier_count": len(dossier_documents),
            "valid_dossier_count": len(results),
            "expected_field_count": expected_fields,
            "resolved_field_count": resolved_fields,
            "missing_field_count": missing_fields,
            "missing_critical_field_count": missing_critical,
            "data_coverage_score": (
                resolved_fields / expected_fields if expected_fields else 0.0
            ),
        },
        "issuer_results": sorted(results, key=lambda item: item["issuer_id"]),
        "errors": sorted(set(errors)),
        "claim_boundaries": {
            "real_collection_complete": False,
            "company_universe_complete": False,
            "training_permitted": False,
            "backtest_permitted": False,
            "recommendation_permitted": False,
            "financial_execution_permitted": False,
        },
        "limitations": [
            "schema and semantic validation do not prove source rights or complete market coverage",
            "synthetic and recorded fixtures do not become real market evidence",
            "missing values remain explicit and are never converted into default numbers",
            "the report cannot authorize training, backtesting, recommendations, or trades",
        ],
    }
    report["report_sha256"] = hash_json(report)
    return report


def validate_company_research_bundle_files(
    universe_path: Path | str,
    dossier_paths: Sequence[Path | str],
) -> dict[str, Any]:
    universe = load_source_evidence_document(universe_path)
    dossiers = [load_source_evidence_document(path) for path in dossier_paths]
    return validate_company_research_bundle(universe, dossiers)


def write_company_dossier_report(path: Path | str, report: Mapping[str, Any]) -> Path:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise FileExistsError("refusing to overwrite an existing company dossier report")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise CompanyDossierError("output parent must be a real directory")
    with target.open("xb") as handle:
        handle.write(canonical_json_bytes(dict(report)))
        handle.flush()
        os.fsync(handle.fileno())
    return target


__all__ = [
    "CompanyDossierError",
    "DOSSIER_SCHEMA_VERSION",
    "REPORT_SCHEMA_VERSION",
    "UNIVERSE_SCHEMA_VERSION",
    "validate_company_dossier",
    "validate_company_research_bundle",
    "validate_company_research_bundle_files",
    "validate_issuer_universe",
    "write_company_dossier_report",
]
