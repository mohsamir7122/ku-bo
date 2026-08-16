from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from .event_factor_common import (
    EventFactorPanelError,
    POST_EVENT_SESSIONS,
    PRE_EVENT_SESSIONS,
    PRODUCT_ID,
    _EVENT_FIELDS,
    _FACTOR_FIELDS,
    _FORBIDDEN_FACTOR_TOKENS,
    _PACKET_FIELDS,
    _POLICY_FIELDS,
    _RECEIPT_FIELDS,
    _SESSION_FIELDS,
    _SNAPSHOT_FIELDS,
    _aware,
    _digest,
    _fields,
    _mapping,
    _number,
    _positive_int,
    _sha,
    _text,
    _url,
)

def _validate_policy(raw: Any) -> dict[str, Any]:
    policy = _mapping(raw, "policy")
    _fields(policy, _POLICY_FIELDS, "policy")
    if _positive_int(policy["pre_event_sessions"], "policy.pre_event_sessions") != 20:
        raise EventFactorPanelError("policy.pre_event_sessions must equal 20")
    if _positive_int(policy["post_event_sessions"], "policy.post_event_sessions") != 20:
        raise EventFactorPanelError("policy.post_event_sessions must equal 20")
    expected = {
        "entry_rule": "FIRST_ELIGIBLE_CLOSE_AFTER_EVENT",
        "price_basis": "TOTAL_RETURN_INDEX",
        "benchmark_rule": "POINT_IN_TIME_MARKET_AND_SECTOR",
        "corporate_action_rule": "ADJUSTED_OR_EXPLICIT_NONE",
        "event_cluster_rule": "ONE_CANONICAL_EVENT_CLUSTER",
        "feature_cutoff_rule": "AVAILABLE_AT_OR_BEFORE_EVENT",
        "overlap_rule": "PURGE_AND_EMBARGO",
    }
    for field, value in expected.items():
        if policy[field] != value:
            raise EventFactorPanelError(f"policy.{field} must equal {value}")
    result = dict(policy)
    result["material_return_threshold_pct"] = _number(
        policy["material_return_threshold_pct"],
        "policy.material_return_threshold_pct",
        minimum=0.01,
        maximum=100.0,
    )
    return result


def _validate_event(raw: Any) -> dict[str, Any]:
    event = _mapping(raw, "event")
    _fields(event, _EVENT_FIELDS, "event")
    published = _aware(event["published_at"], "event.published_at")
    available = _aware(event["available_at"], "event.available_at")
    if available < published:
        raise EventFactorPanelError("event.available_at precedes event.published_at")
    duplicate_of = None
    if event["duplicate_of"] not in (None, ""):
        duplicate_of = _text(event["duplicate_of"], "event.duplicate_of", 128)
    result = {
        "event_id": _text(event["event_id"], "event.event_id", 128),
        "security_code": _text(event["security_code"], "event.security_code", 64),
        "canonical_cluster_id": _text(
            event["canonical_cluster_id"], "event.canonical_cluster_id", 128
        ),
        "event_type": _text(event["event_type"], "event.event_type", 128),
        "published_at": event["published_at"],
        "available_at": event["available_at"],
        "source_url": _url(event["source_url"], "event.source_url"),
        "evidence_sha256": _sha(event["evidence_sha256"], "event.evidence_sha256"),
        "duplicate_of": duplicate_of,
    }
    if duplicate_of == result["event_id"]:
        raise EventFactorPanelError("event.duplicate_of cannot equal event.event_id")
    if duplicate_of is not None:
        raise EventFactorPanelError(
            "event-study packets must contain the canonical event, not a duplicate document"
        )
    return result


