from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .identity import IdentityRecord, StatusRecord, eligible_codes_on, read_csv_rows
from .strict import contains_placeholder, finite_number, parse_aware, parse_iso_date, require_sha256


@dataclass(frozen=True)
class ValidationResult:
    status: str
    rows: int
    errors: tuple[str, ...]
    details: dict[str, Any]


def _result(rows: int, errors: list[str], **details: Any) -> ValidationResult:
    return ValidationResult("PASS" if not errors else "BLOCKED", rows, tuple(sorted(set(errors))), details)


def _csv_bool(value: Any, field: str) -> bool:
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(f"{field} must be true or false")


def _verify_raw_hash(row: dict[str, str], manifest_hashes: frozenset[str]) -> str:
    digest = require_sha256(row.get("raw_sha256"), "raw_sha256")
    if digest not in manifest_hashes:
        raise ValueError("raw_sha256 does not resolve")
    return digest


def validate_trading_calendar(path: Path, *, manifest_hashes: frozenset[str], window_from: date, window_to: date) -> tuple[dict[date, dict[str, Any]], ValidationResult]:
    required = {"trade_date", "is_trading_day", "session_type", "session_regime_id", "continuous_start", "continuous_end", "trade_at_last_end", "raw_sha256"}
    errors: list[str] = []
    parsed: dict[date, dict[str, Any]] = {}
    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return {}, _result(0, [f"CALENDAR_READ:{exc}"])
    missing = sorted(required - set(headers))
    if missing:
        return {}, _result(len(rows), ["CALENDAR_HEADERS:" + ",".join(missing)])
    for index, row in enumerate(rows):
        try:
            day = parse_iso_date(row.get("trade_date"), "trade_date")
            if day in parsed:
                raise ValueError("duplicate civil date")
            is_trading = _csv_bool(row.get("is_trading_day"), "is_trading_day")
            _verify_raw_hash(row, manifest_hashes)
            if is_trading:
                if not row.get("session_regime_id") or not row.get("continuous_start") or not row.get("continuous_end") or not row.get("trade_at_last_end"):
                    raise ValueError("trading day lacks session regime/times")
                for field in ("continuous_start", "continuous_end", "trade_at_last_end"):
                    datetime.strptime(str(row[field]), "%H:%M:%S")
            parsed[day] = {**row, "is_trading_day": is_trading}
        except (TypeError, ValueError) as exc:
            errors.append(f"calendar_row_{index}:{exc}")
    expected_days: list[date] = []
    current = window_from
    while current <= window_to:
        expected_days.append(current)
        current += timedelta(days=1)
    missing_days = sorted(set(expected_days) - set(parsed))
    extra_days = sorted(set(parsed) - set(expected_days))
    if missing_days:
        errors.append("CALENDAR_MISSING_DATES:" + ",".join(day.isoformat() for day in missing_days))
    if extra_days:
        errors.append("CALENDAR_EXTRA_DATES:" + ",".join(day.isoformat() for day in extra_days))
    return parsed, _result(len(rows), errors, expected_dates=len(expected_days), trading_dates=sum(1 for row in parsed.values() if row["is_trading_day"]))


