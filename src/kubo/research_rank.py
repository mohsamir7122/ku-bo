from __future__ import annotations

from collections import defaultdict
import re
from typing import Any
import unicodedata

from .source_network import CLASS_RELIABILITY, NetworkRunValidation, ResearchFinding


def _signed(direction: str) -> float:
    return 1.0 if direction == "POSITIVE" else -1.0 if direction == "NEGATIVE" else 0.0


def _is_substantive(finding: ResearchFinding) -> bool:
    return (
        finding.direction != "NEUTRAL"
        and finding.strength > 0
        and finding.materiality > 0
        and finding.signal_kind != "ARCHIVE_CONTEXT"
    )


def _normalized_claim_tokens(value: str) -> frozenset[str]:
    text = unicodedata.normalize("NFKC", value).lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))
    return frozenset(re.findall(r"[\w\u0600-\u06ff]{3,}", text, flags=re.UNICODE))


def _near_duplicate(left: ResearchFinding, right: ResearchFinding) -> bool:
    if left.signal_kind != right.signal_kind or left.direction != right.direction:
        return False
    if left.event_key == right.event_key or left.origin_id == right.origin_id:
        return True
    if abs((left.available_at - right.available_at).total_seconds()) > 72 * 3600:
        return False
    left_tokens = _normalized_claim_tokens(left.claim_text)
    right_tokens = _normalized_claim_tokens(right.claim_text)
    if min(len(left_tokens), len(right_tokens)) < 6:
        return False
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    containment = overlap / min(len(left_tokens), len(right_tokens))
    jaccard = overlap / union if union else 0.0
    return containment >= 0.90 and jaccard >= 0.82


def _evidence_strength(finding: ResearchFinding, source_map: dict[str, Any]) -> float:
    source = source_map[finding.source_id]
    return CLASS_RELIABILITY[source.source_class] * finding.strength * finding.materiality


def _cluster_findings(findings: list[ResearchFinding]) -> list[list[ResearchFinding]]:
    clusters: list[list[ResearchFinding]] = []
    for finding in findings:
        for cluster in clusters:
            if any(_near_duplicate(finding, existing) for existing in cluster):
                cluster.append(finding)
                break
        else:
            clusters.append([finding])
    return clusters


def _deduplicate_origins(findings: list[ResearchFinding], source_map: dict[str, Any]) -> list[ResearchFinding]:
    """Keep one strongest representative per conservative evidence cluster.

    Five reposts of one disclosure or opinion remain one evidence cluster. The
    strongest source class wins only for scoring; all original rows remain in
    the validated packet for audit.  Near-duplicate text is collapsed only for
    the same signal, direction, security group, and a tight availability window.
    """

    return [
        max(cluster, key=lambda item: (_evidence_strength(item, source_map), item.finding_id))
        for cluster in _cluster_findings(findings)
    ]


def _per_security_role_coverage(
    findings: list[ResearchFinding], source_map: dict[str, Any]
) -> dict[str, int]:
    publisher_groups: dict[str, set[str]] = defaultdict(set)
    cluster_groups: dict[str, set[int]] = defaultdict(set)
    for cluster_index, cluster in enumerate(_cluster_findings(findings)):
        for item in cluster:
            source = source_map[item.source_id]
            for role in item.evidence_roles:
                publisher_groups[role].add(source.independence_group)
                cluster_groups[role].add(cluster_index)
    return {
        role: min(len(groups), len(cluster_groups[role]))
        for role, groups in publisher_groups.items()
        if groups and cluster_groups[role]
    }


def _has_conflict(findings: list[ResearchFinding], source_map: dict[str, Any]) -> tuple[bool, list[str]]:
    # A positive claim about one event and a negative claim about another event
    # are not contradictory evidence.  Conflict is meaningful only when
    # independent publishers disagree about the same typed event.
    by_event: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for item in findings:
        if item.strength * item.materiality >= 0.35 and item.direction != "NEUTRAL":
            group = source_map[item.source_id].independence_group
            by_event[(item.signal_kind, item.event_key)][item.direction].add(group)
    conflicts = sorted(
        f"{signal_kind}:{event_key}"
        for (signal_kind, event_key), directions in by_event.items()
        if any(
            positive != negative
            for positive in directions.get("POSITIVE", set())
            for negative in directions.get("NEGATIVE", set())
        )
    )
    return bool(conflicts), conflicts


