"""Validate the requested KU-BO private research timetable as a disabled contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .codex_live_bootstrap import EXPECTED_PRODUCTS
from .foundation_io import load_strict_json_object


PROGRAM_PATH = Path("config/ku_bo_live_program.json")
TASK_018_PATH = Path("config/ku_bo_018_event_admission_task.json")
EXPECTED_RESEARCH_CYCLES = [
    {"cycle_id": "morning-research", "start_local": "08:00", "target_local": "10:00"},
    {"cycle_id": "midday-refresh", "start_local": "10:00", "target_local": "12:00"},
]
EXPECTED_IMPROVEMENT_CYCLES = [
    {"cycle_id": "evening-evaluation", "start_local": "18:00"},
    {"cycle_id": "midnight-evaluation", "start_local": "00:00"},
]
EXPECTED_GATES = [
    "AUTHORIZED_SOURCE_ACCESS",
    "OFFICIAL_POINT_IN_TIME_DATA",
    "FACTOR9_ADMISSION",
    "APPROVED_PREVIOUS_SESSION_CHAMPION",
    "LOCKED_MODEL_VALIDATION",
    "PROSPECTIVE_VALIDATION",
    "DELIVERY_AUTHORIZATION",
]
EXPECTED_RESEARCH_VIEWS = [
    "SHORT_HORIZON_CANDIDATES",
    "MEDIUM_HORIZON_CANDIDATES",
    "LONG_TERM_RESEARCH_CANDIDATES",
    "NEAR_BOTTOM_REVIEW_QUEUE",
]
EXPECTED_TASK_018_ARTIFACTS = [
    "EVENT_EVIDENCE_MANIFEST",
    "CONTROL_MATCHING_REPORT",
    "POINT_IN_TIME_REVIEW",
    "TRIAL_REGISTRY",
    "LOCKED_TEST_SEAL",
]
EXPECTED_TASK_018_BOUNDARIES = {
    "task_started": False,
    "training_allowed": False,
    "locked_test_visible_to_development": False,
    "accuracy_claim_allowed": False,
    "recommendation_allowed": False,
}
EXPECTED_BOUNDARIES = {
    "schedule_enabled": False,
    "live_collection_enabled": False,
    "model_training_enabled": False,
    "same_day_challenger_output_allowed": False,
    "entry_exit_quotes_allowed": False,
    "buy_sell_recommendations_allowed": False,
    "automatic_merge_allowed": False,
    "email_delivery_guaranteed": False,
}
ROOT_KEYS = frozenset(
    {
        "schema_version",
        "program_id",
        "status",
        "timezone",
        "research_cycles",
        "improvement_cycles",
        "existing_shadow_contract",
        "products",
        "research_views",
        "delivery",
        "required_gates",
        "claim_boundaries",
    }
)


class LiveProgramError(ValueError):
    """Raised when the requested operating contract would enable unsafe behavior."""


def _load(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    try:
        return load_strict_json_object(
            path,
            field=field,
            max_bytes=4 * 1024 * 1024,
        )
    except ValueError as exc:
        raise LiveProgramError(f"cannot load strict {field}: {path}") from exc


def _exact(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveProgramError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise LiveProgramError(
            f"{field} has missing={sorted(keys - actual)} unknown={sorted(actual - keys)}"
        )
    return value


def _validate_task_018(path: Path) -> dict[str, Any]:
    task, _ = _load(path, "KU-BO-018 task")
    expected_keys = frozenset(
        {
            "schema_version",
            "task_id",
            "status",
            "mission",
            "development_set",
            "locked_test",
            "training",
            "required_artifacts",
            "claim_boundaries",
        }
    )
    _exact(task, expected_keys, "KU-BO-018 task")
    if task["schema_version"] != "1.0" or task["task_id"] != "KU-BO-018":
        raise LiveProgramError("unexpected KU-BO-018 task identity")
    if task["status"] != "PROPOSED_NOT_STARTED":
        raise LiveProgramError("KU-BO-018 must remain proposed and not started")
    if task["mission"] != "EVENT_ADMISSION_AND_TRIAL_REGISTRY":
        raise LiveProgramError("KU-BO-018 mission changed")
    if task["development_set"] != {
        "major_events": 50,
        "control_events": 200,
        "locked_test_overlap_allowed": False,
    }:
        raise LiveProgramError("KU-BO-018 development denominator changed")
    if task["locked_test"] != {
        "minimum_events": 500,
        "maximum_events": 600,
        "split_policy": "PURGED_EMBARGOED_WALK_FORWARD",
    }:
        raise LiveProgramError("KU-BO-018 locked test contract changed")
    if task["training"] != {
        "default_rounds": 30,
        "maximum_rounds": 50,
        "rounds_above_default_require_preregistered_hypothesis": True,
        "allowed_in_task": False,
    }:
        raise LiveProgramError("KU-BO-018 training boundary changed")
    if task["required_artifacts"] != EXPECTED_TASK_018_ARTIFACTS:
        raise LiveProgramError("KU-BO-018 required artifacts changed")
    if task["claim_boundaries"] != EXPECTED_TASK_018_BOUNDARIES:
        raise LiveProgramError("KU-BO-018 claim boundaries were weakened")
    return task


def validate_ku_bo_live_program(project_root: Path | str) -> dict[str, Any]:
    """Validate the requested schedule without activating any runtime."""

    root = Path(project_root)
    program_path = root / PROGRAM_PATH
    payload, program_content = _load(program_path, "KU-BO live program")
    _exact(payload, ROOT_KEYS, "KU-BO live program")
    if payload["schema_version"] != "1.0":
        raise LiveProgramError("unsupported KU-BO live program schema")
    if payload["program_id"] != "ku-bo-moh-adaptive-research-v1":
        raise LiveProgramError("unexpected KU-BO live program id")
    if payload["status"] != "DISABLED_UNTIL_AUTHORIZED_AND_GATED":
        raise LiveProgramError("KU-BO live program must remain disabled")
    if payload["timezone"] != "Asia/Kuwait":
        raise LiveProgramError("KU-BO live program timezone must be Asia/Kuwait")
    if payload["research_cycles"] != EXPECTED_RESEARCH_CYCLES:
        raise LiveProgramError("research cycle times differ from the recorded user request")
    if payload["improvement_cycles"] != EXPECTED_IMPROVEMENT_CYCLES:
        raise LiveProgramError("improvement cycle times differ from the recorded user request")
    if payload["existing_shadow_contract"] != {
        "primary_local": "15:07",
        "watchdog_local": "15:37",
        "status": "DISABLED_CONTRACT_ONLY",
    }:
        raise LiveProgramError("existing shadow contract was enabled or changed")
    if payload["products"] != EXPECTED_PRODUCTS:
        raise LiveProgramError("live program products differ from the locked bootstrap")
    if payload["research_views"] != EXPECTED_RESEARCH_VIEWS:
        raise LiveProgramError("live program research views changed")
    if payload["required_gates"] != EXPECTED_GATES:
        raise LiveProgramError("live program required gates were weakened or reordered")
    if payload["claim_boundaries"] != EXPECTED_BOUNDARIES:
        raise LiveProgramError("live program claim boundaries were weakened")
    if payload["delivery"] != {
        "drive_logical_folder": "PRIVATE_REPORT_DESTINATION",
        "email_mode": "SEALED_RESULT_OR_BLOCKER_NOTICE",
        "recipient_resolution": "AUTHORIZED_RUNTIME_ACCOUNT",
    }:
        raise LiveProgramError("live program delivery contract changed")

    product_catalog, _ = _load(root / "config/products.json", "product catalog")
    catalog_products = {
        row.get("product_id"): row.get("horizon_sessions")
        for row in product_catalog.get("products", [])
        if isinstance(row, Mapping)
    }
    for row in EXPECTED_PRODUCTS:
        if catalog_products.get(row["product_id"]) != row["horizon_sessions"]:
            raise LiveProgramError(
                f"product catalog mismatch for {row['product_id']}"
            )

    task = _validate_task_018(root / TASK_018_PATH)
    return {
        "schema_version": "1.0",
        "status": "PASS_DISABLED_PROGRAM_CONTRACT",
        "program_id": payload["program_id"],
        "program_sha256": hashlib.sha256(program_content).hexdigest(),
        "timezone": payload["timezone"],
        "research_cycles": payload["research_cycles"],
        "improvement_cycles": payload["improvement_cycles"],
        "products": payload["products"],
        "task_018_status": task["status"],
        "required_gate_count": len(EXPECTED_GATES),
        "claim_boundaries": EXPECTED_BOUNDARIES,
    }


__all__ = ["LiveProgramError", "validate_ku_bo_live_program"]
