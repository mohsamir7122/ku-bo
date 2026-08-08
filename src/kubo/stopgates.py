from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .strict import require_sha256


REQUIRED_GATES = frozenset(
    {
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
    }
)


@dataclass(frozen=True)
class Gate:
    gate_id: str
    status: str
    severity: str
    evidence_hash: str
    failure_reason: str
    recovery_action: str


def build_stop_gate_report(gates: Iterable[Gate], *, manifest_hashes: frozenset[str], independent_dates: int, minimum_independent_dates: int, event_count: int, minimum_event_count: int = 1) -> dict[str, Any]:
    rows = list(gates)
    errors: list[str] = []
    by_id: dict[str, Gate] = {}
    for index, gate in enumerate(rows):
        if gate.gate_id in by_id:
            errors.append(f"DUPLICATE_GATE:{gate.gate_id}")
        by_id[gate.gate_id] = gate
        if gate.status not in {"PASS", "FAIL"}:
            errors.append(f"INVALID_GATE_STATUS:{gate.gate_id}")
        if gate.severity not in {"CRITICAL", "INFERENCE"}:
            errors.append(f"INVALID_GATE_SEVERITY:{gate.gate_id}")
        try:
            digest = require_sha256(gate.evidence_hash, "evidence_hash")
            if digest not in manifest_hashes:
                errors.append(f"UNRESOLVED_GATE_EVIDENCE:{gate.gate_id}")
        except ValueError:
            errors.append(f"INVALID_GATE_EVIDENCE:{gate.gate_id}")
        if gate.status == "FAIL" and (not gate.failure_reason or not gate.recovery_action):
            errors.append(f"FAILED_GATE_LACKS_RECOVERY:{gate.gate_id}")
    missing = sorted(REQUIRED_GATES - set(by_id))
    if missing:
        errors.append("MISSING_REQUIRED_GATES:" + ",".join(missing))
    critical_failures = sorted(gate.gate_id for gate in rows if gate.status == "FAIL" and gate.severity == "CRITICAL")
    if errors or critical_failures:
        verdict = "STOP_BACKTEST"
    elif independent_dates < minimum_independent_dates or event_count < minimum_event_count:
        verdict = "STOP_INFERENCE"
    else:
        verdict = "READY_TO_SCORE"
    return {
        "schema_version": "2.0",
        "verdict": verdict,
        "gates": [asdict(gate) for gate in rows],
        "critical_failures": critical_failures,
        "independent_dates": independent_dates,
        "minimum_independent_dates": minimum_independent_dates,
        "event_count": event_count,
        "minimum_event_count": minimum_event_count,
        "errors": sorted(set(errors)),
    }


__all__ = ["Gate", "REQUIRED_GATES", "build_stop_gate_report"]