def rank_research_candidates(
    validation: NetworkRunValidation,
    *,
    source_map: dict[str, Any],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Create a transparent source-mosaic rank, never a probability.

    The rank is allowed only after a structurally valid, quorum-complete run.
    It measures the direction and completeness of the captured evidence. It is
    not trained predictive skill and cannot produce a buy recommendation.
    """

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if validation.status != "PASS" or validation.contract is None:
        return []
    policy = validation.policy
    grouped: dict[str, list[ResearchFinding]] = defaultdict(list)
    for item in validation.findings:
        grouped[item.security_code].append(item)

    rows: list[dict[str, Any]] = []
    total_weight = sum(policy.signal_weights.values())
    for security_code, original_findings in grouped.items():
        substantive_findings = [item for item in original_findings if _is_substantive(item)]
        rankable_substantive_findings = [
            item
            for item in substantive_findings
            if source_map[item.source_id].source_class != "COMMUNITY"
            or policy.sentiment_contribution_cap > 0
        ]
        findings = _deduplicate_origins(rankable_substantive_findings, source_map)
        per_security_role_coverage = _per_security_role_coverage(
            rankable_substantive_findings, source_map
        )
        per_security_role_gaps = {
            role: (per_security_role_coverage.get(role, 0), minimum)
            for role, minimum in policy.required_role_quorum.items()
            if per_security_role_coverage.get(role, 0) < minimum
        }
        primary_catalyst_keys = {
            (item.event_key, item.direction)
            for item in substantive_findings
            if item.signal_kind == "CATALYST"
            and item.direction != "NEUTRAL"
            and bool(item.evidence_roles & validation.policy.confirmation_roles)
        }
        secondary_catalyst_keys = {
            (item.event_key, item.direction)
            for item in substantive_findings
            if item.signal_kind == "CATALYST"
            and item.direction != "NEUTRAL"
            and not bool(item.evidence_roles & validation.policy.confirmation_roles)
        }
        unconfirmed_catalyst_keys = secondary_catalyst_keys - primary_catalyst_keys
        signal_values: dict[str, list[tuple[float, bool]]] = defaultdict(list)
        signal_sources: dict[str, set[str]] = defaultdict(set)
        source_groups: set[str] = set()
        source_reliability_by_group: dict[str, float] = {}
        confirmed_catalyst = bool(primary_catalyst_keys)
        ticker = original_findings[0].ticker
        ticker_aliases = {item.ticker.upper() for item in original_findings}
        for item in findings:
            source = source_map[item.source_id]
            reliability = CLASS_RELIABILITY[source.source_class]
            source_groups.add(source.independence_group)
            source_reliability_by_group[source.independence_group] = max(
                reliability, source_reliability_by_group.get(source.independence_group, 0.0)
            )
            value = _signed(item.direction) * item.strength * item.materiality * reliability
            signal_values[item.signal_kind].append(
                (value, source.source_class == "COMMUNITY")
            )
            signal_sources[item.signal_kind].add(source.independence_group)

        present_weight = sum(policy.signal_weights.get(kind, 0.0) for kind in signal_values)
        evidence_coverage = present_weight / total_weight if total_weight else 0.0
        noncommunity_contributions: dict[str, float] = {}
        community_contributions: dict[str, float] = {}
        for kind, weight in policy.signal_weights.items():
            values = signal_values.get(kind, [])
            if not values or weight <= 0:
                noncommunity_contributions[kind] = 0.0
                community_contributions[kind] = 0.0
                continue
            denominator = len(values)
            noncommunity_contributions[kind] = (
                sum(value for value, is_community in values if not is_community)
                / denominator
                * weight
            )
            community_contributions[kind] = (
                sum(value for value, is_community in values if is_community)
                / denominator
                * weight
            )

        raw_community_magnitude = sum(abs(value) for value in community_contributions.values())
        if raw_community_magnitude <= 0 or policy.sentiment_contribution_cap <= 0:
            community_scale = 0.0
        else:
            community_scale = min(
                1.0,
                policy.sentiment_contribution_cap / raw_community_magnitude,
            )
        contributions = {
            kind: max(
                -1.0,
                min(
                    1.0,
                    noncommunity_contributions.get(kind, 0.0)
                    + community_contributions.get(kind, 0.0) * community_scale,
                ),
            )
            for kind in policy.signal_weights
        }
        community_contribution_total = sum(
            abs(value * community_scale) for value in community_contributions.values()
        )
        directional_total = max(-1.0, min(1.0, sum(contributions.values())))
        score = round(50.0 + 50.0 * directional_total, 4)

        conflict, conflict_kinds = _has_conflict(findings, source_map)
        positive_negative = [_signed(item.direction) for item in findings]
        agreement = abs(sum(positive_negative)) / len(positive_negative) if positive_negative else 0.0
        source_quality_factor = (
            sum(source_reliability_by_group.values()) / len(source_reliability_by_group)
            if source_reliability_by_group
            else 0.0
        )
        evidence_direction_alignment = evidence_coverage * agreement
        reasons: list[str] = [
            f"PER_SECURITY_ROLE_QUORUM:{role}:{actual}/{minimum}"
            for role, (actual, minimum) in sorted(per_security_role_gaps.items())
        ]

        if len(ticker_aliases) != 1:
            status = "ABSTAIN"
            reasons.append("TICKER_ALIAS_CONFLICT")
        elif len(source_groups) < policy.minimum_independent_sources:
            status = "ABSTAIN"
            reasons.append("INSUFFICIENT_SOURCE_DIVERSITY")
        elif evidence_coverage < policy.candidate_minimum_coverage:
            status = "ABSTAIN"
            reasons.append("INSUFFICIENT_SIGNAL_COVERAGE")
        else:
            if conflict:
                reasons.append("INDEPENDENT_SOURCE_CONFLICT:" + ",".join(conflict_kinds))
            if unconfirmed_catalyst_keys:
                reasons.append("DIRECTIONAL_CATALYST_NOT_PRIMARY_CONFIRMED")
            status = "WATCH" if reasons else "RESEARCH_CANDIDATE"

        if validation.exact_universe_reconciled:
            scope_label = "FULL_MARKET_RESEARCH_RANK"
        else:
            scope_label = "CANDIDATE_SET_RESEARCH_RANK"
            reasons.append("NOT_A_FULL_MARKET_BEST_CLAIM")

        rows.append(
            {
                "security_code": security_code,
                "ticker": ticker,
                "research_score": score,
                "score_kind": "SOURCE_MOSAIC_EVIDENCE_SCORE_NOT_PROBABILITY",
                "probability": None,
                "recommendation": None,
                "decision_status": status,
                "selected": False,
                "rank": None,
                "scope_label": scope_label,
                "evidence_coverage": round(evidence_coverage, 6),
                "source_quality_factor": round(source_quality_factor, 6),
                "evidence_direction_alignment": round(evidence_direction_alignment, 6),
                "independent_source_groups": len(source_groups),
                "minimum_independent_source_groups": policy.minimum_independent_sources,
                "per_security_role_coverage": dict(sorted(per_security_role_coverage.items())),
                "per_security_role_gaps": {
                    role: {"actual": actual, "required": minimum}
                    for role, (actual, minimum) in sorted(per_security_role_gaps.items())
                },
                "official_catalyst_confirmed": confirmed_catalyst,
                "all_directional_catalysts_primary_confirmed": not unconfirmed_catalyst_keys,
                "source_conflict": conflict,
                "community_contribution_total": round(community_contribution_total, 6),
                "community_contribution_cap": policy.sentiment_contribution_cap,
                "signal_contributions": {key: round(value, 6) for key, value in sorted(contributions.items())},
                "reason_codes": list(dict.fromkeys(reasons)),
            }
        )

    rows.sort(key=lambda row: (-row["research_score"], row["security_code"]))
    rank = 0
    selected = 0
    for row in rows:
        rank += 1
        row["rank"] = rank
        if row["decision_status"] == "RESEARCH_CANDIDATE" and selected < top_k:
            row["selected"] = True
            selected += 1
    return rows


__all__ = ["rank_research_candidates"]
