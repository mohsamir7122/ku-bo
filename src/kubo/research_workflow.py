from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .catalog import Catalog
from .source_network import SourceNetworkCatalog


WORKFLOW_ID = "KUWAIT_120D_NEXT_SESSION_RESEARCH"
_WINDOWS = {
    "context_calendar_days": 120,
    "active_event_calendar_days": 30,
    "community_sentiment_calendar_days": 7,
    "fresh_catalyst_hours": 72,
}
_WAVES = (
    "OFFICIAL_AND_REGULATORY",
    "ISSUER_AND_GOVERNMENT",
    "STRUCTURED_AND_EDITORIAL",
    "COMMUNITY_ARCHIVE_AND_ROUTING",
)
_FALSE_BOUNDARIES = {
    "search_snippet_is_evidence",
    "community_is_official_truth",
    "score_is_probability",
    "historical_replay_is_prospective_validation",
    "missing_data_is_zero_return",
}
_NON_RESEARCH_DOMAIN_CLASSES = frozenset({"SEARCH_ROUTER", "STORAGE"})
_ORCHESTRATED_SOURCE_CLASSES = frozenset(
    {
        "PRIMARY_OFFICIAL",
        "PRIMARY_ISSUER",
        "STRUCTURED_SECONDARY",
        "EDITORIAL",
        "COMMUNITY",
        "WEB_ARCHIVE",
    }
)
_MULTI_LABEL_PUBLIC_SUFFIXES = frozenset(
    {
        "co.uk",
        "com.ae",
        "com.bh",
        "com.kw",
        "com.om",
        "com.qa",
        "com.sa",
        "edu.kw",
        "gov.kw",
        "net.kw",
        "org.kw",
    }
)


@dataclass(frozen=True, slots=True)
class ResearchWorkflowSpec:
    workflow_id: str
    product_id: str
    timezone: str
    context_calendar_days: int
    active_event_calendar_days: int
    community_sentiment_calendar_days: int
    fresh_catalyst_hours: int
    target_distinct_registrable_domains: int
    maximum_distinct_registrable_domains: int
    maximum_requests: int
    maximum_wall_seconds: int
    catalog_distinct_registrable_domains: int
    transient_attempts_per_strategy: int
    empty_result_query_strategies: int
    incremental_corpus: bool
    wave_order: tuple[str, ...]
    decision_sessions: int
    required_consecutive_official_sessions: int
    primary_target: str
    secondary_targets: tuple[str, ...]
    ranking_rule: str
    execution_grade_required: bool
    nontrading_outcome_policy: str
    minimum_universe_coverage: float
    minimum_evaluable_rate: float
    maximum_nonfill_rate: float


def _registrable_domain(hostname: str) -> str:
    labels = hostname.lower().rstrip(".").split(".")
    if len(labels) < 2 or any(not label for label in labels):
        raise ValueError("source catalog contains an invalid hostname")
    suffix = ".".join(labels[-2:])
    if suffix in _MULTI_LABEL_PUBLIC_SUFFIXES:
        if len(labels) < 3:
            raise ValueError("source catalog hostname lacks a registrable label")
        return ".".join(labels[-3:])
    return suffix


def catalog_registrable_domains(catalog: SourceNetworkCatalog) -> tuple[str, ...]:
    """Return research-source sites without treating URLs as publishers.

    This bounded list measures surfaces that may be attempted.  It deliberately
    excludes search routers and storage, and it is never used as an evidence
    independence count.
    """

    return tuple(
        sorted(
            {
                _registrable_domain(domain)
                for source in catalog.sources.values()
                if source.source_class not in _NON_RESEARCH_DOMAIN_CLASSES
                and source.source_class in _ORCHESTRATED_SOURCE_CLASSES
                and source.enabled_by_default
                and source.start_urls
                and ({"PUBLIC_PAGE", "PUBLIC_DOWNLOAD"} & source.access_modes)
                for domain in source.domains
            }
        )
    )


