from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from .strict import contains_placeholder, https_url, parse_iso_date, require_sha256


RESEARCH_PRICE_HISTORY_SCHEMA_VERSION = "1.0"
RESEARCH_PRICE_HISTORY_HEADERS = (
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
_CAPTURE_MODES = frozenset({"USER_EXPORT", "RECORDED_AUTHORIZED_FIXTURE"})
_PRICE_BASES = frozenset({"RAW", "ADJUSTED"})
_UNITS = frozenset({"fils", "KWD"})
_CORPORATE_ACTION_STATES = frozenset(
    {
        "raw_unadjusted",
        "provider_adjusted_method_unverified",
        "officially_adjusted",
        "not_applicable",
        "unknown",
    }
)
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,31}$")
_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_CHANGE_TOLERANCE = Decimal("0.06")


@dataclass(frozen=True)
class ResearchPriceRow:
    trade_date: date
    security_code: str
    ticker: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change_percent: Decimal
    source_id: str
    source_url: str
    raw_sha256: str
    capture_mode: str
    price_basis: str
    currency: str
    unit: str
    corporate_action_status: str

    def to_csv_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["trade_date"] = self.trade_date.isoformat()
        for field in ("open", "high", "low", "close", "change_percent"):
            value[field] = str(value[field])
        return value


@dataclass(frozen=True)
class ResearchPriceHistoryValidation:
    status: str
    rows: int
    securities: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    coverage: dict[str, dict[str, Any]]
    claim_boundaries: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RESEARCH_PRICE_HISTORY_SCHEMA_VERSION,
            "status": self.status,
            "rows": self.rows,
            "securities": self.securities,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "coverage": self.coverage,
            "claim_boundaries": self.claim_boundaries,
        }



def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    text = str("" if value is None else value).replace(",", "").strip()
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    if positive and parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed



def _volume(value: Any) -> int:
    text = str("" if value is None else value).strip()
    if not text.isdigit():
        raise ValueError("volume must be a whole non-negative integer")
    parsed = int(text)
    if parsed < 0:
        raise ValueError("volume must be non-negative")
    return parsed



def parse_research_price_row(
    row: dict[str, Any],
    *,
    index: int,
    manifest_hashes: frozenset[str] | None = None,
) -> ResearchPriceRow:
    if any(contains_placeholder(value) for value in row.values()):
        raise ValueError("template placeholder is forbidden")
    day = parse_iso_date(row.get("trade_date"), "trade_date")
    security_code = str(row.get("security_code", "")).strip()
    ticker = str(row.get("ticker", "")).strip().upper()
    if not security_code.isdigit() or not 1 <= len(security_code) <= 12:
        raise ValueError("security_code must contain 1..12 digits")
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError("ticker must be an uppercase path-safe ASCII symbol")
    open_price = _decimal(row.get("open"), "open", positive=True)
    high = _decimal(row.get("high"), "high", positive=True)
    low = _decimal(row.get("low"), "low", positive=True)
    close = _decimal(row.get("close"), "close", positive=True)
    if high < max(open_price, close, low):
        raise ValueError("OHLC high constraint failed")
    if low > min(open_price, close, high):
        raise ValueError("OHLC low constraint failed")
    volume = _volume(row.get("volume"))
    change_percent = _decimal(row.get("change_percent"), "change_percent")
    source_id = str(row.get("source_id", "")).strip()
    if not _SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("source_id is invalid")
    source_url = https_url(row.get("source_url"), "source_url")
    raw_sha256 = require_sha256(row.get("raw_sha256"), "raw_sha256")
    if manifest_hashes is not None and raw_sha256 not in manifest_hashes:
        raise ValueError("raw_sha256 does not resolve in the supplied manifest")
    capture_mode = str(row.get("capture_mode", "")).strip().upper()
    if capture_mode not in _CAPTURE_MODES:
        raise ValueError("unsupported capture_mode")
    price_basis = str(row.get("price_basis", "")).strip().upper()
    if price_basis not in _PRICE_BASES:
        raise ValueError("price_basis must be RAW or ADJUSTED")
    currency = str(row.get("currency", "")).strip().upper()
    if currency != "KWD":
        raise ValueError("currency must be KWD")
    unit = str(row.get("unit", "")).strip()
    if unit not in _UNITS:
        raise ValueError("unit must be fils or KWD")
    corporate_action_status = str(row.get("corporate_action_status", "")).strip()
    if corporate_action_status not in _CORPORATE_ACTION_STATES:
        raise ValueError("corporate_action_status is invalid")
    if price_basis == "RAW" and corporate_action_status != "raw_unadjusted":
        raise ValueError("RAW prices must remain raw_unadjusted")
    if (
        price_basis == "ADJUSTED"
        and corporate_action_status
        not in {"provider_adjusted_method_unverified", "officially_adjusted"}
    ):
        raise ValueError("ADJUSTED prices require an explicit adjustment status")
    return ResearchPriceRow(
        trade_date=day,
        security_code=security_code,
        ticker=ticker,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        change_percent=change_percent,
        source_id=source_id,
        source_url=source_url,
        raw_sha256=raw_sha256,
        capture_mode=capture_mode,
        price_basis=price_basis,
        currency=currency,
        unit=unit,
        corporate_action_status=corporate_action_status,
    )



