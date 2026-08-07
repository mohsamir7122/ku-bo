from __future__ import annotations

import json
from typing import Any

from .request_contracts import AnalysisRequest, is_forbidden_research_output_field


DEEP_RESEARCH_CANDIDATE_FIELDS = frozenset(
    {
        "rank",
        "ticker",
        "security_code",
        "decision_status",
        "research_score",
        "score_kind",
        "reason_codes",
        "selected",
        "scope_label",
        "evidence_coverage",
        "independent_source_groups",
        "minimum_independent_source_groups",
        "official_catalyst_confirmed",
        "all_directional_catalysts_primary_confirmed",
        "source_conflict",
        "source_quality_factor",
        "evidence_direction_alignment",
        "per_security_role_coverage",
        "per_security_role_gaps",
        "signal_contributions",
        "community_contribution_total",
        "community_contribution_cap",
    }
)

BRIEF_RESEARCH_CANDIDATE_FIELDS = frozenset(
    {
        "rank",
        "ticker",
        "security_code",
        "decision_status",
        "research_score",
        "score_kind",
        "reason_codes",
    }
)

STANDARD_RESEARCH_CANDIDATE_FIELDS = BRIEF_RESEARCH_CANDIDATE_FIELDS | frozenset(
    {
        "selected",
        "scope_label",
        "evidence_coverage",
        "independent_source_groups",
        "official_catalyst_confirmed",
        "source_conflict",
        "source_quality_factor",
        "evidence_direction_alignment",
    }
)