def _object(value: Any, field: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{field} has unknown or missing fields")
    return value


def load_research_workflow(config_dir: Path) -> ResearchWorkflowSpec:
    path = Path(config_dir) / "research_workflows.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("research workflow configuration is unreadable") from exc
    root = _object(payload, "research_workflows", {"schema_version", "workflows"})
    if root["schema_version"] != "1.0":
        raise ValueError("research workflow schema_version must be 1.0")
    rows = root["workflows"]
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("exactly one active research workflow is required")
    row = _object(
        rows[0],
        "workflow",
        {"workflow_id", "product_id", "timezone", "windows", "source_search", "evaluation", "claim_boundaries"},
    )
    if row["workflow_id"] != WORKFLOW_ID or row["product_id"] != WORKFLOW_ID:
        raise ValueError("workflow and product IDs must match the active contract")
    if row["timezone"] != "Asia/Kuwait":
        raise ValueError("workflow timezone must be Asia/Kuwait")
    windows = _object(row["windows"], "windows", set(_WINDOWS))
    if windows != _WINDOWS:
        raise ValueError("workflow windows do not match the 120d/30d/7d/72h contract")
    source = _object(
        row["source_search"],
        "source_search",
        {
            "target_distinct_registrable_domains",
            "maximum_distinct_registrable_domains",
            "maximum_requests",
            "maximum_wall_seconds",
            "transient_attempts_per_strategy",
            "empty_result_query_strategies",
            "incremental_corpus",
            "wave_order",
        },
    )
    integers = (
        "target_distinct_registrable_domains",
        "maximum_distinct_registrable_domains",
        "maximum_requests",
        "maximum_wall_seconds",
        "transient_attempts_per_strategy",
        "empty_result_query_strategies",
    )
    if any(isinstance(source[name], bool) or not isinstance(source[name], int) for name in integers):
        raise ValueError("source-search numeric bounds must be integers")
    if (
        source["target_distinct_registrable_domains"],
        source["maximum_distinct_registrable_domains"],
        source["maximum_requests"],
        source["maximum_wall_seconds"],
    ) != (50, 50, 600, 1800):
        raise ValueError("source domain, request, and wall-time budgets must match the frozen contract")
    if source["transient_attempts_per_strategy"] != 2 or source["empty_result_query_strategies"] != 4:
        raise ValueError("retry and empty-result strategies must be 2 and 4")
    if source["incremental_corpus"] is not True or tuple(source["wave_order"]) != _WAVES:
        raise ValueError("source search must be incremental and use the fixed wave order")
    evaluation = _object(
        row["evaluation"],
        "evaluation",
        {
            "decision_sessions",
            "required_consecutive_official_sessions",
            "primary_target",
            "secondary_targets",
            "ranking_rule",
            "execution_grade_required",
            "nontrading_outcome_policy",
            "minimum_universe_coverage",
            "minimum_evaluable_rate",
            "maximum_nonfill_rate",
        },
    )
    if evaluation["decision_sessions"] != 40 or evaluation["required_consecutive_official_sessions"] != 41:
        raise ValueError("the replay contract requires 40 decisions across 41 sessions")
    if evaluation["primary_target"] != "GROSS_ADJUSTED_RETURN_GT_0":
        raise ValueError("the primary label must answer whether the security rose")
    secondary = tuple(evaluation["secondary_targets"])
    if secondary != ("MARKET_NET_EXCESS_GT_0", "SECTOR_NET_EXCESS_GT_0"):
        raise ValueError("secondary benchmark labels are incomplete")
    if evaluation["ranking_rule"] != "SCORE_DESC_SECURITY_CODE_ASC":
        raise ValueError("ranking must derive from score with a security-code tie-break")
    if evaluation["execution_grade_required"] is not True:
        raise ValueError("the replay requires execution-grade entry, exit, and cost evidence")
    if (
        evaluation["nontrading_outcome_policy"]
        != "STOP_BACKTEST_WHILE_KU_BO_008_D01_OPEN"
    ):
        raise ValueError("nontrading outcomes must stop while KU-BO-008-D01 is open")
    if any(
        isinstance(evaluation[field], bool)
        or not isinstance(evaluation[field], (int, float))
        for field in (
            "minimum_universe_coverage",
            "minimum_evaluable_rate",
            "maximum_nonfill_rate",
        )
    ):
        raise ValueError("evaluation rates must be JSON numbers, not booleans or strings")
    rates = (
        float(evaluation["minimum_universe_coverage"]),
        float(evaluation["minimum_evaluable_rate"]),
        float(evaluation["maximum_nonfill_rate"]),
    )
    if rates != (1.0, 1.0, 0.0):
        raise ValueError(
            "evaluation requires a complete universe, forty evaluable decisions, "
            "and no unresolved non-fill"
        )
    boundaries = _object(row["claim_boundaries"], "claim_boundaries", _FALSE_BOUNDARIES)
    if any(boundaries[name] is not False for name in _FALSE_BOUNDARIES):
        raise ValueError("workflow claim boundaries must remain false")

    # Cross-file integration is part of loading the active workflow. A config
    # row cannot silently name a product or source policy that does not exist.
    catalog = Catalog(config_dir)
    source_catalog = SourceNetworkCatalog(config_dir)
    from .source_orchestrator import load_orchestrator_policy

    orchestrator_policy = load_orchestrator_policy(
        Path(config_dir) / "source_query_strategies.json"
    )
    if WORKFLOW_ID not in catalog.products:
        raise ValueError("workflow product is missing from products.json")
    product = catalog.products[WORKFLOW_ID]
    if (
        product.horizon_sessions != 1
        or product.target_rule != evaluation["primary_target"]
        or product.execution_grade_required is not True
        or product.minimum_independent_dates != 40
        or product.benchmark_rule != "point_in_time_market_and_sector"
        or product.cost_policy
        != "recorded_next_session_entry_to_official_close_with_fees_spread_slippage_zero_nonfill_tolerance_and_absolute_up_primary_label"
        or product.required_capabilities
        != frozenset(
            {
                "security_master",
                "security_status_history",
                "trading_calendar",
                "daily_eod",
                "daily_market_totals",
                "benchmark_history",
                "official_disclosures",
                "corporate_actions",
                "news_context",
                "social_evidence",
                "intraday_bars",
                "l1_quotes",
                "execution_fields",
            }
        )
        or product.allowed_output != "UNVALIDATED_RESEARCH_SCORE_UNTIL_PROSPECTIVE_VALIDATION"
    ):
        raise ValueError("product catalog differs from the active research workflow")
    policy = source_catalog.policy_for(WORKFLOW_ID)
    if (
        policy.probability_allowed
        or policy.recommendation_allowed
        or policy.full_market_coverage_required != 1.0
        or policy.candidate_minimum_coverage != 0.55
        or policy.minimum_independent_sources != 4
        or policy.minimum_independent_community_sources != 0
        or policy.max_source_age_hours != 2880
        or policy.allowed_output != "CANDIDATE_RESEARCH_RANK"
    ):
        raise ValueError("research policy differs from the active claim boundaries")
    source_catalog.policy_for(WORKFLOW_ID)
    if (
        orchestrator_policy.workflow_id != WORKFLOW_ID
        or orchestrator_policy.context_days != windows["context_calendar_days"]
        or orchestrator_policy.target_distinct_registrable_domains
        != source["target_distinct_registrable_domains"]
        or orchestrator_policy.max_distinct_registrable_domains
        != source["maximum_distinct_registrable_domains"]
        or orchestrator_policy.max_requests != source["maximum_requests"]
        or orchestrator_policy.max_wall_seconds != source["maximum_wall_seconds"]
        or orchestrator_policy.max_transient_attempts
        != source["transient_attempts_per_strategy"]
        or len(orchestrator_policy.strategies)
        != source["empty_result_query_strategies"]
        or tuple(wave.wave_id for wave in orchestrator_policy.waves) != _WAVES
    ):
        raise ValueError("source orchestrator policy differs from the active research workflow")
    registered_domains = catalog_registrable_domains(source_catalog)
    if len(registered_domains) < source["target_distinct_registrable_domains"]:
        raise ValueError("source catalog cannot satisfy the configured domain-attempt target")
    return ResearchWorkflowSpec(
        workflow_id=WORKFLOW_ID,
        product_id=WORKFLOW_ID,
        timezone="Asia/Kuwait",
        **windows,
        target_distinct_registrable_domains=source["target_distinct_registrable_domains"],
        maximum_distinct_registrable_domains=source["maximum_distinct_registrable_domains"],
        maximum_requests=source["maximum_requests"],
        maximum_wall_seconds=source["maximum_wall_seconds"],
        catalog_distinct_registrable_domains=len(registered_domains),
        transient_attempts_per_strategy=2,
        empty_result_query_strategies=4,
        incremental_corpus=True,
        wave_order=_WAVES,
        decision_sessions=40,
        required_consecutive_official_sessions=41,
        primary_target=evaluation["primary_target"],
        secondary_targets=secondary,
        ranking_rule=evaluation["ranking_rule"],
        execution_grade_required=True,
        nontrading_outcome_policy=evaluation["nontrading_outcome_policy"],
        minimum_universe_coverage=rates[0],
        minimum_evaluable_rate=rates[1],
        maximum_nonfill_rate=rates[2],
    )


def integrate_research_reports(
    spec: ResearchWorkflowSpec,
    *,
    source_search: Mapping[str, Any],
    context: Mapping[str, Any],
    factors: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    reports = {
        "source_search": source_search,
        "context": context,
        "factors": factors,
        "evaluation": evaluation,
    }
    for name, report in reports.items():
        if not isinstance(report, Mapping) or not isinstance(report.get("status"), str):
            raise ValueError(f"{name} report lacks a status")
    evaluation_status = str(evaluation["status"])
    metrics = evaluation.get("metrics")
    if evaluation_status not in {"PASS_BACKTEST", "STOP_BACKTEST"}:
        raise ValueError("evaluation report has an unknown status")
    if evaluation_status != "PASS_BACKTEST" and metrics is not None:
        raise ValueError("a stopped evaluation must not expose performance metrics")
    if evaluation_status == "PASS_BACKTEST" and not isinstance(metrics, Mapping):
        raise ValueError("a passing evaluation must expose auditable metrics")
    if evaluation_status == "PASS_BACKTEST":
        # v0.1 has no external resolver capable of turning a caller-provided
        # receipt hash into a verified trust decision.  A plain mapping is
        # therefore never allowed to unlock an accuracy claim.
        raise ValueError("PASS_BACKTEST requires an independent authority verifier")
    component_statuses = {name: str(report["status"]) for name, report in reports.items()}
    if evaluation_status == "STOP_BACKTEST":
        status = evaluation_status
    elif any(value in {"FAILED", "BLOCKED", "STOP_BACKTEST"} for value in component_statuses.values()):
        status = "BLOCKED"
    elif any(value in {"PARTIAL", "DEGRADED"} for value in component_statuses.values()):
        status = "PARTIAL"
    else:
        status = "PASS_BACKTEST"
    return {
        "schema_version": "1.0",
        "workflow_id": spec.workflow_id,
        "status": status,
        "component_statuses": component_statuses,
        "metrics": metrics if status == "PASS_BACKTEST" else None,
        "claim_boundaries": {
            "probability_allowed": False,
            "recommendation_allowed": False,
            "prospective_validation_proven": False,
            "accuracy_claim_allowed": status == "PASS_BACKTEST",
        },
    }


__all__ = [
    "WORKFLOW_ID",
    "ResearchWorkflowSpec",
    "catalog_registrable_domains",
    "integrate_research_reports",
    "load_research_workflow",
]
