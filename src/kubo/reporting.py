from __future__ import annotations

import json
import re
from typing import Any
import unicodedata

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


def _claim_scope_errors(request: AnalysisRequest) -> list[str]:
    """Recheck claim/scope invariants at the report trust boundary.

    ``AnalysisRequest`` is frozen, but callers can still instantiate it
    directly instead of using ``from_dict``.  Reporting therefore cannot rely
    solely on constructor-time validation.
    """

    errors: list[str] = []
    codes = (
        tuple(request.security_codes)
        if isinstance(request.security_codes, (list, tuple))
        else ()
    )
    if request.claim_type == "SINGLE_SECURITY":
        if request.scope != "NAMED_SECURITIES":
            errors.append("SINGLE_SECURITY_CLAIM_REQUIRES_NAMED_SECURITIES_SCOPE")
        if len(codes) != 1:
            errors.append("SINGLE_SECURITY_CLAIM_REQUIRES_EXACTLY_ONE_SECURITY")
    elif request.claim_type == "COMPARISON":
        if request.scope != "NAMED_SECURITIES":
            errors.append("COMPARISON_CLAIM_REQUIRES_NAMED_SECURITIES_SCOPE")
        if len(codes) < 2:
            errors.append("COMPARISON_CLAIM_REQUIRES_AT_LEAST_TWO_SECURITIES")
    elif request.claim_type == "RESEARCH_RANK":
        if not isinstance(request.scope, str) or request.scope not in {
            "CANDIDATE_SET",
            "FULL_MARKET",
        }:
            errors.append("RESEARCH_RANK_CLAIM_REQUIRES_CANDIDATE_OR_FULL_MARKET_SCOPE")
        if codes:
            errors.append("RESEARCH_RANK_CLAIM_FORBIDS_SECURITY_CODES")
    return errors


def _full_market_claim_allowed(plan: dict[str, Any], network: dict[str, Any]) -> bool:
    """Derive the full-market boundary from evidence, not a caller flag."""

    contract = network.get("contract") if isinstance(network.get("contract"), dict) else {}
    if (
        network.get("status") != "PASS"
        or contract.get("scope") != "FULL_MARKET"
        or network.get("exact_universe_reconciled") is not True
    ):
        return False
    expected_count = contract.get("expected_universe_count")
    if not isinstance(expected_count, int) or isinstance(expected_count, bool) or expected_count <= 0:
        return False
    rows = [row for row in plan.get("ranked_candidates", []) if isinstance(row, dict)]
    codes = [str(row.get("security_code", "")) for row in rows]
    return bool(
        len(rows) == expected_count
        and len(set(codes)) == expected_count
        and all(code for code in codes)
        and all(
            isinstance(row.get("per_security_role_gaps"), dict)
            and not row["per_security_role_gaps"]
            for row in rows
        )
    )


