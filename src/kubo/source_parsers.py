from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html.parser import HTMLParser
import re
from typing import Any


MAX_PARSER_BYTES = 10 * 1024 * 1024
ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b")
TICKER_RE = re.compile(r"\(([A-Z0-9._-]{1,32})\)")


class ParserDriftError(ValueError):
    """Raised when captured bytes no longer match a parser's declared contract."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        message = code if not detail else f"{code}:{detail}"
        super().__init__(message)


@dataclass(frozen=True)
class IdentityRecord:
    security_code: str
    name: str
    isin: str


@dataclass(frozen=True)
class PriceRecord:
    session_date: str
    close: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    volume: int
    change_percent: Decimal


@dataclass(frozen=True)
class InvestingInstrument:
    ticker: str
    isin: str
    rows: tuple[PriceRecord, ...]


class _TableCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.headings: list[str] = []
        self.document_text: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._heading: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "table" and self._table is None:
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []
        elif tag in {"h1", "h2"}:
            self._heading = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(_clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None
        elif tag in {"h1", "h2"} and self._heading is not None:
            heading = _clean_text("".join(self._heading))
            if heading:
                self.headings.append(heading)
            self._heading = None

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.document_text.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if self._heading is not None:
            self._heading.append(data)


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _decode_html(content: bytes) -> str:
    if not isinstance(content, bytes) or not content:
        raise ParserDriftError("EMPTY_CAPTURE")
    if len(content) > MAX_PARSER_BYTES:
        raise ParserDriftError("PARSER_INPUT_TOO_LARGE")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParserDriftError("NON_UTF8_CAPTURE") from exc
    lowered = text[: 256 * 1024].casefold()
    if any(
        marker in lowered
        for marker in (
            "verify you are human",
            "class=\"g-recaptcha\"",
            "hcaptcha",
            "cf-chl-",
            "subscribe to continue",
            "type=\"password\"",
        )
    ):
        raise ParserDriftError("ACCESS_BLOCKER_CAPTURED")
    return text


def _collect(content: bytes) -> _TableCollector:
    collector = _TableCollector()
    try:
        collector.feed(_decode_html(content))
        collector.close()
    except ParserDriftError:
        raise
    except Exception as exc:  # HTMLParser may surface malformed entity errors.
        raise ParserDriftError("MALFORMED_HTML") from exc
    return collector


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", value.casefold()).strip()


def _find_table(
    tables: list[list[list[str]]],
    required_headers: dict[str, set[str]],
) -> tuple[dict[str, int], list[list[str]]]:
    for table in tables:
        if len(table) < 2:
            continue
        normalized = [_normalized_header(item) for item in table[0]]
        indexes: dict[str, int] = {}
        for canonical, aliases in required_headers.items():
            positions = [index for index, value in enumerate(normalized) if value in aliases]
            if len(positions) != 1:
                break
            indexes[canonical] = positions[0]
        if len(indexes) == len(required_headers):
            return indexes, table[1:]
    raise ParserDriftError("REQUIRED_TABLE_HEADERS_NOT_FOUND")


def parse_boursa_identity_html(content: bytes) -> tuple[IdentityRecord, ...]:
    """Parse the official Boursa security-code/name/ISIN table.

    The parser deliberately does not infer tickers. A downstream materializer
    must reconcile the official code/ISIN pair with an independently captured
    ticker/ISIN pair before it can write ``universe.json``.
    """

    collector = _collect(content)
    indexes, rows = _find_table(
        collector.tables,
        {
            "security_code": {"sec code", "security code"},
            "name": {"name", "company name"},
            "isin": {"isin", "isin code"},
        },
    )
    result: list[IdentityRecord] = []
    seen_codes: set[str] = set()
    seen_isins: set[str] = set()
    maximum_index = max(indexes.values())
    for row_index, row in enumerate(rows, start=1):
        if len(row) <= maximum_index:
            raise ParserDriftError("SHORT_IDENTITY_ROW", str(row_index))
        code = row[indexes["security_code"]].strip()
        name = _clean_text(row[indexes["name"]])
        isin = row[indexes["isin"]].strip().upper()
        if not code.isdigit() or not name or not ISIN_RE.fullmatch(isin):
            raise ParserDriftError("INVALID_IDENTITY_ROW", str(row_index))
        if code in seen_codes or isin in seen_isins:
            raise ParserDriftError("DUPLICATE_IDENTITY_ROW", str(row_index))
        seen_codes.add(code)
        seen_isins.add(isin)
        result.append(IdentityRecord(code, name, isin))
    if not result:
        raise ParserDriftError("ZERO_IDENTITY_ROWS")
    return tuple(result)


def _decimal(value: str, field: str) -> Decimal:
    cleaned = value.replace(",", "").strip()
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParserDriftError("INVALID_NUMERIC_FIELD", field) from exc
    if not parsed.is_finite():
        raise ParserDriftError("NON_FINITE_NUMERIC_FIELD", field)
    return parsed


def _volume(value: str) -> int:
    cleaned = value.replace(",", "").strip().upper()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB]?)", cleaned)
    if not match:
        raise ParserDriftError("INVALID_VOLUME")
    multiplier = {"": Decimal(1), "K": Decimal(1_000), "M": Decimal(1_000_000), "B": Decimal(1_000_000_000)}[
        match.group(2)
    ]
    value_decimal = Decimal(match.group(1)) * multiplier
    if value_decimal < 0 or value_decimal != value_decimal.to_integral_value():
        raise ParserDriftError("INVALID_VOLUME")
    return int(value_decimal)


def _session_date(value: str) -> str:
    for format_string in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), format_string).date().isoformat()
        except ValueError:
            continue
    raise ParserDriftError("INVALID_SESSION_DATE", value)


def parse_investing_history_html(content: bytes) -> InvestingInstrument:
    """Parse one Investing.com historical page without calling undocumented APIs."""

    collector = _collect(content)
    document = _clean_text(" ".join(collector.document_text)).upper()
    ticker_candidates = {
        match.group(1).upper()
        for heading in collector.headings
        for match in TICKER_RE.finditer(heading.upper())
    }
    isin_candidates = set(ISIN_RE.findall(document))
    if len(ticker_candidates) != 1 or len(isin_candidates) != 1:
        raise ParserDriftError("AMBIGUOUS_OR_MISSING_INSTRUMENT_IDENTITY")
    ticker = next(iter(ticker_candidates))
    isin = next(iter(isin_candidates))
    indexes, rows = _find_table(
        collector.tables,
        {
            "date": {"date"},
            "price": {"price", "close"},
            "open": {"open"},
            "high": {"high"},
            "low": {"low"},
            "volume": {"vol", "volume"},
            "change": {"change %", "change"},
        },
    )
    parsed_rows: list[PriceRecord] = []
    maximum_index = max(indexes.values())
    seen_dates: set[str] = set()
    for row_index, row in enumerate(rows, start=1):
        if len(row) <= maximum_index:
            raise ParserDriftError("SHORT_PRICE_ROW", str(row_index))
        session_date = _session_date(row[indexes["date"]])
        close = _decimal(row[indexes["price"]], "price")
        open_price = _decimal(row[indexes["open"]], "open")
        high = _decimal(row[indexes["high"]], "high")
        low = _decimal(row[indexes["low"]], "low")
        change_text = row[indexes["change"]].strip().replace("%", "").replace("+", "")
        change = _decimal(change_text, "change_percent")
        volume = _volume(row[indexes["volume"]])
        if min(close, open_price, high, low) <= 0 or high < max(close, open_price, low) or low > min(close, open_price, high):
            raise ParserDriftError("IMPOSSIBLE_OHLC_ROW", str(row_index))
        if session_date in seen_dates:
            raise ParserDriftError("DUPLICATE_SESSION_DATE", session_date)
        seen_dates.add(session_date)
        parsed_rows.append(PriceRecord(session_date, close, open_price, high, low, volume, change))
    if len(parsed_rows) < 2:
        raise ParserDriftError("INSUFFICIENT_PRICE_ROWS")
    if parsed_rows != sorted(parsed_rows, key=lambda item: item.session_date, reverse=True):
        raise ParserDriftError("PRICE_ROWS_NOT_DESCENDING")
    for current, prior in zip(parsed_rows, parsed_rows[1:]):
        calculated = ((current.close - prior.close) / prior.close) * Decimal(100)
        if abs(calculated - current.change_percent) > Decimal("0.06"):
            raise ParserDriftError("CHANGE_PERCENT_RECONCILIATION_FAILED", current.session_date)
    return InvestingInstrument(ticker, isin, tuple(parsed_rows))


def investing_price_finding(
    instrument: InvestingInstrument,
    *,
    security_code: str,
    source_url: str,
    raw_sha256: str,
    observed_at: datetime,
    capture_mode: str,
) -> dict[str, Any]:
    latest = instrument.rows[0]
    change = float(latest.change_percent)
    if change > 0.05:
        direction = "POSITIVE"
    elif change < -0.05:
        direction = "NEGATIVE"
    else:
        direction = "NEUTRAL"
    strength = round(min(abs(change) / 5.0, 1.0), 6)
    materiality = round(min(abs(change) / 3.0, 1.0), 6)
    identity = f"{security_code}\0{latest.session_date}\0{raw_sha256}".encode("utf-8")
    stable_id = sha256(identity).hexdigest()[:20]
    return {
        "finding_id": f"investing-price-{stable_id}",
        "security_code": security_code,
        "ticker": instrument.ticker,
        "source_id": "investing_history",
        "source_url": source_url,
        "published_at": observed_at.isoformat(),
        "available_at": observed_at.isoformat(),
        "capture_mode": capture_mode,
        "timing_grade": "C",
        "raw_sha256": raw_sha256,
        "evidence_roles": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
        "signal_kind": "PRICE_ACTIVITY",
        "direction": direction,
        "strength": strength,
        "materiality": materiality,
        "origin_id": f"investing-history:{instrument.ticker}:{latest.session_date}",
        "event_key": f"secondary-close:{security_code}:{latest.session_date}",
        "claim_text": (
            f"Provider historical row for {instrument.ticker} on {latest.session_date}: "
            f"close={latest.close}, change={latest.change_percent}%, volume={latest.volume}; "
            "provider units are preserved and are not execution prices."
        ),
        "fact_type": "SECONDARY_PRICE_HISTORY",
    }


PARSER_SOURCE_IDS = {
    "boursa_identity_html_v1": "boursa_current",
    "investing_history_html_v1": "investing_history",
}


__all__ = [
    "IdentityRecord",
    "InvestingInstrument",
    "PARSER_SOURCE_IDS",
    "ParserDriftError",
    "PriceRecord",
    "investing_price_finding",
    "parse_boursa_identity_html",
    "parse_investing_history_html",
]
