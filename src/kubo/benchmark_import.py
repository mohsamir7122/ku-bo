from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
from typing import Any

from .atomic_output import run_atomic_output
from .benchmark_history import (
    MAX_BENCHMARK_VALUE,
    RAW_BENCHMARK_EXPORT_HEADERS,
    BenchmarkEvidenceBinding,
    BenchmarkHistoryRow,
    validate_benchmark_history_rows,
    write_benchmark_history,
)
from .benchmark_registry import (
    BenchmarkDefinition,
    BenchmarkRegistry,
    load_benchmark_registry,
)
from .benchmark_workspace import (
    BENCHMARK_MANIFEST_SCHEMA_VERSION,
    OfficialCalendarReceipt,
    load_official_calendar_receipt,
)
from .foundation_io import (
    load_strict_json_object,
    nonnegative_int,
    positive_int,
    prepare_output_root,
    read_csv_bytes,
    require_real_directory,
    safe_regular_file,
)
from .hashing import canonical_json_bytes, sha256_bytes
from .strict import parse_aware, parse_iso_date, require_sha256, safe_relative_path
from .tri_security_admission import (
    BoundaryAdmissionRequest,
    admit_boundary,
    build_boundary_operation_binding,
)


MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_ARTIFACT_ROWS = 100_000
AVAILABILITY_STATUSES = frozenset({"AVAILABLE", "ZERO_RESULT", "UNAVAILABLE"})
CAPTURE_MODES = frozenset(
    {
        "PUBLIC_OFFICIAL_EXPORT",
        "USER_PROVIDED_OFFICIAL_EXPORT",
        "LICENSED_VENDOR_EXPORT",
        "RECORDED_AUTHORIZED_FIXTURE",
        "SYNTHETIC_GENERATED",
        "SOURCE_ACCESS_RECEIPT",
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
UNAVAILABLE_REASONS = frozenset(
    {
        "LIVE_SOURCE_UNAVAILABLE",
        "EXTERNAL_LICENSE_REQUIRED",
        "AUTHORIZED_EXPORT_NOT_SUPPLIED",
    }
)
REPORT_EVIDENCE_CLASSIFICATIONS = frozenset(
    {
        "PROVEN_REAL_EVIDENCE",
        "RECORDED_AUTHORIZED_FIXTURE",
        "SYNTHETIC_ONLY",
        "PARTIAL",
        "BLOCKED",
        "LIVE_DEPENDENT",
        "LICENSED_FEED_DEPENDENT",
    }
)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_TOP_FIELDS = {
    "schema_version",
    "run_id",
    "registry_id",
    "registry_sha256",
    "registry_date_basis",
    "window_from",
    "window_to",
    "upstream",
    "artifacts",
}
_ARTIFACT_FIELDS = {
    "benchmark_code",
    "source_id",
    "source_url",
    "provider",
    "file_name",
    "availability_status",
    "file_sha256",
    "observed_at",
    "captured_by",
    "capture_mode",
    "rights_status",
    "window_from",
    "window_to",
    "pages_declared",
    "pages_received",
    "result_count_declared",
    "row_count",
    "review_status",
    "review_notes",
    "unavailable_reason",
}


@dataclass(frozen=True)
class AcceptedArtifact:
    definition: BenchmarkDefinition
    file_name: str
    content: bytes
    availability_status: str
    raw_sha256: str
    observed_at: str
    capture_mode: str
    rights_status: str
    evidence_classification: str
    pages_declared: int
    pages_received: int
    result_count_declared: int
    row_count: int
    unavailable_reason: str
    raw_rows: tuple[dict[str, str], ...]

    @property
    def binding(self) -> BenchmarkEvidenceBinding:
        return BenchmarkEvidenceBinding(
            benchmark_code=self.definition.benchmark_code,
            source_url=self.definition.source_url,
            raw_sha256=self.raw_sha256,
            observed_at=self.observed_at,
            capture_mode=self.capture_mode,
            rights_status=self.rights_status,
            evidence_classification=self.evidence_classification,
        )


def _derived_evidence_classification(
    definition: BenchmarkDefinition,
    *,
    capture_mode: str,
    rights_status: str,
) -> str:
    if capture_mode == "SOURCE_ACCESS_RECEIPT":
        expected = {
            "PUBLIC_OFFICIAL_EXPORT": (
                "UNKNOWN",
                "LIVE_DEPENDENT",
            ),
            "LICENSED_EXPORT": (
                "RESTRICTED",
                "LICENSED_FEED_DEPENDENT",
            ),
            "RECORDED_AUTHORIZED_FIXTURE": (
                "FIXTURE_ONLY",
                "RECORDED_AUTHORIZED_FIXTURE",
            ),
        }
        expected_rights, classification = expected[definition.source_access]
        if rights_status != expected_rights:
            raise ValueError("access receipt rights differ from the registry source contract")
        return classification
    pairs = {
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
    if capture_mode in pairs:
        expected_rights, classification = pairs[capture_mode]
        if rights_status != expected_rights:
            raise ValueError("capture_mode and rights_status conflict")
        if capture_mode == "LICENSED_VENDOR_EXPORT" and (
            definition.source_access != "LICENSED_EXPORT"
            or definition.rights_requirement != "EXTERNAL_LICENSE_REQUIRED"
        ):
            raise ValueError("licensed capture is outside the registry source contract")
        return classification
    if capture_mode in {"PUBLIC_OFFICIAL_EXPORT", "USER_PROVIDED_OFFICIAL_EXPORT"}:
        if rights_status != "RESEARCH_USE_AUTHORIZED":
            raise ValueError("official capture requires RESEARCH_USE_AUTHORIZED")
        if definition.source_access != "PUBLIC_OFFICIAL_EXPORT":
            raise ValueError("official capture is outside the registry source contract")
        if definition.registry_state != "VERIFIED_DEFINITION":
            raise ValueError("real evidence requires verified benchmark definition metadata")
        # Registry metadata and a packet-local manifest establish the expected
        # contract, but do not independently prove that these exact bytes were
        # captured from the named source.  Keep the artifact dependent until an
        # external authenticated receipt binds its SHA-256 and capture event.
        return "LIVE_DEPENDENT"
    raise ValueError("unsupported capture_mode")


def _validate_upstream(
    manifest_upstream: Any,
    current: OfficialCalendarReceipt,
) -> None:
    if not isinstance(manifest_upstream, dict):
        raise ValueError("benchmark manifest upstream receipt must be an object")
    expected = current.to_dict()
    if manifest_upstream != expected:
        raise ValueError("benchmark manifest has a stale or mismatched upstream calendar receipt")


def _load_manifest(
    *,
    workspace: Path,
    registry: BenchmarkRegistry,
    receipt: OfficialCalendarReceipt,
    imported_at: datetime,
) -> tuple[dict[str, Any], bytes, dict[str, dict[str, Any]]]:
    payload, content = load_strict_json_object(
        workspace / "manifests" / "benchmark_history_manifest.json",
        field="benchmark history manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    if set(payload) != _TOP_FIELDS:
        raise ValueError("benchmark history manifest has unknown or missing fields")
    if payload["schema_version"] != BENCHMARK_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported benchmark history manifest schema_version")
    run_id = str(payload["run_id"])
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("benchmark manifest run_id is invalid")
    if payload["registry_id"] != registry.registry_id:
        raise ValueError("benchmark manifest registry_id mismatch")
    if require_sha256(payload["registry_sha256"], "registry_sha256") != registry.sha256:
        raise ValueError("benchmark manifest registry_sha256 mismatch")
    if payload["registry_date_basis"] != registry.registry_date_basis:
        raise ValueError("benchmark manifest registry_date_basis mismatch")
    preserved_registry = safe_regular_file(
        workspace / "manifests" / "benchmark_registry.json",
        field="workspace benchmark registry snapshot",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    if sha256_bytes(preserved_registry) != registry.sha256:
        raise ValueError("workspace benchmark registry snapshot is stale")
    start = parse_iso_date(payload["window_from"], "window_from")
    end = parse_iso_date(payload["window_to"], "window_to")
    if start > end:
        raise ValueError("benchmark manifest window is reversed")
    if start < receipt.window_from or end > receipt.window_to:
        raise ValueError("benchmark manifest window is outside official calendar")
    if not any(start <= day <= end for day in receipt.trading_dates):
        raise ValueError("benchmark manifest window has no official trading dates")
    payload["window_from"] = start
    payload["window_to"] = end
    _validate_upstream(payload["upstream"], receipt)

    rows = payload["artifacts"]
    if not isinstance(rows, list) or len(rows) != len(registry.benchmarks):
        raise ValueError("benchmark manifest must contain every registry benchmark exactly once")
    artifacts: dict[str, dict[str, Any]] = {}
    file_names: set[str] = set()
    definitions = registry.by_code
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != _ARTIFACT_FIELDS:
            raise ValueError(f"benchmark artifact {index} has unknown or missing fields")
        code = str(row["benchmark_code"])
        definition = definitions.get(code)
        if definition is None or code in artifacts:
            raise ValueError(f"benchmark artifact {index} has unknown or duplicate code")
        for field in ("source_id", "source_url", "provider"):
            if row[field] != getattr(definition, field):
                raise ValueError(f"benchmark artifact {code}.{field} differs from registry")
        relative = safe_relative_path(row["file_name"], f"{code}.file_name")
        if (
            len(relative.parts) != 1
            or not _FILE_NAME_RE.fullmatch(relative.name)
            or relative.name in {".", ".."}
        ):
            raise ValueError(f"{code}.file_name must be one path-safe component")
        if relative.name.casefold() in file_names:
            raise ValueError("benchmark manifest contains duplicate file_name values")
        file_names.add(relative.name.casefold())
        availability = str(row["availability_status"])
        if availability not in AVAILABILITY_STATUSES:
            raise ValueError(f"{code}.availability_status is invalid or pending")
        digest = require_sha256(row["file_sha256"], f"{code}.file_sha256")
        observed = parse_aware(row["observed_at"], f"{code}.observed_at")
        if observed > imported_at:
            raise ValueError(f"{code}.observed_at is after benchmark imported_at")
        if not str(row["captured_by"]).strip():
            raise ValueError(f"{code}.captured_by is required")
        capture_mode = str(row["capture_mode"])
        rights_status = str(row["rights_status"])
        if capture_mode not in CAPTURE_MODES or rights_status not in RIGHTS_STATUSES:
            raise ValueError(f"{code} has invalid capture or rights status")
        classification = _derived_evidence_classification(
            definition,
            capture_mode=capture_mode,
            rights_status=rights_status,
        )
        if availability == "UNAVAILABLE" and capture_mode != "SOURCE_ACCESS_RECEIPT":
            raise ValueError(f"{code} UNAVAILABLE requires SOURCE_ACCESS_RECEIPT")
        if availability != "UNAVAILABLE" and capture_mode == "SOURCE_ACCESS_RECEIPT":
            raise ValueError(f"{code} source access receipt cannot contain benchmark rows")
        artifact_start = parse_iso_date(row["window_from"], f"{code}.window_from")
        artifact_end = parse_iso_date(row["window_to"], f"{code}.window_to")
        if artifact_start != start or artifact_end != end:
            raise ValueError(f"{code} window must exactly match the manifest window")
        pages_declared = nonnegative_int(row["pages_declared"], f"{code}.pages_declared")
        pages_received = nonnegative_int(row["pages_received"], f"{code}.pages_received")
        if pages_declared != pages_received:
            raise ValueError(f"{code} pagination is incomplete")
        result_count = nonnegative_int(
            row["result_count_declared"],
            f"{code}.result_count_declared",
        )
        row_count = nonnegative_int(row["row_count"], f"{code}.row_count")
        if row["review_status"] != "ACCEPTED":
            raise ValueError(f"benchmark artifact is not accepted: {code}")
        reason = str(row["unavailable_reason"]).strip()
        if availability == "AVAILABLE":
            positive_int(pages_declared, f"{code}.pages_declared")
            if result_count <= 0 or row_count <= 0 or result_count != row_count:
                raise ValueError(f"{code} AVAILABLE counts must be equal and positive")
            if reason:
                raise ValueError(f"{code} AVAILABLE must not declare unavailable_reason")
            if relative.suffix != ".csv":
                raise ValueError(f"{code} AVAILABLE requires a CSV export")
        elif availability == "ZERO_RESULT":
            positive_int(pages_declared, f"{code}.pages_declared")
            if result_count != 0 or row_count != 0:
                raise ValueError(f"{code} ZERO_RESULT requires zero counts")
            if reason:
                raise ValueError(f"{code} ZERO_RESULT must not declare unavailable_reason")
            if relative.suffix != ".csv":
                raise ValueError(f"{code} ZERO_RESULT requires a CSV receipt")
        else:
            if result_count != 0 or row_count != 0:
                raise ValueError(f"{code} UNAVAILABLE requires zero counts")
            if reason not in UNAVAILABLE_REASONS:
                raise ValueError(f"{code}.unavailable_reason is invalid")
        artifacts[code] = {
            **row,
            "file_name": relative.as_posix(),
            "file_sha256": digest,
            "observed_datetime": observed,
            "evidence_classification": classification,
            "pages_declared": pages_declared,
            "pages_received": pages_received,
            "result_count_declared": result_count,
            "row_count": row_count,
        }
    if set(artifacts) != set(definitions):
        raise ValueError("benchmark manifest artifact set is incomplete")
    return payload, content, artifacts


def _read_artifact(
    *,
    workspace: Path,
    definition: BenchmarkDefinition,
    row: dict[str, Any],
    window_from: date,
    window_to: date,
    trading_session_closes: dict[date, str],
) -> AcceptedArtifact:
    code = definition.benchmark_code
    content = safe_regular_file(
        workspace / "raw_exports" / "benchmarks" / row["file_name"],
        field=f"benchmark artifact {code}",
        max_bytes=MAX_ARTIFACT_BYTES,
    )
    if not content:
        raise ValueError(f"benchmark artifact {code} is empty")
    digest = sha256_bytes(content)
    if digest != row["file_sha256"]:
        raise ValueError(f"benchmark artifact hash mismatch: {code}")
    availability = row["availability_status"]
    parsed_rows: list[dict[str, str]] = []
    if availability in {"AVAILABLE", "ZERO_RESULT"}:
        _, parsed_rows = read_csv_bytes(
            content,
            field=f"benchmark export {code}",
            exact_headers=RAW_BENCHMARK_EXPORT_HEADERS,
        )
        if len(parsed_rows) > MAX_ARTIFACT_ROWS:
            raise ValueError(f"benchmark export {code} exceeds {MAX_ARTIFACT_ROWS} rows")
        if availability == "ZERO_RESULT" and parsed_rows:
            raise ValueError(f"benchmark export {code} ZERO_RESULT contains data rows")
        if availability == "AVAILABLE" and len(parsed_rows) != row["row_count"]:
            raise ValueError(f"benchmark export {code} row_count mismatch")
        if len(parsed_rows) != row["result_count_declared"]:
            raise ValueError(f"benchmark export {code} result_count mismatch")
        seen_dates: set[date] = set()
        previous: date | None = None
        for index, item in enumerate(parsed_rows):
            day = parse_iso_date(item["trade_date"], f"{code} row {index}.trade_date")
            if day in seen_dates:
                raise ValueError(f"benchmark export {code} contains duplicate dates")
            if previous is not None and day <= previous:
                raise ValueError(f"benchmark export {code} dates must be strictly increasing")
            if day < window_from or day > window_to:
                raise ValueError(f"benchmark export {code} contains a date outside its window")
            if day > row["observed_datetime"].date():
                raise ValueError(f"benchmark export {code} contains data after observed_at")
            close_time = trading_session_closes.get(day)
            if close_time is None:
                raise ValueError(
                    f"benchmark export {code} date is not an official trading session"
                )
            session_close = parse_aware(
                f"{day.isoformat()}T{close_time}+03:00",
                f"{code} row {index}.session_close",
            )
            if row["observed_datetime"] < session_close:
                raise ValueError(
                    f"benchmark export {code} observed_at precedes official session close"
                )
            seen_dates.add(day)
            previous = day
    return AcceptedArtifact(
        definition=definition,
        file_name=row["file_name"],
        content=content,
        availability_status=availability,
        raw_sha256=digest,
        observed_at=row["observed_datetime"].isoformat(),
        capture_mode=row["capture_mode"],
        rights_status=row["rights_status"],
        evidence_classification=row["evidence_classification"],
        pages_declared=row["pages_declared"],
        pages_received=row["pages_received"],
        result_count_declared=row["result_count_declared"],
        row_count=row["row_count"],
        unavailable_reason=row["unavailable_reason"],
        raw_rows=tuple(parsed_rows),
    )


def _normalized_rows(artifacts: tuple[AcceptedArtifact, ...]) -> list[BenchmarkHistoryRow]:
    rows: list[BenchmarkHistoryRow] = []
    for artifact in artifacts:
        if artifact.availability_status != "AVAILABLE":
            continue
        definition = artifact.definition
        for raw in artifact.raw_rows:
            rows.append(
                BenchmarkHistoryRow(
                    trade_date=parse_iso_date(raw["trade_date"], "trade_date"),
                    benchmark_code=definition.benchmark_code,
                    benchmark_name=definition.benchmark_name,
                    market_scope=definition.market_scope,
                    sector=definition.sector,
                    calculation_basis=definition.calculation_basis,
                    benchmark_value=_benchmark_value(raw["benchmark_value"]),
                    currency=definition.currency,
                    unit=definition.unit,
                    provider=definition.provider,
                    source_id=definition.source_id,
                    source_url=definition.source_url,
                    raw_sha256=artifact.raw_sha256,
                    observed_at=artifact.observed_at,
                    capture_mode=artifact.capture_mode,
                    rights_status=artifact.rights_status,
                    evidence_classification=artifact.evidence_classification,
                )
            )
    return rows


def _benchmark_value(value: str) -> Decimal:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise ValueError("benchmark_value must be a canonical positive decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("benchmark_value must be numeric") from exc
    if not parsed.is_finite() or parsed <= 0 or parsed > MAX_BENCHMARK_VALUE:
        raise ValueError("benchmark_value is outside the allowed positive range")
    return parsed


def _aggregate_evidence_classification(
    artifacts: tuple[AcceptedArtifact, ...],
) -> str:
    if not artifacts:
        return "BLOCKED"
    classifications = {item.evidence_classification for item in artifacts}
    if classifications == {"PROVEN_REAL_EVIDENCE"}:
        return "PROVEN_REAL_EVIDENCE"
    if classifications == {"RECORDED_AUTHORIZED_FIXTURE"}:
        return "RECORDED_AUTHORIZED_FIXTURE"
    if classifications == {"SYNTHETIC_ONLY"}:
        return "SYNTHETIC_ONLY"
    if classifications == {"LICENSED_FEED_DEPENDENT"}:
        return "LICENSED_FEED_DEPENDENT"
    if classifications == {"LIVE_DEPENDENT"}:
        return "LIVE_DEPENDENT"
    return "PARTIAL"


def _comparison_report(
    registry: BenchmarkRegistry,
    *,
    artifacts: tuple[AcceptedArtifact, ...],
    coverage: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_code = {item.definition.benchmark_code: item for item in artifacts}
    series: list[dict[str, Any]] = []
    by_role: dict[str, dict[str, Any]] = {}
    for definition in registry.benchmarks:
        artifact = by_code[definition.benchmark_code]
        item_coverage = coverage.get(definition.benchmark_code, {})
        complete = bool(
            artifact.availability_status == "AVAILABLE"
            and item_coverage
            and not item_coverage.get("missing_trading_dates")
            and not item_coverage.get("extra_trading_dates")
            and item_coverage.get("row_count")
            == item_coverage.get("expected_trading_dates")
        )
        row = {
            "benchmark_code": definition.benchmark_code,
            "role_key": definition.role_key,
            "market_scope": definition.market_scope,
            "sector": definition.sector,
            "calculation_basis": definition.calculation_basis,
            "frequency": definition.frequency,
            "contract_comparison_possible": complete,
            "real_evidence_comparison_possible": (
                complete
                and artifact.evidence_classification == "PROVEN_REAL_EVIDENCE"
            ),
            "evidence_classification": artifact.evidence_classification,
            "no_substitution_used": True,
        }
        series.append(row)
        by_role[definition.role_key] = row

    def summarize(rule: str, roles: list[str], kind: str) -> dict[str, Any]:
        selected = [by_role.get(role) for role in roles]
        contract = bool(
            selected
            and all(item and item["contract_comparison_possible"] for item in selected)
        )
        real = bool(
            selected
            and all(item and item["real_evidence_comparison_possible"] for item in selected)
        )
        return {
            "benchmark_rule": rule,
            "comparison_kind": kind,
            "required_roles": roles,
            "contract_comparison_possible": contract,
            "real_evidence_comparison_possible": real,
            "status": "READY" if real else ("CONTRACT_ONLY" if contract else "BLOCKED"),
        }

    price_roles = ["BROAD_MARKET:PRICE_INDEX:DAILY_CLOSE"] + [
        f"{sector}:PRICE_INDEX:DAILY_CLOSE"
        for sector in sorted({item.sector for item in registry.benchmarks if item.sector})
    ]
    total_return_roles = ["BROAD_MARKET:TOTAL_RETURN_INDEX:DAILY_CLOSE"] + [
        f"{sector}:TOTAL_RETURN_INDEX:DAILY_CLOSE"
        for sector in sorted({item.sector for item in registry.benchmarks if item.sector})
    ]
    product_rules = [
        summarize(
            "point_in_time_market_and_sector",
            price_roles,
            "DAILY_PRICE_RETURN_COMPARISON",
        ),
        summarize(
            "point_in_time_market_and_sector_total_return",
            total_return_roles,
            "DAILY_TOTAL_RETURN_COMPARISON",
        ),
        summarize(
            "event_prevalence_and_market_context",
            ["BROAD_MARKET:PRICE_INDEX:DAILY_CLOSE"],
            "DAILY_PRICE_INDEX_CONTEXT_ONLY",
        ),
        {
            "benchmark_rule": "rare_event_prevalence",
            "comparison_kind": "INDEX_HISTORY_NOT_REQUIRED",
            "required_roles": [],
            "contract_comparison_possible": False,
            "real_evidence_comparison_possible": False,
            "status": "NOT_APPLICABLE",
        },
        {
            "benchmark_rule": "opening_event_prevalence",
            "comparison_kind": "DAILY_INDEX_HISTORY_NOT_APPLICABLE",
            "required_roles": [],
            "contract_comparison_possible": False,
            "real_evidence_comparison_possible": False,
            "status": "NOT_APPLICABLE",
        },
        {
            "benchmark_rule": "same_interval_market_and_sector",
            "comparison_kind": "INTRADAY_BENCHMARK_REQUIRED",
            "required_roles": [],
            "contract_comparison_possible": False,
            "real_evidence_comparison_possible": False,
            "status": "BLOCKED_FREQUENCY_MISMATCH",
        },
    ]
    return {"series": series, "product_rules": product_rules}


def import_benchmark_history(
    *,
    config_dir: Path,
    official_foundation_root: Path,
    workspace: Path,
    output_root: Path,
    imported_at: str,
    admission_request: BoundaryAdmissionRequest,
) -> dict[str, Any]:
    requested_output = Path(os.path.abspath(output_root))
    operation_binding = build_boundary_operation_binding(
        "import_benchmark_history",
        decision_at=admission_request.decision_at,
        imported_at=imported_at,
    )
    token = admit_boundary(
        admission_request,
        boundary_id="import_benchmark_history",
        output_root=requested_output,
        boundary_inputs={
            "config_dir": Path(config_dir),
            "official_foundation_root": Path(official_foundation_root),
            "workspace": Path(workspace),
        },
        operation_binding=operation_binding,
    )

    def worker(staging: Path) -> dict[str, Any]:
        report = _import_benchmark_history_unchecked(
            config_dir=config_dir,
            official_foundation_root=official_foundation_root,
            workspace=workspace,
            output_root=staging,
            imported_at=imported_at,
            logical_output_root=requested_output,
        )
        token.materialize_receipt(staging)
        token.materialize_lineage(staging)
        return report

    return run_atomic_output(
        requested_output,
        worker,
        before_commit=lambda _staging: token.revalidate_before_commit(),
    )


def _import_benchmark_history_unchecked(
    *,
    config_dir: Path,
    official_foundation_root: Path,
    workspace: Path,
    output_root: Path,
    imported_at: str | None = None,
    logical_output_root: Path | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    import_time = now if imported_at is None else parse_aware(imported_at, "imported_at")
    if import_time > now:
        raise ValueError("benchmark imported_at must not be in the future")
    workspace_root = require_real_directory(workspace, field="workspace")
    registry = load_benchmark_registry(config_dir)
    receipt = load_official_calendar_receipt(official_foundation_root)
    manifest, manifest_bytes, manifest_artifacts = _load_manifest(
        workspace=workspace_root,
        registry=registry,
        receipt=receipt,
        imported_at=import_time,
    )
    accepted = tuple(
        _read_artifact(
            workspace=workspace_root,
            definition=definition,
            row=manifest_artifacts[definition.benchmark_code],
            window_from=manifest["window_from"],
            window_to=manifest["window_to"],
            trading_session_closes=receipt.trading_session_closes,
        )
        for definition in registry.benchmarks
    )
    candidate_rows = _normalized_rows(accepted)
    available_hashes = [
        item.raw_sha256
        for item in accepted
        if item.availability_status == "AVAILABLE"
    ]
    if len(set(available_hashes)) != len(available_hashes):
        raise ValueError("benchmark artifacts must have distinct evidence hashes")
    available_codes = frozenset(
        item.definition.benchmark_code
        for item in accepted
        if item.availability_status == "AVAILABLE"
    )
    bindings = {
        item.definition.benchmark_code: item.binding
        for item in accepted
        if item.availability_status == "AVAILABLE"
    }
    manifest_hashes = frozenset(item.raw_sha256 for item in accepted)
    normalized_rows, validation = validate_benchmark_history_rows(
        [item.to_csv_dict() for item in candidate_rows],
        registry=registry,
        bindings=bindings,
        manifest_hashes=manifest_hashes,
        trading_dates=receipt.trading_dates,
        window_from=manifest["window_from"],
        window_to=manifest["window_to"],
        expected_codes=available_codes,
    )
    evidence_classification = _aggregate_evidence_classification(accepted)
    if evidence_classification not in REPORT_EVIDENCE_CLASSIFICATIONS:
        raise AssertionError("internal benchmark evidence classification drift")
    all_required_available = registry.required_codes == available_codes
    real_ready = bool(
        all_required_available
        and validation.status == "PASS"
        and evidence_classification == "PROVEN_REAL_EVIDENCE"
        and all(
            item.definition.registry_state == "VERIFIED_DEFINITION"
            and item.capture_mode
            in {"PUBLIC_OFFICIAL_EXPORT", "USER_PROVIDED_OFFICIAL_EXPORT"}
            for item in accepted
        )
    )
    if real_ready:
        status = "BENCHMARK_HISTORY_READY"
    elif validation.rows > 0:
        status = "PARTIAL"
    else:
        status = "BLOCKED"

    output = prepare_output_root(output_root, label="benchmark import output")
    raw_output = output / "raw"
    normalized_output = output / "normalized"
    report_output = output / "reports"
    for directory in (raw_output, normalized_output, report_output):
        directory.mkdir(parents=True, exist_ok=True)
    evidence_artifacts: list[dict[str, Any]] = []
    for item in accepted:
        preserved = raw_output / item.file_name
        preserved.write_bytes(item.content)
        evidence_artifacts.append(
            {
                "path": preserved.relative_to(output).as_posix(),
                "sha256": item.raw_sha256,
                "size_bytes": len(item.content),
                "source_id": item.definition.source_id,
                "source_url": item.definition.source_url,
                "observed_at": item.observed_at,
                "capture_kind": {
                    "SOURCE_ACCESS_RECEIPT": "ACCESS_RECEIPT",
                    "PUBLIC_OFFICIAL_EXPORT": "RAW_DOWNLOAD",
                    "USER_PROVIDED_OFFICIAL_EXPORT": "USER_EXPORT",
                    "LICENSED_VENDOR_EXPORT": "USER_EXPORT",
                    "RECORDED_AUTHORIZED_FIXTURE": "RECORDED_AUTHORIZED_FIXTURE",
                    "SYNTHETIC_GENERATED": "SYNTHETIC_GENERATED",
                }[item.capture_mode],
                "artifact_role": (
                    "BENCHMARK_SOURCE_ACCESS_RECEIPT"
                    if item.availability_status == "UNAVAILABLE"
                    else "BENCHMARK_HISTORY_EXPORT"
                ),
                "benchmark_code": item.definition.benchmark_code,
                "availability_status": item.availability_status,
                "rights_status": item.rights_status,
                "evidence_classification": item.evidence_classification,
            }
        )
    evidence_manifest = {"schema_version": "3.0", "artifacts": evidence_artifacts}
    evidence_manifest_path = output / "manifest.json"
    evidence_manifest_path.write_bytes(canonical_json_bytes(evidence_manifest))
    (output / "benchmark_registry.json").write_bytes(registry.source_bytes)
    (output / "benchmark_history_manifest.json").write_bytes(manifest_bytes)
    upstream_receipt_path = output / "upstream_calendar_receipt.json"
    upstream_receipt_path.write_bytes(canonical_json_bytes(receipt.to_dict()))
    normalized_path = normalized_output / "benchmark_history.csv"
    write_benchmark_history(normalized_path, normalized_rows)

    comparison_report = _comparison_report(
        registry,
        artifacts=accepted,
        coverage=validation.coverage,
    )
    entry_reports: list[dict[str, Any]] = []
    availability_errors: list[str] = []
    for item in accepted:
        coverage = validation.coverage.get(item.definition.benchmark_code, {})
        if item.availability_status == "ZERO_RESULT":
            availability_errors.append(
                f"BENCHMARK_ZERO_RESULT:{item.definition.benchmark_code}"
            )
        elif item.availability_status == "UNAVAILABLE":
            availability_errors.append(
                f"BENCHMARK_UNAVAILABLE:{item.definition.benchmark_code}:{item.unavailable_reason}"
            )
        validation_status = "PASS" if (
            item.availability_status == "AVAILABLE"
            and coverage
            and not coverage.get("missing_trading_dates")
            and not coverage.get("extra_trading_dates")
            and coverage.get("row_count") == coverage.get("expected_trading_dates")
        ) else "BLOCKED"
        entry_reports.append(
            {
                "benchmark_code": item.definition.benchmark_code,
                "availability_status": item.availability_status,
                "validation_status": validation_status,
                "row_count": item.row_count,
                "expected_trading_dates": coverage.get(
                    "expected_trading_dates",
                    sum(
                        manifest["window_from"] <= day <= manifest["window_to"]
                        for day in receipt.trading_dates
                    ),
                ),
                "missing_trading_dates": coverage.get("missing_trading_dates", []),
                "extra_trading_dates": coverage.get("extra_trading_dates", []),
                "pages_declared": item.pages_declared,
                "pages_received": item.pages_received,
                "result_count_declared": item.result_count_declared,
                "evidence_classification": item.evidence_classification,
                "rights_status": item.rights_status,
                "errors": (
                    []
                    if validation_status == "PASS"
                    else [
                        item.unavailable_reason
                        or (
                            "ZERO_RESULT"
                            if item.availability_status == "ZERO_RESULT"
                            else "TRADING_DATE_RECONCILIATION_FAILED"
                        )
                    ]
                ),
            }
        )

    logical_output = (
        Path(os.path.abspath(logical_output_root))
        if logical_output_root is not None
        else output
    )
    report = {
        "schema_version": "1.0",
        "status": status,
        "contract_status": validation.status,
        "run_id": manifest["run_id"],
        "imported_at": import_time.isoformat(),
        "output_root": str(logical_output),
        "window_from": manifest["window_from"].isoformat(),
        "window_to": manifest["window_to"].isoformat(),
        "registry_id": registry.registry_id,
        "registry_sha256": registry.sha256,
        "registry_date_basis": registry.registry_date_basis,
        "upstream_calendar_receipt": str(
            logical_output / upstream_receipt_path.relative_to(output)
        ),
        "normalized_benchmark_history": str(
            logical_output / normalized_path.relative_to(output)
        ),
        "evidence_manifest": str(
            logical_output / evidence_manifest_path.relative_to(output)
        ),
        "benchmark_count": len(registry.benchmarks),
        "available_benchmark_count": len(available_codes),
        "row_count": len(normalized_rows),
        "query_and_pagination_status": "PASS",
        "evidence_classification": evidence_classification,
        "benchmark_entries": entry_reports,
        "comparisons": comparison_report,
        "errors": sorted(set([*validation.errors, *availability_errors])),
        "remaining_gates": [
            "ARTIFACT_BOUND_BENCHMARK_CAPTURE_AUTHORITY",
            "EFFECTIVE_DATED_HISTORICAL_SECTOR_BINDINGS",
            "OFFICIAL_COMPLETE_DAILY_EOD",
            "FINAL_DATA_FOUNDATION_RECONCILIATION",
        ],
        "claim_boundaries": {
            "benchmark_history_ready_for_declared_window": real_ready,
            "price_index_used_as_total_return_index": False,
            "broad_market_used_as_sector_benchmark": False,
            "fallback_benchmark_substitution_used": False,
            "forward_fill_used": False,
            "synthetic_benchmark_rows_created": any(
                item.availability_status == "AVAILABLE"
                and item.evidence_classification == "SYNTHETIC_ONLY"
                for item in accepted
            ),
            "internal_code_is_official_provider_code": False,
            "registry_effective_from_is_series_inception": False,
            "licensed_manifest_claim_is_external_authenticated_trust": False,
            "artifact_bound_capture_authority_verified": False,
            "recorded_fixture_is_real_evidence": False,
            "synthetic_fixture_is_real_evidence": False,
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }
    report_path = report_output / "benchmark_import_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "AVAILABILITY_STATUSES",
    "REPORT_EVIDENCE_CLASSIFICATIONS",
    "UNAVAILABLE_REASONS",
    "import_benchmark_history",
]
