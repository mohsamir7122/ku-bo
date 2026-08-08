from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .catalog import ProductSpec
from .modelcard import ModelCardResult
from .strict import finite_number, parse_aware, require_sha256, strict_bool


KUWAIT = ZoneInfo("Asia/Kuwait")
PREDICTION_HASH_FIELDS = ("feature_snapshot_hash", "universe_hash", "trading_calendar_hash", "policy_hash", "code_hash", "ledger_event_hash")


def _rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][1] == indexed[position][1]:
            end += 1
        average_rank = (position + 1 + end) / 2
        for cursor in range(position, end):
            ranks[indexed[cursor][0]] = average_rank
        position = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right))
    return numerator / denominator if denominator else None


def _spearman(left: list[float], right: list[float]) -> float | None:
    return _pearson(_rank(left), _rank(right))


def _event_realized(product: ProductSpec, comparable_gross: float, comparable_net_excess: float) -> bool:
    if product.target_rule == "NET_EXCESS_GT_0":
        return comparable_net_excess > 0
    if product.target_rule == "GROSS_RETURN_GTE_5":
        return comparable_gross >= 0.05
    if product.target_rule == "GROSS_RETURN_GTE_10":
        return comparable_gross >= 0.10
    if product.target_rule == "TOTAL_AND_EXCESS_GT_0":
        return comparable_gross > 0 and comparable_net_excess > 0
    raise ValueError(f"evaluation rule is not implemented: {product.target_rule}")


def _ledger_create_map(events: Iterable[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], list[str]]:
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[str] = []
    for index, event in enumerate(events):
        if event.get("event_type") != "CREATE":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            errors.append(f"ledger_{index}:PAYLOAD")
            continue
        key = (str(payload.get("decision_id", "")), str(payload.get("security_code", "")))
        if not all(key) or key in mapping:
            errors.append(f"ledger_{index}:DUPLICATE_OR_EMPTY_KEY")
            continue
        mapping[key] = event
    return mapping, errors


