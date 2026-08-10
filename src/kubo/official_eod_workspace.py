from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from .foundation_io import (
    load_strict_json_object,
    nonnegative_int,
    prepare_output_root,
    read_csv_bytes,
    require_real_directory,
    safe_regular_file,
)
from .hashing import canonical_json_bytes, sha256_bytes
from .strict import https_url, parse_iso_date, require_sha256, safe_relative_path


OFFICIAL_EOD_MANIFEST_SCHEMA_VERSION = "1.0"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

SECURITY_MASTER_HEADERS = (
    "security_code",
    "ticker",
    "isin",
    "name_ar",
    "name_en",
    "board",
    "market_segment",
    "currency",
    "valid_from",
    "valid_to",
    "listing_status",
    "raw_sha256",
    "supporting_raw_sha256s",
    "listing_date",
    "identity_scope",
)
TRADING_CALENDAR_HEADERS = (
    "trade_date",
    "is_trading_day",
    "session_type",
    "session_regime_id",
    "continuous_start",
    "continuous_end",
    "trade_at_last_end",
    "raw_sha256",
    "supporting_raw_sha256s",
    "holiday_name",
)
STATUS_INTERVAL_HEADERS = (
    "security_code",
    "ticker",
    "status",
    "effective_from",
    "effective_to",
    "opening_evidence_sha256",
    "start_notice_id",
    "end_notice_id",
    "evidence_hashes",
)
STATUS_QUERY_HEADERS = (
    "query_id",
    "security_code",
    "ticker",
    "window_from",
    "window_to",
    "pages_declared",
    "pages_received",
    "result_count_declared",
    "rows_normalized",
    "zero_result",
    "raw_sha256",
    "source_url",
)

RAW_OFFICIAL_EOD_HEADERS = (
    "trade_date",
    "security_code",
    "ticker",
    "trading_state",
    "open_fils",
    "high_fils",
    "low_fils",
    "close_fils",
    "volume",
    "value_traded_kwd",
    "trade_count",
    "reference_price_fils",
)
RAW_DAILY_MARKET_TOTAL_HEADERS = (
    "trade_date",
    "board",
    "scope",
    "traded_security_count",
    "total_volume",
    "total_value_kwd",
    "total_trade_count",
)

EVIDENCE_CLASSIFICATIONS = frozenset(
    {
        "PROVEN_REAL_EVIDENCE",
        "RECORDED_AUTHORIZED_FIXTURE",
        "SYNTHETIC_ONLY",
        "PARTIAL",
        "BLOCKED",
        "LIVE_DEPENDENT",
        "LICENSED_FEED_DEPENDENT",
    }
)
RIGHTS_STATUSES = frozenset(
    {"RESEARCH_USE_AUTHORIZED", "FIXTURE_ONLY", "UNKNOWN", "RESTRICTED"}
)
TRADING_STATES = frozenset(
    {
        "TRADED",
        "NO_TRADE",
        "SUSPENDED",
        "HALTED",
        "TRADED_THEN_SUSPENDED",
        "NOT_LISTED_OR_NOT_ELIGIBLE",
    }
)
SUPPLIED_FIELD_GROUPS = frozenset(
    {
        "TRADING_STATE",
        "OHLC",
        "VOLUME",
        "VALUE_TRADED_KWD",
        "TRADE_COUNT",
        "REFERENCE_PRICE",
    }
)
PRICE_BASES = frozenset({"RAW_UNADJUSTED", "OFFICIALLY_ADJUSTED"})
SOURCE_CLASSES = frozenset({"OFFICIAL", "LICENSED"})
CAPTURE_MODES = frozenset(
    {
        "PUBLIC_OFFICIAL_DOWNLOAD",
        "USER_PROVIDED_OFFICIAL_EXPORT",
        "LICENSED_VENDOR_EXPORT",
        "RECORDED_AUTHORIZED_FIXTURE",
        "SYNTHETIC_GENERATED",
    }
)
PROVIDER_AVAILABILITY = frozenset(
    {"AVAILABLE", "PARTIAL", "ZERO_RESULT", "UNAVAILABLE"}
)
MARKET_TOTALS_AVAILABILITY = frozenset(
    {"AVAILABLE", "PARTIAL", "ZERO_RESULT", "NOT_AVAILABLE_FROM_SOURCE"}
)


@dataclass(frozen=True)
class UpstreamContext:
    receipt: dict[str, Any]
    identities: tuple[dict[str, Any], ...]
    calendar: dict[date, dict[str, str]]
    sessions: tuple[date, ...]
    status_intervals: tuple[dict[str, Any], ...]
    security_codes: tuple[str, ...]


