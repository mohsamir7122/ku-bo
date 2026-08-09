from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
import re
from typing import Any


MAX_OFFICIAL_PARSER_BYTES = 10 * 1024 * 1024
_SECURITY_CODE_RE = re.compile(r"^[0-9]{1,12}$")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9._-]{0,31}$")
_ACCESS_BLOCKERS = (
    "verify you are human",
    "g-recaptcha",
    "hcaptcha",
    "cf-chl-",
    "subscribe to continue",
    'type="password"',
)
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class OfficialParserDriftError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        super().__init__(code if not detail else f"{code}:{detail}")


@dataclass(frozen=True)
class ListedCompanyRecord:
    security_code: str
    ticker: str
    name: str
    sector: str
    market_segment: str
    listing_date: date


@dataclass(frozen=True)
class MarketHolidayRecord:
    holiday_date: date
    name: str


@dataclass(frozen=True)
class TradingRegime:
    effective_from: date
    continuous_start: str
    continuous_end: str
    closing_auction_start: str
    closing_auction_end: str
    trade_at_last_start: str
    trade_at_last_end: str
    session_regime_id: str


class _TableCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.document_text: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "table" and self._table is None:
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []

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

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.document_text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _decode_html(content: bytes) -> str:
    if not isinstance(content, bytes) or not content:
        raise OfficialParserDriftError("EMPTY_OFFICIAL_CAPTURE")
    if len(content) > MAX_OFFICIAL_PARSER_BYTES:
        raise OfficialParserDriftError("OFFICIAL_PARSER_INPUT_TOO_LARGE")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OfficialParserDriftError("NON_UTF8_OFFICIAL_CAPTURE") from exc
    lowered = text[: 256 * 1024].casefold()
    if any(marker in lowered for marker in _ACCESS_BLOCKERS):
        raise OfficialParserDriftError("OFFICIAL_ACCESS_BLOCKER_CAPTURED")
    return text


def _collect(content: bytes) -> _TableCollector:
    collector = _TableCollector()
    try:
        collector.feed(_decode_html(content))
        collector.close()
    except OfficialParserDriftError:
        raise
    except Exception as exc:
        raise OfficialParserDriftError("MALFORMED_OFFICIAL_HTML") from exc
    return collector


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


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
            positions = [
                index for index, value in enumerate(normalized) if value in aliases
            ]
            if len(positions) != 1:
                break
            indexes[canonical] = positions[0]
        if len(indexes) == len(required_headers):
            return indexes, table[1:]
    raise OfficialParserDriftError("REQUIRED_OFFICIAL_TABLE_HEADERS_NOT_FOUND")


def _listing_date(value: str) -> date:
    text = _clean_text(value)
    for format_string in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(text, format_string).date()
        except ValueError:
            continue
    raise OfficialParserDriftError("INVALID_LISTING_DATE", text)


def parse_boursa_listed_companies_html(
    content: bytes,
) -> tuple[ListedCompanyRecord, ...]:
    """Parse a rendered official Listed Companies table.

    The public page may be client-rendered. A raw server shell without the table
    fails closed; an authorized browser export of the rendered table is allowed
    when its bytes and capture time are preserved by the caller.
    """

    collector = _collect(content)
    indexes, rows = _find_table(
        collector.tables,
        {
            "security_code": {"sec code", "security code"},
            "ticker": {"ticker", "symbol"},
            "name": {"name", "company name"},
            "sector": {"sector"},
            "market_segment": {"market segment", "market"},
            "listing_date": {"date of listing", "listing date"},
        },
    )
    maximum_index = max(indexes.values())
    result: list[ListedCompanyRecord] = []
    seen_codes: set[str] = set()
    seen_tickers: set[str] = set()
    for row_index, row in enumerate(rows, start=1):
        if len(row) <= maximum_index:
            raise OfficialParserDriftError("SHORT_LISTED_COMPANY_ROW", str(row_index))
        code = row[indexes["security_code"]].strip()
        ticker = row[indexes["ticker"]].strip().upper()
        name = _clean_text(row[indexes["name"]])
        sector = _clean_text(row[indexes["sector"]])
        segment = _clean_text(row[indexes["market_segment"]])
        if not _SECURITY_CODE_RE.fullmatch(code):
            raise OfficialParserDriftError("INVALID_LISTED_SECURITY_CODE", str(row_index))
        if not _TICKER_RE.fullmatch(ticker):
            raise OfficialParserDriftError("INVALID_LISTED_TICKER", str(row_index))
        if not name or not sector or not segment:
            raise OfficialParserDriftError("INCOMPLETE_LISTED_COMPANY_ROW", str(row_index))
        if code in seen_codes or ticker in seen_tickers:
            raise OfficialParserDriftError("DUPLICATE_LISTED_COMPANY_ROW", str(row_index))
        seen_codes.add(code)
        seen_tickers.add(ticker)
        result.append(
            ListedCompanyRecord(
                security_code=code,
                ticker=ticker,
                name=name,
                sector=sector,
                market_segment=segment,
                listing_date=_listing_date(row[indexes["listing_date"]]),
            )
        )
    if not result:
        raise OfficialParserDriftError("ZERO_LISTED_COMPANY_ROWS")
    return tuple(result)