def validate_eod(
    path: Path,
    *,
    manifest_hashes: frozenset[str],
    calendar: dict[date, dict[str, Any]],
    identities: Iterable[IdentityRecord],
    statuses: Iterable[StatusRecord],
    board: str = "cash",
) -> tuple[list[dict[str, Any]], ValidationResult]:
    required = {
        "trade_date",
        "security_code",
        "ticker",
        "open_fils",
        "high_fils",
        "low_fils",
        "close_fils",
        "volume",
        "value_traded_kwd",
        "trade_count",
        "reference_price_fils",
        "trading_status",
        "corporate_action_status",
        "raw_sha256",
    }
    errors: list[str] = []
    parsed: list[dict[str, Any]] = []
    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return [], _result(0, [f"EOD_READ:{exc}"])
    missing = sorted(required - set(headers))
    if missing:
        return [], _result(len(rows), ["EOD_HEADERS:" + ",".join(missing)])
    seen: set[tuple[date, str]] = set()
    allowed_statuses = {"TRADED", "NO_TRADE", "SUSPENDED", "HALTED", "TRADED_THEN_SUSPENDED"}
    for index, row in enumerate(rows):
        try:
            if any(contains_placeholder(value) for value in row.values()):
                raise ValueError("template placeholder")
            day = parse_iso_date(row.get("trade_date"), "trade_date")
            code = str(row.get("security_code", "")).strip()
            key = (day, code)
            if not code or key in seen:
                raise ValueError("missing identity or duplicate security-session key")
            seen.add(key)
            if day not in calendar or not calendar[day]["is_trading_day"]:
                raise ValueError("EOD row is not on an official trading date")
            _verify_raw_hash(row, manifest_hashes)
            status = str(row.get("trading_status", "")).upper()
            if status not in allowed_statuses:
                raise ValueError("invalid trading_status")
            price_fields = ("open_fils", "high_fils", "low_fils", "close_fils")
            numeric: dict[str, float] = {}
            if status in {"TRADED", "TRADED_THEN_SUSPENDED"}:
                for field in price_fields:
                    numeric[field] = finite_number(row.get(field), field, minimum=0.001)
                if numeric["high_fils"] < max(numeric["open_fils"], numeric["close_fils"], numeric["low_fils"]):
                    raise ValueError("OHLC high constraint")
                if numeric["low_fils"] > min(numeric["open_fils"], numeric["close_fils"], numeric["high_fils"]):
                    raise ValueError("OHLC low constraint")
                volume = finite_number(row.get("volume"), "volume", minimum=0)
                value = finite_number(row.get("value_traded_kwd"), "value_traded_kwd", minimum=0)
                trades = finite_number(row.get("trade_count"), "trade_count", minimum=0)
                if volume <= 0 or value <= 0 or trades <= 0:
                    raise ValueError("TRADED requires positive volume, value, and trade_count")
            else:
                if any(row.get(field) not in (None, "") for field in price_fields):
                    raise ValueError("non-traded row contains synthetic OHLC")
                for field in ("volume", "value_traded_kwd", "trade_count"):
                    if row.get(field) not in (None, "", "0", "0.0"):
                        raise ValueError("non-traded row contains positive activity")
            ca_status = str(row.get("corporate_action_status", "")).lower()
            if ca_status not in {"officially_adjusted", "raw_unadjusted", "not_applicable", "unknown"}:
                raise ValueError("invalid corporate_action_status")
            parsed.append({**row, "trade_date": day, "security_code": code, "trading_status": status})
        except (TypeError, ValueError) as exc:
            errors.append(f"eod_row_{index}:{exc}")
    trading_days = sorted(day for day, row in calendar.items() if row["is_trading_day"])
    expected = {(day, code) for day in trading_days for code in eligible_codes_on(day, identities, statuses, board=board)}
    actual = {(row["trade_date"], row["security_code"]) for row in parsed}
    missing_pairs = expected - actual
    extra_pairs = actual - expected
    if missing_pairs:
        errors.append(f"EOD_DENOMINATOR_MISSING:{len(missing_pairs)}")
    if extra_pairs:
        errors.append(f"EOD_DENOMINATOR_EXTRA:{len(extra_pairs)}")
    return parsed, _result(len(rows), errors, expected_pairs=len(expected), actual_pairs=len(actual))


def validate_market_totals(path: Path, *, manifest_hashes: frozenset[str], eod_rows: Iterable[dict[str, Any]], board: str = "cash", value_tolerance_kwd: float = 0.001) -> ValidationResult:
    required = {"trade_date", "board", "traded_security_count", "total_volume", "total_value_kwd", "total_trade_count", "raw_sha256"}
    errors: list[str] = []
    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return _result(0, [f"TOTALS_READ:{exc}"])
    missing = sorted(required - set(headers))
    if missing:
        return _result(len(rows), ["TOTALS_HEADERS:" + ",".join(missing)])
    aggregates: dict[date, dict[str, float]] = {}
    for row in eod_rows:
        if row["trading_status"] not in {"TRADED", "TRADED_THEN_SUSPENDED"}:
            continue
        day = row["trade_date"]
        bucket = aggregates.setdefault(day, {"count": 0.0, "volume": 0.0, "value": 0.0, "trades": 0.0})
        bucket["count"] += 1
        bucket["volume"] += float(row["volume"])
        bucket["value"] += float(row["value_traded_kwd"])
        bucket["trades"] += float(row["trade_count"])
    seen: set[date] = set()
    for index, row in enumerate(rows):
        try:
            day = parse_iso_date(row.get("trade_date"), "trade_date")
            if day in seen:
                raise ValueError("duplicate board total date")
            seen.add(day)
            if str(row.get("board", "")).lower() != board:
                raise ValueError("unexpected board")
            _verify_raw_hash(row, manifest_hashes)
            expected = aggregates.get(day, {"count": 0.0, "volume": 0.0, "value": 0.0, "trades": 0.0})
            supplied = {
                "count": finite_number(row.get("traded_security_count"), "traded_security_count", minimum=0),
                "volume": finite_number(row.get("total_volume"), "total_volume", minimum=0),
                "value": finite_number(row.get("total_value_kwd"), "total_value_kwd", minimum=0),
                "trades": finite_number(row.get("total_trade_count"), "total_trade_count", minimum=0),
            }
            for field in ("count", "volume", "trades"):
                if supplied[field] != expected[field]:
                    raise ValueError(f"{field} does not reconcile")
            if abs(supplied["value"] - expected["value"]) > value_tolerance_kwd:
                raise ValueError("value does not reconcile")
        except (TypeError, ValueError) as exc:
            errors.append(f"totals_row_{index}:{exc}")
    missing_totals = sorted(set(aggregates) - seen)
    if missing_totals:
        errors.append("MISSING_DAILY_TOTALS:" + ",".join(day.isoformat() for day in missing_totals))
    return _result(len(rows), errors, reconciled_dates=len(seen))