def _csv_bool(value: Any, field: str) -> bool:
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(f"{field} must be true or false")


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _hash_list(value: Any, field: str) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    values = tuple(require_sha256(item, field) for item in text.split("|"))
    if len(values) != len(set(values)):
        raise ValueError(f"{field} contains duplicate hashes")
    return values


def _load_evidence_manifest(
    root: Path,
    *,
    stage: str,
) -> tuple[dict[str, Any], bytes, frozenset[str]]:
    manifest, manifest_bytes = load_strict_json_object(
        root / "manifest.json",
        field=f"{stage} evidence manifest",
    )
    if set(manifest) != {"schema_version", "artifacts"}:
        raise ValueError(f"{stage} evidence manifest has unknown or missing fields")
    if manifest["schema_version"] != "3.0":
        raise ValueError(f"unsupported {stage} evidence manifest schema")
    rows = manifest["artifacts"]
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{stage} evidence manifest must contain artifacts")
    required = {
        "path",
        "sha256",
        "size_bytes",
        "source_id",
        "source_url",
        "observed_at",
        "capture_kind",
        "artifact_role",
    }
    seen_paths: set[str] = set()
    hashes: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError(f"{stage} artifact {index} lacks required fields")
        if any(key not in required for key in row):
            raise ValueError(f"{stage} artifact {index} has unknown fields")
        relative = safe_relative_path(row["path"], f"{stage} artifacts[{index}].path")
        path_text = relative.as_posix()
        if path_text in seen_paths:
            raise ValueError(f"{stage} evidence manifest contains duplicate paths")
        seen_paths.add(path_text)
        digest = require_sha256(row["sha256"], f"{stage} artifacts[{index}].sha256")
        content = safe_regular_file(
            root / relative,
            field=f"{stage} artifact {path_text}",
        )
        if sha256_bytes(content) != digest:
            raise ValueError(f"{stage} artifact hash mismatch: {path_text}")
        size = nonnegative_int(row["size_bytes"], f"{stage} artifacts[{index}].size_bytes")
        if size != len(content):
            raise ValueError(f"{stage} artifact size mismatch: {path_text}")
        _nonempty_string(row["source_id"], f"{stage} artifacts[{index}].source_id")
        https_url(row["source_url"], f"{stage} artifacts[{index}].source_url")
        _nonempty_string(row["observed_at"], f"{stage} artifacts[{index}].observed_at")
        _nonempty_string(row["capture_kind"], f"{stage} artifacts[{index}].capture_kind")
        _nonempty_string(row["artifact_role"], f"{stage} artifacts[{index}].artifact_role")
        hashes.add(digest)
    return manifest, manifest_bytes, frozenset(hashes)


def _identity_for(
    identities: Iterable[dict[str, Any]],
    *,
    security_code: str,
    day: date,
) -> dict[str, Any]:
    matches = [
        row
        for row in identities
        if row["security_code"] == security_code
        and row["valid_from_date"] <= day
        and (row["valid_to_date"] is None or day <= row["valid_to_date"])
    ]
    if len(matches) != 1:
        raise ValueError(
            "point-in-time identity is missing or ambiguous; "
            "a current snapshot must not backfill historical sessions: "
            f"{security_code}:{day.isoformat()}"
        )
    return matches[0]


def status_for(
    context: UpstreamContext,
    *,
    security_code: str,
    day: date,
) -> dict[str, Any]:
    matches = [
        row
        for row in context.status_intervals
        if row["security_code"] == security_code
        and row["effective_from_date"] <= day <= row["effective_to_date"]
    ]
    if len(matches) != 1:
        raise ValueError(
            f"effective status is missing or ambiguous: {security_code}:{day.isoformat()}"
        )
    return matches[0]


def identity_for(
    context: UpstreamContext,
    *,
    security_code: str,
    day: date,
) -> dict[str, Any]:
    return _identity_for(context.identities, security_code=security_code, day=day)


