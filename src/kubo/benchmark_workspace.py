from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .benchmark_registry import BenchmarkRegistry, load_benchmark_registry
from .evidence_hashes import parse_supporting_hashes
from .foundation_io import (
    load_strict_json_object,
    prepare_output_root,
    read_csv_bytes,
    require_real_directory,
    safe_regular_file,
)
from .hashing import canonical_json_bytes, sha256_bytes
from .official_foundation_import import TRADING_CALENDAR_HEADERS
from .strict import parse_iso_date, require_sha256, safe_relative_path


BENCHMARK_MANIFEST_SCHEMA_VERSION = "1.0"
MAX_UPSTREAM_BYTES = 20 * 1024 * 1024
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class OfficialCalendarReceipt:
    status: str
    run_id: str
    window_from: date
    window_to: date
    trading_dates: frozenset[date]
    trading_session_closes: dict[date, str]
    official_foundation_report_sha256: str
    trading_calendar_sha256: str
    evidence_manifest_sha256: str
    raw_evidence_hashes: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "calendar_window_from": self.window_from.isoformat(),
            "calendar_window_to": self.window_to.isoformat(),
            "trading_date_count": len(self.trading_dates),
            "official_foundation_report_sha256": self.official_foundation_report_sha256,
            "trading_calendar_sha256": self.trading_calendar_sha256,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
        }


def _manifest_hashes(root: Path) -> tuple[frozenset[str], bytes]:
    payload, content = load_strict_json_object(
        root / "manifest.json",
        field="upstream official evidence manifest",
        max_bytes=MAX_UPSTREAM_BYTES,
    )
    artifacts = payload.get("artifacts")
    if payload.get("schema_version") != "3.0" or not isinstance(artifacts, list):
        raise ValueError("upstream official evidence manifest is invalid")
    if not artifacts:
        raise ValueError("upstream official evidence manifest is empty")
    hashes: set[str] = set()
    paths: set[str] = set()
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            raise ValueError(f"upstream official artifact {index} is invalid")
        relative = safe_relative_path(row.get("path"), f"upstream artifacts[{index}].path")
        if not relative.parts or relative.parts[0] != "raw":
            raise ValueError(f"upstream official artifact {index} is outside raw/")
        relative_text = relative.as_posix()
        if relative_text in paths:
            raise ValueError("upstream official evidence manifest contains duplicate paths")
        paths.add(relative_text)
        artifact_bytes = safe_regular_file(
            root / relative,
            field=f"upstream official artifact {index}",
            max_bytes=MAX_UPSTREAM_BYTES,
        )
        declared = require_sha256(row.get("sha256"), f"upstream artifacts[{index}].sha256")
        if sha256_bytes(artifact_bytes) != declared:
            raise ValueError(f"upstream official artifact {index} hash mismatch")
        if declared in hashes:
            raise ValueError("upstream official evidence manifest contains duplicate hashes")
        hashes.add(declared)
    return frozenset(hashes), content