def evaluate_forecasts(
    predictions: Iterable[dict[str, Any]],
    outcomes: Iterable[dict[str, Any]],
    *,
    product: ProductSpec,
    model_card: ModelCardResult,
    ledger_events: Iterable[dict[str, Any]],
    gate_report: dict[str, Any],
    universe_by_decision: dict[str, frozenset[str]],
    resolved_artifact_hashes: frozenset[str],
    top_k: int = 5,
) -> dict[str, Any]:
    predictions = list(predictions)
    outcomes = list(outcomes)
    errors: list[str] = []
    if top_k <= 0:
        errors.append("TOP_K_NOT_POSITIVE")
    if gate_report.get("verdict") == "STOP_BACKTEST":
        errors.append("STOP_GATE_REPORT_BLOCKS_BACKTEST")
    if model_card.status != "PASS" or not model_card.payload:
        errors.append("MODEL_CARD_INVALID")
    elif model_card.payload.get("product_id") != product.product_id:
        errors.append("MODEL_PRODUCT_MISMATCH")
    ledger_map, ledger_errors = _ledger_create_map(ledger_events)
    errors.extend(ledger_errors)

    prediction_map: dict[tuple[str, str], dict[str, Any]] = {}
    ranks_by_decision: dict[str, set[int]] = defaultdict(set)
    decision_dates: set[str] = set()
    normalized_predictions: list[dict[str, Any]] = []
    for index, row in enumerate(predictions):
        prefix = f"prediction_{index}"
        try:
            decision_id = str(row.get("decision_id", "")).strip()
            code = str(row.get("security_code", "")).strip()
            key = (decision_id, code)
            if not all(key) or key in prediction_map:
                raise ValueError("duplicate or empty prediction key")
            prediction_map[key] = row
            decision_at = parse_aware(row.get("decision_at"), "decision_at")
            due = parse_aware(row.get("outcome_due_at"), "outcome_due_at")
            if due <= decision_at:
                raise ValueError("outcome_due_at is not after decision_at")
            decision_dates.add(decision_at.astimezone(KUWAIT).date().isoformat())
            if str(row.get("product_id")) != product.product_id or str(row.get("target_rule")) != product.target_rule:
                raise ValueError("product or target mismatch")
            if int(row.get("horizon_sessions", 0)) != product.horizon_sessions:
                raise ValueError("horizon mismatch")
            eligible = strict_bool(row.get("eligible"), "eligible")
            selected = strict_bool(row.get("selected"), "selected")
            abstained = strict_bool(row.get("abstained"), "abstained")
            if selected and (abstained or not eligible):
                raise ValueError("invalid selection flags")
            score_value = row.get("score")
            score = finite_number(score_value, "score") if score_value not in (None, "") else None
            probability_value = row.get("probability")
            probability = finite_number(probability_value, "probability", minimum=0, maximum=1) if probability_value not in (None, "") else None
            if probability is not None and not model_card.probability_allowed:
                raise ValueError("probability is not allowed by model card")
            rank_value = row.get("rank")
            rank = int(rank_value) if rank_value not in (None, "") else None
            if rank is not None:
                if rank <= 0 or rank in ranks_by_decision[decision_id]:
                    raise ValueError("rank must be unique and positive")
                ranks_by_decision[decision_id].add(rank)
            for field in PREDICTION_HASH_FIELDS:
                digest = require_sha256(row.get(field), field)
                if field != "ledger_event_hash" and digest not in resolved_artifact_hashes:
                    raise ValueError(f"{field} does not resolve")
            if model_card.payload and row.get("model_version") != model_card.payload.get("model_version"):
                raise ValueError("model_version mismatch")
            if model_card.payload and row.get("policy_hash") != model_card.payload.get("policy_hash"):
                raise ValueError("policy_hash mismatch")
            expected_universe = universe_by_decision.get(decision_id)
            if expected_universe is None or code not in expected_universe:
                raise ValueError("prediction is outside frozen universe")
            ledger_event = ledger_map.get(key)
            if ledger_event is None or row.get("ledger_event_hash") != ledger_event.get("event_hash"):
                raise ValueError("prediction lacks matching CREATE ledger event")
            payload = ledger_event["payload"]
            for field in ("decision_id", "security_code", "product_id", "target_rule", "decision_at", "outcome_due_at", "horizon_sessions", "model_version", "eligible", "selected", "abstained", "score", "probability", "rank"):
                if payload.get(field) != row.get(field):
                    raise ValueError(f"ledger payload mismatch: {field}")
            for field in ("feature_snapshot_hash", "universe_hash", "trading_calendar_hash", "policy_hash", "code_hash"):
                if ledger_event.get(field) != row.get(field):
                    raise ValueError(f"ledger evidence mismatch: {field}")
            normalized_predictions.append({**row, "score": score, "probability": probability, "rank": rank, "eligible": eligible, "selected": selected, "abstained": abstained})
        except (TypeError, ValueError) as exc:
            errors.append(f"{prefix}:{exc}")
    for decision_id, expected in universe_by_decision.items():
        actual = {code for d_id, code in prediction_map if d_id == decision_id}
        if actual != set(expected):
            errors.append(f"DENOMINATOR_MISMATCH:{decision_id}:missing={len(set(expected)-actual)}:extra={len(actual-set(expected))}")

    outcome_map: dict[tuple[str, str], dict[str, Any]] = {}
    normalized_outcomes: dict[tuple[str, str], dict[str, Any]] = {}
    non_fill_policy = str((model_card.payload or {}).get("non_fill_policy", ""))
    for index, row in enumerate(outcomes):
        prefix = f"outcome_{index}"
        try:
            key = (str(row.get("decision_id", "")), str(row.get("security_code", "")))
            if not all(key) or key in outcome_map:
                raise ValueError("duplicate or empty outcome key")
            outcome_map[key] = row
            prediction = prediction_map.get(key)
            if prediction is None:
                raise ValueError("outcome has no prediction")
            outcome_at = parse_aware(row.get("outcome_at"), "outcome_at")
            if outcome_at != parse_aware(prediction.get("outcome_due_at"), "outcome_due_at"):
                raise ValueError("outcome_at differs from predeclared due time")
            if int(row.get("horizon_sessions", 0)) != product.horizon_sessions:
                raise ValueError("outcome horizon mismatch")
            market_entry = finite_number(row.get("market_entry_price_fils"), "market_entry_price_fils", minimum=0.001)
            market_exit = finite_number(row.get("market_exit_price_fils"), "market_exit_price_fils", minimum=0.001)
            factor = finite_number(row.get("price_adjustment_factor"), "price_adjustment_factor", minimum=0.0000001)
            distribution = finite_number(row.get("cash_distribution_return"), "cash_distribution_return")
            benchmark_entry = finite_number(row.get("benchmark_entry_value"), "benchmark_entry_value", minimum=0.0000001)
            benchmark_exit = finite_number(row.get("benchmark_exit_value"), "benchmark_exit_value", minimum=0.0000001)
            benchmark_return = benchmark_exit / benchmark_entry - 1
            comparable_gross = market_exit * factor / market_entry - 1 + distribution
            comparable_net_excess = comparable_gross - benchmark_return
            cost = sum(
                finite_number(row.get(field), field, minimum=0)
                for field in ("fees_return", "spread_return", "slippage_return", "market_impact_return")
            )
            fill_status = str(row.get("fill_status", "")).upper()
            selected = bool(prediction.get("selected"))
            if selected and fill_status == "FILLED":
                executed_entry = finite_number(row.get("executed_entry_price_fils"), "executed_entry_price_fils", minimum=0.001)
                executed_exit = finite_number(row.get("executed_exit_price_fils"), "executed_exit_price_fils", minimum=0.001)
                executed_gross = executed_exit * factor / executed_entry - 1 + distribution
                executed_net_excess = executed_gross - benchmark_return - cost
            elif selected and fill_status == "NOT_FILLED" and non_fill_policy == "HOLD_CASH":
                executed_gross = 0.0
                executed_net_excess = -benchmark_return
            elif selected:
                raise ValueError("selected row lacks a valid frozen fill disposition")
            else:
                if fill_status not in {"MARKET_OBSERVED", "NOT_APPLICABLE", "FILLED"}:
                    raise ValueError("invalid unselected fill_status")
                executed_gross = None
                executed_net_excess = None
            for field in ("price_evidence_hash", "benchmark_evidence_hash", "corporate_action_evidence_hash", "outcome_evidence_hash"):
                value = row.get(field)
                if field == "corporate_action_evidence_hash" and value in (None, "") and factor == 1.0 and distribution == 0.0:
                    continue
                digest = require_sha256(value, field)
                if digest not in resolved_artifact_hashes:
                    raise ValueError(f"{field} does not resolve")
            supplied = row.get("comparable_net_excess_return")
            if supplied not in (None, "") and abs(finite_number(supplied, "comparable_net_excess_return") - comparable_net_excess) > 1e-10:
                raise ValueError("supplied comparable return disagrees with recomputation")
            normalized_outcomes[key] = {
                "comparable_gross": comparable_gross,
                "benchmark_return": benchmark_return,
                "comparable_net_excess": comparable_net_excess,
                "executed_gross": executed_gross,
                "executed_net_excess": executed_net_excess,
                "fill_status": fill_status,
                "event_realized": _event_realized(product, comparable_gross, comparable_net_excess),
            }
        except (TypeError, ValueError) as exc:
            errors.append(f"{prefix}:{exc}")
    expected_keys = set(prediction_map)
    if set(outcome_map) != expected_keys:
        errors.append(f"OUTCOME_DENOMINATOR_MISMATCH:missing={len(expected_keys-set(outcome_map))}:extra={len(set(outcome_map)-expected_keys)}")

    if errors:
        return {
            "status": "STOP_BACKTEST",
            "errors": sorted(set(errors)),
            "prediction_rows": len(predictions),
            "outcome_rows": len(outcomes),
            "metrics": None,
        }

    by_decision: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in normalized_predictions:
        key = (str(prediction["decision_id"]), str(prediction["security_code"]))
        by_decision[key[0]].append({"prediction": prediction, "outcome": normalized_outcomes[key]})
    rank_ics: list[float] = []
    precision_values: list[float] = []
    recall_values: list[float] = []
    selected_executed: list[float] = []
    brier_terms: list[float] = []
    nonfills = 0
    selected_count = 0
    for decision_id, rows in by_decision.items():
        scored = [item for item in rows if item["prediction"]["score"] is not None and not item["prediction"]["abstained"]]
        if len(scored) >= 2:
            ic = _spearman([float(item["prediction"]["score"]) for item in scored], [float(item["outcome"]["comparable_net_excess"]) for item in scored])
            if ic is not None:
                rank_ics.append(ic)
        selected = [item for item in rows if item["prediction"]["selected"] and not item["prediction"]["abstained"]]
        actual_top = sorted(rows, key=lambda item: (-float(item["outcome"]["comparable_net_excess"]), str(item["prediction"]["security_code"])))[: min(top_k, len(rows))]
        selected_codes = {str(item["prediction"]["security_code"]) for item in selected}
        actual_codes = {str(item["prediction"]["security_code"]) for item in actual_top}
        if selected:
            precision_values.append(sum(1 for item in selected if item["outcome"]["event_realized"]) / len(selected))
        if actual_codes:
            recall_values.append(len(selected_codes & actual_codes) / len(actual_codes))
        for item in selected:
            selected_count += 1
            if item["outcome"]["fill_status"] == "NOT_FILLED":
                nonfills += 1
            if item["outcome"]["executed_net_excess"] is not None:
                selected_executed.append(float(item["outcome"]["executed_net_excess"]))
        for item in rows:
            probability = item["prediction"]["probability"]
            if probability is not None:
                actual = 1.0 if item["outcome"]["event_realized"] else 0.0
                brier_terms.append((float(probability) - actual) ** 2)
    abstained_count = sum(1 for row in normalized_predictions if row["abstained"])
    metrics = {
        "decision_dates": len(decision_dates),
        "denominator_rows": len(normalized_predictions),
        "coverage": 1.0,
        "abstention_rate": abstained_count / len(normalized_predictions) if normalized_predictions else None,
        "mean_rank_ic": mean(rank_ics) if rank_ics else None,
        "mean_precision_selected": mean(precision_values) if precision_values else None,
        "mean_recall_at_k": mean(recall_values) if recall_values else None,
        "mean_selected_executed_net_excess": mean(selected_executed) if selected_executed else None,
        "selected_count": selected_count,
        "non_fill_rate": nonfills / selected_count if selected_count else None,
        "brier_score": mean(brier_terms) if brier_terms else None,
        "probability_rows": len(brier_terms),
    }
    status = "PASS"
    reason = None
    if len(decision_dates) < product.minimum_independent_dates or gate_report.get("verdict") == "STOP_INFERENCE":
        status = "STOP_INFERENCE"
        reason = "insufficient independent decision dates or preregistered power"
    return {"status": status, "reason": reason, "errors": [], "metrics": metrics}


__all__ = ["evaluate_forecasts"]