def validate_query_ledger(path: Path, *, manifest_hashes: frozenset[str], window_from: date, window_to: date) -> tuple[list[dict[str, Any]], ValidationResult]:
    required = {"query_id", "dataset", "window_from", "window_to", "pages_declared", "pages_received", "result_count_declared", "rows_normalized", "zero_result", "raw_sha256"}
    errors: list[str] = []
    parsed: list[dict[str, Any]] = []
    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return [], _result(0, [f"QUERY_READ:{exc}"])
    missing = sorted(required - set(headers))
    if missing:
        return [], _result(len(rows), ["QUERY_HEADERS:" + ",".join(missing)])
    seen: set[str] = set()
    for index, row in enumerate(rows):
        try:
            query_id = str(row.get("query_id", "")).strip()
            if not query_id or query_id in seen:
                raise ValueError("missing or duplicate query_id")
            seen.add(query_id)
            start = parse_iso_date(row.get("window_from"), "window_from")
            end = parse_iso_date(row.get("window_to"), "window_to")
            if start > end or start < window_from or end > window_to:
                raise ValueError("query window is outside collection window")
            pages_declared = int(row.get("pages_declared", ""))
            pages_received = int(row.get("pages_received", ""))
            result_count = int(row.get("result_count_declared", ""))
            normalized = int(row.get("rows_normalized", ""))
            zero = _csv_bool(row.get("zero_result"), "zero_result")
            if min(pages_declared, pages_received, result_count, normalized) < 0:
                raise ValueError("negative query counts")
            if pages_declared != pages_received:
                raise ValueError("pagination incomplete")
            if zero != (result_count == 0 and normalized == 0):
                raise ValueError("zero_result does not match counts")
            _verify_raw_hash(row, manifest_hashes)
            parsed.append({**row, "window_from": start, "window_to": end, "zero_result": zero})
        except (TypeError, ValueError) as exc:
            errors.append(f"query_row_{index}:{exc}")
    return parsed, _result(len(rows), errors)


def validate_event_table(
    path: Path,
    *,
    dataset: str,
    manifest_hashes: frozenset[str],
    query_rows: Iterable[dict[str, Any]],
    required_columns: set[str],
) -> ValidationResult:
    errors: list[str] = []
    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return _result(0, [f"{dataset.upper()}_READ:{exc}"])
    missing = sorted(required_columns - set(headers))
    if missing:
        return _result(len(rows), [f"{dataset.upper()}_HEADERS:" + ",".join(missing)])
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        try:
            code = str(row.get("security_code", "")).strip()
            item_id = str(row.get("news_id") or row.get("action_id") or "").strip()
            if not code or not item_id or (code, item_id) in seen:
                raise ValueError("missing or duplicate event identity")
            seen.add((code, item_id))
            _verify_raw_hash(row, manifest_hashes)
            for key, value in row.items():
                if contains_placeholder(value):
                    raise ValueError(f"placeholder in {key}")
            if dataset == "disclosures":
                published = parse_aware(row.get("published_at"), "published_at")
                event_value = row.get("event_at")
                if event_value not in (None, ""):
                    parse_aware(event_value, "event_at")
                fetched = parse_aware(row.get("fetched_at"), "fetched_at")
                if fetched < published:
                    raise ValueError("fetched_at precedes published_at")
            else:
                parse_iso_date(row.get("announcement_date"), "announcement_date")
                factor_status = str(row.get("factor_status", "")).lower()
                if factor_status not in {"official", "pending", "not_applicable"}:
                    raise ValueError("invalid factor_status")
                if factor_status == "official":
                    finite_number(row.get("adjustment_factor"), "adjustment_factor", minimum=0.0000001)
        except (TypeError, ValueError) as exc:
            errors.append(f"{dataset}_row_{index}:{exc}")
    relevant_queries = [row for row in query_rows if str(row.get("dataset")) == dataset]
    if not rows:
        if not relevant_queries or not all(bool(row.get("zero_result")) for row in relevant_queries):
            errors.append(f"{dataset.upper()}_EMPTY_WITHOUT_EXPLICIT_ZERO_QUERY")
    elif sum(int(row.get("rows_normalized", 0)) for row in relevant_queries) != len(rows):
        errors.append(f"{dataset.upper()}_QUERY_ROW_RECONCILIATION")
    return _result(len(rows), errors)


DISCLOSURE_COLUMNS = {
    "security_code",
    "ticker",
    "news_id",
    "announcement_type",
    "event_at",
    "published_at",
    "relation_type",
    "original_news_id",
    "fetched_at",
    "raw_sha256",
}

CORPORATE_ACTION_COLUMNS = {
    "security_code",
    "ticker",
    "action_id",
    "action_type",
    "announcement_date",
    "ex_date",
    "record_date",
    "payment_date",
    "adjustment_factor",
    "factor_status",
    "raw_sha256",
}


__all__ = [
    "CORPORATE_ACTION_COLUMNS",
    "DISCLOSURE_COLUMNS",
    "ValidationResult",
    "validate_eod",
    "validate_event_table",
    "validate_market_totals",
    "validate_query_ledger",
    "validate_trading_calendar",
]