def load_official_calendar_receipt(
    official_foundation_root: Path,
) -> OfficialCalendarReceipt:
    root = require_real_directory(
        official_foundation_root,
        field="official_foundation_root",
    )
    report, report_bytes = load_strict_json_object(
        root / "reports" / "official_foundation_import_report.json",
        field="upstream official foundation report",
        max_bytes=MAX_UPSTREAM_BYTES,
    )
    if report.get("status") != "CURRENT_IDENTITY_AND_CALENDAR_READY":
        raise ValueError("upstream official foundation is not ready")
    if report.get("calendar_status") != "PASS":
        raise ValueError("upstream official trading calendar is not ready")
    run_id = str(report.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("upstream official foundation report lacks run_id")
    window_from = parse_iso_date(
        report.get("calendar_window_from"),
        "upstream calendar_window_from",
    )
    window_to = parse_iso_date(
        report.get("calendar_window_to"),
        "upstream calendar_window_to",
    )
    if window_from > window_to:
        raise ValueError("upstream official calendar window is reversed")

    raw_hashes, evidence_manifest_bytes = _manifest_hashes(root)
    calendar_bytes = safe_regular_file(
        root / "normalized" / "trading_calendar.csv",
        field="upstream trading_calendar.csv",
        max_bytes=MAX_UPSTREAM_BYTES,
    )
    _, rows = read_csv_bytes(
        calendar_bytes,
        field="upstream trading_calendar.csv",
        exact_headers=TRADING_CALENDAR_HEADERS,
    )
    expected_civil_dates: set[date] = set()
    current = window_from
    while current <= window_to:
        expected_civil_dates.add(current)
        current += timedelta(days=1)
    seen: set[date] = set()
    trading_dates: set[date] = set()
    trading_session_closes: dict[date, str] = {}
    for index, row in enumerate(rows):
        day = parse_iso_date(row["trade_date"], f"calendar row {index}.trade_date")
        if day in seen:
            raise ValueError("upstream trading calendar contains duplicate civil dates")
        seen.add(day)
        is_trading = row["is_trading_day"].casefold()
        if is_trading not in {"true", "false"}:
            raise ValueError("upstream trading calendar contains invalid is_trading_day")
        digest = require_sha256(row["raw_sha256"], f"calendar row {index}.raw_sha256")
        if digest not in raw_hashes:
            raise ValueError("upstream trading calendar raw_sha256 does not resolve")
        supporting = parse_supporting_hashes(
            row.get("supporting_raw_sha256s"),
            field=f"calendar row {index}.supporting_raw_sha256s",
            manifest_hashes=raw_hashes,
        )
        if digest in supporting:
            raise ValueError("upstream calendar duplicates primary evidence as supporting")
        if is_trading == "true":
            close_time = str(row.get("trade_at_last_end", ""))
            if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]", close_time):
                raise ValueError(
                    "upstream trading calendar contains invalid trade_at_last_end"
                )
            trading_dates.add(day)
            trading_session_closes[day] = close_time
    if seen != expected_civil_dates:
        missing = len(expected_civil_dates - seen)
        extra = len(seen - expected_civil_dates)
        raise ValueError(
            f"upstream trading calendar denominator mismatch: missing={missing}:extra={extra}"
        )
    if not trading_dates:
        raise ValueError("upstream trading calendar contains no trading dates")
    return OfficialCalendarReceipt(
        status="CURRENT_IDENTITY_AND_CALENDAR_READY",
        run_id=run_id,
        window_from=window_from,
        window_to=window_to,
        trading_dates=frozenset(trading_dates),
        trading_session_closes=trading_session_closes,
        official_foundation_report_sha256=sha256_bytes(report_bytes),
        trading_calendar_sha256=sha256_bytes(calendar_bytes),
        evidence_manifest_sha256=sha256_bytes(evidence_manifest_bytes),
        raw_evidence_hashes=raw_hashes,
    )


def _artifact_template(
    definition: Any,
    *,
    window_from: date,
    window_to: date,
    prepared_by: str,
) -> dict[str, Any]:
    return {
        "benchmark_code": definition.benchmark_code,
        "source_id": definition.source_id,
        "source_url": definition.source_url,
        "provider": definition.provider,
        "file_name": f"{definition.benchmark_code}.csv",
        "availability_status": "PENDING",
        "file_sha256": "",
        "observed_at": "",
        "captured_by": prepared_by,
        "capture_mode": "",
        "rights_status": "",
        "window_from": window_from.isoformat(),
        "window_to": window_to.isoformat(),
        "pages_declared": "",
        "pages_received": "",
        "result_count_declared": "",
        "row_count": "",
        "review_status": "PENDING",
        "review_notes": "",
        "unavailable_reason": "",
    }


