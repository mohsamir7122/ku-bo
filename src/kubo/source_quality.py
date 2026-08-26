"""Adaptive, fail-closed quality assessment for KU-BO research sources.

The score routes a source to review actions. It is never a probability, an
authorization receipt, or automatic evidence admission.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Mapping

from .foundation_io import load_strict_json_object


POLICY_PATH = Path("config/source_quality_policy.json")
DIMENSION_IDS = (
    "authority",
    "rights_and_access",
    "point_in_time_integrity",
    "identity_binding",
    "parser_stability",
    "coverage_completeness",
    "publisher_independence",
)
EXPECTED_DIMENSION_WEIGHTS = {
    "authority": 0.24,
    "rights_and_access": 0.18,
    "point_in_time_integrity": 0.18,
    "identity_binding": 0.14,
    "parser_stability": 0.10,
    "coverage_completeness": 0.10,
    "publisher_independence": 0.06,
}
EXPECTED_THRESHOLDS = {
    "admit": 0.80,
    "corroboration_only": 0.60,
    "quarantine_below": 0.60,
}
EXPECTED_ACTIONS = {
    "ADMIT": "MONITOR_AND_REVALIDATE",
    "CORROBORATION_ONLY": "ADD_INDEPENDENT_PRIMARY_OR_OFFICIAL_SOURCE",
    "QUARANTINE": "RECOVER_RIGHTS_IDENTITY_TIME_AND_HASH_BEFORE_RETRY",
    "BLOCK": "STOP_ROUTE_AND_RECORD_FAILURE",
}
EXPECTED_ROLE_LIMITS = {
    "OFFICIAL_TRUTH": ("OFFICIAL_FACT", "OFFICIAL_IDENTITY", "OFFICIAL_EVENT"),
    "SECONDARY_RESEARCH": ("PRICE_CONTEXT", "NEWS_CORROBORATION", "RESEARCH_CONTEXT"),
    "COMMUNITY_ROUTING_ONLY": ("SENTIMENT", "ROUTING"),
    "PRIVATE_STORAGE_ONLY": (),
}
EXPECTED_CLAIM_BOUNDARIES = {
    "catalog_presence_proves_quality": False,
    "drive_presence_grants_rights": False,
    "single_source_can_prove_market_view": False,
    "community_can_create_official_fact": False,
    "quality_score_is_probability": False,
    "automatic_source_promotion_allowed": False,
}
EXPECTED_HARD_BLOCKS = frozenset(
    {
        "ACCESS_CONTROL_BYPASS",
        "RIGHTS_UNKNOWN_FOR_SYSTEMATIC_REUSE",
        "PRIVATE_LOCATOR_LEAK",
        "UNBOUND_SECURITY_IDENTITY",
        "POINT_IN_TIME_UNPROVEN",
        "PARSER_DRIFT",
        "HASH_MISMATCH",
    }
)
ROOT_KEYS = frozenset(
    {
        "schema_version",
        "policy_id",
        "status",
        "dimensions",
        "thresholds",
        "hard_blocks",
        "adaptive_actions",
        "role_limits",
        "claim_boundaries",
    }
)
THRESHOLD_KEYS = frozenset({"admit", "corroboration_only", "quarantine_below"})
ACTION_KEYS = frozenset({"ADMIT", "CORROBORATION_ONLY", "QUARANTINE", "BLOCK"})
ROLE_KEYS = frozenset(
    {"OFFICIAL_TRUTH", "SECONDARY_RESEARCH", "COMMUNITY_ROUTING_ONLY", "PRIVATE_STORAGE_ONLY"}
)


class SourceQualityError(ValueError):
    """Raised when a quality policy or assessment weakens a source gate."""


def _load_object(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    try:
        return load_strict_json_object(
            path,
            field=field,
            max_bytes=4 * 1024 * 1024,
        )
    except ValueError as exc:
        raise SourceQualityError(f"cannot load strict {field} JSON: {path}") from exc


def _exact_keys(value: Any, expected: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SourceQualityError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != expected:
        raise SourceQualityError(
            f"{field} has missing={sorted(expected - actual)} unknown={sorted(actual - expected)}"
        )
    return value


def _unit_interval(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceQualityError(f"{field} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1 or (positive and parsed == 0):
        raise SourceQualityError(f"{field} must be {'greater than 0 and ' if positive else ''}within [0, 1]")
    return parsed


def _policy_path(project_root_or_path: Path | str) -> Path:
    value = Path(project_root_or_path)
    return value / POLICY_PATH if value.is_dir() else value


def validate_source_quality_policy(project_root_or_path: Path | str) -> dict[str, Any]:
    """Validate the locked policy and return a sanitized contract report."""

    path = _policy_path(project_root_or_path)
    payload, policy_content = _load_object(path, "source quality policy")
    _exact_keys(payload, ROOT_KEYS, "source quality policy")
    if payload["schema_version"] != "1.0":
        raise SourceQualityError("unsupported source quality schema")
    if payload["policy_id"] != "ku-bo-adaptive-source-quality-v1":
        raise SourceQualityError("unexpected source quality policy_id")
    if payload["status"] != "CONTRACT_ONLY":
        raise SourceQualityError("source quality policy must remain CONTRACT_ONLY")

    dimensions = payload["dimensions"]
    if not isinstance(dimensions, list) or len(dimensions) != len(DIMENSION_IDS):
        raise SourceQualityError("source quality dimensions must contain exactly seven rows")
    weights: dict[str, float] = {}
    for index, row in enumerate(dimensions):
        item = _exact_keys(row, frozenset({"dimension_id", "weight"}), f"dimensions[{index}]")
        dimension_id = item["dimension_id"]
        if dimension_id not in DIMENSION_IDS or dimension_id in weights:
            raise SourceQualityError("source quality dimensions must be unique and canonical")
        weights[str(dimension_id)] = _unit_interval(
            item["weight"], f"dimensions[{index}].weight", positive=True
        )
    if tuple(weights) != DIMENSION_IDS:
        raise SourceQualityError("source quality dimensions are reordered or incomplete")
    if not math.isclose(sum(weights.values()), 1.0, rel_tol=0, abs_tol=1e-9):
        raise SourceQualityError("source quality weights must sum to 1")
    if weights != EXPECTED_DIMENSION_WEIGHTS:
        raise SourceQualityError("source quality v1 weights changed without a policy version bump")

    thresholds = _exact_keys(payload["thresholds"], THRESHOLD_KEYS, "thresholds")
    parsed_thresholds = {
        key: _unit_interval(value, f"thresholds.{key}") for key, value in thresholds.items()
    }
    if not (
        parsed_thresholds["quarantine_below"]
        == parsed_thresholds["corroboration_only"]
        < parsed_thresholds["admit"]
    ):
        raise SourceQualityError("source quality thresholds overlap or leave an ambiguous gap")
    if parsed_thresholds != EXPECTED_THRESHOLDS:
        raise SourceQualityError("source quality v1 thresholds changed without a policy version bump")

    hard_blocks = payload["hard_blocks"]
    if (
        not isinstance(hard_blocks, list)
        or any(not isinstance(code, str) for code in hard_blocks)
        or frozenset(hard_blocks) != EXPECTED_HARD_BLOCKS
    ):
        raise SourceQualityError("source quality hard blocks were weakened or changed")
    if len(hard_blocks) != len(EXPECTED_HARD_BLOCKS):
        raise SourceQualityError("source quality hard blocks contain duplicates")

    actions = _exact_keys(payload["adaptive_actions"], ACTION_KEYS, "adaptive_actions")
    if dict(actions) != EXPECTED_ACTIONS:
        raise SourceQualityError("source quality adaptive actions changed without a version bump")

    role_limits = _exact_keys(payload["role_limits"], ROLE_KEYS, "role_limits")
    normalized_roles: dict[str, tuple[str, ...]] = {}
    for role, values in role_limits.items():
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) or not value for value in values)
            or len(values) != len(set(values))
        ):
            raise SourceQualityError(f"role_limits.{role} must be a unique array")
        normalized_roles[role] = tuple(values)
    if normalized_roles != EXPECTED_ROLE_LIMITS:
        raise SourceQualityError("source quality role limits changed without a version bump")

    if payload["claim_boundaries"] != EXPECTED_CLAIM_BOUNDARIES:
        raise SourceQualityError("source quality claim boundaries were weakened")

    return {
        "schema_version": "1.0",
        "status": "PASS_SOURCE_QUALITY_CONTRACT",
        "policy_id": payload["policy_id"],
        "policy_sha256": hashlib.sha256(policy_content).hexdigest(),
        "dimension_weights": weights,
        "thresholds": parsed_thresholds,
        "hard_block_count": len(EXPECTED_HARD_BLOCKS),
        "claim_boundaries": EXPECTED_CLAIM_BOUNDARIES,
    }


def assess_source_quality(
    project_root_or_path: Path | str,
    *,
    source_id: str,
    source_role: str,
    requested_fact_role: str,
    dimension_scores: Mapping[str, Any],
    failure_codes: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Route one source assessment without promoting or authorizing it."""

    path = _policy_path(project_root_or_path)
    policy, policy_content = _load_object(path, "source quality policy")
    contract = validate_source_quality_policy(path)
    if hashlib.sha256(policy_content).hexdigest() != contract["policy_sha256"]:
        raise SourceQualityError("source quality policy changed during assessment")
    if not isinstance(source_id, str) or not source_id or source_id != source_id.strip():
        raise SourceQualityError("source_id must be a canonical non-empty string")
    if source_role not in ROLE_KEYS:
        raise SourceQualityError("source_role is outside the policy")
    if not isinstance(dimension_scores, Mapping) or frozenset(dimension_scores) != frozenset(
        DIMENSION_IDS
    ):
        raise SourceQualityError("dimension_scores must cover the exact quality denominator")

    weights = contract["dimension_weights"]
    parsed_scores = {
        dimension: _unit_interval(dimension_scores[dimension], f"dimension_scores.{dimension}")
        for dimension in DIMENSION_IDS
    }
    if not isinstance(failure_codes, (list, tuple)) or any(
        not isinstance(code, str) or not code for code in failure_codes
    ):
        raise SourceQualityError("failure_codes must be unique non-empty identifiers")
    unique_failures = tuple(dict.fromkeys(failure_codes))
    if len(unique_failures) != len(failure_codes):
        raise SourceQualityError("failure_codes must be unique non-empty identifiers")

    role_limits = policy["role_limits"]
    failures = list(unique_failures)
    if requested_fact_role not in role_limits[source_role]:
        failures.append("ROLE_LIMIT_VIOLATION")
    hard_failures = sorted(set(failures) & EXPECTED_HARD_BLOCKS)
    if "ROLE_LIMIT_VIOLATION" in failures:
        hard_failures.append("ROLE_LIMIT_VIOLATION")

    score = round(
        sum(parsed_scores[dimension] * weights[dimension] for dimension in DIMENSION_IDS),
        6,
    )
    if hard_failures:
        disposition = "BLOCK"
    elif score >= contract["thresholds"]["admit"]:
        disposition = "ADMIT"
    elif score >= contract["thresholds"]["corroboration_only"]:
        disposition = "CORROBORATION_ONLY"
    else:
        disposition = "QUARANTINE"

    return {
        "schema_version": "1.0",
        "status": "QUALITY_ROUTING_ONLY",
        "source_id": source_id,
        "source_role": source_role,
        "requested_fact_role": requested_fact_role,
        "quality_score": score,
        "quality_score_is_probability": False,
        "disposition": disposition,
        "adaptive_action": policy["adaptive_actions"][disposition],
        "failure_codes": sorted(set(failures)),
        "automatic_promotion_allowed": False,
    }


__all__ = [
    "DIMENSION_IDS",
    "SourceQualityError",
    "assess_source_quality",
    "validate_source_quality_policy",
]
