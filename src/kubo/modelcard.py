from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import ProductSpec
from .hashing import sha256_file
from .strict import finite_number, parse_aware, require_sha256, safe_relative_path


MODEL_STATES = frozenset({"CANDIDATE", "PILOT_LOCKED", "PILOT_EVALUATED", "PROMISING_PILOT", "PROSPECTIVE_VALIDATED", "RETIRED"})
PROSPECTIVE_RECEIPT_GATES = frozenset(
    {
        "artifact_resolution",
        "prospective_ledger",
        "temporal_validation",
        "full_denominator",
        "baseline_comparison",
        "costs_and_nonfill",
        "calibration",
    }
)
PROSPECTIVE_ARTIFACT_FIELDS = {
    "trial_registry": "trial_registry_hash",
    "model": "model_hash",
    "code": "code_hash",
    "policy": "policy_hash",
    "prospective_ledger": "prospective_ledger_hash",
}


@dataclass(frozen=True)
class ModelCardResult:
    status: str
    validation_status: str | None
    model_version: str | None
    probability_allowed: bool
    errors: tuple[str, ...]
    payload: dict[str, Any] | None


def _resolve_local_file(base: Path, value: Any, field: str) -> Path:
    relative = safe_relative_path(value, field)
    target = (base / relative).resolve()
    if base not in target.parents or not target.is_file():
        raise ValueError(f"{field} does not resolve to a file beside the model card")
    return target


def _validate_prospective_receipt(
    payload: dict[str, Any],
    *,
    card_path: Path,
    product: ProductSpec,
    approved_at: datetime,
    errors: list[str],
) -> None:
    """Resolve the evidence behind a prospective-validation claim.

    Hash-shaped strings are not validation.  A prospective card must bind a
    local receipt, and that receipt must in turn bind the trial registry,
    model, code, policy, and prospective ledger bytes it says were validated.
    """

    try:
        receipt_digest = require_sha256(
            payload.get("validation_receipt_hash"), "validation_receipt_hash"
        )
        receipt_path = _resolve_local_file(
            card_path.parent.resolve(),
            payload.get("validation_receipt_path"),
            "validation_receipt_path",
        )
        if sha256_file(receipt_path) != receipt_digest:
            raise ValueError("validation_receipt_hash does not match the receipt file")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise ValueError("validation receipt must be a JSON object")
        if receipt.get("schema_version") != "1.0":
            raise ValueError("unsupported validation receipt schema")
        if not str(receipt.get("receipt_id", "")).strip():
            raise ValueError("validation receipt requires receipt_id")
        if receipt.get("product_id") != product.product_id:
            raise ValueError("validation receipt product mismatch")
        if receipt.get("model_version") != payload.get("model_version"):
            raise ValueError("validation receipt model_version mismatch")
        if receipt.get("validation_status") != "PROSPECTIVE_VALIDATED":
            raise ValueError("validation receipt is not prospective")
        validated_at = parse_aware(receipt.get("validated_at"), "validation_receipt.validated_at")
        if validated_at > approved_at:
            raise ValueError("validation receipt postdates model approval")
        independent_dates = receipt.get("independent_dates")
        if isinstance(independent_dates, bool) or not isinstance(independent_dates, int):
            raise ValueError("validation receipt independent_dates must be an integer")
        if independent_dates < product.minimum_independent_dates:
            raise ValueError("validation receipt has insufficient independent dates")

        gates = receipt.get("gates")
        if not isinstance(gates, dict):
            raise ValueError("validation receipt gates must be an object")
        missing_gates = sorted(gate for gate in PROSPECTIVE_RECEIPT_GATES if gates.get(gate) is not True)
        if missing_gates:
            raise ValueError("validation receipt gates failed: " + ",".join(missing_gates))

        artifacts = receipt.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError("validation receipt artifacts must be an object")
        resolved_paths: set[Path] = set()
        for artifact_name, card_hash_field in PROSPECTIVE_ARTIFACT_FIELDS.items():
            descriptor = artifacts.get(artifact_name)
            if not isinstance(descriptor, dict):
                raise ValueError(f"validation receipt is missing artifact: {artifact_name}")
            declared_digest = require_sha256(
                descriptor.get("sha256"),
                f"validation_receipt.artifacts.{artifact_name}.sha256",
            )
            card_digest = require_sha256(payload.get(card_hash_field), card_hash_field)
            if declared_digest != card_digest:
                raise ValueError(f"validation receipt artifact hash mismatch: {artifact_name}")
            artifact_path = _resolve_local_file(
                card_path.parent.resolve(),
                descriptor.get("path"),
                f"validation_receipt.artifacts.{artifact_name}.path",
            )
            if artifact_path in resolved_paths:
                raise ValueError("validation receipt artifacts must resolve to distinct files")
            resolved_paths.add(artifact_path)
            if sha256_file(artifact_path) != declared_digest:
                raise ValueError(f"validation receipt artifact bytes mismatch: {artifact_name}")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"INVALID_PROSPECTIVE_VALIDATION_RECEIPT:{exc}")


