"""Trusted source roles and claim-level evidence handling for Kuwait research.

This module produces research evidence only.  It cannot unlock probability-
bearing forecasts, authorize source access, average conflicts, or turn copied
news into independent corroboration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlsplit

from .foundation_io import load_strict_json_object
from .hashing import canonical_json_bytes
from .source_network import SourceNetworkCatalog
from .strict import parse_aware, require_sha256, sensitive_query_key


REGISTRY_PATH = Path("config/research_source_registry.json")
SOURCE_ROLES = frozenset(
    {
        "OFFICIAL_PRIMARY",
        "LICENSED_MARKET_DATA",
        "STRUCTURED_SECONDARY",
        "RELIABLE_NEWS",
        "COMMUNITY_DISCOVERY",
    }
)
CLAIM_TYPES = frozenset(
    {
        "OFFICIAL_FACT",
        "PRICE",
        "FUNDAMENTAL",
        "NEWS_EVENT",
        "MARKET_CONTEXT",
        "DISCOVERY",
        "SENTIMENT",
        "RISK_SIGNAL",
    }
)
CLASS_ROLE_MAP = {
    "PRIMARY_OFFICIAL": "OFFICIAL_PRIMARY",
    "PRIMARY_ISSUER": "OFFICIAL_PRIMARY",
    "LICENSED": "LICENSED_MARKET_DATA",
    "STRUCTURED_SECONDARY": "STRUCTURED_SECONDARY",
    "EDITORIAL": "RELIABLE_NEWS",
    "COMMUNITY": "COMMUNITY_DISCOVERY",
}
EXCLUDED_SOURCE_CLASSES = ("SEARCH_ROUTER", "STORAGE", "WEB_ARCHIVE")
ROLE_CEILINGS = {
    "OFFICIAL_PRIMARY": 98,
    "LICENSED_MARKET_DATA": 95,
    "STRUCTURED_SECONDARY": 72,
    "RELIABLE_NEWS": 82,
    "COMMUNITY_DISCOVERY": 30,
}
ALLOWED_CLAIMS = {
    "OFFICIAL_PRIMARY": (
        "OFFICIAL_FACT",
        "PRICE",
        "FUNDAMENTAL",
        "NEWS_EVENT",
        "MARKET_CONTEXT",
        "RISK_SIGNAL",
    ),
    "LICENSED_MARKET_DATA": ("PRICE", "FUNDAMENTAL", "MARKET_CONTEXT", "RISK_SIGNAL"),
    "STRUCTURED_SECONDARY": (
        "PRICE",
        "FUNDAMENTAL",
        "NEWS_EVENT",
        "MARKET_CONTEXT",
        "DISCOVERY",
        "RISK_SIGNAL",
    ),
    "RELIABLE_NEWS": ("NEWS_EVENT", "MARKET_CONTEXT", "DISCOVERY", "RISK_SIGNAL"),
    "COMMUNITY_DISCOVERY": ("DISCOVERY", "SENTIMENT", "RISK_SIGNAL"),
}
EXPECTED_BOUNDARIES = {
    "caller_supplied_source_role_is_authoritative": False,
    "registry_role_grants_access_rights": False,
    "credibility_score_is_stock_probability": False,
    "community_can_confirm_official_fact_or_price": False,
    "copied_news_counts_as_independent_confirmation": False,
    "conflicting_values_may_be_averaged": False,
    "research_network_may_unlock_strict_forecast": False,
}
OBSERVATION_BOUNDARIES = {
    "market_direction_probability_computed": False,
    "strict_forecast_unlocked": False,
    "access_rights_inferred_from_registry": False,
    "independent_confirmation_established_by_observation": False,
}
REQUIRED_NAMED_SOURCES = {
    "boursa_current": "OFFICIAL_PRIMARY",
    "cma_ifsah": "OFFICIAL_PRIMARY",
    "kcc_maqasa_official": "OFFICIAL_PRIMARY",
    "issuer_ir_verified": "OFFICIAL_PRIMARY",
    "ice_kuwait_archive": "LICENSED_MARKET_DATA",
    "authorized_broker_feed": "LICENSED_MARKET_DATA",
    "mubasher_kuwait": "STRUCTURED_SECONDARY",
    "investing_history": "STRUCTURED_SECONDARY",
    "reuters_middle_east": "RELIABLE_NEWS",
    "kuna": "RELIABLE_NEWS",
    "indexsignal_forum": "COMMUNITY_DISCOVERY",
}
INPUT_KEYS = frozenset(
    {
        "observation_id",
        "market",
        "source_id",
        "claimed_source_role",
        "security_code",
        "claim_id",
        "claim_key",
        "claim_type",
        "field_name",
        "claim_value",
        "claim_text",
        "publisher",
        "canonical_url",
        "published_at",
        "event_at",
        "observed_at",
        "fetched_at",
        "provider_as_of",
        "content_hash",
        "access_method",
        "transformation_history",
        "origin_id",
    }
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ResearchNetworkError(ValueError):
    """Raised when research evidence violates source, time, or lineage gates."""


@dataclass(frozen=True)
class TrustedSource:
    source_id: str
    source_role: str
    source_class: str
    independence_group: str
    domains: tuple[str, ...]
    access_methods: tuple[str, ...]
    credibility_ceiling: int
    rights_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _exact(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != keys:
        actual = frozenset(value) if isinstance(value, Mapping) else frozenset()
        raise ResearchNetworkError(
            f"{field} has missing={sorted(keys - actual)} unknown={sorted(actual - keys)}"
        )
    return value


def _registry(project_root: Path) -> tuple[dict[str, Any], bytes, SourceNetworkCatalog]:
    try:
        payload, content = load_strict_json_object(
            project_root / REGISTRY_PATH,
            field="trusted research source registry",
            max_bytes=512 * 1024,
        )
    except ValueError as exc:
        raise ResearchNetworkError(str(exc)) from exc
    catalog = SourceNetworkCatalog(project_root / "config")
    return payload, content, catalog


def validate_research_source_registry(project_root: Path | str) -> dict[str, Any]:
    root = Path(project_root).resolve()
    payload, content, catalog = _registry(root)
    _exact(
        payload,
        frozenset(
            {
                "schema_version",
                "registry_id",
                "market",
                "class_role_map",
                "excluded_source_classes",
                "required_named_sources",
                "role_policies",
                "source_credibility_caps",
                "claim_boundaries",
            }
        ),
        "research source registry",
    )
    if (
        payload["schema_version"] != "1.0"
        or payload["registry_id"] != "ku-bo-kuwait-trusted-source-roles-v1"
        or payload["market"] != "KUWAIT"
    ):
        raise ResearchNetworkError("research source registry identity changed")
    if payload["class_role_map"] != CLASS_ROLE_MAP:
        raise ResearchNetworkError("trusted source class-to-role mapping changed")
    if payload["excluded_source_classes"] != list(EXCLUDED_SOURCE_CLASSES):
        raise ResearchNetworkError("excluded source classes changed")
    if payload["claim_boundaries"] != EXPECTED_BOUNDARIES:
        raise ResearchNetworkError("research source claim boundaries were weakened")

    policies = payload["role_policies"]
    if not isinstance(policies, Mapping) or frozenset(policies) != SOURCE_ROLES:
        raise ResearchNetworkError("research source role policies are incomplete")
    for role in SOURCE_ROLES:
        row = _exact(
            policies[role],
            frozenset({"credibility_ceiling", "allowed_claim_types"}),
            f"role_policies.{role}",
        )
        if row["credibility_ceiling"] != ROLE_CEILINGS[role] or tuple(
            row["allowed_claim_types"]
        ) != ALLOWED_CLAIMS[role]:
            raise ResearchNetworkError(f"role policy changed for {role}")

    named_rows = payload["required_named_sources"]
    if not isinstance(named_rows, list):
        raise ResearchNetworkError("required named sources must be an array")
    named: dict[str, str] = {}
    for index, raw in enumerate(named_rows):
        row = _exact(raw, frozenset({"source_id", "source_role"}), f"named[{index}]")
        source_id = str(row["source_id"])
        role = str(row["source_role"])
        if source_id in named or role not in SOURCE_ROLES:
            raise ResearchNetworkError("required named source rows must be unique and canonical")
        named[source_id] = role
    if named != REQUIRED_NAMED_SOURCES:
        raise ResearchNetworkError("required named source registry is incomplete or reordered")

    mapped_count = 0
    for source_id, source in catalog.sources.items():
        mapped_role = CLASS_ROLE_MAP.get(source.source_class)
        if mapped_role is not None:
            mapped_count += 1
        elif source.source_class not in EXCLUDED_SOURCE_CLASSES:
            raise ResearchNetworkError(f"source class has no trusted role or exclusion: {source_id}")
    for source_id, expected_role in REQUIRED_NAMED_SOURCES.items():
        source = catalog.sources.get(source_id)
        if source is None or CLASS_ROLE_MAP.get(source.source_class) != expected_role:
            raise ResearchNetworkError(f"named source role does not match trusted catalog: {source_id}")

    caps = payload["source_credibility_caps"]
    if caps != {"indexsignal_forum": 25}:
        raise ResearchNetworkError("source-specific credibility caps changed")
    return {
        "schema_version": "1.0",
        "status": "PASS_TRUSTED_SOURCE_REGISTRY",
        "registry_id": payload["registry_id"],
        "registry_sha256": hashlib.sha256(content).hexdigest(),
        "mapped_source_count": mapped_count,
        "required_named_source_count": len(named),
        "roles": sorted(SOURCE_ROLES),
        "claim_boundaries": EXPECTED_BOUNDARIES,
    }


def resolve_trusted_source(
    project_root: Path | str,
    source_id: str,
    *,
    claimed_source_role: str | None = None,
) -> TrustedSource:
    root = Path(project_root).resolve()
    validate_research_source_registry(root)
    payload, _content, catalog = _registry(root)
    source = catalog.sources.get(str(source_id))
    if source is None:
        raise ResearchNetworkError("source_id is absent from the trusted catalog")
    role = CLASS_ROLE_MAP.get(source.source_class)
    if role is None:
        raise ResearchNetworkError("source_id is not admitted for analytical evidence")
    if claimed_source_role is not None and claimed_source_role != role:
        raise ResearchNetworkError("caller-supplied source_role conflicts with trusted registry")
    if source.requires_entitlement:
        rights_status = "ENTITLEMENT_REQUIRED"
    elif source.requires_runtime_domain_registry:
        rights_status = "RUNTIME_AUTHORITY_REQUIRED"
    else:
        rights_status = "TERMS_REVIEW_REQUIRED"
    source_cap = int(payload["source_credibility_caps"].get(source.source_id, ROLE_CEILINGS[role]))
    return TrustedSource(
        source_id=source.source_id,
        source_role=role,
        source_class=source.source_class,
        independence_group=source.independence_group,
        domains=tuple(source.domains),
        access_methods=tuple(source.access_modes),
        credibility_ceiling=min(ROLE_CEILINGS[role], source_cap),
        rights_status=rights_status,
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _time(value: Any, field: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    try:
        return parse_aware(value, field).astimezone(timezone.utc)
    except ValueError as exc:
        raise ResearchNetworkError(str(exc)) from exc


def _identifier(value: Any, field: str) -> str:
    text = str(value or "")
    if not _ID_RE.fullmatch(text):
        raise ResearchNetworkError(f"{field} must be a canonical identifier")
    return text


def _canonical_url(value: Any, source: TrustedSource) -> str:
    url = str(value or "")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ResearchNetworkError("canonical_url is malformed") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise ResearchNetworkError("canonical_url must be credential-free standard HTTPS")
    host = parsed.hostname.casefold().rstrip(".")
    if not source.domains or not any(
        host == domain.casefold() or host.endswith("." + domain.casefold())
        for domain in source.domains
    ):
        raise ResearchNetworkError("canonical_url is outside the trusted source domains")
    if any(sensitive_query_key(key) for key, _value in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ResearchNetworkError("canonical_url contains a sensitive query parameter")
    return url


def _json_value(value: Any) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
        return json.loads(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ResearchNetworkError("claim_value must be finite canonical JSON") from exc


def _transformations(value: Any, content_hash: str) -> tuple[list[dict[str, str]], str]:
    if not isinstance(value, list) or len(value) > 128:
        raise ResearchNetworkError("transformation_history must be a bounded array")
    previous_hash = content_hash
    previous_time: datetime | None = None
    rows: list[dict[str, str]] = []
    seen_steps: set[str] = set()
    for index, raw in enumerate(value):
        row = _exact(
            raw,
            frozenset({"step_id", "tool_version", "applied_at", "input_sha256", "output_sha256"}),
            f"transformation_history[{index}]",
        )
        step_id = _identifier(row["step_id"], f"transform[{index}].step_id")
        if step_id in seen_steps:
            raise ResearchNetworkError("transformation step IDs must be unique")
        seen_steps.add(step_id)
        tool_version = str(row["tool_version"] or "").strip()
        if not tool_version or len(tool_version) > 128:
            raise ResearchNetworkError("transformation tool_version is invalid")
        applied = _time(row["applied_at"], f"transform[{index}].applied_at")
        assert applied is not None
        if previous_time is not None and applied < previous_time:
            raise ResearchNetworkError("transformation timestamps are not monotonic")
        input_hash = require_sha256(row["input_sha256"], f"transform[{index}].input_sha256")
        output_hash = require_sha256(row["output_sha256"], f"transform[{index}].output_sha256")
        if input_hash != previous_hash:
            raise ResearchNetworkError("transformation hash chain is broken")
        rows.append(
            {
                "step_id": step_id,
                "tool_version": tool_version,
                "applied_at": _timestamp(applied),
                "input_sha256": input_hash,
                "output_sha256": output_hash,
            }
        )
        previous_hash = output_hash
        previous_time = applied
    return rows, previous_hash


def build_research_observation(
    project_root: Path | str,
    values: Mapping[str, Any],
    *,
    known_at: datetime | str,
) -> dict[str, Any]:
    """Validate and enrich one field/claim without trusting caller role metadata."""

    row = _exact(values, INPUT_KEYS, "research observation input")
    cutoff = _time(known_at, "known_at")
    assert cutoff is not None
    if row["market"] != "KUWAIT":
        raise ResearchNetworkError("research observation escaped the Kuwait market")
    source = resolve_trusted_source(
        project_root,
        str(row["source_id"]),
        claimed_source_role=str(row["claimed_source_role"]),
    )
    claim_type = str(row["claim_type"])
    if claim_type not in CLAIM_TYPES or claim_type not in ALLOWED_CLAIMS[source.source_role]:
        raise ResearchNetworkError("claim type is outside the trusted source role")
    access_method = str(row["access_method"])
    if access_method not in source.access_methods:
        raise ResearchNetworkError("access_method is outside the trusted source contract")
    canonical_url = _canonical_url(row["canonical_url"], source)

    published = _time(row["published_at"], "published_at", nullable=True)
    event = _time(row["event_at"], "event_at", nullable=True)
    observed = _time(row["observed_at"], "observed_at")
    fetched = _time(row["fetched_at"], "fetched_at")
    provider = _time(row["provider_as_of"], "provider_as_of", nullable=True)
    assert observed is not None and fetched is not None
    for field, value in (
        ("published_at", published),
        ("event_at", event),
        ("observed_at", observed),
        ("provider_as_of", provider),
    ):
        if value is not None and value > cutoff:
            raise ResearchNetworkError(f"TEMPORAL_LEAKAGE:{field}_AFTER_KNOWN_AT")
    if fetched < observed:
        raise ResearchNetworkError("fetched_at cannot precede observed_at")
    if published is not None and published > observed:
        raise ResearchNetworkError("observed_at cannot precede published_at")
    if provider is not None and provider > observed:
        raise ResearchNetworkError("observed_at cannot precede provider_as_of")
    if event is not None and event > observed:
        raise ResearchNetworkError("observed_at cannot precede event_at")

    content_hash = require_sha256(row["content_hash"], "content_hash")
    transformations, transformed_hash = _transformations(
        row["transformation_history"], content_hash
    )
    temporal_deduction = 0
    if published is None:
        temporal_deduction += 4
    if event is None:
        temporal_deduction += 3
    if provider is None and claim_type in {"PRICE", "FUNDAMENTAL", "MARKET_CONTEXT"}:
        temporal_deduction += 5
    rights_deduction = 15
    provenance_deduction = 0 if transformations else 2
    role_ceiling = ROLE_CEILINGS[source.source_role]
    source_cap = source.credibility_ceiling
    credibility = max(
        0,
        min(source_cap, role_ceiling - rights_deduction - temporal_deduction - provenance_deduction),
    )
    if source.source_role == "COMMUNITY_DISCOVERY":
        credibility = min(credibility, source_cap)
    admission_status = "WATCH_ONLY"

    claim_text = " ".join(str(row["claim_text"] or "").split())
    publisher = " ".join(str(row["publisher"] or "").split())
    origin_id = " ".join(str(row["origin_id"] or "").split())
    field_name = str(row["field_name"] or "").strip()
    security_code = str(row["security_code"] or "").strip()
    if not claim_text or not publisher or not origin_id or not field_name or not security_code:
        raise ResearchNetworkError("claim provenance text fields must be non-empty")
    if len(claim_text) > 20000 or len(publisher) > 512 or len(origin_id) > 512:
        raise ResearchNetworkError("claim provenance text field exceeds its bound")
    return {
        "schema_version": "1.0",
        "observation_id": _identifier(row["observation_id"], "observation_id"),
        "market": "KUWAIT",
        "source_id": source.source_id,
        "source_role": source.source_role,
        "source_independence_group": source.independence_group,
        "rights_status": source.rights_status,
        "security_code": security_code,
        "claim_id": _identifier(row["claim_id"], "claim_id"),
        "claim_key": _identifier(row["claim_key"], "claim_key"),
        "claim_type": claim_type,
        "field_name": field_name,
        "claim_value": _json_value(row["claim_value"]),
        "claim_text": claim_text,
        "publisher": publisher,
        "canonical_url": canonical_url,
        "published_at": _timestamp(published) if published is not None else None,
        "event_at": _timestamp(event) if event is not None else None,
        "observed_at": _timestamp(observed),
        "fetched_at": _timestamp(fetched),
        "provider_as_of": _timestamp(provider) if provider is not None else None,
        "known_at": _timestamp(cutoff),
        "content_hash": content_hash,
        "access_method": access_method,
        "transformation_history": transformations,
        "transformed_content_hash": transformed_hash,
        "origin_id": origin_id,
        "credibility_score": int(credibility),
        "credibility_components": {
            "role_ceiling": role_ceiling,
            "source_cap": source_cap,
            "rights_deduction": rights_deduction,
            "temporal_completeness_deduction": temporal_deduction,
            "provenance_deduction": provenance_deduction,
        },
        "credibility_score_is_stock_probability": False,
        "admission_status": admission_status,
        "claim_boundaries": OBSERVATION_BOUNDARIES,
    }


def _normalized_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())


def detect_copied_news(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Cluster declared/same-byte news origins without inflating confirmations."""

    rows = [dict(item) for item in observations if item.get("claim_type") == "NEWS_EVENT"]
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            same_origin = rows[left].get("origin_id") == rows[right].get("origin_id")
            same_bytes = rows[left].get("content_hash") == rows[right].get("content_hash")
            left_text = _normalized_text(str(rows[left].get("claim_text", "")))
            right_text = _normalized_text(str(rows[right].get("claim_text", "")))
            same_long_text = len(left_text) >= 80 and left_text == right_text
            if same_origin or same_bytes or same_long_text:
                union(left, right)

    groups: dict[int, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(find(index), []).append(row)
    clusters = []
    for members in groups.values():
        observation_ids = sorted(str(item["observation_id"]) for item in members)
        cluster_id = hashlib.sha256(canonical_json_bytes(observation_ids)).hexdigest()
        clusters.append(
            {
                "cluster_id": cluster_id,
                "observation_ids": observation_ids,
                "publisher_count": len({str(item["publisher"]) for item in members}),
                "independent_confirmation_units": 1,
                "copied_or_syndicated": len(members) > 1,
            }
        )
    return {
        "schema_version": "1.0",
        "status": "COPY_ORIGIN_ANALYZED",
        "news_observation_count": len(rows),
        "independent_origin_count": len(clusters),
        "clusters": sorted(clusters, key=lambda item: item["cluster_id"]),
        "copied_news_counts_as_independent_confirmation": False,
    }


def build_conflict_ledger(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Record contradictory field values; never synthesize an average."""

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for raw in observations:
        row = dict(raw)
        key = (str(row.get("security_code")), str(row.get("claim_key")), str(row.get("field_name")))
        groups.setdefault(key, []).append(row)
    conflicts: list[dict[str, Any]] = []
    for (security_code, claim_key, field_name), rows in groups.items():
        values: dict[bytes, list[dict[str, Any]]] = {}
        for row in rows:
            values.setdefault(canonical_json_bytes(row.get("claim_value")), []).append(row)
        if len(values) <= 1:
            continue
        claim_types = {str(row.get("claim_type")) for row in rows}
        disposition = "ABSTAIN" if "PRICE" in claim_types else "WATCH"
        conflicts.append(
            {
                "conflict_id": hashlib.sha256(
                    canonical_json_bytes([security_code, claim_key, field_name])
                ).hexdigest(),
                "security_code": security_code,
                "claim_key": claim_key,
                "field_name": field_name,
                "observation_ids": sorted(str(row.get("observation_id")) for row in rows),
                "distinct_value_count": len(values),
                "disposition": disposition,
                "aggregation_method": "NO_AVERAGING",
                "resolved_value": None,
            }
        )
    overall = "ABSTAIN" if any(row["disposition"] == "ABSTAIN" for row in conflicts) else "WATCH" if conflicts else "CLEAR"
    return {
        "schema_version": "1.0",
        "status": "CONFLICT_LEDGER_BUILT",
        "conflict_count": len(conflicts),
        "overall_disposition": overall,
        "conflicts": sorted(conflicts, key=lambda item: item["conflict_id"]),
        "conflicting_values_averaged": False,
    }


__all__ = [
    "CLAIM_TYPES",
    "ResearchNetworkError",
    "SOURCE_ROLES",
    "TrustedSource",
    "build_conflict_ledger",
    "build_research_observation",
    "detect_copied_news",
    "resolve_trusted_source",
    "validate_research_source_registry",
]