def _holiday_year(document: str) -> int:
    match = re.search(
        r"(?:Kuwait\s+)?Public\s+Holidays\s+(20[0-9]{2})",
        document,
        flags=re.IGNORECASE,
    )
    if not match:
        raise OfficialParserDriftError("HOLIDAY_YEAR_NOT_FOUND")
    return int(match.group(1))


def _holiday_days(value: str) -> tuple[int, ...]:
    text = _clean_text(value).replace("–", "-").replace("—", "-")
    if not text or text == "-":
        return ()
    range_match = re.fullmatch(r"([0-9]{1,2})\s*-\s*([0-9]{1,2})", text)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        if end < start:
            raise OfficialParserDriftError("REVERSED_HOLIDAY_RANGE", text)
        return tuple(range(start, end + 1))
    values = tuple(int(item) for item in re.findall(r"[0-9]{1,2}", text))
    if not values:
        raise OfficialParserDriftError("INVALID_HOLIDAY_DAY", text)
    return values


def parse_boursa_market_holidays_html(
    content: bytes,
) -> tuple[int, tuple[MarketHolidayRecord, ...]]:
    collector = _collect(content)
    document = _clean_text(" ".join(collector.document_text))
    year = _holiday_year(document)
    indexes, rows = _find_table(
        collector.tables,
        {
            "month": {"month"},
            "date": {"date"},
            "holiday": {"vacation", "holiday", "public holiday"},
        },
    )
    maximum_index = max(indexes.values())
    result: list[MarketHolidayRecord] = []
    seen: set[date] = set()
    for row_index, row in enumerate(rows, start=1):
        if len(row) <= maximum_index:
            raise OfficialParserDriftError("SHORT_HOLIDAY_ROW", str(row_index))
        month_text = _clean_text(row[indexes["month"]]).casefold()
        if month_text not in _MONTHS:
            raise OfficialParserDriftError("INVALID_HOLIDAY_MONTH", month_text)
        days = _holiday_days(row[indexes["date"]])
        if not days:
            continue
        name = _clean_text(row[indexes["holiday"]])
        if not name or name == "-":
            raise OfficialParserDriftError("HOLIDAY_NAME_REQUIRED", str(row_index))
        for day_number in days:
            try:
                holiday_date = date(year, _MONTHS[month_text], day_number)
            except ValueError as exc:
                raise OfficialParserDriftError(
                    "INVALID_HOLIDAY_DATE", f"{month_text}:{day_number}"
                ) from exc
            if holiday_date in seen:
                raise OfficialParserDriftError(
                    "DUPLICATE_HOLIDAY_DATE", holiday_date.isoformat()
                )
            seen.add(holiday_date)
            result.append(MarketHolidayRecord(holiday_date, name))
    if not result:
        raise OfficialParserDriftError("ZERO_MARKET_HOLIDAYS")
    return year, tuple(sorted(result, key=lambda item: item.holiday_date))


