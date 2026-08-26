"""Fail-closed validation for the repository's Codex handoff contract.

The bootstrap contract records operating intent only.  Passing this validator
does not create a live collector, a validated model, or an investment signal.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


BOOTSTRAP_CONFIG = Path("config/codex_live_bootstrap.json")
PRODUCT_CATALOG = Path("config/products.json")

EXPECTED_REPOSITORY = {
    "slug": "mohsamir7122/ku-bo",
    "single_codebase": True,
    "required_entrypoint": "CODEX_START_HERE.md",
    "active_task_file": "docs/codex/CURRENT_TASK.md",
    "merge_policy": "DRAFT_PR_ONLY_UNTIL_USER_APPROVAL",
}
EXPECTED_RUNTIME = {
    "timezone": "Asia/Kuwait",
    "primary_activation_local": "15:07",
    "watchdog_activation_local": "15:37",
    "activation_window_name": "THREE_PM_KUWAIT",
    "non_session_mode": "MAINTENANCE_ONLY",
    "scheduled_runtime_default": "DISABLED_UNTIL_AUTHORIZED",
    "manual_entry_command": (
        "python scripts/validate_codex_live_bootstrap.py --project-root ."
    ),
}
EXPECTED_DRIVE = {
    "logical_root_name": "AI Rebuild",
    "storage_class": "PRIVATE_RUNTIME_ONLY",
    "canonical_data_root": "04_Curated_Core/KU_BO",
    "private_import_root": "02_Google_Drive/KU_BO",
    "quarantine_root": "90_Quarantine_Duplicates/KU_BO",
    "report_root": "99_Reports/KU_BO",
    "required_canonical_subpaths": [
        "00_Manifests",
        "01_Factor9_Research",
        "02_Event_Evidence",
        "03_Market_Data",
        "04_Model_Freezes",
        "05_Daily_Reports",
    ],
    "unique_file_policy": "HASH_AND_PROVENANCE_BEFORE_CANONICAL_ADMISSION",
    "duplicate_policy": "QUARANTINE_BEFORE_ANY_DELETE",
    "overwrite_policy": "VERSIONED_NO_OVERWRITE",
    "repository_may_store_drive_ids": False,
    "repository_may_store_private_bytes": False,
}
EXPECTED_FACTOR9 = {
    "asset_status": "RESEARCH_ASSET_PENDING_ADMISSION",
    "promotion_ceiling": "RESEARCH_INPUT_ONLY",
    "company_master_rows": 140,
    "price_tickers": 137,
    "original_price_rows": 534135,
    "clean_price_rows": 533997,
    "excluded_price_rows": 138,
    "reported_validation_issues": 243,
    "primary_historical_price_origin": "MUBASHER_SECONDARY",
    "historical_price_rights_status": "REQUIRES_RUNTIME_REVIEW",
    "event_label_status": "OCR_AUTO_LABELS_MEDIUM_CONFIDENCE_REVIEW_REQUIRED",
    "preserve_without_recomputing": [
        "RAW_PRICE_FILES",
        "CLEAN_PRICE_FILE",
        "EXCLUDED_ROW_FILE",
        "FAILURE_LEDGER",
        "COMPANY_MASTER",
        "PRICE_FACTOR_OUTPUTS",
        "EVENT_LIBRARY",
        "REVIEW_QUEUE",
    ],
    "known_blockers": [
        "OFFICIAL_SECURITY_IDENTITY_NOT_BOUND_FOR_EVERY_ROW",
        "AUTOMATED_REUSE_RIGHTS_NOT_PROVEN",
        "CORPORATE_ACTION_ADJUSTMENT_NOT_PROVEN_COMPLETE",
        "OCR_EVENT_LABELS_NOT_OFFICIAL_TRUTH",
        "POINT_IN_TIME_AVAILABILITY_NOT_PROVEN_FOR_EVERY_EVENT",
        "FUNDAMENTAL_AND_MARKET_CAP_FIELDS_NOT_FINAL",
    ],
    "admission_gates": [
        "HASH_BOUND_DRIVE_MANIFEST",
        "RIGHTS_AND_ACCESS_REVIEW",
        "OFFICIAL_EFFECTIVE_DATED_IDENTITY",
        "RAW_CLEAN_EXCLUSION_RECONCILIATION",
        "OFFICIAL_CORPORATE_ACTION_RECONCILIATION",
        "EVENT_LABEL_HUMAN_OR_OFFICIAL_REVIEW",
        "POINT_IN_TIME_TIMESTAMP_RECONCILIATION",
    ],
}
EXPECTED_EVENT_TRAINING = {
    "development_major_events": 50,
    "development_control_events": 200,
    "default_training_rounds": 30,
    "maximum_training_rounds": 50,
    "extra_round_requires_preregistered_hypothesis": True,
    "development_events_allowed_in_regression_replay": True,
    "locked_test_minimum_events": 500,
    "locked_test_maximum_events": 600,
    "locked_test_may_overlap_development": False,
    "split_policy": "PURGED_EMBARGOED_WALK_FORWARD",
    "control_matching": [
        "SECTOR",
        "LIQUIDITY",
        "VOLATILITY",
        "MARKET_REGIME",
        "ELIGIBILITY_DATE",
    ],
    "missing_data_policy": "RECOVER_THEN_PROXY_FLAG_THEN_ABSTAIN",
    "trial_registry_required": True,
}
EXPECTED_STAGES = [
    "VERIFY_SESSION_AND_ACQUIRE_RUN_LOCK",
    "PROBE_AUTHORIZED_SOURCE_ACCESS",
    "COLLECT_AND_HASH_RAW_EVIDENCE",
    "VALIDATE_AND_NORMALIZE_POINT_IN_TIME",
    "BUILD_EVENT_AND_FACTOR_SNAPSHOT",
    "RUN_PREVIOUS_APPROVED_CHAMPION",
    "SEAL_DAILY_RESEARCH_OUTPUT",
    "MATURE_AND_SCORE_PRIOR_OUTCOMES",
    "TRAIN_CHALLENGERS",
    "EMIT_DRAFT_CHANGE_PROPOSALS",
]
EXPECTED_PRODUCTS = [
    {"product_id": "three_session_rank", "horizon_sessions": 3},
    {"product_id": "five_session_weekly_swing", "horizon_sessions": 5},
    {"product_id": "twenty_one_session_monthly_swing", "horizon_sessions": 21},
    {"product_id": "sixty_three_session_quarter_rank", "horizon_sessions": 63},
]
EXPECTED_DAILY_SCALARS = {
    "champion_policy": "PREVIOUS_APPROVED_FREEZE_ONLY",
    "challenger_same_day_output_allowed": False,
    "champion_freeze_path": (
        "AI Rebuild/04_Curated_Core/KU_BO/04_Model_Freezes"
    ),
    "daily_report_path": "AI Rebuild/04_Curated_Core/KU_BO/05_Daily_Reports",
    "code_change_policy": "TASK_BRANCH_TESTS_DRAFT_PR_NO_AUTO_MERGE",
    "model_promotion_policy": (
        "PROMOTE_ONLY_AFTER_LOCKED_VALIDATION_AND_PROSPECTIVE_GATES"
    ),
}
EXPECTED_ALLOWED_DECISIONS = ["RESEARCH_CANDIDATE", "WATCH", "ABSTAIN"]
EXPECTED_SOURCE_ROLES = {
    "official_truth": ["BOURSA_KUWAIT", "CMA_IFSAH", "ISSUER"],
    "secondary_research": [
        "INVESTING_AUTHORIZED_EXPORT",
        "MUBASHER_REVIEWED_SECONDARY",
        "REUTERS_OR_LOCAL_NEWS",
    ],
    "community_routing_only": [
        "TELEGRAM_AUTHORIZED_EXPORT",
        "INDEXSIGNAL_AUTHORIZED_EXPORT",
    ],
    "private_storage_only": ["GOOGLE_DRIVE_AI_REBUILD"],
    "execution_required": ["LICENSED_FEED_OR_BROKER_EXPORT"],
}
EXPECTED_CLAIM_BOUNDARIES = {
    "bootstrap_is_live_runtime": False,
    "drive_presence_grants_data_rights": False,
    "factor9_is_training_truth": False,
    "factor9_is_validated_model": False,
    "challenger_may_issue_same_day_output": False,
    "scheduled_time_is_exactly_guaranteed": False,
    "automatic_code_merge_allowed": False,
    "research_candidate_is_buy_recommendation": False,
    "delayed_public_price_is_execution_quote": False,
    "structural_test_proves_predictive_skill": False,
}

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "mission_id",
        "mission_status",
        "repository",
        "runtime",
        "drive",
        "factor9",
        "event_training",
        "daily_runtime",
        "source_roles",
        "claim_boundaries",
    }
)


class CodexBootstrapError(ValueError):
    """Raised when the Codex bootstrap contract has been weakened or forged."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CodexBootstrapError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise CodexBootstrapError(f"non-finite JSON value is forbidden: {value}")