def prepare_benchmark_workspace(
    *,
    config_dir: Path,
    official_foundation_root: Path,
    output_root: Path,
    run_id: str,
    window_from: str,
    window_to: str,
    prepared_by: str = "",
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be a canonical path-safe identifier")
    start = parse_iso_date(window_from, "window_from")
    end = parse_iso_date(window_to, "window_to")
    if start > end:
        raise ValueError("benchmark window is reversed")
    registry: BenchmarkRegistry = load_benchmark_registry(config_dir)
    receipt = load_official_calendar_receipt(official_foundation_root)
    if start < receipt.window_from or end > receipt.window_to:
        raise ValueError("benchmark window is outside the official calendar window")
    expected_trading_dates = {
        day for day in receipt.trading_dates if start <= day <= end
    }
    if not expected_trading_dates:
        raise ValueError("benchmark window contains no official trading dates")

    root = prepare_output_root(output_root, label="benchmark workspace")
    raw_dir = root / "raw_exports" / "benchmarks"
    manifest_dir = root / "manifests"
    report_dir = root / "reports"
    for directory in (
        raw_dir,
        manifest_dir,
        root / "normalized",
        report_dir,
        root / "quarantine",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    artifacts = [
        _artifact_template(
            definition,
            window_from=start,
            window_to=end,
            prepared_by=prepared_by,
        )
        for definition in registry.benchmarks
    ]
    for artifact in artifacts:
        placeholder = raw_dir / f"{artifact['file_name']}.placeholder"
        placeholder.write_text(
            "Replace with the exact authorized benchmark export bytes using the "
            "canonical columns trade_date,benchmark_value.\n"
            f"Internal KU-BO requirement code: {artifact['benchmark_code']}\n"
            "Do not invent or enter an official provider code. Preserve the original "
            "bytes, hash them, and complete pagination, rights, and review fields.\n"
            "For ZERO_RESULT keep a header-only accepted export. For UNAVAILABLE, "
            "change file_name to a path-safe receipt file and preserve the exact receipt.\n",
            encoding="utf-8",
        )

    upstream = receipt.to_dict()
    manifest = {
        "schema_version": BENCHMARK_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "registry_id": registry.registry_id,
        "registry_sha256": registry.sha256,
        "registry_date_basis": registry.registry_date_basis,
        "window_from": start.isoformat(),
        "window_to": end.isoformat(),
        "upstream": upstream,
        "artifacts": artifacts,
    }
    manifest_path = manifest_dir / "benchmark_history_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    (manifest_dir / "benchmark_registry.json").write_bytes(registry.source_bytes)

    checklist = report_dir / "benchmark_collection_checklist.md"
    checklist.write_text(
        "\n".join(
            [
                "# Benchmark History Collection Checklist",
                "",
                "- Internal `KU_BO_*` codes are requirement identifiers, not provider codes.",
                "- `effective_from` is a registry-observation date, not index launch "
                "or history inception.",
                "- Preserve exact authorized bytes; never edit or forward-fill an export.",
                "- Set price-index and total-return series separately.",
                "- Set broad-market and sector series separately; no substitution is permitted.",
                "- Reconcile pages, declared results, row count, and the official "
                "trading calendar.",
                "- Licensed exports remain `LICENSED_FEED_DEPENDENT` without "
                "external authenticated trust.",
                "- Evidence `rights_status` uses the shared values "
                "`RESEARCH_USE_AUTHORIZED`, `FIXTURE_ONLY`, `UNKNOWN`, or "
                "`RESTRICTED`; registry `rights_requirement` remains a separate "
                "source requirement.",
                "- Recorded fixtures prove code contracts only and never real-data readiness.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "workspace_kind": "BENCHMARK_HISTORY_COLLECTION",
        "run_id": run_id,
        "output_root": str(root),
        "registry_id": registry.registry_id,
        "registry_sha256": registry.sha256,
        "registry_date_basis": registry.registry_date_basis,
        "window_from": start.isoformat(),
        "window_to": end.isoformat(),
        "expected_trading_date_count": len(expected_trading_dates),
        "benchmark_count": len(registry.benchmarks),
        "manifest_path": str(manifest_path),
        "checklist_path": str(checklist),
        "upstream": upstream,
        "claim_boundaries": {
            "workspace_contains_benchmark_evidence": False,
            "internal_code_is_official_provider_code": False,
            "registry_effective_from_is_series_inception": False,
            "price_index_is_total_return_index": False,
            "broad_market_is_sector_benchmark": False,
            "licensed_export_is_authenticated_by_manifest_claim": False,
            "recorded_fixture_is_real_evidence": False,
            "backtest_ready": False,
        },
    }
    report_path = report_dir / "benchmark_workspace_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "BENCHMARK_MANIFEST_SCHEMA_VERSION",
    "OfficialCalendarReceipt",
    "load_official_calendar_receipt",
    "prepare_benchmark_workspace",
]
