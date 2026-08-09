from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .strict import parse_iso_date, require_sha256


SECURITY_STATUS_EVIDENCE_HEADERS = (
    "security_code",
    "ticker",
    "board",
    "status",
    "effective_from",
    "effective_to",
    "reason_code",
    "notice_id",
    "raw_sha256",
    "identity_snapshot_sha256",
    "temporal_scope",
    "source_url",
)
DELISTING_ARCHIVE_HEADERS = (
    "security_code",
    "ticker",
    "name",
    "sector",
    "market_segment",
    "delisting_date",
    "raw_sha256",
    "source_url",
)
CORPORATE_ACTION_SCHEDULE_HEADERS = (
    "security_code",
    "ticker",
    "isin",
    "action_id",
    "cum_date",
    "ex_date",
    "record_date",
    "payment_date",
    "action_type",
    "adjustment_factor",
    "factor_status",
    "raw_sha256",
    "query_id",
    "coverage_scope",
    "source_url",
)
CORPORATE_ACTION_ENRICHMENT_HEADERS = (
    "action_id",
    "security_code",
    "ticker",
    "ex_date",
    "required_enrichment",
    "disclosure_url",
    "disclosure_raw_sha256",
    "review_status",
    "review_notes",
)
QUERY_LEDGER_HEADERS = (
    "query_id",
    "dataset",
    "window_from",
    "window_to",
    "pages_declared",
    "pages_received",
    "result_count_declared",
    "rows_normalized",
    "zero_result",
    "raw_sha256",
)


def write_csv(path: Path, headers: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def validate_security_status_evidence_rows(
    rows: Iterable[dict[str, Any]],
    *,
    expected_codes: frozenset[str],
    suspended_codes: frozenset[str],
    manifest_hashes: frozenset[str],
    identity_snapshot_sha256: str,
    snapshot_date: date,
) -> dict[str, Any]:
    values = list(rows)
    errors: list[str] = []
    seen_codes: set[str] = set()
    observed_suspended: set[str] = set()
    for index, row in enumerate(values):
        try:
            code = str(row.get("security_code", ""))
            ticker = str(row.get("ticker", ""))
            if code not in expected_codes or not ticker:
                raise ValueError("row is outside the expected current pilot identity")
            if code in seen_codes:
                raise ValueError("duplicate current status row")
            seen_codes.add(code)
            if str(row.get("board", "")).lower() != "cash":
                raise ValueError("board must be cash")
            status = str(row.get("status", "")).upper()
            if status not in {"TRADING", "SUSPENDED"}:
                raise ValueError("current snapshot status must be TRADING or SUSPENDED")
            if status == "SUSPENDED":
                observed_suspended.add(code)
            effective_from = parse_iso_date(row.get("effective_from"), "effective_from")
            if effective_from != snapshot_date or row.get("effective_to") not in (None, ""):
                raise ValueError("current snapshot interval must start at snapshot date and remain open")
            expected_reason = (
                "PRESENT_IN_CURRENT_SUSPENDED_TABLE"
                if status == "SUSPENDED"
                else "ABSENT_FROM_COMPLETE_SUSPENDED_TABLE"
            )
            if row.get("reason_code") != expected_reason:
                raise ValueError("reason_code does not match current suspended snapshot")
            if not str(row.get("notice_id", "")).startswith(
                f"status-snapshot:{snapshot_date.isoformat()}:{code}:"
            ):
                raise ValueError("notice_id is not bound to the status snapshot")
            digest = require_sha256(row.get("raw_sha256"), "raw_sha256")
            if digest not in manifest_hashes:
                raise ValueError("raw_sha256 does not resolve")
            identity_hash = require_sha256(
                row.get("identity_snapshot_sha256"),
                "identity_snapshot_sha256",
            )
            if identity_hash != identity_snapshot_sha256:
                raise ValueError("identity snapshot hash mismatch")
            if row.get("temporal_scope") != "CURRENT_SNAPSHOT_ONLY":
                raise ValueError("temporal_scope must remain CURRENT_SNAPSHOT_ONLY")
            source_url = str(row.get("source_url", ""))
            if not source_url.startswith("https://"):
                raise ValueError("source_url must be HTTPS")
        except (TypeError, ValueError) as exc:
            errors.append(f"status_row_{index}:{exc}")
    if seen_codes != set(expected_codes):
        errors.append(
            "STATUS_DENOMINATOR_MISMATCH:"
            f"missing={len(set(expected_codes) - seen_codes)}:"
            f"extra={len(seen_codes - set(expected_codes))}"
        )
    expected_suspended = set(expected_codes) & set(suspended_codes)
    if observed_suspended != expected_suspended:
        errors.append(
            "SUSPENDED_SET_MISMATCH:"
            f"missing={len(expected_suspended - observed_suspended)}:"
            f"extra={len(observed_suspended - expected_suspended)}"
        )
    return {
        "status": "PASS" if values and not errors else "BLOCKED",
        "rows": len(values),
        "expected_rows": len(expected_codes),
        "suspended_rows": len(observed_suspended),
        "trading_rows": len(values) - len(observed_suspended),
        "errors": sorted(set(errors)),
        "temporal_scope": "CURRENT_SNAPSHOT_ONLY",
        "security_status_history_ready": False,
    }


def validate_delisting_archive_rows(
    rows: Iterable[dict[str, Any]],
    *,
    manifest_hashes: frozenset[str],
    snapshot_date: date,
) -> dict[str, Any]:
    values = list(rows)
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(values):
        try:
            code = str(row.get("security_code", ""))
            ticker = str(row.get("ticker", ""))
            if not code or not ticker or code in seen:
                raise ValueError("missing or duplicate delisted identity")
            seen.add(code)
            delisting_date = parse_iso_date(row.get("delisting_date"), "delisting_date")
            if delisting_date > snapshot_date:
                raise ValueError("delisting date is after the status snapshot")
            digest = require_sha256(row.get("raw_sha256"), "raw_sha256")
            if digest not in manifest_hashes:
                raise ValueError("raw_sha256 does not resolve")
            if not str(row.get("source_url", "")).startswith("https://"):
                raise ValueError("source_url must be HTTPS")
        except (TypeError, ValueError) as exc:
            errors.append(f"delisting_row_{index}:{exc}")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "rows": len(values),
        "errors": sorted(set(errors)),
        "scope": "OFFICIAL_DELISTING_ARCHIVE",
    }


