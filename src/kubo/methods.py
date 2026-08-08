from __future__ import annotations

from typing import Any, Iterable

from .catalog import MethodSpec, ProductSpec


MANDATORY_METHOD_GATES = frozenset({"point_in_time", "chronological_walk_forward", "full_denominator", "costs_and_nonfill", "baseline_comparison", "trial_registry"})


def select_methods(methods: Iterable[MethodSpec], product: ProductSpec, passed_capabilities: frozenset[str]) -> dict[str, Any]:
    available: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for method in methods:
        if product.product_id not in method.supports or method.state == "RETIRED":
            continue
        missing = sorted(method.required_capabilities - passed_capabilities)
        row = {
            "method_id": method.method_id,
            "state": method.state,
            "missing_capabilities": missing,
            "validation_gates": sorted(method.validation_gates),
            "emits_probability": method.emits_probability,
            "purpose": method.purpose,
        }
        if missing or method.state == "BLOCKED_CAPABILITY":
            blocked.append(row)
        else:
            available.append(row)
    available.sort(key=lambda row: (0 if row["state"] == "FROZEN_BASELINE" else 1, row["method_id"]))
    blocked.sort(key=lambda row: row["method_id"])
    return {"available": available, "blocked": blocked}


def audit_method(method: MethodSpec, supplied_gates: dict[str, bool]) -> dict[str, Any]:
    required = set(MANDATORY_METHOD_GATES) | set(method.validation_gates)
    if method.emits_probability:
        required.add("calibration")
    passed = sorted(gate for gate in required if supplied_gates.get(gate) is True)
    failed = sorted(required - set(passed))
    return {
        "method_id": method.method_id,
        "status": "AUDIT_PASS" if not failed else "AUDIT_BLOCKED",
        "passed_gates": passed,
        "failed_gates": failed,
        "note": "Mechanical method audit only; predictive validity requires sealed out-of-sample evidence.",
    }


__all__ = ["MANDATORY_METHOD_GATES", "audit_method", "select_methods"]
