from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping

from .benchmark_registry import BenchmarkRegistry
from .foundation_io import read_csv_bytes, safe_regular_file, write_csv
from .strict import contains_placeholder, https_url, parse_aware, parse_iso_date, require_sha256


BENCHMARK_HISTORY_SCHEMA_VERSION = "1.0"
BENCHMARK_HISTORY_HEADERS = (
    "trade_date",
    "benchmark_code",
    "benchmark_name",
    "market_scope",
    "sector",
    "calculation_basis",
    "benchmark_value",
    "currency",
    "unit",
    "provider",
    "source_id",
    "source_url",
    "raw_sha256",
    "observed_at",
    "capture_mode",
    "rights_status",
    "evidence_classification",
)
RAW_BENCHMARK_EXPORT_HEADERS = ("trade_date", "benchmark_value")
MAX_BENCHMARK_VALUE = Decimal("1000000000000")
CAPTURE_MODES = frozenset(
    {
        "PUBLIC_OFFICIAL_EXPORT",
        "USER_PROVIDED_OFFICIAL_EXPORT",
        "LICENSED_VENDOR_EXPORT",
        "RECORDED_AUTHORIZED_FIXTURE",
        "SYNTHETIC_GENERATED",
    }
)
RIGHTS_STATUSES = frozenset(
    {
        "RESEARCH_USE_AUTHORIZED",
        "FIXTURE_ONLY",
        "UNKNOWN",
        "RESTRICTED",
    }
)
ROW_EVIDENCE_CLASSIFICATIONS = frozenset(
    {
        "PROVEN_REAL_EVIDENCE",
        "RECORDED_AUTHORIZED_FIXTURE",
        "SYNTHETIC_ONLY",
        "LICENSED_FEED_DEPENDENT",
        "LIVE_DEPENDENT",
    }
)


@dataclass(frozen=True)
class BenchmarkEvidenceBinding:
    benchmark_code: str
    source_url: str
    raw_sha256: str
    observed_at: str
    capture_mode: str
    rights_status: str
    evidence_classification: str


@dataclass(frozen=True)
class BenchmarkHistoryRow:
    trade_date: date
    benchmark_code: str
    benchmark_name: str
    market_scope: str
    sector: str
    calculation_basis: str
    benchmark_value: Decimal
    currency: str
    unit: str
    provider: str
    source_id: str
    source_url: str
    raw_sha256: str
    observed_at: str
    capture_mode: str
    rights_status: str
    evidence_classification: str

    def to_csv_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["trade_date"] = self.trade_date.isoformat()
        row["benchmark_value"] = str(self.benchmark_value)
        return row


@dataclass(frozen=True)
class BenchmarkHistoryValidation:
    status: str
    rows: int
    benchmarks: int
    errors: tuple[str, ...]
    coverage: dict[str, dict[str, Any]]
    claim_boundaries: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BENCHMARK_HISTORY_SCHEMA_VERSION,
            "status": self.status,
            "rows": self.rows,
            "benchmarks": self.benchmarks,
            "errors": list(self.errors),
            "coverage": self.coverage,
            "claim_boundaries": self.claim_boundaries,
        }


def _decimal(value: Any, field: str) -> Decimal:
    text = str("" if value is None else value).strip()
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    if parsed <= 0 or parsed > MAX_BENCHMARK_VALUE:
        raise ValueError(
            f"{field} must be positive and <= {MAX_BENCHMARK_VALUE}"
        )
    return parsed