def _sanitize_research_output(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_research_output(item)
            for key, item in value.items()
            if not is_forbidden_research_output_field(key)
        }
    if isinstance(value, list):
        return [_sanitize_research_output(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_research_output(item) for item in value)
    return value


def _filter_candidates(plan: dict[str, Any], request: AnalysisRequest) -> list[dict[str, Any]]:
    rows = [dict(row) for row in plan.get("ranked_candidates", []) if isinstance(row, dict)]
    if request.mode == "research_network":
        rows = [
            _sanitize_research_output(
                {
                    key: value
                    for key, value in row.items()
                    if key in DEEP_RESEARCH_CANDIDATE_FIELDS
                }
            )
            for row in rows
        ]
    if request.security_codes:
        allowed = set(request.security_codes)
        rows = [row for row in rows if str(row.get("security_code")) in allowed]
    rows = rows[: request.top_k]
    detail_fields = {
        "brief": BRIEF_RESEARCH_CANDIDATE_FIELDS,
        "standard": STANDARD_RESEARCH_CANDIDATE_FIELDS,
        "deep": DEEP_RESEARCH_CANDIDATE_FIELDS,
    }[request.detail_level]
    if request.requested_fields:
        requested = frozenset(request.requested_fields)
        unsupported = sorted(requested - DEEP_RESEARCH_CANDIDATE_FIELDS)
        unavailable = sorted(requested - detail_fields)
        if unsupported:
            raise ValueError("unsupported requested_fields: " + ",".join(unsupported))
        if unavailable:
            raise ValueError(
                f"requested_fields exceed {request.detail_level} detail level: "
                + ",".join(unavailable)
            )
        # Identity, decision status, score semantics, and reason codes remain
        # mandatory so a custom projection cannot remove its audit context.
        allowed_fields = BRIEF_RESEARCH_CANDIDATE_FIELDS | requested
    else:
        allowed_fields = detail_fields
    return [{key: value for key, value in row.items() if key in allowed_fields} for row in rows]


def build_report(plan: dict[str, Any], request: AnalysisRequest) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("pipeline plan must be an object")
    network = plan.get("network_run") if isinstance(plan.get("network_run"), dict) else {}
    candidates = _filter_candidates(plan, request)
    scope_errors: list[str] = []
    boundary_errors: list[str] = []
    if plan.get("mode") != request.mode:
        boundary_errors.append("REQUEST_MODE_DOES_NOT_MATCH_PIPELINE_PLAN")
    plan_product = plan.get("product") if isinstance(plan.get("product"), dict) else {}
    if plan_product.get("product_id") != request.product_id:
        boundary_errors.append("REQUEST_PRODUCT_DOES_NOT_MATCH_PIPELINE_PLAN")
    contract = network.get("contract") if isinstance(network.get("contract"), dict) else {}
    packet_scope = contract.get("scope")
    compatible_packet_scopes = {
        "CANDIDATE_SET": {"CANDIDATE_SET", "FULL_MARKET"},
        # Named-security research must have been collected for that named scope
        # (or as an exact full-market packet); a discovery candidate scan is not
        # a substitute for security-directed collection.
        "NAMED_SECURITIES": {"NAMED_SECURITIES", "FULL_MARKET"},
        "FULL_MARKET": {"FULL_MARKET"},
    }
    if contract and packet_scope not in compatible_packet_scopes[request.scope]:
        scope_errors.append(
            f"REQUEST_SCOPE_INCOMPATIBLE_WITH_PACKET:{request.scope}:{packet_scope}"
        )
    if request.scope == "FULL_MARKET" and (
        packet_scope != "FULL_MARKET" or network.get("exact_universe_reconciled") is not True
    ):
        scope_errors.append("FULL_MARKET_REQUEST_REQUIRES_EXACT_POINT_IN_TIME_UNIVERSE")
    validated_packet_hash = network.get("evidence_packet_hash")
    planned_packet_hash = plan.get("evidence_packet_hash")
    if network.get("status") in {"PASS", "PARTIAL"} and (
        not isinstance(validated_packet_hash, str)
        or planned_packet_hash != validated_packet_hash
    ):
        boundary_errors.append("EVIDENCE_PACKET_HASH_DOES_NOT_MATCH_VALIDATION")
    if request.security_codes:
        resolved_codes = {str(row.get("security_code")) for row in candidates}
        missing_codes = sorted(set(request.security_codes) - resolved_codes)
        if missing_codes:
            scope_errors.append("REQUESTED_SECURITIES_NOT_RESOLVED:" + ",".join(missing_codes))
    contract_errors = [*boundary_errors, *scope_errors]
    status = "REQUEST_SCOPE_UNSATISFIED" if contract_errors else plan.get("status", "BLOCKED")
    if contract_errors:
        candidates = []
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "request": request.to_dict(),
        "status": status,
        "mode": plan.get("mode", request.mode),
        "product": (
            _sanitize_research_output(plan.get("product"))
            if request.mode == "research_network"
            else plan.get("product")
        ),
        "scope": network.get("contract", {}).get("scope") if isinstance(network.get("contract"), dict) else None,
        "decision_at": network.get("contract", {}).get("decision_at") if isinstance(network.get("contract"), dict) else None,
        "evidence_packet_hash": (
            validated_packet_hash
            if validated_packet_hash == planned_packet_hash
            else None
        ),
        "candidates": candidates,
        "evidence_summary": {
            "network_status": network.get("status"),
            "independent_sources": network.get("independent_sources"),
            "role_coverage": network.get("role_coverage", {}),
            "official_confirmation_available": network.get("official_confirmation_available"),
            "coverage_gaps": network.get("coverage_gaps", []),
            "warnings": network.get("warnings", []),
            "source_states": network.get("source_states", {}),
            "source_query_statuses": network.get("source_query_statuses", {}),
            "degraded_source_ids": network.get("degraded_source_ids", []),
        },
        "reasons": list(dict.fromkeys([*plan.get("reasons", []), *contract_errors])),
        "claim_boundaries": dict(plan.get("claim_boundaries", {})),
    }
    report["claim_boundaries"].update(
        {
            "research_score_is_probability": False,
            "missing_source_is_negative_evidence": False,
            "blocked_official_site_blocks_entire_market_run": False,
        }
    )
    if request.detail_level == "deep":
        report["diagnostics"] = {
            "artifact_count": network.get("artifact_count"),
            "finding_count": network.get("finding_count"),
            "source_observation_count": network.get("source_observation_count"),
            "exact_universe_reconciled": network.get("exact_universe_reconciled"),
            "contract": network.get("contract"),
            "structural_errors": network.get("structural_errors", []),
            "source_states": network.get("source_states", {}),
            "source_query_statuses": network.get("source_query_statuses", {}),
            "degraded_source_ids": network.get("degraded_source_ids", []),
        }
    return report


