from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import re
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from .strict import finite_number, parse_aware, require_sha256, strict_bool


PRODUCT_ID = "KUWAIT_120D_NEXT_SESSION_RESEARCH"
CONTEXT_LOOKBACK = timedelta(days=120)
ACTIVE_EVENT_LOOKBACK = timedelta(days=30)
COMMUNITY_SENTIMENT_LOOKBACK = timedelta(days=7)
FRESH_CATALYST_LOOKBACK = timedelta(hours=72)

WINDOWS: tuple[tuple[str, timedelta], ...] = (
    ("CONTEXT_120D", CONTEXT_LOOKBACK),
    ("ACTIVE_EVENT_30D", ACTIVE_EVENT_LOOKBACK),
    ("COMMUNITY_SENTIMENT_7D", COMMUNITY_SENTIMENT_LOOKBACK),
    ("FRESH_CATALYST_72H", FRESH_CATALYST_LOOKBACK),
)
WINDOW_NAMES = frozenset(name for name, _ in WINDOWS)

# Factor observation freshness is a separate contract from context-event tagging.
# In particular, an official trading-status observation must be current enough to
# support a next-session disposition; a 72-hour catalyst window is too permissive
# for that gate.
FACTOR_WINDOW_LIMITS: Mapping[str, tuple[int | None, int | None]] = {
    "CONTEXT_120D": (120, None),
    "ACTIVE_EVENT_30D": (30, None),
    "COMMUNITY_SENTIMENT_7D": (7, None),
    "FRESH_CATALYST_72H": (None, 72),
    "CURRENT_STATUS_24H": (None, 24),
}
FACTOR_WINDOW_NAMES = frozenset(FACTOR_WINDOW_LIMITS)

EVENT_SCOPES = frozenset({"KUWAIT_MACRO", "SECTOR", "SECURITY"})
EVENT_DIRECTIONS = frozenset({"POSITIVE", "NEGATIVE", "NEUTRAL", "UNKNOWN"})
SOURCE_CLASSES = frozenset(
    {
        "OFFICIAL",
        "REGULATOR",
        "ISSUER",
        "GOVERNMENT",
        "NEWS",
        "MARKET_DATA",
        "COMMUNITY",
        "SEARCH_ROUTING",
        "ARCHIVE",
    }
)
FACTUAL_STATUSES = frozenset(
    {
        "OFFICIAL_CONFIRMED",
        "MULTISOURCE_CORROBORATED",
        "UNCONFIRMED",
        "CONTESTED",
        "ROUTING_ONLY",
    }
)
CONTRADICTION_STATUSES = frozenset({"UNCONTESTED", "CONTESTED", "RESOLVED", "UNKNOWN"})
CORRECTION_STATUSES = frozenset({"CURRENT", "CORRECTED", "SUPERSEDED"})
# CURRENT facts and current corrective events remain active. SUPERSEDED is the
# sole inactive state in this vocabulary and must never feed a factor.
FACTOR_ELIGIBLE_CORRECTION_STATUSES = frozenset({"CURRENT", "CORRECTED"})
RELATION_TYPES = frozenset({"STANDALONE", "ORIGINAL", "REPUBLISHED", "SUPPLEMENTARY", "CORRECTIVE"})
CAPTURE_MODES = frozenset({"PROSPECTIVE", "HISTORICAL_POINT_IN_TIME", "RECORDED_FIXTURE"})

EXPOSURE_TYPES = frozenset(
    {
        "DIRECT_NAMED",
        "CONTRACT_COUNTERPARTY",
        "SECTOR_EXPOSURE",
        "INFERRED_EXPOSURE",
        "UNRESOLVED",
    }
)
CONFIRMATION_CLASSES = frozenset(
    {"OFFICIAL_EVIDENCE", "NEWS_CORROBORATED", "ANALYTICAL_INFERENCE", "UNRESOLVED"}
)

FACTOR_STATUSES = frozenset({"OBSERVED", "MISSING", "NOT_APPLICABLE", "REJECTED"})
DISPOSITIONS = frozenset({"SELECTED", "REJECTED", "ABSTAINED", "UNRESOLVED"})
FAILED_STAGES = frozenset(
    {
        "UNIVERSE_IDENTITY",
        "SECURITY_STATUS",
        "PRICE_DATA",
        "EVENT_CONTEXT",
        "EXPOSURE_MAPPING",
        "FACTOR_INPUTS",
        "FACTOR_VALIDATION",
        "RANKING",
        "DISPOSITION",
    }
)

_EVENT_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_FACTOR_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REGISTRY_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_SECURITY_CODE_RE = re.compile(r"^[0-9]{1,12}$")
_SCOPE_KEY_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,63}$")

_RAW_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "event_id",
        "scope",
        "scope_key",
        "event_type",
        "direction",
        "materiality",
        "confidence",
        "novelty",
        "event_at",
        "published_at",
        "first_available_at",
        "captured_at",
        "decision_at",
        "capture_mode",
        "source_id",
        "source_group_id",
        "source_class",
        "origin_id",
        "origin_hash",
        "content_hash",
        "evidence_hashes",
        "availability_evidence_hashes",
        "relation_type",
        "original_event_id",
        "factual_status",
        "contradiction_status",
        "correction_status",
        "summary",
    }
)

_EXPOSURE_KEYS = frozenset(
    {
        "schema_version",
        "exposure_id",
        "canonical_event_id",
        "security_code",
        "exposure_type",
        "sector_code",
        "direction",
        "confidence",
        "materiality",
        "available_at",
        "decision_at",
        "confirmation_class",
        "contradiction_status",
        "factor_eligible",
        "evidence_hashes",
        "reason_codes",
    }
)

_FACTOR_INPUT_KEYS = frozenset({"status", "value", "available_at", "evidence_hashes", "reason_codes"})
_DISPOSITION_INPUT_KEYS = frozenset({"disposition", "first_failed_stage", "reason_codes", "score", "score_kind"})


def _require_exact_keys(row: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    if not isinstance(row, Mapping):
        raise ValueError(f"{label} must be an object")
    actual = frozenset(row)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"{label} has missing={missing} extra={extra}")


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _enum(value: Any, field: str, allowed: frozenset[str]) -> str:
    text = str(value or "").strip().upper()
    if text not in allowed:
        raise ValueError(f"{field} is invalid")
    return text


