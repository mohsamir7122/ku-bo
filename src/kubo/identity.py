from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .evidence_hashes import parse_supporting_hashes
from .strict import parse_iso_date, require_sha256


ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
LISTED_STATUSES = frozenset({"ACTIVE", "LISTED", "TRADING", "SUSPENDED", "HALTED"})
SESSION_ELIGIBLE_STATUSES = frozenset({"TRADING", "SUSPENDED", "HALTED"})


@dataclass(frozen=True)
class IdentityRecord:
    security_code: str
    ticker: str
    isin: str | None
    name_ar: str
    name_en: str
    board: str
    market_segment: str
    currency: str
    valid_from: date
    valid_to: date | None
    listing_status: str
    raw_sha256: str
    supporting_raw_sha256s: tuple[str, ...] = ()

    def active_on(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)


@dataclass(frozen=True)
class StatusRecord:
    security_code: str
    board: str
    status: str
    effective_from: date
    effective_to: date | None
    raw_sha256: str

    def active_on(self, day: date) -> bool:
        return self.effective_from <= day and (self.effective_to is None or day <= self.effective_to)


def read_csv_rows(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = tuple(reader.fieldnames or ())
        if len(headers) != len(set(headers)):
            raise ValueError(f"duplicate CSV headers: {path}")
        return headers, [dict(row) for row in reader]


def _optional_date(value: Any, field: str) -> date | None:
    return None if value in (None, "") else parse_iso_date(value, field)


def _overlap(start_a: date, end_a: date | None, start_b: date, end_b: date | None) -> bool:
    upper_a = end_a or date.max
    upper_b = end_b or date.max
    return start_a <= upper_b and start_b <= upper_a


def validate_security_master(path: Path, *, manifest_hashes: frozenset[str]) -> tuple[list[IdentityRecord], list[str]]:
    required = {
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
    }
    errors: list[str] = []
    records: list[IdentityRecord] = []
    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return [], [f"MASTER_READ:{exc}"]
    missing_headers = sorted(required - set(headers))
    if missing_headers:
        return [], ["MASTER_HEADERS:" + ",".join(missing_headers)]
    if not rows:
        return [], ["MASTER_EMPTY"]
    supports_multiple_hashes = "supporting_raw_sha256s" in headers
    for index, row in enumerate(rows):
        try:
            code = str(row.get("security_code", "")).strip()
            ticker = str(row.get("ticker", "")).strip().upper()
            board = str(row.get("board", "")).strip().lower()
            if not code or not ticker or not board:
                raise ValueError("security_code, ticker, and board are required")
            isin_value = str(row.get("isin", "")).strip().upper()
            isin = isin_value or None
            if isin and not ISIN_RE.fullmatch(isin):
                raise ValueError("invalid ISIN")
            currency = str(row.get("currency", "")).strip().upper()
            if currency != "KWD":
                raise ValueError("cash-market currency must be KWD")
            status = str(row.get("listing_status", "")).strip().upper()
            if status not in LISTED_STATUSES | {"DELISTED"}:
                raise ValueError("invalid listing_status")
            start = parse_iso_date(row.get("valid_from"), "valid_from")
            end = _optional_date(row.get("valid_to"), "valid_to")
            if end and end < start:
                raise ValueError("valid_to precedes valid_from")
            raw_hash = require_sha256(row.get("raw_sha256"), "raw_sha256")
            if raw_hash not in manifest_hashes:
                raise ValueError("raw_sha256 does not resolve")
            supporting_hashes = (
                parse_supporting_hashes(
                    row.get("supporting_raw_sha256s"),
                    field="supporting_raw_sha256s",
                    manifest_hashes=manifest_hashes,
                )
                if supports_multiple_hashes
                else ()
            )
            if raw_hash in supporting_hashes:
                raise ValueError("primary raw_sha256 is duplicated in supporting evidence")
            records.append(
                IdentityRecord(
                    security_code=code,
                    ticker=ticker,
                    isin=isin,
                    name_ar=str(row.get("name_ar", "")).strip(),
                    name_en=str(row.get("name_en", "")).strip(),
                    board=board,
                    market_segment=str(row.get("market_segment", "")).strip(),
                    currency=currency,
                    valid_from=start,
                    valid_to=end,
                    listing_status=status,
                    raw_sha256=raw_hash,
                    supporting_raw_sha256s=supporting_hashes,
                )
            )
        except ValueError as exc:
            errors.append(f"master_row_{index}:{exc}")
    groups: dict[tuple[str, str], list[IdentityRecord]] = {}
    for record in records:
        groups.setdefault((record.security_code, record.board), []).append(record)
    for key, group in groups.items():
        ordered = sorted(group, key=lambda item: item.valid_from)
        for previous, current in zip(ordered, ordered[1:]):
            if _overlap(previous.valid_from, previous.valid_to, current.valid_from, current.valid_to):
                errors.append(f"MASTER_OVERLAP:{key[0]}:{key[1]}")
    with_isin = [record for record in records if record.isin]
    for index, left in enumerate(with_isin):
        for right in with_isin[index + 1 :]:
            if left.isin == right.isin and (left.security_code != right.security_code or left.board != right.board) and _overlap(left.valid_from, left.valid_to, right.valid_from, right.valid_to):
                errors.append(f"ISIN_COLLISION:{left.isin}")
    return records, sorted(set(errors))


def validate_status_history(path: Path, *, manifest_hashes: frozenset[str], known_codes: frozenset[str]) -> tuple[list[StatusRecord], list[str]]:
    required = {"security_code", "board", "status", "effective_from", "effective_to", "reason_code", "notice_id", "raw_sha256"}
    errors: list[str] = []
    records: list[StatusRecord] = []
    try:
        headers, rows = read_csv_rows(path)
    except (OSError, ValueError) as exc:
        return [], [f"STATUS_READ:{exc}"]
    missing_headers = sorted(required - set(headers))
    if missing_headers:
        return [], ["STATUS_HEADERS:" + ",".join(missing_headers)]
    if not rows:
        return [], ["STATUS_EMPTY"]
    allowed = SESSION_ELIGIBLE_STATUSES | {"DELISTED", "LISTED_NOT_YET_TRADING"}
    for index, row in enumerate(rows):
        try:
            code = str(row.get("security_code", "")).strip()
            if code not in known_codes:
                raise ValueError("unknown security_code")
            board = str(row.get("board", "")).strip().lower()
            status = str(row.get("status", "")).strip().upper()
            if not board or status not in allowed:
                raise ValueError("invalid board or status")
            start = parse_iso_date(row.get("effective_from"), "effective_from")
            end = _optional_date(row.get("effective_to"), "effective_to")
            if end and end < start:
                raise ValueError("effective_to precedes effective_from")
            raw_hash = require_sha256(row.get("raw_sha256"), "raw_sha256")
            if raw_hash not in manifest_hashes:
                raise ValueError("raw_sha256 does not resolve")
            records.append(StatusRecord(code, board, status, start, end, raw_hash))
        except ValueError as exc:
            errors.append(f"status_row_{index}:{exc}")
    groups: dict[tuple[str, str], list[StatusRecord]] = {}
    for record in records:
        groups.setdefault((record.security_code, record.board), []).append(record)
    for key, group in groups.items():
        ordered = sorted(group, key=lambda item: item.effective_from)
        for previous, current in zip(ordered, ordered[1:]):
            if _overlap(previous.effective_from, previous.effective_to, current.effective_from, current.effective_to):
                errors.append(f"STATUS_OVERLAP:{key[0]}:{key[1]}")
    return records, sorted(set(errors))


class IdentityResolver:
    def __init__(self, records: Iterable[IdentityRecord]):
        self.records = tuple(records)

    def resolve(self, *, as_of: date, board: str, security_code: str | None = None, isin: str | None = None, ticker: str | None = None) -> IdentityRecord:
        if security_code in (None, "") and isin in (None, ""):
            raise ValueError("security_code or ISIN is required; ticker alone is invalid")
        candidates = [item for item in self.records if item.board == board.lower() and item.active_on(as_of)]
        if security_code not in (None, ""):
            candidates = [item for item in candidates if item.security_code == str(security_code)]
        if isin not in (None, ""):
            candidates = [item for item in candidates if item.isin == str(isin).upper()]
        if ticker not in (None, ""):
            candidates = [item for item in candidates if item.ticker == str(ticker).upper()]
        if len(candidates) != 1:
            raise LookupError("point-in-time identity is missing or ambiguous")
        return candidates[0]


def eligible_codes_on(day: date, identities: Iterable[IdentityRecord], statuses: Iterable[StatusRecord], *, board: str = "cash") -> frozenset[str]:
    identity_codes = {item.security_code for item in identities if item.board == board and item.active_on(day) and item.listing_status in LISTED_STATUSES}
    by_code: dict[str, list[StatusRecord]] = {}
    for item in statuses:
        if item.board == board and item.active_on(day):
            by_code.setdefault(item.security_code, []).append(item)
    eligible: set[str] = set()
    for code in identity_codes:
        active = by_code.get(code, [])
        if len(active) == 1 and active[0].status in SESSION_ELIGIBLE_STATUSES:
            eligible.add(code)
    return frozenset(eligible)


__all__ = [
    "IdentityRecord",
    "IdentityResolver",
    "StatusRecord",
    "eligible_codes_on",
    "read_csv_rows",
    "validate_security_master",
    "validate_status_history",
]
