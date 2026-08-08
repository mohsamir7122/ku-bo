from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .hashing import hash_json, sha256_file
from .provenance import evidence_packet_hash as compute_evidence_packet_hash
from .runtime_trust import RuntimeTrustError, RuntimeTrustRegistry
from .strict import finite_number, https_url, parse_aware, parse_iso_date, require_sha256, resolved_regular_file, safe_relative_path, strict_bool


SOURCE_CLASSES = frozenset(
    {
        "PRIMARY_OFFICIAL",
        "PRIMARY_ISSUER",
        "STRUCTURED_SECONDARY",
        "EDITORIAL",
        "COMMUNITY",
        "WEB_ARCHIVE",
        "SEARCH_ROUTER",
        "LICENSED",
        "STORAGE",
    }
)
CAPABILITY_STATUSES = frozenset(
    {
        "DEFINED_ONLY",
        "CAPTURE_ONLY",
        "PARSER_IMPLEMENTED",
        "END_TO_END_TESTED",
        "LIVE_OPERATIONAL",
    }
)
CAPTURE_CAPABILITIES = frozenset(
    {
        "CATALOG_ONLY",
        "PUBLIC_HTTP_OR_USER_EXPORT",
        "AUTHORIZED_EXTERNAL",
        "LICENSED_EXTERNAL",
    }
)
FIXTURE_EVIDENCE_CLASSES = frozenset(
    {"NONE", "GENERATED_CONTRACT_FIXTURE", "RECORDED_AUTHORIZED_FIXTURE"}
)
ACCESS_STATES = frozenset({"AVAILABLE", "PARTIAL", "BLOCKED", "ERROR", "AUTH_REQUIRED", "UNTESTED"})
QUERY_STATUSES = frozenset({"QUALIFIED", "ZERO_RESULT", "BLOCKED", "ERROR", "AUTH_REQUIRED", "PARSER_DRIFT", "DATA_QUALITY_REJECTED"})
SCOPES = frozenset({"NAMED_SECURITIES", "CANDIDATE_SET", "FULL_MARKET"})
SIGNAL_KINDS = frozenset({"CATALYST", "PRICE_ACTIVITY", "TECHNICAL", "FUNDAMENTAL", "SENTIMENT", "LIQUIDITY", "RISK", "ARCHIVE_CONTEXT"})
DIRECTIONS = frozenset({"POSITIVE", "NEGATIVE", "NEUTRAL"})
CAPTURE_MODES = frozenset({"PROSPECTIVE", "ARCHIVE_CAPTURE", "SEARCH_INDEX", "USER_EXPORT"})
TIMING_GRADES = ("A", "B", "C", "D", "E", "F")
CONTRIBUTING_QUERY_STATUSES = frozenset({"QUALIFIED", "ZERO_RESULT"})
NON_EVIDENCE_ROLES = frozenset({"SEARCH_ROUTER", "STORAGE_ONLY"})
ROLE_SIGNAL_KINDS = {
    "IDENTITY_REFERENCE": frozenset({"RISK", "ARCHIVE_CONTEXT"}),
    "OFFICIAL_EVENT": frozenset({"CATALYST", "FUNDAMENTAL", "RISK"}),
    "ISSUER_PRIMARY": frozenset({"CATALYST", "FUNDAMENTAL", "RISK"}),
    "MARKET_DISCOVERY": frozenset({"PRICE_ACTIVITY", "TECHNICAL", "LIQUIDITY", "RISK"}),
    "PRICE_HISTORY": frozenset({"PRICE_ACTIVITY", "TECHNICAL", "LIQUIDITY", "RISK"}),
    "FUNDAMENTAL_ARCHIVE": frozenset({"CATALYST", "FUNDAMENTAL", "RISK", "ARCHIVE_CONTEXT"}),
    "NEWS_ARCHIVE": frozenset({"CATALYST", "FUNDAMENTAL", "SENTIMENT", "RISK", "ARCHIVE_CONTEXT"}),
    "COMMUNITY_SENTIMENT": frozenset({"SENTIMENT", "RISK"}),
    "WEB_ARCHIVE": frozenset({"ARCHIVE_CONTEXT"}),
    "SEARCH_ROUTER": frozenset(),
    "EXECUTION_TAPE": frozenset({"PRICE_ACTIVITY", "TECHNICAL", "LIQUIDITY", "RISK"}),
    "STORAGE_ONLY": frozenset(),
}
CLASS_RELIABILITY = {
    "PRIMARY_OFFICIAL": 1.00,
    "PRIMARY_ISSUER": 0.95,
    "LICENSED": 0.95,
    "STRUCTURED_SECONDARY": 0.70,
    "EDITORIAL": 0.65,
    "COMMUNITY": 0.35,
    "WEB_ARCHIVE": 0.25,
    "SEARCH_ROUTER": 0.00,
    "STORAGE": 0.00,
}

