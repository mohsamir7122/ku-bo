from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
import re


MAX_STATUS_CORPORATE_PARSER_BYTES = 10 * 1024 * 1024
_SECURITY_CODE_RE = re.compile(r"^[0-9]{1,12}$")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9._-]{0,31}$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_ACCESS_BLOCKERS = (
    "verify you are human",
    "g-recaptcha",
    "hcaptcha",
    "cf-chl-",
    "subscribe to continue",
    'type="password"',
)


class StatusCorporateParserDriftError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        super().__init__(code if not detail else f"{code}:{detail}")


@dataclass(frozen=True)
class StatusCompanyRecord:
    security_code: str
    ticker: str
    name: str
    sector: str
    market_segment: str


@dataclass(frozen=True)
class DelistedCompanyRecord:
    security_code: str
    ticker: str
    name: str
    sector: str
    market_segment: str
    delisting_date: date


@dataclass(frozen=True)
class CorporateActionScheduleRecord:
    isin: str
    security_code: str
    ticker: str
    cum_date: date
    ex_date: date
    record_date: date
    payment_date: date | None


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
        raise StatusCorporateParserDriftError("EMPTY_STATUS_CORPORATE_CAPTURE")
    if len(content) > MAX_STATUS_CORPORATE_PARSER_BYTES:
        raise StatusCorporateParserDriftError("STATUS_CORPORATE_INPUT_TOO_LARGE")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StatusCorporateParserDriftError("NON_UTF8_STATUS_CORPORATE_CAPTURE") from exc
    lowered = text[: 256 * 1024].casefold()
    if any(marker in lowered for marker in _ACCESS_BLOCKERS):
        raise StatusCorporateParserDriftError("STATUS_CORPORATE_ACCESS_BLOCKER_CAPTURED")
    return text


def _collect(content: bytes) -> _TableCollector:
    collector = _TableCollector()
    try:
        collector.feed(_decode_html(content))
        collector.close()
    except StatusCorporateParserDriftError:
        raise
    except Exception as exc:
        raise StatusCorporateParserDriftError("MALFORMED_STATUS_CORPORATE_HTML") from exc
    return collector


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _header_matches(value: str, aliases: set[str]) -> bool:
    normalized_aliases = {_normalized_header(alias) for alias in aliases}
    for alias in normalized_aliases:
        if value == alias or value.startswith(alias + " "):
            return True
        if len(alias) >= 6 and f" {alias} " in f" {value} ":
            return True
    return False


def _find_table(
    tables: list[list[list[str]]],
    required_headers: dict[str, set[str]],
) -> tuple[dict[str, int], list[list[str]]]:
    for table in tables:
        if not table:
            continue
        normalized = [_normalized_header(item) for item in table[0]]
        indexes: dict[str, int] = {}
        for canonical, aliases in required_headers.items():
            positions = [
                index
                for index, value in enumerate(normalized)
                if _header_matches(value, aliases)
            ]
            if len(positions) != 1:
                break
            indexes[canonical] = positions[0]
        if len(indexes) == len(required_headers):
            return indexes, table[1:]
    raise StatusCorporateParserDriftError("REQUIRED_STATUS_CORPORATE_TABLE_NOT_FOUND")


def _date_value(value: str, field: str, *, nullable: bool = False) -> date | None:
    text = _clean_text(value)
    if nullable and (not text or text in {"-", "N/A", "NA"}):
        return None
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
    raise StatusCorporateParserDriftError("INVALID_STATUS_CORPORATE_DATE", f"{field}:{text}")


def _valid_isin(value: str) -> bool:
    if not _ISIN_RE.fullmatch(value):
        return False
    expanded = "".join(
        str(ord(character) - ord("A") + 10) if character.isalpha() else character
        for character in value
    )
    checksum = 0
    for index, character in enumerate(reversed(expanded)):
        number = int(character)
        if index % 2:
            number *= 2
        checksum += number // 10 + number % 10
    return checksum % 10 == 0


