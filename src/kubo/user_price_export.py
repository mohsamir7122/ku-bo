from __future__ import annotations

import csv
import json
import os
import stat
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .atomic_output import run_atomic_output
from .hashing import canonical_json_bytes, sha256_bytes
from .price_collection_workspace import MANIFEST_HEADERS
from .research_price_history import (
    ResearchPriceRow,
    validate_research_price_history_rows,
    write_research_price_history,
)
from .strict import https_url, parse_aware, parse_iso_date, require_sha256
from .tri_security_admission import (
    BoundaryAdmissionRequest,
    admit_boundary,
    build_boundary_operation_binding,
)
from .vendor_symbol_mapping import VendorSymbolMapping, VendorSymbolMappingCatalog


INVESTING_EXPORT_HEADERS = (
    "Date",
    "Price",
    "Open",
    "High",
    "Low",
    "Vol.",
    "Change %",
)
KUWAIT = ZoneInfo("Asia/Kuwait")
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_EXPORT_ROWS = 50_000
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_ROWS = 10_000
_CHANGE_TOLERANCE = Decimal("0.06")



def _reject_symlink_components(path: Path, field: str) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise ValueError(f"{field} is missing or unreadable: {path}") from exc
        if stat.S_ISLNK(mode):
            raise ValueError(f"{field} must not contain symlinks: {path}")
    return absolute



