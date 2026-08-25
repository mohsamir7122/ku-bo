"""Semantic source fallback planning without network access."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from .foundation_io import load_strict_json_object
from .market_scope import validate_market_scope
from .source_network import NetworkSource, SourceNetworkCatalog
from .strict import https_url, parse_aware, strict_bool


POLICY_PATH = Path("config/source_fallback_policy.json")
CAPABILITY_IDS = frozenset(
    {
        "security_identity",
        "market_calendar",
        "completed_eod_history",
        "corporate_actions",
        "official_disclosures",
        "fundamentals",
        "news_context",
        "community_attention",
        "execution_context",
    }
)
CAPABILITY_ROLES = {
    "security_identity": frozenset({"IDENTITY_REFERENCE"}),
    "market_calendar": frozenset({"MARKET_DISCOVERY", "PRICE_HISTORY", "EXECUTION_TAPE"}),
    "completed_eod_history": frozenset({"PRICE_HISTORY"}),
    "corporate_actions": frozenset({"OFFICIAL_EVENT"}),
    "official_disclosures": frozenset({"OFFICIAL_EVENT"}),
    "fundamentals": frozenset({"FUNDAMENTAL_ARCHIVE"}),
    "news_context": frozenset({"NEWS_ARCHIVE"}),
    "community_attention": frozenset({"COMMUNITY_SENTIMENT"}),
    "execution_context": frozenset({"EXECUTION_TAPE"}),
}
TRANSPORT_STATUSES = frozenset(
    {
        "SUCCESS",
        "HTTP_ERROR",
        "TIMEOUT",
        "ACCESS_BLOCKED",
        "ENTITLEMENT_REQUIRED",
        "NETWORK_ERROR",
    }
)
SEMANTIC_STATUSES = frozenset(
    {
        "ROWS_PRESENT",
        "ZERO_ROWS",
        "VERIFIED_ZERO_RESULT",
        "PARSE_FAILED",
        "ACCESS_BLOCKED",
        "NOT_EVALUATED",
    }
)
SEMANTIC_RULES = {
    "transport_success_proves_semantic_success": False,
    "zero_rows_requires_verified_zero_result": True,
    "blocked_source_ends_capability_attempt": False,
    "access_controls_may_be_bypassed": False,
    "fallback_changes_claim_grade": False,
}
ORIGINAL_SOURCE_POLICY = {
    "secondary_and_community_leads_require_original_check": True,
    "search_result_is_evidence": False,
    "unregistered_origin_requires_source_admission": True,
}
POLICY_BOUNDARIES = {
    "planner_performs_network_access": False,
    "fallback_result_satisfies_product_quorum": False,
    "source_certainty_is_analytical_certainty": False,
    "fallback_result_is_probability": False,
    "fallback_result_is_recommendation": False,
    "automatic_source_promotion_allowed": False,
}
REPORT_BOUNDARIES = {
    "network_access_performed": False,
    "product_quorum_satisfied": False,
    "probability_computed": False,
    "recommendation_generated": False,
    "access_control_bypassed": False,
    "source_promoted_automatically": False,
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SourceFallbackError(ValueError):
    """Raised when fallback policy or observations violate the contract."""


def _exact(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != keys:
        raise SourceFallbackError(f"{field} has unknown or missing fields")
    return value


def _policy(project_root: Path) -> tuple[dict[str, Any], bytes]:
    try:
        return load_strict_json_object(
            project_root / POLICY_PATH,
            field="source fallback policy",
            max_bytes=256 * 1024,
        )
    except ValueError as exc:
        raise SourceFallbackError(str(exc)) from exc


def _validated_policy(
    project_root: Path,
) -> tuple[dict[str, Any], bytes, SourceNetworkCatalog, dict[str, Mapping[str, Any]]]:
    validate_market_scope(project_root)
    payload, content = _policy(project_root)
    _exact(
        payload,
        frozenset(
            {
                "schema_version",
                "policy_id",
                "status",
                "market_scope_id",
                "capabilities",
                "semantic_rules",
                "original_source_verification",
                "claim_boundaries",
            }
        ),
        "source fallback policy",
    )
    if payload.get("schema_version") != "1.0":
        raise SourceFallbackError("source fallback schema_version must be 1.0")
    if payload.get("policy_id") != "ku-bo-semantic-source-fallback-v1":
        raise SourceFallbackError("source fallback policy_id changed")
    if payload.get("status") != "CONTRACT_ONLY_NO_NETWORK":
        raise SourceFallbackError("source fallback status must remain non-network")
    if payload.get("market_scope_id") != "ku-bo-kuwait-only-v1":
        raise SourceFallbackError("source fallback escaped the locked market scope")
    if payload.get("semantic_rules") != SEMANTIC_RULES:
        raise SourceFallbackError("source fallback semantic rules were weakened")
    if payload.get("original_source_verification") != ORIGINAL_SOURCE_POLICY:
        raise SourceFallbackError("original-source verification policy changed")
    if payload.get("claim_boundaries") != POLICY_BOUNDARIES:
        raise SourceFallbackError("source fallback claim boundaries changed")

    catalog = SourceNetworkCatalog(project_root / "config")
    rows = payload.get("capabilities")
    if not isinstance(rows, list) or len(rows) != len(CAPABILITY_IDS):
        raise SourceFallbackError("source fallback capabilities must be complete")
    capabilities: dict[str, Mapping[str, Any]] = {}
    used_sources: set[str] = set()
    for index, raw in enumerate(rows):
        row = _exact(
            raw,
            frozenset(
                {
                    "capability_id",
                    "source_chain",
                    "verified_zero_result_can_satisfy",
                }
            ),
            f"capabilities[{index}]",
        )
        capability_id = row.get("capability_id")
        if capability_id not in CAPABILITY_IDS or capability_id in capabilities:
            raise SourceFallbackError("source fallback capability IDs must be unique and complete")
        chain = row.get("source_chain")
        if not isinstance(chain, list) or len(chain) < 2 or len(chain) != len(set(chain)):
            raise SourceFallbackError(f"{capability_id}.source_chain must contain unique fallbacks")
        for source_id in chain:
            if not isinstance(source_id, str) or source_id not in catalog.sources:
                raise SourceFallbackError(f"{capability_id} references an unknown source")
            source = catalog.sources[source_id]
            if source.source_class in {"SEARCH_ROUTER", "STORAGE", "WEB_ARCHIVE"}:
                raise SourceFallbackError(
                    f"{capability_id} assigns factual fallback work to {source.source_class}"
                )
            if not source.roles & CAPABILITY_ROLES[str(capability_id)]:
                raise SourceFallbackError(
                    f"{source_id} lacks a role admitted for {capability_id}"
                )
            used_sources.add(source_id)
        strict_bool(
            row.get("verified_zero_result_can_satisfy"),
            f"{capability_id}.verified_zero_result_can_satisfy",
        )
        capabilities[str(capability_id)] = row
    if frozenset(capabilities) != CAPABILITY_IDS:
        raise SourceFallbackError("source fallback capability set is incomplete")
    return payload, content, catalog, capabilities


def validate_source_fallback_policy(project_root: Path | str) -> dict[str, Any]:
    """Validate fallback chains against the canonical source catalog."""

    root = Path(project_root).resolve()
    payload, content, catalog, capabilities = _validated_policy(root)
    used = {
        source_id
        for row in capabilities.values()
        for source_id in row["source_chain"]
    }
    gated = sorted(
        source_id
        for source_id in used
        if catalog.sources[source_id].requires_entitlement
        or catalog.sources[source_id].requires_runtime_domain_registry
        or not catalog.sources[source_id].enabled_by_default
    )
    return {
        "schema_version": "1.0",
        "status": "PASS_CONTRACT_ONLY_NO_NETWORK",
        "policy_id": payload["policy_id"],
        "market_scope_id": payload["market_scope_id"],
        "capability_count": len(capabilities),
        "referenced_source_count": len(used),
        "runtime_or_entitlement_gated_sources": gated,
        "policy_sha256": hashlib.sha256(content).hexdigest(),
        "claim_boundaries": REPORT_BOUNDARIES,
    }


def _request(value: Path | str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        payload, _ = load_strict_json_object(
            Path(value),
            field="source fallback request",
            max_bytes=512 * 1024,
        )
    except ValueError as exc:
        raise SourceFallbackError(str(exc)) from exc
    return payload


def _observation_disposition(row: Mapping[str, Any]) -> str:
    semantic = row["semantic_status"]
    if semantic == "ROWS_PRESENT":
        return "AVAILABLE_ROWS"
    if semantic == "VERIFIED_ZERO_RESULT":
        return "VERIFIED_ZERO_RESULT"
    if semantic == "ZERO_ROWS":
        return "UNVERIFIED_ZERO_RESULT"
    if semantic == "PARSE_FAILED":
        return "SEMANTIC_FAILURE"
    return "SOURCE_ACCESS_TERMINAL"


def _validate_observation(
    raw: Any,
    *,
    index: int,
    decision_at: Any,
    chain: tuple[str, ...],
) -> dict[str, Any]:
    row = _exact(
        raw,
        frozenset(
            {
                "source_id",
                "attempted_at",
                "transport_status",
                "semantic_status",
                "qualified_row_count",
                "zero_result_verified",
                "cited_original_urls",
            }
        ),
        f"observations[{index}]",
    )
    source_id = row.get("source_id")
    if not isinstance(source_id, str) or source_id not in chain:
        raise SourceFallbackError(f"observations[{index}].source_id is outside the capability chain")
    attempted_at = parse_aware(row.get("attempted_at"), f"observations[{index}].attempted_at")
    if attempted_at > decision_at:
        raise SourceFallbackError("source observation occurs after decision_at")
    transport = row.get("transport_status")
    semantic = row.get("semantic_status")
    if transport not in TRANSPORT_STATUSES or semantic not in SEMANTIC_STATUSES:
        raise SourceFallbackError("source observation contains an unsupported status")
    count = row.get("qualified_row_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise SourceFallbackError("qualified_row_count must be a non-negative integer")
    verified_zero = strict_bool(
        row.get("zero_result_verified"),
        f"observations[{index}].zero_result_verified",
    )
    if transport == "SUCCESS":
        if semantic == "ROWS_PRESENT" and (count <= 0 or verified_zero):
            raise SourceFallbackError("ROWS_PRESENT requires positive qualified rows")
        if semantic == "VERIFIED_ZERO_RESULT" and (count != 0 or not verified_zero):
            raise SourceFallbackError("VERIFIED_ZERO_RESULT requires an explicit zero receipt")
        if semantic == "ZERO_ROWS" and (count != 0 or verified_zero):
            raise SourceFallbackError("ZERO_ROWS must remain unverified")
        if semantic in {"ACCESS_BLOCKED", "NOT_EVALUATED"}:
            raise SourceFallbackError("successful transport requires a semantic evaluation")
        if semantic == "PARSE_FAILED" and (count != 0 or verified_zero):
            raise SourceFallbackError("PARSE_FAILED cannot declare qualified rows")
    else:
        if semantic not in {"ACCESS_BLOCKED", "NOT_EVALUATED"} or count != 0 or verified_zero:
            raise SourceFallbackError("failed transport cannot claim semantic data")
    urls = row.get("cited_original_urls")
    if not isinstance(urls, list) or len(urls) > 32 or len(urls) != len(set(urls)):
        raise SourceFallbackError("cited_original_urls must be a bounded unique array")
    safe_urls = [
        https_url(item, f"observations[{index}].cited_original_urls")
        for item in urls
    ]
    return {
        "source_id": source_id,
        "attempted_at": attempted_at.isoformat(),
        "transport_status": transport,
        "semantic_status": semantic,
        "qualified_row_count": count,
        "zero_result_verified": verified_zero,
        "cited_original_urls": safe_urls,
        "disposition": _observation_disposition(row),
    }


def _source_receipt(source: NetworkSource, catalog: SourceNetworkCatalog) -> dict[str, Any]:
    capability = catalog.capabilities[source.source_id]
    return {
        "source_id": source.source_id,
        "source_class": source.source_class,
        "enabled_by_default": source.enabled_by_default,
        "requires_entitlement": source.requires_entitlement,
        "requires_runtime_domain_registry": source.requires_runtime_domain_registry,
        "implementation_status": capability.status,
        "live_operational": capability.live_operational,
    }


def _matching_sources(url: str, catalog: SourceNetworkCatalog) -> list[str]:
    host = (urlsplit(url).hostname or "").casefold()
    matches: list[str] = []
    for source in catalog.sources.values():
        if source.source_class in {"SEARCH_ROUTER", "STORAGE"}:
            continue
        if any(host == domain or host.endswith("." + domain) for domain in source.domains):
            matches.append(source.source_id)
    return sorted(matches)


def plan_source_fallback(
    project_root: Path | str,
    request: Path | str | Mapping[str, Any],
) -> dict[str, Any]:
    """Plan the next authorized source attempt from bounded observation receipts."""

    root = Path(project_root).resolve()
    _, policy_content, catalog, capabilities = _validated_policy(root)
    payload = _request(request)
    _exact(
        payload,
        frozenset({"schema_version", "request_id", "capability_id", "decision_at", "observations"}),
        "source fallback request",
    )
    if payload.get("schema_version") != "1.0":
        raise SourceFallbackError("source fallback request schema_version must be 1.0")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not _ID_RE.fullmatch(request_id):
        raise SourceFallbackError("request_id is invalid")
    capability_id = payload.get("capability_id")
    if capability_id not in capabilities:
        raise SourceFallbackError("capability_id is not registered")
    decision_at = parse_aware(payload.get("decision_at"), "decision_at")
    chain = tuple(str(item) for item in capabilities[str(capability_id)]["source_chain"])
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list) or len(raw_observations) > 32:
        raise SourceFallbackError("observations must be a bounded array")
    observations = [
        _validate_observation(
            raw,
            index=index,
            decision_at=decision_at,
            chain=chain,
        )
        for index, raw in enumerate(raw_observations)
    ]
    observed_ids = [row["source_id"] for row in observations]
    if len(observed_ids) != len(set(observed_ids)):
        raise SourceFallbackError("each source may have only one terminal observation")
    if observed_ids != list(chain[: len(observed_ids)]):
        raise SourceFallbackError(
            "source observations must be an ordered prefix of the fallback chain"
        )
    by_source = {row["source_id"]: row for row in observations}
    attempts = [by_source[source_id] for source_id in chain if source_id in by_source]

    selected_id: str | None = None
    selected_kind: str | None = None
    verified_zero_can_satisfy = bool(
        capabilities[str(capability_id)]["verified_zero_result_can_satisfy"]
    )
    for source_id in chain:
        row = by_source.get(source_id)
        if row is None:
            continue
        if row["semantic_status"] == "ROWS_PRESENT":
            selected_id = source_id
            selected_kind = "ROWS_PRESENT"
            break
        if row["semantic_status"] == "VERIFIED_ZERO_RESULT" and verified_zero_can_satisfy:
            selected_id = source_id
            selected_kind = "VERIFIED_ZERO_RESULT"
            break

    next_id = None if selected_id else next((item for item in chain if item not in by_source), None)
    if selected_kind == "ROWS_PRESENT":
        status = "CAPABILITY_EVIDENCE_AVAILABLE"
    elif selected_kind == "VERIFIED_ZERO_RESULT":
        status = "CAPABILITY_VERIFIED_ZERO_RESULT"
    elif next_id is not None:
        status = "CAPABILITY_FALLBACK_REQUIRED"
    else:
        status = "CAPABILITY_EXHAUSTED_ABSTAIN"

    verification_queue: list[dict[str, Any]] = []
    queued_urls: set[str] = set()
    for row in attempts:
        for url in row["cited_original_urls"]:
            if url in queued_urls:
                continue
            queued_urls.add(url)
            matches = _matching_sources(url, catalog)
            verification_queue.append(
                {
                    "discovered_by_source_id": row["source_id"],
                    "original_url": url,
                    "matched_registered_source_ids": matches,
                    "status": (
                        "REGISTERED_ORIGINAL_REQUIRES_VERIFICATION"
                        if matches
                        else "UNREGISTERED_ORIGINAL_REQUIRES_ADMISSION"
                    ),
                }
            )

    selected_source = (
        _source_receipt(catalog.sources[selected_id], catalog) if selected_id else None
    )
    if selected_kind == "VERIFIED_ZERO_RESULT":
        source_certainty = "VERIFIED_ZERO_RECEIPT"
    elif selected_id and catalog.sources[selected_id].source_class in {
        "PRIMARY_OFFICIAL",
        "PRIMARY_ISSUER",
        "LICENSED",
    }:
        source_certainty = "DIRECT_PRIMARY_RECEIPT"
    elif selected_id:
        source_certainty = "NON_PRIMARY_RECEIPT_PENDING_CONFIRMATION"
    else:
        source_certainty = "NO_USABLE_RECEIPT"

    return {
        "schema_version": "1.0",
        "status": status,
        "request_id": request_id,
        "capability_id": capability_id,
        "decision_at": decision_at.isoformat(),
        "policy_sha256": hashlib.sha256(policy_content).hexdigest(),
        "attempts": attempts,
        "selected_source": selected_source,
        "next_source": (
            _source_receipt(catalog.sources[next_id], catalog) if next_id else None
        ),
        "original_source_verification_queue": verification_queue,
        "source_certainty_state": source_certainty,
        "analytical_certainty_state": "NOT_COMPUTED",
        "claim_boundaries": REPORT_BOUNDARIES,
    }


__all__ = [
    "CAPABILITY_IDS",
    "CAPABILITY_ROLES",
    "SourceFallbackError",
    "plan_source_fallback",
    "validate_source_fallback_policy",
]
