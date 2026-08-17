from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from .disclosure_reaction_common import (
    DisclosureReactionError,
    POST_SESSIONS,
    PRE_SESSIONS,
    aware,
    day,
    exact_fields,
    mapping,
    number,
    sha256,
    text,
)

_SESSION_FIELDS = {
    "trade_date", "session_close_at", "observed_at",
    "stock_total_return_index", "market_total_return_index",
    "sector_total_return_index", "calendar_evidence_sha256",
    "price_evidence_sha256", "market_benchmark_evidence_sha256",
    "sector_benchmark_evidence_sha256", "corporate_action_evidence_sha256",
}
_FIELDS = {
    "schema_version", "data_domain", "immutability", "window_id",
    "security_code", "canonical_cluster_id", "disclosure_record_id",
    "frozen_at", "price_basis", "benchmark_basis", "corporate_action_status",
    "pre_sessions", "post_sessions", "evidence_receipts",
}
_RECEIPTS = {
    "trading_calendar_sha256", "price_history_sha256",
    "market_benchmark_sha256", "sector_benchmark_sha256",
    "corporate_actions_sha256",
}


def _validate_sessions(raw: Any, *, field: str, expected_count: int) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise DisclosureReactionError(f"{field} must be an array")
    if len(raw) != expected_count:
        raise DisclosureReactionError(f"{field} must contain exactly {expected_count} sessions")
    result: list[dict[str, Any]] = []
    dates: list[str] = []
    closes: list[datetime] = []
    for index, item in enumerate(raw):
        row = mapping(item, f"{field}[{index}]")
        exact_fields(row, _SESSION_FIELDS, f"{field}[{index}]")
        trade_date = day(row["trade_date"], f"{field}[{index}].trade_date")
        close = aware(row["session_close_at"], f"{field}[{index}].session_close_at")
        observed = aware(row["observed_at"], f"{field}[{index}].observed_at")
        if close.date() != trade_date:
            raise DisclosureReactionError(f"{field}[{index}] date/close mismatch")
        if observed < close:
            raise DisclosureReactionError(f"{field}[{index}] observed before close")
        validated = {
            "trade_date": trade_date.isoformat(),
            "session_close_at": row["session_close_at"],
            "observed_at": row["observed_at"],
            "stock_total_return_index": number(row["stock_total_return_index"], f"{field}[{index}].stock_total_return_index", minimum=1e-12),
            "market_total_return_index": number(row["market_total_return_index"], f"{field}[{index}].market_total_return_index", minimum=1e-12),
            "sector_total_return_index": number(row["sector_total_return_index"], f"{field}[{index}].sector_total_return_index", minimum=1e-12),
        }
        for evidence_field in (
            "calendar_evidence_sha256", "price_evidence_sha256",
            "market_benchmark_evidence_sha256", "sector_benchmark_evidence_sha256",
            "corporate_action_evidence_sha256",
        ):
            validated[evidence_field] = sha256(row[evidence_field], f"{field}[{index}].{evidence_field}")
        result.append(validated)
        dates.append(trade_date.isoformat())
        closes.append(close)
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise DisclosureReactionError(f"{field} must be unique and ascending")
    if closes != sorted(closes):
        raise DisclosureReactionError(f"{field} closes must be ascending")
    return result


def validate_historical_event_market_window(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = mapping(raw, "historical_market_window")
    exact_fields(value, _FIELDS, "historical_market_window")
    if value["schema_version"] != "1.0":
        raise DisclosureReactionError("historical market window schema_version must equal 1.0")
    if value["data_domain"] != "HISTORICAL_EVENT_MARKET_WINDOW":
        raise DisclosureReactionError("historical market window data_domain mismatch")
    if value["immutability"] != "FROZEN":
        raise DisclosureReactionError("historical event market window must be FROZEN")
    if value["price_basis"] != "TOTAL_RETURN_INDEX":
        raise DisclosureReactionError("historical event window requires TOTAL_RETURN_INDEX")
    if value["benchmark_basis"] != "MARKET_AND_SECTOR_EXCESS":
        raise DisclosureReactionError("historical event window requires market and sector benchmarks")
    if value["corporate_action_status"] not in {"ADJUSTED", "VERIFIED_NONE"}:
        raise DisclosureReactionError("corporate_action_status must be ADJUSTED or VERIFIED_NONE")
    security_code = text(value["security_code"], "historical_market_window.security_code", 64).upper()
    if security_code != "HUMANSOFT":
        raise DisclosureReactionError("historical market window security_code must equal HUMANSOFT")
    pre = _validate_sessions(value["pre_sessions"], field="historical_market_window.pre_sessions", expected_count=PRE_SESSIONS)
    post = _validate_sessions(value["post_sessions"], field="historical_market_window.post_sessions", expected_count=POST_SESSIONS)
    if pre[-1]["trade_date"] >= post[0]["trade_date"]:
        raise DisclosureReactionError("historical market pre/post windows overlap")
    frozen_at = aware(value["frozen_at"], "historical_market_window.frozen_at")
    latest_observed = max(aware(row["observed_at"], "session.observed_at") for row in (*pre, *post))
    if frozen_at < latest_observed:
        raise DisclosureReactionError("historical market window frozen before all observations existed")
    receipts = mapping(value["evidence_receipts"], "historical_market_window.evidence_receipts")
    exact_fields(receipts, _RECEIPTS, "historical_market_window.evidence_receipts")
    validated_receipts = {key: sha256(item, f"historical_market_window.evidence_receipts.{key}") for key, item in receipts.items()}
    receipt_map = {
        "calendar_evidence_sha256": "trading_calendar_sha256",
        "price_evidence_sha256": "price_history_sha256",
        "market_benchmark_evidence_sha256": "market_benchmark_sha256",
        "sector_benchmark_evidence_sha256": "sector_benchmark_sha256",
        "corporate_action_evidence_sha256": "corporate_actions_sha256",
    }
    for window_name, rows in (("pre_sessions", pre), ("post_sessions", post)):
        for index, row in enumerate(rows):
            for row_field, receipt_field in receipt_map.items():
                if row[row_field] != validated_receipts[receipt_field]:
                    raise DisclosureReactionError(
                        f"historical_market_window.{window_name}[{index}].{row_field} receipt mismatch"
                    )
    return {
        **dict(value),
        "window_id": text(value["window_id"], "historical_market_window.window_id", 128),
        "security_code": security_code,
        "canonical_cluster_id": text(value["canonical_cluster_id"], "historical_market_window.canonical_cluster_id", 128),
        "disclosure_record_id": text(value["disclosure_record_id"], "historical_market_window.disclosure_record_id", 128),
        "pre_sessions": pre,
        "post_sessions": post,
        "evidence_receipts": validated_receipts,
    }


__all__ = ["validate_historical_event_market_window"]
