from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .strict import https_url, parse_iso_date, require_sha256


PILOT_IDENTITY_SCHEMA_VERSION = "1.0"
VENDOR_MAPPING_SCHEMA_VERSION = "1.0"
IDENTITY_STATES = frozenset({"UNVERIFIED_SEED", "VERIFIED_OFFICIAL", "RETIRED"})
MAPPING_STATES = frozenset(
    {
        "CANDIDATE_URL_OBSERVED",
        "CANDIDATE_NEEDS_CAPTURE",
        "VALIDATED_BY_RAW_CAPTURE",
        "RETIRED",
    }
)
_SECURITY_CODE_RE = re.compile(r"^[0-9]{1,12}$")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,31}$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_PROVIDER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_PROVIDER_SYMBOL_RE = re.compile(r"^[a-z0-9]+(?:-+[a-z0-9]+)*$")
_INVESTING_HOSTS = frozenset(
    {"investing.com", "www.investing.com", "sa.investing.com"}
)


@dataclass(frozen=True)
class PilotIdentitySeed:
    security_code: str
    ticker: str
    name_en: str
    name_ar: str
    isin: str
    sector: str
    identity_state: str
    official_artifact_sha256: str | None
    valid_from: str | None
    valid_to: str | None
    notes: str

    @property
    def officially_verified(self) -> bool:
        return self.identity_state == "VERIFIED_OFFICIAL"


@dataclass(frozen=True)
class VendorSymbolMapping:
    security_code: str
    ticker: str
    isin: str
    provider: str
    provider_symbol: str
    provider_url: str
    mapping_state: str
    evidence_notes: str



def _load_object(path: Path, field: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field} must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return payload



def _valid_isin(value: str) -> bool:
    """Validate ISO 6166 shape and Luhn check digit."""

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



def _identity_seed(row: Any, index: int) -> PilotIdentitySeed:
    expected = {
        "security_code",
        "ticker",
        "name_en",
        "name_ar",
        "isin",
        "sector",
        "identity_state",
        "official_artifact_sha256",
        "valid_from",
        "valid_to",
        "notes",
    }
    if not isinstance(row, dict) or set(row) != expected:
        raise ValueError(f"security seed {index} has unknown or missing fields")
    security_code = str(row["security_code"])
    ticker = str(row["ticker"])
    isin = str(row["isin"])
    state = str(row["identity_state"])
    if not _SECURITY_CODE_RE.fullmatch(security_code):
        raise ValueError(f"security seed {index} has invalid security_code")
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"security seed {index} has invalid ticker")
    if not _valid_isin(isin):
        raise ValueError(f"security seed {index} has invalid ISIN")
    if state not in IDENTITY_STATES:
        raise ValueError(f"security seed {index} has invalid identity_state")
    if not str(row["name_en"]).strip() or not str(row["sector"]).strip():
        raise ValueError(f"security seed {index} requires name_en and sector")

    raw_hash = row["official_artifact_sha256"]
    valid_from = row["valid_from"]
    valid_to = row["valid_to"]
    if state == "VERIFIED_OFFICIAL":
        raw_hash = require_sha256(raw_hash, "official_artifact_sha256")
        if valid_from in (None, ""):
            raise ValueError(
                f"security seed {index} verified identity requires valid_from"
            )
        start = parse_iso_date(valid_from, "valid_from")
        end = (
            None
            if valid_to in (None, "")
            else parse_iso_date(valid_to, "valid_to")
        )
        if end is not None and end < start:
            raise ValueError(f"security seed {index} valid_to precedes valid_from")
        valid_from = start.isoformat()
        valid_to = None if end is None else end.isoformat()
    else:
        if raw_hash not in (None, "") or valid_from not in (None, "") or valid_to not in (None, ""):
            raise ValueError(
                f"security seed {index} cannot carry official proof before verification"
            )
        raw_hash = None
        valid_from = None
        valid_to = None

    return PilotIdentitySeed(
        security_code=security_code,
        ticker=ticker,
        name_en=str(row["name_en"]).strip(),
        name_ar=str(row["name_ar"]).strip(),
        isin=isin,
        sector=str(row["sector"]).strip(),
        identity_state=state,
        official_artifact_sha256=raw_hash,
        valid_from=valid_from,
        valid_to=valid_to,
        notes=str(row["notes"]),
    )