def _hashes(
    value: Any,
    field: str,
    *,
    manifest_hashes: frozenset[str] | None,
    minimum: int = 0,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    normalized = tuple(require_sha256(item, field) for item in value)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must be unique")
    if len(normalized) < minimum:
        raise ValueError(f"{field} requires at least {minimum} item(s)")
    if manifest_hashes is not None and set(normalized) - manifest_hashes:
        raise ValueError(f"{field} contains an unresolved evidence hash")
    return normalized


def _reason_codes(value: Any, field: str, *, minimum: int = 0) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    rows = tuple(str(item or "").strip().upper() for item in value)
    if len(rows) != len(set(rows)):
        raise ValueError(f"{field} must be unique")
    if len(rows) < minimum or any(not _REASON_CODE_RE.fullmatch(item) for item in rows):
        raise ValueError(f"{field} contains an invalid reason code")
    return rows


def _canonical_json_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _factor_snapshot_content_hash(snapshot: Mapping[str, Any]) -> str:
    material = dict(snapshot)
    material.pop("snapshot_id", None)
    material.pop("factor_snapshot_sha256", None)
    return _canonical_json_hash(material)


def window_tags_for(*, first_available_at: Any, decision_at: Any) -> tuple[str, ...]:
    available = parse_aware(first_available_at, "first_available_at")
    decision = parse_aware(decision_at, "decision_at")
    if available > decision:
        raise ValueError("event is available after decision cutoff")
    age = decision - available
    if age > CONTEXT_LOOKBACK:
        raise ValueError("event falls outside CONTEXT_120D")
    return tuple(name for name, lookback in WINDOWS if age <= lookback)


@dataclass(frozen=True)
class ContextEvent:
    event_id: str
    scope: str
    scope_key: str
    event_type: str
    direction: str
    materiality: float
    confidence: float
    novelty: float
    event_at: str
    published_at: str
    first_available_at: str
    captured_at: str
    decision_at: str
    capture_mode: str
    source_id: str
    source_group_id: str
    source_class: str
    origin_id: str
    origin_hash: str
    content_hash: str
    evidence_hashes: tuple[str, ...]
    availability_evidence_hashes: tuple[str, ...]
    relation_type: str
    original_event_id: str | None
    factual_status: str
    contradiction_status: str
    correction_status: str
    summary: str
    window_tags: tuple[str, ...]


def context_event_from_dict(
    row: Mapping[str, Any],
    *,
    manifest_hashes: frozenset[str] | None = None,
) -> ContextEvent:
    _require_exact_keys(row, _RAW_EVENT_KEYS, "context event")
    if row["schema_version"] != "1.0":
        raise ValueError("unsupported context event schema_version")
    event_id = _required_text(row["event_id"], "event_id")
    scope = _enum(row["scope"], "scope", EVENT_SCOPES)
    scope_key = _required_text(row["scope_key"], "scope_key").upper()
    if scope == "KUWAIT_MACRO" and scope_key != "KUWAIT":
        raise ValueError("KUWAIT_MACRO scope_key must be KUWAIT")
    if scope == "SECURITY" and not _SECURITY_CODE_RE.fullmatch(scope_key):
        raise ValueError("SECURITY scope_key must be a security_code")
    if scope == "SECTOR" and not _SCOPE_KEY_RE.fullmatch(scope_key):
        raise ValueError("SECTOR scope_key is invalid")
    event_type = _required_text(row["event_type"], "event_type").upper()
    if not _EVENT_TYPE_RE.fullmatch(event_type):
        raise ValueError("event_type is invalid")
    direction = _enum(row["direction"], "direction", EVENT_DIRECTIONS)
    materiality = finite_number(row["materiality"], "materiality", minimum=0, maximum=1)
    confidence = finite_number(row["confidence"], "confidence", minimum=0, maximum=1)
    novelty = finite_number(row["novelty"], "novelty", minimum=0, maximum=1)
    event_at = parse_aware(row["event_at"], "event_at")
    published = parse_aware(row["published_at"], "published_at")
    available = parse_aware(row["first_available_at"], "first_available_at")
    captured = parse_aware(row["captured_at"], "captured_at")
    decision = parse_aware(row["decision_at"], "decision_at")
    if available < published:
        raise ValueError("first_available_at precedes published_at")
    if captured < available:
        raise ValueError("captured_at precedes first_available_at")
    tags = window_tags_for(first_available_at=available, decision_at=decision)
    capture_mode = _enum(row["capture_mode"], "capture_mode", CAPTURE_MODES)
    if capture_mode == "PROSPECTIVE" and captured > decision:
        raise ValueError("prospective event was captured after decision cutoff")
    source_id = _required_text(row["source_id"], "source_id")
    source_group_id = _required_text(row["source_group_id"], "source_group_id")
    source_class = _enum(row["source_class"], "source_class", SOURCE_CLASSES)
    origin_id = _required_text(row["origin_id"], "origin_id")
    origin_hash = require_sha256(row["origin_hash"], "origin_hash")
    content_hash = require_sha256(row["content_hash"], "content_hash")
    evidence_hashes = _hashes(row["evidence_hashes"], "evidence_hashes", manifest_hashes=manifest_hashes, minimum=1)
    availability_hashes = _hashes(
        row["availability_evidence_hashes"],
        "availability_evidence_hashes",
        manifest_hashes=manifest_hashes,
        minimum=1,
    )
    relation_type = _enum(row["relation_type"], "relation_type", RELATION_TYPES)
    original_event_id = str(row["original_event_id"] or "").strip() or None
    if relation_type in {"REPUBLISHED", "SUPPLEMENTARY", "CORRECTIVE"} and not original_event_id:
        raise ValueError("dependent context event requires original_event_id")
    if relation_type in {"STANDALONE", "ORIGINAL"} and original_event_id is not None:
        raise ValueError("standalone/original context event cannot reference an original_event_id")
    factual_status = _enum(row["factual_status"], "factual_status", FACTUAL_STATUSES)
    contradiction_status = _enum(
        row["contradiction_status"], "contradiction_status", CONTRADICTION_STATUSES
    )
    correction_status = _enum(row["correction_status"], "correction_status", CORRECTION_STATUSES)
    summary = _required_text(row["summary"], "summary")
    if source_class in {"COMMUNITY", "SEARCH_ROUTING", "ARCHIVE"} and factual_status in {
        "OFFICIAL_CONFIRMED",
        "MULTISOURCE_CORROBORATED",
    }:
        raise ValueError("community/routing/archive source cannot establish factual confirmation")
    if factual_status == "OFFICIAL_CONFIRMED" and source_class not in {
        "OFFICIAL",
        "REGULATOR",
        "ISSUER",
        "GOVERNMENT",
    }:
        raise ValueError("OFFICIAL_CONFIRMED requires an official primary source class")
    if source_class == "SEARCH_ROUTING" and factual_status != "ROUTING_ONLY":
        raise ValueError("search routing source must remain ROUTING_ONLY")
    if factual_status == "CONTESTED" and contradiction_status != "CONTESTED":
        raise ValueError("CONTESTED factual status requires CONTESTED contradiction status")
    return ContextEvent(
        event_id=event_id,
        scope=scope,
        scope_key=scope_key,
        event_type=event_type,
        direction=direction,
        materiality=materiality,
        confidence=confidence,
        novelty=novelty,
        event_at=event_at.isoformat(),
        published_at=published.isoformat(),
        first_available_at=available.isoformat(),
        captured_at=captured.isoformat(),
        decision_at=decision.isoformat(),
        capture_mode=capture_mode,
        source_id=source_id,
        source_group_id=source_group_id,
        source_class=source_class,
        origin_id=origin_id,
        origin_hash=origin_hash,
        content_hash=content_hash,
        evidence_hashes=evidence_hashes,
        availability_evidence_hashes=availability_hashes,
        relation_type=relation_type,
        original_event_id=original_event_id,
        factual_status=factual_status,
        contradiction_status=contradiction_status,
        correction_status=correction_status,
        summary=summary,
        window_tags=tags,
    )


def _canonical_factual_status(group: list[ContextEvent]) -> str:
    if any(item.factual_status == "CONTESTED" for item in group):
        return "CONTESTED"
    if any(item.factual_status == "OFFICIAL_CONFIRMED" for item in group):
        return "OFFICIAL_CONFIRMED"
    groups = {item.source_group_id for item in group}
    if len(groups) >= 2 and any(item.factual_status == "MULTISOURCE_CORROBORATED" for item in group):
        return "MULTISOURCE_CORROBORATED"
    if all(item.factual_status == "ROUTING_ONLY" for item in group):
        return "ROUTING_ONLY"
    return "UNCONFIRMED"


def _canonical_event_id(group: list[ContextEvent]) -> str:
    first = min(
        group,
        key=lambda item: (parse_aware(item.first_available_at, "first_available_at"), item.event_id),
    )
    identity = "|".join(
        (
            first.scope,
            first.scope_key,
            first.origin_hash,
            first.content_hash,
        )
    )
    return "ctx-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def deduplicate_context_events(events: Iterable[ContextEvent]) -> list[dict[str, Any]]:
    rows = list(events)
    by_id: dict[str, ContextEvent] = {}
    for row in rows:
        if row.event_id in by_id:
            raise ValueError(f"duplicate event_id: {row.event_id}")
        by_id[row.event_id] = row
    for row in rows:
        if row.original_event_id and row.original_event_id not in by_id:
            raise ValueError(f"missing original context event: {row.original_event_id}")
        if row.original_event_id:
            parent = by_id[row.original_event_id]
            if (parent.scope, parent.scope_key) != (row.scope, row.scope_key):
                raise ValueError("context event relation crosses scopes")
        if rows and row.decision_at != rows[0].decision_at:
            raise ValueError("context events must share one decision cutoff")

    parent: dict[str, str] = {row.event_id: row.event_id for row in rows}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    deduplicable = {"STANDALONE", "ORIGINAL", "REPUBLISHED"}
    origin_seen: dict[tuple[str, str, str], str] = {}
    content_seen: dict[tuple[str, str, str], str] = {}
    for row in rows:
        if row.relation_type == "REPUBLISHED" and row.original_event_id:
            union(row.event_id, row.original_event_id)
        if row.relation_type not in deduplicable:
            continue
        origin_key = (row.scope, row.scope_key, row.origin_hash)
        content_key = (row.scope, row.scope_key, row.content_hash)
        if origin_key in origin_seen:
            union(row.event_id, origin_seen[origin_key])
        else:
            origin_seen[origin_key] = row.event_id
        if content_key in content_seen:
            union(row.event_id, content_seen[content_key])
        else:
            content_seen[content_key] = row.event_id

    groups: dict[str, list[ContextEvent]] = {}
    for row in rows:
        groups.setdefault(find(row.event_id), []).append(row)

    output: list[dict[str, Any]] = []
    for group in groups.values():
        group.sort(key=lambda item: (parse_aware(item.first_available_at, "first_available_at"), item.event_id))
        first = group[0]
        for item in group[1:]:
            if (item.scope, item.scope_key, item.event_type, item.direction) != (
                first.scope,
                first.scope_key,
                first.event_type,
                first.direction,
            ):
                raise ValueError("origin/content duplicate has conflicting event semantics")
            if (item.materiality, item.confidence, item.novelty) != (
                first.materiality,
                first.confidence,
                first.novelty,
            ):
                raise ValueError("origin/content duplicate has conflicting analytical values")
        factual_status = _canonical_factual_status(group)
        contradiction_status = (
            "CONTESTED"
            if factual_status == "CONTESTED" or any(item.contradiction_status == "CONTESTED" for item in group)
            else "RESOLVED"
            if any(item.contradiction_status == "RESOLVED" for item in group)
            else "UNKNOWN"
            if all(item.contradiction_status == "UNKNOWN" for item in group)
            else "UNCONTESTED"
        )
        correction_status = (
            "SUPERSEDED"
            if any(item.correction_status == "SUPERSEDED" for item in group)
            else "CORRECTED"
            if any(item.correction_status == "CORRECTED" for item in group)
            else "CURRENT"
        )
        output.append(
            {
                "schema_version": "1.0",
                "canonical_event_id": _canonical_event_id(group),
                "event_ids": sorted(item.event_id for item in group),
                "scope": first.scope,
                "scope_key": first.scope_key,
                "event_type": first.event_type,
                "direction": first.direction,
                "materiality": first.materiality,
                "confidence": first.confidence,
                "novelty": first.novelty,
                "event_at": min(parse_aware(item.event_at, "event_at") for item in group).isoformat(),
                "first_published_at": min(parse_aware(item.published_at, "published_at") for item in group).isoformat(),
                "first_available_at": min(parse_aware(item.first_available_at, "first_available_at") for item in group).isoformat(),
                "last_captured_at": max(parse_aware(item.captured_at, "captured_at") for item in group).isoformat(),
                "decision_at": first.decision_at,
                "capture_modes": sorted({item.capture_mode for item in group}),
                "source_ids": sorted({item.source_id for item in group}),
                "source_group_ids": sorted({item.source_group_id for item in group}),
                "source_classes": sorted({item.source_class for item in group}),
                "origin_ids": sorted({item.origin_id for item in group}),
                "origin_hashes": sorted({item.origin_hash for item in group}),
                "content_hashes": sorted({item.content_hash for item in group}),
                "evidence_hashes": sorted({digest for item in group for digest in item.evidence_hashes}),
                "availability_evidence_hashes": sorted(
                    {digest for item in group for digest in item.availability_evidence_hashes}
                ),
                "relation_types": sorted({item.relation_type for item in group}),
                "diffusion_count": len(group),
                "independent_source_groups": len({item.source_group_id for item in group}),
                "factual_status": factual_status,
                "contradiction_status": contradiction_status,
                "correction_status": correction_status,
                "window_tags": list(
                    window_tags_for(
                        first_available_at=min(
                            parse_aware(item.first_available_at, "first_available_at") for item in group
                        ),
                        decision_at=first.decision_at,
                    )
                ),
                "summary": first.summary,
            }
        )
    output.sort(key=lambda item: (item["first_available_at"], item["scope"], item["scope_key"], item["canonical_event_id"]))
    return output


@dataclass(frozen=True)
class SecurityExposure:
    exposure_id: str
    canonical_event_id: str
    security_code: str
    exposure_type: str
    sector_code: str | None
    direction: str
    confidence: float
    materiality: float
    available_at: str
    decision_at: str
    confirmation_class: str
    contradiction_status: str
    factor_eligible: bool
    evidence_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "exposure_id": self.exposure_id,
            "canonical_event_id": self.canonical_event_id,
            "security_code": self.security_code,
            "exposure_type": self.exposure_type,
            "sector_code": self.sector_code,
            "direction": self.direction,
            "confidence": self.confidence,
            "materiality": self.materiality,
            "available_at": self.available_at,
            "decision_at": self.decision_at,
            "confirmation_class": self.confirmation_class,
            "contradiction_status": self.contradiction_status,
            "factor_eligible": self.factor_eligible,
            "evidence_hashes": list(self.evidence_hashes),
            "reason_codes": list(self.reason_codes),
        }