def _read_regular_file_once(path: Path, *, field: str, max_bytes: int) -> bytes:
    absolute = _reject_symlink_components(path, field)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise ValueError(f"cannot open {field}: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{field} must be a regular file")
        if metadata.st_size > max_bytes:
            raise ValueError(f"{field} exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"{field} exceeds {max_bytes} bytes")
        after = os.fstat(descriptor)
        if (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError(f"{field} changed while being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)



def _dict_rows_from_csv(
    content: bytes,
    *,
    field: str,
    expected_headers: tuple[str, ...],
    max_rows: int,
) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field} must be UTF-8 CSV") from exc
    reader = csv.DictReader(StringIO(text, newline=""))
    headers = tuple(reader.fieldnames or ())
    if headers != expected_headers:
        raise ValueError(
            f"{field} headers must exactly match: " + ",".join(expected_headers)
        )
    rows: list[dict[str, str]] = []
    for row in reader:
        if None in row:
            raise ValueError(f"{field} contains a row wider than its header")
        rows.append({key: str(value or "").strip() for key, value in row.items()})
        if len(rows) > max_rows:
            raise ValueError(f"{field} exceeds {max_rows} rows")
    return rows



def _decimal(value: str, field: str) -> Decimal:
    cleaned = value.replace(",", "").strip().replace("%", "").replace("+", "")
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed



def _volume(value: str) -> int:
    cleaned = value.replace(",", "").strip().upper()
    suffix = cleaned[-1:] if cleaned else ""
    multiplier = Decimal(1)
    if suffix in {"K", "M", "B"}:
        cleaned = cleaned[:-1]
        multiplier = {
            "K": Decimal(1_000),
            "M": Decimal(1_000_000),
            "B": Decimal(1_000_000_000),
        }[suffix]
    parsed = _decimal(cleaned, "Vol.")
    total = parsed * multiplier
    if total < 0 or total != total.to_integral_value():
        raise ValueError("Vol. must resolve to a whole non-negative number")
    return int(total)



def _row_date(value: str) -> date:
    text = value.strip()
    for format_string in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, format_string).date()
        except ValueError:
            continue
    raise ValueError(f"Date must be Investing-style or ISO: {value}")



def _parse_investing_rows(content: bytes) -> list[dict[str, Any]]:
    rows = _dict_rows_from_csv(
        content,
        field="Investing CSV export",
        expected_headers=INVESTING_EXPORT_HEADERS,
        max_rows=MAX_EXPORT_ROWS,
    )
    if len(rows) < 2:
        raise ValueError("Investing CSV export must contain at least two rows")
    parsed: list[dict[str, Any]] = []
    seen_dates: set[date] = set()
    previous_day: date | None = None
    for index, row in enumerate(rows, start=1):
        day = _row_date(row["Date"])
        if day in seen_dates:
            raise ValueError(f"duplicate Date in CSV export: {day.isoformat()}")
        if previous_day is not None and day >= previous_day:
            raise ValueError("CSV export rows must be newest-first")
        seen_dates.add(day)
        previous_day = day
        close = _decimal(row["Price"], "Price")
        open_price = _decimal(row["Open"], "Open")
        high = _decimal(row["High"], "High")
        low = _decimal(row["Low"], "Low")
        volume = _volume(row["Vol."])
        change_percent = _decimal(row["Change %"], "Change %")
        if min(close, open_price, high, low) <= 0:
            raise ValueError(f"non-positive OHLC value at CSV row {index}")
        if high < max(close, open_price, low) or low > min(close, open_price, high):
            raise ValueError(f"impossible OHLC row at CSV row {index}")
        parsed.append(
            {
                "trade_date": day,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "change_percent": change_percent,
            }
        )
    for current, prior in zip(parsed, parsed[1:]):
        calculated = ((current["close"] - prior["close"]) / prior["close"]) * Decimal(100)
        if abs(calculated - current["change_percent"]) > _CHANGE_TOLERANCE:
            raise ValueError(
                "Change % does not reconcile for "
                + current["trade_date"].isoformat()
            )
    return parsed



def _manifest_path(input_dir: Path) -> Path:
    candidates = (
        input_dir / "price_collection_manifest.csv",
        input_dir.parent / "manifests" / "price_collection_manifest.csv",
        input_dir.parent.parent / "manifests" / "price_collection_manifest.csv",
    )
    present = [candidate for candidate in candidates if candidate.exists() or candidate.is_symlink()]
    unique = list(dict.fromkeys(Path(os.path.abspath(candidate)) for candidate in present))
    if not unique:
        raise ValueError("price_collection_manifest.csv is required")
    if len(unique) != 1:
        raise ValueError("multiple price_collection_manifest.csv files make provenance ambiguous")
    return unique[0]



def _load_manifest(
    input_dir: Path,
    catalog: VendorSymbolMappingCatalog,
) -> tuple[Path, dict[str, dict[str, str]], bytes]:
    path = _manifest_path(input_dir)
    content = _read_regular_file_once(
        path,
        field="collection manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    rows = _dict_rows_from_csv(
        content,
        field="collection manifest",
        expected_headers=MANIFEST_HEADERS,
        max_rows=MAX_MANIFEST_ROWS,
    )
    if not rows:
        raise ValueError("collection manifest must contain at least one row")
    known_tickers = {
        mapping.ticker for mapping in catalog.capture_candidates("investing")
    }
    by_ticker: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        ticker = row["ticker"].upper()
        if not ticker:
            raise ValueError(f"collection manifest row {index} requires ticker")
        if ticker in by_ticker:
            raise ValueError(f"duplicate collection manifest ticker: {ticker}")
        if ticker not in known_tickers:
            raise ValueError(f"unknown collection manifest ticker: {ticker}")
        by_ticker[ticker] = row
    return path, by_ticker, content



def _positive_int(value: str, field: str, *, maximum: int) -> int:
    if not value.isdigit():
        raise ValueError(f"{field} must be a positive integer")
    parsed = int(value)
    if parsed <= 0 or parsed > maximum:
        raise ValueError(f"{field} must be between 1 and {maximum}")
    return parsed



def _validate_manifest_row(
    *,
    mapping: VendorSymbolMapping,
    catalog: VendorSymbolMappingCatalog,
    row: dict[str, str],
    export_bytes: bytes,
    parsed_rows: list[dict[str, Any]],
    observed: datetime,
) -> dict[str, str]:
    identity = catalog.identities.identities[mapping.ticker]
    expected_identity = {
        "ticker": mapping.ticker,
        "security_code": mapping.security_code,
        "isin": mapping.isin,
        "name_en": identity.name_en,
        "sector": identity.sector,
    }
    for field, expected in expected_identity.items():
        actual = row[field].upper() if field in {"ticker", "isin"} else row[field]
        expected_value = expected.upper() if field in {"ticker", "isin"} else expected
        if actual != expected_value:
            raise ValueError(f"manifest {field} does not match the pilot catalogs")
    if row["source_name"].casefold() != "investing":
        raise ValueError("manifest source_name must be investing")
    if row["source_type"] not in {
        "SECONDARY_MANUAL_EXPORT",
        "SECONDARY_RAW_PRICE_EXPORT",
    }:
        raise ValueError("manifest source_type is not approved for an Investing export")
    source_url = https_url(row["source_url_or_location"], "source_url_or_location")
    if source_url != mapping.provider_url:
        raise ValueError("manifest source_url_or_location does not match vendor mapping")
    downloaded = parse_aware(row["downloaded_at"], "downloaded_at")
    if downloaded > observed:
        raise ValueError("manifest downloaded_at must not be after observed_at")
    if not row["downloaded_by"]:
        raise ValueError("manifest downloaded_by is required")
    expected_name = f"{mapping.ticker}.csv"
    if row["file_name"] != expected_name:
        raise ValueError(f"manifest file_name must be {expected_name}")
    expected_hash = require_sha256(row["file_sha256"], "file_sha256")
    actual_hash = sha256_bytes(export_bytes)
    if expected_hash != actual_hash:
        raise ValueError("manifest file_sha256 does not match the CSV bytes")

    dates = [item["trade_date"] for item in parsed_rows]
    date_start = parse_iso_date(row["date_range_start"], "date_range_start")
    date_end = parse_iso_date(row["date_range_end"], "date_range_end")
    if date_start > date_end:
        raise ValueError("manifest date range is reversed")
    if date_start != min(dates) or date_end != max(dates):
        raise ValueError("manifest date range does not match the CSV sessions")
    if date_end > observed.astimezone(KUWAIT).date():
        raise ValueError("latest CSV session exceeds observed_at in Asia/Kuwait")
    if date_end > downloaded.astimezone(KUWAIT).date():
        raise ValueError("latest CSV session exceeds downloaded_at in Asia/Kuwait")
    if _positive_int(row["row_count"], "row_count", maximum=MAX_EXPORT_ROWS) != len(parsed_rows):
        raise ValueError("manifest row_count does not match the CSV")

    price_basis = row["price_basis"].upper()
    if price_basis not in {"RAW", "ADJUSTED"}:
        raise ValueError("manifest price_basis must be RAW or ADJUSTED")
    if row["currency"] != "KWD":
        raise ValueError("manifest currency must be KWD")
    if row["unit"] not in {"fils", "KWD"}:
        raise ValueError("manifest unit must be fils or KWD")
    if row["allowed_use"] != "USER_EXPORT":
        raise ValueError("manifest allowed_use must be USER_EXPORT")
    if row["review_status"] != "ACCEPTED":
        raise ValueError("manifest review_status must be ACCEPTED")
    return {
        "source_url": source_url,
        "downloaded_at": downloaded.isoformat(),
        "price_basis": price_basis,
        "currency": row["currency"],
        "unit": row["unit"],
        "raw_sha256": actual_hash,
    }



def _prepare_output_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:-1]:
        current /= component
        if current.exists() and current.is_symlink():
            raise ValueError("output_root parent must not contain symlinks")
    if absolute.exists() or absolute.is_symlink():
        if absolute.is_symlink() or not absolute.is_dir():
            raise ValueError("output_root must be a real directory")
        if any(absolute.iterdir()):
            raise ValueError("output_root must be empty to preserve prior evidence")
    else:
        absolute.mkdir(parents=True, exist_ok=False)
    return absolute



