from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from io import StringIO
import os
from pathlib import Path
import stat
from typing import Any
from zoneinfo import ZoneInfo

from .hashing import canonical_json_bytes, sha256_bytes
from .price_collection_workspace import MANIFEST_HEADERS
from .source_parsers import PriceRecord, parse_investing_history_html
from .strict import https_url, parse_aware, parse_iso_date, require_sha256
from .symbol_mapping import SymbolMapping, SymbolMappingCatalog


INVESTING_EXPORT_HEADERS = ("Date", "Price", "Open", "High", "Low", "Vol.", "Change %")
KUWAIT = ZoneInfo("Asia/Kuwait")
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_EXPORT_ROWS = 50_000
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_ROWS = 10_000
NORMALIZED_EOD_HEADERS = (
    "trade_date",
    "security_code",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "change_percent",
    "source_id",
    "source_url",
    "raw_sha256",
    "capture_mode",
    "price_basis",
    "currency",
    "unit",
    "corporate_action_status",
)


@dataclass(frozen=True)
class ImportedPriceExport:
    mapping: SymbolMapping
    raw_path: Path
    normalized_html_path: Path
    raw_sha256: str
    normalized_sha256: str
    rows: tuple[PriceRecord, ...]
    source_url: str
    downloaded_at: str
    price_basis: str
    currency: str
    unit: str


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
        multiplier = {"K": Decimal(1_000), "M": Decimal(1_000_000), "B": Decimal(1_000_000_000)}[suffix]
    parsed = _decimal(cleaned, "Vol.")
    total = parsed * multiplier
    if total < 0 or total != total.to_integral_value():
        raise ValueError("Vol. must resolve to a whole non-negative number")
    return int(total)


def _row_date(value: str) -> str:
    text = value.strip()
    for format_string in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, format_string).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Date must be Investing-style or ISO: {value}")


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
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError(f"{field} exceeds {max_bytes} bytes")
        return content
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
        raise ValueError(f"{field} headers must exactly match: " + ",".join(expected_headers))
    rows: list[dict[str, str]] = []
    for row in reader:
        if None in row:
            raise ValueError(f"{field} contains a row wider than its header")
        rows.append({key: str(value or "").strip() for key, value in row.items()})
        if len(rows) > max_rows:
            raise ValueError(f"{field} exceeds {max_rows} rows")
    return rows


def _read_export_rows(content: bytes) -> list[dict[str, str]]:
    rows = _dict_rows_from_csv(
        content,
        field="Investing CSV export",
        expected_headers=INVESTING_EXPORT_HEADERS,
        max_rows=MAX_EXPORT_ROWS,
    )
    if len(rows) < 2:
        raise ValueError("Investing CSV export must contain at least two rows")
    return rows


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
    catalog: SymbolMappingCatalog,
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
    by_ticker: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        ticker = row["ticker"].upper()
        if not ticker:
            raise ValueError(f"collection manifest row {index} requires ticker")
        if ticker in by_ticker:
            raise ValueError(f"duplicate collection manifest ticker: {ticker}")
        if ticker not in catalog.mappings:
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
    mapping: SymbolMapping,
    row: dict[str, str],
    export_bytes: bytes,
    rows: list[dict[str, str]],
    observed: datetime,
) -> dict[str, str]:
    expected_identity = {
        "ticker": mapping.boursa_symbol,
        "security_code": mapping.security_code,
        "isin": mapping.isin,
        "name_en": mapping.name_en,
        "sector": mapping.sector,
    }
    for field, expected in expected_identity.items():
        actual = row[field].upper() if field in {"ticker", "isin"} else row[field]
        expected_value = expected.upper() if field in {"ticker", "isin"} else expected
        if not expected_value or actual != expected_value:
            raise ValueError(f"manifest {field} does not match symbol_mapping")
    if row["source_name"].casefold() != "investing":
        raise ValueError("manifest source_name must be investing")
    if row["source_type"] not in {"SECONDARY_MANUAL_EXPORT", "SECONDARY_RAW_PRICE_EXPORT"}:
        raise ValueError("manifest source_type is not approved for an Investing user export")
    source_url = https_url(row["source_url_or_location"], "manifest source_url_or_location")
    expected_url = https_url(mapping.investing_url, "investing_url")
    if source_url != expected_url:
        raise ValueError("manifest source_url_or_location does not match symbol_mapping")
    downloaded = parse_aware(row["downloaded_at"], "manifest downloaded_at")
    if downloaded > observed:
        raise ValueError("manifest downloaded_at must not be after observed_at")
    if not row["downloaded_by"]:
        raise ValueError("manifest downloaded_by is required")
    expected_name = f"{mapping.boursa_symbol}.csv"
    if row["file_name"] != expected_name:
        raise ValueError(f"manifest file_name must be {expected_name}")
    expected_hash = require_sha256(row["file_sha256"], "manifest file_sha256")
    actual_hash = sha256_bytes(export_bytes)
    if expected_hash != actual_hash:
        raise ValueError("manifest file_sha256 does not match the CSV bytes")
    actual_dates = tuple(_row_date(item["Date"]) for item in rows)
    date_start = parse_iso_date(row["date_range_start"], "manifest date_range_start")
    date_end = parse_iso_date(row["date_range_end"], "manifest date_range_end")
    if date_start > date_end:
        raise ValueError("manifest date range is reversed")
    if date_start != date.fromisoformat(min(actual_dates)) or date_end != date.fromisoformat(max(actual_dates)):
        raise ValueError("manifest date range does not match the CSV sessions")
    if date_end > observed.astimezone(KUWAIT).date():
        raise ValueError("latest CSV session exceeds observed_at in Asia/Kuwait")
    if date_end > downloaded.astimezone(KUWAIT).date():
        raise ValueError("latest CSV session exceeds manifest downloaded_at in Asia/Kuwait")
    if _positive_int(row["row_count"], "manifest row_count", maximum=MAX_EXPORT_ROWS) != len(rows):
        raise ValueError("manifest row_count does not match the CSV")
    price_basis = row["price_basis"].upper()
    if price_basis not in {"RAW", "ADJUSTED"}:
        raise ValueError("manifest price_basis must be RAW or ADJUSTED for import")
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