def _validate_evidence_tuple(
    *,
    capture_mode: str,
    rights_status: str,
    evidence_classification: str,
    registry_state: str,
) -> None:
    if capture_mode not in CAPTURE_MODES:
        raise ValueError("capture_mode is invalid")
    if rights_status not in RIGHTS_STATUSES:
        raise ValueError("rights_status is invalid")
    if evidence_classification not in ROW_EVIDENCE_CLASSIFICATIONS:
        raise ValueError("evidence_classification is invalid for a materialized row")
    expected = {
        "RECORDED_AUTHORIZED_FIXTURE": (
            "FIXTURE_ONLY",
            "RECORDED_AUTHORIZED_FIXTURE",
        ),
        "SYNTHETIC_GENERATED": ("FIXTURE_ONLY", "SYNTHETIC_ONLY"),
        "LICENSED_VENDOR_EXPORT": (
            "RESEARCH_USE_AUTHORIZED",
            "LICENSED_FEED_DEPENDENT",
        ),
    }
    if capture_mode in expected and expected[capture_mode] != (
        rights_status,
        evidence_classification,
    ):
        raise ValueError("capture_mode, rights_status, and evidence classification conflict")
    if capture_mode in {"PUBLIC_OFFICIAL_EXPORT", "USER_PROVIDED_OFFICIAL_EXPORT"}:
        if rights_status != "RESEARCH_USE_AUTHORIZED":
            raise ValueError("official export requires RESEARCH_USE_AUTHORIZED")
        if registry_state != "VERIFIED_DEFINITION":
            raise ValueError(
                "official real-evidence classification requires verified registry metadata"
            )
        if evidence_classification != "LIVE_DEPENDENT":
            raise ValueError(
                "official export without artifact-bound capture authority must use "
                "LIVE_DEPENDENT"
            )


def parse_benchmark_history_row(
    row: Mapping[str, Any],
    *,
    registry: BenchmarkRegistry,
    bindings: Mapping[str, BenchmarkEvidenceBinding],
    manifest_hashes: frozenset[str],
) -> BenchmarkHistoryRow:
    if set(row) != set(BENCHMARK_HISTORY_HEADERS):
        raise ValueError("normalized row has unknown or missing fields")
    if any(contains_placeholder(value) for value in row.values()):
        raise ValueError("template placeholder is forbidden")
    code = str(row.get("benchmark_code", "")).strip()
    definition = registry.by_code.get(code)
    if definition is None:
        raise ValueError("benchmark_code is not in the registry")
    binding = bindings.get(code)
    if binding is None:
        raise ValueError("benchmark_code lacks an available evidence binding")
    day = parse_iso_date(row.get("trade_date"), "trade_date")
    value = _decimal(row.get("benchmark_value"), "benchmark_value")
    frozen = {
        "benchmark_name": definition.benchmark_name,
        "market_scope": definition.market_scope,
        "sector": definition.sector,
        "calculation_basis": definition.calculation_basis,
        "currency": definition.currency,
        "unit": definition.unit,
        "provider": definition.provider,
        "source_id": definition.source_id,
    }
    for field, expected in frozen.items():
        if str(row.get(field, "")) != expected:
            raise ValueError(f"{field} differs from the benchmark registry")
    source_url = https_url(row.get("source_url"), "source_url")
    digest = require_sha256(row.get("raw_sha256"), "raw_sha256")
    observed_at = parse_aware(row.get("observed_at"), "observed_at").isoformat()
    capture_mode = str(row.get("capture_mode", ""))
    rights_status = str(row.get("rights_status", ""))
    evidence_classification = str(row.get("evidence_classification", ""))
    expected_binding = {
        "source_url": binding.source_url,
        "raw_sha256": binding.raw_sha256,
        "observed_at": binding.observed_at,
        "capture_mode": binding.capture_mode,
        "rights_status": binding.rights_status,
        "evidence_classification": binding.evidence_classification,
    }
    actual_binding = {
        "source_url": source_url,
        "raw_sha256": digest,
        "observed_at": observed_at,
        "capture_mode": capture_mode,
        "rights_status": rights_status,
        "evidence_classification": evidence_classification,
    }
    if actual_binding != expected_binding:
        raise ValueError("normalized evidence metadata differs from the accepted binding")
    if digest not in manifest_hashes:
        raise ValueError("raw_sha256 does not resolve")
    _validate_evidence_tuple(
        capture_mode=capture_mode,
        rights_status=rights_status,
        evidence_classification=evidence_classification,
        registry_state=definition.registry_state,
    )
    return BenchmarkHistoryRow(
        trade_date=day,
        benchmark_code=code,
        benchmark_name=definition.benchmark_name,
        market_scope=definition.market_scope,
        sector=definition.sector,
        calculation_basis=definition.calculation_basis,
        benchmark_value=value,
        currency=definition.currency,
        unit=definition.unit,
        provider=definition.provider,
        source_id=definition.source_id,
        source_url=source_url,
        raw_sha256=digest,
        observed_at=observed_at,
        capture_mode=capture_mode,
        rights_status=rights_status,
        evidence_classification=evidence_classification,
    )