def _load_official_foundation(root: Path) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], dict[date, dict[str, str]]]:
    report, report_bytes = load_strict_json_object(
        root / "reports" / "official_foundation_import_report.json",
        field="official foundation import report",
    )
    if report.get("status") != "CURRENT_IDENTITY_AND_CALENDAR_READY":
        raise ValueError("official foundation is not ready")
    report_from = parse_iso_date(report.get("calendar_window_from"), "calendar_window_from")
    report_to = parse_iso_date(report.get("calendar_window_to"), "calendar_window_to")
    snapshot_date = parse_iso_date(
        report.get("identity_snapshot_effective_date"),
        "identity_snapshot_effective_date",
    )
    _, manifest_bytes, manifest_hashes = _load_evidence_manifest(
        root, stage="official foundation"
    )
    master_bytes = safe_regular_file(
        root / "normalized" / "security_master.csv",
        field="official security_master.csv",
    )
    _, master_rows = read_csv_bytes(
        master_bytes,
        field="official security_master.csv",
        exact_headers=SECURITY_MASTER_HEADERS,
    )
    if not master_rows:
        raise ValueError("official security_master.csv is empty")
    identities: list[dict[str, Any]] = []
    for index, row in enumerate(master_rows):
        code = row["security_code"]
        ticker = row["ticker"]
        if not code.isdigit() or not ticker or ticker != ticker.upper():
            raise ValueError(f"security master row {index} has invalid identity")
        if row["board"].lower() != "cash" or row["currency"] != "KWD":
            raise ValueError(f"security master row {index} is outside the KWD cash board")
        valid_from = parse_iso_date(row["valid_from"], f"security master row {index}.valid_from")
        valid_to = (
            None
            if not row["valid_to"]
            else parse_iso_date(row["valid_to"], f"security master row {index}.valid_to")
        )
        if valid_to is not None and valid_to < valid_from:
            raise ValueError(f"security master row {index} has a reversed interval")
        if row["listing_status"] not in {
            "ACTIVE",
            "LISTED",
            "TRADING",
            "SUSPENDED",
            "HALTED",
            "DELISTED",
        }:
            raise ValueError(f"security master row {index} has invalid listing_status")
        raw_hash = require_sha256(row["raw_sha256"], f"security master row {index}.raw_sha256")
        supporting = _hash_list(
            row["supporting_raw_sha256s"],
            f"security master row {index}.supporting_raw_sha256s",
        )
        if raw_hash not in manifest_hashes or any(item not in manifest_hashes for item in supporting):
            raise ValueError(f"security master row {index} has unresolved evidence")
        identities.append(
            {
                **row,
                "security_code": code,
                "ticker": ticker,
                "valid_from_date": valid_from,
                "valid_to_date": valid_to,
            }
        )
    for index, left in enumerate(identities):
        for right in identities[index + 1 :]:
            if left["security_code"] != right["security_code"]:
                continue
            left_end = left["valid_to_date"] or date.max
            right_end = right["valid_to_date"] or date.max
            if left["valid_from_date"] <= right_end and right["valid_from_date"] <= left_end:
                raise ValueError(f"overlapping official identities: {left['security_code']}")

    calendar_bytes = safe_regular_file(
        root / "normalized" / "trading_calendar.csv",
        field="official trading_calendar.csv",
    )
    _, calendar_rows = read_csv_bytes(
        calendar_bytes,
        field="official trading_calendar.csv",
        exact_headers=TRADING_CALENDAR_HEADERS,
    )
    calendar: dict[date, dict[str, str]] = {}
    for index, row in enumerate(calendar_rows):
        day = parse_iso_date(row["trade_date"], f"calendar row {index}.trade_date")
        if day in calendar:
            raise ValueError(f"duplicate official calendar date: {day.isoformat()}")
        _csv_bool(row["is_trading_day"], f"calendar row {index}.is_trading_day")
        raw_hash = require_sha256(row["raw_sha256"], f"calendar row {index}.raw_sha256")
        supporting = _hash_list(
            row["supporting_raw_sha256s"],
            f"calendar row {index}.supporting_raw_sha256s",
        )
        if raw_hash not in manifest_hashes or any(item not in manifest_hashes for item in supporting):
            raise ValueError(f"calendar row {index} has unresolved evidence")
        calendar[day] = row
    expected_days: set[date] = set()
    current = report_from
    while current <= report_to:
        expected_days.add(current)
        current += timedelta(days=1)
    if set(calendar) != expected_days:
        raise ValueError("official calendar does not exactly cover its reported window")
    return (
        {
            "status": report["status"],
            "run_id": report.get("run_id"),
            "report_sha256": sha256_bytes(report_bytes),
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "security_master_sha256": sha256_bytes(master_bytes),
            "trading_calendar_sha256": sha256_bytes(calendar_bytes),
            "calendar_window_from": report_from.isoformat(),
            "calendar_window_to": report_to.isoformat(),
            "identity_snapshot_effective_date": snapshot_date.isoformat(),
        },
        tuple(identities),
        calendar,
    )


