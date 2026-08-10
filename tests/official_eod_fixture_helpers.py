from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from kubo.hashing import canonical_json_bytes
from kubo.official_eod_workspace import (
    RAW_DAILY_MARKET_TOTAL_HEADERS,
    RAW_OFFICIAL_EOD_HEADERS,
    SECURITY_MASTER_HEADERS,
    STATUS_INTERVAL_HEADERS,
    STATUS_QUERY_HEADERS,
    TRADING_CALENDAR_HEADERS,
)


SECURITIES = {
    "101": "NBK",
    "108": "KFH",
    "413": "MABANEE",
    "605": "ZAIN",
    "623": "HUMANSOFT",
}
SESSIONS = ("2026-08-08", "2026-08-09")
OFFICIAL_URL = "https://www.boursakuwait.com.kw/"


def _write_csv(path: Path, headers: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(headers), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _evidence_root(root: Path, *, stage: str) -> str:
    raw = root / "raw" / "evidence.official"
    raw.parent.mkdir(parents=True, exist_ok=True)
    content = f"recorded authorized {stage} contract fixture".encode("utf-8")
    raw.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    (root / "manifest.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "3.0",
                "artifacts": [
                    {
                        "path": "raw/evidence.official",
                        "sha256": digest,
                        "size_bytes": len(content),
                        "source_id": "boursa_kuwait",
                        "source_url": OFFICIAL_URL,
                        "observed_at": "2026-08-09T16:00:00+03:00",
                        "capture_kind": "USER_EXPORT",
                        "artifact_role": stage,
                    }
                ],
            }
        )
    )
    return digest


def build_eod_upstreams(root: Path) -> tuple[Path, Path]:
    official = root / "official-output"
    official.mkdir()
    official_hash = _evidence_root(official, stage="OFFICIAL_FOUNDATION_FIXTURE")
    master_rows = []
    for index, (code, ticker) in enumerate(SECURITIES.items()):
        master_rows.append(
            {
                "security_code": code,
                "ticker": ticker,
                "isin": f"KW0{index + 1:09d}",
                "name_ar": "",
                "name_en": f"{ticker} fixture",
                "board": "cash",
                "market_segment": "PREMIER" if code in {"101", "108"} else "MAIN",
                "currency": "KWD",
                "valid_from": "2026-08-08",
                "valid_to": "",
                "listing_status": "ACTIVE",
                "raw_sha256": official_hash,
                "supporting_raw_sha256s": "",
                "listing_date": "2000-01-01",
                "identity_scope": "CURRENT_SNAPSHOT_ONLY",
            }
        )
    _write_csv(
        official / "normalized" / "security_master.csv",
        SECURITY_MASTER_HEADERS,
        master_rows,
    )
    calendar_rows = []
    for day in ("2026-08-07", *SESSIONS):
        calendar_rows.append(
            {
                "trade_date": day,
                "is_trading_day": "true",
                "session_type": "NORMAL",
                "session_regime_id": "CASH-2025-10-12",
                "continuous_start": "09:00:00",
                "continuous_end": "12:30:00",
                "trade_at_last_end": "12:40:00",
                "raw_sha256": official_hash,
                "supporting_raw_sha256s": "",
                "holiday_name": "",
            }
        )
    _write_csv(
        official / "normalized" / "trading_calendar.csv",
        TRADING_CALENDAR_HEADERS,
        calendar_rows,
    )
    (official / "reports").mkdir()
    (official / "reports" / "official_foundation_import_report.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "1.0",
                "status": "CURRENT_IDENTITY_AND_CALENDAR_READY",
                "run_id": "official-eod-fixture",
                "calendar_window_from": "2026-08-07",
                "calendar_window_to": "2026-08-09",
                "identity_snapshot_effective_date": "2026-08-08",
            }
        )
    )

    history = root / "history-output"
    history.mkdir()
    history_hash = _evidence_root(history, stage="STATUS_HISTORY_FIXTURE")
    status_by_code = {
        "101": "TRADING",
        "108": "SUSPENDED",
        "413": "TRADING",
        "605": "DELISTED",
        "623": "TRADING",
    }
    interval_rows = []
    query_rows = []
    for code, ticker in SECURITIES.items():
        interval_rows.append(
            {
                "security_code": code,
                "ticker": ticker,
                "status": status_by_code[code],
                "effective_from": "2026-08-07",
                "effective_to": "2026-08-09",
                "opening_evidence_sha256": history_hash,
                "start_notice_id": "WINDOW_OPEN",
                "end_notice_id": "WINDOW_CLOSE",
                "evidence_hashes": history_hash,
            }
        )
        query_rows.append(
            {
                "query_id": f"fixture:{code}",
                "security_code": code,
                "ticker": ticker,
                "window_from": "2026-08-07",
                "window_to": "2026-08-09",
                "pages_declared": "1",
                "pages_received": "1",
                "result_count_declared": "0",
                "rows_normalized": "0",
                "zero_result": "true",
                "raw_sha256": history_hash,
                "source_url": OFFICIAL_URL,
            }
        )
    _write_csv(
        history / "normalized" / "status_intervals.csv",
        STATUS_INTERVAL_HEADERS,
        interval_rows,
    )
    _write_csv(
        history / "manifests" / "status_query_ledger.csv",
        STATUS_QUERY_HEADERS,
        query_rows,
    )
    (history / "reports").mkdir()
    (history / "reports" / "status_history_import_report.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "1.0",
                "status": "HISTORICAL_STATUS_INTERVALS_READY",
                "run_id": "status-history-eod-fixture",
                "history_window_from": "2026-08-07",
                "history_window_to": "2026-08-09",
            }
        )
    )
    return official, history