def validate_corporate_action_schedule_rows(
    rows: Iterable[dict[str, Any]],
    *,
    expected_identity: dict[str, tuple[str, str]],
    manifest_hashes: frozenset[str],
    query_id: str,
    action_window_from: date,
    action_window_to: date,
) -> dict[str, Any]:
    values = list(rows)
    errors: list[str] = []
    seen_ids: set[str] = set()
    pending_factors = 0
    for index, row in enumerate(values):
        try:
            code = str(row.get("security_code", ""))
            ticker = str(row.get("ticker", ""))
            isin = str(row.get("isin", ""))
            expected = expected_identity.get(code)
            if expected is None or expected != (ticker, isin):
                raise ValueError("corporate action identity does not match current official identity")
            action_id = str(row.get("action_id", ""))
            if not action_id or action_id in seen_ids:
                raise ValueError("missing or duplicate action_id")
            seen_ids.add(action_id)
            cum_date = parse_iso_date(row.get("cum_date"), "cum_date")
            ex_date = parse_iso_date(row.get("ex_date"), "ex_date")
            record_date = parse_iso_date(row.get("record_date"), "record_date")
            payment_raw = row.get("payment_date")
            payment_date = (
                None
                if payment_raw in (None, "")
                else parse_iso_date(payment_raw, "payment_date")
            )
            if not cum_date < ex_date <= record_date:
                raise ValueError("corporate action dates are out of order")
            if payment_date is not None and payment_date < record_date:
                raise ValueError("payment date precedes record date")
            relevant_dates = [cum_date, ex_date, record_date]
            if payment_date is not None:
                relevant_dates.append(payment_date)
            if max(relevant_dates) < action_window_from or min(relevant_dates) > action_window_to:
                raise ValueError("corporate action schedule is outside the declared query window")
            if row.get("action_type") != "UNCLASSIFIED_ENTITLEMENT":
                raise ValueError("schedule-only row cannot claim an action type")
            if row.get("adjustment_factor") not in (None, ""):
                raise ValueError("schedule-only row cannot contain an adjustment factor")
            if row.get("factor_status") != "pending":
                raise ValueError("factor_status must remain pending before disclosure enrichment")
            pending_factors += 1
            digest = require_sha256(row.get("raw_sha256"), "raw_sha256")
            if digest not in manifest_hashes:
                raise ValueError("raw_sha256 does not resolve")
            if row.get("query_id") != query_id:
                raise ValueError("query_id mismatch")
            if row.get("coverage_scope") != "OFFICIAL_SCHEDULE_DATES_ONLY":
                raise ValueError("coverage_scope cannot claim action type or factor completeness")
            if not str(row.get("source_url", "")).startswith("https://"):
                raise ValueError("source_url must be HTTPS")
        except (TypeError, ValueError) as exc:
            errors.append(f"corporate_action_row_{index}:{exc}")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "rows": len(values),
        "pending_factor_rows": pending_factors,
        "errors": sorted(set(errors)),
        "coverage_scope": "OFFICIAL_SCHEDULE_DATES_ONLY",
        "corporate_action_factor_ledger_ready": not values,
        "action_type_complete": not values,
    }


__all__ = [
    "CORPORATE_ACTION_ENRICHMENT_HEADERS",
    "CORPORATE_ACTION_SCHEDULE_HEADERS",
    "DELISTING_ARCHIVE_HEADERS",
    "QUERY_LEDGER_HEADERS",
    "SECURITY_STATUS_EVIDENCE_HEADERS",
    "validate_corporate_action_schedule_rows",
    "validate_delisting_archive_rows",
    "validate_security_status_evidence_rows",
    "write_csv",
]