def _import_investing_user_exports_unchecked(
    *,
    config_dir: Path,
    input_dir: Path,
    output_root: Path,
    observed_at: str,
    decision_at: str | None = None,
    logical_output_root: Path | None = None,
) -> dict[str, Any]:
    observed = parse_aware(observed_at, "observed_at")
    decision = parse_aware(decision_at or observed_at, "decision_at")
    if observed > decision:
        raise ValueError("observed_at must not be after decision_at")
    input_dir = Path(input_dir)
    if not input_dir.is_dir() or input_dir.is_symlink():
        raise ValueError("input_dir must be a real directory")
    output_root = _prepare_output_root(Path(output_root))
    logical_output = (
        Path(os.path.abspath(logical_output_root))
        if logical_output_root is not None
        else output_root
    )

    catalog = VendorSymbolMappingCatalog(config_dir)
    candidates = sorted(
        catalog.capture_candidates("investing"),
        key=lambda mapping: mapping.ticker,
    )
    raw_dir = output_root / "raw"
    normalized_dir = output_root / "normalized"
    report_dir = output_root / "reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    manifest_errors: list[str] = []
    manifest_path: Path | None = None
    manifest_rows: dict[str, dict[str, str]] = {}
    manifest_bytes: bytes | None = None
    try:
        manifest_path, manifest_rows, manifest_bytes = _load_manifest(input_dir, catalog)
    except ValueError as exc:
        manifest_errors.append(str(exc))

    imported_symbols: list[str] = []
    missing_exports: list[str] = []
    rejected_exports: dict[str, str] = {}
    normalized_rows: list[ResearchPriceRow] = []
    manifest_artifacts: list[dict[str, Any]] = []
    downloaded_times: dict[str, str] = {}

    for mapping in candidates:
        export_path = input_dir / f"{mapping.ticker}.csv"
        if not export_path.exists() and not export_path.is_symlink():
            missing_exports.append(mapping.ticker)
            continue
        try:
            manifest_row = manifest_rows.get(mapping.ticker)
            if manifest_row is None:
                raise ValueError("an accepted collection manifest row is required")
            export_bytes = _read_regular_file_once(
                export_path,
                field=f"{mapping.ticker} CSV export",
                max_bytes=MAX_EXPORT_BYTES,
            )
            parsed_rows = _parse_investing_rows(export_bytes)
            metadata = _validate_manifest_row(
                mapping=mapping,
                catalog=catalog,
                row=manifest_row,
                export_bytes=export_bytes,
                parsed_rows=parsed_rows,
                observed=observed,
            )
            preserved_path = raw_dir / f"{mapping.ticker}.investing_export.csv"
            preserved_path.write_bytes(export_bytes)
            manifest_artifacts.append(
                {
                    "path": preserved_path.relative_to(output_root).as_posix(),
                    "sha256": metadata["raw_sha256"],
                    "size_bytes": len(export_bytes),
                    "source_id": "investing_history",
                    "source_url": metadata["source_url"],
                    "observed_at": metadata["downloaded_at"],
                    "capture_kind": "USER_EXPORT",
                    "artifact_role": "ORIGINAL_USER_EXPORT",
                }
            )
            corporate_action_status = (
                "raw_unadjusted"
                if metadata["price_basis"] == "RAW"
                else "provider_adjusted_method_unverified"
            )
            for row in parsed_rows:
                normalized_rows.append(
                    ResearchPriceRow(
                        trade_date=row["trade_date"],
                        security_code=mapping.security_code,
                        ticker=mapping.ticker,
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        change_percent=row["change_percent"],
                        source_id="investing_history",
                        source_url=metadata["source_url"],
                        raw_sha256=metadata["raw_sha256"],
                        capture_mode="USER_EXPORT",
                        price_basis=metadata["price_basis"],
                        currency=metadata["currency"],
                        unit=metadata["unit"],
                        corporate_action_status=corporate_action_status,
                    )
                )
            imported_symbols.append(mapping.ticker)
            downloaded_times[mapping.ticker] = metadata["downloaded_at"]
        except (OSError, TypeError, ValueError) as exc:
            rejected_exports[mapping.ticker] = str(exc)

    normalized_path = normalized_dir / "research_price_history.csv"
    write_research_price_history(normalized_path, normalized_rows)
    parsed_rows, validation = validate_research_price_history_rows(
        [row.to_csv_dict() for row in normalized_rows],
        manifest_hashes=frozenset(item["sha256"] for item in manifest_artifacts),
    )
    del parsed_rows

    evidence_manifest = {
        "schema_version": "3.0",
        "artifacts": manifest_artifacts,
    }
    (output_root / "manifest.json").write_bytes(canonical_json_bytes(evidence_manifest))
    source_observations = {
        "schema_version": "3.0",
        "sources": (
            [
                {
                    "source_id": "investing_history",
                    "state": "AVAILABLE",
                    "access_mode": "USER_EXPORT",
                    "attempted_at": observed.isoformat(),
                    "query_status": (
                        "QUALIFIED" if validation.status == "PASS" else "DATA_QUALITY_REJECTED"
                    ),
                    "roles_observed": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
                    "qualified_items": validation.rows if validation.status == "PASS" else 0,
                    "zero_result": False,
                    "raw_sha256s": sorted(
                        item["sha256"] for item in manifest_artifacts
                    ),
                    "data_quality_flags": (
                        [] if validation.status == "PASS" else ["RESEARCH_PRICE_HISTORY_VALIDATION_FAILED"]
                    ),
                    "limitations": [
                        "SECONDARY_PRICE_HISTORY_ONLY",
                        "OFFICIAL_IDENTITY_ARTIFACT_REQUIRED",
                        "TRADING_CALENDAR_REQUIRED",
                        "CORPORATE_ACTION_LEDGER_REQUIRED",
                        "BENCHMARK_REQUIRED",
                    ],
                    "entitlement_id": "",
                }
            ]
            if manifest_artifacts
            else []
        ),
    }
    (output_root / "source_observations.json").write_bytes(
        canonical_json_bytes(source_observations)
    )

    preserved_manifest_path: Path | None = None
    if manifest_bytes is not None:
        preserved_manifest_path = output_root / "price_collection_manifest.csv"
        preserved_manifest_path.write_bytes(manifest_bytes)

    all_prices_ready = bool(candidates) and (
        len(imported_symbols) == len(candidates)
        and not missing_exports
        and not rejected_exports
        and not manifest_errors
        and validation.status == "PASS"
    )
    if all_prices_ready:
        price_history_status = "RESEARCH_PRICE_HISTORY_READY"
    elif normalized_rows:
        price_history_status = "PARTIAL"
    else:
        price_history_status = "BLOCKED"

    official_identity_ready = catalog.identities.official_identity_ready
    if price_history_status == "RESEARCH_PRICE_HISTORY_READY" and not official_identity_ready:
        status = "BLOCKED_OFFICIAL_IDENTITY"
    else:
        status = price_history_status

    data_quality_report = validation.to_dict()
    data_quality_report.update(
        {
            "imported_symbols": imported_symbols,
            "missing_exports": missing_exports,
            "rejected_exports": rejected_exports,
            "manifest_errors": manifest_errors,
            "downloaded_at_by_symbol": dict(sorted(downloaded_times.items())),
        }
    )
    data_quality_path = report_dir / "data_quality_report.json"
    data_quality_path.write_bytes(canonical_json_bytes(data_quality_report))

    report = {
        "schema_version": "1.0",
        "status": status,
        "price_history_status": price_history_status,
        "capture_mode": "USER_EXPORT",
        "decision_at": decision.isoformat(),
        "observed_at": observed.isoformat(),
        "output_root": str(logical_output),
        "collection_manifest": str(manifest_path) if manifest_path else None,
        "preserved_collection_manifest": (
            str(logical_output / "price_collection_manifest.csv")
            if preserved_manifest_path
            else None
        ),
        "collection_manifest_sha256": (
            sha256_bytes(manifest_bytes) if manifest_bytes is not None else None
        ),
        "manifest_errors": manifest_errors,
        "imported_symbols": imported_symbols,
        "missing_exports": missing_exports,
        "rejected_exports": rejected_exports,
        "normalized_research_price_history": str(
            logical_output / "normalized" / "research_price_history.csv"
        ),
        "data_quality_report": str(
            logical_output / "reports" / "data_quality_report.json"
        ),
        "row_count": len(normalized_rows),
        "official_identity_ready": official_identity_ready,
        "remaining_gates": [
            "OFFICIAL_IDENTITY_ARTIFACT",
            "EFFECTIVE_DATED_IDENTITY_BINDINGS",
            "TRADING_CALENDAR",
            "SECURITY_STATUS_HISTORY",
            "CORPORATE_ACTION_LEDGER",
            "BENCHMARK_HISTORY",
        ],
        "claim_boundaries": {
            "provider_prices_are_secondary": True,
            "vendor_mapping_is_official_identity": False,
            "seed_identity_is_official_evidence": False,
            "research_price_history_is_complete_daily_eod": False,
            "no_synthetic_market_fields_created": True,
            "no_forward_fill_used": True,
            "forecast_generated": False,
            "probability_generated": False,
            "recommendation_generated": False,
            "accuracy_claimed": False,
            "backtest_ready": False,
        },
    }
    report_path = report_dir / "user_export_import_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