def security_exposure_from_dict(
    row: Mapping[str, Any],
    *,
    manifest_hashes: frozenset[str] | None = None,
) -> SecurityExposure:
    _require_exact_keys(row, _EXPOSURE_KEYS, "security exposure")
    if row["schema_version"] != "1.0":
        raise ValueError("unsupported security exposure schema_version")
    exposure_id = _required_text(row["exposure_id"], "exposure_id")
    if not re.fullmatch(r"exp-[0-9a-f]{24}", exposure_id):
        raise ValueError("exposure_id is invalid")
    canonical_event_id = _required_text(row["canonical_event_id"], "canonical_event_id")
    if not re.fullmatch(r"ctx-[0-9a-f]{24}", canonical_event_id):
        raise ValueError("canonical_event_id is invalid")
    security_code = _required_text(row["security_code"], "security_code")
    if not _SECURITY_CODE_RE.fullmatch(security_code):
        raise ValueError("security_code is invalid")
    exposure_type = _enum(row["exposure_type"], "exposure_type", EXPOSURE_TYPES)
    sector_code = str(row["sector_code"] or "").strip().upper() or None
    if sector_code is not None and not _SCOPE_KEY_RE.fullmatch(sector_code):
        raise ValueError("sector_code is invalid")
    if exposure_type == "SECTOR_EXPOSURE" and sector_code is None:
        raise ValueError("SECTOR_EXPOSURE requires sector_code")
    if exposure_type != "SECTOR_EXPOSURE" and sector_code is not None:
        raise ValueError("sector_code is only valid for SECTOR_EXPOSURE")
    direction = _enum(row["direction"], "direction", EVENT_DIRECTIONS)
    confidence = finite_number(row["confidence"], "confidence", minimum=0, maximum=1)
    materiality = finite_number(row["materiality"], "materiality", minimum=0, maximum=1)
    available = parse_aware(row["available_at"], "available_at")
    decision = parse_aware(row["decision_at"], "decision_at")
    if available > decision:
        raise ValueError("security exposure is available after decision cutoff")
    confirmation = _enum(row["confirmation_class"], "confirmation_class", CONFIRMATION_CLASSES)
    contradiction = _enum(row["contradiction_status"], "contradiction_status", CONTRADICTION_STATUSES)
    factor_eligible = strict_bool(row["factor_eligible"], "factor_eligible")
    evidence_hashes = _hashes(row["evidence_hashes"], "evidence_hashes", manifest_hashes=manifest_hashes, minimum=1)
    reasons = _reason_codes(row["reason_codes"], "reason_codes", minimum=0)
    if exposure_type == "INFERRED_EXPOSURE" and confirmation != "ANALYTICAL_INFERENCE":
        raise ValueError("INFERRED_EXPOSURE must remain ANALYTICAL_INFERENCE")
    if exposure_type == "UNRESOLVED":
        if confirmation != "UNRESOLVED" or factor_eligible or direction != "UNKNOWN" or not reasons:
            raise ValueError("UNRESOLVED exposure must remain non-factor-eligible with reasons")
    elif confirmation == "UNRESOLVED":
        raise ValueError("resolved exposure type cannot use UNRESOLVED confirmation")
    if exposure_type in {"DIRECT_NAMED", "CONTRACT_COUNTERPARTY"} and confirmation == "ANALYTICAL_INFERENCE":
        raise ValueError("direct/counterparty exposure cannot be relabeled as analytical inference")
    if contradiction == "CONTESTED" and factor_eligible:
        raise ValueError("contested security exposure cannot be factor eligible")
    return SecurityExposure(
        exposure_id=exposure_id,
        canonical_event_id=canonical_event_id,
        security_code=security_code,
        exposure_type=exposure_type,
        sector_code=sector_code,
        direction=direction,
        confidence=confidence,
        materiality=materiality,
        available_at=available.isoformat(),
        decision_at=decision.isoformat(),
        confirmation_class=confirmation,
        contradiction_status=contradiction,
        factor_eligible=factor_eligible,
        evidence_hashes=evidence_hashes,
        reason_codes=reasons,
    )


