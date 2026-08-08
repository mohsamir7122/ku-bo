from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .strict import https_url, parse_iso_date


SYMBOL_MAPPING_SCHEMA_VERSION = "1.0"
_SECURITY_CODE_RE = re.compile(r"^[0-9]+$")
_BOURSA_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{0,31}$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_INVESTING_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TRADINGVIEW_SYMBOL_RE = re.compile(r"^KSE:[A-Z][A-Z0-9]{0,31}$")
_INVESTING_DOMAINS = frozenset(
    {"investing.com", "www.investing.com", "sa.investing.com"}
)


MAPPING_STATES = frozenset(
    {
        "CANDIDATE_URL_OBSERVED",
        "CANDIDATE_NEEDS_CAPTURE",
        "UNRESOLVED_INVESTING_URL",
        "VALIDATED_BY_RAW_CAPTURE",
        "RETIRED",
    }
)


@dataclass(frozen=True)
class SymbolMapping:
    security_code: str
    boursa_symbol: str
    name_en: str
    name_ar: str
    isin: str
    sector: str
    investing_slug: str
    investing_url: str
    tradingview_symbol: str
    marketscreener_query: str
    mapping_state: str
    evidence_notes: str

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "SymbolMapping":
        state = str(row.get("mapping_state", ""))
        if state not in MAPPING_STATES:
            raise ValueError(f"unsupported mapping_state: {state}")

        security_code = str(row.get("security_code", ""))
        if not _SECURITY_CODE_RE.fullmatch(security_code):
            raise ValueError("security_code must contain ASCII digits only")

        boursa_symbol = str(row.get("boursa_symbol", ""))
        if not _BOURSA_SYMBOL_RE.fullmatch(boursa_symbol):
            raise ValueError(
                "boursa_symbol must be an uppercase, path-safe ASCII ticker"
            )

        isin = str(row.get("isin", ""))
        if not _valid_isin(isin):
            raise ValueError(f"isin must be a valid uppercase ISIN: {isin}")

        investing_slug = str(row.get("investing_slug", ""))
        if investing_slug and not _INVESTING_SLUG_RE.fullmatch(investing_slug):
            raise ValueError(
                f"investing_slug must be a lowercase, path-safe slug: {boursa_symbol}"
            )

        investing_url = str(row.get("investing_url", ""))
        if investing_url:
            https_url(investing_url, "investing_url")
            parsed = urlsplit(investing_url)
            if (parsed.hostname or "").lower() not in _INVESTING_DOMAINS:
                raise ValueError(
                    f"investing_url must use an approved Investing.com domain: {investing_url}"
                )
            if parsed.query:
                raise ValueError("investing_url must not contain a query string")
            expected_path = f"/equities/{investing_slug}-historical-data"
            if not investing_slug or parsed.path != expected_path:
                raise ValueError(
                    "investing_url path must exactly match investing_slug: "
                    f"{boursa_symbol}"
                )

        tradingview_symbol = str(row.get("tradingview_symbol", ""))
        if tradingview_symbol and not _TRADINGVIEW_SYMBOL_RE.fullmatch(
            tradingview_symbol
        ):
            raise ValueError(
                f"tradingview_symbol must be a path-safe KSE ticker: {boursa_symbol}"
            )

        mapping = cls(
            security_code=security_code,
            boursa_symbol=boursa_symbol,
            name_en=str(row.get("name_en", "")),
            name_ar=str(row.get("name_ar", "")),
            isin=isin,
            sector=str(row.get("sector", "")),
            investing_slug=investing_slug,
            investing_url=investing_url,
            tradingview_symbol=tradingview_symbol,
            marketscreener_query=str(row.get("marketscreener_query", "")),
            mapping_state=state,
            evidence_notes=str(row.get("evidence_notes", "")),
        )
        if not mapping.boursa_symbol or not mapping.name_en:
            raise ValueError("mapping requires boursa_symbol and name_en")
        if mapping.mapping_state == "UNRESOLVED_INVESTING_URL" and mapping.investing_url:
            raise ValueError(f"unresolved mapping cannot carry investing_url: {mapping.boursa_symbol}")
        if mapping.mapping_state in {"CANDIDATE_URL_OBSERVED", "VALIDATED_BY_RAW_CAPTURE"} and not mapping.investing_url:
            raise ValueError(f"{mapping.mapping_state} requires investing_url: {mapping.boursa_symbol}")
        return mapping