def build_report(plan: dict[str, Any], request: AnalysisRequest) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("pipeline plan must be an object")
    network = plan.get("network_run") if isinstance(plan.get("network_run"), dict) else {}
    scope_errors: list[str] = []
    boundary_errors: list[str] = []
    request_snapshot = request.to_dict()
    try:
        reparsed_request = AnalysisRequest.from_dict(request_snapshot)
    except (TypeError, ValueError):
        boundary_errors.append("REQUEST_CONTRACT_INVALID")
        request_contract_valid = False
    else:
        request_contract_valid = reparsed_request == request
        if not request_contract_valid:
            boundary_errors.append("REQUEST_CONTRACT_INVALID")
    candidates = _filter_candidates(plan, request) if request_contract_valid else []
    scope_errors.extend(_claim_scope_errors(request))
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
    compatible_scopes = (
        compatible_packet_scopes.get(request.scope)
        if isinstance(request.scope, str)
        else None
    )
    if compatible_scopes is None:
        scope_errors.append("REQUEST_SCOPE_UNSUPPORTED")
    elif contract and packet_scope not in compatible_scopes:
        scope_errors.append(
            f"REQUEST_SCOPE_INCOMPATIBLE_WITH_PACKET:{request.scope}:{packet_scope}"
        )
    if (
        request.scope == "NAMED_SECURITIES"
        and packet_scope == "FULL_MARKET"
        and network.get("exact_universe_reconciled") is not True
    ):
        scope_errors.append(
            "NAMED_SECURITIES_OVER_FULL_MARKET_REQUIRES_EXACT_POINT_IN_TIME_UNIVERSE"
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
    runtime_trust_required = network.get("runtime_trust_required") is True
    runtime_trust_fields = (
        "runtime_trust_registry_id",
        "runtime_trust_registry_hash",
        "runtime_trust_key_id",
    )
    if any(plan.get(field) != network.get(field) for field in runtime_trust_fields):
        boundary_errors.append("RUNTIME_TRUST_PROVENANCE_DOES_NOT_MATCH_VALIDATION")
    if runtime_trust_required:
        if any(not network.get(field) for field in runtime_trust_fields):
            boundary_errors.append("RUNTIME_TRUST_PROVENANCE_REQUIRED")
    elif any(network.get(field) is not None for field in runtime_trust_fields):
        boundary_errors.append("UNNEEDED_RUNTIME_TRUST_PROVENANCE")
    if request_contract_valid and request.security_codes:
        resolved_codes = {str(row.get("security_code")) for row in candidates}
        missing_codes = sorted(set(request.security_codes) - resolved_codes)
        if missing_codes:
            scope_errors.append("REQUESTED_SECURITIES_NOT_RESOLVED:" + ",".join(missing_codes))
    contract_errors = [*boundary_errors, *scope_errors]
    full_market_claim_allowed = _full_market_claim_allowed(plan, network)
    exact_universe_reconciled = network.get("exact_universe_reconciled") is True
    status = "REQUEST_SCOPE_UNSATISFIED" if contract_errors else plan.get("status", "BLOCKED")
    report_reasons = list(plan.get("reasons", []))
    if (
        not contract_errors
        and packet_scope == "FULL_MARKET"
        and network.get("exact_universe_reconciled") is True
        and not full_market_claim_allowed
    ):
        if status == "RESEARCH_READY":
            status = "RESEARCH_PARTIAL"
        report_reasons.append("FULL_MARKET_PER_SECURITY_ROLE_COVERAGE_INCOMPLETE")
    if contract_errors:
        candidates = []
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "request": request_snapshot,
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
        "runtime_trust_required": runtime_trust_required,
        "runtime_trust_registry_id": network.get("runtime_trust_registry_id"),
        "runtime_trust_registry_hash": network.get("runtime_trust_registry_hash"),
        "runtime_trust_key_id": network.get("runtime_trust_key_id"),
        "exact_universe_reconciled": exact_universe_reconciled,
        "full_market_claim_allowed": full_market_claim_allowed,
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
            "sensitive_source_ids": network.get("sensitive_source_ids", []),
        },
        "reasons": list(dict.fromkeys([*report_reasons, *contract_errors])),
        "claim_boundaries": dict(plan.get("claim_boundaries", {})),
    }
    report["claim_boundaries"].update(
        {
            "research_score_is_probability": False,
            "missing_source_is_negative_evidence": False,
            "blocked_official_site_blocks_entire_market_run": False,
            "full_market_claim_allowed": full_market_claim_allowed,
        }
    )
    if request.detail_level == "deep":
        report["diagnostics"] = {
            "artifact_count": network.get("artifact_count"),
            "finding_count": network.get("finding_count"),
            "source_observation_count": network.get("source_observation_count"),
            "exact_universe_reconciled": network.get("exact_universe_reconciled"),
            "full_market_claim_allowed": full_market_claim_allowed,
            "contract": network.get("contract"),
            "structural_errors": network.get("structural_errors", []),
            "source_states": network.get("source_states", {}),
            "source_query_statuses": network.get("source_query_statuses", {}),
            "degraded_source_ids": network.get("degraded_source_ids", []),
            "runtime_trust_required": runtime_trust_required,
            "sensitive_source_ids": network.get("sensitive_source_ids", []),
            "runtime_trust_registry_id": network.get("runtime_trust_registry_id"),
            "runtime_trust_registry_hash": network.get("runtime_trust_registry_hash"),
            "runtime_trust_key_id": network.get("runtime_trust_key_id"),
        }
    return report


_MARKDOWN_META = re.compile(r"([\\`*_{}\[\]()<>#+\-.!|~])")


def _display_value(value: Any, *, language: str) -> str:
    if value is None:
        return "غير متاح" if language == "ar" else "not available"
    if isinstance(value, bool):
        if language == "ar":
            return "نعم" if value else "لا"
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _clean_markdown_dynamic(value: Any, *, language: str) -> str:
    text = unicodedata.normalize("NFC", _display_value(value, language=language))
    text = "".join(
        " "
        if unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        else character
        for character in text
    )
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        return text
    return "غير متاح" if language == "ar" else "not available"


def _markdown_plain(value: Any, *, language: str) -> str:
    """Render untrusted dynamic text without creating Markdown structure."""

    return _MARKDOWN_META.sub(
        r"\\\1", _clean_markdown_dynamic(value, language=language)
    )


def _markdown_code(value: Any, *, language: str) -> str:
    """Render an untrusted value in a CommonMark-safe variable code span."""

    text = _clean_markdown_dynamic(value, language=language)
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    return f"{fence} {text} {fence}"