def _load_status_history(
    root: Path,
    *,
    expected_codes: frozenset[str],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    report, report_bytes = load_strict_json_object(
        root / "reports" / "status_history_import_report.json",
        field="status history import report",
    )
    if report.get("status") != "HISTORICAL_STATUS_INTERVALS_READY":
        raise ValueError("status history is not ready")
    report_from = parse_iso_date(report.get("history_window_from"), "history_window_from")
    report_to = parse_iso_date(report.get("history_window_to"), "history_window_to")
    _, manifest_bytes, manifest_hashes = _load_evidence_manifest(root, stage="status history")
    interval_bytes = safe_regular_file(
        root / "normalized" / "status_intervals.csv",
        field="historical status_intervals.csv",
    )
    _, interval_rows = read_csv_bytes(
        interval_bytes,
        field="historical status_intervals.csv",
        exact_headers=STATUS_INTERVAL_HEADERS,
    )
    if not interval_rows:
        raise ValueError("historical status_intervals.csv is empty")
    intervals: list[dict[str, Any]] = []
    for index, row in enumerate(interval_rows):
        code = row["security_code"]
        ticker = row["ticker"]
        if code not in expected_codes or not ticker or ticker != ticker.upper():
            raise ValueError(f"status interval row {index} has invalid identity")
        if row["status"] not in {"TRADING", "SUSPENDED", "DELISTED"}:
            raise ValueError(f"status interval row {index} has invalid status")
        start = parse_iso_date(row["effective_from"], f"status interval row {index}.effective_from")
        end = parse_iso_date(row["effective_to"], f"status interval row {index}.effective_to")
        if start > end or start < report_from or end > report_to:
            raise ValueError(f"status interval row {index} is outside the reported window")
        evidence = {
            require_sha256(
                row["opening_evidence_sha256"],
                f"status interval row {index}.opening_evidence_sha256",
            ),
            *_hash_list(row["evidence_hashes"], f"status interval row {index}.evidence_hashes"),
        }
        if any(item not in manifest_hashes for item in evidence):
            raise ValueError(f"status interval row {index} has unresolved evidence")
        intervals.append(
            {
                **row,
                "effective_from_date": start,
                "effective_to_date": end,
            }
        )

    query_bytes = safe_regular_file(
        root / "manifests" / "status_query_ledger.csv",
        field="historical status query ledger",
    )
    _, query_rows = read_csv_bytes(
        query_bytes,
        field="historical status query ledger",
        exact_headers=STATUS_QUERY_HEADERS,
    )
    query_codes: set[str] = set()
    for index, row in enumerate(query_rows):
        code = row["security_code"]
        if code not in expected_codes or code in query_codes:
            raise ValueError(f"status query row {index} has unknown or duplicate security_code")
        query_codes.add(code)
        start = parse_iso_date(row["window_from"], f"status query row {index}.window_from")
        end = parse_iso_date(row["window_to"], f"status query row {index}.window_to")
        pages_declared = nonnegative_int(row["pages_declared"], f"status query row {index}.pages_declared")
        pages_received = nonnegative_int(row["pages_received"], f"status query row {index}.pages_received")
        count = nonnegative_int(
            row["result_count_declared"],
            f"status query row {index}.result_count_declared",
        )
        normalized = nonnegative_int(
            row["rows_normalized"], f"status query row {index}.rows_normalized"
        )
        zero = _csv_bool(row["zero_result"], f"status query row {index}.zero_result")
        digest = require_sha256(row["raw_sha256"], f"status query row {index}.raw_sha256")
        https_url(row["source_url"], f"status query row {index}.source_url")
        if start != report_from or end != report_to:
            raise ValueError(f"status query row {index} does not cover the reported window")
        if pages_declared <= 0 or pages_declared != pages_received:
            raise ValueError(f"status query row {index} has incomplete pagination")
        if count != normalized or zero != (count == 0):
            raise ValueError(f"status query row {index} does not reconcile result counts")
        if digest not in manifest_hashes:
            raise ValueError(f"status query row {index} has unresolved raw evidence")
    if query_codes != set(expected_codes):
        raise ValueError("status query ledger does not cover the declared pilot codes")
    return (
        {
            "status": report["status"],
            "run_id": report.get("run_id"),
            "report_sha256": sha256_bytes(report_bytes),
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "status_intervals_sha256": sha256_bytes(interval_bytes),
            "status_query_ledger_sha256": sha256_bytes(query_bytes),
            "history_window_from": report_from.isoformat(),
            "history_window_to": report_to.isoformat(),
        },
        tuple(intervals),
    )


def load_eod_upstreams(
    *,
    official_foundation_root: Path,
    status_history_root: Path,
    window_from: date,
    window_to: date,
) -> UpstreamContext:
    if window_from > window_to:
        raise ValueError("official EOD window is reversed")
    official_root = require_real_directory(
        Path(official_foundation_root), field="official_foundation_root"
    )
    history_root = require_real_directory(
        Path(status_history_root), field="status_history_root"
    )
    official_receipt, identities, calendar = _load_official_foundation(official_root)
    if not (
        parse_iso_date(official_receipt["calendar_window_from"], "calendar_window_from")
        <= window_from
        <= window_to
        <= parse_iso_date(official_receipt["calendar_window_to"], "calendar_window_to")
    ):
        raise ValueError("official EOD window is outside the official calendar")
    security_codes = tuple(sorted({row["security_code"] for row in identities}, key=int))
    if not security_codes:
        raise ValueError("official identity denominator is empty")
    status_receipt, intervals = _load_status_history(
        history_root, expected_codes=frozenset(security_codes)
    )
    if not (
        parse_iso_date(status_receipt["history_window_from"], "history_window_from")
        <= window_from
        <= window_to
        <= parse_iso_date(status_receipt["history_window_to"], "history_window_to")
    ):
        raise ValueError("official EOD window is outside historical status coverage")
    sessions = tuple(
        sorted(
            day
            for day, row in calendar.items()
            if window_from <= day <= window_to
            and _csv_bool(row["is_trading_day"], "is_trading_day")
        )
    )
    if not sessions:
        raise ValueError("official EOD window contains no official trading sessions")
    context = UpstreamContext(
        receipt={
            "official_foundation": official_receipt,
            "status_history": status_receipt,
        },
        identities=identities,
        calendar=calendar,
        sessions=sessions,
        status_intervals=intervals,
        security_codes=security_codes,
    )
    for day in sessions:
        for code in security_codes:
            identity = identity_for(context, security_code=code, day=day)
            status = status_for(context, security_code=code, day=day)
            if identity["ticker"] != status["ticker"]:
                raise ValueError(
                    f"effective identity/status ticker mismatch: {code}:{day.isoformat()}"
                )
    return context


def _provider_template(*, prepared_by: str) -> dict[str, Any]:
    return {
        "provider_id": "replace-with-stable-provider-id",
        "source_id": "boursa_kuwait",
        "source_url": "https://www.boursakuwait.com.kw/",
        "source_class": "OFFICIAL",
        "capture_mode": "",
        "availability_status": "UNAVAILABLE",
        "file_name": "official-eod.csv",
        "file_sha256": "",
        "observed_at": "",
        "captured_by": prepared_by,
        "review_status": "PENDING",
        "supplied_fields": ["TRADING_STATE"],
        "field_origin": "OFFICIAL_SOURCE_FIELDS",
        "price_basis": "RAW_UNADJUSTED",
        "evidence_classification": "BLOCKED",
        "rights_status": "UNKNOWN",
        "pages_declared": "",
        "pages_received": "",
        "result_count_declared": "",
        "rows_normalized": "",
        "zero_result": False,
        "subject_id": "",
        "entitlement_id": "",
    }


def _market_totals_template(*, prepared_by: str) -> dict[str, Any]:
    return {
        "provider_id": "",
        "source_id": "",
        "source_url": "",
        "source_class": "OFFICIAL",
        "capture_mode": "",
        "availability_status": "NOT_AVAILABLE_FROM_SOURCE",
        "file_name": "",
        "file_sha256": "",
        "observed_at": "",
        "captured_by": prepared_by,
        "review_status": "PENDING",
        "scope": "DECLARED_PILOT",
        "board": "cash",
        "evidence_classification": "PARTIAL",
        "rights_status": "UNKNOWN",
        "pages_declared": "",
        "pages_received": "",
        "result_count_declared": "",
        "rows_normalized": "",
        "zero_result": False,
        "subject_id": "",
        "entitlement_id": "",
    }


def prepare_official_eod_workspace(
    *,
    official_foundation_root: str | Path,
    status_history_root: str | Path,
    output_root: str | Path,
    run_id: str,
    window_from: str,
    window_to: str,
    prepared_by: str = "",
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be a canonical path-safe identifier")
    start = parse_iso_date(window_from, "window_from")
    end = parse_iso_date(window_to, "window_to")
    context = load_eod_upstreams(
        official_foundation_root=Path(official_foundation_root),
        status_history_root=Path(status_history_root),
        window_from=start,
        window_to=end,
    )
    root = prepare_output_root(Path(output_root), label="official EOD workspace")
    provider_dir = root / "raw_exports" / "providers"
    totals_dir = root / "raw_exports" / "market_totals"
    manifest_dir = root / "manifests"
    report_dir = root / "reports"
    for directory in (
        provider_dir,
        totals_dir,
        manifest_dir,
        root / "normalized",
        report_dir,
        root / "quarantine",
    ):
        directory.mkdir(parents=True, exist_ok=False)

    provider_template = _provider_template(prepared_by=prepared_by)
    totals_template = _market_totals_template(prepared_by=prepared_by)
    manifest = {
        "schema_version": OFFICIAL_EOD_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "window_from": start.isoformat(),
        "window_to": end.isoformat(),
        "upstream": context.receipt,
        "providers": [],
        "market_totals": totals_template,
    }
    manifest_path = manifest_dir / "official_eod_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    (manifest_dir / "provider_template.json").write_bytes(
        canonical_json_bytes(provider_template)
    )
    (provider_dir / "official-eod.csv.placeholder").write_text(
        ",".join(RAW_OFFICIAL_EOD_HEADERS)
        + "\nReplace this placeholder with a canonical authorized export. "
        "Do not infer absent fields or states.\n",
        encoding="utf-8",
    )
    (totals_dir / "daily-market-totals.csv.placeholder").write_text(
        ",".join(RAW_DAILY_MARKET_TOTAL_HEADERS)
        + "\nUse only same-scope DECLARED_PILOT totals. Never compare a pilot aggregate "
        "to a full-market total.\n",
        encoding="utf-8",
    )
    checklist = (
        "# Official Complete Daily EOD checklist\n\n"
        "- Add one provider object per preserved official or licensed export.\n"
        "- Preserve exact bytes and bind SHA-256, HTTPS source URL, observation time, capture mode, rights, and evidence class.\n"
        "- Reconcile complete pagination and explicit zero/partial availability.\n"
        "- Declare official field groups and RAW_UNADJUSTED or OFFICIALLY_ADJUSTED basis.\n"
        "- Supply every pilot security × every official session; never backfill a current identity snapshot.\n"
        "- Keep all non-traded OHLC blank and never derive official fields from secondary data.\n"
        "- Use market totals only when their scope is exactly DECLARED_PILOT.\n"
    )
    checklist_path = report_dir / "official_eod_checklist.md"
    checklist_path.write_text(checklist, encoding="utf-8")
    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "workspace_kind": "OFFICIAL_COMPLETE_DAILY_EOD",
        "run_id": run_id,
        "output_root": str(root),
        "window_from": start.isoformat(),
        "window_to": end.isoformat(),
        "security_codes": list(context.security_codes),
        "official_session_count": len(context.sessions),
        "expected_pair_count": len(context.security_codes) * len(context.sessions),
        "manifest_path": str(manifest_path),
        "checklist_path": str(checklist_path),
        "upstream": context.receipt,
        "claim_boundaries": {
            "workspace_contains_official_eod_evidence": False,
            "placeholder_is_evidence": False,
            "current_snapshot_backfills_history": False,
            "research_price_history_is_official_eod": False,
            "complete_official_eod_ready": False,
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }
    (report_dir / "official_eod_workspace_report.json").write_bytes(
        canonical_json_bytes(report)
    )
    return report


__all__ = [
    "CAPTURE_MODES",
    "EVIDENCE_CLASSIFICATIONS",
    "MARKET_TOTALS_AVAILABILITY",
    "OFFICIAL_EOD_MANIFEST_SCHEMA_VERSION",
    "PRICE_BASES",
    "PROVIDER_AVAILABILITY",
    "RAW_DAILY_MARKET_TOTAL_HEADERS",
    "RAW_OFFICIAL_EOD_HEADERS",
    "RIGHTS_STATUSES",
    "SOURCE_CLASSES",
    "SUPPLIED_FIELD_GROUPS",
    "TRADING_STATES",
    "UpstreamContext",
    "identity_for",
    "load_eod_upstreams",
    "prepare_official_eod_workspace",
    "status_for",
]