# `fact_eligibility` is intentionally more specific than the coarse role and
# signal contracts. Every finding must declare a type that its source is
# explicitly allowed to support.
EVIDENCE_SOURCE_CLASSES = frozenset(
    {
        "PRIMARY_OFFICIAL",
        "PRIMARY_ISSUER",
        "STRUCTURED_SECONDARY",
        "EDITORIAL",
        "COMMUNITY",
        "WEB_ARCHIVE",
        "LICENSED",
    }
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _host_allowed(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in domains)


def _grade_not_stronger(actual: str, ceiling: str) -> bool:
    return actual in TIMING_GRADES and ceiling in TIMING_GRADES and TIMING_GRADES.index(actual) >= TIMING_GRADES.index(ceiling)


def _is_substantive_finding(finding: "ResearchFinding") -> bool:
    """Return whether a finding can satisfy evidence coverage or diversity.

    Neutral and zero-strength/materiality rows remain in the packet for audit,
    but cannot make a weak packet appear better covered.
    """

    return (
        finding.direction != "NEUTRAL"
        and finding.strength > 0
        and finding.materiality > 0
        and finding.signal_kind != "ARCHIVE_CONTEXT"
    )


def _requires_external_runtime_trust(source: "NetworkSource") -> bool:
    return (
        source.requires_runtime_domain_registry
        or not source.enabled_by_default
        or source.source_class == "LICENSED"
        or source.requires_entitlement
    )


def _ticker_alias(value: Any) -> str:
    """Validate the deliberately small display-alias grammar.

    Security identity is the official numeric code.  Tickers are display
    aliases, so accepting whitespace, Markdown delimiters, or control
    characters here would add ambiguity without improving identity coverage.
    """

    if not isinstance(value, str) or not 1 <= len(value) <= 32:
        raise ValueError("ticker must contain 1..32 Unicode alphanumeric or ._- characters")
    if any(not (character.isalnum() or character in "._-") for character in value):
        raise ValueError("ticker must contain 1..32 Unicode alphanumeric or ._- characters")
    return value.upper()


@dataclass(frozen=True)
class NetworkSource:
    source_id: str
    name: str
    source_class: str
    roles: frozenset[str]
    domains: tuple[str, ...]
    start_urls: tuple[str, ...]
    access_modes: frozenset[str]
    independence_group: str
    timing_grade_ceiling: str
    fact_eligibility: frozenset[str]
    enabled_by_default: bool
    requires_runtime_domain_registry: bool
    requires_entitlement: bool
    notes: str


@dataclass(frozen=True)
class ResearchPolicy:
    profile_id: str
    products: frozenset[str]
    required_role_quorum: dict[str, int]
    confirmation_roles: frozenset[str]
    minimum_independent_sources: int
    minimum_independent_community_sources: int
    max_source_age_hours: float
    signal_weights: dict[str, float]
    sentiment_contribution_cap: float
    candidate_minimum_coverage: float
    full_market_coverage_required: float
    allowed_output: str
    probability_allowed: bool
    recommendation_allowed: bool


@dataclass(frozen=True)
class SourceCapability:
    status: str
    capture: str
    parser_ids: tuple[str, ...]
    fixture_evidence: str
    live_operational: bool


class SourceNetworkCatalog:
    def __init__(self, config_dir: Path):
        network = _load_json(config_dir / "source_network.json")
        policy_payload = _load_json(config_dir / "research_policies.json")
        if network.get("schema_version") != "3.0" or policy_payload.get("schema_version") != "3.0":
            raise ValueError("source network and research policy schemas must be 3.0")
        roles = network.get("role_vocabulary")
        if not isinstance(roles, list) or not roles:
            raise ValueError("role_vocabulary must be a non-empty list")
        self.roles = frozenset(str(item) for item in roles)
        if self.roles != frozenset(ROLE_SIGNAL_KINDS):
            raise ValueError("role_vocabulary does not match the enforced role-to-signal contract")
        self.sources = self._load_sources(network.get("sources"))
        self.capabilities = self._load_capabilities(
            _load_json(config_dir / "source_capabilities.json")
        )
        allowed_outputs = frozenset(str(item) for item in policy_payload.get("allowed_outputs", []))
        forbidden_outputs = frozenset(str(item) for item in policy_payload.get("forbidden_outputs", []))
        if not allowed_outputs or allowed_outputs & forbidden_outputs:
            raise ValueError("research output allowlist is empty or overlaps the forbidden outputs")
        self.policies, self.product_to_policy = self._load_policies(
            policy_payload.get("profiles"),
            allowed_outputs=allowed_outputs,
            forbidden_outputs=forbidden_outputs,
        )

    def _load_capabilities(self, payload: dict[str, Any]) -> dict[str, SourceCapability]:
        if payload.get("schema_version") != "1.0":
            raise ValueError("source capability matrix schema must be 1.0")
        if set(payload) != {
            "schema_version",
            "default_capability",
            "overrides",
            "claim_boundaries",
        }:
            raise ValueError("source capability matrix has unknown or missing fields")
        boundaries = payload.get("claim_boundaries")
        required_boundaries = {
            "catalog_entry_is_connector": False,
            "capture_success_is_parser_success": False,
            "contract_fixture_is_live_acceptance": False,
            "parser_implemented_is_live_operational": False,
        }
        if boundaries != required_boundaries:
            raise ValueError("source capability claim boundaries must all remain false")
        default = payload.get("default_capability")
        overrides = payload.get("overrides")
        if not isinstance(default, dict) or not isinstance(overrides, dict):
            raise ValueError("source capability default and overrides must be objects")
        unknown = sorted(set(overrides) - set(self.sources))
        if unknown:
            raise ValueError("source capability overrides reference unknown sources: " + ",".join(unknown))

        result: dict[str, SourceCapability] = {}
        for source_id in self.sources:
            row = overrides.get(source_id, default)
            if not isinstance(row, dict) or set(row) != {
                "status",
                "capture",
                "parser_ids",
                "fixture_evidence",
                "live_operational",
            }:
                raise ValueError(f"invalid source capability fields: {source_id}")
            status = str(row.get("status", ""))
            capture = str(row.get("capture", ""))
            fixture = str(row.get("fixture_evidence", ""))
            parsers = tuple(str(item) for item in row.get("parser_ids", []))
            live = strict_bool(row.get("live_operational"), f"{source_id}.live_operational")
            if status not in CAPABILITY_STATUSES or capture not in CAPTURE_CAPABILITIES:
                raise ValueError(f"invalid source capability state: {source_id}")
            if fixture not in FIXTURE_EVIDENCE_CLASSES or len(parsers) != len(set(parsers)):
                raise ValueError(f"invalid source parser/fixture capability: {source_id}")
            if any(not parser_id or len(parser_id) > 128 for parser_id in parsers):
                raise ValueError(f"invalid parser_id: {source_id}")
            if status in {"PARSER_IMPLEMENTED", "END_TO_END_TESTED", "LIVE_OPERATIONAL"} and not parsers:
                raise ValueError(f"parser-capable source has no parser_ids: {source_id}")
            if status in {"DEFINED_ONLY", "CAPTURE_ONLY"} and parsers:
                raise ValueError(f"non-parser source declares parser_ids: {source_id}")
            if live != (status == "LIVE_OPERATIONAL"):
                raise ValueError(f"live_operational conflicts with status: {source_id}")
            if live and fixture != "RECORDED_AUTHORIZED_FIXTURE":
                raise ValueError(f"live source lacks recorded authorized fixture evidence: {source_id}")
            result[source_id] = SourceCapability(status, capture, parsers, fixture, live)
        return result

    def _load_sources(self, rows: Any) -> dict[str, NetworkSource]:
        if not isinstance(rows, list) or not rows:
            raise ValueError("sources must be a non-empty list")
        result: dict[str, NetworkSource] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"source_{index} is not an object")
            source_id = str(row.get("source_id", "")).strip()
            if not source_id or source_id in result:
                raise ValueError(f"duplicate or empty source_id: {source_id}")
            source_class = str(row.get("source_class", ""))
            if source_class not in SOURCE_CLASSES:
                raise ValueError(f"unsupported source_class: {source_class}")
            source_roles = frozenset(str(item) for item in row.get("roles", []))
            if not source_roles or source_roles - self.roles:
                raise ValueError(f"invalid roles for {source_id}: {sorted(source_roles - self.roles)}")
            domains = tuple(str(item).lower() for item in row.get("domains", []))
            urls = tuple(https_url(item, f"{source_id}.start_url") for item in row.get("start_urls", []))
            if domains and any(not _host_allowed(url, domains) for url in urls):
                raise ValueError(f"start URL outside registered domains: {source_id}")
            ceiling = str(row.get("timing_grade_ceiling", ""))
            if ceiling not in TIMING_GRADES:
                raise ValueError(f"invalid timing grade ceiling: {source_id}")
            enabled = strict_bool(row.get("enabled_by_default"), f"{source_id}.enabled_by_default")
            requires_runtime_registry = strict_bool(
                row.get("requires_runtime_domain_registry", False),
                f"{source_id}.requires_runtime_domain_registry",
            )
            requires_entitlement = strict_bool(
                row.get("requires_entitlement", False),
                f"{source_id}.requires_entitlement",
            )
            source = NetworkSource(
                source_id=source_id,
                name=str(row.get("name", source_id)),
                source_class=source_class,
                roles=source_roles,
                domains=domains,
                start_urls=urls,
                access_modes=frozenset(str(item) for item in row.get("access_modes", [])),
                independence_group=str(row.get("independence_group", "")).strip(),
                timing_grade_ceiling=ceiling,
                fact_eligibility=frozenset(str(item) for item in row.get("fact_eligibility", [])),
                enabled_by_default=enabled,
                requires_runtime_domain_registry=requires_runtime_registry,
                requires_entitlement=requires_entitlement,
                notes=str(row.get("notes", "")),
            )
            if not source.independence_group or not source.access_modes:
                raise ValueError(f"source lacks independence group or access modes: {source_id}")
            if source.source_class in {"SEARCH_ROUTER", "STORAGE"} and source.fact_eligibility:
                raise ValueError(f"non-evidence source declares fact eligibility: {source_id}")
            if source.source_class in EVIDENCE_SOURCE_CLASSES and not source.fact_eligibility:
                raise ValueError(f"evidence source lacks fact eligibility: {source_id}")
            if source.source_class == "COMMUNITY" and source.roles != frozenset({"COMMUNITY_SENTIMENT"}):
                raise ValueError(f"community source declares non-community roles: {source_id}")
            if source.source_class == "WEB_ARCHIVE" and source.roles != frozenset({"WEB_ARCHIVE"}):
                raise ValueError(f"web archive declares non-archive roles: {source_id}")
            if source.source_class == "SEARCH_ROUTER" and source.roles != frozenset({"SEARCH_ROUTER"}):
                raise ValueError(f"search router declares evidence roles: {source_id}")
            if source.source_class == "STORAGE" and source.roles != frozenset({"STORAGE_ONLY"}):
                raise ValueError(f"storage source declares evidence roles: {source_id}")
            if "OFFICIAL_EVENT" in source.roles and source.source_class not in {
                "PRIMARY_OFFICIAL",
                "PRIMARY_ISSUER",
            }:
                raise ValueError(f"non-primary source declares OFFICIAL_EVENT: {source_id}")
            if "ISSUER_PRIMARY" in source.roles and source.source_class != "PRIMARY_ISSUER":
                raise ValueError(f"non-issuer source declares ISSUER_PRIMARY: {source_id}")
            if "EXECUTION_TAPE" in source.roles and source.source_class != "LICENSED":
                raise ValueError(f"non-licensed source declares EXECUTION_TAPE: {source_id}")
            if source.source_class == "LICENSED" and not source.requires_entitlement:
                raise ValueError(f"licensed source must require entitlement: {source_id}")
            if (
                not source.domains
                and source.source_class not in {"SEARCH_ROUTER", "STORAGE"}
                and not source.requires_runtime_domain_registry
            ):
                raise ValueError(f"dynamic-domain source lacks runtime registry requirement: {source_id}")
            result[source_id] = source
        return result

    def _load_policies(
        self,
        rows: Any,
        *,
        allowed_outputs: frozenset[str],
        forbidden_outputs: frozenset[str],
    ) -> tuple[dict[str, ResearchPolicy], dict[str, ResearchPolicy]]:
        if not isinstance(rows, list) or not rows:
            raise ValueError("profiles must be a non-empty list")
        profiles: dict[str, ResearchPolicy] = {}
        products: dict[str, ResearchPolicy] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"profile_{index} is not an object")
            profile_id = str(row.get("profile_id", "")).strip()
            if not profile_id or profile_id in profiles:
                raise ValueError(f"duplicate or empty profile_id: {profile_id}")
            product_ids = frozenset(str(item) for item in row.get("products", []))
            if not product_ids or product_ids & products.keys():
                raise ValueError(f"empty or duplicated product policy mapping: {profile_id}")
            quorum = {str(key): int(value) for key, value in dict(row.get("required_role_quorum", {})).items()}
            if not quorum or any(role not in self.roles or count <= 0 for role, count in quorum.items()):
                raise ValueError(f"invalid role quorum: {profile_id}")
            weights = {str(key): float(value) for key, value in dict(row.get("signal_weights", {})).items()}
            if set(weights) - SIGNAL_KINDS or any(value < 0 for value in weights.values()) or not 0.99 <= sum(weights.values()) <= 1.01:
                raise ValueError(f"invalid signal weights: {profile_id}")
            confirmation_roles = frozenset(str(item) for item in row.get("confirmation_roles", []))
            if not confirmation_roles or confirmation_roles - {
                "OFFICIAL_EVENT",
                "ISSUER_PRIMARY",
            }:
                raise ValueError(f"invalid official confirmation roles: {profile_id}")
            allowed_output = str(row.get("allowed_output", ""))
            if allowed_output not in allowed_outputs or allowed_output in forbidden_outputs:
                raise ValueError(f"forbidden or unregistered research output: {profile_id}")
            policy = ResearchPolicy(
                profile_id=profile_id,
                products=product_ids,
                required_role_quorum=quorum,
                confirmation_roles=confirmation_roles,
                minimum_independent_sources=int(row.get("minimum_independent_sources", 1)),
                minimum_independent_community_sources=int(row.get("minimum_independent_community_sources", 0)),
                max_source_age_hours=finite_number(row.get("max_source_age_hours"), f"{profile_id}.max_source_age_hours", minimum=0.01),
                signal_weights=weights,
                sentiment_contribution_cap=finite_number(row.get("sentiment_contribution_cap"), f"{profile_id}.sentiment_contribution_cap", minimum=0, maximum=1),
                candidate_minimum_coverage=finite_number(row.get("candidate_minimum_coverage"), f"{profile_id}.candidate_minimum_coverage", minimum=0, maximum=1),
                full_market_coverage_required=finite_number(row.get("full_market_coverage_required"), f"{profile_id}.full_market_coverage_required", minimum=0, maximum=1),
                allowed_output=allowed_output,
                probability_allowed=strict_bool(row.get("probability_allowed"), f"{profile_id}.probability_allowed"),
                recommendation_allowed=strict_bool(row.get("recommendation_allowed"), f"{profile_id}.recommendation_allowed"),
            )
            if policy.minimum_independent_sources <= 0 or policy.probability_allowed or policy.recommendation_allowed:
                raise ValueError(f"research-only profile violates claim boundary: {profile_id}")
            if weights.get("SENTIMENT", 0) > policy.sentiment_contribution_cap + 1e-12:
                raise ValueError(f"sentiment weight exceeds cap: {profile_id}")
            profiles[profile_id] = policy
            for product_id in product_ids:
                products[product_id] = policy
        return profiles, products

    def policy_for(self, product_id: str) -> ResearchPolicy:
        try:
            return self.product_to_policy[product_id]
        except KeyError as exc:
            raise KeyError(f"no source-network policy for product: {product_id}") from exc

    def report(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for capability in self.capabilities.values():
            status_counts[capability.status] = status_counts.get(capability.status, 0) + 1
        return {
            "status": "PASS",
            "sources": len(self.sources),
            "profiles": len(self.policies),
            "products": len(self.product_to_policy),
            "roles": sorted(self.roles),
            "capability_status_counts": dict(sorted(status_counts.items())),
            "parser_sources": sorted(
                source_id
                for source_id, capability in self.capabilities.items()
                if capability.parser_ids
            ),
            "live_operational_sources": sorted(
                source_id
                for source_id, capability in self.capabilities.items()
                if capability.live_operational
            ),
            "claim_boundaries": {
                "probability_allowed": False,
                "recommendation_allowed": False,
                "community_is_official_truth": False,
                "search_snippet_is_evidence": False,
                "catalog_entry_is_connector": False,
                "capture_success_is_parser_success": False,
                "contract_fixture_is_live_acceptance": False,
                "parser_implemented_is_live_operational": False,
            },
        }


@dataclass(frozen=True)
class NetworkArtifact:
    path: str
    sha256: str
    size_bytes: int
    source_id: str
    source_url: str
    observed_at: datetime
    capture_kind: str
    runtime_authority_registry_id: str = ""
    runtime_authority_domain: str = ""
    runtime_authority_subject_id: str = ""
    runtime_authority_security_codes: tuple[str, ...] = ()
    runtime_authority_evidence_sha256: str = ""


@dataclass(frozen=True)
class SourceObservation:
    source_id: str
    state: str
    access_mode: str
    attempted_at: datetime
    query_status: str
    roles_observed: frozenset[str]
    qualified_items: int
    zero_result: bool
    raw_sha256s: tuple[str, ...]
    data_quality_flags: tuple[str, ...]
    limitations: tuple[str, ...]
    entitlement_id: str
    entitlement_evidence_sha256: str
    enabled_for_run: bool
    activation_id: str
    activation_evidence_sha256: str

    @property
    def contributes(self) -> bool:
        return self.state in {"AVAILABLE", "PARTIAL"} and self.query_status in CONTRIBUTING_QUERY_STATUSES and not self.data_quality_flags


@dataclass(frozen=True)
class ResearchFinding:
    finding_id: str
    security_code: str
    ticker: str
    source_id: str
    source_url: str
    published_at: datetime
    available_at: datetime
    capture_mode: str
    timing_grade: str
    raw_sha256: str
    evidence_roles: frozenset[str]
    signal_kind: str
    direction: str
    strength: float
    materiality: float
    origin_id: str
    event_key: str
    claim_text: str
    fact_type: str


@dataclass(frozen=True)
class NetworkRunContract:
    run_id: str
    product_id: str
    decision_at: datetime
    timezone: str
    scope: str
    expected_universe_count: int
    covered_universe_count: int
    max_requests: int
    max_raw_bytes: int
    max_wall_seconds: int
    usage_requests: int
    usage_raw_bytes: int
    usage_wall_seconds: int

    @property
    def universe_coverage(self) -> float:
        return self.covered_universe_count / self.expected_universe_count if self.expected_universe_count else 0.0


@dataclass(frozen=True)
class NetworkRunValidation:
    status: str
    structural_errors: tuple[str, ...]
    coverage_gaps: tuple[str, ...]
    warnings: tuple[str, ...]
    contract: NetworkRunContract | None
    policy: ResearchPolicy
    artifacts: tuple[NetworkArtifact, ...]
    observations: tuple[SourceObservation, ...]
    findings: tuple[ResearchFinding, ...]
    role_coverage: dict[str, int]
    independent_sources: int
    official_confirmation_available: bool
    exact_universe_reconciled: bool
    evidence_packet_hash: str | None = None
    runtime_trust_required: bool = False
    sensitive_source_ids: tuple[str, ...] = ()
    runtime_trust_registry_id: str | None = None
    runtime_trust_registry_hash: str | None = None
    runtime_trust_key_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        source_states = {item.source_id: item.state for item in self.observations}
        source_query_statuses = {
            item.source_id: item.query_status for item in self.observations
        }
        degraded_source_ids = sorted(
            item.source_id
            for item in self.observations
            if item.state != "AVAILABLE"
            or item.query_status not in CONTRIBUTING_QUERY_STATUSES
            or bool(item.data_quality_flags)
        )
        return {
            "status": self.status,
            "structural_errors": list(self.structural_errors),
            "coverage_gaps": list(self.coverage_gaps),
            "warnings": list(self.warnings),
            "contract": None
            if self.contract is None
            else {
                **asdict(self.contract),
                "decision_at": self.contract.decision_at.isoformat(),
                "universe_coverage": self.contract.universe_coverage,
            },
            "policy": self.policy.profile_id,
            "artifact_count": len(self.artifacts),
            "source_observation_count": len(self.observations),
            "source_states": dict(sorted(source_states.items())),
            "source_query_statuses": dict(sorted(source_query_statuses.items())),
            "degraded_source_ids": degraded_source_ids,
            "finding_count": len(self.findings),
            "role_coverage": dict(sorted(self.role_coverage.items())),
            "independent_sources": self.independent_sources,
            "official_confirmation_available": self.official_confirmation_available,
            "exact_universe_reconciled": self.exact_universe_reconciled,
            "evidence_packet_hash": self.evidence_packet_hash,
            "runtime_trust_required": self.runtime_trust_required,
            "sensitive_source_ids": list(self.sensitive_source_ids),
            "runtime_trust_registry_id": self.runtime_trust_registry_id,
            "runtime_trust_registry_hash": self.runtime_trust_registry_hash,
            "runtime_trust_key_id": self.runtime_trust_key_id,
            "claim_boundaries": {
                "allowed_output": self.policy.allowed_output if self.status == "PASS" else "WATCH_OR_ABSTAIN",
                "probability_allowed": False,
                "recommendation_allowed": False,
                # Exact identity is necessary but per-security role coverage
                # is evaluated by the ranking stage.  The pipeline may promote
                # this conservative boundary only after that check succeeds.
                "full_market_claim_allowed": False,
            },
        }


class SourceNetworkRunValidator:
    def __init__(
        self,
        run_root: Path,
        catalog: SourceNetworkCatalog,
        product_id: str,
        *,
        runtime_trust_registry: RuntimeTrustRegistry | None = None,
    ):
        self.run_root = run_root.resolve()
        self.catalog = catalog
        self.product_id = product_id
        self.policy = catalog.policy_for(product_id)
        self.runtime_trust_registry = runtime_trust_registry

    def validate(self) -> NetworkRunValidation:
        errors: list[str] = []
        gaps: list[str] = []
        warnings: list[str] = []
        contract = self._load_contract(errors)
        artifacts, _artifact_hashes = self._load_manifest(contract, errors)
        observations = self._load_observations(contract, artifacts, errors, warnings)
        findings = self._load_findings(contract, observations, artifacts, errors, warnings)
        sensitive_source_ids = tuple(
            sorted(
                {
                    item.source_id
                    for item in observations
                    if item.contributes
                    and _requires_external_runtime_trust(self.catalog.sources[item.source_id])
                }
            )
        )
        runtime_trust_required = bool(sensitive_source_ids)
        if runtime_trust_required and self.runtime_trust_registry is None:
            errors.append("RUNTIME_TRUST_REGISTRY_REQUIRED")
        exact_universe_reconciled = self._validate_universe(
            contract, artifacts, observations, findings, errors, warnings
        )

        findings_by_source: dict[str, list[ResearchFinding]] = {}
        for finding in findings:
            findings_by_source.setdefault(finding.source_id, []).append(finding)

        role_publisher_groups: dict[str, set[str]] = {role: set() for role in self.catalog.roles}
        role_origin_groups: dict[str, set[str]] = {role: set() for role in self.catalog.roles}
        role_event_groups: dict[str, set[str]] = {role: set() for role in self.catalog.roles}
        contributing_groups: set[str] = set()
        community_groups: set[str] = set()
        for observation in observations:
            if not observation.contributes:
                continue
            source = self.catalog.sources[observation.source_id]
            # Run-level coverage records that a role was actually inspected.
            # Candidate-level coverage is stricter in research_rank.py and
            # excludes neutral/zero-value findings from score and diversity.
            source_findings = findings_by_source.get(observation.source_id, [])
            if observation.query_status == "ZERO_RESULT":
                # A documented zero result is useful collection evidence, but
                # it is not affirmative market evidence and cannot fill a
                # role or source-diversity quorum.
                continue
            substantive_findings = [
                finding
                for finding in source_findings
                if _is_substantive_finding(finding)
            ]
            if not substantive_findings:
                warnings.append(f"QUALIFIED_SOURCE_WITHOUT_RANKABLE_FINDINGS:{observation.source_id}")
                continue
            if (
                source.source_class == "COMMUNITY"
                and self.policy.sentiment_contribution_cap <= 0
            ):
                continue
            contributing_groups.add(source.independence_group)
            if source.source_class == "COMMUNITY":
                community_groups.add(source.independence_group)
            for finding in substantive_findings:
                for role in finding.evidence_roles - NON_EVIDENCE_ROLES:
                    role_publisher_groups[role].add(source.independence_group)
                    role_origin_groups[role].add(finding.origin_id)
                    role_event_groups[role].add(finding.event_key)

        role_coverage: dict[str, int] = {}
        for role in self.catalog.roles:
            qualified_count = min(
                len(role_publisher_groups[role]),
                len(role_origin_groups[role]),
                len(role_event_groups[role]),
            )
            if qualified_count:
                role_coverage[role] = qualified_count
        for role, minimum in self.policy.required_role_quorum.items():
            actual = role_coverage.get(role, 0)
            if actual < minimum:
                gaps.append(f"ROLE_QUORUM:{role}:{actual}/{minimum}")
        if len(contributing_groups) < self.policy.minimum_independent_sources:
            gaps.append(f"INDEPENDENT_SOURCES:{len(contributing_groups)}/{self.policy.minimum_independent_sources}")
        if len(community_groups) < self.policy.minimum_independent_community_sources:
            gaps.append(f"COMMUNITY_SOURCES:{len(community_groups)}/{self.policy.minimum_independent_community_sources}")
        if not findings:
            gaps.append("NO_VALIDATED_FINDINGS")

        official_confirmation_available = any(
            _is_substantive_finding(finding)
            and bool(finding.evidence_roles & self.policy.confirmation_roles)
            for finding in findings
        )
        if not official_confirmation_available:
            warnings.append("OFFICIAL_OR_ISSUER_CONFIRMATION_UNAVAILABLE")
        for observation in observations:
            source = self.catalog.sources[observation.source_id]
            if (
                source.roles & self.policy.confirmation_roles
                and not observation.contributes
            ):
                warnings.append(
                    "OFFICIAL_SOURCE_UNAVAILABLE:"
                    f"{observation.source_id}:{observation.state}:{observation.query_status}"
                )
        if contract and contract.scope == "FULL_MARKET" and not exact_universe_reconciled:
            warnings.append("FULL_MARKET_LABEL_FORBIDDEN_UNRECONCILED_UNIVERSE")

        packet_hash: str | None = None
        if not errors:
            try:
                packet_hash = compute_evidence_packet_hash(self.run_root)
            except (OSError, TypeError, ValueError) as exc:
                errors.append(f"INVALID_EVIDENCE_PACKET_PROVENANCE:{exc}")

        status = "BLOCKED" if errors else "PARTIAL" if gaps else "PASS"
        return NetworkRunValidation(
            status=status,
            structural_errors=tuple(sorted(set(errors))),
            coverage_gaps=tuple(sorted(set(gaps))),
            warnings=tuple(sorted(set(warnings))),
            contract=contract,
            policy=self.policy,
            artifacts=tuple(artifacts),
            observations=tuple(observations),
            findings=tuple(findings),
            role_coverage=role_coverage,
            independent_sources=len(contributing_groups),
            official_confirmation_available=official_confirmation_available,
            exact_universe_reconciled=exact_universe_reconciled,
            evidence_packet_hash=packet_hash,
            runtime_trust_required=runtime_trust_required,
            sensitive_source_ids=sensitive_source_ids,
            runtime_trust_registry_id=(
                self.runtime_trust_registry.registry_id
                if runtime_trust_required and self.runtime_trust_registry is not None
                else None
            ),
            runtime_trust_registry_hash=(
                self.runtime_trust_registry.content_sha256
                if runtime_trust_required and self.runtime_trust_registry is not None
                else None
            ),
            runtime_trust_key_id=(
                self.runtime_trust_registry.authenticated_key_id
                if runtime_trust_required and self.runtime_trust_registry is not None
                else None
            ),
        )

    def _validate_universe(
        self,
        contract: NetworkRunContract | None,
        artifacts: list[NetworkArtifact],
        observations: list[SourceObservation],
        findings: list[ResearchFinding],
        errors: list[str],
        warnings: list[str],
    ) -> bool:
        """Require current, evidence-linked security identity in every scope.

        A partially covered full-market run remains usable as candidate-set
        research when every covered security has a valid identity binding. It
        cannot, however, receive the exact full-market label.
        """

        if contract is None:
            return False
        path = self.run_root / "universe.json"
        if not path.is_file():
            errors.append("MISSING_SECURITY_IDENTITY_RECEIPT")
            return False
        try:
            payload = _load_json(path)
            if payload.get("schema_version") != "3.0":
                raise ValueError("unsupported universe schema")
            if payload.get("reconciliation_status") != "EXACT":
                raise ValueError("reconciliation_status must be EXACT")
            if payload.get("membership_basis") != "POINT_IN_TIME_OFFICIAL":
                raise ValueError("membership_basis must be POINT_IN_TIME_OFFICIAL")

            expected = [str(item).strip() for item in payload.get("expected_security_codes", [])]
            covered = [str(item).strip() for item in payload.get("covered_security_codes", [])]
            if not expected or any(not item.isdigit() for item in expected + covered):
                raise ValueError("universe codes must be non-empty official numeric codes")
            if len(expected) != len(set(expected)) or len(covered) != len(set(covered)):
                raise ValueError("universe codes must be unique")
            expected_set = set(expected)
            covered_set = set(covered)
            if not covered_set.issubset(expected_set):
                raise ValueError("covered universe is not a subset of expected universe")
            if len(expected) != contract.expected_universe_count or len(covered) != contract.covered_universe_count:
                raise ValueError("universe lists do not match declared counts")
            if {item.security_code for item in findings} - covered_set:
                raise ValueError("finding security lies outside covered universe")

            identity_rows = payload.get("securities")
            if not isinstance(identity_rows, list) or not identity_rows:
                raise ValueError("securities must be a non-empty list")
            bindings: dict[str, str] = {}
            kuwait_tz = ZoneInfo(contract.timezone)
            decision_day = contract.decision_at.astimezone(kuwait_tz).date()
            for index, row in enumerate(identity_rows):
                if not isinstance(row, dict):
                    raise ValueError(f"securities[{index}] is not an object")
                code = str(row.get("security_code", "")).strip()
                ticker = _ticker_alias(row.get("ticker"))
                if not code.isdigit() or code in bindings:
                    raise ValueError("identity bindings require unique numeric code and ticker")
                valid_from = parse_iso_date(row.get("valid_from"), "valid_from")
                valid_to_value = row.get("valid_to")
                valid_to = (
                    parse_iso_date(valid_to_value, "valid_to")
                    if valid_to_value not in (None, "")
                    else None
                )
                if valid_to and valid_to < valid_from:
                    raise ValueError("identity binding valid_to precedes valid_from")
                if decision_day < valid_from or (valid_to and decision_day > valid_to):
                    raise ValueError("identity binding is not effective at decision_at")
                bindings[code] = ticker
            if set(bindings) != covered_set:
                raise ValueError("identity bindings do not match the covered universe")
            for finding in findings:
                if bindings.get(finding.security_code) != finding.ticker.upper():
                    raise ValueError(
                        f"ticker mismatch for security_code {finding.security_code}"
                    )

            source_id = str(payload.get("membership_source_id", ""))
            if source_id not in self.catalog.sources:
                raise ValueError("unknown membership source")
            source = self.catalog.sources[source_id]
            if source.source_class not in {"PRIMARY_OFFICIAL", "LICENSED"} or "IDENTITY_REFERENCE" not in source.roles:
                raise ValueError("membership source is not official/licensed identity evidence")
            digest = require_sha256(payload.get("membership_raw_sha256"), "membership_raw_sha256")
            if not any(item.sha256 == digest and item.source_id == source_id for item in artifacts):
                raise ValueError("membership raw hash is unresolved for its source")
            observation = next((item for item in observations if item.source_id == source_id), None)
            if (
                observation is None
                or not observation.contributes
                or "IDENTITY_REFERENCE" not in observation.roles_observed
                or digest not in observation.raw_sha256s
            ):
                raise ValueError("membership source observation is not contributing")
            membership_artifacts = [
                item
                for item in artifacts
                if item.sha256 == digest
                and item.source_id == source_id
                and item.capture_kind != "ACCESS_RECEIPT"
            ]
            if not membership_artifacts:
                raise ValueError("membership raw hash is not usable identity evidence")
            membership_as_of = parse_aware(payload.get("membership_as_of"), "membership_as_of")
            if membership_as_of.astimezone(kuwait_tz).date() != decision_day:
                raise ValueError("membership_as_of must be on the decision_at date")
            if membership_as_of > contract.decision_at:
                raise ValueError("membership_as_of is after decision_at")
            membership_age_hours = (
                contract.decision_at - membership_as_of
            ).total_seconds() / 3600
            maximum_membership_age = min(self.policy.max_source_age_hours, 24.0)
            if membership_age_hours > maximum_membership_age:
                raise ValueError(
                    "membership_as_of is stale for the research policy:"
                    f"{membership_age_hours:.3f}h>{maximum_membership_age:.3f}h"
                )
            if not any(
                item.sha256 == digest
                and item.source_id == source_id
                and item.observed_at >= membership_as_of
                for item in membership_artifacts
            ):
                raise ValueError("membership evidence was captured before membership_as_of")
            substantive_finding_codes = {
                finding.security_code
                for finding in findings
                if _is_substantive_finding(finding)
            }
            missing_substantive_codes = sorted(
                expected_set - substantive_finding_codes
            )
            full_market_complete = (
                contract.scope == "FULL_MARKET"
                and covered_set == expected_set
                and contract.universe_coverage
                >= self.policy.full_market_coverage_required
                and not missing_substantive_codes
            )
            if contract.scope == "FULL_MARKET" and not full_market_complete:
                warnings.append("FULL_MARKET_COVERAGE_INCOMPLETE")
                if missing_substantive_codes:
                    warnings.append(
                        "FULL_MARKET_SUBSTANTIVE_FINDING_COVERAGE_INCOMPLETE:"
                        + ",".join(missing_substantive_codes)
                    )
            return full_market_complete
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"SECURITY_IDENTITY_BINDING_REJECTED:{exc}")
            return False

    def _load_contract(self, errors: list[str]) -> NetworkRunContract | None:
        path = self.run_root / "research_run.json"
        if not path.is_file():
            errors.append("MISSING_RESEARCH_RUN")
            return None
        try:
            payload = _load_json(path)
            if payload.get("schema_version") != "3.0":
                raise ValueError("unsupported research run schema")
            run_id = str(payload.get("run_id", "")).strip()
            product_id = str(payload.get("product_id", "")).strip()
            if not run_id or product_id != self.product_id:
                raise ValueError("run_id or product_id mismatch")
            decision_at = parse_aware(payload.get("decision_at"), "decision_at")
            timezone = str(payload.get("timezone", ""))
            if timezone != "Asia/Kuwait":
                raise ValueError("timezone must be Asia/Kuwait")
            scope = str(payload.get("scope", ""))
            if scope not in SCOPES:
                raise ValueError("invalid research scope")
            expected = int(payload.get("expected_universe_count", 0))
            covered = int(payload.get("covered_universe_count", 0))
            if expected <= 0 or covered < 0 or covered > expected:
                raise ValueError("invalid universe counts")
            budget = payload.get("budget")
            usage = payload.get("usage")
            if not isinstance(budget, dict) or not isinstance(usage, dict):
                raise ValueError("budget and usage are required")
            budget_values: dict[str, int] = {}
            usage_values: dict[str, int] = {}
            for key in ("max_requests", "max_raw_bytes", "max_wall_seconds"):
                budget_values[key] = int(budget.get(key, 0))
                if budget_values[key] <= 0:
                    raise ValueError(f"budget.{key} must be positive")
            for key in ("requests", "raw_bytes", "wall_seconds"):
                usage_values[key] = int(usage.get(key, -1))
                if usage_values[key] < 0:
                    raise ValueError(f"usage.{key} must be non-negative")
            if any(usage_values[key] > budget_values["max_" + key] for key in ("requests", "raw_bytes", "wall_seconds")):
                raise ValueError("research budget exceeded")
            return NetworkRunContract(
                run_id,
                product_id,
                decision_at,
                timezone,
                scope,
                expected,
                covered,
                budget_values["max_requests"],
                budget_values["max_raw_bytes"],
                budget_values["max_wall_seconds"],
                usage_values["requests"],
                usage_values["raw_bytes"],
                usage_values["wall_seconds"],
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"INVALID_RESEARCH_RUN:{exc}")
            return None

    def _load_manifest(
        self, contract: NetworkRunContract | None, errors: list[str]
    ) -> tuple[list[NetworkArtifact], frozenset[str]]:
        path = self.run_root / "manifest.json"
        if not path.is_file():
            errors.append("MISSING_NETWORK_MANIFEST")
            return [], frozenset()
        artifacts: list[NetworkArtifact] = []
        hashes: set[str] = set()
        seen_paths: set[str] = set()
        try:
            payload = _load_json(path)
            if payload.get("schema_version") != "3.0":
                raise ValueError("unsupported network manifest schema")
            rows = payload.get("artifacts")
            if not isinstance(rows, list) or not rows:
                raise ValueError("manifest artifacts must be non-empty")
            for index, row in enumerate(rows):
                prefix = f"artifact_{index}"
                try:
                    if not isinstance(row, dict):
                        raise ValueError("not an object")
                    relative = safe_relative_path(row.get("path"), "path")
                    if not relative.parts or relative.parts[0] != "raw":
                        raise ValueError("artifact path must be inside raw/")
                    relative_text = relative.as_posix()
                    if relative_text in seen_paths:
                        raise ValueError("duplicate artifact path")
                    seen_paths.add(relative_text)
                    file_path = resolved_regular_file(self.run_root, relative, "artifact path")
                    digest = require_sha256(row.get("sha256"), "sha256")
                    if sha256_file(file_path) != digest:
                        raise ValueError("artifact hash mismatch")
                    size = int(row.get("size_bytes", -1))
                    if size != file_path.stat().st_size:
                        raise ValueError("artifact size mismatch")
                    source_id = str(row.get("source_id", ""))
                    if source_id not in self.catalog.sources:
                        raise ValueError("unknown source_id")
                    source = self.catalog.sources[source_id]
                    source_url = https_url(row.get("source_url"), "source_url")
                    if source.domains and not _host_allowed(source_url, source.domains):
                        raise ValueError("source URL outside registered domains")
                    observed_at = parse_aware(row.get("observed_at"), "observed_at")
                    if contract and observed_at > contract.decision_at:
                        raise ValueError("artifact observed_at is after decision_at")
                    capture_kind = str(row.get("capture_kind", ""))
                    if capture_kind not in {"RAW_PAGE", "RAW_DOWNLOAD", "USER_EXPORT", "ACCESS_RECEIPT", "ARCHIVE_CAPTURE"}:
                        raise ValueError("invalid capture_kind")

                    registry_id = ""
                    authority_domain = ""
                    authority_subject = ""
                    authority_codes: tuple[str, ...] = ()
                    authority_hash = ""
                    if source.requires_runtime_domain_registry:
                        authority = row.get("runtime_authority")
                        if not isinstance(authority, dict):
                            raise ValueError(
                                "structured runtime_authority is required; a bare boolean is not evidence"
                            )
                        registry_id = str(authority.get("registry_id", "")).strip()
                        authority_domain = str(authority.get("verified_domain", "")).strip().lower().rstrip(".")
                        authority_subject = str(authority.get("subject_id", "")).strip()
                        authority_hash = require_sha256(
                            authority.get("evidence_sha256"), "runtime_authority.evidence_sha256"
                        )
                        authority_codes = tuple(
                            str(item).strip() for item in authority.get("security_codes", [])
                        )
                        if (
                            not registry_id
                            or not authority_subject
                            or not authority_domain
                            or "/" in authority_domain
                            or not _host_allowed(source_url, (authority_domain,))
                        ):
                            raise ValueError("invalid runtime authority registry/domain/subject binding")
                        if any(not item.isdigit() for item in authority_codes) or len(authority_codes) != len(
                            set(authority_codes)
                        ):
                            raise ValueError("runtime authority security codes must be unique numeric codes")
                        if source.source_class == "PRIMARY_ISSUER" and not authority_codes:
                            raise ValueError("issuer runtime authority must bind at least one security_code")
                        verified_at = parse_aware(authority.get("verified_at"), "runtime_authority.verified_at")
                        if verified_at > observed_at or (contract and verified_at > contract.decision_at):
                            raise ValueError("runtime authority was verified after the artifact or decision")
                        registry = self.runtime_trust_registry
                        if registry is None:
                            raise ValueError("external runtime trust registry is required")
                        if registry_id != registry.registry_id:
                            raise ValueError("runtime authority registry_id does not match the trusted registry")
                        if contract is None:
                            raise ValueError("runtime authority requires a valid decision contract")
                        observed_entry = registry.require_authority(
                            source_id=source_id,
                            subject_id=authority_subject,
                            domain=authority_domain,
                            decision_at=observed_at,
                        )
                        decision_entry = registry.require_authority(
                            source_id=source_id,
                            subject_id=authority_subject,
                            domain=authority_domain,
                            decision_at=contract.decision_at,
                        )
                        if observed_entry != decision_entry:
                            raise ValueError("runtime authority binding changed before decision_at")
                        for security_code in authority_codes:
                            bound_entry = registry.require_authority(
                                source_id=source_id,
                                subject_id=authority_subject,
                                domain=authority_domain,
                                security_code=security_code,
                                decision_at=contract.decision_at,
                            )
                            if bound_entry != decision_entry:
                                raise ValueError("runtime authority security binding is ambiguous")

                    artifacts.append(
                        NetworkArtifact(
                            relative_text,
                            digest,
                            size,
                            source_id,
                            source_url,
                            observed_at,
                            capture_kind,
                            registry_id,
                            authority_domain,
                            authority_subject,
                            authority_codes,
                            authority_hash,
                        )
                    )
                    hashes.add(digest)
                except (OSError, RuntimeTrustError, TypeError, ValueError) as exc:
                    errors.append(f"{prefix}:{exc}")

            artifact_by_hash: dict[str, list[NetworkArtifact]] = {}
            for artifact in artifacts:
                artifact_by_hash.setdefault(artifact.sha256, []).append(artifact)
            for artifact in artifacts:
                if not artifact.runtime_authority_registry_id:
                    continue
                authority_rows = artifact_by_hash.get(artifact.runtime_authority_evidence_sha256, [])
                authority_rows = [
                    item for item in authority_rows if item.capture_kind != "ACCESS_RECEIPT"
                ]
                if not authority_rows:
                    errors.append(
                        f"RUNTIME_AUTHORITY_EVIDENCE_UNRESOLVED:{artifact.path}"
                    )
                    continue
                source = self.catalog.sources[artifact.source_id]
                if source.source_class == "PRIMARY_ISSUER" and not any(
                    self.catalog.sources[item.source_id].source_class == "PRIMARY_OFFICIAL"
                    and "IDENTITY_REFERENCE" in self.catalog.sources[item.source_id].roles
                    for item in authority_rows
                ):
                    errors.append(
                        f"ISSUER_RUNTIME_AUTHORITY_NOT_OFFICIAL_IDENTITY_EVIDENCE:{artifact.path}"
                    )

            if contract is not None:
                manifest_raw_bytes = sum(item.size_bytes for item in artifacts)
                if manifest_raw_bytes != contract.usage_raw_bytes:
                    errors.append(
                        "RAW_BYTE_USAGE_MISMATCH:"
                        f"manifest={manifest_raw_bytes}:declared={contract.usage_raw_bytes}"
                    )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"INVALID_NETWORK_MANIFEST:{exc}")
        return artifacts, frozenset(hashes)

    def _load_observations(
        self,
        contract: NetworkRunContract | None,
        artifacts: list[NetworkArtifact],
        errors: list[str],
        warnings: list[str],
    ) -> list[SourceObservation]:
        path = self.run_root / "source_observations.json"
        if not path.is_file():
            errors.append("MISSING_SOURCE_OBSERVATIONS")
            return []
        observations: list[SourceObservation] = []
        seen: set[str] = set()
        artifact_map: dict[tuple[str, str], list[NetworkArtifact]] = {}
        for artifact in artifacts:
            artifact_map.setdefault((artifact.source_id, artifact.sha256), []).append(artifact)
        try:
            payload = _load_json(path)
            if payload.get("schema_version") != "3.0":
                raise ValueError("unsupported source observation schema")
            rows = payload.get("sources")
            if not isinstance(rows, list) or not rows:
                raise ValueError("sources must be non-empty")
            for index, row in enumerate(rows):
                prefix = f"source_observation_{index}"
                try:
                    if not isinstance(row, dict):
                        raise ValueError("not an object")
                    source_id = str(row.get("source_id", ""))
                    if source_id not in self.catalog.sources or source_id in seen:
                        raise ValueError("unknown or duplicate source_id")
                    seen.add(source_id)
                    source = self.catalog.sources[source_id]
                    state = str(row.get("state", ""))
                    query_status = str(row.get("query_status", ""))
                    access_mode = str(row.get("access_mode", ""))
                    if state not in ACCESS_STATES or query_status not in QUERY_STATUSES or access_mode not in source.access_modes:
                        raise ValueError("invalid state, query_status, or access_mode")
                    attempted_at = parse_aware(row.get("attempted_at"), "attempted_at")
                    if contract and attempted_at > contract.decision_at:
                        raise ValueError("source attempted after decision_at")
                    if contract:
                        age_hours = (contract.decision_at - attempted_at).total_seconds() / 3600
                        if age_hours > self.policy.max_source_age_hours:
                            warnings.append(f"STALE_SOURCE_OBSERVATION:{source_id}")
                            query_status = "DATA_QUALITY_REJECTED"
                    roles_observed = frozenset(str(item) for item in row.get("roles_observed", []))
                    if not roles_observed or roles_observed - source.roles:
                        raise ValueError("roles_observed outside source contract")
                    qualified_items = int(row.get("qualified_items", -1))
                    zero_result = strict_bool(row.get("zero_result"), "zero_result")
                    if qualified_items < 0 or zero_result != (query_status == "ZERO_RESULT"):
                        raise ValueError("invalid qualified_items or zero_result")
                    if query_status == "QUALIFIED" and qualified_items <= 0:
                        raise ValueError("QUALIFIED must have at least one qualified item")
                    if query_status == "ZERO_RESULT" and qualified_items != 0:
                        raise ValueError("ZERO_RESULT must have zero qualified items")
                    if query_status not in CONTRIBUTING_QUERY_STATUSES and qualified_items != 0:
                        raise ValueError("non-contributing query status must have zero qualified items")
                    raw_hashes = tuple(require_sha256(item, "raw_sha256") for item in row.get("raw_sha256s", []))
                    if len(raw_hashes) != len(set(raw_hashes)):
                        raise ValueError("duplicate raw evidence hash")
                    flags = tuple(str(item) for item in row.get("data_quality_flags", []))
                    limitations = tuple(str(item) for item in row.get("limitations", []))
                    if query_status in CONTRIBUTING_QUERY_STATUSES:
                        if not raw_hashes or any((source_id, digest) not in artifact_map for digest in raw_hashes):
                            raise ValueError("contributing observation requires raw evidence resolved to the same source")
                        usable = [
                            artifact
                            for digest in raw_hashes
                            for artifact in artifact_map[(source_id, digest)]
                            if artifact.capture_kind != "ACCESS_RECEIPT"
                        ]
                        if not usable:
                            raise ValueError("access receipt cannot establish a contributing observation")
                    contributes = (
                        state in {"AVAILABLE", "PARTIAL"}
                        and query_status in CONTRIBUTING_QUERY_STATUSES
                        and not flags
                    )

                    enabled_for_run = source.enabled_by_default
                    activation_id = ""
                    activation_hash = ""
                    if not source.enabled_by_default and contributes:
                        enabled_for_run = strict_bool(row.get("enabled_for_run"), "enabled_for_run")
                        activation_id = str(row.get("activation_id", "")).strip()
                        activation_hash = require_sha256(
                            row.get("activation_evidence_sha256"), "activation_evidence_sha256"
                        )
                        if not enabled_for_run or not activation_id:
                            raise ValueError("disabled source requires explicit per-run activation")
                        if (source_id, activation_hash) not in artifact_map or activation_hash not in raw_hashes:
                            raise ValueError("source activation evidence is unresolved for the same source")

                    entitlement = str(row.get("entitlement_id", "")).strip()
                    entitlement_hash = ""
                    if source.requires_entitlement and contributes:
                        entitlement_hash = require_sha256(
                            row.get("entitlement_evidence_sha256"), "entitlement_evidence_sha256"
                        )
                        entitlement_artifacts = artifact_map.get((source_id, entitlement_hash), [])
                        if (
                            not entitlement
                            or entitlement_hash not in raw_hashes
                            or not any(item.capture_kind == "ACCESS_RECEIPT" for item in entitlement_artifacts)
                        ):
                            raise ValueError(
                                "licensed source requires entitlement_id and a same-source ACCESS_RECEIPT"
                            )
                    if contributes and _requires_external_runtime_trust(source):
                        registry = self.runtime_trust_registry
                        if registry is None or contract is None:
                            raise ValueError("sensitive source requires an external runtime trust registry")
                        trust_entries = []
                        if not source.enabled_by_default:
                            attempted_entry = registry.require_activation(
                                source_id=source_id,
                                activation_id=activation_id,
                                decision_at=attempted_at,
                            )
                            decision_entry = registry.require_activation(
                                source_id=source_id,
                                activation_id=activation_id,
                                decision_at=contract.decision_at,
                            )
                            if attempted_entry != decision_entry:
                                raise ValueError("runtime activation binding changed before decision_at")
                            trust_entries.append(decision_entry)
                        if source.requires_entitlement:
                            attempted_entry = registry.require_entitlement(
                                source_id=source_id,
                                entitlement_id=entitlement,
                                decision_at=attempted_at,
                            )
                            decision_entry = registry.require_entitlement(
                                source_id=source_id,
                                entitlement_id=entitlement,
                                decision_at=contract.decision_at,
                            )
                            if attempted_entry != decision_entry:
                                raise ValueError("runtime entitlement binding changed before decision_at")
                            trust_entries.append(decision_entry)
                        if len(set(trust_entries)) > 1:
                            raise ValueError("source activation and entitlement do not share one trust entry")
                    if "EXECUTION_TAPE" in roles_observed and contributes:
                        if source.source_class != "LICENSED" or not source.requires_entitlement:
                            raise ValueError("execution tape requires an entitlement-enforced licensed source")
                    observations.append(
                        SourceObservation(
                            source_id,
                            state,
                            access_mode,
                            attempted_at,
                            query_status,
                            roles_observed,
                            qualified_items,
                            zero_result,
                            raw_hashes,
                            flags,
                            limitations,
                            entitlement,
                            entitlement_hash,
                            enabled_for_run,
                            activation_id,
                            activation_hash,
                        )
                    )
                except (RuntimeTrustError, TypeError, ValueError) as exc:
                    errors.append(f"{prefix}:{exc}")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"INVALID_SOURCE_OBSERVATIONS:{exc}")
        return observations

    def _load_findings(
        self,
        contract: NetworkRunContract | None,
        observations: list[SourceObservation],
        artifacts: list[NetworkArtifact],
        errors: list[str],
        warnings: list[str],
    ) -> list[ResearchFinding]:
        path = self.run_root / "findings.jsonl"
        if not path.is_file():
            errors.append("MISSING_FINDINGS")
            return []
        observation_map = {item.source_id: item for item in observations}
        artifact_map: dict[tuple[str, str], list[NetworkArtifact]] = {}
        for artifact in artifacts:
            artifact_map.setdefault((artifact.source_id, artifact.sha256), []).append(artifact)
        findings: list[ResearchFinding] = []
        seen: set[str] = set()
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            prefix = f"finding_{index}"
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("not an object")
                finding_id = str(row.get("finding_id", "")).strip()
                if not finding_id or finding_id in seen:
                    raise ValueError("duplicate or empty finding_id")
                seen.add(finding_id)
                security_code = str(row.get("security_code", "")).strip()
                if not security_code.isdigit():
                    raise ValueError("security_code must be the official numeric code")
                ticker = _ticker_alias(row.get("ticker"))
                source_id = str(row.get("source_id", ""))
                if source_id not in self.catalog.sources or source_id not in observation_map:
                    raise ValueError("finding source was not observed")
                observation = observation_map[source_id]
                if not observation.contributes:
                    raise ValueError("finding source observation is not contributing")
                source = self.catalog.sources[source_id]
                source_url = https_url(row.get("source_url"), "source_url")
                if source.domains and not _host_allowed(source_url, source.domains):
                    raise ValueError("finding URL outside registered source domains")
                published_at = parse_aware(row.get("published_at"), "published_at")
                available_at = parse_aware(row.get("available_at"), "available_at")
                if published_at > available_at:
                    raise ValueError("published_at is after available_at")
                if contract and available_at > contract.decision_at:
                    raise ValueError("finding available after decision_at")
                capture_mode = str(row.get("capture_mode", ""))
                if capture_mode not in CAPTURE_MODES:
                    raise ValueError("invalid capture_mode")
                if capture_mode == "SEARCH_INDEX":
                    raise ValueError("search index or snippet cannot create a finding")
                timing_grade = str(row.get("timing_grade", ""))
                if not _grade_not_stronger(timing_grade, source.timing_grade_ceiling):
                    raise ValueError("timing grade stronger than source ceiling")
                raw_hash = require_sha256(row.get("raw_sha256"), "raw_sha256")
                matching_artifacts = artifact_map.get((source_id, raw_hash), [])
                if not matching_artifacts or raw_hash not in observation.raw_sha256s:
                    raise ValueError("finding raw evidence is unresolved for the same source")
                url_artifacts = [
                    item for item in matching_artifacts if item.source_url == source_url
                ]
                if not url_artifacts:
                    raise ValueError(
                        "finding source_url does not match its referenced artifact source_url"
                    )
                if source.requires_runtime_domain_registry and not any(
                    item.runtime_authority_registry_id
                    and _host_allowed(source_url, (item.runtime_authority_domain,))
                    and security_code in item.runtime_authority_security_codes
                    for item in url_artifacts
                ):
                    raise ValueError(
                        "finding is not bound to a structured runtime domain/security authority"
                    )
                if _requires_external_runtime_trust(source):
                    registry = self.runtime_trust_registry
                    if registry is None or contract is None:
                        raise ValueError("sensitive finding requires an external runtime trust registry")
                    trust_entries = []
                    if source.requires_runtime_domain_registry:
                        authority_entries = []
                        for item in url_artifacts:
                            if (
                                item.runtime_authority_registry_id != registry.registry_id
                                or security_code not in item.runtime_authority_security_codes
                            ):
                                continue
                            try:
                                observed_entry = registry.require_authority(
                                    source_id=source_id,
                                    subject_id=item.runtime_authority_subject_id,
                                    domain=item.runtime_authority_domain,
                                    security_code=security_code,
                                    decision_at=item.observed_at,
                                )
                                decision_entry = registry.require_authority(
                                    source_id=source_id,
                                    subject_id=item.runtime_authority_subject_id,
                                    domain=item.runtime_authority_domain,
                                    security_code=security_code,
                                    decision_at=contract.decision_at,
                                )
                            except RuntimeTrustError:
                                continue
                            if observed_entry == decision_entry:
                                authority_entries.append(decision_entry)
                        if len(set(authority_entries)) != 1:
                            raise ValueError(
                                "finding security_code lacks a unique external runtime authority"
                            )
                        trust_entries.append(authority_entries[0])
                    if not source.enabled_by_default:
                        attempted_entry = registry.require_activation(
                            source_id=source_id,
                            activation_id=observation.activation_id,
                            security_code=security_code,
                            decision_at=observation.attempted_at,
                        )
                        decision_entry = registry.require_activation(
                            source_id=source_id,
                            activation_id=observation.activation_id,
                            security_code=security_code,
                            decision_at=contract.decision_at,
                        )
                        if attempted_entry != decision_entry:
                            raise ValueError("finding activation binding changed before decision_at")
                        trust_entries.append(decision_entry)
                    if source.requires_entitlement:
                        attempted_entry = registry.require_entitlement(
                            source_id=source_id,
                            entitlement_id=observation.entitlement_id,
                            security_code=security_code,
                            decision_at=observation.attempted_at,
                        )
                        decision_entry = registry.require_entitlement(
                            source_id=source_id,
                            entitlement_id=observation.entitlement_id,
                            security_code=security_code,
                            decision_at=contract.decision_at,
                        )
                        if attempted_entry != decision_entry:
                            raise ValueError("finding entitlement binding changed before decision_at")
                        trust_entries.append(decision_entry)
                    if len(set(trust_entries)) != 1:
                        raise ValueError("sensitive finding trust bindings do not resolve to one entry")
                    source_host = urlparse(source_url).hostname or ""
                    if not trust_entries[0].authorizes_domain(source_host):
                        raise ValueError("sensitive finding domain is outside its trusted entry")
                if not any(item.capture_kind != "ACCESS_RECEIPT" for item in url_artifacts):
                    raise ValueError("access receipt cannot support a finding")
                if not any(item.observed_at >= available_at for item in url_artifacts):
                    raise ValueError("raw evidence was observed before the finding became available")
                if capture_mode == "ARCHIVE_CAPTURE" and not any(
                    item.capture_kind == "ARCHIVE_CAPTURE" for item in url_artifacts
                ):
                    raise ValueError("archive finding requires an archive-capture artifact")
                evidence_roles = frozenset(str(item) for item in row.get("evidence_roles", []))
                if (
                    not evidence_roles
                    or evidence_roles - source.roles
                    or evidence_roles - observation.roles_observed
                ):
                    raise ValueError("evidence_roles are outside the source observation contract")
                signal_kind = str(row.get("signal_kind", ""))
                direction = str(row.get("direction", ""))
                if signal_kind not in SIGNAL_KINDS or direction not in DIRECTIONS:
                    raise ValueError("invalid signal_kind or direction")
                if source.source_class == "COMMUNITY" and signal_kind not in {"SENTIMENT", "RISK"}:
                    raise ValueError("community findings are limited to sentiment or risk")
                if source.source_class == "WEB_ARCHIVE" and signal_kind != "ARCHIVE_CONTEXT":
                    raise ValueError("web archive findings are context only")
                if source.source_class in {"SEARCH_ROUTER", "STORAGE"}:
                    raise ValueError("search and storage cannot create findings")
                if any(signal_kind not in ROLE_SIGNAL_KINDS[role] for role in evidence_roles):
                    raise ValueError("signal_kind is not eligible for every declared evidence role")
                fact_type = str(row.get("fact_type", "")).strip()
                if not fact_type:
                    raise ValueError("fact_type is required")
                if fact_type not in source.fact_eligibility:
                    raise ValueError("fact_type is outside source fact_eligibility")
                if contract and signal_kind != "ARCHIVE_CONTEXT":
                    available_age = (
                        contract.decision_at - available_at
                    ).total_seconds() / 3600
                    published_age = (
                        contract.decision_at - published_at
                    ).total_seconds() / 3600
                    if (
                        available_age > self.policy.max_source_age_hours
                        or published_age > self.policy.max_source_age_hours
                    ):
                        warnings.append(f"STALE_FINDING_REJECTED:{finding_id}")
                        continue
                strength = finite_number(row.get("strength"), "strength", minimum=0, maximum=1)
                materiality = finite_number(row.get("materiality"), "materiality", minimum=0, maximum=1)
                origin_id = str(row.get("origin_id", "")).strip()
                event_key = str(row.get("event_key", "")).strip()
                claim_text = str(row.get("claim_text", "")).strip()
                if not origin_id or not event_key or not claim_text:
                    raise ValueError("origin_id, event_key, and claim_text are required")
                findings.append(
                    ResearchFinding(
                        finding_id,
                        security_code,
                        ticker,
                        source_id,
                        source_url,
                        published_at,
                        available_at,
                        capture_mode,
                        timing_grade,
                        raw_hash,
                        evidence_roles,
                        signal_kind,
                        direction,
                        strength,
                        materiality,
                        origin_id,
                        event_key,
                        claim_text,
                        fact_type,
                    )
                )
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                errors.append(f"{prefix}:{exc}")
        if findings and contract:
            found_codes = {item.security_code for item in findings}
            if len(found_codes) > contract.covered_universe_count:
                errors.append("FINDINGS_EXCEED_COVERED_UNIVERSE")
        duplicate_origins = len(findings) - len(
            {(item.security_code, item.origin_id, item.event_key, item.signal_kind) for item in findings}
        )
        if duplicate_origins:
            warnings.append(f"REPOST_ORIGIN_CLUSTERS_DEDUPED:{duplicate_origins}")
        return findings


