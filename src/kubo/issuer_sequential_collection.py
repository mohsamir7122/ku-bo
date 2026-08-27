from __future__ import annotations

import copy
from datetime import datetime
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from .company_dossier import CompanyDossierError, validate_issuer_universe
from .foundation_io import require_real_directory, safe_regular_file, strict_json_object
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .runtime_trust import RuntimeTrustError, RuntimeTrustRegistry
from .source_network import SourceNetworkCatalog
from .strict import parse_aware


POLICY_SCHEMA_VERSION = "1.0"
POLICY_ID = "ku-bo-kuwait-security-by-security-v1"
PLAN_SCHEMA_VERSION = "issuer-sequential-collection-plan-v1"

SECURITY_LIFECYCLE = (
    "QUEUED",
    "IDENTITY_BOUND",
    "SOURCE_PLAN_FROZEN",
    "COLLECTING",
    "RECONCILING",
    "VALIDATING",
    "SEALING",
)
TERMINAL_SECURITY_STATUSES = frozenset(
    {
        "SEALED_ALL_SOURCE_ATTEMPTS_TERMINAL",
        "SEALED_WITH_EXPLICIT_GAPS",
        "SEALED_BLOCKED",
    }
)
TERMINAL_SOURCE_STATUSES = frozenset(
    {
        "COLLECTED",
        "VERIFIED_ZERO",
        "REVIEWED_NOT_APPLICABLE",
        "BLOCKED_RIGHTS",
        "BLOCKED_ROBOTS",
        "BLOCKED_ACCESS",
        "AUTH_REQUIRED",
        "ENTITLEMENT_REQUIRED",
        "PAYWALL",
        "RATE_LIMITED_EXHAUSTED",
        "NETWORK_ERROR_EXHAUSTED",
        "PARSER_DRIFT",
        "ISSUER_OFFICIAL_SITE_UNRESOLVED",
    }
)
USER_REQUIRED_SOURCE_IDS = frozenset(
    {
        "boursa_current",
        "boursa_disclosure_archive",
        "boursa_reports_archive",
        "cma_ifsah",
        "kcc_maqasa_official",
        "issuer_ir_verified",
        "investing_history",
        "reuters_middle_east",
        "yahoo_finance_kw",
        "alqabas_economy",
        "alanba_economy",
        "indexsignal_forum",
        "web_search_router",
        "lseg_workspace_authorized",
        "alphastocks_authorized_connector",
    }
)
SOURCE_WAVE_SOURCES = (
    ("boursa_current", "cma_ifsah"),
    ("issuer_ir_verified",),
    ("boursa_disclosure_archive", "boursa_reports_archive", "kcc_maqasa_official"),
    ("authorized_broker_feed", "lseg_workspace_authorized", "ice_kuwait_archive"),
    (
        "investing_history",
        "yahoo_finance_kw",
        "mubasher_kuwait",
        "argaam_kuwait",
        "tradingview_screeners",
        "marketscreener_kuwait",
        "alphastocks_authorized_connector",
    ),
    (
        "reuters_middle_east",
        "kuna",
        "alqabas_economy",
        "alanba_economy",
        "alrai_economy",
        "aljarida_economy",
        "zawya",
        "asharq_business",
    ),
    (
        "indexsignal_forum",
        "telegram_boursakw",
        "telegram_kuwaitstockex",
        "telegram_kuwaitse",
        "web_search_router",
    ),
)
SOURCE_WAVE_IDS = (
    "OFFICIAL_IDENTITY",
    "ISSUER_PRIMARY",
    "OFFICIAL_MARKET_FILINGS_AND_ACTIONS",
    "LICENSED_AND_AUTHORIZED_MARKET_DATA",
    "STRUCTURED_SECONDARY",
    "EDITORIAL_CONTEXT",
    "DISCOVERY_AND_SENTIMENT_ONLY",
)
OFFICIAL_CONTENT_AREAS = (
    "FINANCIAL_REPORTS",
    "INVESTOR_PRESENTATIONS",
    "OFFICIAL_RELEASES",
    "GOVERNANCE_AND_OWNERSHIP",
    "GENERAL_ASSEMBLIES",
    "STRATEGY_PROJECTS_AND_SUBSIDIARIES",
)
SOURCE_CLASS_EXPECTATIONS = {
    **{source_id: "PRIMARY_OFFICIAL" for source_id in SOURCE_WAVE_SOURCES[0]},
    "issuer_ir_verified": "PRIMARY_ISSUER",
    **{source_id: "PRIMARY_OFFICIAL" for source_id in SOURCE_WAVE_SOURCES[2]},
    **{source_id: "LICENSED" for source_id in SOURCE_WAVE_SOURCES[3]},
    **{source_id: "STRUCTURED_SECONDARY" for source_id in SOURCE_WAVE_SOURCES[4]},
    **{source_id: "EDITORIAL" for source_id in SOURCE_WAVE_SOURCES[5]},
    **{source_id: "COMMUNITY" for source_id in SOURCE_WAVE_SOURCES[6][:-1]},
    "web_search_router": "SEARCH_ROUTER",
}
RUNTIME_DOMAIN_REQUIRED_SOURCES = frozenset(
    {"issuer_ir_verified", "authorized_broker_feed", "alphastocks_authorized_connector"}
)
ENTITLEMENT_REQUIRED_SOURCES = frozenset(
    {
        "authorized_broker_feed",
        "lseg_workspace_authorized",
        "ice_kuwait_archive",
        "alphastocks_authorized_connector",
    }
)
DISABLED_BY_DEFAULT_SOURCES = frozenset(
    RUNTIME_DOMAIN_REQUIRED_SOURCES | ENTITLEMENT_REQUIRED_SOURCES
)
FIXTURE_TESTED_SOURCES = frozenset({"boursa_current", "investing_history"})
CLAIM_BOUNDARIES = {
    "policy_executes_network_access": False,
    "catalog_entry_proves_source_access": False,
    "terminal_execution_proves_data_completeness": False,
    "community_or_search_confirms_official_fact": False,
    "licensed_source_may_be_used_without_entitlement": False,
    "partial_collection_unlocks_training_backtest_or_forecast": False,
    "collection_plan_is_trading_advice": False,
}
EXECUTION_INVARIANTS = {
    "grain": "SECURITY",
    "mode": "SECURITY_SEQUENTIAL",
    "order": "SECURITY_CODE_NUMERIC_ASC",
    "max_active_securities": 1,
    "next_security_requires_terminal_seal": True,
    "blocked_security_aborts_market_run": False,
    "source_failure_scope": "SOURCE_LOCAL",
    "source_execution_mode": "EXHAUSTIVE_PER_SECURITY",
    "shared_artifact_reuse": "CONTENT_ADDRESSED_WITH_PER_SECURITY_EXTRACTION",
}
COMPLETION_INVARIANTS = {
    "all_planned_sources_require_terminal_receipt": True,
    "unattempted_source_blocks_security_seal": True,
    "all_universe_securities_require_one_terminal_seal": True,
    "universe_must_be_exact": True,
    "official_site_gap_must_be_explicit": True,
    "source_substitution_allowed": False,
    "republication_counts_as_independent_source": False,
    "market_wide_artifact_requires_per_security_lineage": True,
    "complete_claim_requires_no_blocks_or_critical_gaps": True,
}

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "market",
        "execution",
        "security_lifecycle",
        "terminal_security_statuses",
        "terminal_source_statuses",
        "official_company_site",
        "source_waves",
        "user_required_source_ids",
        "completion_rules",
        "claim_boundaries",
    }
)
_EXECUTION_FIELDS = frozenset(
    set(EXECUTION_INVARIANTS) | {"max_parallel_sources_within_security"}
)
_OFFICIAL_SITE_FIELDS = frozenset(
    {
        "source_id",
        "required_for_every_security",
        "authority_binding",
        "domain_guessing_allowed",
        "unresolved_status",
        "required_content_areas",
    }
)
_WAVE_FIELDS = frozenset({"wave_id", "ordinal", "source_ids", "purpose"})
_IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ATTEMPT_RESULT_FIELDS = frozenset(
    {
        "terminal_status",
        "attempted_at",
        "completed_at",
        "artifact_count",
        "observation_count",
        "requested_domain",
        "activation_id",
        "entitlement_id",
        "artifact_manifest_sha256",
        "limitation",
    }
)
_PLAN_FIELDS = frozenset(
    {
        "schema_version",
        "plan_id",
        "run_id",
        "generated_at",
        "market",
        "universe_as_of",
        "universe_evidence_class",
        "universe_status",
        "issuer_universe_sha256",
        "policy_id",
        "policy_sha256",
        "source_network_sha256",
        "source_capabilities_sha256",
        "execution",
        "security_lifecycle",
        "terminal_security_statuses",
        "terminal_source_statuses",
        "security_count",
        "planned_source_count_per_security",
        "total_source_attempts_planned",
        "user_required_source_ids",
        "queue",
        "completion_rules",
        "claim_boundaries",
        "plan_sha256",
    }
)
_SECURITY_PLAN_FIELDS = frozenset(
    {
        "ordinal",
        "issuer_id",
        "security_code",
        "ticker",
        "isin",
        "board",
        "market_segment",
        "listing_status",
        "legal_name_ar",
        "legal_name_en",
        "identity_sha256",
        "query_terms",
        "initial_state",
        "official_company_site",
        "source_plan",
    }
)
_OFFICIAL_PLAN_FIELDS = frozenset(
    {
        "source_id",
        "required",
        "binding_status",
        "authority_binding",
        "domain_guessing_allowed",
        "unresolved_terminal_status",
        "required_content_areas",
        "authority_registry_id",
        "authority_registry_sha256",
        "authority_authenticated_key_id",
        "authority_registry_issued_at",
        "authority_registry_expires_at",
        "authority_subject_id",
        "authority_entry_valid_from",
        "authority_entry_valid_until",
        "verified_domains",
        "activation_id",
    }
)
_SOURCE_PLAN_FIELDS = frozenset(
    {
        "source_ordinal",
        "wave_ordinal",
        "wave_id",
        "source_id",
        "source_class",
        "roles",
        "independence_group",
        "capability_status",
        "enabled_by_default",
        "requires_runtime_domain_registry",
        "requires_entitlement",
        "initial_status",
    }
)
_NON_BLOCKING_SOURCE_STATUSES = frozenset(
    {"COLLECTED", "VERIFIED_ZERO", "REVIEWED_NOT_APPLICABLE"}
)
_RUN_CLAIM_BOUNDARIES = {
    "callback_execution_proves_live_source_access": False,
    "terminal_receipt_proves_data_completeness": False,
    "content_hashes_are_authenticated_evidence": False,
    "artifact_manifests_were_reopened": False,
    "explicit_gap_may_be_silently_omitted": False,
    "run_unlocks_training_backtest_or_forecast": False,
    "run_is_trading_advice": False,
}
_RUN_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "plan_id",
        "plan_sha256",
        "market",
        "observed_at",
        "execution_evidence_class",
        "status",
        "security_count",
        "sealed_security_count",
        "planned_source_attempt_count",
        "terminal_source_attempt_count",
        "artifact_count",
        "observation_count",
        "security_receipts",
        "claim_boundaries",
        "run_receipt_sha256",
    }
)
_SECURITY_RECEIPT_FIELDS = frozenset(
    {
        "ordinal",
        "issuer_id",
        "security_code",
        "ticker",
        "started_at",
        "completed_at",
        "seal_status",
        "planned_source_count",
        "terminal_source_count",
        "collected_source_count",
        "explicit_gap_source_count",
        "artifact_count",
        "observation_count",
        "previous_security_seal_sha256",
        "source_receipts",
        "security_seal_sha256",
    }
)
_SOURCE_RECEIPT_FIELDS = frozenset(
    {
        "source_ordinal",
        "wave_ordinal",
        "wave_id",
        "source_id",
        "terminal_status",
        "attempted_at",
        "completed_at",
        "artifact_count",
        "observation_count",
        "requested_domain",
        "activation_id",
        "entitlement_id",
        "artifact_manifest_sha256",
        "runtime_authority_bound",
        "authority_registry_id",
        "authority_registry_sha256",
        "authority_authenticated_key_id",
        "limitation",
        "security_code",
        "source_receipt_sha256",
    }
)