def _markdown_code_list(value: Any, *, language: str, empty: str) -> str:
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
    elif value is None:
        items = []
    else:
        items = [value]
    if not items:
        return _markdown_code(empty, language=language)
    return ", ".join(_markdown_code(item, language=language) for item in items)


def _render_markdown_ar(report: dict[str, Any]) -> str:
    request = report.get("request", {})
    lines = [
        "# تقرير KU-BO البحثي",
        "",
        f"- رقم الطلب: {_markdown_code(request.get('request_id'), language='ar')}",
        f"- الحالة: {_markdown_code(report.get('status'), language='ar')}",
        f"- المنتج: {_markdown_code(request.get('product_id'), language='ar')}",
        f"- وقت القرار: {_markdown_code(report.get('decision_at'), language='ar')}",
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
                    "### "
                    f"{_markdown_plain(row.get('rank'), language='ar')}. "
                    f"{_markdown_code(row.get('ticker'), language='ar')} — "
                    f"{_markdown_code(row.get('security_code'), language='ar')}",
                    "",
                    f"- القرار البحثي: {_markdown_code(row.get('decision_status'), language='ar')}",
                    f"- Evidence Score: {_markdown_code(row.get('research_score'), language='ar')} — ليس Probability.",
                    f"- تغطية الأدلة: {_markdown_code(row.get('evidence_coverage'), language='ar')}",
                    f"- مجموعات المصادر المستقلة: {_markdown_code(row.get('independent_source_groups'), language='ar')}",
                    f"- تأكيد المحفز رسميًا: {_markdown_code(row.get('official_catalyst_confirmed'), language='ar')}",
                    f"- تعارض مستقل: {_markdown_code(row.get('source_conflict'), language='ar')}",
                    f"- أسباب الحذر: {_markdown_code_list(row.get('reason_codes'), language='ar', empty='لا يوجد')}",
                    "",
                ]
            )
    evidence = report.get("evidence_summary", {})
    lines.extend(
        [
            "## حالة الأدلة",
            "",
            f"- حالة الحزمة: {_markdown_code(evidence.get('network_status'), language='ar')}",
            f"- عدد مجموعات المصادر المستقلة: {_markdown_code(evidence.get('independent_sources'), language='ar')}",
            f"- فجوات التغطية: {_markdown_code_list(evidence.get('coverage_gaps'), language='ar', empty='لا يوجد')}",
            f"- تحذيرات: {_markdown_code_list(evidence.get('warnings'), language='ar', empty='لا يوجد')}",
            f"- المصادر المتدهورة: {_markdown_code_list(evidence.get('degraded_source_ids'), language='ar', empty='لا يوجد')}",
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
        f"- Request: {_markdown_code(request.get('request_id'), language='en')}",
        f"- Status: {_markdown_code(report.get('status'), language='en')}",
        f"- Product: {_markdown_code(request.get('product_id'), language='en')}",
        f"- Decision time: {_markdown_code(report.get('decision_at'), language='en')}",
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
                    "### "
                    f"{_markdown_plain(row.get('rank'), language='en')}. "
                    f"{_markdown_code(row.get('ticker'), language='en')} — "
                    f"{_markdown_code(row.get('security_code'), language='en')}",
                    "",
                    f"- Research decision: {_markdown_code(row.get('decision_status'), language='en')}",
                    f"- Evidence Score: {_markdown_code(row.get('research_score'), language='en')} — not a probability.",
                    f"- Evidence coverage: {_markdown_code(row.get('evidence_coverage'), language='en')}",
                    f"- Independent source groups: {_markdown_code(row.get('independent_source_groups'), language='en')}",
                    f"- Official catalyst confirmation: {_markdown_code(row.get('official_catalyst_confirmed'), language='en')}",
                    f"- Independent conflict: {_markdown_code(row.get('source_conflict'), language='en')}",
                    f"- Caution codes: {_markdown_code_list(row.get('reason_codes'), language='en', empty='none')}",
                    "",
                ]
            )
    evidence = report.get("evidence_summary", {})
    lines.extend(
        [
            "## Evidence status",
            "",
            f"- Packet status: {_markdown_code(evidence.get('network_status'), language='en')}",
            f"- Independent source groups: {_markdown_code(evidence.get('independent_sources'), language='en')}",
            f"- Coverage gaps: {_markdown_code_list(evidence.get('coverage_gaps'), language='en', empty='none')}",
            f"- Warnings: {_markdown_code_list(evidence.get('warnings'), language='en', empty='none')}",
            f"- Degraded sources: {_markdown_code_list(evidence.get('degraded_source_ids'), language='en', empty='none')}",
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