def validate_security_exposures(
    exposures: Iterable[SecurityExposure],
    *,
    context_events: Iterable[Mapping[str, Any]],
    expected_security_codes: Iterable[str],
) -> dict[str, Any]:
    rows = list(exposures)
    events = list(context_events)
    event_map = {str(item.get("canonical_event_id", "")): item for item in events}
    expected = {str(item) for item in expected_security_codes}
    errors: list[str] = []
    ids: set[str] = set()
    keys: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows):
        try:
            if row.exposure_id in ids:
                raise ValueError("duplicate exposure_id")
            ids.add(row.exposure_id)
            key = (row.canonical_event_id, row.security_code, row.exposure_type)
            if key in keys:
                raise ValueError("duplicate event/security/exposure_type")
            keys.add(key)
            if row.security_code not in expected:
                raise ValueError("exposure security is outside frozen denominator")
            event = event_map.get(row.canonical_event_id)
            if event is None:
                raise ValueError("exposure event does not resolve")
            if parse_aware(row.available_at, "available_at") < parse_aware(
                event.get("first_available_at"), "event.first_available_at"
            ):
                raise ValueError("exposure predates its event availability")
            if row.decision_at != str(event.get("decision_at", "")):
                raise ValueError("exposure decision cutoff does not match its event")
            event_evidence = set(event.get("evidence_hashes", [])) | set(
                event.get("availability_evidence_hashes", [])
            )
            if not set(row.evidence_hashes) & event_evidence:
                raise ValueError("exposure evidence does not bind to its event")
            if row.exposure_type == "DIRECT_NAMED" and event.get("scope") == "SECURITY" and str(
                event.get("scope_key")
            ) != row.security_code:
                raise ValueError("DIRECT_NAMED security conflicts with SECURITY event scope")
            if row.exposure_type == "SECTOR_EXPOSURE" and event.get("scope") == "SECTOR" and str(
                event.get("scope_key")
            ) != row.sector_code:
                raise ValueError("SECTOR_EXPOSURE sector conflicts with event scope")
            source_classes = set(event.get("source_classes", []))
            factual_status = str(event.get("factual_status", ""))
            correction_status = str(event.get("correction_status", "")).upper()
            if row.factor_eligible and correction_status not in FACTOR_ELIGIBLE_CORRECTION_STATUSES:
                raise ValueError("inactive/superseded event cannot create a factor-eligible exposure")
            if row.factor_eligible and factual_status in {"ROUTING_ONLY", "CONTESTED"}:
                raise ValueError("routing-only/contested event cannot create a factor-eligible exposure")
            if row.factor_eligible and source_classes and source_classes <= {"COMMUNITY", "SEARCH_ROUTING", "ARCHIVE"}:
                raise ValueError("community/routing/archive-only event cannot create factual exposure")
        except (TypeError, ValueError) as exc:
            errors.append(f"exposure_{index}:{exc}")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "rows": len(rows),
        "resolved_event_ids": len({row.canonical_event_id for row in rows if row.canonical_event_id in event_map}),
        "errors": sorted(set(errors)),
    }


@dataclass(frozen=True)
class FactorDefinition:
    factor_id: str
    family: str
    value_type: str
    lookback_window: str
    window_days: int | None
    window_hours: int | None
    required_for_selection: bool
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "family": self.family,
            "value_type": self.value_type,
            "lookback_window": self.lookback_window,
            "window_days": self.window_days,
            "window_hours": self.window_hours,
            "required_for_selection": self.required_for_selection,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "allowed_values": list(self.allowed_values),
        }