def _value(value: Any) -> str:
    if value is None:
        return "غير متاح"
    if isinstance(value, bool):
        return "نعم" if value else "لا"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _value_en(value: Any) -> str:
    if value is None:
        return "not available"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _render_markdown_ar(report: dict[str, Any]) -> str:
    request = report.get("request", {})
    lines = [
        "# تقرير KU-BO البحثي",
        "",
        f"- رقم الطلب: `{_value(request.get('request_id'))}`",
        f"- الحالة: `{_value(report.get('status'))}`",
        f"- المنتج: `{_value(request.get('product_id'))}`",
        f"- وقت القرار: `{_value(report.get('decision_at'))}`",
        "",
        "## الخلاصة",
        "",
    ]
    candidates = report.get("candidates", [])
    if not candidates:
        lines.append("لا توجد نتائج قابلة للترتيب ضمن الأدلة والقيود الحالية.")
    else:
        for row in candidates:
            lines.extend(
                [
                    f"### {_value(row.get('rank'))}. {_value(row.get('ticker'))} — {_value(row.get('security_code'))}",
                    "",
                    f"- القرار البحثي: `{_value(row.get('decision_status'))}`",
                    f"- Evidence Score: `{_value(row.get('research_score'))}` — ليس Probability.",
                    f"- تغطية الأدلة: `{_value(row.get('evidence_coverage'))}`",
                    f"- مجموعات المصادر المستقلة: `{_value(row.get('independent_source_groups'))}`",
                    f"- تأكيد المحفز رسميًا: `{_value(row.get('official_catalyst_confirmed'))}`",
                    f"- تعارض مستقل: `{_value(row.get('source_conflict'))}`",
                    f"- أسباب الحذر: `{', '.join(row.get('reason_codes', [])) or 'لا يوجد'}`",
                    "",
                ]
            )
    evidence = report.get("evidence_summary", {})
    lines.extend(
        [
            "## حالة الأدلة",
            "",
            f"- حالة الحزمة: `{_value(evidence.get('network_status'))}`",
            f"- عدد مجموعات المصادر المستقلة: `{_value(evidence.get('independent_sources'))}`",
            f"- فجوات التغطية: `{', '.join(evidence.get('coverage_gaps', [])) or 'لا يوجد'}`",
            f"- تحذيرات: `{', '.join(evidence.get('warnings', [])) or 'لا يوجد'}`",
            f"- المصادر المتدهورة: `{', '.join(evidence.get('degraded_source_ids', [])) or 'لا يوجد'}`",
            "",
            "## حدود الادعاء",
            "",
            "هذا التقرير Research Decision-Support فقط. تعطل مصدر رسمي يخفض الثقة والتأكيد الرسمي، لكنه لا يوقف السوق كله. Evidence Score ليس Probability، ولا يمثل أمر شراء أو سعر دخول أو قدرة تنفيذ فعلية.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_markdown_en(report: dict[str, Any]) -> str:
    request = report.get("request", {})
    lines = [
        "# KU-BO research report",
        "",
        f"- Request: `{_value_en(request.get('request_id'))}`",
        f"- Status: `{_value_en(report.get('status'))}`",
        f"- Product: `{_value_en(request.get('product_id'))}`",
        f"- Decision time: `{_value_en(report.get('decision_at'))}`",
        "",
        "## Result",
        "",
    ]
    candidates = report.get("candidates", [])
    if not candidates:
        lines.append("No candidate can be ranked within the current evidence and claim boundaries.")
    else:
        for row in candidates:
            lines.extend(
                [
                    f"### {_value_en(row.get('rank'))}. {_value_en(row.get('ticker'))} — {_value_en(row.get('security_code'))}",
                    "",
                    f"- Research decision: `{_value_en(row.get('decision_status'))}`",
                    f"- Evidence Score: `{_value_en(row.get('research_score'))}` — not a probability.",
                    f"- Evidence coverage: `{_value_en(row.get('evidence_coverage'))}`",
                    f"- Independent source groups: `{_value_en(row.get('independent_source_groups'))}`",
                    f"- Official catalyst confirmation: `{_value_en(row.get('official_catalyst_confirmed'))}`",
                    f"- Independent conflict: `{_value_en(row.get('source_conflict'))}`",
                    f"- Caution codes: `{', '.join(row.get('reason_codes', [])) or 'none'}`",
                    "",
                ]
            )
    evidence = report.get("evidence_summary", {})
    lines.extend(
        [
            "## Evidence status",
            "",
            f"- Packet status: `{_value_en(evidence.get('network_status'))}`",
            f"- Independent source groups: `{_value_en(evidence.get('independent_sources'))}`",
            f"- Coverage gaps: `{', '.join(evidence.get('coverage_gaps', [])) or 'none'}`",
            f"- Warnings: `{', '.join(evidence.get('warnings', [])) or 'none'}`",
            f"- Degraded sources: `{', '.join(evidence.get('degraded_source_ids', [])) or 'none'}`",
            "",
            "## Claim boundary",
            "",
            "This is research decision-support. A blocked official source lowers official confirmation but does not stop the entire market run. An Evidence Score is not a probability, buy order, entry price, or proof of execution.",
            "",
        ]
    )
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    language = str(report.get("request", {}).get("language", "ar"))
    return _render_markdown_en(report) if language == "en" else _render_markdown_ar(report)


def render_report(report: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    if output_format == "markdown":
        return render_markdown(report)
    raise ValueError(f"unsupported output format: {output_format}")


__all__ = ["build_report", "render_markdown", "render_report"]