def _status_rows(
    content: bytes,
    *,
    include_delisting_date: bool,
) -> tuple[StatusCompanyRecord | DelistedCompanyRecord, ...]:
    collector = _collect(content)
    required = {
        "security_code": {"sec code", "security code"},
        "ticker": {"ticker", "symbol"},
        "name": {"name", "company name"},
        "sector": {"sector"},
        "market_segment": {"market segment", "market"},
    }
    if include_delisting_date:
        required["delisting_date"] = {"date of delisting", "delisting date"}
    indexes, rows = _find_table(collector.tables, required)
    maximum_index = max(indexes.values())
    result: list[StatusCompanyRecord | DelistedCompanyRecord] = []
    seen_codes: set[str] = set()
    seen_tickers: set[str] = set()
    for row_index, row in enumerate(rows, start=1):
        if len(row) <= maximum_index:
            raise StatusCorporateParserDriftError("SHORT_STATUS_COMPANY_ROW", str(row_index))
        code = row[indexes["security_code"]].strip()
        ticker = row[indexes["ticker"]].strip().upper()
        name = _clean_text(row[indexes["name"]])
        sector = _clean_text(row[indexes["sector"]])
        segment = _clean_text(row[indexes["market_segment"]])
        if not _SECURITY_CODE_RE.fullmatch(code):
            raise StatusCorporateParserDriftError("INVALID_STATUS_SECURITY_CODE", str(row_index))
        if not _TICKER_RE.fullmatch(ticker):
            raise StatusCorporateParserDriftError("INVALID_STATUS_TICKER", str(row_index))
        if not name or not sector or not segment:
            raise StatusCorporateParserDriftError("INCOMPLETE_STATUS_COMPANY_ROW", str(row_index))
        if code in seen_codes or ticker in seen_tickers:
            raise StatusCorporateParserDriftError("DUPLICATE_STATUS_COMPANY_ROW", str(row_index))
        seen_codes.add(code)
        seen_tickers.add(ticker)
        if include_delisting_date:
            delisting_date = _date_value(
                row[indexes["delisting_date"]],
                "delisting_date",
            )
            assert delisting_date is not None
            result.append(
                DelistedCompanyRecord(
                    code,
                    ticker,
                    name,
                    sector,
                    segment,
                    delisting_date,
                )
            )
        else:
            result.append(StatusCompanyRecord(code, ticker, name, sector, segment))
    return tuple(result)


def parse_boursa_suspended_companies_html(
    content: bytes,
) -> tuple[StatusCompanyRecord, ...]:
    rows = _status_rows(content, include_delisting_date=False)
    return tuple(item for item in rows if isinstance(item, StatusCompanyRecord))


def parse_boursa_delisted_companies_html(
    content: bytes,
) -> tuple[DelistedCompanyRecord, ...]:
    rows = _status_rows(content, include_delisting_date=True)
    return tuple(item for item in rows if isinstance(item, DelistedCompanyRecord))


def parse_boursa_corporate_actions_html(
    content: bytes,
) -> tuple[CorporateActionScheduleRecord, ...]:
    collector = _collect(content)
    indexes, rows = _find_table(
        collector.tables,
        {
            "isin": {"isin code", "isin"},
            "security_code": {"sec code", "security code"},
            "ticker": {"ticker", "security name", "stock name"},
            "cum_date": {
                "cum dividend date",
                "cum div date",
                "cum-dividend date",
                "cum-div date",
            },
            "ex_date": {
                "ex dividend date",
                "ex div date",
                "ex-dividend date",
                "ex-div date",
            },
            "record_date": {"record date"},
            "payment_date": {"payment date", "distribution date"},
        },
    )
    maximum_index = max(indexes.values())
    result: list[CorporateActionScheduleRecord] = []
    seen: set[tuple[str, date, date]] = set()
    for row_index, row in enumerate(rows, start=1):
        if len(row) <= maximum_index:
            raise StatusCorporateParserDriftError("SHORT_CORPORATE_ACTION_ROW", str(row_index))
        isin = row[indexes["isin"]].strip().upper()
        code = row[indexes["security_code"]].strip()
        ticker = row[indexes["ticker"]].strip().upper()
        if not _valid_isin(isin):
            raise StatusCorporateParserDriftError("INVALID_CORPORATE_ACTION_ISIN", str(row_index))
        if not _SECURITY_CODE_RE.fullmatch(code):
            raise StatusCorporateParserDriftError("INVALID_CORPORATE_ACTION_CODE", str(row_index))
        if not _TICKER_RE.fullmatch(ticker):
            raise StatusCorporateParserDriftError("INVALID_CORPORATE_ACTION_TICKER", str(row_index))
        cum_date = _date_value(row[indexes["cum_date"]], "cum_date")
        ex_date = _date_value(row[indexes["ex_date"]], "ex_date")
        record_date = _date_value(row[indexes["record_date"]], "record_date")
        payment_date = _date_value(
            row[indexes["payment_date"]],
            "payment_date",
            nullable=True,
        )
        assert cum_date is not None and ex_date is not None and record_date is not None
        if not cum_date < ex_date <= record_date:
            raise StatusCorporateParserDriftError(
                "CORPORATE_ACTION_DATE_ORDER",
                str(row_index),
            )
        if payment_date is not None and payment_date < record_date:
            raise StatusCorporateParserDriftError(
                "PAYMENT_PRECEDES_RECORD_DATE",
                str(row_index),
            )
        key = (code, ex_date, record_date)
        if key in seen:
            raise StatusCorporateParserDriftError("DUPLICATE_CORPORATE_ACTION_ROW", str(row_index))
        seen.add(key)
        result.append(
            CorporateActionScheduleRecord(
                isin=isin,
                security_code=code,
                ticker=ticker,
                cum_date=cum_date,
                ex_date=ex_date,
                record_date=record_date,
                payment_date=payment_date,
            )
        )
    return tuple(result)


__all__ = [
    "CorporateActionScheduleRecord",
    "DelistedCompanyRecord",
    "MAX_STATUS_CORPORATE_PARSER_BYTES",
    "StatusCompanyRecord",
    "StatusCorporateParserDriftError",
    "parse_boursa_corporate_actions_html",
    "parse_boursa_delisted_companies_html",
    "parse_boursa_suspended_companies_html",
]
