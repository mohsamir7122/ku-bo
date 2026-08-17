from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .disclosure_reaction_common import (
    DisclosureReactionError,
    aware,
    exact_fields,
    mapping,
    safe_https_url,
    sha256,
    text,
)

_FIELDS = {
    "schema_version", "data_domain", "immutability", "record_id",
    "security_code", "canonical_cluster_id", "record_type", "headline",
    "published_at", "available_at", "archived_at", "official_source_url",
    "evidence_sha256", "corrects_record_id", "supersedes_record_id",
}


def validate_historical_disclosure_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = mapping(raw, "historical_disclosure")
    exact_fields(value, _FIELDS, "historical_disclosure")
    if value["schema_version"] != "1.0":
        raise DisclosureReactionError("historical_disclosure.schema_version must equal 1.0")
    if value["data_domain"] != "HISTORICAL_DISCLOSURE_ARCHIVE":
        raise DisclosureReactionError("historical disclosure data_domain mismatch")
    if value["immutability"] != "APPEND_ONLY":
        raise DisclosureReactionError("historical disclosure archive must be APPEND_ONLY")
    record_type = text(value["record_type"], "historical_disclosure.record_type", 32)
    if record_type not in {"ORIGINAL", "CORRECTION", "SUPPLEMENT", "WITHDRAWAL"}:
        raise DisclosureReactionError(f"unsupported disclosure record_type: {record_type}")
    published = aware(value["published_at"], "historical_disclosure.published_at")
    available = aware(value["available_at"], "historical_disclosure.available_at")
    archived = aware(value["archived_at"], "historical_disclosure.archived_at")
    if available < published:
        raise DisclosureReactionError("disclosure available_at precedes published_at")
    if archived < available:
        raise DisclosureReactionError("disclosure archived_at precedes available_at")
    corrects = value["corrects_record_id"]
    supersedes = value["supersedes_record_id"]
    if corrects is not None:
        corrects = text(corrects, "historical_disclosure.corrects_record_id", 128)
    if supersedes is not None:
        supersedes = text(supersedes, "historical_disclosure.supersedes_record_id", 128)
    if record_type == "ORIGINAL" and (corrects is not None or supersedes is not None):
        raise DisclosureReactionError("ORIGINAL disclosure cannot correct or supersede another record")
    if record_type == "CORRECTION" and corrects is None:
        raise DisclosureReactionError("CORRECTION requires corrects_record_id")
    if record_type in {"SUPPLEMENT", "WITHDRAWAL"} and corrects is None and supersedes is None:
        raise DisclosureReactionError(f"{record_type} requires lineage to an earlier record")
    record_id = text(value["record_id"], "historical_disclosure.record_id", 128)
    if record_id in {corrects, supersedes}:
        raise DisclosureReactionError("historical disclosure cannot reference itself")
    security_code = text(value["security_code"], "historical_disclosure.security_code", 64).upper()
    if security_code != "HUMANSOFT":
        raise DisclosureReactionError("historical disclosure security_code must equal HUMANSOFT")
    return {
        **dict(value),
        "record_id": record_id,
        "security_code": security_code,
        "canonical_cluster_id": text(value["canonical_cluster_id"], "historical_disclosure.canonical_cluster_id", 128),
        "record_type": record_type,
        "headline": text(value["headline"], "historical_disclosure.headline", 1000),
        "official_source_url": safe_https_url(value["official_source_url"], "historical_disclosure.official_source_url"),
        "evidence_sha256": sha256(value["evidence_sha256"], "historical_disclosure.evidence_sha256"),
        "corrects_record_id": corrects,
        "supersedes_record_id": supersedes,
    }


__all__ = ["validate_historical_disclosure_record"]
