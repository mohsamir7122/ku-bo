from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capabilities import AUTHORIZED_ACCESS
from .strict import finite_number, parse_aware, require_sha256


@dataclass(frozen=True)
class ExecutionAssessment:
    status: str
    reason_codes: tuple[str, ...]
    age_minutes: float | None
    feed_access: str


def assess_execution(snapshot: dict[str, Any], *, decision_at: str, manifest_hashes: frozenset[str], max_age_minutes: float = 2.0) -> ExecutionAssessment:
    reasons: list[str] = []
    feed_access = str(snapshot.get("feed_access", "")).upper()
    if feed_access not in AUTHORIZED_ACCESS:
        reasons.append("EXECUTION_FEED_NOT_AUTHORIZED")
    if not str(snapshot.get("entitlement_id", "")).strip():
        reasons.append("MISSING_FEED_ENTITLEMENT_ID")
    try:
        evidence_hash = require_sha256(snapshot.get("raw_sha256"), "raw_sha256")
        if evidence_hash not in manifest_hashes:
            reasons.append("EXECUTION_EVIDENCE_UNRESOLVED")
    except ValueError:
        reasons.append("EXECUTION_EVIDENCE_UNRESOLVED")
    age: float | None = None
    try:
        decision = parse_aware(decision_at, "decision_at")
        observed = parse_aware(snapshot.get("observed_at"), "observed_at")
        provider = parse_aware(snapshot.get("provider_as_of"), "provider_as_of")
        if provider > observed or observed > decision:
            reasons.append("EXECUTION_TIMESTAMP_ORDER")
        age = (decision - provider).total_seconds() / 60
        declared = finite_number(snapshot.get("delay_minutes"), "delay_minutes", minimum=0)
        measured = (observed - provider).total_seconds() / 60
        if abs(declared - measured) > 1:
            reasons.append("DELAY_DECLARATION_MISMATCH")
        if age < 0 or age > max_age_minutes:
            reasons.append("STALE_OR_FUTURE_EXECUTION_SNAPSHOT")
    except ValueError:
        reasons.append("INVALID_EXECUTION_TIMESTAMPS")
    if str(snapshot.get("market_phase", "")).upper() not in {"OPENING_AUCTION", "CONTINUOUS", "CLOSING_AUCTION", "TRADE_AT_LAST"}:
        reasons.append("NON_EXECUTABLE_MARKET_PHASE")
    trading_status = str(snapshot.get("trading_status", "")).upper()
    if trading_status != "TRADED":
        reasons.append(f"TRADING_STATUS_{trading_status or 'UNKNOWN'}")
    try:
        bid = finite_number(snapshot.get("bid_fils"), "bid_fils", minimum=0.001)
        ask = finite_number(snapshot.get("ask_fils"), "ask_fils", minimum=0.001)
        reference = finite_number(snapshot.get("reference_price_fils"), "reference_price_fils", minimum=0.001)
        if ask < bid:
            reasons.append("CROSSED_QUOTE")
        if ask / reference >= 1.10 - 1e-12:
            reasons.append("UPPER_LIMIT_QUEUE_OR_CENSORING")
        if bid / reference <= 0.95 + 1e-12:
            reasons.append("LOWER_LIMIT_STATE")
    except ValueError:
        reasons.append("INVALID_TWO_SIDED_QUOTE")
    hard = bool(reasons)
    return ExecutionAssessment("EXECUTABLE" if not hard else "DETECTED_NOT_EXECUTABLE", tuple(dict.fromkeys(reasons)), age, feed_access)


__all__ = ["ExecutionAssessment", "assess_execution"]