DEFAULT_FACTOR_DEFINITIONS: tuple[FactorDefinition, ...] = (
    FactorDefinition("price_momentum_5d", "PRICE_MOMENTUM", "NUMBER", "COMMUNITY_SENTIMENT_7D", 7, None, True),
    FactorDefinition("price_momentum_20d", "PRICE_MOMENTUM", "NUMBER", "ACTIVE_EVENT_30D", 30, None, False),
    FactorDefinition(
        "market_relative_strength_5d",
        "MARKET_RELATIVE_STRENGTH",
        "NUMBER",
        "COMMUNITY_SENTIMENT_7D",
        7,
        None,
        False,
    ),
    FactorDefinition(
        "sector_relative_strength_5d",
        "SECTOR_RELATIVE_STRENGTH",
        "NUMBER",
        "COMMUNITY_SENTIMENT_7D",
        7,
        None,
        False,
    ),
    FactorDefinition("liquidity_activity_20d", "LIQUIDITY", "NUMBER", "ACTIVE_EVENT_30D", 30, None, True),
    FactorDefinition(
        "realized_volatility_20d", "VOLATILITY", "NUMBER", "ACTIVE_EVENT_30D", 30, None, False, 0.0, None
    ),
    FactorDefinition("official_disclosure_30d", "DISCLOSURE", "NUMBER", "ACTIVE_EVENT_30D", 30, None, False),
    FactorDefinition(
        "corporate_action_state",
        "CORPORATE_ACTION",
        "ENUM",
        "CONTEXT_120D",
        120,
        None,
        False,
        allowed_values=("NO_ACTION", "PENDING", "ACTIVE", "UNRESOLVED"),
    ),
    FactorDefinition(
        "security_trading_status",
        "SECURITY_STATUS",
        "ENUM",
        "CURRENT_STATUS_24H",
        None,
        24,
        True,
        allowed_values=("TRADING", "SUSPENDED", "HALTED", "DELISTED", "UNRESOLVED"),
    ),
    FactorDefinition("kuwait_context_regime_120d", "KUWAIT_CONTEXT", "NUMBER", "CONTEXT_120D", 120, None, False),
    FactorDefinition("market_regime_30d", "MARKET_REGIME", "NUMBER", "ACTIVE_EVENT_30D", 30, None, False),
    FactorDefinition("sector_regime_30d", "SECTOR_REGIME", "NUMBER", "ACTIVE_EVENT_30D", 30, None, False),
    FactorDefinition("event_exposure_30d", "EVENT_EXPOSURE", "NUMBER", "ACTIVE_EVENT_30D", 30, None, False),
    FactorDefinition("fresh_catalyst_72h", "FRESH_CATALYST", "NUMBER", "FRESH_CATALYST_72H", None, 72, False),
    FactorDefinition(
        "community_sentiment_7d",
        "COMMUNITY_SENTIMENT",
        "NUMBER",
        "COMMUNITY_SENTIMENT_7D",
        7,
        None,
        False,
        -1.0,
        1.0,
    ),
)


def factor_registry_payload(
    definitions: Iterable[FactorDefinition] = DEFAULT_FACTOR_DEFINITIONS,
    *,
    registry_version: str = "1.0.0",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "registry_id": "kuwait-120d-next-session-factor-registry",
        "registry_version": registry_version,
        "product_id": PRODUCT_ID,
        "definitions": [item.to_dict() for item in definitions],
        "claim_boundaries": {
            "score_is_probability": False,
            "registry_proves_predictive_skill": False,
            "missing_may_be_encoded_as_zero": False,
            "recommendation_allowed": False,
        },
    }
    payload["registry_sha256"] = _canonical_json_hash(payload)
    return payload


DEFAULT_FACTOR_REGISTRY = factor_registry_payload()


