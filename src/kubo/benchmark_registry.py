from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .foundation_io import load_strict_json_object
from .hashing import sha256_bytes
from .strict import https_url, parse_iso_date, strict_bool


BENCHMARK_REGISTRY_SCHEMA_VERSION = "1.0"
BENCHMARK_REGISTRY_FILE = Path("pilot") / "benchmark_registry.json"
REGISTRY_DATE_BASIS = (
    "KU_BO_REGISTRY_OBSERVATION_NOT_PROVIDER_LAUNCH_OR_SERIES_INCEPTION"
)
REGISTRY_CLAIM_BOUNDARY = (
    "INTERNAL_REQUIREMENT_CODES_ONLY_PROVIDER_CODES_AND_SERIES_INCEPTION_UNVERIFIED"
)
BENCHMARK_CODE_RE = re.compile(r"^KU_BO_[A-Z0-9_]{1,58}$")
SOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
MARKET_SCOPES = frozenset({"BROAD_MARKET", "SECTOR"})
CALCULATION_BASES = frozenset({"PRICE_INDEX", "TOTAL_RETURN_INDEX"})
SOURCE_ACCESS_VALUES = frozenset(
    {"PUBLIC_OFFICIAL_EXPORT", "LICENSED_EXPORT", "RECORDED_AUTHORIZED_FIXTURE"}
)
RIGHTS_REQUIREMENTS = frozenset(
    {"PUBLIC_RESEARCH_ALLOWED", "EXTERNAL_LICENSE_REQUIRED", "RECORDED_FIXTURE_ONLY"}
)
REGISTRY_STATES = frozenset({"UNVERIFIED_SEED", "VERIFIED_DEFINITION"})
PILOT_SECTORS = frozenset(
    {"Banks", "Consumer Services", "Real Estate", "Telecommunications"}
)

_TOP_FIELDS = {
    "schema_version",
    "registry_id",
    "registry_observed_on",
    "registry_date_basis",
    "claim_boundary",
    "benchmarks",
}
_BENCHMARK_FIELDS = {
    "benchmark_code",
    "benchmark_code_namespace",
    "benchmark_name",
    "provider",
    "source_id",
    "source_url",
    "currency",
    "unit",
    "market_scope",
    "sector",
    "calculation_basis",
    "frequency",
    "effective_from",
    "effective_to",
    "source_access",
    "rights_requirement",
    "registry_state",
    "required_for_pilot",
}


@dataclass(frozen=True)
class BenchmarkDefinition:
    benchmark_code: str
    benchmark_name: str
    provider: str
    source_id: str
    source_url: str
    currency: str
    unit: str
    market_scope: str
    sector: str
    calculation_basis: str
    frequency: str
    effective_from: date
    effective_to: date | None
    source_access: str
    rights_requirement: str
    registry_state: str
    required_for_pilot: bool

    @property
    def role_key(self) -> str:
        scope = self.market_scope if self.market_scope == "BROAD_MARKET" else self.sector
        return f"{scope}:{self.calculation_basis}:{self.frequency}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_code": self.benchmark_code,
            "benchmark_code_namespace": "KU_BO_INTERNAL",
            "benchmark_name": self.benchmark_name,
            "provider": self.provider,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "currency": self.currency,
            "unit": self.unit,
            "market_scope": self.market_scope,
            "sector": self.sector,
            "calculation_basis": self.calculation_basis,
            "frequency": self.frequency,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": (
                None if self.effective_to is None else self.effective_to.isoformat()
            ),
            "source_access": self.source_access,
            "rights_requirement": self.rights_requirement,
            "registry_state": self.registry_state,
            "required_for_pilot": self.required_for_pilot,
        }


