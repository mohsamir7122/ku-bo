from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any

from .event_factor_common import (
    EventFactorPanelError,
    MATERIAL_RETURN_THRESHOLD_PCT,
    _RETRO_FIELDS,
    _aware,
    _fields,
    _mapping,
    _number,
    _positive_int,
    _text,
)

def _actual_label(return_pct: float, threshold: float) -> str:
    if return_pct >= threshold:
        return "POSITIVE"
    if return_pct <= -threshold:
        return "NEGATIVE"
    return "NEUTRAL"


def _predicted_label(action: str) -> str:
    mapping = {"LONG": "POSITIVE", "AVOID": "NEGATIVE", "NEUTRAL": "NEUTRAL"}
    if action not in mapping:
        raise EventFactorPanelError(f"unsupported action: {action}")
    return mapping[action]


def _ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        rank = ((cursor + 1) + end) / 2.0
        for position in range(cursor, end):
            result[ordered[position][0]] = rank
        cursor = end
    return result


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_dev = [value - left_mean for value in left]
    right_dev = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_dev)
        * sum(value * value for value in right_dev)
    )
    if denominator == 0.0:
        return None
    return sum(a * b for a, b in zip(left_dev, right_dev, strict=True)) / denominator


def audit_retrospective_decisions(
    rows: Sequence[Mapping[str, Any]],
    *,
    material_return_threshold_pct: float = MATERIAL_RETURN_THRESHOLD_PCT,
    decision_cadence_sessions: int | None = None,
) -> dict[str, Any]:
    """Measure a sealed ledger without promoting it to prospective accuracy."""

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise EventFactorPanelError("rows must be a non-empty array")
    threshold = _number(
        material_return_threshold_pct,
        "material_return_threshold_pct",
        minimum=0.01,
        maximum=100.0,
    )
    cadence = (
        _positive_int(decision_cadence_sessions, "decision_cadence_sessions")
        if decision_cadence_sessions is not None
        else None
    )
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(rows):
        row = _mapping(item, f"rows[{index}]")
        _fields(row, _RETRO_FIELDS, f"rows[{index}]")
        decision_id = _text(row["decision_id"], f"rows[{index}].decision_id", 128)
        if decision_id in seen:
            raise EventFactorPanelError(f"duplicate decision_id: {decision_id}")
        seen.add(decision_id)
        _aware(row["decision_at"], f"rows[{index}].decision_at")
        action = _text(row["action"], f"rows[{index}].action", 32)
        relative_return = _number(
            row["relative_return_pct"], f"rows[{index}].relative_return_pct"
        )
        parsed.append(
            {
                "score": _number(row["score"], f"rows[{index}].score"),
                "action": action,
                "predicted": _predicted_label(action),
                "actual": _actual_label(relative_return, threshold),
                "return": relative_return,
                "model_horizon": _positive_int(
                    row["model_horizon_sessions"],
                    f"rows[{index}].model_horizon_sessions",
                ),
                "audited_horizon": _positive_int(
                    row["audited_horizon_sessions"],
                    f"rows[{index}].audited_horizon_sessions",
                ),
            }
        )

    labels = ("NEGATIVE", "NEUTRAL", "POSITIVE")
    confusion = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for row in parsed:
        confusion[row["actual"]][row["predicted"]] += 1
    counts_actual = {
        label: sum(row["actual"] == label for row in parsed) for label in labels
    }
    counts_predicted = {
        label: sum(row["predicted"] == label for row in parsed) for label in labels
    }
    recalls: list[float] = []
    f1s: list[float] = []
    for label in labels:
        tp = confusion[label][label]
        fn = sum(confusion[label][other] for other in labels if other != label)
        fp = sum(confusion[other][label] for other in labels if other != label)
        recall = tp / (tp + fn) if tp + fn else 0.0
        precision = tp / (tp + fp) if tp + fp else 0.0
        recalls.append(recall)
        f1s.append(
            2.0 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    directional = [row for row in parsed if row["action"] != "NEUTRAL"]
    material_hits = sum(row["actual"] == row["predicted"] for row in directional)
    sign_hits = sum(
        (row["action"] == "LONG" and row["return"] > 0.0)
        or (row["action"] == "AVOID" and row["return"] < 0.0)
        for row in directional
    )
    scores = [float(row["score"]) for row in parsed]
    returns = [float(row["return"]) for row in parsed]
    audited_horizons = sorted({int(row["audited_horizon"]) for row in parsed})
    model_horizons = sorted({int(row["model_horizon"]) for row in parsed})
    overlap = (
        "UNKNOWN_WITHOUT_DECISION_CADENCE"
        if cadence is None
        else (
            "OVERLAPPING_OUTCOME_WINDOWS"
            if any(horizon > cadence for horizon in audited_horizons)
            else "NON_OVERLAPPING_BY_DECLARED_CADENCE"
        )
    )
    total = len(parsed)
    hits = sum(row["actual"] == row["predicted"] for row in parsed)
    return {
        "schema_version": "1.0",
        "study_mode": "RETROSPECTIVE_DECISION_LEDGER_AUDIT",
        "sample_size": total,
        "material_return_threshold_pct": threshold,
        "actual_class_counts": counts_actual,
        "predicted_class_counts": counts_predicted,
        "confusion_matrix": confusion,
        "raw_concordance_hits": hits,
        "raw_concordance_rate": hits / total,
        "always_neutral_hits": counts_actual["NEUTRAL"],
        "always_neutral_rate": counts_actual["NEUTRAL"] / total,
        "balanced_accuracy": statistics.fmean(recalls),
        "macro_f1": statistics.fmean(f1s),
        "directional_signal_count": len(directional),
        "material_directional_hits": material_hits,
        "material_directional_rate": material_hits / len(directional) if directional else None,
        "sign_directional_hits": sign_hits,
        "sign_directional_rate": sign_hits / len(directional) if directional else None,
        "pearson_score_return": _pearson(scores, returns),
        "spearman_score_return": _pearson(_ranks(scores), _ranks(returns)),
        "model_horizons": model_horizons,
        "audited_horizons": audited_horizons,
        "cross_horizon": any(
            row["model_horizon"] != row["audited_horizon"] for row in parsed
        ),
        "overlap_status": overlap,
        "p_value_reported": False,
        "probability": None,
        "accuracy_claim_allowed": False,
        "claim_boundaries": {
            "retrospective_is_prospective_accuracy": False,
            "cross_horizon_is_production_validation": False,
            "overlapping_windows_are_independent": False,
            "always_neutral_baseline_must_be_reported": True,
            "score_correlation_is_trade_policy": False,
        },
    }


def _csv_positive_int(value: Any, field: str) -> int:
    number = _number(value, field, minimum=1)
    if not number.is_integer():
        raise EventFactorPanelError(f"{field} must be a positive integer")
    return int(number)


def audit_retrospective_csv(
    input_path: Path,
    *,
    output_path: Path | None = None,
    audited_horizon_sessions: int = 20,
    decision_cadence_sessions: int | None = 5,
    material_return_threshold_pct: float = MATERIAL_RETURN_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Audit the sealed HUMANSOFT-style CSV and emit aggregate-only JSON."""

    path = Path(input_path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or ())
            required = {
                "prediction_id",
                "protocol_version",
                "decision_at",
                "horizon_sessions",
                "score",
                "action",
                f"excess_return_{audited_horizon_sessions}_pct",
            }
            if not required.issubset(headers):
                missing = ",".join(sorted(required - headers))
                raise EventFactorPanelError(
                    f"retrospective CSV missing columns: {missing}"
                )
            source_rows = list(reader)
    except OSError as exc:
        raise EventFactorPanelError(
            f"cannot read retrospective CSV: {exc}"
        ) from exc
    if not source_rows:
        raise EventFactorPanelError("retrospective CSV has no rows")

    protocols = sorted(
        {
            _text(row.get("protocol_version"), "protocol_version", 256)
            for row in source_rows
        }
    )
    mapped: list[dict[str, Any]] = []
    return_field = f"excess_return_{audited_horizon_sessions}_pct"
    for index, row in enumerate(source_rows):
        mapped.append(
            {
                "decision_id": _text(
                    row.get("prediction_id"),
                    f"csv.rows[{index}].prediction_id",
                    128,
                ),
                "decision_at": _text(
                    row.get("decision_at"),
                    f"csv.rows[{index}].decision_at",
                    64,
                ),
                "model_horizon_sessions": _csv_positive_int(
                    row.get("horizon_sessions"),
                    f"csv.rows[{index}].horizon_sessions",
                ),
                "audited_horizon_sessions": audited_horizon_sessions,
                "score": _number(
                    row.get("score"), f"csv.rows[{index}].score"
                ),
                "action": _text(
                    row.get("action"),
                    f"csv.rows[{index}].action",
                    32,
                ),
                "relative_return_pct": _number(
                    row.get(return_field),
                    f"csv.rows[{index}].{return_field}",
                ),
            }
        )
    result = audit_retrospective_decisions(
        mapped,
        material_return_threshold_pct=material_return_threshold_pct,
        decision_cadence_sessions=decision_cadence_sessions,
    )
    result = {
        **result,
        "source_filename": path.name,
        "source_protocol_versions": protocols,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_level_data_emitted": False,
    }
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
    return result



__all__ = ["audit_retrospective_csv", "audit_retrospective_decisions"]