def validate_benchmark_history_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    registry: BenchmarkRegistry,
    bindings: Mapping[str, BenchmarkEvidenceBinding],
    manifest_hashes: frozenset[str],
    trading_dates: frozenset[date],
    window_from: date,
    window_to: date,
    expected_codes: frozenset[str],
) -> tuple[tuple[BenchmarkHistoryRow, ...], BenchmarkHistoryValidation]:
    raw_rows = list(rows)
    errors: list[str] = []
    parsed: list[BenchmarkHistoryRow] = []
    seen: set[tuple[str, date]] = set()
    previous_by_code: dict[str, date] = {}
    expected_dates = frozenset(
        day for day in trading_dates if window_from <= day <= window_to
    )
    if not expected_dates:
        errors.append("BENCHMARK_WINDOW_HAS_NO_OFFICIAL_TRADING_DATES")
    for index, row in enumerate(raw_rows):
        try:
            item = parse_benchmark_history_row(
                row,
                registry=registry,
                bindings=bindings,
                manifest_hashes=manifest_hashes,
            )
            if item.benchmark_code not in expected_codes:
                raise ValueError("row belongs to a benchmark not declared AVAILABLE")
            key = (item.benchmark_code, item.trade_date)
            if key in seen:
                raise ValueError("duplicate benchmark/trading-date key")
            previous = previous_by_code.get(item.benchmark_code)
            if previous is not None and item.trade_date <= previous:
                raise ValueError("benchmark dates must be strictly increasing")
            if item.trade_date not in expected_dates:
                raise ValueError("benchmark row is not an official trading date in the window")
            seen.add(key)
            previous_by_code[item.benchmark_code] = item.trade_date
            parsed.append(item)
        except (TypeError, ValueError) as exc:
            errors.append(f"benchmark_row_{index}:{exc}")

    grouped: dict[str, list[BenchmarkHistoryRow]] = {}
    for item in parsed:
        grouped.setdefault(item.benchmark_code, []).append(item)
    coverage: dict[str, dict[str, Any]] = {}
    for code in sorted(expected_codes):
        items = grouped.get(code, [])
        actual_dates = frozenset(item.trade_date for item in items)
        missing_dates = sorted(expected_dates - actual_dates)
        extra_dates = sorted(actual_dates - expected_dates)
        if missing_dates:
            errors.append(f"BENCHMARK_TRADING_DATE_GAP:{code}:{len(missing_dates)}")
        if extra_dates:
            errors.append(f"BENCHMARK_EXTRA_TRADING_DATES:{code}:{len(extra_dates)}")
        definition = registry.by_code.get(code)
        coverage[code] = {
            "row_count": len(items),
            "expected_trading_dates": len(expected_dates),
            "date_start": "" if not items else min(item.trade_date for item in items).isoformat(),
            "date_end": "" if not items else max(item.trade_date for item in items).isoformat(),
            "missing_trading_dates": [day.isoformat() for day in missing_dates],
            "extra_trading_dates": [day.isoformat() for day in extra_dates],
            "market_scope": "" if definition is None else definition.market_scope,
            "sector": "" if definition is None else definition.sector,
            "calculation_basis": (
                "" if definition is None else definition.calculation_basis
            ),
            "evidence_classification": (
                "" if code not in bindings else bindings[code].evidence_classification
            ),
        }
    unknown_groups = sorted(set(grouped) - expected_codes)
    if unknown_groups:
        errors.append("UNDECLARED_AVAILABLE_BENCHMARKS:" + ",".join(unknown_groups))
    if not expected_codes:
        errors.append("NO_AVAILABLE_BENCHMARK_SERIES")
    status = "PASS" if parsed and not errors else "BLOCKED"
    validation = BenchmarkHistoryValidation(
        status=status,
        rows=len(parsed),
        benchmarks=len(grouped),
        errors=tuple(sorted(set(errors))),
        coverage=coverage,
        claim_boundaries={
            "price_index_used_as_total_return_index": False,
            "broad_market_used_as_sector_benchmark": False,
            "fallback_benchmark_substitution_used": False,
            "forward_fill_used": False,
            "synthetic_benchmark_rows_created": any(
                item.evidence_classification == "SYNTHETIC_ONLY" for item in parsed
            ),
            "registry_effective_from_used_as_series_inception": False,
            "backtest_ready": False,
        },
    )
    return tuple(parsed), validation