def validate_live_probe(
    path: Path,
    catalog: SourceNetworkCatalog,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate an access-only observation receipt.

    A live probe can establish access state and visible source families. It can
    never establish market facts, a point-in-time feature, or a forecast.
    """

    errors: list[str] = []
    rows_out: list[dict[str, Any]] = []
    try:
        payload = _load_json(path)
        if set(payload) != {
            "schema_version",
            "probe_id",
            "probe_version",
            "observed_at",
            "expires_at",
            "purpose",
            "sources",
        }:
            raise ValueError("access probe has unknown or missing top-level fields")
        if payload.get("schema_version") != "3.1-access-probe":
            raise ValueError("unsupported access probe schema")
        probe_id = str(payload.get("probe_id", "")).strip()
        probe_version = str(payload.get("probe_version", "")).strip()
        purpose = str(payload.get("purpose", "")).strip()
        if not probe_id or not probe_version or not purpose:
            raise ValueError("probe_id, probe_version, and purpose are required")
        observed_at = parse_aware(payload.get("observed_at"), "observed_at")
        expires_at = parse_aware(payload.get("expires_at"), "expires_at")
        reference_now = now or datetime.now(timezone.utc)
        if reference_now.tzinfo is None or reference_now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if observed_at > reference_now + timedelta(minutes=5):
            raise ValueError("access probe observed_at is in the future")
        if expires_at <= observed_at:
            raise ValueError("access probe expires_at must follow observed_at")
        if expires_at - observed_at > timedelta(hours=24):
            raise ValueError("access probe validity cannot exceed 24 hours")
        if reference_now > expires_at:
            raise ValueError("access probe is expired")
        rows = payload.get("sources")
        if not isinstance(rows, list) or not rows:
            raise ValueError("probe sources must be non-empty")
        seen: set[str] = set()
        for index, row in enumerate(rows):
            try:
                if not isinstance(row, dict):
                    raise ValueError("not an object")
                if set(row) != {
                    "source_id",
                    "state",
                    "tested_url",
                    "final_url",
                    "attempted_at",
                    "http_status",
                    "observation",
                    "data_quality_flags",
                    "artifact",
                }:
                    raise ValueError("unknown or missing fields")
                source_id = str(row.get("source_id", ""))
                if source_id not in catalog.sources or source_id in seen:
                    raise ValueError("unknown or duplicate source_id")
                seen.add(source_id)
                state = str(row.get("state", ""))
                if state not in ACCESS_STATES:
                    raise ValueError("invalid state")
                source = catalog.sources[source_id]
                tested_url = https_url(row.get("tested_url"), "tested_url")
                final_url = https_url(row.get("final_url"), "final_url")
                if source.domains and (
                    not _host_allowed(tested_url, source.domains)
                    or not _host_allowed(final_url, source.domains)
                ):
                    raise ValueError("tested/final URL outside registered domains")
                attempted_at = parse_aware(row.get("attempted_at"), "attempted_at")
                if attempted_at > observed_at or observed_at - attempted_at > timedelta(hours=1):
                    raise ValueError("attempted_at is after or implausibly far before observed_at")
                http_status_value = row.get("http_status")
                if http_status_value is None:
                    http_status = None
                elif isinstance(http_status_value, bool) or not isinstance(http_status_value, int):
                    raise ValueError("http_status must be an integer or null")
                else:
                    http_status = http_status_value
                    if not 100 <= http_status <= 599:
                        raise ValueError("http_status is outside 100..599")
                if state in {"AVAILABLE", "PARTIAL"} and (
                    http_status is None or not 200 <= http_status <= 299
                ):
                    raise ValueError("AVAILABLE/PARTIAL requires a successful HTTP status")
                observation = row.get("observation")
                if not isinstance(observation, str) or not observation.strip() or len(observation) > 2000:
                    raise ValueError("observation must be a non-empty string of at most 2000 characters")
                flags_value = row.get("data_quality_flags")
                if not isinstance(flags_value, list) or any(
                    not isinstance(item, str)
                    or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", item)
                    for item in flags_value
                ):
                    raise ValueError("data_quality_flags must be an array of stable uppercase codes")
                if len(flags_value) != len(set(flags_value)):
                    raise ValueError("data_quality_flags contains duplicates")
                artifact_value = row.get("artifact")
                artifact_out = None
                if artifact_value is not None:
                    if not isinstance(artifact_value, dict) or set(artifact_value) != {
                        "path",
                        "sha256",
                        "size_bytes",
                        "content_type",
                        "capture_kind",
                    }:
                        raise ValueError("artifact has unknown or missing fields")
                    relative = safe_relative_path(artifact_value.get("path"), "artifact.path")
                    if not relative.parts or relative.parts[0] != "raw":
                        raise ValueError("probe artifact must be inside raw/")
                    probe_root = path.parent.resolve()
                    artifact_path = resolved_regular_file(
                        probe_root, relative, "probe artifact"
                    )
                    digest = require_sha256(artifact_value.get("sha256"), "artifact.sha256")
                    size = artifact_value.get("size_bytes")
                    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                        raise ValueError("artifact.size_bytes must be a non-negative integer")
                    if artifact_path.stat().st_size != size or sha256_file(artifact_path) != digest:
                        raise ValueError("probe artifact bytes do not match size/hash")
                    content_type = str(artifact_value.get("content_type", "")).strip().lower()
                    capture_kind = str(artifact_value.get("capture_kind", ""))
                    if not content_type or capture_kind not in {
                        "RAW_PAGE",
                        "RAW_DOWNLOAD",
                        "USER_EXPORT",
                        "ARCHIVE_CAPTURE",
                    }:
                        raise ValueError("artifact content_type/capture_kind is invalid")
                    artifact_out = {
                        "path": relative.as_posix(),
                        "sha256": digest,
                        "size_bytes": size,
                        "content_type": content_type,
                        "capture_kind": capture_kind,
                    }
                if state in {"AVAILABLE", "PARTIAL"} and artifact_out is None:
                    raise ValueError("AVAILABLE/PARTIAL requires a hash-bound raw artifact")
                rows_out.append(
                    {
                        "source_id": source_id,
                        "state": state,
                        "tested_url": tested_url,
                        "final_url": final_url,
                        "attempted_at": attempted_at.isoformat(),
                        "http_status": http_status,
                        "observation": observation.strip(),
                        "data_quality_flags": list(flags_value),
                        "artifact": artifact_out,
                    }
                )
            except (TypeError, ValueError) as exc:
                errors.append(f"probe_source_{index}:{exc}")
        return {
            "status": "PASS" if not errors else "BLOCKED",
            "probe_id": probe_id,
            "probe_version": probe_version,
            "observed_at": observed_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "probe_hash": hash_json(payload),
            "sources": rows_out,
            "errors": errors,
            "claim_boundaries": {
                "access_probe_is_market_evidence": False,
                "access_probe_is_historical_coverage": False,
                "access_probe_is_forecast": False,
            },
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {"status": "BLOCKED", "sources": rows_out, "errors": [*errors, f"INVALID_ACCESS_PROBE:{exc}"]}


__all__ = [
    "NetworkRunValidation",
    "ResearchFinding",
    "ResearchPolicy",
    "SourceNetworkCatalog",
    "SourceNetworkRunValidator",
    "validate_live_probe",
]