def _vendor_mapping(
    row: Any,
    index: int,
    identities: dict[str, PilotIdentitySeed],
) -> VendorSymbolMapping:
    expected = {
        "security_code",
        "ticker",
        "isin",
        "provider",
        "provider_symbol",
        "provider_url",
        "mapping_state",
        "evidence_notes",
    }
    if not isinstance(row, dict) or set(row) != expected:
        raise ValueError(f"vendor mapping {index} has unknown or missing fields")
    security_code = str(row["security_code"])
    ticker = str(row["ticker"])
    isin = str(row["isin"])
    provider = str(row["provider"])
    provider_symbol = str(row["provider_symbol"])
    provider_url = str(row["provider_url"])
    state = str(row["mapping_state"])
    if not _SECURITY_CODE_RE.fullmatch(security_code):
        raise ValueError(f"vendor mapping {index} has invalid security_code")
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"vendor mapping {index} has invalid ticker")
    if not _valid_isin(isin):
        raise ValueError(f"vendor mapping {index} has invalid ISIN")
    if not _PROVIDER_RE.fullmatch(provider):
        raise ValueError(f"vendor mapping {index} has invalid provider")
    if not _PROVIDER_SYMBOL_RE.fullmatch(provider_symbol):
        raise ValueError(f"vendor mapping {index} has invalid provider_symbol")
    if state not in MAPPING_STATES:
        raise ValueError(f"vendor mapping {index} has invalid mapping_state")

    canonical_url = https_url(provider_url, "provider_url")
    parsed = urlsplit(canonical_url)
    if provider == "investing":
        if (parsed.hostname or "").lower() not in _INVESTING_HOSTS:
            raise ValueError("Investing mapping uses an unapproved host")
        if parsed.query or parsed.fragment:
            raise ValueError("Investing mapping URL must not contain query or fragment")
        expected_path = f"/equities/{provider_symbol}-historical-data"
        if parsed.path != expected_path:
            raise ValueError("Investing mapping URL does not match provider_symbol")
    else:
        raise ValueError(f"unsupported pilot provider: {provider}")

    identity = identities.get(ticker)
    if identity is None:
        raise ValueError(f"vendor mapping {index} has no matching identity seed")
    if identity.security_code != security_code or identity.isin != isin:
        raise ValueError(
            f"vendor mapping {index} conflicts with the separated identity seed"
        )
    return VendorSymbolMapping(
        security_code=security_code,
        ticker=ticker,
        isin=isin,
        provider=provider,
        provider_symbol=provider_symbol,
        provider_url=canonical_url,
        mapping_state=state,
        evidence_notes=str(row["evidence_notes"]),
    )


