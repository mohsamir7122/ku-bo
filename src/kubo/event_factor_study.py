from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import statistics
from typing import Any

from .event_factor_common import (
    EventFactorPanelError,
    _digest,
    _fields,
    _mapping,
    _sha,
    _text,
)
from .event_factor_packet import validate_event_factor_panel_packet

def _pct(start: float, end: float) -> float:
    return (end / start - 1.0) * 100.0


def _returns(values: Sequence[float]) -> list[float]:
    return [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]


def _volatility(values: Sequence[float]) -> float:
    changes = _returns(values)
    return statistics.stdev(changes) * math.sqrt(252.0) * 100.0


def _max_drawdown(values: Sequence[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst * 100.0


def _max_runup(values: Sequence[float]) -> float:
    trough = values[0]
    best = 0.0
    for value in values:
        trough = min(trough, value)
        best = max(best, value / trough - 1.0)
    return best * 100.0


def _event_metrics(validated: Mapping[str, Any]) -> dict[str, Any]:
    """Compute internal structural metrics; public v1 withholds them on STOP."""

    pre = validated["pre_sessions"]
    post = validated["post_sessions"]
    pre_stock = [float(row["stock_total_return_index"]) for row in pre]
    post_stock = [float(row["stock_total_return_index"]) for row in post]
    post_market = [float(row["market_total_return_index"]) for row in post]
    post_sector = [float(row["sector_total_return_index"]) for row in post]
    pre_volume = [float(row["volume"]) for row in pre]
    post_volume = [float(row["volume"]) for row in post]
    stock_return = _pct(post_stock[0], post_stock[-1])
    market_return = _pct(post_market[0], post_market[-1])
    sector_return = _pct(post_sector[0], post_sector[-1])
    factors = validated["factor_snapshot"]["factors"]
    pre_mean = statistics.fmean(pre_volume)
    post_mean = statistics.fmean(post_volume)
    return {
        "pre_session_count": len(pre),
        "post_session_count": len(post),
        "pre_stock_return_pct": _pct(pre_stock[0], pre_stock[-1]),
        "post_stock_return_pct": stock_return,
        "post_market_return_pct": market_return,
        "post_sector_return_pct": sector_return,
        "post_market_excess_return_pct": stock_return - market_return,
        "post_sector_excess_return_pct": stock_return - sector_return,
        "pre_annualized_volatility_pct": _volatility(pre_stock),
        "post_annualized_volatility_pct": _volatility(post_stock),
        "pre_average_volume": pre_mean,
        "post_average_volume": post_mean,
        "post_to_pre_volume_ratio": post_mean / pre_mean if pre_mean else None,
        "post_max_drawdown_pct": _max_drawdown(post_stock),
        "post_max_runup_pct": _max_runup(post_stock),
        "observed_factor_count": sum(row["state"] == "OBSERVED" for row in factors),
        "unknown_factor_count": sum(
            row["state"] == "UNKNOWN_NOT_OBSERVED" for row in factors
        ),
        "blocked_factor_count": sum(row["state"] == "BLOCKED" for row in factors),
        "probability": None,
    }


def evaluate_event_factor_panel(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed until an independent final authority receipt exists."""

    errors: list[str] = []
    warnings: list[str] = []
    packet_id: str | None = None
    input_sha256: str | None = None
    diagnostics = {
        "pre_sessions": 0,
        "post_sessions": 0,
        "factor_rows": 0,
        "observed_factor_rows": 0,
        "unknown_factor_rows": 0,
        "blocked_factor_rows": 0,
    }
    try:
        input_sha256 = _digest(packet)
        validated = validate_event_factor_panel_packet(packet)
        packet_id = validated["packet_id"]
        factors = validated["factor_snapshot"]["factors"]
        diagnostics = {
            "pre_sessions": len(validated["pre_sessions"]),
            "post_sessions": len(validated["post_sessions"]),
            "factor_rows": len(factors),
            "observed_factor_rows": sum(row["state"] == "OBSERVED" for row in factors),
            "unknown_factor_rows": sum(
                row["state"] == "UNKNOWN_NOT_OBSERVED" for row in factors
            ),
            "blocked_factor_rows": sum(row["state"] == "BLOCKED" for row in factors),
        }
        warnings.append("STRUCTURAL_METRICS_COMPUTABLE_BUT_WITHHELD_PENDING_AUTHORITY")
    except (EventFactorPanelError, TypeError, ValueError) as exc:
        errors.append(f"EVENT_FACTOR_PACKET_INVALID:{exc}")
    errors.append("INDEPENDENT_FINAL_EVENT_STUDY_AUTHORITY_RECEIPT_REQUIRED")
    result = {
        "schema_version": "1.0",
        "status": "STOP_EVENT_STUDY",
        "input_sha256": input_sha256,
        "packet_id": packet_id,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "metrics": None,
        "diagnostics": diagnostics,
        "agreement_rate": None,
        "agreement_rate_status": "NOT_APPLICABLE",
        "accuracy_claim_allowed": False,
        "claim_boundaries": {
            "event_study_is_prospective_accuracy": False,
            "retrospective_cross_horizon_is_production_accuracy": False,
            "independent_final_authority_receipt_verified": False,
            "corporate_actions_must_be_adjusted_or_explicit_none": True,
            "market_and_sector_benchmarks_are_required": True,
            "metrics_withheld_on_stop": True,
            "probability_generated": False,
        },
    }
    return validate_event_factor_panel_result(result)


def validate_event_factor_panel_result(result: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(result, "result")
    expected = {
        "schema_version",
        "status",
        "input_sha256",
        "packet_id",
        "errors",
        "warnings",
        "metrics",
        "diagnostics",
        "agreement_rate",
        "agreement_rate_status",
        "accuracy_claim_allowed",
        "claim_boundaries",
    }
    _fields(result, expected, "result")
    if result["schema_version"] != "1.0" or result["status"] != "STOP_EVENT_STUDY":
        raise EventFactorPanelError("public v1 only permits STOP_EVENT_STUDY")
    if result["metrics"] is not None or result["agreement_rate"] is not None:
        raise EventFactorPanelError("STOP_EVENT_STUDY must withhold metrics")
    if result["agreement_rate_status"] != "NOT_APPLICABLE":
        raise EventFactorPanelError("agreement_rate_status must be NOT_APPLICABLE")
    if result["accuracy_claim_allowed"] is not False:
        raise EventFactorPanelError("accuracy claims are forbidden on STOP")
    if result["input_sha256"] is not None:
        _sha(result["input_sha256"], "result.input_sha256")
    if result["packet_id"] is not None:
        _text(result["packet_id"], "result.packet_id", 128)
    for field in ("errors", "warnings"):
        values = result[field]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise EventFactorPanelError(f"result.{field} must be an array")
        if len(set(values)) != len(values):
            raise EventFactorPanelError(f"result.{field} must be unique")
    if not result["errors"]:
        raise EventFactorPanelError("STOP_EVENT_STUDY requires an error")
    diagnostics = _mapping(result["diagnostics"], "result.diagnostics")
    diagnostic_fields = {
        "pre_sessions",
        "post_sessions",
        "factor_rows",
        "observed_factor_rows",
        "unknown_factor_rows",
        "blocked_factor_rows",
    }
    _fields(diagnostics, diagnostic_fields, "result.diagnostics")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in diagnostics.values()):
        raise EventFactorPanelError("diagnostics must be non-negative integers")
    expected_boundaries = {
        "event_study_is_prospective_accuracy": False,
        "retrospective_cross_horizon_is_production_accuracy": False,
        "independent_final_authority_receipt_verified": False,
        "corporate_actions_must_be_adjusted_or_explicit_none": True,
        "market_and_sector_benchmarks_are_required": True,
        "metrics_withheld_on_stop": True,
        "probability_generated": False,
    }
    boundaries = _mapping(result["claim_boundaries"], "result.claim_boundaries")
    _fields(boundaries, set(expected_boundaries), "result.claim_boundaries")
    if dict(boundaries) != expected_boundaries:
        raise EventFactorPanelError("claim boundaries violate the v1 STOP contract")
    return result

__all__ = [
    "_event_metrics",
    "evaluate_event_factor_panel",
    "validate_event_factor_panel_result",
]