def _html_from_investing_csv(mapping: SymbolMapping, rows: list[dict[str, str]]) -> bytes:
    if not mapping.isin:
        raise ValueError(f"{mapping.boursa_symbol} requires ISIN before USER_EXPORT import")
    body_rows: list[str] = []
    seen_dates: set[str] = set()
    previous_date = "9999-12-31"
    for index, row in enumerate(rows, start=1):
        session_date = _row_date(row["Date"])
        if session_date in seen_dates:
            raise ValueError(f"duplicate Date in CSV export: {session_date}")
        if session_date >= previous_date:
            raise ValueError("CSV export rows must be newest-first")
        seen_dates.add(session_date)
        previous_date = session_date
        close = _decimal(row["Price"], "Price")
        open_price = _decimal(row["Open"], "Open")
        high = _decimal(row["High"], "High")
        low = _decimal(row["Low"], "Low")
        _volume(row["Vol."])
        _decimal(row["Change %"], "Change %")
        if min(close, open_price, high, low) <= 0 or high < max(close, open_price, low) or low > min(close, open_price, high):
            raise ValueError(f"impossible OHLC row at CSV row {index}")
        cells = "".join(
            f"<td>{escape(str(row[header]))}</td>"
            for header in INVESTING_EXPORT_HEADERS
        )
        body_rows.append(f"<tr>{cells}</tr>")
    html = (
        "<!doctype html><html lang=\"en\"><head><title>USER_EXPORT Investing history</title></head>"
        "<body>"
        f"<h1>{escape(mapping.name_en)} ({escape(mapping.boursa_symbol)})</h1>"
        f"<dl><dt>ISIN</dt><dd>{escape(mapping.isin)}</dd></dl>"
        "<table><thead><tr>"
        "<th>Date</th><th>Price</th><th>Open</th><th>High</th><th>Low</th><th>Vol.</th><th>Change %</th>"
        "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></body></html>\n"
    )
    return html.encode("utf-8")


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def import_investing_user_exports(
    *,
    config_dir: Path,
    input_dir: Path,
    output_root: Path,
    observed_at: str,
    product_id: str = "next_session_rank",
    decision_at: str | None = None,
) -> dict[str, Any]:
    observed = parse_aware(observed_at, "observed_at")
    decision = parse_aware(decision_at or observed_at, "decision_at")
    if observed > decision:
        raise ValueError("observed_at must not be after decision_at")
    catalog = SymbolMappingCatalog(config_dir)
    if output_root.exists() or output_root.is_symlink():
        if output_root.is_symlink() or not output_root.is_dir():
            raise ValueError("output_root must be a non-symlink directory")
        if any(output_root.iterdir()):
            raise ValueError("output_root must be empty to preserve an existing evidence pack")
    else:
        output_root.mkdir(parents=True, exist_ok=False)
    raw_dir = output_root / "raw"
    normalized_dir = output_root / "normalized"
    imported: list[ImportedPriceExport] = []
    missing: list[str] = []
    rejected: dict[str, str] = {}
    manifest_errors: list[str] = []
    manifest_path: Path | None = None
    manifest_bytes: bytes | None = None
    manifest_rows: dict[str, dict[str, str]] = {}
    try:
        manifest_path, manifest_rows, manifest_bytes = _load_manifest(input_dir, catalog)
    except ValueError as exc:
        manifest_errors.append(str(exc))

    candidates = catalog.capture_candidates()
    for mapping in candidates:
        export_path = input_dir / f"{mapping.boursa_symbol}.csv"
        if not export_path.exists() and not export_path.is_symlink():
            missing.append(mapping.boursa_symbol)
            continue
        try:
            manifest_row = manifest_rows.get(mapping.boursa_symbol)
            if manifest_row is None:
                raise ValueError("an accepted collection manifest row is required")
            export_bytes = _read_regular_file_once(
                export_path,
                field=f"{mapping.boursa_symbol} CSV export",
                max_bytes=MAX_EXPORT_BYTES,
            )
            rows = _read_export_rows(export_bytes)
            metadata = _validate_manifest_row(
                mapping=mapping,
                row=manifest_row,
                export_bytes=export_bytes,
                rows=rows,
                observed=observed,
            )
            html = _html_from_investing_csv(mapping, rows)
            instrument = parse_investing_history_html(html)

            html_path = raw_dir / f"{mapping.boursa_symbol}.investing_history.html"
            raw_path = raw_dir / f"{mapping.boursa_symbol}.investing_export.csv"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_bytes(html)
            # The source file is never opened again. The preserved artifact and
            # its digest are derived from the exact bytes that were validated.
            raw_path.write_bytes(export_bytes)
            imported.append(
                ImportedPriceExport(
                    mapping=mapping,
                    raw_path=raw_path,
                    normalized_html_path=html_path,
                    raw_sha256=metadata["raw_sha256"],
                    normalized_sha256=sha256_bytes(html),
                    rows=instrument.rows,
                    source_url=metadata["source_url"],
                    downloaded_at=metadata["downloaded_at"],
                    price_basis=metadata["price_basis"],
                    currency=metadata["currency"],
                    unit=metadata["unit"],
                )
            )
        except ValueError as exc:
            rejected[mapping.boursa_symbol] = str(exc)

    eod_rows: list[dict[str, Any]] = []
    manifest_artifacts: list[dict[str, Any]] = []
    secondary_parser_tasks: list[dict[str, str]] = []
    for item in imported:
        raw_relative = item.raw_path.relative_to(output_root).as_posix()
        html_relative = item.normalized_html_path.relative_to(output_root).as_posix()
        manifest_artifacts.extend(
            [
                {
                    "path": raw_relative,
                    "sha256": item.raw_sha256,
                    "size_bytes": item.raw_path.stat().st_size,
                    "source_id": "investing_history",
                    "source_url": item.source_url,
                    "observed_at": item.downloaded_at,
                    "capture_kind": "USER_EXPORT",
                    "artifact_role": "ORIGINAL_USER_EXPORT",
                },
                {
                    "path": html_relative,
                    "sha256": item.normalized_sha256,
                    "size_bytes": item.normalized_html_path.stat().st_size,
                    "source_id": "investing_history",
                    "source_url": item.source_url,
                    "observed_at": item.downloaded_at,
                    "capture_kind": "USER_EXPORT",
                    "artifact_role": "PARSER_CONTRACT_HTML",
                },
            ]
        )
        secondary_parser_tasks.append(
            {
                "parser_id": "investing_history_html_v1",
                "source_id": "investing_history",
                "artifact_sha256": item.normalized_sha256,
            }
        )
        for row in item.rows:
            eod_rows.append(
                {
                    "trade_date": row.session_date,
                    "security_code": item.mapping.security_code,
                    "ticker": item.mapping.boursa_symbol,
                    "open": str(row.open),
                    "high": str(row.high),
                    "low": str(row.low),
                    "close": str(row.close),
                    "volume": row.volume,
                    "change_percent": str(row.change_percent),
                    "source_id": "investing_history",
                    "source_url": item.source_url,
                    "raw_sha256": item.raw_sha256,
                    "capture_mode": "USER_EXPORT",
                    "price_basis": item.price_basis,
                    "currency": item.currency,
                    "unit": item.unit,
                    "corporate_action_status": (
                        "raw_unadjusted"
                        if item.price_basis == "RAW"
                        else "provider_adjusted_method_unverified"
                    ),
                }
            )

    eod_rows.sort(key=lambda row: (row["trade_date"], row["ticker"]))
    _write_csv(normalized_dir / "eod_ohlcv.csv", NORMALIZED_EOD_HEADERS, eod_rows)
    manifest = {"schema_version": "3.0", "artifacts": manifest_artifacts}
    sources: list[dict[str, Any]] = []
    if imported:
        limitations = ["SECONDARY_PRICE_HISTORY_ONLY", "OFFICIAL_IDENTITY_ARTIFACT_REQUIRED"]
        if any(item.price_basis == "RAW" for item in imported):
            limitations.append("CORPORATE_ACTION_LEDGER_REQUIRED_FOR_RAW_PRICES")
        if any(item.price_basis == "ADJUSTED" for item in imported):
            limitations.append("PROVIDER_ADJUSTMENT_METHOD_UNVERIFIED")
        sources.append(
            {
                "source_id": "investing_history",
                "state": "AVAILABLE",
                "access_mode": "USER_EXPORT",
                "attempted_at": observed.isoformat(),
                "query_status": "DATA_QUALITY_REJECTED",
                "roles_observed": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
                "qualified_items": 0,
                "zero_result": False,
                "raw_sha256s": sorted(
                    digest
                    for item in imported
                    for digest in (item.raw_sha256, item.normalized_sha256)
                ),
                "data_quality_flags": ["RAW_CAPTURE_PENDING_PARSER_VALIDATION"],
                "limitations": limitations,
                "entitlement_id": "",
            }
        )
    observations = {"schema_version": "3.0", "sources": sources}
    parser_plan_draft = {
        "draft_schema_version": "1.0",
        "status": "BLOCKED_REQUIREMENTS",
        "materialization_ready": False,
        "run_id": output_root.name,
        "product_id": product_id,
        "decision_at": decision.isoformat(),
        "scope": "NAMED_SECURITIES",
        "captured_secondary_artifacts": secondary_parser_tasks,
        "identity_candidates": [
            {
                "security_code": item.mapping.security_code,
                "ticker": item.mapping.boursa_symbol,
                "isin": item.mapping.isin,
                "secondary_artifact_sha256": item.normalized_sha256,
            }
            for item in imported
        ],
        "missing_requirements": [
            {
                "requirement_id": "OFFICIAL_IDENTITY_ARTIFACT",
                "source_id": "boursa_current",
                "parser_id": "boursa_identity_html_v1",
                "detail": "One fresh official membership artifact must bind every security code and ISIN.",
            },
            {
                "requirement_id": "EFFECTIVE_DATED_IDENTITY_BINDINGS",
                "detail": "Binding validity dates must come from official evidence; no date is inferred by this importer.",
            },
        ],
        "next_step": "Build a validated parser plan only after official identity evidence and effective-dated bindings are supplied.",
    }
    (output_root / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    (output_root / "source_observations.json").write_bytes(canonical_json_bytes(observations))
    preserved_manifest_path: Path | None = None
    if manifest_bytes is not None:
        preserved_manifest_path = output_root / "price_collection_manifest.csv"
        preserved_manifest_path.write_bytes(manifest_bytes)
    draft_path = output_root / "parser_plan_investing_user_export_draft.json"
    draft_path.write_bytes(canonical_json_bytes(parser_plan_draft))

    complete = (
        bool(imported)
        and len(imported) == len(candidates)
        and not missing
        and not rejected
        and not manifest_errors
    )
    status = "PRICE_IMPORT_READY_ONLY" if complete else "PARTIAL" if imported else "BLOCKED"
    report = {
        "status": status,
        "capture_mode": "USER_EXPORT",
        "output_root": str(output_root),
        "collection_manifest": str(manifest_path) if manifest_path is not None else None,
        "preserved_collection_manifest": (
            str(preserved_manifest_path) if preserved_manifest_path is not None else None
        ),
        "collection_manifest_sha256": (
            sha256_bytes(manifest_bytes) if manifest_bytes is not None else None
        ),
        "manifest_errors": manifest_errors,
        "imported_symbols": [item.mapping.boursa_symbol for item in imported],
        "missing_exports": missing,
        "rejected_exports": rejected,
        "normalized_eod": str(normalized_dir / "eod_ohlcv.csv"),
        "parser_plan_draft": str(draft_path),
        "parser_materialization_ready": False,
        "row_count": len(eod_rows),
        "claim_boundaries": {
            "provider_prices_are_secondary": True,
            "corporate_action_ledger_not_supplied": True,
            "official_identity_artifact_not_supplied": True,
            "not_a_trading_recommendation": True,
            "backtest_requires_real_point_in_time_exports": True,
        },
    }
    (output_root / "user_export_import_report.json").write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "INVESTING_EXPORT_HEADERS",
    "NORMALIZED_EOD_HEADERS",
    "import_investing_user_exports",
]