def import_investing_user_exports(
    *,
    config_dir: Path,
    input_dir: Path,
    output_root: Path,
    observed_at: str,
    decision_at: str,
    admission_request: BoundaryAdmissionRequest,
) -> dict[str, Any]:
    target = Path(os.path.abspath(output_root))
    operation_binding = build_boundary_operation_binding(
        "import_user_price_exports",
        decision_at=decision_at,
        observed_at=observed_at,
    )
    token = admit_boundary(
        admission_request,
        boundary_id="import_user_price_exports",
        output_root=target,
        boundary_inputs={
            "config_dir": config_dir,
            "input_dir": input_dir,
        },
        operation_binding=operation_binding,
    )

    def worker(staging: Path) -> dict[str, Any]:
        report = _import_investing_user_exports_unchecked(
            config_dir=config_dir,
            input_dir=input_dir,
            output_root=staging,
            observed_at=observed_at,
            decision_at=decision_at,
            logical_output_root=target,
        )
        token.materialize_receipt(staging)
        token.materialize_lineage(staging)
        return report

    return run_atomic_output(
        target,
        worker,
        before_commit=lambda _staging: token.revalidate_before_commit(),
    )


__all__ = [
    "INVESTING_EXPORT_HEADERS",
    "import_investing_user_exports",
]