def complete_eod_rows() -> list[dict[str, str]]:
    states = {
        ("2026-08-08", "101"): "TRADED",
        ("2026-08-08", "108"): "SUSPENDED",
        ("2026-08-08", "413"): "HALTED",
        ("2026-08-08", "605"): "NOT_LISTED_OR_NOT_ELIGIBLE",
        ("2026-08-08", "623"): "TRADED",
        ("2026-08-09", "101"): "NO_TRADE",
        ("2026-08-09", "108"): "TRADED_THEN_SUSPENDED",
        ("2026-08-09", "413"): "TRADED",
        ("2026-08-09", "605"): "NOT_LISTED_OR_NOT_ELIGIBLE",
        ("2026-08-09", "623"): "NO_TRADE",
    }
    rows: list[dict[str, str]] = []
    for day in SESSIONS:
        for code, ticker in SECURITIES.items():
            state = states[(day, code)]
            traded = state in {"TRADED", "TRADED_THEN_SUSPENDED"}
            rows.append(
                {
                    "trade_date": day,
                    "security_code": code,
                    "ticker": ticker,
                    "trading_state": state,
                    "open_fils": "100" if traded else "",
                    "high_fils": "110" if traded else "",
                    "low_fils": "90" if traded else "",
                    "close_fils": "105" if traded else "",
                    "volume": "10" if traded else "0",
                    "value_traded_kwd": "1.05" if traded else "0",
                    "trade_count": "1" if traded else "0",
                    "reference_price_fils": "100",
                }
            )
    return rows


