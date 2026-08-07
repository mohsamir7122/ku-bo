from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .strict import parse_aware, require_sha256


SOURCE_ROLES = frozenset({"OFFICIAL_FILING", "REGULATOR_OR_EXCHANGE", "ISSUER_PRIMARY", "NEWS_CONTEXT", "FINANCIAL_CONTEXT", "FORUM", "TELEGRAM", "SOCIAL"})
RELATION_TYPES = frozenset({"STANDALONE", "ORIGINAL", "SUPPLEMENTARY", "CORRECTIVE", "REPUBLISHED"})
FACT_ROLES = frozenset({"OFFICIAL_FILING", "REGULATOR_OR_EXCHANGE", "ISSUER_PRIMARY"})
SOCIAL_ROLES = frozenset({"FORUM", "TELEGRAM", "SOCIAL"})


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    security_code: str
    source_id: str
    source_role: str
    event_type: str
    direction: str
    novelty: float
    event_at: str
    published_at: str
    first_available_at: str
    captured_at: str
    content_hash: str
    evidence_hash: str
    relation_type: str
    original_event_id: str | None
    raw_text: str


def event_from_dict(row: dict[str, Any], *, manifest_hashes: frozenset[str]) -> EventRecord:
    event_id = str(row.get("event_id", "")).strip()
    security_code = str(row.get("security_code", "")).strip()
    source_id = str(row.get("source_id", "")).strip()
    if not event_id or not security_code or not source_id:
        raise ValueError("event_id, security_code, and source_id are required")
    role = str(row.get("source_role", "")).upper()
    relation = str(row.get("relation_type", "STANDALONE")).upper()
    if role not in SOURCE_ROLES or relation not in RELATION_TYPES:
        raise ValueError("invalid source_role or relation_type")
    original = str(row.get("original_event_id", "")).strip() or None
    if relation in {"SUPPLEMENTARY", "CORRECTIVE", "REPUBLISHED"} and not original:
        raise ValueError("dependent event requires original_event_id")
    novelty = float(row.get("novelty", 0.0))
    if not 0 <= novelty <= 1:
        raise ValueError("novelty must be in [0,1]")
    event_at = parse_aware(row.get("event_at"), "event_at")
    published = parse_aware(row.get("published_at"), "published_at")
    available = parse_aware(row.get("first_available_at"), "first_available_at")
    captured = parse_aware(row.get("captured_at"), "captured_at")
    if available < published or captured < available:
        raise ValueError("event timestamp ordering is invalid")
    content_hash = require_sha256(row.get("content_hash"), "content_hash")
    evidence_hash = require_sha256(row.get("evidence_hash"), "evidence_hash")
    if evidence_hash not in manifest_hashes:
        raise ValueError("event evidence_hash does not resolve")
    return EventRecord(
        event_id=event_id,
        security_code=security_code,
        source_id=source_id,
        source_role=role,
        event_type=str(row.get("event_type", "UNKNOWN")).upper(),
        direction=str(row.get("direction", "UNKNOWN")).upper(),
        novelty=novelty,
        event_at=event_at.isoformat(),
        published_at=published.isoformat(),
        first_available_at=available.isoformat(),
        captured_at=captured.isoformat(),
        content_hash=content_hash,
        evidence_hash=evidence_hash,
        relation_type=relation,
        original_event_id=original,
        raw_text=str(row.get("raw_text", "")),
    )


def canonicalize_events(events: Iterable[EventRecord]) -> list[dict[str, Any]]:
    rows = list(events)
    by_id: dict[str, EventRecord] = {}
    for row in rows:
        if row.event_id in by_id:
            raise ValueError(f"duplicate event_id: {row.event_id}")
        by_id[row.event_id] = row
    for row in rows:
        if row.original_event_id and row.original_event_id not in by_id:
            raise ValueError(f"missing original event: {row.original_event_id}")
        if row.original_event_id and by_id[row.original_event_id].security_code != row.security_code:
            raise ValueError("event relation crosses security identities")
    referenced_parents = {row.original_event_id for row in rows if row.original_event_id}
    groups: dict[tuple[str, str], list[EventRecord]] = {}
    for row in rows:
        canonical = row.original_event_id or (row.event_id if row.event_id in referenced_parents else row.content_hash)
        groups.setdefault((row.security_code, canonical), []).append(row)
    output: list[dict[str, Any]] = []
    for (security_code, canonical), group in groups.items():
        group.sort(key=lambda item: (parse_aware(item.first_available_at, "first_available_at"), item.event_id))
        first = group[0]
        output.append(
            {
                "canonical_event_id": canonical,
                "security_code": security_code,
                "event_type": first.event_type,
                "direction": first.direction,
                "novelty": first.novelty,
                "event_at": min(group, key=lambda item: parse_aware(item.event_at, "event_at")).event_at,
                "first_published_at": min(group, key=lambda item: parse_aware(item.published_at, "published_at")).published_at,
                "first_available_at": first.first_available_at,
                "last_captured_at": max(group, key=lambda item: parse_aware(item.captured_at, "captured_at")).captured_at,
                "source_ids": sorted({item.source_id for item in group}),
                "source_roles": sorted({item.source_role for item in group}),
                "evidence_hashes": sorted({item.evidence_hash for item in group}),
                "diffusion_count": len(group),
                "source_diversity": len({item.source_id for item in group}),
                "official_fact_seen": any(item.source_role in FACT_ROLES for item in group),
                "event_ids": [item.event_id for item in group],
            }
        )
    output.sort(key=lambda item: (item["first_available_at"], item["security_code"], item["canonical_event_id"]))
    return output


__all__ = ["EventRecord", "canonicalize_events", "event_from_dict"]
