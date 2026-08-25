"""Sanitized binding from predecessor user jobs to the canonical KU-BO core."""

from __future__ import annotations

from collections import Counter
import importlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .foundation_io import load_strict_json_object
from .market_scope import validate_market_scope


MANIFEST_PATH = Path("config/predecessor_capability_parity.json")
MIGRATION_RULES = {
    "source_repository_read_only": True,
    "git_history_merge_allowed": False,
    "second_engine_allowed": False,
    "direct_source_script_execution_allowed": False,
    "raw_private_data_copy_allowed": False,
    "source_locator_publication_allowed": False,
    "reimplementation_through_kubo_required": True,
}
CLAIM_BOUNDARIES = {
    "software_binding_proves_operational_readiness": False,
    "predecessor_claims_transfer_validation": False,
    "private_source_detail_is_public": False,
    "additional_market_support_imported": False,
    "training_authorized": False,
    "recommendations_authorized": False,
    "live_execution_authorized": False,
}
EXPECTED_BINDINGS = {
    "official_evidence_acquisition": (
        "kubo.official_foundation_import",
        "import_official_foundation",
    ),
    "user_authorized_price_import": (
        "kubo.user_price_export",
        "import_investing_user_exports",
    ),
    "semantic_source_fallback": ("kubo.source_fallback", "plan_source_fallback"),
    "source_health_validation": ("kubo.source_network", "validate_live_probe"),
    "research_candidate_ranking": ("kubo.research_rank", "rank_research_candidates"),
    "catalyst_context_deduplication": (
        "kubo.context_research",
        "deduplicate_context_events",
    ),
    "momentum_event_dataset": ("kubo.events", "canonicalize_events"),
    "portfolio_order_reconciliation": (
        "kubo.portfolio_state",
        "validate_portfolio_state",
    ),
    "training_event_admission": (
        "kubo.ku_bo_live_program",
        "validate_ku_bo_live_program",
    ),
    "factor9_admission": (
        "kubo.factor9_admission",
        "validate_factor9_admission_manifest",
    ),
    "market_regime_research": ("kubo.context_research", "build_factor_snapshot"),
    "resumable_daily_pipeline": ("kubo.live_dry_run", "run_daily_dry_run"),
    "daily_monitor_validation": ("kubo.live_dry_run", "validate_live_dry_run"),
    "backtest_evaluation": (
        "kubo.forty_session_replay",
        "evaluate_forty_session_replay",
    ),
}
EXPECTED_METADATA = {
    "official_evidence_acquisition": (
        "Import official identity and calendar evidence with provenance receipts.",
        "kubo-data-foundation import-official-foundation",
        "BOUND_TO_EXISTING_CORE",
        "EVIDENCE_IMPORT_ONLY",
    ),
    "user_authorized_price_import": (
        "Import user-authorized historical price exports without provider impersonation.",
        "kubo-data-foundation import-user-price-exports",
        "BOUND_TO_EXISTING_CORE",
        "EVIDENCE_IMPORT_ONLY",
    ),
    "semantic_source_fallback": (
        "Continue an evidence capability after transport or semantic source failure.",
        "kubo plan-source-fallback",
        "REIMPLEMENTED_IN_CANONICAL_CORE",
        "NO_NETWORK_PLANNING_ONLY",
    ),
    "source_health_validation": (
        "Distinguish source transport reachability from usable semantic evidence.",
        "kubo validate-live-probe",
        "BOUND_TO_EXISTING_CORE",
        "STRUCTURAL_VALIDATION_ONLY",
    ),
    "research_candidate_ranking": (
        "Rank research candidates only after source coverage and conflict checks.",
        None,
        "BOUND_TO_EXISTING_CORE",
        "RESEARCH_ONLY",
    ),
    "catalyst_context_deduplication": (
        "Deduplicate catalyst and context claims by evidence origin.",
        None,
        "BOUND_TO_EXISTING_CORE",
        "RESEARCH_ONLY",
    ),
    "momentum_event_dataset": (
        "Canonicalize event records for later momentum and event-study work.",
        None,
        "BOUND_TO_EXISTING_CORE",
        "DATASET_CONSTRUCTION_ONLY",
    ),
    "portfolio_order_reconciliation": (
        "Validate point-in-time portfolio and order exports against evidence bytes.",
        "kubo validate-portfolio-state",
        "REIMPLEMENTED_IN_CANONICAL_CORE",
        "STRUCTURAL_VALIDATION_ONLY",
    ),
    "training_event_admission": (
        "Validate the proposed event-development and locked-test program contract.",
        "kubo validate-ku-bo-live-program",
        "BOUND_TO_EXISTING_CORE",
        "NO_TRAINING",
    ),
    "factor9_admission": (
        "Admit Factor9 research assets only after evidence and leakage gates.",
        "kubo validate-factor9-admission",
        "BOUND_TO_EXISTING_CORE",
        "ADMISSION_ONLY",
    ),
    "market_regime_research": (
        "Build point-in-time factor snapshots for regime-oriented research.",
        None,
        "CONTRACT_BOUND_ONLY",
        "RESEARCH_ONLY",
    ),
    "resumable_daily_pipeline": (
        "Run a receipt-backed resumable daily dry-run with previous-session champion freezes.",
        "kubo run-live-dry-run",
        "BOUND_TO_EXISTING_CORE",
        "ABSTAIN_ONLY",
    ),
    "daily_monitor_validation": (
        "Revalidate a completed or interrupted dry-run from immutable receipts.",
        "kubo validate-live-dry-run",
        "BOUND_TO_EXISTING_CORE",
        "ABSTAIN_ONLY",
    ),
    "backtest_evaluation": (
        "Evaluate a sealed forty-session replay without changing its frozen decisions.",
        "kubo evaluate-forty-session-replay",
        "BOUND_TO_EXISTING_CORE",
        "EVALUATION_ONLY",
    ),
}
SOFTWARE_STATUSES = frozenset(
    {"BOUND_TO_EXISTING_CORE", "REIMPLEMENTED_IN_CANONICAL_CORE", "CONTRACT_BOUND_ONLY"}
)
OPERATIONAL_CEILINGS = frozenset(
    {
        "EVIDENCE_IMPORT_ONLY",
        "NO_NETWORK_PLANNING_ONLY",
        "STRUCTURAL_VALIDATION_ONLY",
        "RESEARCH_ONLY",
        "DATASET_CONSTRUCTION_ONLY",
        "NO_TRAINING",
        "ADMISSION_ONLY",
        "ABSTAIN_ONLY",
        "EVALUATION_ONLY",
    }
)
_PRIVATE_MARKERS = (
    "github.com/",
    "refs/heads/",
    "origin/agent/",
    "repository@sha:",
    "private-source-locator:",
)
_COMMIT_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", re.IGNORECASE)


