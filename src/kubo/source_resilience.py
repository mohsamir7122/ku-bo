"""Bounded, fail-closed source adapter resilience primitives.

The controller is intentionally in-memory for one collection run.  It never
waits for a circuit to close on the critical path: callers record the circuit
and immediately continue with the next registered source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
from typing import Any

from .hashing import canonical_json_bytes
from .strict import parse_aware


TRANSIENT_SOURCE_ERRORS = frozenset(
    {
        "CONNECTOR_INTERNAL_ERROR",
        "HTTP_DNS_ERROR",
        "HTTP_SERVER_ERROR",
        "HTTP_TIMEOUT",
        "HTTP_TRANSPORT_ERROR",
        "ROBOTS_DNS_ERROR",
        "ROBOTS_UNREACHABLE",
    }
)
RATE_LIMIT_ERRORS = frozenset({"HTTP_RATE_LIMITED"})
HARD_BLOCK_ERRORS = frozenset(
    {
        "AUTH_REQUIRED_PAGE",
        "CAPTCHA_DETECTED",
        "HTTP_AUTH_REQUIRED",
        "HTTP_FORBIDDEN",
        "MISSING_SECRET",
        "PAYWALL_DETECTED",
        "ROBOTS_DISALLOWED",
        "ROBOTS_POLICY_UNAVAILABLE",
        "ROBOTS_POLICY_TOO_LARGE",
        "ROBOTS_REDIRECT_BLOCKED",
        "ROBOTS_REDIRECT_OUTSIDE_ALLOWLIST",
        "TERMS_NOT_PERMITTED",
        "TERMS_REVIEW_REQUIRED",
        "TOS_NOT_PERMITTED",
        "TOS_REVIEW_REQUIRED",
    }
)
QUARANTINE_ERRORS = frozenset(
    {
        "PARSER_DRIFT",
        "PARSER_SCHEMA_FAILURE",
        "SCHEMA_VALIDATION_FAILED",
    }
)
ADAPTER_STATES = frozenset({"ACTIVE", "CIRCUIT_OPEN", "DISABLED", "QUARANTINED"})


class SourceResilienceError(ValueError):
    """Raised when retry state could permit an unbounded or duplicate attempt."""


def _utc(value: datetime | str, field: str) -> datetime:
    parsed = value if isinstance(value, datetime) else parse_aware(value, field)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceResilienceError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def source_failure_fingerprint(
    *, source_id: str, error_code: str, registrable_domain: str, stage: str = "COLLECTION"
) -> str:
    material = {
        "market": "KUWAIT",
        "stage": str(stage).strip().upper(),
        "source_id": str(source_id).strip().casefold(),
        "registrable_domain": str(registrable_domain).strip().casefold(),
        "error_code": str(error_code or "UNKNOWN_SOURCE_FAILURE").strip().upper(),
    }
    if any(not value for value in material.values()):
        raise SourceResilienceError("source failure fingerprint fields must be non-empty")
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def source_attempt_idempotency_key(
    *,
    run_id: str,
    event_type: str,
    source_id: str,
    route_id: str,
    strategy_id: str,
    attempt_ordinal: int,
    requested_url: str,
    window_from: str,
    window_to: str,
) -> str:
    if isinstance(attempt_ordinal, bool) or not isinstance(attempt_ordinal, int) or attempt_ordinal < 1:
        raise SourceResilienceError("attempt_ordinal must be a positive integer")
    material = {
        "run_id": str(run_id).strip(),
        "event_type": str(event_type).strip(),
        "source_id": str(source_id).strip(),
        "route_id": str(route_id).strip(),
        "strategy_id": str(strategy_id).strip(),
        "attempt_ordinal": attempt_ordinal,
        "requested_url": str(requested_url).strip(),
        "window_from": str(window_from).strip(),
        "window_to": str(window_to).strip(),
    }
    if any(value == "" for key, value in material.items() if key != "attempt_ordinal"):
        raise SourceResilienceError("idempotency key fields must be non-empty")
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def classify_source_result(result: Any) -> str:
    """Classify a capture result without trusting a caller-supplied category."""

    code = str(getattr(result, "error_code", "") or "").strip().upper()
    state = str(getattr(result, "state", "") or "").strip().upper()
    query_status = str(getattr(result, "query_status", "") or "").strip().upper()
    flags = {str(item).strip().upper() for item in getattr(result, "data_quality_flags", ())}
    if code in RATE_LIMIT_ERRORS:
        return "RATE_LIMITED"
    if code in QUARANTINE_ERRORS or query_status == "PARSER_DRIFT" or bool(
        flags & QUARANTINE_ERRORS
    ):
        return "QUARANTINE"
    if code in HARD_BLOCK_ERRORS or state in {"BLOCKED", "AUTH_REQUIRED"}:
        return "HARD_BLOCK"
    if code in TRANSIENT_SOURCE_ERRORS and state == "ERROR":
        return "TRANSIENT"
    return "NONE"


@dataclass(frozen=True)
class SourceCircuit:
    source_id: str
    state: str
    failure_fingerprint: str
    reason: str
    opened_at: str
    retry_after_at: str | None
    attempt_count: int
    attempt_budget: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceResilienceController:
    """Track one-run idempotency, attempt budgets, and adapter circuits."""

    def __init__(
        self,
        *,
        max_attempts: int = 2,
        transient_circuit_seconds: float = 30.0,
        missing_retry_after_seconds: float = 300.0,
    ) -> None:
        if max_attempts != 2:
            raise SourceResilienceError("source attempt budget must remain exactly two")
        for field, value in (
            ("transient_circuit_seconds", transient_circuit_seconds),
            ("missing_retry_after_seconds", missing_retry_after_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value <= 0:
                raise SourceResilienceError(f"{field} must be a positive finite number")
        self.max_attempts = max_attempts
        self.transient_circuit_seconds = float(transient_circuit_seconds)
        self.missing_retry_after_seconds = float(missing_retry_after_seconds)
        self._idempotency_keys: set[str] = set()
        self._circuits: dict[str, SourceCircuit] = {}

    def reserve(self, idempotency_key: str, *, attempt_ordinal: int) -> None:
        key = str(idempotency_key)
        if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
            raise SourceResilienceError("idempotency_key must be a lowercase SHA-256")
        if attempt_ordinal < 1 or attempt_ordinal > self.max_attempts:
            raise SourceResilienceError("source attempt budget exhausted")
        if key in self._idempotency_keys:
            raise SourceResilienceError("duplicate source attempt idempotency key")
        self._idempotency_keys.add(key)

    def open_circuit(
        self,
        *,
        source_id: str,
        error_code: str,
        registrable_domain: str,
        classification: str,
        opened_at: datetime | str,
        attempt_count: int,
        retry_after_seconds: float | None = None,
    ) -> SourceCircuit:
        if attempt_count < 1 or attempt_count > self.max_attempts:
            raise SourceResilienceError("circuit attempt_count is outside its budget")
        current = _utc(opened_at, "opened_at")
        if classification == "RATE_LIMITED":
            delay = self.missing_retry_after_seconds if retry_after_seconds is None else retry_after_seconds
            if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not math.isfinite(float(delay)) or float(delay) < 0:
                raise SourceResilienceError("Retry-After must be a non-negative finite number")
            state = "CIRCUIT_OPEN"
            retry_at = current + timedelta(seconds=float(delay))
        elif classification == "TRANSIENT":
            state = "CIRCUIT_OPEN"
            retry_at = current + timedelta(seconds=self.transient_circuit_seconds)
        elif classification == "HARD_BLOCK":
            state = "DISABLED"
            retry_at = None
        elif classification == "QUARANTINE":
            state = "QUARANTINED"
            retry_at = None
        else:
            raise SourceResilienceError("only failures may open or disable an adapter")
        fingerprint = source_failure_fingerprint(
            source_id=source_id,
            error_code=error_code,
            registrable_domain=registrable_domain,
        )
        record = SourceCircuit(
            source_id=str(source_id),
            state=state,
            failure_fingerprint=fingerprint,
            reason=str(error_code or classification),
            opened_at=current.isoformat().replace("+00:00", "Z"),
            retry_after_at=(
                retry_at.isoformat().replace("+00:00", "Z") if retry_at is not None else None
            ),
            attempt_count=attempt_count,
            attempt_budget=self.max_attempts,
        )
        self._circuits[str(source_id)] = record
        return record

    def adapter_available(self, source_id: str) -> bool:
        return str(source_id) not in self._circuits

    def circuit(self, source_id: str) -> SourceCircuit | None:
        return self._circuits.get(str(source_id))

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._circuits[key].to_dict() for key in sorted(self._circuits))


__all__ = [
    "ADAPTER_STATES",
    "HARD_BLOCK_ERRORS",
    "QUARANTINE_ERRORS",
    "RATE_LIMIT_ERRORS",
    "SourceCircuit",
    "SourceResilienceController",
    "SourceResilienceError",
    "TRANSIENT_SOURCE_ERRORS",
    "classify_source_result",
    "source_attempt_idempotency_key",
    "source_failure_fingerprint",
]