@dataclass(frozen=True)
class BenchmarkRegistry:
    registry_id: str
    registry_observed_on: date
    registry_date_basis: str
    claim_boundary: str
    benchmarks: tuple[BenchmarkDefinition, ...]
    sha256: str
    source_bytes: bytes

    @property
    def by_code(self) -> dict[str, BenchmarkDefinition]:
        return {item.benchmark_code: item for item in self.benchmarks}

    @property
    def required_codes(self) -> frozenset[str]:
        return frozenset(
            item.benchmark_code for item in self.benchmarks if item.required_for_pilot
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BENCHMARK_REGISTRY_SCHEMA_VERSION,
            "registry_id": self.registry_id,
            "registry_observed_on": self.registry_observed_on.isoformat(),
            "registry_date_basis": self.registry_date_basis,
            "claim_boundary": self.claim_boundary,
            "benchmarks": [item.to_dict() for item in self.benchmarks],
        }


def _registry_path(config_dir: Path) -> Path:
    value = Path(config_dir)
    return value / BENCHMARK_REGISTRY_FILE if value.is_dir() else value


def _definition(row: Any, *, index: int, observed_on: date) -> BenchmarkDefinition:
    field = f"benchmarks[{index}]"
    if not isinstance(row, dict) or set(row) != _BENCHMARK_FIELDS:
        raise ValueError(f"{field} has unknown or missing fields")
    code = str(row["benchmark_code"])
    if not BENCHMARK_CODE_RE.fullmatch(code):
        raise ValueError(f"{field}.benchmark_code must be a KU-BO internal code")
    if row["benchmark_code_namespace"] != "KU_BO_INTERNAL":
        raise ValueError(f"{field}.benchmark_code_namespace must be KU_BO_INTERNAL")
    name = str(row["benchmark_name"]).strip()
    provider = str(row["provider"]).strip()
    source_id = str(row["source_id"]).strip()
    if not name or not provider:
        raise ValueError(f"{field} requires benchmark_name and provider")
    if not SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError(f"{field}.source_id is invalid")
    source_url = https_url(row["source_url"], f"{field}.source_url")
    currency = str(row["currency"]).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError(f"{field}.currency must be an ISO-style three-letter code")
    if row["unit"] != "INDEX_POINTS":
        raise ValueError(f"{field}.unit must be INDEX_POINTS")
    market_scope = str(row["market_scope"])
    calculation_basis = str(row["calculation_basis"])
    if market_scope not in MARKET_SCOPES:
        raise ValueError(f"{field}.market_scope is invalid")
    if calculation_basis not in CALCULATION_BASES:
        raise ValueError(f"{field}.calculation_basis is invalid")
    sector = str(row["sector"]).strip()
    if market_scope == "BROAD_MARKET" and sector:
        raise ValueError(f"{field}: broad-market benchmarks must not declare sector")
    if market_scope == "SECTOR" and not sector:
        raise ValueError(f"{field}: sector benchmarks require sector")
    if row["frequency"] != "DAILY_CLOSE":
        raise ValueError(f"{field}.frequency must be DAILY_CLOSE")
    effective_from = parse_iso_date(row["effective_from"], f"{field}.effective_from")
    effective_to = (
        None
        if row["effective_to"] is None
        else parse_iso_date(row["effective_to"], f"{field}.effective_to")
    )
    if effective_from != observed_on:
        raise ValueError(
            f"{field}.effective_from must equal registry_observed_on under the registry date basis"
        )
    if effective_to is not None and effective_to < effective_from:
        raise ValueError(f"{field}.effective_to precedes effective_from")
    source_access = str(row["source_access"])
    rights_requirement = str(row["rights_requirement"])
    if source_access not in SOURCE_ACCESS_VALUES:
        raise ValueError(f"{field}.source_access is invalid")
    if rights_requirement not in RIGHTS_REQUIREMENTS:
        raise ValueError(f"{field}.rights_requirement is invalid")
    compatible_rights = {
        "PUBLIC_OFFICIAL_EXPORT": "PUBLIC_RESEARCH_ALLOWED",
        "LICENSED_EXPORT": "EXTERNAL_LICENSE_REQUIRED",
        "RECORDED_AUTHORIZED_FIXTURE": "RECORDED_FIXTURE_ONLY",
    }
    if compatible_rights[source_access] != rights_requirement:
        raise ValueError(f"{field}: source_access and rights_requirement conflict")
    registry_state = str(row["registry_state"])
    if registry_state not in REGISTRY_STATES:
        raise ValueError(f"{field}.registry_state is invalid")
    required = strict_bool(row["required_for_pilot"], f"{field}.required_for_pilot")
    return BenchmarkDefinition(
        benchmark_code=code,
        benchmark_name=name,
        provider=provider,
        source_id=source_id,
        source_url=source_url,
        currency=currency,
        unit="INDEX_POINTS",
        market_scope=market_scope,
        sector=sector,
        calculation_basis=calculation_basis,
        frequency="DAILY_CLOSE",
        effective_from=effective_from,
        effective_to=effective_to,
        source_access=source_access,
        rights_requirement=rights_requirement,
        registry_state=registry_state,
        required_for_pilot=required,
    )