def validate_research_price_history_rows(
    rows: Iterable[dict[str, Any]],
    *,
    manifest_hashes: frozenset[str] | None = None,
) -> tuple[tuple[ResearchPriceRow, ...], ResearchPriceHistoryValidation]:
    raw_rows = list(rows)
    errors: list[str] = []
    warnings: list[str] = []
    parsed: list[ResearchPriceRow] = []
    keys: set[tuple[date, str, str]] = set()
    for index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            errors.append(f"row_{index}:row must be an object")
            continue
        try:
            item = parse_research_price_row(
                row,
                index=index,
                manifest_hashes=manifest_hashes,
            )
            key = (item.trade_date, item.security_code, item.source_id)
            if key in keys:
                raise ValueError("duplicate security/session/source key")
            keys.add(key)
            parsed.append(item)
        except (TypeError, ValueError) as exc:
            errors.append(f"row_{index}:{exc}")

    grouped: dict[str, list[ResearchPriceRow]] = {}
    for item in parsed:
        grouped.setdefault(item.security_code, []).append(item)
    coverage: dict[str, dict[str, Any]] = {}
    for security_code, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.trade_date)
        tickers = {item.ticker for item in ordered}
        units = {item.unit for item in ordered}
        bases = {item.price_basis for item in ordered}
        sources = {item.source_id for item in ordered}
        if len(tickers) != 1:
            errors.append(f"security_{security_code}:ticker changes require official identity history")
        if len(units) != 1:
            errors.append(f"security_{security_code}:mixed price units")
        if len(bases) != 1:
            errors.append(f"security_{security_code}:mixed RAW and ADJUSTED prices")
        for prior, current in zip(ordered, ordered[1:]):
            expected = ((current.close - prior.close) / prior.close) * Decimal(100)
            if abs(expected - current.change_percent) > _CHANGE_TOLERANCE:
                errors.append(
                    f"security_{security_code}:change_percent mismatch:{current.trade_date.isoformat()}"
                )
        coverage[security_code] = {
            "ticker": ordered[0].ticker,
            "row_count": len(ordered),
            "date_start": ordered[0].trade_date.isoformat(),
            "date_end": ordered[-1].trade_date.isoformat(),
            "zero_volume_rows": sum(item.volume == 0 for item in ordered),
            "units": sorted(units),
            "price_bases": sorted(bases),
            "source_ids": sorted(sources),
        }

    if parsed:
        warnings.extend(
            [
                "TRADING_CALENDAR_NOT_SUPPLIED_GAPS_NOT_CLASSIFIED",
                "SECURITY_STATUS_HISTORY_NOT_SUPPLIED",
                "BENCHMARK_NOT_SUPPLIED",
                "CORPORATE_ACTION_LEDGER_REQUIRED_BEFORE_RETURN_ANALYSIS",
            ]
        )
    if not raw_rows:
        errors.append("RESEARCH_PRICE_HISTORY_EMPTY")
    status = "PASS" if parsed and not errors else "BLOCKED"
    validation = ResearchPriceHistoryValidation(
        status=status,
        rows=len(parsed),
        securities=len(grouped),
        errors=tuple(sorted(set(errors))),
        warnings=tuple(sorted(set(warnings))),
        coverage=coverage,
        claim_boundaries={
            "research_price_history_is_complete_daily_eod": False,
            "missing_session_is_zero_volume": False,
            "derived_trade_count_is_official": False,
            "derived_value_traded_is_official": False,
            "provider_adjusted_price_is_officially_adjusted": False,
            "backtest_ready": False,
        },
    )
    return tuple(parsed), validation



def read_research_price_history(
    path: Path,
    *,
    manifest_hashes: frozenset[str] | None = None,
) -> tuple[tuple[ResearchPriceRow, ...], ResearchPriceHistoryValidation]:
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = tuple(reader.fieldnames or ())
            if headers != RESEARCH_PRICE_HISTORY_HEADERS:
                raise ValueError(
                    "research price history headers must exactly match the v1 contract"
                )
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, ValueError) as exc:
        validation = ResearchPriceHistoryValidation(
            status="BLOCKED",
            rows=0,
            securities=0,
            errors=(f"RESEARCH_PRICE_HISTORY_READ:{exc}",),
            warnings=(),
            coverage={},
            claim_boundaries={
                "research_price_history_is_complete_daily_eod": False,
                "missing_session_is_zero_volume": False,
                "derived_trade_count_is_official": False,
                "derived_value_traded_is_official": False,
                "provider_adjusted_price_is_officially_adjusted": False,
                "backtest_ready": False,
            },
        )
        return (), validation
    return validate_research_price_history_rows(rows, manifest_hashes=manifest_hashes)



def write_research_price_history(
    path: Path,
    rows: Iterable[ResearchPriceRow],
) -> None:
    ordered = sorted(
        rows,
        key=lambda item: (item.trade_date, item.security_code, item.source_id),
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=RESEARCH_PRICE_HISTORY_HEADERS,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in ordered:
            writer.writerow(row.to_csv_dict())


__all__ = [
    "RESEARCH_PRICE_HISTORY_HEADERS",
    "RESEARCH_PRICE_HISTORY_SCHEMA_VERSION",
    "ResearchPriceHistoryValidation",
    "ResearchPriceRow",
    "parse_research_price_row",
    "read_research_price_history",
    "validate_research_price_history_rows",
    "write_research_price_history",
]
