"""Shared fail-closed process-exit classification for machine reports."""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any


_BLOCKING_PREFIXES = (
    "BLOCKED",
    "DEGRADED",
    "ERROR",
    "FAILED",
    "FAIL_",
    "PARTIAL",
    "RETRYABLE_",
    "STOP_",
)
_BLOCKING_SUFFIXES = (
    "_ABSTAIN",
    "_BLOCKED",
    "_FAILED",
    "_NOT_READY",
    "_PARTIAL",
    "_PENDING_ADMISSION",
    "_REQUIRED",
    "_UNBOUND",
    "_UNREACHABLE",
    "_UNSATISFIED",
)
_BLOCKING_EXACT = frozenset(
    {
        "BLOCKED",
        "DRY_RUN_BLOCKED",
        "FAIL",
        "FAILED",
        "NO_TRADE",
        "ROBOTS_UNREACHABLE",
        "SECURITY_BLOCK",
    }
)
_NON_BLOCKING_EXACT = frozenset(
    {
        "ALL_SECURITIES_TERMINAL_NO_SOURCE_GAPS",
        "ALL_SECURITIES_TERMINAL_WITH_EXPLICIT_GAPS",
        "BENCHMARK_HISTORY_READY",
        "CAPABILITY_EVIDENCE_AVAILABLE",
        "CAPABILITY_VERIFIED_ZERO_RESULT",
        "CA_ENRICHMENT_READY",
        "CA_ENRICHMENT_ZERO_RESULT_READY",
        "CA_REFERENCE_FACTORS_READY_RETURN_POLICY_PENDING",
        "COMPLETE",
        "CONFIGURED_FOR_WORKSPACE_PREPARATION",
        "CONTRACT_INTEGRATED",
        "CONTRACT_INTEGRATED_WITH_SOURCE_LIMITATIONS",
        "CURRENT_IDENTITY_AND_CALENDAR_READY",
        "CURRENT_STATUS_AND_CA_SCHEDULE_READY",
        "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY",
        "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST",
        "DRY_RUN_COMPLETE_NO_RECOMMENDATION",
        "HISTORICAL_STATUS_INTERVALS_READY",
        "OFFICIAL_COMPLETE_EOD_READY",
        "PASS",
        "PASS_ACCESS_ONLY",
        "PASS_BACKGROUND_OCCURRENCE_RESOLUTION",
        "PASS_BACKTEST",
        "PASS_COMPLETED_OUTPUT_VERIFICATION",
        "PASS_CONTRACT",
        "PASS_CONTRACT_CHECK",
        "PASS_CONTRACT_NOT_EXECUTED",
        "PASS_CONTRACT_ONLY_NO_NETWORK",
        "PASS_DISABLED_PROGRAM_CONTRACT",
        "PASS_FAIL_CLOSED_BACKFILL_POLICY",
        "PASS_FAIL_CLOSED_PRIORITY_POLICY",
        "PASS_FAIL_CLOSED_RECOVERY_POLICY",
        "PASS_HANDOFF_CONTRACT",
        "PASS_INCOMPLETE_RIGHTS_AWARE_BUNDLE",
        "PASS_KUWAIT_ONLY_MARKET_SCOPE",
        "PASS_PLAN_NOT_EXECUTED",
        "PASS_PREVIOUS_FREEZE_ONLY",
        "PASS_RUN_RECEIPT_INTERNAL_CONSISTENCY_ONLY",
        "PASS_SCHEDULE_CONTRACT",
        "PASS_SOFTWARE_PARITY_NON_OPERATIONAL",
        "PASS_SOURCE_QUALITY_CONTRACT",
        "PASS_TRUSTED_SOURCE_REGISTRY",
        "PLANNED_NOT_EXECUTED",
        "RESEARCH_NETWORK_COMPLETE",
        "RESEARCH_PRICE_HISTORY_READY",
        "RESEARCH_READY",
        "RESOLVED_BY_UNIQUE_AUTHORITATIVE_VALUE",
        "STRUCTURE_AND_RECONCILIATION_VALID_ONLY",
        "STRUCTURE_VALID_ONLY",
        "STRUCTURE_VALID_ONLY_WITH_EXPLICIT_GAPS",
    }
)
_STATUS_RE = re.compile(r"[A-Z][A-Z0-9_]{0,127}")


def is_blocking_status(value: Any, *, known: Iterable[str] = ()) -> bool:
    """Return whether a report status must produce a non-zero process exit."""

    if not isinstance(value, str) or _STATUS_RE.fullmatch(value) is None:
        return True
    status = value
    admitted_known = frozenset(str(item).strip().upper() for item in known)
    explicitly_blocked = (
        status in _BLOCKING_EXACT
        or status in admitted_known
        or status.startswith(_BLOCKING_PREFIXES)
        or status.endswith(_BLOCKING_SUFFIXES)
    )
    return explicitly_blocked or status not in _NON_BLOCKING_EXACT


__all__ = ["is_blocking_status"]