class IssuerSequentialCollectionError(ValueError):
    """Raised when the security-by-security collection contract is invalid."""


def _exact_object(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IssuerSequentialCollectionError(f"{label} must be an object")
    actual = set(value)
    if actual != fields:
        raise IssuerSequentialCollectionError(
            f"{label} fields differ: missing={sorted(fields - actual)} "
            f"extra={sorted(actual - fields)}"
        )
    return dict(value)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise IssuerSequentialCollectionError(f"{label} must be an uppercase identifier")
    return value


def _unique_text_list(value: Any, label: str, *, minimum: int = 1) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) < minimum
        or any(not isinstance(item, str) or not item or item != item.strip() for item in value)
        or len(set(value)) != len(value)
    ):
        raise IssuerSequentialCollectionError(
            f"{label} must be a unique non-empty string list"
        )
    return list(value)


def _bounded_integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise IssuerSequentialCollectionError(
            f"{label} must be an integer greater than or equal to {minimum}"
        )
    return value


def _load_object(path: Path, label: str) -> dict[str, Any]:
    payload, _content = _load_object_with_content(path, label)
    return payload


def _load_object_with_content(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    content = safe_regular_file(path, field=label)
    return strict_json_object(content, label), content


def _validate_policy(
    policy: Mapping[str, Any], catalog: SourceNetworkCatalog
) -> dict[str, Any]:
    root = _exact_object(policy, _TOP_LEVEL_FIELDS, "sequential collection policy")
    if root["schema_version"] != POLICY_SCHEMA_VERSION or root["policy_id"] != POLICY_ID:
        raise IssuerSequentialCollectionError("unsupported sequential collection policy")
    if root["market"] != "BOURSA_KUWAIT":
        raise IssuerSequentialCollectionError("sequential collection policy must remain Kuwait-only")

    execution = _exact_object(root["execution"], _EXECUTION_FIELDS, "execution")
    for field, expected in EXECUTION_INVARIANTS.items():
        if execution[field] != expected:
            raise IssuerSequentialCollectionError(f"execution.{field} violates the invariant")
    parallelism = execution["max_parallel_sources_within_security"]
    if (
        not isinstance(parallelism, int)
        or isinstance(parallelism, bool)
        or not 1 <= parallelism <= 16
    ):
        raise IssuerSequentialCollectionError(
            "execution.max_parallel_sources_within_security must be 1..16"
        )

    lifecycle = tuple(_unique_text_list(root["security_lifecycle"], "security_lifecycle", minimum=7))
    if lifecycle != SECURITY_LIFECYCLE:
        raise IssuerSequentialCollectionError("security lifecycle is incomplete or out of order")
    security_statuses = frozenset(
        _unique_text_list(root["terminal_security_statuses"], "terminal_security_statuses")
    )
    if security_statuses != TERMINAL_SECURITY_STATUSES:
        raise IssuerSequentialCollectionError("terminal security statuses are incomplete")
    source_statuses = frozenset(
        _unique_text_list(root["terminal_source_statuses"], "terminal_source_statuses")
    )
    if source_statuses != TERMINAL_SOURCE_STATUSES:
        raise IssuerSequentialCollectionError("terminal source statuses are incomplete")

    official = _exact_object(
        root["official_company_site"], _OFFICIAL_SITE_FIELDS, "official_company_site"
    )
    expected_official = {
        "source_id": "issuer_ir_verified",
        "required_for_every_security": True,
        "authority_binding": "SIGNED_RUNTIME_TRUST_REGISTRY",
        "domain_guessing_allowed": False,
        "unresolved_status": "ISSUER_OFFICIAL_SITE_UNRESOLVED",
    }
    for field, expected in expected_official.items():
        if official[field] != expected:
            raise IssuerSequentialCollectionError(
                f"official_company_site.{field} violates the invariant"
            )
    content_areas = _unique_text_list(
        official["required_content_areas"], "official_company_site.required_content_areas", minimum=6
    )
    if tuple(content_areas) != OFFICIAL_CONTENT_AREAS:
        raise IssuerSequentialCollectionError("official company content areas changed")

    raw_waves = root["source_waves"]
    if not isinstance(raw_waves, list) or len(raw_waves) != len(SOURCE_WAVE_SOURCES):
        raise IssuerSequentialCollectionError("source_waves must contain exactly seven waves")
    waves: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    seen_wave_ids: set[str] = set()
    for index, raw_wave in enumerate(raw_waves, start=1):
        wave = _exact_object(raw_wave, _WAVE_FIELDS, f"source_waves[{index - 1}]")
        wave_id = _identifier(wave["wave_id"], f"source_waves[{index - 1}].wave_id")
        if (
            wave_id in seen_wave_ids
            or wave["ordinal"] != index
            or wave_id != SOURCE_WAVE_IDS[index - 1]
        ):
            raise IssuerSequentialCollectionError("source waves must have unique contiguous ordinals")
        purpose = wave["purpose"]
        if not isinstance(purpose, str) or not purpose.strip() or purpose != purpose.strip():
            raise IssuerSequentialCollectionError("source wave purpose must be bounded text")
        source_ids = _unique_text_list(wave["source_ids"], f"source_waves[{index - 1}].source_ids")
        if tuple(source_ids) != SOURCE_WAVE_SOURCES[index - 1]:
            raise IssuerSequentialCollectionError(
                f"source_waves[{index - 1}] differs from its locked source/class role"
            )
        duplicates = seen_sources.intersection(source_ids)
        if duplicates:
            raise IssuerSequentialCollectionError(
                "a source may be planned only once per security: " + ",".join(sorted(duplicates))
            )
        unknown = set(source_ids) - set(catalog.sources)
        if unknown:
            raise IssuerSequentialCollectionError(
                "source waves reference unknown sources: " + ",".join(sorted(unknown))
            )
        for source_id in source_ids:
            source = catalog.sources[source_id]
            capability = catalog.capabilities[source_id]
            if source.source_class != SOURCE_CLASS_EXPECTATIONS[source_id]:
                raise IssuerSequentialCollectionError(
                    f"{source_id} source class differs from the locked security plan"
                )
            if source.requires_runtime_domain_registry != (
                source_id in RUNTIME_DOMAIN_REQUIRED_SOURCES
            ):
                raise IssuerSequentialCollectionError(
                    f"{source_id} runtime-domain gate differs from the locked security plan"
                )
            if source.requires_entitlement != (
                source_id in ENTITLEMENT_REQUIRED_SOURCES
            ):
                raise IssuerSequentialCollectionError(
                    f"{source_id} entitlement gate differs from the locked security plan"
                )
            if source.enabled_by_default != (source_id not in DISABLED_BY_DEFAULT_SOURCES):
                raise IssuerSequentialCollectionError(
                    f"{source_id} default activation differs from the locked security plan"
                )
            expected_capability = (
                "END_TO_END_TESTED" if source_id in FIXTURE_TESTED_SOURCES else "DEFINED_ONLY"
            )
            if capability.status != expected_capability:
                raise IssuerSequentialCollectionError(
                    f"{source_id} capability status requires a policy version change"
                )
        seen_wave_ids.add(wave_id)
        seen_sources.update(source_ids)
        waves.append(
            {
                "wave_id": wave_id,
                "ordinal": index,
                "source_ids": source_ids,
                "purpose": purpose,
            }
        )

    user_required = frozenset(
        _unique_text_list(root["user_required_source_ids"], "user_required_source_ids")
    )
    if user_required != USER_REQUIRED_SOURCE_IDS:
        raise IssuerSequentialCollectionError("user-required source denominator differs")
    if not user_required <= seen_sources:
        raise IssuerSequentialCollectionError("not every user-required source is scheduled")
    if official["source_id"] not in seen_sources:
        raise IssuerSequentialCollectionError("official company website is not scheduled")

    completion = _exact_object(
        root["completion_rules"], frozenset(COMPLETION_INVARIANTS), "completion_rules"
    )
    if completion != COMPLETION_INVARIANTS:
        raise IssuerSequentialCollectionError("completion rules violate security sealing")
    if root["claim_boundaries"] != CLAIM_BOUNDARIES:
        raise IssuerSequentialCollectionError("collection claim boundaries must remain false")

    root["execution"] = execution
    root["security_lifecycle"] = list(lifecycle)
    root["terminal_security_statuses"] = sorted(security_statuses)
    root["terminal_source_statuses"] = sorted(source_statuses)
    official["required_content_areas"] = content_areas
    root["official_company_site"] = official
    root["source_waves"] = waves
    root["user_required_source_ids"] = sorted(user_required)
    root["completion_rules"] = completion
    return root


def validate_issuer_sequential_collection_policy(project_root: Path | str) -> dict[str, Any]:
    root = Path(project_root)
    catalog = SourceNetworkCatalog(root / "config")
    policy_path = root / "config" / "issuer_sequential_collection_policy.json"
    policy_document, policy_content = _load_object_with_content(
        policy_path, "sequential collection policy"
    )
    policy = _validate_policy(policy_document, catalog)
    planned_sources = [
        source_id for wave in policy["source_waves"] for source_id in wave["source_ids"]
    ]
    return {
        "status": "PASS_CONTRACT_NOT_EXECUTED",
        "policy_id": policy["policy_id"],
        "policy_sha256": sha256_bytes(policy_content),
        "security_grain": policy["execution"]["grain"],
        "security_execution_mode": policy["execution"]["mode"],
        "max_active_securities": policy["execution"]["max_active_securities"],
        "planned_source_count_per_security": len(planned_sources),
        "source_wave_count": len(policy["source_waves"]),
        "user_required_source_ids": policy["user_required_source_ids"],
        "official_company_site_required": True,
        "claim_boundaries": policy["claim_boundaries"],
    }


def _active_identity_for_code(
    validated_universe: Mapping[str, Any], security_code: str
) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    as_of = validated_universe["as_of"].date()
    matches: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
    for issuer_id, issuer in validated_universe["issuers"].items():
        for identity in issuer["security_identities"]:
            if (
                identity["security_code"] == security_code
                and identity["_start"] <= as_of
                and (identity["_end"] is None or as_of <= identity["_end"])
                and identity["listing_status"] != "DELISTED"
            ):
                matches.append((issuer_id, issuer, identity))
    if len(matches) != 1:
        raise IssuerSequentialCollectionError(
            f"security {security_code} does not bind to exactly one active identity"
        )
    return matches[0]


def _canonical_universe_queue(
    validated_universe: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Derive the only permitted queue identity from an external universe."""

    rows: list[dict[str, Any]] = []
    ordered_codes = sorted(
        validated_universe["active_security_codes"],
        key=lambda code: (int(code), code),
    )
    for ordinal, code in enumerate(ordered_codes, start=1):
        issuer_id, issuer, identity = _active_identity_for_code(validated_universe, code)
        identity_payload = {
            "issuer_id": issuer_id,
            "security_code": code,
            "ticker": identity["ticker"],
            "isin": identity["isin"],
            "board": identity["board"],
            "market_segment": identity["market_segment"],
            "listing_status": identity["listing_status"],
            "legal_name_ar": issuer["legal_name_ar"],
            "legal_name_en": issuer["legal_name_en"],
        }
        query_terms = [identity["ticker"]]
        if identity["isin"] is not None:
            query_terms.append(identity["isin"])
        query_terms.extend([issuer["legal_name_ar"], issuer["legal_name_en"], code])
        rows.append(
            {
                "ordinal": ordinal,
                **identity_payload,
                "identity_sha256": hash_json(identity_payload),
                "query_terms": list(dict.fromkeys(query_terms)),
            }
        )
    return rows


def _validated_universe_authority(
    authority: Path | str | Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """Reopen and validate the universe supplied outside the plan trust boundary."""

    if isinstance(authority, Mapping):
        universe_document = copy.deepcopy(dict(authority))
        universe_sha256 = hash_json(universe_document)
    else:
        universe_path = Path(authority)
        universe_document, universe_content = _load_object_with_content(
            universe_path, "issuer universe authority"
        )
        universe_sha256 = hash_json(universe_document)
        if universe_content != safe_regular_file(
            universe_path, field="issuer universe authority"
        ):
            raise IssuerSequentialCollectionError(
                "issuer universe authority changed while it was reopened"
            )
    try:
        universe = validate_issuer_universe(universe_document)
    except CompanyDossierError as exc:
        raise IssuerSequentialCollectionError(str(exc)) from exc
    return universe, universe_sha256


def _source_plan(policy: Mapping[str, Any], catalog: SourceNetworkCatalog) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordinal = 0
    for wave in policy["source_waves"]:
        for source_id in wave["source_ids"]:
            ordinal += 1
            source = catalog.sources[source_id]
            capability = catalog.capabilities[source_id]
            rows.append(
                {
                    "source_ordinal": ordinal,
                    "wave_ordinal": wave["ordinal"],
                    "wave_id": wave["wave_id"],
                    "source_id": source_id,
                    "source_class": source.source_class,
                    "roles": sorted(source.roles),
                    "independence_group": source.independence_group,
                    "capability_status": capability.status,
                    "enabled_by_default": source.enabled_by_default,
                    "requires_runtime_domain_registry": source.requires_runtime_domain_registry,
                    "requires_entitlement": source.requires_entitlement,
                    "initial_status": "PLANNED",
                }
            )
    return rows


def compile_issuer_sequential_collection_plan(
    project_root: Path | str,
    universe_path: Path | str,
    *,
    run_id: str,
    generated_at: str | datetime,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise IssuerSequentialCollectionError("run_id is invalid")
    instant = parse_aware(generated_at, "generated_at")
    root = Path(project_root)
    universe_file = Path(universe_path)
    universe, universe_sha256 = _validated_universe_authority(universe_file)
    if universe["universe_status"] != "EXACT":
        raise IssuerSequentialCollectionError(
            "security-by-security collection requires an EXACT point-in-time universe"
        )
    if instant < universe["as_of"]:
        raise IssuerSequentialCollectionError(
            "generated_at cannot precede the point-in-time universe as_of"
        )

    policy_path = root / "config" / "issuer_sequential_collection_policy.json"
    policy_document, policy_content = _load_object_with_content(
        policy_path, "sequential collection policy"
    )
    network_path = root / "config" / "source_network.json"
    capability_path = root / "config" / "source_capabilities.json"
    network_content_before = safe_regular_file(network_path, field="source network")
    capability_content_before = safe_regular_file(
        capability_path, field="source capability matrix"
    )
    catalog = SourceNetworkCatalog(root / "config")
    if network_content_before != safe_regular_file(network_path, field="source network"):
        raise IssuerSequentialCollectionError("source network changed while plan was compiled")
    if capability_content_before != safe_regular_file(
        capability_path, field="source capability matrix"
    ):
        raise IssuerSequentialCollectionError(
            "source capability matrix changed while plan was compiled"
        )
    policy = _validate_policy(policy_document, catalog)
    source_plan = _source_plan(policy, catalog)

    queue: list[dict[str, Any]] = []
    for canonical_identity in _canonical_universe_queue(universe):
        ordinal = canonical_identity["ordinal"]
        code = canonical_identity["security_code"]
        issuer_id = canonical_identity["issuer_id"]
        authority_entries = []
        if runtime_trust_registry is not None:
            if not runtime_trust_registry.active_at(instant):
                raise IssuerSequentialCollectionError(
                    "runtime trust registry is not valid at generated_at"
                )
            authority_entries = [
                entry
                for entry in runtime_trust_registry.entries
                if entry.source_id == "issuer_ir_verified"
                and entry.subject_id == issuer_id
                and code in entry.security_codes
                and entry.active_at(instant)
            ]
            if len(authority_entries) > 1:
                raise IssuerSequentialCollectionError(
                    f"security {code} has ambiguous official-site authority"
                )
        authority = authority_entries[0] if authority_entries else None
        queue.append(
            {
                **canonical_identity,
                "initial_state": "QUEUED",
                "official_company_site": {
                    "source_id": "issuer_ir_verified",
                    "required": True,
                    "binding_status": (
                        "BOUND" if authority is not None else "REQUIRED_AT_EXECUTION"
                    ),
                    "authority_binding": "SIGNED_RUNTIME_TRUST_REGISTRY",
                    "domain_guessing_allowed": False,
                    "unresolved_terminal_status": "ISSUER_OFFICIAL_SITE_UNRESOLVED",
                    "required_content_areas": policy["official_company_site"][
                        "required_content_areas"
                    ],
                    "authority_registry_id": (
                        runtime_trust_registry.registry_id if authority is not None else None
                    ),
                    "authority_registry_sha256": (
                        runtime_trust_registry.content_sha256
                        if authority is not None
                        else None
                    ),
                    "authority_authenticated_key_id": (
                        runtime_trust_registry.authenticated_key_id
                        if authority is not None
                        else None
                    ),
                    "authority_registry_issued_at": (
                        runtime_trust_registry.issued_at.isoformat()
                        if authority is not None
                        else None
                    ),
                    "authority_registry_expires_at": (
                        runtime_trust_registry.expires_at.isoformat()
                        if authority is not None
                        else None
                    ),
                    "authority_subject_id": (
                        authority.subject_id if authority is not None else None
                    ),
                    "authority_entry_valid_from": (
                        authority.valid_from.isoformat() if authority is not None else None
                    ),
                    "authority_entry_valid_until": (
                        authority.valid_until.isoformat() if authority is not None else None
                    ),
                    "verified_domains": (
                        list(authority.domains) if authority is not None else []
                    ),
                    "activation_id": (
                        authority.activation_id if authority is not None else None
                    ),
                },
                "source_plan": copy.deepcopy(source_plan),
            }
        )

    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": f"{run_id}:security-sequential",
        "run_id": run_id,
        "generated_at": instant.isoformat(),
        "market": "BOURSA_KUWAIT",
        "universe_as_of": universe["as_of"].isoformat(),
        "universe_evidence_class": universe["evidence_class"],
        "universe_status": universe["universe_status"],
        "issuer_universe_sha256": universe_sha256,
        "policy_id": policy["policy_id"],
        "policy_sha256": sha256_bytes(policy_content),
        "source_network_sha256": sha256_bytes(network_content_before),
        "source_capabilities_sha256": sha256_bytes(capability_content_before),
        "execution": policy["execution"],
        "security_lifecycle": policy["security_lifecycle"],
        "terminal_security_statuses": policy["terminal_security_statuses"],
        "terminal_source_statuses": policy["terminal_source_statuses"],
        "security_count": len(queue),
        "planned_source_count_per_security": len(source_plan),
        "total_source_attempts_planned": len(queue) * len(source_plan),
        "user_required_source_ids": policy["user_required_source_ids"],
        "queue": queue,
        "completion_rules": policy["completion_rules"],
        "claim_boundaries": policy["claim_boundaries"],
    }
    plan["plan_sha256"] = hash_json(plan)
    return plan


def _validate_compiled_plan(
    plan: Mapping[str, Any],
    *,
    issuer_universe: Path | str | Mapping[str, Any],
    project_root: Path | str,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise IssuerSequentialCollectionError("collection plan must be an object")
    row = _exact_object(plan, _PLAN_FIELDS, "collection plan")
    if row.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise IssuerSequentialCollectionError("unsupported sequential collection plan")
    if row.get("policy_id") != POLICY_ID:
        raise IssuerSequentialCollectionError("collection plan policy id changed")
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise IssuerSequentialCollectionError("collection plan run_id is invalid")
    if row.get("plan_id") != f"{run_id}:security-sequential":
        raise IssuerSequentialCollectionError("collection plan_id is not derived from run_id")
    submitted_hash = row.get("plan_sha256")
    if not isinstance(submitted_hash, str):
        raise IssuerSequentialCollectionError("collection plan lacks plan_sha256")
    material = {key: value for key, value in row.items() if key != "plan_sha256"}
    if hash_json(material) != submitted_hash:
        raise IssuerSequentialCollectionError("collection plan hash mismatch")
    if row.get("universe_status") != "EXACT" or row.get("market") != "BOURSA_KUWAIT":
        raise IssuerSequentialCollectionError("collection plan lacks an exact Kuwait universe")
    generated_at = parse_aware(row.get("generated_at"), "collection plan generated_at")
    universe_as_of = parse_aware(row.get("universe_as_of"), "collection plan universe_as_of")
    if generated_at < universe_as_of:
        raise IssuerSequentialCollectionError(
            "collection plan generated_at precedes universe_as_of"
        )
    for field in (
        "issuer_universe_sha256",
        "policy_sha256",
        "source_network_sha256",
        "source_capabilities_sha256",
    ):
        value = row.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise IssuerSequentialCollectionError(f"collection plan {field} is invalid")
    trusted_universe, universe_sha256 = _validated_universe_authority(issuer_universe)
    if universe_sha256 != row["issuer_universe_sha256"]:
        raise IssuerSequentialCollectionError(
            "collection plan differs from the reopened issuer universe authority"
        )
    if (
        trusted_universe["universe_status"] != "EXACT"
        or trusted_universe["as_of"].isoformat() != row["universe_as_of"]
        or trusted_universe["evidence_class"] != row["universe_evidence_class"]
    ):
        raise IssuerSequentialCollectionError(
            "collection plan universe metadata differs from the reopened authority"
        )
    canonical_universe_queue = _canonical_universe_queue(trusted_universe)
    root = Path(project_root)
    policy_document, policy_content = _load_object_with_content(
        root / "config" / "issuer_sequential_collection_policy.json",
        "sequential collection policy",
    )
    network_content = safe_regular_file(
        root / "config" / "source_network.json", field="source network"
    )
    capability_content = safe_regular_file(
        root / "config" / "source_capabilities.json",
        field="source capability matrix",
    )
    if (
        sha256_bytes(policy_content) != row["policy_sha256"]
        or sha256_bytes(network_content) != row["source_network_sha256"]
        or sha256_bytes(capability_content) != row["source_capabilities_sha256"]
    ):
        raise IssuerSequentialCollectionError(
            "collection plan config hashes differ from the reopened project root"
        )
    catalog = SourceNetworkCatalog(root / "config")
    if (
        network_content
        != safe_regular_file(root / "config" / "source_network.json", field="source network")
        or capability_content
        != safe_regular_file(
            root / "config" / "source_capabilities.json",
            field="source capability matrix",
        )
        or policy_content
        != safe_regular_file(
            root / "config" / "issuer_sequential_collection_policy.json",
            field="sequential collection policy",
        )
    ):
        raise IssuerSequentialCollectionError(
            "collection config changed while the plan was reopened"
        )
    canonical_policy = _validate_policy(policy_document, catalog)
    canonical_source_plan = _source_plan(canonical_policy, catalog)
    execution = row.get("execution")
    if not isinstance(execution, Mapping):
        raise IssuerSequentialCollectionError("collection plan execution is invalid")
    for field, expected in EXECUTION_INVARIANTS.items():
        if execution.get(field) != expected:
            raise IssuerSequentialCollectionError(
                f"collection plan execution.{field} violates the invariant"
            )
    parallelism = execution.get("max_parallel_sources_within_security")
    if (
        not isinstance(parallelism, int)
        or isinstance(parallelism, bool)
        or not 1 <= parallelism <= 16
    ):
        raise IssuerSequentialCollectionError("collection plan source parallelism is invalid")
    if tuple(row.get("security_lifecycle", ())) != SECURITY_LIFECYCLE:
        raise IssuerSequentialCollectionError("collection plan security lifecycle changed")
    if row.get("completion_rules") != COMPLETION_INVARIANTS:
        raise IssuerSequentialCollectionError("collection plan completion rules changed")
    if row.get("claim_boundaries") != CLAIM_BOUNDARIES:
        raise IssuerSequentialCollectionError("collection plan claim boundaries changed")
    if row.get("terminal_source_statuses") != sorted(TERMINAL_SOURCE_STATUSES):
        raise IssuerSequentialCollectionError("collection plan terminal source statuses changed")
    if row.get("terminal_security_statuses") != sorted(TERMINAL_SECURITY_STATUSES):
        raise IssuerSequentialCollectionError("collection plan terminal security statuses changed")
    if row.get("user_required_source_ids") != sorted(USER_REQUIRED_SOURCE_IDS):
        raise IssuerSequentialCollectionError("collection plan user source denominator changed")

    queue = row.get("queue")
    if not isinstance(queue, list) or not queue:
        raise IssuerSequentialCollectionError("collection plan queue must be non-empty")
    if len(queue) != len(canonical_universe_queue):
        raise IssuerSequentialCollectionError(
            "collection plan security denominator differs from the reopened issuer universe"
        )
    security_count = _bounded_integer(
        row.get("security_count"), "collection plan security_count", minimum=1
    )
    if security_count != len(queue):
        raise IssuerSequentialCollectionError("collection plan security count is inconsistent")
    source_count = _bounded_integer(
        row.get("planned_source_count_per_security"),
        "collection plan planned_source_count_per_security",
        minimum=1,
    )
    expected_source_ids = tuple(
        source_id for source_ids in SOURCE_WAVE_SOURCES for source_id in source_ids
    )
    if source_count != len(expected_source_ids):
        raise IssuerSequentialCollectionError("collection plan source count is invalid")
    total_source_attempts = _bounded_integer(
        row.get("total_source_attempts_planned"),
        "collection plan total_source_attempts_planned",
        minimum=1,
    )
    if total_source_attempts != len(queue) * source_count:
        raise IssuerSequentialCollectionError("collection plan attempt count is inconsistent")

    codes: list[str] = []
    canonical_source_plan_sha256: str | None = None
    for ordinal, security in enumerate(queue, start=1):
        canonical_identity = canonical_universe_queue[ordinal - 1]
        security = _exact_object(
            security, _SECURITY_PLAN_FIELDS, f"collection plan queue[{ordinal - 1}]"
        )
        if _bounded_integer(
            security.get("ordinal"), "security queue ordinal", minimum=1
        ) != ordinal:
            raise IssuerSequentialCollectionError("security queue ordinals are not contiguous")
        code = str(security.get("security_code", ""))
        if not code.isdigit():
            raise IssuerSequentialCollectionError("security queue contains an invalid code")
        codes.append(code)
        if security.get("initial_state") != "QUEUED":
            raise IssuerSequentialCollectionError("security does not begin QUEUED")
        reopened_identity = {
            field: security.get(field) for field in canonical_identity
        }
        if canonical_json_bytes(reopened_identity) != canonical_json_bytes(
            canonical_identity
        ):
            raise IssuerSequentialCollectionError(
                "security queue identity differs from the reopened issuer universe"
            )
        identity_payload = {
            field: security.get(field)
            for field in (
                "issuer_id",
                "security_code",
                "ticker",
                "isin",
                "board",
                "market_segment",
                "listing_status",
                "legal_name_ar",
                "legal_name_en",
            )
        }
        if hash_json(identity_payload) != security.get("identity_sha256"):
            raise IssuerSequentialCollectionError("security identity hash mismatch")
        query_terms = _unique_text_list(
            security.get("query_terms"), f"security {code} query_terms"
        )
        if security.get("ticker") not in query_terms or code not in query_terms:
            raise IssuerSequentialCollectionError(
                "security query terms do not retain ticker and security code"
            )
        official = _exact_object(
            security.get("official_company_site"),
            _OFFICIAL_PLAN_FIELDS,
            f"security {code} official_company_site",
        )
        if official.get("source_id") != "issuer_ir_verified":
            raise IssuerSequentialCollectionError("security lacks its official company source")
        if (
            official.get("required") is not True
            or official.get("domain_guessing_allowed") is not False
            or official.get("authority_binding") != "SIGNED_RUNTIME_TRUST_REGISTRY"
            or official.get("unresolved_terminal_status")
            != "ISSUER_OFFICIAL_SITE_UNRESOLVED"
            or tuple(official.get("required_content_areas", ()))
            != OFFICIAL_CONTENT_AREAS
        ):
            raise IssuerSequentialCollectionError("official company source binding is unsafe")
        binding_status = official.get("binding_status")
        if binding_status == "BOUND":
            if (
                not isinstance(official.get("authority_registry_id"), str)
                or not isinstance(official.get("authority_subject_id"), str)
                or official.get("authority_subject_id") != security.get("issuer_id")
                or not isinstance(official.get("authority_registry_sha256"), str)
                or re.fullmatch(
                    r"[0-9a-f]{64}", str(official.get("authority_registry_sha256"))
                )
                is None
                or not isinstance(official.get("verified_domains"), list)
                or not official["verified_domains"]
                or len(official["verified_domains"])
                != len(set(official["verified_domains"]))
                or any(
                    not isinstance(domain, str)
                    or domain != domain.casefold()
                    or re.fullmatch(
                        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}",
                        domain,
                    )
                    is None
                    for domain in official["verified_domains"]
                )
                or not isinstance(official.get("authority_authenticated_key_id"), str)
                or not official["authority_authenticated_key_id"]
            ):
                raise IssuerSequentialCollectionError(
                    "bound official company source lacks exact registry evidence"
                )
            registry_issued = parse_aware(
                official.get("authority_registry_issued_at"),
                "official company authority registry issued_at",
            )
            registry_expires = parse_aware(
                official.get("authority_registry_expires_at"),
                "official company authority registry expires_at",
            )
            entry_from = parse_aware(
                official.get("authority_entry_valid_from"),
                "official company authority entry valid_from",
            )
            entry_until = parse_aware(
                official.get("authority_entry_valid_until"),
                "official company authority entry valid_until",
            )
            if not (
                registry_issued <= generated_at < registry_expires
                and entry_from <= generated_at < entry_until
            ):
                raise IssuerSequentialCollectionError(
                    "official company authority is not valid at plan generation"
                )
            if runtime_trust_registry is None:
                raise IssuerSequentialCollectionError(
                    "bound official company source requires a reopened runtime trust registry"
                )
            if (
                runtime_trust_registry.registry_id != official["authority_registry_id"]
                or runtime_trust_registry.content_sha256
                != official["authority_registry_sha256"]
                or runtime_trust_registry.authenticated_key_id
                != official["authority_authenticated_key_id"]
                or runtime_trust_registry.issued_at.isoformat()
                != official["authority_registry_issued_at"]
                or runtime_trust_registry.expires_at.isoformat()
                != official["authority_registry_expires_at"]
            ):
                raise IssuerSequentialCollectionError(
                    "bound official company source differs from the reopened runtime registry"
                )
            authority_entries = [
                entry
                for entry in runtime_trust_registry.entries
                if entry.source_id == "issuer_ir_verified"
                and entry.subject_id == security["issuer_id"]
                and security["security_code"] in entry.security_codes
                and entry.active_at(generated_at)
            ]
            if len(authority_entries) != 1:
                raise IssuerSequentialCollectionError(
                    "official company runtime authority is not unique at plan generation"
                )
            authority_entry = authority_entries[0]
            if (
                list(authority_entry.domains) != official["verified_domains"]
                or authority_entry.activation_id != official["activation_id"]
                or authority_entry.valid_from.isoformat()
                != official["authority_entry_valid_from"]
                or authority_entry.valid_until.isoformat()
                != official["authority_entry_valid_until"]
            ):
                raise IssuerSequentialCollectionError(
                    "official company plan binding differs from the authenticated registry entry"
                )
        elif binding_status == "REQUIRED_AT_EXECUTION":
            if any(
                official.get(field) is not None
                for field in (
                    "authority_registry_id",
                    "authority_registry_sha256",
                    "authority_authenticated_key_id",
                    "authority_registry_issued_at",
                    "authority_registry_expires_at",
                    "authority_subject_id",
                    "authority_entry_valid_from",
                    "authority_entry_valid_until",
                    "activation_id",
                )
            ) or official.get("verified_domains") != []:
                raise IssuerSequentialCollectionError(
                    "unbound official company source contains asserted authority"
                )
        else:
            raise IssuerSequentialCollectionError("official company binding status is invalid")
        sources = security.get("source_plan")
        if not isinstance(sources, list) or len(sources) != source_count:
            raise IssuerSequentialCollectionError("security source plan count is inconsistent")
        source_ids: list[str] = []
        for source_ordinal, source in enumerate(sources, start=1):
            source = _exact_object(
                source,
                _SOURCE_PLAN_FIELDS,
                f"security {code} source_plan[{source_ordinal - 1}]",
            )
            if _bounded_integer(
                source.get("source_ordinal"), "source plan ordinal", minimum=1
            ) != source_ordinal:
                raise IssuerSequentialCollectionError("source plan ordinals are not contiguous")
            source_id = str(source.get("source_id", ""))
            if not source_id or source.get("initial_status") != "PLANNED":
                raise IssuerSequentialCollectionError("source plan contains an invalid row")
            expected_source_id = expected_source_ids[source_ordinal - 1]
            expected_wave_ordinal = next(
                wave_ordinal
                for wave_ordinal, source_ids_in_wave in enumerate(
                    SOURCE_WAVE_SOURCES, start=1
                )
                if expected_source_id in source_ids_in_wave
            )
            wave_ordinal = _bounded_integer(
                source.get("wave_ordinal"), "source plan wave_ordinal", minimum=1
            )
            if (
                source_id != expected_source_id
                or wave_ordinal != expected_wave_ordinal
                or source.get("wave_id") != SOURCE_WAVE_IDS[expected_wave_ordinal - 1]
                or source.get("source_class") != SOURCE_CLASS_EXPECTATIONS[source_id]
                or source.get("requires_runtime_domain_registry")
                != (source_id in RUNTIME_DOMAIN_REQUIRED_SOURCES)
                or source.get("requires_entitlement")
                != (source_id in ENTITLEMENT_REQUIRED_SOURCES)
                or source.get("enabled_by_default")
                != (source_id not in DISABLED_BY_DEFAULT_SOURCES)
                or source.get("capability_status")
                != (
                    "END_TO_END_TESTED"
                    if source_id in FIXTURE_TESTED_SOURCES
                    else "DEFINED_ONLY"
                )
            ):
                raise IssuerSequentialCollectionError(
                    "source plan differs from the locked per-security denominator"
                )
            _unique_text_list(source.get("roles"), f"source {source_id} roles")
            if (
                not isinstance(source.get("independence_group"), str)
                or not source["independence_group"].strip()
            ):
                raise IssuerSequentialCollectionError(
                    "source plan independence group is invalid"
                )
            source_ids.append(source_id)
        if tuple(source_ids) != expected_source_ids:
            raise IssuerSequentialCollectionError(
                "each security must contain the exact locked source denominator"
            )
        if canonical_json_bytes(sources) != canonical_json_bytes(canonical_source_plan):
            raise IssuerSequentialCollectionError(
                "security source plan differs from the reopened catalog and capability matrix"
            )
        current_source_plan_sha256 = hash_json(sources)
        if canonical_source_plan_sha256 is None:
            canonical_source_plan_sha256 = current_source_plan_sha256
        elif current_source_plan_sha256 != canonical_source_plan_sha256:
            raise IssuerSequentialCollectionError(
                "every security must receive the identical source denominator"
            )
    if len(codes) != len(set(codes)) or codes != sorted(codes, key=lambda code: (int(code), code)):
        raise IssuerSequentialCollectionError(
            "security queue must be unique and ordered by numeric security code"
        )
    return copy.deepcopy(row)


def validate_issuer_sequential_collection_plan(
    plan: Mapping[str, Any],
    *,
    issuer_universe: Path | str | Mapping[str, Any],
    project_root: Path | str,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    trusted = _validate_compiled_plan(
        plan,
        issuer_universe=issuer_universe,
        project_root=project_root,
        runtime_trust_registry=runtime_trust_registry,
    )
    bound_sites = sum(
        item["official_company_site"]["binding_status"] == "BOUND"
        for item in trusted["queue"]
    )
    return {
        "status": "PASS_PLAN_NOT_EXECUTED",
        "plan_id": trusted["plan_id"],
        "plan_sha256": trusted["plan_sha256"],
        "security_count": trusted["security_count"],
        "planned_source_count_per_security": trusted[
            "planned_source_count_per_security"
        ],
        "total_source_attempts_planned": trusted["total_source_attempts_planned"],
        "official_company_sites_bound": bound_sites,
        "official_company_sites_pending": trusted["security_count"] - bound_sites,
        "universe_evidence_class": trusted["universe_evidence_class"],
        "full_market_claim_allowed": False,
        "claim_boundaries": trusted["claim_boundaries"],
    }


def validate_issuer_sequential_collection_plan_file(
    path: Path | str,
    *,
    issuer_universe: Path | str | Mapping[str, Any],
    project_root: Path | str,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    plan = _load_object(Path(path), "sequential collection plan")
    return validate_issuer_sequential_collection_plan(
        plan,
        issuer_universe=issuer_universe,
        project_root=project_root,
        runtime_trust_registry=runtime_trust_registry,
    )


def _attempt_receipt(
    security: Mapping[str, Any],
    source: Mapping[str, Any],
    raw_result: Mapping[str, Any],
    *,
    runtime_trust_registry: RuntimeTrustRegistry | None,
) -> dict[str, Any]:
    result = _exact_object(raw_result, _ATTEMPT_RESULT_FIELDS, "source attempt result")
    terminal_status = result["terminal_status"]
    if terminal_status not in TERMINAL_SOURCE_STATUSES:
        raise IssuerSequentialCollectionError("source attempt did not return a terminal status")
    attempted = parse_aware(result["attempted_at"], "source attempt attempted_at")
    completed = parse_aware(result["completed_at"], "source attempt completed_at")
    if completed < attempted:
        raise IssuerSequentialCollectionError("source attempt completed before it started")
    artifact_count = result["artifact_count"]
    observation_count = result["observation_count"]
    if (
        not isinstance(artifact_count, int)
        or isinstance(artifact_count, bool)
        or artifact_count < 0
        or not isinstance(observation_count, int)
        or isinstance(observation_count, bool)
        or observation_count < 0
    ):
        raise IssuerSequentialCollectionError("source attempt counts must be non-negative integers")
    limitation = result["limitation"]
    if not isinstance(limitation, str) or limitation != limitation.strip() or len(limitation) > 2000:
        raise IssuerSequentialCollectionError("source attempt limitation must be bounded text")
    if terminal_status in _NON_BLOCKING_SOURCE_STATUSES and artifact_count < 1:
        raise IssuerSequentialCollectionError(
            f"{terminal_status} source must retain at least one artifact"
        )
    if terminal_status != "COLLECTED" and observation_count:
        raise IssuerSequentialCollectionError(
            "only COLLECTED source attempts may report observations"
        )
    requested_domain = result["requested_domain"]
    activation_id = result["activation_id"]
    entitlement_id = result["entitlement_id"]
    artifact_manifest_sha256 = result["artifact_manifest_sha256"]
    for value, field in (
        (requested_domain, "requested_domain"),
        (activation_id, "activation_id"),
        (entitlement_id, "entitlement_id"),
    ):
        if value is not None and (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 255
        ):
            raise IssuerSequentialCollectionError(
                f"source attempt {field} must be null or a bounded identifier"
            )
    if artifact_manifest_sha256 is not None and (
        not isinstance(artifact_manifest_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", artifact_manifest_sha256) is None
    ):
        raise IssuerSequentialCollectionError(
            "source attempt artifact_manifest_sha256 is invalid"
        )
    if artifact_count and artifact_manifest_sha256 is None:
        raise IssuerSequentialCollectionError(
            "retained source artifacts require a manifest SHA-256"
        )
    if terminal_status in _NON_BLOCKING_SOURCE_STATUSES and artifact_manifest_sha256 is None:
        raise IssuerSequentialCollectionError(
            f"{terminal_status} source requires a reopenable artifact manifest digest"
        )

    source_id = source["source_id"]
    affirmative = terminal_status in _NON_BLOCKING_SOURCE_STATUSES
    requires_domain = bool(source["requires_runtime_domain_registry"])
    requires_entitlement = bool(source["requires_entitlement"])
    authority_bound = False
    authority_registry_id: str | None = None
    authority_registry_sha256: str | None = None
    authority_authenticated_key_id: str | None = None

    if terminal_status == "ISSUER_OFFICIAL_SITE_UNRESOLVED" and source_id != "issuer_ir_verified":
        raise IssuerSequentialCollectionError(
            "official-site unresolved status belongs only to issuer_ir_verified"
        )
    if source_id == "issuer_ir_verified":
        official = security["official_company_site"]
        if official["binding_status"] != "BOUND":
            if terminal_status != "ISSUER_OFFICIAL_SITE_UNRESOLVED":
                raise IssuerSequentialCollectionError(
                    "unbound official company website must retain its explicit unresolved status"
                )
        elif terminal_status == "REVIEWED_NOT_APPLICABLE":
            raise IssuerSequentialCollectionError(
                "required official company website cannot be marked not applicable"
            )

    if affirmative and (requires_domain or requires_entitlement):
        if runtime_trust_registry is None:
            raise IssuerSequentialCollectionError(
                f"{source_id} cannot be verified without a reopened runtime trust registry"
            )
        try:
            authority_entries = []
            if source_id == "issuer_ir_verified":
                official = security["official_company_site"]
                if official["binding_status"] != "BOUND":
                    raise IssuerSequentialCollectionError(
                        "official company website lacks a signed plan binding"
                    )
                if (
                    runtime_trust_registry.registry_id
                    != official["authority_registry_id"]
                    or runtime_trust_registry.content_sha256
                    != official["authority_registry_sha256"]
                    or runtime_trust_registry.authenticated_key_id
                    != official["authority_authenticated_key_id"]
                ):
                    raise IssuerSequentialCollectionError(
                        "official company runtime registry differs from the signed plan binding"
                    )
                if requested_domain is None:
                    raise IssuerSequentialCollectionError(
                        "official company source requires the tested domain"
                    )
                authority_entries.append(
                    runtime_trust_registry.require_authority(
                        source_id=source_id,
                        subject_id=security["issuer_id"],
                        domain=requested_domain,
                        decision_at=attempted,
                        security_code=security["security_code"],
                    )
                )
            elif requires_domain:
                if activation_id is None or requested_domain is None:
                    raise IssuerSequentialCollectionError(
                        f"{source_id} requires activation and tested-domain evidence"
                    )
                activation_entry = runtime_trust_registry.require_activation(
                    source_id=source_id,
                    activation_id=activation_id,
                    decision_at=attempted,
                    security_code=security["security_code"],
                )
                if not activation_entry.authorizes_domain(requested_domain):
                    raise IssuerSequentialCollectionError(
                        f"{source_id} tested domain is outside the authorized activation"
                    )
                authority_entries.append(activation_entry)
            if requires_entitlement:
                if entitlement_id is None:
                    raise IssuerSequentialCollectionError(
                        f"{source_id} requires entitlement evidence"
                    )
                authority_entries.append(
                    runtime_trust_registry.require_entitlement(
                        source_id=source_id,
                        entitlement_id=entitlement_id,
                        decision_at=attempted,
                        security_code=security["security_code"],
                    )
                )
            if len(authority_entries) > 1 and any(
                entry != authority_entries[0] for entry in authority_entries[1:]
            ):
                raise IssuerSequentialCollectionError(
                    f"{source_id} activation and entitlement do not bind the same authority entry"
                )
        except RuntimeTrustError as exc:
            raise IssuerSequentialCollectionError(str(exc)) from exc
        authority_bound = True
        authority_registry_id = runtime_trust_registry.registry_id
        authority_registry_sha256 = runtime_trust_registry.content_sha256
        authority_authenticated_key_id = runtime_trust_registry.authenticated_key_id
    elif any(value is not None for value in (activation_id, entitlement_id)):
        raise IssuerSequentialCollectionError(
            "source attempt cannot assert activation or entitlement without verified data"
        )
    receipt = {
        "source_ordinal": source["source_ordinal"],
        "wave_ordinal": source["wave_ordinal"],
        "wave_id": source["wave_id"],
        "source_id": source["source_id"],
        "terminal_status": terminal_status,
        "attempted_at": attempted.isoformat(),
        "completed_at": completed.isoformat(),
        "artifact_count": artifact_count,
        "observation_count": observation_count,
        "requested_domain": requested_domain,
        "activation_id": activation_id,
        "entitlement_id": entitlement_id,
        "artifact_manifest_sha256": artifact_manifest_sha256,
        "runtime_authority_bound": authority_bound,
        "authority_registry_id": authority_registry_id,
        "authority_registry_sha256": authority_registry_sha256,
        "authority_authenticated_key_id": authority_authenticated_key_id,
        "limitation": limitation,
        "security_code": security["security_code"],
    }
    receipt["source_receipt_sha256"] = hash_json(receipt)
    return receipt


def execute_issuer_sequential_collection_plan(
    plan: Mapping[str, Any],
    attempt_source: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]],
    *,
    project_root: Path | str,
    issuer_universe: Path | str | Mapping[str, Any],
    observed_at: str | datetime,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    """Execute a trusted plan through an injected source-attempt adapter.

    The coordinator is deliberately synchronous at the security boundary: every
    planned source for one security receives a terminal receipt and the security
    is sealed before the next security can start. The injected adapter owns actual
    network access, retries, rights checks, raw storage, and parsing. Expected
    source/network/parser failures must be normalized by that adapter into one of
    the terminal statuses. An exception or malformed receipt is a fatal adapter-
    contract violation, not a source-local business outcome.
    """

    trusted = _validate_compiled_plan(
        plan,
        issuer_universe=issuer_universe,
        project_root=project_root,
        runtime_trust_registry=runtime_trust_registry,
    )
    plan_generated_at = parse_aware(trusted["generated_at"], "collection plan generated_at")
    observed = parse_aware(observed_at, "collection run observed_at")
    if observed < plan_generated_at:
        raise IssuerSequentialCollectionError(
            "collection run observed_at precedes plan generation"
        )
    security_receipts: list[dict[str, Any]] = []
    previous_seal_sha256: str | None = None
    previous_completed_at: datetime | None = None
    for security in trusted["queue"]:
        source_receipts: list[dict[str, Any]] = []
        for source in security["source_plan"]:
            raw_result = attempt_source(
                copy.deepcopy(security),
                copy.deepcopy(source),
            )
            if not isinstance(raw_result, Mapping):
                raise IssuerSequentialCollectionError(
                    "source adapter must return a terminal receipt object"
                )
            receipt = _attempt_receipt(
                security,
                source,
                raw_result,
                runtime_trust_registry=runtime_trust_registry,
            )
            attempted = parse_aware(receipt["attempted_at"], "source receipt attempted_at")
            completed_at = parse_aware(
                receipt["completed_at"], "source receipt completed_at"
            )
            if attempted < plan_generated_at:
                raise IssuerSequentialCollectionError(
                    "source attempt started before the collection plan was generated"
                )
            if completed_at > observed:
                raise IssuerSequentialCollectionError(
                    "source attempt completed after collection run observed_at"
                )
            source_receipts.append(receipt)
        started = min(
            parse_aware(item["attempted_at"], "source receipt attempted_at")
            for item in source_receipts
        )
        completed = max(
            parse_aware(item["completed_at"], "source receipt completed_at")
            for item in source_receipts
        )
        if previous_completed_at is not None and started < previous_completed_at:
            raise IssuerSequentialCollectionError(
                "next security started before the previous security was sealed"
            )
        non_blocking = sum(
            item["terminal_status"] in _NON_BLOCKING_SOURCE_STATUSES
            for item in source_receipts
        )
        if non_blocking == len(source_receipts):
            seal_status = "SEALED_ALL_SOURCE_ATTEMPTS_TERMINAL"
        elif non_blocking:
            seal_status = "SEALED_WITH_EXPLICIT_GAPS"
        else:
            seal_status = "SEALED_BLOCKED"
        security_receipt = {
            "ordinal": security["ordinal"],
            "issuer_id": security["issuer_id"],
            "security_code": security["security_code"],
            "ticker": security["ticker"],
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "seal_status": seal_status,
            "planned_source_count": len(source_receipts),
            "terminal_source_count": len(source_receipts),
            "collected_source_count": sum(
                item["terminal_status"] == "COLLECTED" for item in source_receipts
            ),
            "explicit_gap_source_count": len(source_receipts) - non_blocking,
            "artifact_count": sum(item["artifact_count"] for item in source_receipts),
            "observation_count": sum(
                item["observation_count"] for item in source_receipts
            ),
            "previous_security_seal_sha256": previous_seal_sha256,
            "source_receipts": source_receipts,
        }
        security_receipt["security_seal_sha256"] = hash_json(security_receipt)
        security_receipts.append(security_receipt)
        previous_seal_sha256 = security_receipt["security_seal_sha256"]
        previous_completed_at = completed

    seals = [item["seal_status"] for item in security_receipts]
    if all(status == "SEALED_ALL_SOURCE_ATTEMPTS_TERMINAL" for status in seals):
        status = "ALL_SECURITIES_TERMINAL_NO_SOURCE_GAPS"
    elif any(status == "SEALED_BLOCKED" for status in seals):
        status = "ALL_SECURITIES_TERMINAL_BLOCKED"
    else:
        status = "ALL_SECURITIES_TERMINAL_WITH_EXPLICIT_GAPS"
    run = {
        "schema_version": "issuer-sequential-collection-run-v1",
        "run_id": trusted["run_id"],
        "plan_id": trusted["plan_id"],
        "plan_sha256": trusted["plan_sha256"],
        "market": "BOURSA_KUWAIT",
        "observed_at": observed.isoformat(),
        "execution_evidence_class": "ADAPTER_ASSERTED_RECEIPTS",
        "status": status,
        "security_count": len(security_receipts),
        "sealed_security_count": len(security_receipts),
        "planned_source_attempt_count": trusted["total_source_attempts_planned"],
        "terminal_source_attempt_count": sum(
            item["terminal_source_count"] for item in security_receipts
        ),
        "artifact_count": sum(item["artifact_count"] for item in security_receipts),
        "observation_count": sum(
            item["observation_count"] for item in security_receipts
        ),
        "security_receipts": security_receipts,
        "claim_boundaries": _RUN_CLAIM_BOUNDARIES,
    }
    run["run_receipt_sha256"] = hash_json(run)
    return run


def _validated_run_document(
    run: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    project_root: Path | str,
    issuer_universe: Path | str | Mapping[str, Any],
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    trusted_plan = _validate_compiled_plan(
        plan,
        issuer_universe=issuer_universe,
        project_root=project_root,
        runtime_trust_registry=runtime_trust_registry,
    )
    row = _exact_object(run, _RUN_FIELDS, "sequential collection run")
    submitted_hash = row.get("run_receipt_sha256")
    if not isinstance(submitted_hash, str) or hash_json(
        {key: value for key, value in row.items() if key != "run_receipt_sha256"}
    ) != submitted_hash:
        raise IssuerSequentialCollectionError("collection run receipt hash mismatch")
    if (
        row.get("schema_version") != "issuer-sequential-collection-run-v1"
        or row.get("run_id") != trusted_plan["run_id"]
        or row.get("plan_id") != trusted_plan["plan_id"]
        or row.get("plan_sha256") != trusted_plan["plan_sha256"]
        or row.get("market") != "BOURSA_KUWAIT"
        or row.get("execution_evidence_class") != "ADAPTER_ASSERTED_RECEIPTS"
        or row.get("claim_boundaries") != _RUN_CLAIM_BOUNDARIES
    ):
        raise IssuerSequentialCollectionError("collection run identity or claims changed")
    for field, minimum in (
        ("security_count", 1),
        ("sealed_security_count", 1),
        ("planned_source_attempt_count", 1),
        ("terminal_source_attempt_count", 1),
        ("artifact_count", 0),
        ("observation_count", 0),
    ):
        _bounded_integer(row.get(field), f"collection run {field}", minimum=minimum)
    observed = parse_aware(row.get("observed_at"), "collection run observed_at")
    generated = parse_aware(trusted_plan["generated_at"], "collection plan generated_at")
    if observed < generated:
        raise IssuerSequentialCollectionError("collection run predates its plan")

    security_receipts = row.get("security_receipts")
    if not isinstance(security_receipts, list) or len(security_receipts) != len(
        trusted_plan["queue"]
    ):
        raise IssuerSequentialCollectionError("collection run security denominator differs")

    previous_seal: str | None = None
    previous_completed: datetime | None = None
    total_artifacts = 0
    total_observations = 0
    total_sources = 0
    seals: list[str] = []
    for planned_security, raw_security_receipt in zip(
        trusted_plan["queue"], security_receipts, strict=True
    ):
        security_receipt = _exact_object(
            raw_security_receipt,
            _SECURITY_RECEIPT_FIELDS,
            f"security receipt {planned_security['security_code']}",
        )
        _bounded_integer(
            security_receipt.get("ordinal"), "security receipt ordinal", minimum=1
        )
        for field in ("ordinal", "issuer_id", "security_code", "ticker"):
            if security_receipt.get(field) != planned_security[field]:
                raise IssuerSequentialCollectionError(
                    f"security receipt {field} differs from the collection plan"
                )
        source_receipts = security_receipt.get("source_receipts")
        if not isinstance(source_receipts, list) or len(source_receipts) != len(
            planned_security["source_plan"]
        ):
            raise IssuerSequentialCollectionError(
                "security receipt source denominator differs from the collection plan"
            )
        reopened_sources: list[dict[str, Any]] = []
        for planned_source, raw_source_receipt in zip(
            planned_security["source_plan"], source_receipts, strict=True
        ):
            source_receipt = _exact_object(
                raw_source_receipt,
                _SOURCE_RECEIPT_FIELDS,
                f"source receipt {planned_source['source_id']}",
            )
            submitted_source_hash = source_receipt["source_receipt_sha256"]
            if not isinstance(submitted_source_hash, str) or hash_json(
                {
                    key: value
                    for key, value in source_receipt.items()
                    if key != "source_receipt_sha256"
                }
            ) != submitted_source_hash:
                raise IssuerSequentialCollectionError("source receipt hash mismatch")
            raw_result = {
                "terminal_status": source_receipt["terminal_status"],
                "attempted_at": source_receipt["attempted_at"],
                "completed_at": source_receipt["completed_at"],
                "artifact_count": source_receipt["artifact_count"],
                "observation_count": source_receipt["observation_count"],
                "requested_domain": source_receipt["requested_domain"],
                "activation_id": source_receipt["activation_id"],
                "entitlement_id": source_receipt["entitlement_id"],
                "artifact_manifest_sha256": source_receipt[
                    "artifact_manifest_sha256"
                ],
                "limitation": source_receipt["limitation"],
            }
            reopened = _attempt_receipt(
                planned_security,
                planned_source,
                raw_result,
                runtime_trust_registry=runtime_trust_registry,
            )
            if reopened != source_receipt:
                raise IssuerSequentialCollectionError(
                    "source receipt authority or plan binding differs"
                )
            attempted = parse_aware(reopened["attempted_at"], "source attempted_at")
            completed = parse_aware(reopened["completed_at"], "source completed_at")
            if attempted < generated or completed > observed:
                raise IssuerSequentialCollectionError(
                    "source receipt falls outside the plan/run time boundary"
                )
            reopened_sources.append(reopened)

        started = min(
            parse_aware(item["attempted_at"], "source attempted_at")
            for item in reopened_sources
        )
        completed = max(
            parse_aware(item["completed_at"], "source completed_at")
            for item in reopened_sources
        )
        if (
            security_receipt.get("started_at") != started.isoformat()
            or security_receipt.get("completed_at") != completed.isoformat()
            or (previous_completed is not None and started < previous_completed)
        ):
            raise IssuerSequentialCollectionError(
                "security receipt violates the sequential time boundary"
            )
        non_blocking = sum(
            item["terminal_status"] in _NON_BLOCKING_SOURCE_STATUSES
            for item in reopened_sources
        )
        expected_seal = (
            "SEALED_ALL_SOURCE_ATTEMPTS_TERMINAL"
            if non_blocking == len(reopened_sources)
            else "SEALED_WITH_EXPLICIT_GAPS"
            if non_blocking
            else "SEALED_BLOCKED"
        )
        expected_counts = {
            "planned_source_count": len(reopened_sources),
            "terminal_source_count": len(reopened_sources),
            "collected_source_count": sum(
                item["terminal_status"] == "COLLECTED" for item in reopened_sources
            ),
            "explicit_gap_source_count": len(reopened_sources) - non_blocking,
            "artifact_count": sum(item["artifact_count"] for item in reopened_sources),
            "observation_count": sum(
                item["observation_count"] for item in reopened_sources
            ),
        }
        for field, value in expected_counts.items():
            _bounded_integer(
                security_receipt.get(field),
                f"security receipt {field}",
                minimum=0 if value == 0 else 1,
            )
        if security_receipt.get("seal_status") != expected_seal or any(
            security_receipt.get(field) != value
            for field, value in expected_counts.items()
        ):
            raise IssuerSequentialCollectionError(
                "security seal status or counts are inconsistent"
            )
        if security_receipt.get("previous_security_seal_sha256") != previous_seal:
            raise IssuerSequentialCollectionError("security seal chain is broken")
        if hash_json(
            {
                key: value
                for key, value in security_receipt.items()
                if key != "security_seal_sha256"
            }
        ) != security_receipt.get("security_seal_sha256"):
            raise IssuerSequentialCollectionError("security seal hash mismatch")
        previous_seal = security_receipt["security_seal_sha256"]
        previous_completed = completed
        total_sources += len(reopened_sources)
        total_artifacts += expected_counts["artifact_count"]
        total_observations += expected_counts["observation_count"]
        seals.append(expected_seal)

    expected_status = (
        "ALL_SECURITIES_TERMINAL_NO_SOURCE_GAPS"
        if all(status == "SEALED_ALL_SOURCE_ATTEMPTS_TERMINAL" for status in seals)
        else "ALL_SECURITIES_TERMINAL_BLOCKED"
        if any(status == "SEALED_BLOCKED" for status in seals)
        else "ALL_SECURITIES_TERMINAL_WITH_EXPLICIT_GAPS"
    )
    expected_top = {
        "status": expected_status,
        "security_count": len(security_receipts),
        "sealed_security_count": len(security_receipts),
        "planned_source_attempt_count": trusted_plan["total_source_attempts_planned"],
        "terminal_source_attempt_count": total_sources,
        "artifact_count": total_artifacts,
        "observation_count": total_observations,
    }
    if any(row.get(field) != value for field, value in expected_top.items()):
        raise IssuerSequentialCollectionError("collection run status or counts are inconsistent")
    return row


def validate_issuer_sequential_collection_run(
    run: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    project_root: Path | str,
    issuer_universe: Path | str | Mapping[str, Any],
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    trusted = _validated_run_document(
        run,
        plan,
        project_root=project_root,
        issuer_universe=issuer_universe,
        runtime_trust_registry=runtime_trust_registry,
    )
    return {
        "status": "PASS_RUN_RECEIPT_INTERNAL_CONSISTENCY_ONLY",
        "run_id": trusted["run_id"],
        "run_receipt_sha256": trusted["run_receipt_sha256"],
        "execution_evidence_class": trusted["execution_evidence_class"],
        "security_count": trusted["security_count"],
        "terminal_source_attempt_count": trusted["terminal_source_attempt_count"],
        "artifact_count": trusted["artifact_count"],
        "observation_count": trusted["observation_count"],
        "full_market_claim_allowed": False,
        "claim_boundaries": trusted["claim_boundaries"],
    }


def _write_exclusive_json(path: Path | str, payload: Mapping[str, Any], *, label: str) -> Path:
    target = Path(os.path.abspath(Path(path)))
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite an existing {label}")
    parent = require_real_directory(target.parent, field=f"{label} parent")
    target = parent / target.name
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(target, flags, 0o600)
        content = canonical_json_bytes(dict(payload))
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError(f"{label} write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return target


def write_issuer_sequential_collection_plan(
    path: Path | str,
    plan: Mapping[str, Any],
    *,
    project_root: Path | str,
    issuer_universe: Path | str | Mapping[str, Any],
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> Path:
    trusted = _validate_compiled_plan(
        plan,
        issuer_universe=issuer_universe,
        project_root=project_root,
        runtime_trust_registry=runtime_trust_registry,
    )
    return _write_exclusive_json(
        path,
        trusted,
        label="sequential collection plan",
    )


def write_issuer_sequential_collection_run(
    path: Path | str,
    run: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    project_root: Path | str,
    issuer_universe: Path | str | Mapping[str, Any],
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> Path:
    trusted = _validated_run_document(
        run,
        plan,
        project_root=project_root,
        issuer_universe=issuer_universe,
        runtime_trust_registry=runtime_trust_registry,
    )
    return _write_exclusive_json(
        path,
        trusted,
        label="sequential collection run receipt",
    )


__all__ = [
    "IssuerSequentialCollectionError",
    "PLAN_SCHEMA_VERSION",
    "compile_issuer_sequential_collection_plan",
    "execute_issuer_sequential_collection_plan",
    "validate_issuer_sequential_collection_policy",
    "validate_issuer_sequential_collection_plan",
    "validate_issuer_sequential_collection_plan_file",
    "validate_issuer_sequential_collection_run",
    "write_issuer_sequential_collection_plan",
    "write_issuer_sequential_collection_run",
]