def add_provider(
    workspace: Path,
    *,
    provider_id: str = "fixture-provider",
    rows: list[dict[str, str]] | None = None,
    supplied_fields: list[str] | None = None,
    evidence_classification: str = "RECORDED_AUTHORIZED_FIXTURE",
    rights_status: str = "FIXTURE_ONLY",
    source_class: str = "OFFICIAL",
    capture_mode: str | None = None,
    availability_status: str = "AVAILABLE",
    price_basis: str = "RAW_UNADJUSTED",
) -> None:
    rows = complete_eod_rows() if rows is None else rows
    supplied_fields = supplied_fields or [
        "TRADING_STATE",
        "OHLC",
        "VOLUME",
        "VALUE_TRADED_KWD",
        "TRADE_COUNT",
        "REFERENCE_PRICE",
    ]
    capture_mode = capture_mode or (
        "RECORDED_AUTHORIZED_FIXTURE"
        if evidence_classification == "RECORDED_AUTHORIZED_FIXTURE"
        else "SYNTHETIC_GENERATED"
        if evidence_classification == "SYNTHETIC_ONLY"
        else "LICENSED_VENDOR_EXPORT"
        if source_class == "LICENSED"
        else "USER_PROVIDED_OFFICIAL_EXPORT"
    )
    file_name = f"{provider_id}.csv"
    path = workspace / "raw_exports" / "providers" / file_name
    _write_csv(path, RAW_OFFICIAL_EOD_HEADERS, rows)
    content = path.read_bytes()
    manifest_path = workspace / "manifests" / "official_eod_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["providers"].append(
        {
            "provider_id": provider_id,
            "source_id": "boursa_kuwait" if source_class == "OFFICIAL" else "licensed_vendor",
            "source_url": OFFICIAL_URL if source_class == "OFFICIAL" else "https://vendor.example.com/eod",
            "source_class": source_class,
            "capture_mode": capture_mode,
            "availability_status": availability_status,
            "file_name": file_name,
            "file_sha256": hashlib.sha256(content).hexdigest(),
            "observed_at": "2026-08-09T17:00:00+03:00",
            "captured_by": "unit-test",
            "review_status": "ACCEPTED",
            "supplied_fields": supplied_fields,
            "field_origin": "OFFICIAL_SOURCE_FIELDS" if source_class == "OFFICIAL" else "LICENSED_SOURCE_FIELDS",
            "price_basis": price_basis,
            "evidence_classification": evidence_classification,
            "rights_status": rights_status,
            "pages_declared": 1,
            "pages_received": 1 if availability_status != "PARTIAL" else 0,
            "result_count_declared": len(rows),
            "rows_normalized": len(rows),
            "zero_result": False,
            "subject_id": "" if source_class == "OFFICIAL" else "licensed-subject",
            "entitlement_id": "" if source_class == "OFFICIAL" else "licensed-entitlement",
        }
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest))


def add_matching_market_totals(workspace: Path, *, mismatch: bool = False) -> None:
    rows = [
        {
            "trade_date": day,
            "board": "cash",
            "scope": "DECLARED_PILOT",
            "traded_security_count": "3" if mismatch and day == SESSIONS[0] else "2",
            "total_volume": "20",
            "total_value_kwd": "2.10",
            "total_trade_count": "2",
        }
        for day in SESSIONS
    ]
    path = workspace / "raw_exports" / "market_totals" / "pilot-totals.csv"
    _write_csv(path, RAW_DAILY_MARKET_TOTAL_HEADERS, rows)
    content = path.read_bytes()
    manifest_path = workspace / "manifests" / "official_eod_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["market_totals"] = {
        "provider_id": "fixture-totals",
        "source_id": "boursa_kuwait",
        "source_url": OFFICIAL_URL,
        "source_class": "OFFICIAL",
        "capture_mode": "RECORDED_AUTHORIZED_FIXTURE",
        "availability_status": "AVAILABLE",
        "file_name": "pilot-totals.csv",
        "file_sha256": hashlib.sha256(content).hexdigest(),
        "observed_at": "2026-08-09T17:05:00+03:00",
        "captured_by": "unit-test",
        "review_status": "ACCEPTED",
        "scope": "DECLARED_PILOT",
        "board": "cash",
        "evidence_classification": "RECORDED_AUTHORIZED_FIXTURE",
        "rights_status": "FIXTURE_ONLY",
        "pages_declared": 1,
        "pages_received": 1,
        "result_count_declared": 2,
        "rows_normalized": 2,
        "zero_result": False,
        "subject_id": "",
        "entitlement_id": "",
    }
    manifest_path.write_bytes(canonical_json_bytes(manifest))


__all__ = [
    "SECURITIES",
    "SESSIONS",
    "add_matching_market_totals",
    "add_provider",
    "build_eod_upstreams",
    "complete_eod_rows",
]