class PilotIdentitySeedCatalog:
    def __init__(self, config_dir: Path):
        path = Path(config_dir) / "pilot" / "security_master_seed.json"
        payload = _load_object(path, "security_master_seed.json")
        expected = {
            "schema_version",
            "as_of",
            "scope",
            "claim_boundary",
            "securities",
        }
        if set(payload) != expected:
            raise ValueError("security_master_seed.json has unknown or missing fields")
        if payload["schema_version"] != PILOT_IDENTITY_SCHEMA_VERSION:
            raise ValueError("unsupported pilot identity schema_version")
        self.as_of = parse_iso_date(payload["as_of"], "security_master_seed.as_of").isoformat()
        self.scope = str(payload["scope"])
        if payload["claim_boundary"] != "SEED_IDENTITY_NOT_OFFICIAL_EVIDENCE":
            raise ValueError("pilot identity claim boundary cannot be weakened")
        rows = payload["securities"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("pilot identity securities must be a non-empty list")
        identities = [_identity_seed(row, index) for index, row in enumerate(rows)]
        self.identities: dict[str, PilotIdentitySeed] = {}
        codes: set[str] = set()
        isins: set[str] = set()
        for identity in identities:
            if identity.ticker in self.identities:
                raise ValueError(f"duplicate pilot ticker: {identity.ticker}")
            if identity.security_code in codes:
                raise ValueError(f"duplicate pilot security_code: {identity.security_code}")
            if identity.isin in isins:
                raise ValueError(f"duplicate pilot ISIN: {identity.isin}")
            self.identities[identity.ticker] = identity
            codes.add(identity.security_code)
            isins.add(identity.isin)

    @property
    def official_identity_ready(self) -> bool:
        return bool(self.identities) and all(
            item.officially_verified and item.identity_state != "RETIRED"
            for item in self.identities.values()
        )

    def report(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        for identity in self.identities.values():
            states[identity.identity_state] = states.get(identity.identity_state, 0) + 1
        return {
            "status": "PASS",
            "schema_version": PILOT_IDENTITY_SCHEMA_VERSION,
            "as_of": self.as_of,
            "scope": self.scope,
            "security_count": len(self.identities),
            "identity_states": dict(sorted(states.items())),
            "official_identity_ready": self.official_identity_ready,
            "claim_boundary": "SEED_IDENTITY_NOT_OFFICIAL_EVIDENCE",
        }


class VendorSymbolMappingCatalog:
    def __init__(
        self,
        config_dir: Path,
        identities: PilotIdentitySeedCatalog | None = None,
    ):
        self.identities = identities or PilotIdentitySeedCatalog(config_dir)
        path = Path(config_dir) / "pilot" / "vendor_symbol_mappings.json"
        payload = _load_object(path, "vendor_symbol_mappings.json")
        expected = {
            "schema_version",
            "as_of",
            "scope",
            "claim_boundary",
            "mappings",
        }
        if set(payload) != expected:
            raise ValueError("vendor_symbol_mappings.json has unknown or missing fields")
        if payload["schema_version"] != VENDOR_MAPPING_SCHEMA_VERSION:
            raise ValueError("unsupported vendor mapping schema_version")
        self.as_of = parse_iso_date(payload["as_of"], "vendor_symbol_mappings.as_of").isoformat()
        self.scope = str(payload["scope"])
        if payload["claim_boundary"] != "VENDOR_MAPPING_IS_NOT_OFFICIAL_SECURITY_IDENTITY":
            raise ValueError("vendor mapping claim boundary cannot be weakened")
        rows = payload["mappings"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("vendor mappings must be a non-empty list")
        mappings = [
            _vendor_mapping(row, index, self.identities.identities)
            for index, row in enumerate(rows)
        ]
        self.mappings: dict[tuple[str, str], VendorSymbolMapping] = {}
        provider_urls: set[str] = set()
        provider_symbols: set[tuple[str, str]] = set()
        for mapping in mappings:
            key = (mapping.provider, mapping.ticker)
            if key in self.mappings:
                raise ValueError(f"duplicate vendor mapping: {mapping.provider}:{mapping.ticker}")
            provider_symbol_key = (mapping.provider, mapping.provider_symbol)
            if mapping.provider_url in provider_urls:
                raise ValueError(f"duplicate provider_url: {mapping.provider_url}")
            if provider_symbol_key in provider_symbols:
                raise ValueError(
                    f"duplicate provider_symbol: {mapping.provider}:{mapping.provider_symbol}"
                )
            self.mappings[key] = mapping
            provider_urls.add(mapping.provider_url)
            provider_symbols.add(provider_symbol_key)

    def capture_candidates(self, provider: str = "investing") -> list[VendorSymbolMapping]:
        return [
            mapping
            for (row_provider, _), mapping in self.mappings.items()
            if row_provider == provider
            and mapping.mapping_state
            in {
                "CANDIDATE_URL_OBSERVED",
                "CANDIDATE_NEEDS_CAPTURE",
                "VALIDATED_BY_RAW_CAPTURE",
            }
        ]

    def report(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        providers: dict[str, int] = {}
        for mapping in self.mappings.values():
            states[mapping.mapping_state] = states.get(mapping.mapping_state, 0) + 1
            providers[mapping.provider] = providers.get(mapping.provider, 0) + 1
        return {
            "status": "PASS",
            "schema_version": VENDOR_MAPPING_SCHEMA_VERSION,
            "as_of": self.as_of,
            "scope": self.scope,
            "mapping_count": len(self.mappings),
            "mapping_states": dict(sorted(states.items())),
            "providers": dict(sorted(providers.items())),
            "official_identity_ready": self.identities.official_identity_ready,
            "claim_boundary": "VENDOR_MAPPING_IS_NOT_OFFICIAL_SECURITY_IDENTITY",
        }


__all__ = [
    "IDENTITY_STATES",
    "MAPPING_STATES",
    "PILOT_IDENTITY_SCHEMA_VERSION",
    "VENDOR_MAPPING_SCHEMA_VERSION",
    "PilotIdentitySeed",
    "PilotIdentitySeedCatalog",
    "VendorSymbolMapping",
    "VendorSymbolMappingCatalog",
]
