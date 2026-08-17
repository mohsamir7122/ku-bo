from __future__ import annotations

from collections.abc import Mapping, Sequence
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

_ITEM_FIELDS = {
    "opinion_id", "published_at", "source_kind", "source_group",
    "source_url", "stance", "relevance", "evidence_sha256",
}
_FIELDS = {
    "schema_version", "data_domain", "immutability", "archive_id",
    "security_code", "canonical_cluster_id", "captured_through",
    "items", "evidence_sha256",
}


def validate_public_opinion_archive(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = mapping(raw, "public_opinion_archive")
    exact_fields(value, _FIELDS, "public_opinion_archive")
    if value["schema_version"] != "1.0":
        raise DisclosureReactionError("public opinion archive schema_version must equal 1.0")
    if value["data_domain"] != "HISTORICAL_PUBLIC_OPINION_ARCHIVE":
        raise DisclosureReactionError("public opinion archive data_domain mismatch")
    if value["immutability"] != "FROZEN_AS_OF_CAPTURE":
        raise DisclosureReactionError("public opinion archive must be FROZEN_AS_OF_CAPTURE")
    security_code = text(value["security_code"], "public_opinion_archive.security_code", 64).upper()
    if security_code != "HUMANSOFT":
        raise DisclosureReactionError("public opinion archive security_code must equal HUMANSOFT")
    captured_through = aware(value["captured_through"], "public_opinion_archive.captured_through")
    items = value["items"]
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise DisclosureReactionError("public_opinion_archive.items must be an array")
    seen: set[str] = set()
    validated_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        row = mapping(item, f"public_opinion_archive.items[{index}]")
        exact_fields(row, _ITEM_FIELDS, f"public_opinion_archive.items[{index}]")
        opinion_id = text(row["opinion_id"], f"public_opinion_archive.items[{index}].opinion_id", 128)
        if opinion_id in seen:
            raise DisclosureReactionError(f"duplicate opinion_id: {opinion_id}")
        seen.add(opinion_id)
        published = aware(row["published_at"], f"public_opinion_archive.items[{index}].published_at")
        if published > captured_through:
            raise DisclosureReactionError("public opinion item postdates captured_through")
        source_kind = text(row["source_kind"], f"public_opinion_archive.items[{index}].source_kind", 64)
        if source_kind not in {"NEWSPAPER", "FINANCIAL_MEDIA", "SOCIAL_MEDIA", "ANALYST_COMMENTARY", "FORUM"}:
            raise DisclosureReactionError(f"unsupported public opinion source_kind: {source_kind}")
        stance = text(row["stance"], f"public_opinion_archive.items[{index}].stance", 32)
        if stance not in {"POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"}:
            raise DisclosureReactionError(f"unsupported public opinion stance: {stance}")
        relevance = text(row["relevance"], f"public_opinion_archive.items[{index}].relevance", 64)
        if relevance not in {"DIRECT_DISCLOSURE_REACTION", "COMPANY_CONTEXT", "RUMOR_OR_SPECULATION"}:
            raise DisclosureReactionError(f"unsupported public opinion relevance: {relevance}")
        validated_items.append({
            "opinion_id": opinion_id,
            "published_at": row["published_at"],
            "source_kind": source_kind,
            "source_group": text(row["source_group"], f"public_opinion_archive.items[{index}].source_group", 128),
            "source_url": safe_https_url(row["source_url"], f"public_opinion_archive.items[{index}].source_url"),
            "stance": stance,
            "relevance": relevance,
            "evidence_sha256": sha256(row["evidence_sha256"], f"public_opinion_archive.items[{index}].evidence_sha256"),
        })
    return {
        **dict(value),
        "archive_id": text(value["archive_id"], "public_opinion_archive.archive_id", 128),
        "security_code": security_code,
        "canonical_cluster_id": text(value["canonical_cluster_id"], "public_opinion_archive.canonical_cluster_id", 128),
        "items": validated_items,
        "evidence_sha256": sha256(value["evidence_sha256"], "public_opinion_archive.evidence_sha256"),
    }


__all__ = ["validate_public_opinion_archive"]
