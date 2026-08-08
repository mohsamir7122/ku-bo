from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog import ProductSpec
from .execution import ExecutionAssessment
from .modelcard import ModelCardResult
from .strict import finite_number


@dataclass(frozen=True)
class Decision:
    security_code: str
    product_id: str
    status: str
    profile_classes: tuple[str, ...]
    score: float | None
    probability: float | None
    expected_net_edge: float | None
    reason_codes: tuple[str, ...]


def classify_profiles(features: dict[str, Any]) -> tuple[str, ...]:
    profiles: list[str] = []
    try:
        volatility = finite_number(features.get("volatility_percentile"), "volatility_percentile", minimum=0, maximum=1)
    except ValueError:
        volatility = None
    liquidity = str(features.get("liquidity_bucket", "UNKNOWN")).upper()
    discontinuity = features.get("discontinuity_flag") is True
    if (volatility is not None and volatility >= 0.75) or liquidity in {"THIN", "MICRO"} or discontinuity:
        profiles.append("SPECULATIVE_PROFILE")
    try:
        quality = finite_number(features.get("fundamental_quality_score"), "fundamental_quality_score", minimum=0, maximum=1)
        risk = finite_number(features.get("balance_sheet_risk"), "balance_sheet_risk", minimum=0, maximum=1)
        cash = finite_number(features.get("cash_flow_quality"), "cash_flow_quality", minimum=0, maximum=1)
        if quality >= 0.60 and risk <= 0.40 and cash >= 0.60 and liquidity in {"HIGH", "MEDIUM"}:
            profiles.append("INVESTMENT_PROFILE")
    except ValueError:
        pass
    return tuple(profiles) if profiles else ("UNCLASSIFIED_PROFILE",)


def build_decision(
    *,
    security_code: str,
    product: ProductSpec,
    model_card: ModelCardResult,
    score: float | None,
    probability: float | None,
    expected_net_edge: float | None,
    estimated_cost: float | None,
    safety_margin: float,
    gates: dict[str, bool],
    profile_features: dict[str, Any],
    execution: ExecutionAssessment | None,
) -> Decision:
    reasons: list[str] = []
    required_gates = {"pack", "identity", "timing", "universe", "corporate_actions", "feature_snapshot", "policy_hash"}
    for gate in sorted(required_gates):
        if gates.get(gate) is not True:
            reasons.append(f"{gate.upper()}_GATE_FAILED")
    if model_card.status != "PASS" or model_card.validation_status != "PROSPECTIVE_VALIDATED":
        reasons.append("MODEL_NOT_PROSPECTIVELY_VALIDATED")
    if probability is not None and not model_card.probability_allowed:
        reasons.append("PROBABILITY_NOT_ALLOWED")
    if expected_net_edge is None or estimated_cost is None:
        reasons.append("EDGE_OR_COST_MISSING")
    else:
        edge = finite_number(expected_net_edge, "expected_net_edge")
        cost = finite_number(estimated_cost, "estimated_cost", minimum=0)
        if edge <= cost + safety_margin:
            reasons.append("EDGE_NOT_ABOVE_COST_AND_MARGIN")
    execution_pass = execution is not None and execution.status == "EXECUTABLE"
    if product.execution_grade_required and not execution_pass:
        reasons.append("EXECUTION_REQUIRED_AND_NOT_PASSED")

    core_pass = not reasons
    profiles = classify_profiles(profile_features)
    if core_pass and execution_pass:
        status = "HIGH_BUY_OPPORTUNITY"
        profiles += ("HIGH_BUY_OPPORTUNITY",)
    elif core_pass:
        status = "QUALIFIED_RESEARCH_NOT_YET_EXECUTABLE"
    elif any(reason.endswith("_GATE_FAILED") for reason in reasons) or "MODEL_NOT_PROSPECTIVELY_VALIDATED" in reasons:
        status = "WATCH"
    else:
        status = "ABSTAIN"
    return Decision(security_code, product.product_id, status, profiles, score, probability, expected_net_edge, tuple(dict.fromkeys(reasons)))


__all__ = ["Decision", "build_decision", "classify_profiles"]