def validate_model_card(path: Path, product: ProductSpec) -> ModelCardResult:
    if not path.is_file():
        return ModelCardResult("BLOCKED", None, None, False, ("MISSING_MODEL_CARD",), None)
    approved_at: datetime | None = None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ModelCardResult("BLOCKED", None, None, False, (f"INVALID_MODEL_CARD:{exc}",), None)
    if not isinstance(payload, dict):
        return ModelCardResult("BLOCKED", None, None, False, ("MODEL_CARD_NOT_OBJECT",), None)
    errors: list[str] = []
    required_text = (
        "model_version",
        "product_id",
        "target_rule",
        "decision_cutoff_rule",
        "eligible_universe_rule",
        "training_window",
        "calibration_window",
        "cost_and_fill_policy",
        "abstention_policy",
        "calibration_method",
    )
    for field in required_text:
        if not str(payload.get(field, "")).strip():
            errors.append(f"MISSING:{field}")
    state = str(payload.get("validation_status", ""))
    if state not in MODEL_STATES:
        errors.append("INVALID_VALIDATION_STATUS")
    if payload.get("product_id") != product.product_id:
        errors.append("MODEL_PRODUCT_MISMATCH")
    if payload.get("target_rule") != product.target_rule:
        errors.append("MODEL_TARGET_MISMATCH")
    try:
        if int(payload.get("horizon_sessions", 0)) != product.horizon_sessions:
            errors.append("MODEL_HORIZON_MISMATCH")
        if int(payload.get("purge_sessions", -1)) < product.horizon_sessions:
            errors.append("PURGE_SHORTER_THAN_HORIZON")
        if int(payload.get("embargo_sessions", -1)) < 0:
            errors.append("INVALID_EMBARGO")
        finite_number(payload.get("minimum_coverage"), "minimum_coverage", minimum=0, maximum=1)
        finite_number(payload.get("minimum_expected_net_edge"), "minimum_expected_net_edge")
        finite_number(payload.get("frozen_base_rate"), "frozen_base_rate", minimum=0, maximum=1)
        approved_at = parse_aware(payload.get("approved_at"), "approved_at")
        if approved_at > datetime.now(timezone.utc):
            errors.append("APPROVED_AT_IN_FUTURE")
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    for field in ("trial_registry_hash", "model_hash", "code_hash", "policy_hash"):
        try:
            require_sha256(payload.get(field), field)
        except ValueError as exc:
            errors.append(str(exc))
    for field in ("feature_names_and_available_at_rules", "locked_test_windows", "baseline_models", "out_of_sample_metrics_by_window_and_regime", "retirement_triggers"):
        if not payload.get(field):
            errors.append(f"MISSING:{field}")
    if state == "PROSPECTIVE_VALIDATED" and approved_at is not None:
        _validate_prospective_receipt(
            payload,
            card_path=path.resolve(),
            product=product,
            approved_at=approved_at,
            errors=errors,
        )
    probability_allowed = state == "PROSPECTIVE_VALIDATED" and not errors
    return ModelCardResult("PASS" if not errors else "BLOCKED", state or None, str(payload.get("model_version") or "") or None, probability_allowed, tuple(sorted(set(errors))), payload)


__all__ = [
    "MODEL_STATES",
    "PROSPECTIVE_ARTIFACT_FIELDS",
    "PROSPECTIVE_RECEIPT_GATES",
    "ModelCardResult",
    "validate_model_card",
]