class CapabilityParityError(ValueError):
    """Raised when sanitized parity drifts or exposes private source detail."""


def _exact(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != keys:
        raise CapabilityParityError(f"{field} has unknown or missing fields")
    return value


def _contains_private_detail(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=True, sort_keys=True).casefold()
    return any(marker in serialized for marker in _PRIVATE_MARKERS) or bool(
        _COMMIT_RE.search(serialized)
    )


def validate_predecessor_capability_parity(project_root: Path | str) -> dict[str, Any]:
    """Resolve every admitted user job to a callable in the installed KU-BO package."""

    root = Path(project_root).resolve()
    validate_market_scope(root)
    try:
        payload, _ = load_strict_json_object(
            root / MANIFEST_PATH,
            field="predecessor capability parity",
            max_bytes=512 * 1024,
        )
    except ValueError as exc:
        raise CapabilityParityError(str(exc)) from exc
    _exact(
        payload,
        frozenset(
            {
                "schema_version",
                "manifest_id",
                "source_alias",
                "target_package",
                "market_scope_id",
                "migration_rules",
                "capabilities",
                "claim_boundaries",
            }
        ),
        "capability parity manifest",
    )
    if _contains_private_detail(payload):
        raise CapabilityParityError("capability parity exposes private source detail")
    if payload.get("schema_version") != "1.0":
        raise CapabilityParityError("capability parity schema_version must be 1.0")
    if payload.get("manifest_id") != "ku-bo-private-predecessor-capability-parity-v1":
        raise CapabilityParityError("capability parity manifest_id changed")
    if payload.get("source_alias") != "PRIVATE_PREDECESSOR_SOURCE":
        raise CapabilityParityError("private predecessor must use its sanitized alias")
    if payload.get("target_package") != "kubo":
        raise CapabilityParityError("capabilities must target the canonical kubo package")
    if payload.get("market_scope_id") != "ku-bo-kuwait-only-v1":
        raise CapabilityParityError("capability parity escaped the locked market scope")
    if payload.get("migration_rules") != MIGRATION_RULES:
        raise CapabilityParityError("capability migration rules were weakened")
    if payload.get("claim_boundaries") != CLAIM_BOUNDARIES:
        raise CapabilityParityError("capability parity claim boundaries changed")

    rows = payload.get("capabilities")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_BINDINGS):
        raise CapabilityParityError("capability parity must bind all admitted user jobs")
    seen: set[str] = set()
    statuses: Counter[str] = Counter()
    ceilings: Counter[str] = Counter()
    resolved: list[str] = []
    keys = frozenset(
        {
            "capability_id",
            "user_job",
            "target_module",
            "target_callable",
            "cli_command",
            "software_status",
            "operational_ceiling",
        }
    )
    for index, raw in enumerate(rows):
        row = _exact(raw, keys, f"capabilities[{index}]")
        capability_id = row.get("capability_id")
        if not isinstance(capability_id, str) or capability_id in seen:
            raise CapabilityParityError("capability IDs must be unique strings")
        seen.add(capability_id)
        expected = EXPECTED_BINDINGS.get(capability_id)
        actual = (row.get("target_module"), row.get("target_callable"))
        if expected is None or actual != expected:
            raise CapabilityParityError(f"canonical binding drift: {capability_id}")
        status = row.get("software_status")
        ceiling = row.get("operational_ceiling")
        if status not in SOFTWARE_STATUSES or ceiling not in OPERATIONAL_CEILINGS:
            raise CapabilityParityError(f"status or ceiling is invalid: {capability_id}")
        cli_command = row.get("cli_command")
        if cli_command is not None and (
            not isinstance(cli_command, str)
            or not cli_command.startswith(("kubo ", "kubo-data-foundation "))
        ):
            raise CapabilityParityError(f"CLI binding is invalid: {capability_id}")
        metadata = (row.get("user_job"), cli_command, status, ceiling)
        if metadata != EXPECTED_METADATA.get(str(capability_id)):
            raise CapabilityParityError(f"capability metadata drift: {capability_id}")
        try:
            module = importlib.import_module(str(actual[0]))
            target = getattr(module, str(actual[1]))
        except (ImportError, AttributeError) as exc:
            raise CapabilityParityError(f"canonical callable is unresolved: {capability_id}") from exc
        if not callable(target):
            raise CapabilityParityError(f"canonical target is not callable: {capability_id}")
        statuses[str(status)] += 1
        ceilings[str(ceiling)] += 1
        resolved.append(capability_id)
    if seen != set(EXPECTED_BINDINGS):
        raise CapabilityParityError("capability parity set is incomplete")

    return {
        "schema_version": "1.0",
        "status": "PASS_SOFTWARE_PARITY_NON_OPERATIONAL",
        "manifest_id": payload["manifest_id"],
        "source_alias": payload["source_alias"],
        "target_package": payload["target_package"],
        "market_scope_id": payload["market_scope_id"],
        "capability_count": len(rows),
        "resolved_callable_count": len(resolved),
        "software_status_counts": dict(sorted(statuses.items())),
        "operational_ceiling_counts": dict(sorted(ceilings.items())),
        "private_source_details_present": False,
        "claim_boundaries": CLAIM_BOUNDARIES,
    }


__all__ = ["CapabilityParityError", "validate_predecessor_capability_parity"]