def read_benchmark_history(
    path: Path,
    *,
    registry: BenchmarkRegistry,
    bindings: Mapping[str, BenchmarkEvidenceBinding],
    manifest_hashes: frozenset[str],
    trading_dates: frozenset[date],
    window_from: date,
    window_to: date,
    expected_codes: frozenset[str],
) -> tuple[tuple[BenchmarkHistoryRow, ...], BenchmarkHistoryValidation]:
    try:
        content = safe_regular_file(
            path,
            field="benchmark_history.csv",
            max_bytes=64 * 1024 * 1024,
        )
        _, rows = read_csv_bytes(
            content,
            field="benchmark_history.csv",
            exact_headers=BENCHMARK_HISTORY_HEADERS,
        )
    except ValueError as exc:
        return (), BenchmarkHistoryValidation(
            status="BLOCKED",
            rows=0,
            benchmarks=0,
            errors=(f"BENCHMARK_HISTORY_READ:{exc}",),
            coverage={},
            claim_boundaries={
                "price_index_used_as_total_return_index": False,
                "broad_market_used_as_sector_benchmark": False,
                "fallback_benchmark_substitution_used": False,
                "forward_fill_used": False,
                "synthetic_benchmark_rows_created": False,
                "registry_effective_from_used_as_series_inception": False,
                "backtest_ready": False,
            },
        )
    return validate_benchmark_history_rows(
        rows,
        registry=registry,
        bindings=bindings,
        manifest_hashes=manifest_hashes,
        trading_dates=trading_dates,
        window_from=window_from,
        window_to=window_to,
        expected_codes=expected_codes,
    )


def write_benchmark_history(path: Path, rows: Iterable[BenchmarkHistoryRow]) -> None:
    ordered = sorted(rows, key=lambda item: (item.benchmark_code, item.trade_date))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_csv(
        target,
        headers=BENCHMARK_HISTORY_HEADERS,
        rows=[item.to_csv_dict() for item in ordered],
    )


__all__ = [
    "BENCHMARK_HISTORY_HEADERS",
    "BENCHMARK_HISTORY_SCHEMA_VERSION",
    "CAPTURE_MODES",
    "MAX_BENCHMARK_VALUE",
    "RAW_BENCHMARK_EXPORT_HEADERS",
    "RIGHTS_STATUSES",
    "ROW_EVIDENCE_CLASSIFICATIONS",
    "BenchmarkEvidenceBinding",
    "BenchmarkHistoryRow",
    "BenchmarkHistoryValidation",
    "parse_benchmark_history_row",
    "read_benchmark_history",
    "validate_benchmark_history_rows",
    "write_benchmark_history",
]