def _validate_snapshot(raw: Any, event_available: datetime) -> dict[str, Any]:
    snapshot = _mapping(raw, "factor_snapshot")
    _fields(snapshot, _SNAPSHOT_FIELDS, "factor_snapshot")
    snapshot_at = _aware(snapshot["snapshot_at"], "factor_snapshot.snapshot_at")
    if snapshot_at > event_available:
        raise EventFactorPanelError("factor snapshot exceeds event cutoff")
    factors = snapshot["factors"]
    if not isinstance(factors, Sequence) or isinstance(factors, (str, bytes)) or not factors:
        raise EventFactorPanelError("factor_snapshot.factors must be non-empty")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(factors):
        factor = _mapping(item, f"factor_snapshot.factors[{index}]")
        _fields(factor, _FACTOR_FIELDS, f"factor_snapshot.factors[{index}]")
        factor_id = _text(
            factor["factor_id"], f"factor_snapshot.factors[{index}].factor_id", 128
        )
        if factor_id in seen:
            raise EventFactorPanelError(f"duplicate factor_id: {factor_id}")
        seen.add(factor_id)
        folded = factor_id.casefold()
        if any(token in folded for token in _FORBIDDEN_FACTOR_TOKENS):
            raise EventFactorPanelError(
                f"factor {factor_id} contains a future/label token"
            )
        state = _text(factor["state"], f"factor_snapshot.factors[{index}].state", 64)
        if state not in {"OBSERVED", "UNKNOWN_NOT_OBSERVED", "BLOCKED"}:
            raise EventFactorPanelError(f"invalid factor state: {state}")
        available = _aware(
            factor["available_at"], f"factor_snapshot.factors[{index}].available_at"
        )
        if available > event_available:
            raise EventFactorPanelError(f"factor {factor_id} became available after event")
        if available > snapshot_at:
            raise EventFactorPanelError(
                f"factor {factor_id} became available after factor snapshot"
            )
        if state == "OBSERVED":
            value: float | None = _number(
                factor["value"], f"factor_snapshot.factors[{index}].value"
            )
        else:
            if factor["value"] is not None:
                raise EventFactorPanelError(
                    f"factor {factor_id} must use null when state={state}"
                )
            value = None
        validated.append(
            {
                "factor_id": factor_id,
                "state": state,
                "value": value,
                "available_at": factor["available_at"],
                "evidence_sha256": _sha(
                    factor["evidence_sha256"],
                    f"factor_snapshot.factors[{index}].evidence_sha256",
                ),
            }
        )
    return {
        "snapshot_id": _text(snapshot["snapshot_id"], "factor_snapshot.snapshot_id", 128),
        "snapshot_at": snapshot["snapshot_at"],
        "evidence_sha256": _sha(
            snapshot["evidence_sha256"], "factor_snapshot.evidence_sha256"
        ),
        "factors": validated,
    }


def _validate_sessions(
    raw: Any,
    *,
    field: str,
    event_available: datetime,
    before_event: bool,
) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise EventFactorPanelError(f"{field} must be an array")
    required = PRE_EVENT_SESSIONS if before_event else POST_EVENT_SESSIONS
    if len(raw) != required:
        raise EventFactorPanelError(f"{field} must contain exactly {required} sessions")
    result: list[dict[str, Any]] = []
    dates: list[str] = []
    closes: list[datetime] = []
    for index, item in enumerate(raw):
        row = _mapping(item, f"{field}[{index}]")
        _fields(row, _SESSION_FIELDS, f"{field}[{index}]")
        trade_date = _text(row["trade_date"], f"{field}[{index}].trade_date", 10)
        try:
            datetime.strptime(trade_date, "%Y-%m-%d")
        except ValueError as exc:
            raise EventFactorPanelError(
                f"{field}[{index}].trade_date must be YYYY-MM-DD"
            ) from exc
        close = _aware(row["session_close_at"], f"{field}[{index}].session_close_at")
        observed = _aware(row["observed_at"], f"{field}[{index}].observed_at")
        if close.date().isoformat() != trade_date:
            raise EventFactorPanelError(f"{field}[{index}] date/close mismatch")
        if observed < close:
            raise EventFactorPanelError(f"{field}[{index}] observed before close")
        if before_event and (observed > event_available or close >= event_available):
            raise EventFactorPanelError(f"{field}[{index}] is not available pre-event")
        if not before_event and close <= event_available:
            raise EventFactorPanelError(f"{field}[{index}] is not strictly post-event")
        validated = {
            "trade_date": trade_date,
            "session_close_at": row["session_close_at"],
            "observed_at": row["observed_at"],
            "stock_total_return_index": _number(
                row["stock_total_return_index"],
                f"{field}[{index}].stock_total_return_index",
                minimum=1e-12,
            ),
            "market_total_return_index": _number(
                row["market_total_return_index"],
                f"{field}[{index}].market_total_return_index",
                minimum=1e-12,
            ),
            "sector_total_return_index": _number(
                row["sector_total_return_index"],
                f"{field}[{index}].sector_total_return_index",
                minimum=1e-12,
            ),
            "volume": _number(row["volume"], f"{field}[{index}].volume", minimum=0.0),
        }
        for evidence in (
            "calendar_evidence_sha256",
            "price_evidence_sha256",
            "market_benchmark_evidence_sha256",
            "sector_benchmark_evidence_sha256",
            "corporate_action_evidence_sha256",
        ):
            validated[evidence] = _sha(row[evidence], f"{field}[{index}].{evidence}")
        result.append(validated)
        dates.append(trade_date)
        closes.append(close)
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise EventFactorPanelError(f"{field} must be unique and ascending")
    if closes != sorted(closes):
        raise EventFactorPanelError(f"{field} closes must be ascending")
    return result


