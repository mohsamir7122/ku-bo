from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from kubo.catalog import Catalog, ProductSpec
from kubo.ledger import ForecastLedger
from kubo.modelcard import ModelCardResult
from kubo.stopgates import Gate, build_stop_gate_report
from kubo.synthetic import build_synthetic_valid_pack

HASHES = {char: char * 64 for char in "abcdef"}


def catalog(root: Path) -> Catalog:
    return Catalog(root / "config")


def synthetic_pack(path: Path) -> Path:
    return build_synthetic_valid_pack(path)


def valid_model(product: ProductSpec, *, probability_allowed: bool = True) -> ModelCardResult:
    payload = {
        "model_version": "model-v2",
        "product_id": product.product_id,
        "target_rule": product.target_rule,
        "horizon_sessions": product.horizon_sessions,
        "policy_hash": HASHES["a"],
        "non_fill_policy": "HOLD_CASH",
    }
    return ModelCardResult("PASS", "PROSPECTIVE_VALIDATED", "model-v2", probability_allowed, (), payload)


def product_with_minimum(product: ProductSpec, minimum: int) -> ProductSpec:
    return replace(product, minimum_independent_dates=minimum)


def gate_report(minimum_dates: int = 1, independent_dates: int = 1) -> dict[str, Any]:
    gates = [Gate(gate_id, "PASS", "CRITICAL", HASHES["a"], "", "") for gate_id in sorted({
        "ARTIFACT_RESOLUTION",
        "FORECAST_LEDGER",
        "LEDGER_SEAL",
        "LEAKAGE_CONTROL",
        "THESIS_EPISODES",
        "FULL_DENOMINATOR",
        "UNIVERSE_BENCHMARK",
        "POINT_IN_TIME_IDENTITY",
        "PRICE_CA_QA",
        "PROCESS_VALID_CLAIMS",
    })]
    return build_stop_gate_report(gates, manifest_hashes=frozenset(HASHES.values()), independent_dates=independent_dates, minimum_independent_dates=minimum_dates, event_count=1)


def one_decision_evaluation_fixture(directory: Path, product: ProductSpec, *, probability: float | None = None) -> dict[str, Any]:
    ledger = ForecastLedger(directory / "ledger.jsonl", "ledger-eval")
    payload = {
        "decision_id": "d1",
        "security_code": "101",
        "product_id": product.product_id,
        "target_rule": product.target_rule,
        "decision_at": "2026-08-06T14:00:00+03:00",
        "outcome_due_at": "2026-08-09T13:15:00+03:00",
        "horizon_sessions": product.horizon_sessions,
        "model_version": "model-v2",
        "entry_rule": "first feasible print",
        "eligible": True,
        "selected": True,
        "abstained": False,
        "score": 0.7,
        "probability": probability,
        "rank": 1,
        "thesis_episode_id": "episode-1",
    }
    event = ledger.append(
        event_type="CREATE",
        claim_id="claim-1",
        issued_at="2026-08-06T14:00:00+03:00",
        effective_at="2026-08-06T14:00:00+03:00",
        recorded_at="2026-08-06T14:01:00+03:00",
        test_mode=True,
        source_hash=HASHES["f"],
        actor_or_model_id="model-v2",
        policy_hash=HASHES["a"],
        code_hash=HASHES["b"],
        feature_snapshot_hash=HASHES["c"],
        universe_hash=HASHES["d"],
        trading_calendar_hash=HASHES["e"],
        security_status_hash=HASHES["f"],
        forecast_evidence_mode="SYNTHETIC_CONTRACT_ONLY",
        payload=payload,
    )
    prediction = {
        **payload,
        "feature_snapshot_hash": HASHES["c"],
        "universe_hash": HASHES["d"],
        "trading_calendar_hash": HASHES["e"],
        "security_status_hash": HASHES["f"],
        "policy_hash": HASHES["a"],
        "code_hash": HASHES["b"],
        "ledger_event_hash": event["event_hash"],
    }
    outcome = {
        "decision_id": "d1",
        "security_code": "101",
        "outcome_at": "2026-08-09T13:15:00+03:00",
        "horizon_sessions": product.horizon_sessions,
        "market_entry_price_fils": 100,
        "market_exit_price_fils": 105,
        "price_adjustment_factor": 1.0,
        "cash_distribution_return": 0.0,
        "benchmark_entry_value": 1000,
        "benchmark_exit_value": 1010,
        "fees_return": 0.001,
        "spread_return": 0.001,
        "slippage_return": 0.001,
        "market_impact_return": 0.0,
        "fill_status": "FILLED",
        "executed_entry_price_fils": 101,
        "executed_exit_price_fils": 104,
        "price_evidence_hash": HASHES["a"],
        "benchmark_evidence_hash": HASHES["a"],
        "corporate_action_evidence_hash": "",
        "outcome_evidence_hash": HASHES["a"],
    }
    return {"ledger": ledger, "event": event, "prediction": prediction, "outcome": outcome}


def rewrite_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