def load_benchmark_registry(config_dir: Path) -> BenchmarkRegistry:
    path = _registry_path(config_dir)
    payload, content = load_strict_json_object(
        path,
        field="benchmark registry",
        max_bytes=2 * 1024 * 1024,
    )
    if set(payload) != _TOP_FIELDS:
        raise ValueError("benchmark registry has unknown or missing fields")
    if payload["schema_version"] != BENCHMARK_REGISTRY_SCHEMA_VERSION:
        raise ValueError("unsupported benchmark registry schema_version")
    registry_id = str(payload["registry_id"]).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", registry_id):
        raise ValueError("benchmark registry_id is invalid")
    observed_on = parse_iso_date(payload["registry_observed_on"], "registry_observed_on")
    if payload["registry_date_basis"] != REGISTRY_DATE_BASIS:
        raise ValueError("benchmark registry_date_basis is not the frozen KU-BO basis")
    if payload["claim_boundary"] != REGISTRY_CLAIM_BOUNDARY:
        raise ValueError("benchmark registry claim_boundary is not the frozen KU-BO boundary")
    rows = payload["benchmarks"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("benchmark registry must contain benchmark definitions")
    definitions = tuple(
        _definition(row, index=index, observed_on=observed_on)
        for index, row in enumerate(rows)
    )
    codes = [item.benchmark_code for item in definitions]
    if len(codes) != len(set(codes)):
        raise ValueError("benchmark registry contains duplicate benchmark_code")
    roles = [item.role_key for item in definitions]
    if len(roles) != len(set(roles)):
        raise ValueError("benchmark registry contains ambiguous duplicate comparison roles")

    required_roles = {
        f"BROAD_MARKET:{basis}:DAILY_CLOSE"
        for basis in CALCULATION_BASES
    } | {
        f"{sector}:{basis}:DAILY_CLOSE"
        for sector in PILOT_SECTORS
        for basis in CALCULATION_BASES
    }
    actual_required = {
        item.role_key for item in definitions if item.required_for_pilot
    }
    if actual_required != required_roles:
        missing = sorted(required_roles - actual_required)
        extra = sorted(actual_required - required_roles)
        raise ValueError(
            "benchmark registry pilot role mismatch: "
            f"missing={','.join(missing)}:extra={','.join(extra)}"
        )
    return BenchmarkRegistry(
        registry_id=registry_id,
        registry_observed_on=observed_on,
        registry_date_basis=REGISTRY_DATE_BASIS,
        claim_boundary=REGISTRY_CLAIM_BOUNDARY,
        benchmarks=definitions,
        sha256=sha256_bytes(content),
        source_bytes=content,
    )


__all__ = [
    "BENCHMARK_CODE_RE",
    "BENCHMARK_REGISTRY_FILE",
    "BENCHMARK_REGISTRY_SCHEMA_VERSION",
    "CALCULATION_BASES",
    "MARKET_SCOPES",
    "PILOT_SECTORS",
    "REGISTRY_CLAIM_BOUNDARY",
    "REGISTRY_DATE_BASIS",
    "RIGHTS_REQUIREMENTS",
    "SOURCE_ACCESS_VALUES",
    "BenchmarkDefinition",
    "BenchmarkRegistry",
    "load_benchmark_registry",
]