def _valid_isin(value: str) -> bool:
    """Validate the ISO 6166 shape and Luhn check digit."""

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


class SymbolMappingCatalog:
    def __init__(self, config_dir: Path):
        path = config_dir / "symbol_mapping.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("symbol_mapping.json must contain a JSON object")
        rows = payload.get("mappings")
        if not isinstance(rows, list) or not rows:
            raise ValueError("symbol_mapping.json must contain a non-empty mappings list")
        self.schema_version = str(payload.get("schema_version", ""))
        if self.schema_version != SYMBOL_MAPPING_SCHEMA_VERSION:
            raise ValueError(
                "symbol_mapping schema_version must be "
                f"{SYMBOL_MAPPING_SCHEMA_VERSION}"
            )
        self.as_of = str(payload.get("as_of", ""))
        parse_iso_date(self.as_of, "symbol_mapping.as_of")
        coverage = payload.get("coverage")
        if not isinstance(coverage, dict):
            raise ValueError("symbol_mapping coverage must be an object")
        coverage_count = coverage.get("security_count")
        if isinstance(coverage_count, bool) or not isinstance(coverage_count, int):
            raise ValueError("coverage.security_count must be an integer")
        if coverage_count != len(rows):
            raise ValueError(
                "coverage.security_count must equal the number of mapping rows"
            )
        if not isinstance(coverage.get("scope"), str) or not coverage["scope"]:
            raise ValueError("coverage.scope must be a non-empty string")
        self.coverage = dict(coverage)
        self.mappings = self._load_unique(rows)

    @staticmethod
    def _load_unique(rows: list[Any]) -> dict[str, SymbolMapping]:
        result: dict[str, SymbolMapping] = {}
        security_codes: set[int] = set()
        isins: set[str] = set()
        investing_slugs: set[str] = set()
        investing_urls: set[str] = set()
        tradingview_symbols: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("symbol mapping row must be an object")
            mapping = SymbolMapping.from_dict(row)
            if mapping.boursa_symbol in result:
                raise ValueError(f"duplicate boursa_symbol: {mapping.boursa_symbol}")
            numeric_security_code = int(mapping.security_code)
            if numeric_security_code in security_codes:
                raise ValueError(f"duplicate security_code: {mapping.security_code}")
            security_codes.add(numeric_security_code)
            if mapping.isin in isins:
                raise ValueError(f"duplicate isin: {mapping.isin}")
            isins.add(mapping.isin)
            if mapping.investing_slug:
                if mapping.investing_slug in investing_slugs:
                    raise ValueError(
                        f"duplicate investing_slug: {mapping.investing_slug}"
                    )
                investing_slugs.add(mapping.investing_slug)
            if mapping.investing_url:
                if mapping.investing_url in investing_urls:
                    raise ValueError(f"duplicate investing_url: {mapping.investing_url}")
                investing_urls.add(mapping.investing_url)
            if mapping.tradingview_symbol:
                if mapping.tradingview_symbol in tradingview_symbols:
                    raise ValueError(f"duplicate tradingview_symbol: {mapping.tradingview_symbol}")
                tradingview_symbols.add(mapping.tradingview_symbol)
            result[mapping.boursa_symbol] = mapping
        return result

    def report(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        with_investing = 0
        for mapping in self.mappings.values():
            states[mapping.mapping_state] = states.get(mapping.mapping_state, 0) + 1
            if mapping.investing_url:
                with_investing += 1
        return {
            "status": "PASS",
            "schema_version": self.schema_version,
            "as_of": self.as_of,
            "scope": self.coverage.get("scope", ""),
            "security_count": len(self.mappings),
            "with_investing_url": with_investing,
            "mapping_states": states,
            "symbols": sorted(self.mappings),
        }

    def capture_candidates(self) -> list[SymbolMapping]:
        return [
            mapping
            for mapping in self.mappings.values()
            if mapping.investing_url
            and mapping.mapping_state
            in {
                "CANDIDATE_URL_OBSERVED",
                "CANDIDATE_NEEDS_CAPTURE",
                "VALIDATED_BY_RAW_CAPTURE",
            }
        ]


__all__ = [
    "MAPPING_STATES",
    "SYMBOL_MAPPING_SCHEMA_VERSION",
    "SymbolMapping",
    "SymbolMappingCatalog",
]