def _time_24h(value: str, meridiem: str) -> str:
    try:
        parsed = datetime.strptime(
            f"{value} {meridiem.replace('.', '').upper()}", "%I:%M %p"
        )
    except ValueError as exc:
        raise OfficialParserDriftError("INVALID_TRADING_TIME", f"{value} {meridiem}") from exc
    return parsed.strftime("%H:%M:%S")


def _time_range(document: str, phrase: str) -> tuple[str, str]:
    pattern = re.compile(
        phrase
        + r".*?from\s+(\d{1,2}:\d{2})\s*([ap]\.?m\.?)\s+to\s+"
        + r"(\d{1,2}:\d{2})\s*([ap]\.?m\.?)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(document)
    if not match:
        raise OfficialParserDriftError("TRADING_TIME_RANGE_NOT_FOUND", phrase)
    return _time_24h(match.group(1), match.group(2)), _time_24h(
        match.group(3), match.group(4)
    )


def parse_boursa_trading_extension_html(content: bytes) -> TradingRegime:
    collector = _collect(content)
    document = _clean_text(" ".join(collector.document_text))
    effective_match = re.search(
        r"Starting\s+(?:[A-Za-z]+,\s*)?([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20[0-9]{2})",
        document,
        flags=re.IGNORECASE,
    )
    if not effective_match:
        raise OfficialParserDriftError("TRADING_REGIME_EFFECTIVE_DATE_NOT_FOUND")
    month = _MONTHS.get(effective_match.group(1).casefold())
    if month is None:
        raise OfficialParserDriftError("INVALID_TRADING_REGIME_MONTH")
    effective_from = date(
        int(effective_match.group(3)), month, int(effective_match.group(2))
    )
    continuous_start, continuous_end = _time_range(
        document, r"continuous\s+trading\s+session"
    )
    closing_start, closing_end = _time_range(
        document, r"closing\s+auction\s+session"
    )
    last_start, last_end = _time_range(document, r"trade\s+at\s+last\s+session")
    if continuous_end != closing_start or closing_end != last_start:
        raise OfficialParserDriftError("TRADING_SESSION_RANGES_DO_NOT_CONNECT")
    regime_id = (
        f"BK_CASH_{effective_from.isoformat()}_"
        f"{continuous_start.replace(':', '')}_{last_end.replace(':', '')}"
    )
    return TradingRegime(
        effective_from=effective_from,
        continuous_start=continuous_start,
        continuous_end=continuous_end,
        closing_auction_start=closing_start,
        closing_auction_end=closing_end,
        trade_at_last_start=last_start,
        trade_at_last_end=last_end,
        session_regime_id=regime_id,
    )


def parse_boursa_contact_weekdays_html(content: bytes) -> frozenset[int]:
    collector = _collect(content)
    document = _clean_text(" ".join(collector.document_text))
    match = re.search(
        r"Trading\s+Hours\s*:?.*?\((Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*-\s*"
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\)",
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise OfficialParserDriftError("TRADING_WEEKDAY_RANGE_NOT_FOUND")
    start_name = match.group(1).casefold()
    end_name = match.group(2).casefold()
    ordered_names = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )
    start = ordered_names.index(start_name)
    end = ordered_names.index(end_name)
    selected: list[str] = []
    cursor = start
    while True:
        selected.append(ordered_names[cursor])
        if cursor == end:
            break
        cursor = (cursor + 1) % len(ordered_names)
        if len(selected) > len(ordered_names):
            raise OfficialParserDriftError("INVALID_TRADING_WEEKDAY_RANGE")
    weekdays = frozenset(_WEEKDAYS[name] for name in selected)
    if not weekdays:
        raise OfficialParserDriftError("ZERO_TRADING_WEEKDAYS")
    return weekdays


__all__ = [
    "ListedCompanyRecord",
    "MarketHolidayRecord",
    "MAX_OFFICIAL_PARSER_BYTES",
    "OfficialParserDriftError",
    "TradingRegime",
    "parse_boursa_contact_weekdays_html",
    "parse_boursa_listed_companies_html",
    "parse_boursa_market_holidays_html",
    "parse_boursa_trading_extension_html",
]