def _load_strict_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CodexBootstrapError(f"cannot load strict JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CodexBootstrapError(f"JSON root must be an object: {path}")
    return payload


def _exact_keys(value: Any, expected: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CodexBootstrapError(f"{field} must be an object")
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise CodexBootstrapError(
            f"{field} has missing={missing} unknown={unknown}"
        )
    return value


def _require_exact(value: Any, expected: Any, field: str) -> None:
    if value != expected:
        raise CodexBootstrapError(f"{field} does not match the locked contract")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _catalog_product_map(path: Path) -> dict[str, int]:
    catalog = _load_strict_json(path)
    _exact_keys(
        catalog,
        frozenset({"catalog_version", "timezone", "products"}),
        "product catalog",
    )
    if catalog["timezone"] != "Asia/Kuwait":
        raise CodexBootstrapError("product catalog timezone must be Asia/Kuwait")
    products = catalog["products"]
    if not isinstance(products, list) or not products:
        raise CodexBootstrapError("product catalog products must be a non-empty list")
    result: dict[str, int] = {}
    for index, row in enumerate(products):
        if not isinstance(row, Mapping):
            raise CodexBootstrapError(f"products[{index}] must be an object")
        product_id = row.get("product_id")
        horizon = row.get("horizon_sessions")
        if not isinstance(product_id, str) or not product_id:
            raise CodexBootstrapError(f"products[{index}].product_id is invalid")
        if product_id in result:
            raise CodexBootstrapError(f"duplicate product_id: {product_id}")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
            raise CodexBootstrapError(f"products[{index}].horizon_sessions is invalid")
        result[product_id] = horizon
    return result


def _validate_no_private_drive_locator(payload: Mapping[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True).lower()
    forbidden_fragments = (
        "drive.google.com",
        "docs.google.com",
        "?id=",
        "/folders/",
        "/file/d/",
        "oauth",
        "access_token",
        "refresh_token",
        "cookie",
        "sessionid",
    )
    found = [fragment for fragment in forbidden_fragments if fragment in serialized]
    if found:
        raise CodexBootstrapError(
            "bootstrap config must not contain private Drive locators or credentials: "
            + ",".join(found)
        )


def validate_codex_live_bootstrap(
    project_root: Path | str,
    *,
    config_path: Path | str | None = None,
) -> dict[str, Any]:
    """Validate the frozen Codex operating contract and return a bounded report."""

    root = Path(project_root).resolve()
    path = (
        Path(config_path).resolve()
        if config_path is not None
        else root / BOOTSTRAP_CONFIG
    )
    payload = _load_strict_json(path)
    _exact_keys(payload, _ROOT_KEYS, "bootstrap")
    _require_exact(payload["schema_version"], "1.0", "schema_version")
    _require_exact(payload["mission_id"], "ku-bo-live-adaptive-v4", "mission_id")
    _require_exact(
        payload["mission_status"],
        "READY_FOR_CODEX_EXECUTION",
        "mission_status",
    )
    _require_exact(payload["repository"], EXPECTED_REPOSITORY, "repository")
    _require_exact(payload["runtime"], EXPECTED_RUNTIME, "runtime")
    _require_exact(payload["drive"], EXPECTED_DRIVE, "drive")
    _require_exact(payload["factor9"], EXPECTED_FACTOR9, "factor9")
    _require_exact(
        payload["event_training"], EXPECTED_EVENT_TRAINING, "event_training"
    )
    _require_exact(payload["source_roles"], EXPECTED_SOURCE_ROLES, "source_roles")
    _require_exact(
        payload["claim_boundaries"],
        EXPECTED_CLAIM_BOUNDARIES,
        "claim_boundaries",
    )

    daily = _exact_keys(
        payload["daily_runtime"],
        frozenset(
            {
                "champion_policy",
                "challenger_same_day_output_allowed",
                "champion_freeze_path",
                "daily_report_path",
                "stages",
                "products",
                "allowed_decisions",
                "code_change_policy",
                "model_promotion_policy",
            }
        ),
        "daily_runtime",
    )
    for field, expected in EXPECTED_DAILY_SCALARS.items():
        _require_exact(daily[field], expected, f"daily_runtime.{field}")
    _require_exact(daily["stages"], EXPECTED_STAGES, "daily_runtime.stages")
    _require_exact(daily["products"], EXPECTED_PRODUCTS, "daily_runtime.products")
    _require_exact(
        daily["allowed_decisions"],
        EXPECTED_ALLOWED_DECISIONS,
        "daily_runtime.allowed_decisions",
    )

    factor9 = payload["factor9"]
    if factor9["original_price_rows"] - factor9["clean_price_rows"] != factor9[
        "excluded_price_rows"
    ]:
        raise CodexBootstrapError("Factor 9 raw/clean/excluded counts do not reconcile")
    if factor9["price_tickers"] > factor9["company_master_rows"]:
        raise CodexBootstrapError("Factor 9 ticker count exceeds the company master")

    training = payload["event_training"]
    if training["default_training_rounds"] > training["maximum_training_rounds"]:
        raise CodexBootstrapError("default training rounds exceed the maximum")
    if training["locked_test_minimum_events"] > training["locked_test_maximum_events"]:
        raise CodexBootstrapError("locked-test bounds are inverted")
    if training["locked_test_may_overlap_development"]:
        raise CodexBootstrapError("locked test must remain disjoint from development")

    catalog_products = _catalog_product_map(root / PRODUCT_CATALOG)
    for row in EXPECTED_PRODUCTS:
        if catalog_products.get(row["product_id"]) != row["horizon_sessions"]:
            raise CodexBootstrapError(
                f"bootstrap product is not bound to product catalog: {row['product_id']}"
            )

    for relative in (
        EXPECTED_REPOSITORY["required_entrypoint"],
        EXPECTED_REPOSITORY["active_task_file"],
    ):
        referenced = root / relative
        if not referenced.is_file():
            raise CodexBootstrapError(f"required control file is missing: {relative}")

    _validate_no_private_drive_locator(payload)
    return {
        "schema_version": "1.0",
        "status": "PASS_HANDOFF_CONTRACT",
        "mission_id": payload["mission_id"],
        "mission_status": payload["mission_status"],
        "config_sha256": _sha256(path),
        "timezone": EXPECTED_RUNTIME["timezone"],
        "activation_local": EXPECTED_RUNTIME["primary_activation_local"],
        "watchdog_local": EXPECTED_RUNTIME["watchdog_activation_local"],
        "live_runtime_status": "NOT_IMPLEMENTED",
        "scheduled_runtime_status": "DISABLED_UNTIL_AUTHORIZED",
        "factor9_status": EXPECTED_FACTOR9["asset_status"],
        "factor9_admission_gate_count": len(EXPECTED_FACTOR9["admission_gates"]),
        "development_event_count": (
            EXPECTED_EVENT_TRAINING["development_major_events"]
            + EXPECTED_EVENT_TRAINING["development_control_events"]
        ),
        "locked_test_range": [
            EXPECTED_EVENT_TRAINING["locked_test_minimum_events"],
            EXPECTED_EVENT_TRAINING["locked_test_maximum_events"],
        ],
        "daily_stage_count": len(EXPECTED_STAGES),
        "products": EXPECTED_PRODUCTS,
        "claim_boundaries": EXPECTED_CLAIM_BOUNDARIES,
    }


__all__ = [
    "BOOTSTRAP_CONFIG",
    "CodexBootstrapError",
    "EXPECTED_CLAIM_BOUNDARIES",
    "EXPECTED_PRODUCTS",
    "validate_codex_live_bootstrap",
]