def validate_event_factor_panel_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the event-centered twenty-before/twenty-after packet."""

    packet = _mapping(packet, "packet")
    _fields(packet, _PACKET_FIELDS, "packet")
    if packet["schema_version"] != "1.0":
        raise EventFactorPanelError("schema_version must equal 1.0")
    if packet["product_id"] != PRODUCT_ID:
        raise EventFactorPanelError(f"product_id must equal {PRODUCT_ID}")
    if packet["timezone"] != "Asia/Kuwait":
        raise EventFactorPanelError("timezone must equal Asia/Kuwait")
    if packet["evidence_classification"] != "PROVEN_REAL_EVIDENCE":
        raise EventFactorPanelError(
            "evidence_classification must equal PROVEN_REAL_EVIDENCE"
        )
    if packet["rights_status"] != "RESEARCH_USE_AUTHORIZED":
        raise EventFactorPanelError("rights_status must equal RESEARCH_USE_AUTHORIZED")
    if packet["independent_authority_receipt"] is not None:
        raise EventFactorPanelError(
            "independent_authority_receipt is not accepted by public v1"
        )

    created_at = _aware(packet["created_at"], "packet.created_at")
    policy = _validate_policy(packet["policy"])
    event = _validate_event(packet["event"])
    event_available = _aware(event["available_at"], "event.available_at")
    if created_at < event_available:
        raise EventFactorPanelError("packet.created_at precedes event.available_at")
    snapshot = _validate_snapshot(packet["factor_snapshot"], event_available)
    pre = _validate_sessions(
        packet["pre_sessions"],
        field="pre_sessions",
        event_available=event_available,
        before_event=True,
    )
    post = _validate_sessions(
        packet["post_sessions"],
        field="post_sessions",
        event_available=event_available,
        before_event=False,
    )
    if pre[-1]["trade_date"] >= post[0]["trade_date"]:
        raise EventFactorPanelError("pre/post windows overlap")
    latest_observed = max(
        _aware(row["observed_at"], "session.observed_at")
        for row in (*pre, *post)
    )
    if created_at < latest_observed:
        raise EventFactorPanelError(
            "packet.created_at precedes an included session observation"
        )

    receipts = _mapping(packet["evidence_receipts"], "evidence_receipts")
    _fields(receipts, _RECEIPT_FIELDS, "evidence_receipts")
    validated_receipts = {
        field: _sha(value, f"evidence_receipts.{field}")
        for field, value in receipts.items()
    }
    if validated_receipts["event_ledger_sha256"] != event["evidence_sha256"]:
        raise EventFactorPanelError("event does not match event-ledger receipt")
    if validated_receipts["factor_snapshot_sha256"] != snapshot["evidence_sha256"]:
        raise EventFactorPanelError("snapshot does not match snapshot receipt")
    session_receipt_map = {
        "calendar_evidence_sha256": "trading_calendar_sha256",
        "price_evidence_sha256": "price_history_sha256",
        "market_benchmark_evidence_sha256": "market_benchmark_sha256",
        "sector_benchmark_evidence_sha256": "sector_benchmark_sha256",
        "corporate_action_evidence_sha256": "corporate_actions_sha256",
    }
    for window_name, rows in (("pre_sessions", pre), ("post_sessions", post)):
        for index, row in enumerate(rows):
            for row_field, receipt_field in session_receipt_map.items():
                if row[row_field] != validated_receipts[receipt_field]:
                    raise EventFactorPanelError(
                        f"{window_name}[{index}].{row_field} does not match "
                        f"evidence_receipts.{receipt_field}"
                    )

    return {
        **dict(packet),
        "packet_id": _text(packet["packet_id"], "packet.packet_id", 128),
        "policy": policy,
        "event": event,
        "factor_snapshot": snapshot,
        "pre_sessions": pre,
        "post_sessions": post,
        "evidence_receipts": validated_receipts,
    }


__all__ = ["validate_event_factor_panel_packet"]
