"""Shared fail-closed process-exit classification for machine reports."""

from __future__ import annotations

from collections.abc import Iterable
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


def is_blocking_status(value: Any, *, known: Iterable[str] = ()) -> bool:
    """Return whether a report status must produce a non-zero process exit."""

    if not isinstance(value, str) or not value.strip():
        return False
    status = value.strip().upper()
    admitted_known = frozenset(str(item).strip().upper() for item in known)
    return (
        status in _BLOCKING_EXACT
        or status in admitted_known
        or status.startswith(_BLOCKING_PREFIXES)
        or status.endswith(_BLOCKING_SUFFIXES)
    )


__all__ = ["is_blocking_status"]
