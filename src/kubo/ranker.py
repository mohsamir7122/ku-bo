from __future__ import annotations

from typing import Any, Iterable

from .strict import finite_number


FEATURE_WEIGHTS = {
    "relative_return_5d": 0.25,
    "relative_return_20d": 0.15,
    "relative_value_20d": 0.20,
    "relative_volume_20d": 0.15,
    "official_event_net_30d": 0.15,
    "liquidity_percentile": 0.10,
}


def heuristic_rank(rows: Iterable[dict[str, Any]], *, product_id: str, top_k: int, minimum_feature_coverage: float = 0.67) -> list[dict[str, Any]]:
    if top_k <= 0 or not 0 <= minimum_feature_coverage <= 1:
        raise ValueError("invalid top_k or minimum_feature_coverage")
    prepared: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        code = str(row.get("security_code", "")).strip()
        if not code or code in seen:
            raise ValueError("denominator requires unique non-empty security_code values")
        seen.add(code)
        available: dict[str, float] = {}
        for feature in FEATURE_WEIGHTS:
            if row.get(feature) not in (None, ""):
                available[feature] = finite_number(row.get(feature), feature)
        coverage = len(available) / len(FEATURE_WEIGHTS)
        score = sum(FEATURE_WEIGHTS[name] * value for name, value in available.items()) if coverage >= minimum_feature_coverage else None
        abstained = score is None
        prepared.append(
            {
                **row,
                "security_code": code,
                "product_id": product_id,
                "score": score,
                "score_kind": "UNVALIDATED_HEURISTIC_BASELINE",
                "probability": None,
                "selected": False,
                "abstained": abstained,
                "eligible": True,
                "decision_status": "ABSTAIN" if abstained else "DETECTED",
                "reason_codes": ["INSUFFICIENT_FEATURE_COVERAGE"] if abstained else [],
                "feature_coverage": coverage,
                "available_features": sorted(available),
            }
        )
    scored = sorted((row for row in prepared if row["score"] is not None), key=lambda item: (-float(item["score"]), item["security_code"]))
    abstained_rows = sorted((row for row in prepared if row["score"] is None), key=lambda item: item["security_code"])
    for rank, row in enumerate(scored, start=1):
        row["rank"] = rank
        row["selected"] = rank <= top_k
    for row in abstained_rows:
        row["rank"] = None
    return scored + abstained_rows


__all__ = ["FEATURE_WEIGHTS", "heuristic_rank"]