def _parse_factor_registry(payload: Mapping[str, Any]) -> tuple[FactorDefinition, ...]:
    expected = frozenset(
        {
            "schema_version",
            "registry_id",
            "registry_version",
            "product_id",
            "definitions",
            "claim_boundaries",
            "registry_sha256",
        }
    )
    _require_exact_keys(payload, expected, "factor registry")
    if payload["schema_version"] != "1.0" or payload["product_id"] != PRODUCT_ID:
        raise ValueError("unsupported factor registry schema/product")
    if payload["registry_id"] != "kuwait-120d-next-session-factor-registry":
        raise ValueError("factor registry_id is invalid")
    if not _REGISTRY_VERSION_RE.fullmatch(str(payload["registry_version"])):
        raise ValueError("factor registry_version must use semantic versioning")
    claims = payload["claim_boundaries"]
    expected_claims = {
        "score_is_probability": False,
        "registry_proves_predictive_skill": False,
        "missing_may_be_encoded_as_zero": False,
        "recommendation_allowed": False,
    }
    if claims != expected_claims:
        raise ValueError("factor registry claim boundaries were weakened")
    definitions = payload["definitions"]
    if not isinstance(definitions, list) or not definitions:
        raise ValueError("factor registry definitions must be a non-empty list")
    parsed: list[FactorDefinition] = []
    seen: set[str] = set()
    definition_keys = frozenset(
        {
            "factor_id",
            "family",
            "value_type",
            "lookback_window",
            "window_days",
            "window_hours",
            "required_for_selection",
            "minimum",
            "maximum",
            "allowed_values",
        }
    )
    for index, row in enumerate(definitions):
        _require_exact_keys(row, definition_keys, f"factor definition {index}")
        factor_id = str(row["factor_id"])
        if not _FACTOR_ID_RE.fullmatch(factor_id) or factor_id in seen:
            raise ValueError("factor_id is invalid or duplicated")
        seen.add(factor_id)
        family = _required_text(row["family"], "family").upper()
        if not _EVENT_TYPE_RE.fullmatch(family):
            raise ValueError("factor family is invalid")
        value_type = str(row["value_type"]).upper()
        if value_type not in {"NUMBER", "ENUM"}:
            raise ValueError("factor value_type is invalid")
        window = str(row["lookback_window"]).upper()
        if window not in FACTOR_WINDOW_NAMES:
            raise ValueError("factor lookback_window is invalid")
        window_days = row["window_days"]
        window_hours = row["window_hours"]
        if window_days is not None and (
            isinstance(window_days, bool) or not isinstance(window_days, int) or window_days <= 0
        ):
            raise ValueError("factor window_days must be a positive integer or null")
        if window_hours is not None and (
            isinstance(window_hours, bool) or not isinstance(window_hours, int) or window_hours <= 0
        ):
            raise ValueError("factor window_hours must be a positive integer or null")
        if (window_days is None) == (window_hours is None):
            raise ValueError("factor must declare exactly one of window_days/window_hours")
        if (window_days, window_hours) != FACTOR_WINDOW_LIMITS[window]:
            raise ValueError("factor window duration does not match lookback_window")
        required = strict_bool(row["required_for_selection"], "required_for_selection")
        minimum = None if row["minimum"] is None else finite_number(row["minimum"], "minimum")
        maximum = None if row["maximum"] is None else finite_number(row["maximum"], "maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("factor minimum exceeds maximum")
        allowed = row["allowed_values"]
        if not isinstance(allowed, list) or len(allowed) != len(set(allowed)):
            raise ValueError("factor allowed_values must be a unique list")
        allowed_values = tuple(_required_text(item, "allowed_value").upper() for item in allowed)
        if value_type == "NUMBER" and allowed_values:
            raise ValueError("numeric factor cannot declare allowed_values")
        if value_type == "ENUM" and (not allowed_values or minimum is not None or maximum is not None):
            raise ValueError("enum factor needs values and cannot declare numeric bounds")
        parsed.append(
            FactorDefinition(
                factor_id=factor_id,
                family=family,
                value_type=value_type,
                lookback_window=window,
                window_days=window_days,
                window_hours=window_hours,
                required_for_selection=required,
                minimum=minimum,
                maximum=maximum,
                allowed_values=allowed_values,
            )
        )
    claimed_hash = require_sha256(payload["registry_sha256"], "registry_sha256")
    without_hash = dict(payload)
    without_hash.pop("registry_sha256")
    if claimed_hash != _canonical_json_hash(without_hash):
        raise ValueError("factor registry hash mismatch")
    return tuple(parsed)


def validate_factor_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        parsed = _parse_factor_registry(payload)
    except (TypeError, ValueError) as exc:
        return {"status": "BLOCKED", "definition_count": 0, "errors": [str(exc)]}
    return {"status": "PASS", "definition_count": len(parsed), "errors": []}


def _factor_value(definition: FactorDefinition, value: Any) -> float | str:
    if definition.value_type == "NUMBER":
        return finite_number(value, definition.factor_id, minimum=definition.minimum, maximum=definition.maximum)
    text = str(value or "").strip().upper()
    if text not in definition.allowed_values:
        raise ValueError(f"{definition.factor_id} has an invalid enum value")
    return text


def _factor_window(definition: FactorDefinition) -> timedelta:
    if definition.window_days is not None:
        return timedelta(days=definition.window_days)
    if definition.window_hours is not None:
        return timedelta(hours=definition.window_hours)
    raise ValueError(f"{definition.factor_id} has no factor observation window")


def _factor_row(
    definition: FactorDefinition,
    supplied: Mapping[str, Any] | None,
    *,
    decision_at: str,
    manifest_hashes: frozenset[str],
) -> dict[str, Any]:
    if supplied is None:
        return {
            "factor_id": definition.factor_id,
            "status": "MISSING",
            "value": None,
            "available_at": None,
            "evidence_hashes": [],
            "reason_codes": ["INPUT_NOT_SUPPLIED"],
        }
    _require_exact_keys(supplied, _FACTOR_INPUT_KEYS, f"factor input {definition.factor_id}")
    status = _enum(supplied["status"], "status", FACTOR_STATUSES)
    reasons = _reason_codes(
        supplied["reason_codes"],
        "reason_codes",
        minimum=1 if status != "OBSERVED" else 0,
    )
    if status == "MISSING":
        if supplied["value"] is not None or supplied["available_at"] is not None or supplied["evidence_hashes"]:
            raise ValueError(f"{definition.factor_id} MISSING must remain null and evidence-free")
        return {
            "factor_id": definition.factor_id,
            "status": status,
            "value": None,
            "available_at": None,
            "evidence_hashes": [],
            "reason_codes": sorted(reasons),
        }
    evidence_hashes = _hashes(
        supplied["evidence_hashes"],
        "evidence_hashes",
        manifest_hashes=manifest_hashes,
        minimum=1,
    )
    available = parse_aware(supplied["available_at"], "available_at")
    decision = parse_aware(decision_at, "decision_at")
    if available > decision:
        raise ValueError(f"{definition.factor_id} contains look-ahead availability")
    if status != "REJECTED" and decision - available > _factor_window(definition):
        raise ValueError(f"{definition.factor_id} availability falls outside its registry window")
    if status in {"NOT_APPLICABLE", "REJECTED"}:
        if supplied["value"] is not None:
            raise ValueError(f"{definition.factor_id} {status} must not carry a value")
        return {
            "factor_id": definition.factor_id,
            "status": status,
            "value": None,
            "available_at": available.isoformat(),
            "evidence_hashes": sorted(evidence_hashes),
            "reason_codes": sorted(reasons),
        }
    value = _factor_value(definition, supplied["value"])
    return {
        "factor_id": definition.factor_id,
        "status": status,
        "value": value,
        "available_at": available.isoformat(),
        "evidence_hashes": sorted(evidence_hashes),
        "reason_codes": sorted(reasons),
    }


def _sorted_security_codes(values: Iterable[str]) -> list[str]:
    rows = [str(item).strip() for item in values]
    if not rows or any(not _SECURITY_CODE_RE.fullmatch(item) for item in rows):
        raise ValueError("expected_security_codes must contain valid security codes")
    if len(rows) != len(set(rows)):
        raise ValueError("expected_security_codes must be unique")
    return sorted(rows, key=lambda item: (int(item), item))


def _disposition_row(
    supplied: Mapping[str, Any] | None,
    *,
    required_complete: bool,
    selection_allowed: bool,
    any_rejected: bool,
) -> tuple[str, str | None, list[str], float | None, str | None]:
    if supplied is None:
        if any_rejected:
            return "UNRESOLVED", "FACTOR_VALIDATION", ["FACTOR_REJECTED"], None, None
        if not required_complete:
            return "ABSTAINED", "FACTOR_INPUTS", ["REQUIRED_FACTOR_MISSING"], None, None
        if not selection_allowed:
            return "REJECTED", "SECURITY_STATUS", ["SECURITY_NOT_TRADABLE"], None, None
        return "UNRESOLVED", "DISPOSITION", ["DISPOSITION_NOT_SUPPLIED"], None, None
    _require_exact_keys(supplied, _DISPOSITION_INPUT_KEYS, "disposition input")
    disposition = _enum(supplied["disposition"], "disposition", DISPOSITIONS)
    stage = str(supplied["first_failed_stage"] or "").strip().upper() or None
    reasons = sorted(
        _reason_codes(
            supplied["reason_codes"],
            "reason_codes",
            minimum=0 if disposition == "SELECTED" else 1,
        )
    )
    score = None if supplied["score"] is None else finite_number(supplied["score"], "score")
    score_kind = str(supplied["score_kind"] or "").strip().upper() or None
    if disposition == "SELECTED":
        if not required_complete or not selection_allowed or any_rejected:
            raise ValueError("SELECTED requires all mandatory factors and no rejected factor")
        if stage is not None or reasons or score is None or score_kind != "UNVALIDATED_RESEARCH_SCORE":
            raise ValueError("SELECTED disposition has invalid stage/reasons/score")
    else:
        if stage not in FAILED_STAGES:
            raise ValueError("non-selected disposition requires a valid first_failed_stage")
        if score is None and score_kind is not None:
            raise ValueError("score_kind cannot exist without score")
        if score is not None and score_kind != "UNVALIDATED_RESEARCH_SCORE":
            raise ValueError("score must remain an UNVALIDATED_RESEARCH_SCORE")
        if disposition in {"ABSTAINED", "UNRESOLVED"} and score is not None:
            raise ValueError("ABSTAINED/UNRESOLVED cannot carry a score")
    return disposition, stage, reasons, score, score_kind


def build_factor_snapshot(
    *,
    decision_id: str,
    decision_at: str,
    universe_as_of: str,
    expected_security_codes: Iterable[str],
    factor_inputs_by_security: Mapping[str, Mapping[str, Mapping[str, Any]]],
    dispositions_by_security: Mapping[str, Mapping[str, Any]] | None,
    manifest_hashes: frozenset[str],
    registry: Mapping[str, Any] = DEFAULT_FACTOR_REGISTRY,
) -> dict[str, Any]:
    decision_id = _required_text(decision_id, "decision_id")
    decision = parse_aware(decision_at, "decision_at")
    universe_time = parse_aware(universe_as_of, "universe_as_of")
    kuwait = ZoneInfo("Asia/Kuwait")
    if universe_time > decision or universe_time.astimezone(kuwait).date() != decision.astimezone(kuwait).date():
        raise ValueError("universe_as_of must be at/before decision on the same Kuwait civil date")
    expected = _sorted_security_codes(expected_security_codes)
    expected_set = set(expected)
    if set(factor_inputs_by_security) - expected_set:
        raise ValueError("factor inputs contain security outside frozen denominator")
    if dispositions_by_security is not None and set(dispositions_by_security) - expected_set:
        raise ValueError("dispositions contain security outside frozen denominator")
    definitions = _parse_factor_registry(registry)
    definition_map = {item.factor_id: item for item in definitions}
    rows: list[dict[str, Any]] = []
    for security_code in expected:
        supplied_factors = factor_inputs_by_security.get(security_code, {})
        if not isinstance(supplied_factors, Mapping):
            raise ValueError("security factor inputs must be an object")
        unknown_factors = set(supplied_factors) - set(definition_map)
        if unknown_factors:
            raise ValueError(f"unknown factor ids for {security_code}: {sorted(unknown_factors)}")
        factors = [
            _factor_row(
                definition,
                supplied_factors.get(definition.factor_id),
                decision_at=decision.isoformat(),
                manifest_hashes=manifest_hashes,
            )
            for definition in definitions
        ]
        observed = sum(item["status"] == "OBSERVED" for item in factors)
        missing = sum(item["status"] == "MISSING" for item in factors)
        not_applicable = sum(item["status"] == "NOT_APPLICABLE" for item in factors)
        rejected = sum(item["status"] == "REJECTED" for item in factors)
        required_ids = {item.factor_id for item in definitions if item.required_for_selection}
        required_satisfied = {
            item["factor_id"]
            for item in factors
            if item["factor_id"] in required_ids and item["status"] == "OBSERVED"
        }
        required_coverage = len(required_satisfied) / len(required_ids) if required_ids else 1.0
        trading_factor = next(item for item in factors if item["factor_id"] == "security_trading_status")
        selection_blocked = trading_factor["status"] != "OBSERVED" or trading_factor["value"] != "TRADING"
        disposition_input = None if dispositions_by_security is None else dispositions_by_security.get(security_code)
        disposition, stage, reasons, score, score_kind = _disposition_row(
            disposition_input,
            required_complete=required_coverage == 1.0,
            selection_allowed=not selection_blocked,
            any_rejected=bool(rejected),
        )
        rows.append(
            {
                "security_code": security_code,
                "factors": factors,
                "observed_factor_count": observed,
                "missing_factor_count": missing,
                "not_applicable_factor_count": not_applicable,
                "rejected_factor_count": rejected,
                "required_factor_coverage": required_coverage,
                "disposition": disposition,
                "first_failed_stage": stage,
                "reason_codes": reasons,
                "score": score,
                "score_kind": score_kind,
                "probability": None,
            }
        )
    snapshot = {
        "schema_version": "1.0",
        "product_id": PRODUCT_ID,
        "decision_id": decision_id,
        "decision_at": decision.isoformat(),
        "universe_as_of": universe_time.isoformat(),
        "registry_id": registry["registry_id"],
        "registry_version": registry["registry_version"],
        "registry_sha256": registry["registry_sha256"],
        "expected_security_codes": expected,
        "rows": rows,
        "denominator_reconciliation": {
            "status": "EXACT",
            "expected_count": len(expected),
            "row_count": len(rows),
            "missing_security_codes": [],
            "extra_security_codes": [],
            "duplicate_security_codes": [],
        },
        "claim_boundaries": {
            "score_is_probability": False,
            "missing_encoded_as_zero": False,
            "forecast_accuracy_claimed": False,
            "full_market_coverage_claimed": False,
            "recommendation_allowed": False,
        },
    }
    factor_snapshot_sha256 = _factor_snapshot_content_hash(snapshot)
    snapshot["factor_snapshot_sha256"] = factor_snapshot_sha256
    snapshot["snapshot_id"] = "factor-snapshot-" + factor_snapshot_sha256[:24]
    validation = validate_factor_snapshot(snapshot, registry=registry, manifest_hashes=manifest_hashes)
    if validation["status"] != "PASS":
        raise ValueError("invalid built factor snapshot: " + "; ".join(validation["errors"]))
    return snapshot


def validate_factor_snapshot(
    snapshot: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
    manifest_hashes: frozenset[str],
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        definitions = _parse_factor_registry(registry)
        expected_top = frozenset(
            {
                "schema_version",
                "snapshot_id",
                "factor_snapshot_sha256",
                "product_id",
                "decision_id",
                "decision_at",
                "universe_as_of",
                "registry_id",
                "registry_version",
                "registry_sha256",
                "expected_security_codes",
                "rows",
                "denominator_reconciliation",
                "claim_boundaries",
            }
        )
        _require_exact_keys(snapshot, expected_top, "factor snapshot")
        if snapshot["schema_version"] != "1.0" or snapshot["product_id"] != PRODUCT_ID:
            raise ValueError("unsupported factor snapshot schema/product")
        _required_text(snapshot["decision_id"], "decision_id")
        decision = parse_aware(snapshot["decision_at"], "decision_at")
        universe = parse_aware(snapshot["universe_as_of"], "universe_as_of")
        kuwait = ZoneInfo("Asia/Kuwait")
        if universe > decision or universe.astimezone(kuwait).date() != decision.astimezone(kuwait).date():
            raise ValueError("invalid universe_as_of cutoff")
        for field in ("registry_id", "registry_version", "registry_sha256"):
            if snapshot[field] != registry[field]:
                raise ValueError(f"snapshot {field} does not match registry")
        expected = _sorted_security_codes(snapshot["expected_security_codes"])
        if expected != snapshot["expected_security_codes"]:
            raise ValueError("expected_security_codes must use deterministic order")
        rows = snapshot["rows"]
        if not isinstance(rows, list):
            raise ValueError("factor snapshot rows must be a list")
        codes = [str(row.get("security_code", "")) for row in rows if isinstance(row, Mapping)]
        if len(rows) != len(expected) or set(codes) != set(expected) or len(codes) != len(set(codes)):
            raise ValueError("factor snapshot does not reconcile the full denominator")
        if codes != expected:
            raise ValueError("factor snapshot rows must use deterministic denominator order")
        definition_map = {item.factor_id: item for item in definitions}
        required_ids = {item.factor_id for item in definitions if item.required_for_selection}
        row_keys = frozenset(
            {
                "security_code",
                "factors",
                "observed_factor_count",
                "missing_factor_count",
                "not_applicable_factor_count",
                "rejected_factor_count",
                "required_factor_coverage",
                "disposition",
                "first_failed_stage",
                "reason_codes",
                "score",
                "score_kind",
                "probability",
            }
        )
        factor_keys = frozenset({"factor_id", "status", "value", "available_at", "evidence_hashes", "reason_codes"})
        for row_index, row in enumerate(rows):
            _require_exact_keys(row, row_keys, f"factor snapshot row {row_index}")
            factors = row["factors"]
            if not isinstance(factors, list):
                raise ValueError("factors must be a list")
            factor_ids = [str(item.get("factor_id", "")) for item in factors if isinstance(item, Mapping)]
            if factor_ids != list(definition_map):
                raise ValueError("factor row must contain registry definitions exactly once in canonical order")
            counts = {status: 0 for status in FACTOR_STATUSES}
            required_satisfied: set[str] = set()
            for factor_index, factor in enumerate(factors):
                _require_exact_keys(factor, factor_keys, f"factor {row_index}:{factor_index}")
                factor_id = str(factor["factor_id"])
                definition = definition_map[factor_id]
                status = _enum(factor["status"], "factor status", FACTOR_STATUSES)
                counts[status] += 1
                reasons = _reason_codes(
                    factor["reason_codes"],
                    "factor reason_codes",
                    minimum=1 if status != "OBSERVED" else 0,
                )
                if status == "MISSING":
                    if factor["value"] is not None or factor["available_at"] is not None or factor["evidence_hashes"]:
                        raise ValueError("MISSING factor must remain null and evidence-free")
                else:
                    hashes = _hashes(
                        factor["evidence_hashes"],
                        "factor evidence_hashes",
                        manifest_hashes=manifest_hashes,
                        minimum=1,
                    )
                    if list(hashes) != sorted(hashes):
                        raise ValueError("factor evidence_hashes must use canonical order")
                    available = parse_aware(factor["available_at"], "factor available_at")
                    if available > decision:
                        raise ValueError("factor contains look-ahead availability")
                    if status != "REJECTED" and decision - available > _factor_window(definition):
                        raise ValueError(f"{factor_id} availability falls outside its registry window")
                    if status == "OBSERVED":
                        _factor_value(definition, factor["value"])
                    elif factor["value"] is not None:
                        raise ValueError(f"{status} factor must not carry a value")
                    if factor_id in required_ids and status == "OBSERVED":
                        required_satisfied.add(factor_id)
                if status == "OBSERVED" and reasons and "OBSERVED_ZERO_WITH_COVERAGE" not in reasons:
                    # Observed factors may carry non-failure provenance codes, but they must remain machine-safe.
                    _reason_codes(list(reasons), "observed reason_codes")
                if list(reasons) != sorted(reasons):
                    raise ValueError("factor reason_codes must use canonical order")
            expected_counts = {
                "OBSERVED": row["observed_factor_count"],
                "MISSING": row["missing_factor_count"],
                "NOT_APPLICABLE": row["not_applicable_factor_count"],
                "REJECTED": row["rejected_factor_count"],
            }
            if counts != expected_counts:
                raise ValueError("factor status counts do not reconcile")
            coverage = len(required_satisfied) / len(required_ids) if required_ids else 1.0
            if abs(finite_number(row["required_factor_coverage"], "required_factor_coverage") - coverage) > 1e-12:
                raise ValueError("required_factor_coverage does not reconcile")
            disposition = _enum(row["disposition"], "disposition", DISPOSITIONS)
            stage = str(row["first_failed_stage"] or "").strip().upper() or None
            reason_codes = _reason_codes(
                row["reason_codes"],
                "row reason_codes",
                minimum=0 if disposition == "SELECTED" else 1,
            )
            if list(reason_codes) != sorted(reason_codes):
                raise ValueError("row reason_codes must use canonical order")
            score = None if row["score"] is None else finite_number(row["score"], "score")
            score_kind = str(row["score_kind"] or "").strip().upper() or None
            if row["probability"] is not None:
                raise ValueError("factor snapshot probability must remain null")
            if disposition == "SELECTED":
                if coverage != 1 or counts["REJECTED"] or stage is not None or reason_codes:
                    raise ValueError("invalid SELECTED disposition")
                if score is None or score_kind != "UNVALIDATED_RESEARCH_SCORE":
                    raise ValueError("SELECTED requires unvalidated research score")
                trading_factor = next(item for item in factors if item["factor_id"] == "security_trading_status")
                if trading_factor["status"] != "OBSERVED" or trading_factor["value"] != "TRADING":
                    raise ValueError("SELECTED security must be observed as TRADING")
            else:
                if stage not in FAILED_STAGES:
                    raise ValueError("non-selected row requires first_failed_stage")
                if score is None and score_kind is not None:
                    raise ValueError("score_kind cannot exist without score")
                if score is not None and score_kind != "UNVALIDATED_RESEARCH_SCORE":
                    raise ValueError("score kind is invalid")
                if disposition in {"ABSTAINED", "UNRESOLVED"} and score is not None:
                    raise ValueError("ABSTAINED/UNRESOLVED cannot carry score")
        reconciliation = snapshot["denominator_reconciliation"]
        expected_reconciliation = {
            "status": "EXACT",
            "expected_count": len(expected),
            "row_count": len(rows),
            "missing_security_codes": [],
            "extra_security_codes": [],
            "duplicate_security_codes": [],
        }
        if reconciliation != expected_reconciliation:
            raise ValueError("denominator reconciliation was forged or is incomplete")
        expected_claims = {
            "score_is_probability": False,
            "missing_encoded_as_zero": False,
            "forecast_accuracy_claimed": False,
            "full_market_coverage_claimed": False,
            "recommendation_allowed": False,
        }
        if snapshot["claim_boundaries"] != expected_claims:
            raise ValueError("factor snapshot claim boundaries were weakened")
        claimed_snapshot_hash = require_sha256(
            snapshot["factor_snapshot_sha256"], "factor_snapshot_sha256"
        )
        expected_snapshot_hash = _factor_snapshot_content_hash(snapshot)
        if claimed_snapshot_hash != expected_snapshot_hash:
            raise ValueError("factor snapshot content hash mismatch")
        expected_snapshot_id = "factor-snapshot-" + expected_snapshot_hash[:24]
        if snapshot["snapshot_id"] != expected_snapshot_id:
            raise ValueError("factor snapshot_id mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors))}


__all__ = [
    "ACTIVE_EVENT_LOOKBACK",
    "COMMUNITY_SENTIMENT_LOOKBACK",
    "CONTEXT_LOOKBACK",
    "ContextEvent",
    "DEFAULT_FACTOR_DEFINITIONS",
    "DEFAULT_FACTOR_REGISTRY",
    "EXPOSURE_TYPES",
    "FRESH_CATALYST_LOOKBACK",
    "FactorDefinition",
    "PRODUCT_ID",
    "SecurityExposure",
    "WINDOWS",
    "build_factor_snapshot",
    "context_event_from_dict",
    "deduplicate_context_events",
    "factor_registry_payload",
    "security_exposure_from_dict",
    "validate_factor_registry",
    "validate_factor_snapshot",
    "validate_security_exposures",
    "window_tags_for",
]
