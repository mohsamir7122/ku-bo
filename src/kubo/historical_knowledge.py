"""Fail-closed planning contracts for Kuwait's historical knowledge layer.

This module plans research work; it does not claim that a year, company, case,
or source has been collected.  Materialized evidence remains a separate future
stage and must carry capture time, content hashes, and source-specific rights.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


LAYER_IDS = (
    "KUWAIT_YEARBOOK_1500_PRESENT",
    "COMMERCIAL_CRISIS_CHRONOLOGY_1927_PRESENT",
    "COMPANY_LIFECYCLE_1970_PRESENT",
    "COMPANY_MEDIA_HISTORY_1980_PRESENT",
    "COMPANY_CASES_ROLLING_20Y",
    "RECENT_ECONOMIC_EVENTS_ROLLING_5Y",
)

SOURCE_TIERS = frozenset(
    {
        "PRIMARY_OFFICIAL",
        "PRIMARY_ARCHIVE",
        "INTERGOVERNMENTAL",
        "EDITORIAL",
        "COMMUNITY",
        "ROUTING_ONLY",
    }
)
ACCESS_MODES = frozenset(
    {
        "PUBLIC_PAGE",
        "PUBLIC_DOWNLOAD",
        "INTERACTIVE_PUBLIC",
        "AUTHENTICATED",
        "PHYSICAL_ARCHIVE",
        "LICENSED",
    }
)
SOURCE_ROLES = frozenset(
    {
        "NATIONAL_HISTORY",
        "OFFICIAL_GAZETTE",
        "COMMERCIAL_REGISTRY",
        "COMPANY_IDENTITY",
        "REGULATORY_ACTION",
        "COURT_RECORD",
        "ECONOMIC_STATISTICS",
        "COMPANY_DISCLOSURE",
        "NEWS_ARCHIVE",
        "SOCIAL_ROUTING",
        "COMMUNITY_ROUTING",
        "WEB_ARCHIVE",
        "SEARCH_ROUTING",
    }
)
FACT_TYPES = frozenset(
    {
        "HISTORICAL_EVENT",
        "COMPANY_REGISTRATION",
        "FOUNDER_IDENTITY",
        "COMPANY_STATUS",
        "REGULATORY_ACTION",
        "LEGAL_ALLEGATION",
        "COURT_OUTCOME",
        "NEWS_MENTION",
        "SOCIAL_SENTIMENT",
    }
)

_SOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


def _strict_object(payload: Any, *, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be an object")
    missing = sorted(keys - set(payload))
    extra = sorted(set(payload) - keys)
    if missing or extra:
        raise ValueError(f"{label} has missing={missing} extra={extra}")
    return payload


def _strict_json(path: Path) -> Mapping[str, Any]:
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load strict JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


@dataclass(frozen=True)
class HistoricalSource:
    source_id: str
    name: str
    organization: str
    tier: str
    roles: tuple[str, ...]
    base_urls: tuple[str, ...]
    languages: tuple[str, ...]
    earliest_year: int | None
    access_modes: tuple[str, ...]
    rights_note: str
    automation_note: str
    capability_status: str


@dataclass(frozen=True)
class ResearchLayer:
    layer_id: str
    start_rule: str
    end_rule: str
    grain: str
    source_roles: tuple[str, ...]
    company_enumeration_required: bool
    decision_use: str
    query_templates: tuple[str, ...]


class HistoricalKnowledgeCatalog:
    """Validated source and layer definitions with conservative claim rules."""

    _SOURCE_KEYS = frozenset(
        {
            "source_id",
            "name",
            "organization",
            "tier",
            "roles",
            "base_urls",
            "languages",
            "earliest_year",
            "access_modes",
            "rights_note",
            "automation_note",
            "capability_status",
        }
    )
    _LAYER_KEYS = frozenset(
        {
            "layer_id",
            "start_rule",
            "end_rule",
            "grain",
            "source_roles",
            "company_enumeration_required",
            "decision_use",
            "query_templates",
        }
    )

    def __init__(self, config_root: Path):
        source_payload = _strict_json(config_root / "historical_sources.json")
        layer_payload = _strict_json(config_root / "historical_research_layers.json")
        self.sources = self._load_sources(source_payload)
        self.layers = self._load_layers(layer_payload)

    @classmethod
    def _load_sources(cls, payload: Mapping[str, Any]) -> tuple[HistoricalSource, ...]:
        root = _strict_object(
            payload,
            keys=frozenset({"schema_version", "capability_claim", "sources"}),
            label="historical source registry",
        )
        if root["schema_version"] != "1.0" or root["capability_claim"] != "DEFINED_ONLY":
            raise ValueError("historical source registry must remain DEFINED_ONLY schema 1.0")
        rows = root["sources"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("historical source registry requires sources")
        loaded: list[HistoricalSource] = []
        seen: set[str] = set()
        for index, value in enumerate(rows):
            row = _strict_object(value, keys=cls._SOURCE_KEYS, label=f"source[{index}]")
            source_id = str(row["source_id"])
            if not _SOURCE_ID_RE.fullmatch(source_id) or source_id in seen:
                raise ValueError("source_id must be unique lower snake case")
            seen.add(source_id)
            tier = str(row["tier"])
            roles = tuple(str(item) for item in row["roles"])
            modes = tuple(str(item) for item in row["access_modes"])
            urls = tuple(str(item) for item in row["base_urls"])
            if tier not in SOURCE_TIERS or not roles or set(roles) - SOURCE_ROLES:
                raise ValueError(f"{source_id} has invalid tier or roles")
            if not modes or set(modes) - ACCESS_MODES:
                raise ValueError(f"{source_id} has invalid access_modes")
            if not urls or any(urlparse(url).scheme != "https" or not urlparse(url).netloc for url in urls):
                raise ValueError(f"{source_id} requires HTTPS base_urls")
            if row["capability_status"] != "DEFINED_ONLY":
                raise ValueError(f"{source_id} capability cannot exceed DEFINED_ONLY")
            earliest = row["earliest_year"]
            if earliest is not None and (not isinstance(earliest, int) or earliest < 1):
                raise ValueError(f"{source_id}.earliest_year is invalid")
            loaded.append(
                HistoricalSource(
                    source_id=source_id,
                    name=str(row["name"]),
                    organization=str(row["organization"]),
                    tier=tier,
                    roles=roles,
                    base_urls=urls,
                    languages=tuple(str(item) for item in row["languages"]),
                    earliest_year=earliest,
                    access_modes=modes,
                    rights_note=str(row["rights_note"]),
                    automation_note=str(row["automation_note"]),
                    capability_status="DEFINED_ONLY",
                )
            )
        return tuple(loaded)

    @classmethod
    def _load_layers(cls, payload: Mapping[str, Any]) -> tuple[ResearchLayer, ...]:
        root = _strict_object(
            payload,
            keys=frozenset({"schema_version", "layers"}),
            label="historical research layers",
        )
        if root["schema_version"] != "1.0" or not isinstance(root["layers"], list):
            raise ValueError("historical research layers must be schema 1.0")
        loaded: list[ResearchLayer] = []
        for index, value in enumerate(root["layers"]):
            row = _strict_object(value, keys=cls._LAYER_KEYS, label=f"layer[{index}]")
            roles = tuple(str(item) for item in row["source_roles"])
            queries = tuple(str(item).strip() for item in row["query_templates"])
            if set(roles) - SOURCE_ROLES:
                raise ValueError("layer contains an invalid source role")
            if row["grain"] not in {"YEAR", "COMPANY_YEAR"}:
                raise ValueError("layer grain is invalid")
            if row["decision_use"] != "CONTEXT_ONLY":
                raise ValueError("historical layers cannot directly produce a trading decision")
            if len(queries) < 2 or any("{year}" not in item for item in queries):
                raise ValueError("each historical layer requires bilingual or alternate year query templates")
            loaded.append(
                ResearchLayer(
                    layer_id=str(row["layer_id"]),
                    start_rule=str(row["start_rule"]),
                    end_rule=str(row["end_rule"]),
                    grain=str(row["grain"]),
                    source_roles=roles,
                    company_enumeration_required=bool(row["company_enumeration_required"]),
                    decision_use="CONTEXT_ONLY",
                    query_templates=queries,
                )
            )
        if tuple(item.layer_id for item in loaded) != LAYER_IDS:
            raise ValueError("historical layer order or membership is invalid")
        return tuple(loaded)

    def report(self) -> dict[str, Any]:
        tier_counts = {tier: 0 for tier in sorted(SOURCE_TIERS)}
        for source in self.sources:
            tier_counts[source.tier] += 1
        return {
            "status": "PASS_CONTRACT",
            "readiness_status": "DEFINED_ONLY",
            "source_count": len(self.sources),
            "layer_count": len(self.layers),
            "tier_counts": tier_counts,
            "claim_boundaries": {
                "historical_corpus_collected": False,
                "company_universe_enumerated": False,
                "legal_records_collected": False,
                "direct_trading_decision_allowed": False,
            },
        }

    def sources_for_roles(self, roles: Iterable[str], *, year: int) -> tuple[str, ...]:
        required = set(roles)
        return tuple(
            source.source_id
            for source in self.sources
            if required.intersection(source.roles)
            and (source.earliest_year is None or source.earliest_year <= year)
        )


def _start_year(rule: str, current_year: int) -> int:
    fixed = {"FIXED_1500": 1500, "FIXED_1927": 1927, "FIXED_1970": 1970, "FIXED_1980": 1980}
    if rule in fixed:
        return fixed[rule]
    if rule == "ROLLING_20_CALENDAR_YEARS":
        return current_year - 19
    if rule == "ROLLING_5_CALENDAR_YEARS":
        return current_year - 4
    raise ValueError(f"unsupported start rule: {rule}")


def compile_research_plan(catalog: HistoricalKnowledgeCatalog, *, as_of: date) -> dict[str, Any]:
    """Create a deterministic annual plan, including explicit uncollected coverage."""

    if as_of > date.today():
        raise ValueError("as_of cannot be in the future")
    tasks: list[dict[str, Any]] = []
    layer_summaries: list[dict[str, Any]] = []
    for layer in catalog.layers:
        first = _start_year(layer.start_rule, as_of.year)
        if layer.end_rule != "AS_OF_YEAR":
            raise ValueError("unsupported end rule")
        for year in range(first, as_of.year + 1):
            task_id = hashlib.sha256(f"{layer.layer_id}:{year}:{as_of.isoformat()}".encode()).hexdigest()[:24]
            tasks.append(
                {
                    "task_id": f"hist-{task_id}",
                    "layer_id": layer.layer_id,
                    "year": year,
                    "grain": layer.grain,
                    "coverage_status": "NOT_COLLECTED",
                    "source_ids": list(catalog.sources_for_roles(layer.source_roles, year=year)),
                    "queries": [item.replace("{year}", str(year)) for item in layer.query_templates],
                    "company_enumeration_required": layer.company_enumeration_required,
                    "decision_use": "CONTEXT_ONLY",
                }
            )
        layer_summaries.append(
            {
                "layer_id": layer.layer_id,
                "start_year": first,
                "end_year": as_of.year,
                "year_count": as_of.year - first + 1,
                "grain": layer.grain,
                "coverage_status": "NOT_COLLECTED",
            }
        )
    plan = {
        "schema_version": "1.0",
        "plan_id": "",
        "as_of": as_of.isoformat(),
        "status": "PLANNED_NOT_EXECUTED",
        "decision_use": "CONTEXT_ONLY",
        "layers": layer_summaries,
        "tasks": tasks,
        "claim_boundaries": {
            "complete_history_claim_allowed": False,
            "complete_company_universe_claim_allowed": False,
            "legal_guilt_inference_allowed": False,
            "social_media_fact_confirmation_allowed": False,
            "direct_trading_decision_allowed": False,
        },
    }
    canonical = json.dumps({**plan, "plan_id": ""}, sort_keys=True, separators=(",", ":")).encode()
    plan["plan_id"] = "hist-plan-" + hashlib.sha256(canonical).hexdigest()[:24]
    return plan


def validate_claim_support(
    catalog: HistoricalKnowledgeCatalog,
    *,
    fact_type: str,
    source_ids: Iterable[str],
    legal_status: str | None = None,
) -> None:
    """Reject unsupported identity, legal, status, and social-media claims."""

    normalized = fact_type.strip().upper()
    if normalized not in FACT_TYPES:
        raise ValueError("fact_type is invalid")
    source_map = {item.source_id: item for item in catalog.sources}
    try:
        sources = tuple(source_map[item] for item in source_ids)
    except KeyError as exc:
        raise ValueError("claim references an unknown historical source") from exc
    if not sources:
        raise ValueError("claim requires at least one source")
    roles = set().union(*(set(item.roles) for item in sources))
    tiers = {item.tier for item in sources}
    if normalized in {"COMPANY_REGISTRATION", "FOUNDER_IDENTITY", "COMPANY_STATUS"}:
        if not {"COMMERCIAL_REGISTRY", "OFFICIAL_GAZETTE", "COMPANY_DISCLOSURE"}.intersection(roles):
            raise ValueError("company identity/status requires primary registry, gazette, or filing evidence")
        if not tiers.intersection({"PRIMARY_OFFICIAL", "PRIMARY_ARCHIVE"}):
            raise ValueError("company identity/status requires a primary source")
    if normalized in {"LEGAL_ALLEGATION", "COURT_OUTCOME", "REGULATORY_ACTION"}:
        if not {"COURT_RECORD", "REGULATORY_ACTION", "OFFICIAL_GAZETTE"}.intersection(roles):
            raise ValueError("legal claims require court, regulator, or official-gazette evidence")
        if legal_status not in {"ALLEGED", "REFERRED", "CHARGED", "DECIDED", "APPEALED", "FINAL"}:
            raise ValueError("legal claims require an explicit procedural status")
    if normalized == "SOCIAL_SENTIMENT":
        return
    if tiers.issubset({"COMMUNITY", "ROUTING_ONLY"}):
        raise ValueError("community/routing sources cannot establish factual claims")


def parse_as_of(value: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("as_of must be YYYY-MM-DD") from exc
    return parsed
