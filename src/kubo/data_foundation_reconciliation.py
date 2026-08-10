from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Mapping, TextIO
from urllib.parse import urlsplit

from .foundation_io import (
    load_strict_json_object,
    prepare_output_root,
    read_csv_bytes,
    require_real_directory,
    safe_regular_file,
    strict_json_object,
)
from .hashing import canonical_json_bytes
from .strict import parse_aware, parse_iso_date


DATA_FOUNDATION_RECONCILIATION_SCHEMA_VERSION = "1.0"

GATE_ORDER = (
    "POINT_IN_TIME_IDENTITY",
    "TRADING_CALENDAR",
    "SECURITY_STATUS_HISTORY",
    "PRICE_DENOMINATOR",
    "PRICE_EVIDENCE",
    "PRICE_CORPORATE_ACTION_QA",
    "BENCHMARK_HISTORY",
    "BENCHMARK_EVIDENCE",
    "MARKET_TOTAL_RECONCILIATION",
    "QUERY_AND_PAGINATION_COMPLETENESS",
    "RUNTIME_SECRET_GUARD",
    "CLAIM_BOUNDARIES",
)

GATE_STATUSES = frozenset({"PASS", "PARTIAL", "BLOCKED"})
EVIDENCE_CLASSIFICATIONS = frozenset(
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
_COMPONENT_ORDER = (
    "OFFICIAL_FOUNDATION",
    "STATUS_HISTORY",
    "CA_ENRICHMENT",
    "RESEARCH_PRICE_HISTORY",
    "BENCHMARK",
    "OFFICIAL_EOD",
)
_RESEARCH_COMPATIBLE_RIGHTS = frozenset(
    {
        "RESEARCH_USE_AUTHORIZED",
        "AUTHORIZED_RESEARCH_USE",
        "PUBLIC_RESEARCH_USE",
        "LICENSED_RESEARCH_USE",
        "USER_EXPORT_RESEARCH_USE",
        "PUBLIC_RESEARCH_ALLOWED",
        "LICENSED_INTERNAL_RESEARCH_ALLOWED",
    }
)
_FIXTURE_RIGHTS = frozenset(
    {"FIXTURE_ONLY", "RECORDED_FIXTURE_ONLY", "SYNTHETIC_ONLY"}
)
_BLOCKED_REPORT_STATUSES = frozenset({"BLOCKED", "FAIL", "FAILED", "INVALID"})
_PARTIAL_REPORT_STATUSES = frozenset(
    {
        "PARTIAL",
        "LIVE_DEPENDENT",
        "LICENSED_FEED_DEPENDENT",
        "BLOCKED_OFFICIAL_IDENTITY",
    }
)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_COMPLEX_ACTIONS = frozenset(
    {"RIGHTS_ISSUE", "CAPITAL_REDUCTION", "MERGER", "PAR_VALUE_CHANGE", "OTHER"}
)
_NON_TRADED_STATES = frozenset(
    {"NO_TRADE", "SUSPENDED", "HALTED", "NOT_LISTED_OR_NOT_ELIGIBLE"}
)
_REAL_CAPTURE_KINDS = frozenset(
    {"RAW_PAGE", "RAW_DOWNLOAD", "USER_EXPORT", "ARCHIVE_CAPTURE"}
)
_PUBLIC_AUTHORITY_ROLES = frozenset({"OFFICIAL_TRUTH", "ISSUER_PRIMARY"})


@dataclass
class _ComponentAudit:
    component: str
    root: Path
    report_path: str
    manifest: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    rows: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    json_files: dict[str, dict[str, Any]] = field(default_factory=dict)
    file_hashes: dict[str, str] = field(default_factory=dict)
    artifact_hashes: frozenset[str] = frozenset()
    evidence_classification: str = "PARTIAL"
    rights_statuses: tuple[str, ...] = ()
    rights_compatible: bool = False
    structural_errors: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def hashes(self, *paths: str) -> list[dict[str, str]]:
        selected = set(paths)
        return [
            {
                "component": self.component,
                "path": path,
                "sha256": digest,
            }
            for path, digest in sorted(self.file_hashes.items())
            if not selected or path in selected
        ]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _error_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def _relative_artifact_path(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field_name} must be a canonical relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise ValueError(f"{field_name} must be a canonical relative POSIX path")
    return value


def _read_component_bytes(
    audit: _ComponentAudit,
    relative_path: str,
    *,
    required: bool = True,
) -> bytes | None:
    try:
        canonical = _relative_artifact_path(
            relative_path,
            field_name=f"{audit.component} file path",
        )
        content = safe_regular_file(
            audit.root / PurePosixPath(canonical),
            field=f"{audit.component}:{canonical}",
        )
    except (OSError, ValueError) as exc:
        if required:
            audit.structural_errors.append(
                f"{audit.component}_{_error_code(relative_path)}_INVALID:{exc}"
            )
        return None
    audit.file_hashes[canonical] = _sha256(content)
    return content


def _read_component_json(
    audit: _ComponentAudit,
    relative_path: str,
    *,
    required: bool = True,
) -> dict[str, Any] | None:
    content = _read_component_bytes(audit, relative_path, required=required)
    if content is None:
        return None
    try:
        payload = strict_json_object(content, f"{audit.component}:{relative_path}")
    except ValueError as exc:
        audit.structural_errors.append(
            f"{audit.component}_{_error_code(relative_path)}_INVALID:{exc}"
        )
        return None
    audit.json_files[relative_path] = payload
    return payload


def _read_component_csv(
    audit: _ComponentAudit,
    relative_path: str,
    *,
    required_headers: tuple[str, ...] = (),
    required: bool = True,
) -> list[dict[str, str]] | None:
    content = _read_component_bytes(audit, relative_path, required=required)
    if content is None:
        return None
    try:
        _, rows = read_csv_bytes(
            content,
            field=f"{audit.component}:{relative_path}",
            required_headers=required_headers,
        )
    except ValueError as exc:
        audit.structural_errors.append(
            f"{audit.component}_{_error_code(relative_path)}_INVALID:{exc}"
        )
        return None
    audit.rows[relative_path] = rows
    return rows


def _aggregate_classification(values: list[str]) -> str:
    if not values:
        return "PARTIAL"
    selected = set(values)
    for value in (
        "BLOCKED",
        "SYNTHETIC_ONLY",
        "RECORDED_AUTHORIZED_FIXTURE",
        "LICENSED_FEED_DEPENDENT",
        "LIVE_DEPENDENT",
        "PARTIAL",
    ):
        if value in selected:
            return value
    return "PROVEN_REAL_EVIDENCE"


def _audit_manifest(audit: _ComponentAudit) -> None:
    payload = _read_component_json(audit, "manifest.json")
    audit.manifest = payload
    if payload is None:
        audit.evidence_classification = "BLOCKED"
        return
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        audit.structural_errors.append(f"{audit.component}_MANIFEST_ARTIFACTS_NOT_LIST")
        audit.evidence_classification = "BLOCKED"
        return

    classifications: list[str] = []
    rights_statuses: list[str] = []
    verified_hashes: set[str] = set()
    seen_paths: set[str] = set()
    metadata_missing = False
    for index, row in enumerate(artifacts):
        label = f"{audit.component}_MANIFEST_ARTIFACT_{index}"
        if not isinstance(row, dict):
            audit.structural_errors.append(f"{label}_NOT_OBJECT")
            continue
        try:
            relative = _relative_artifact_path(
                row.get("path"),
                field_name=f"{label}.path",
            )
            if relative in seen_paths:
                raise ValueError("artifact path is duplicated")
            seen_paths.add(relative)
            declared_hash = row.get("sha256")
            if not isinstance(declared_hash, str) or not _HASH_RE.fullmatch(
                declared_hash
            ):
                raise ValueError("artifact sha256 is invalid")
            content = _read_component_bytes(audit, relative)
            if content is None:
                continue
            actual_hash = _sha256(content)
            if declared_hash != actual_hash:
                raise ValueError("artifact sha256 does not match preserved bytes")
            size_bytes = row.get("size_bytes")
            if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
                raise ValueError("artifact size_bytes must be an integer")
            if size_bytes != len(content):
                raise ValueError("artifact size_bytes does not match preserved bytes")
            verified_hashes.add(actual_hash)

            classification = row.get("evidence_classification")
            rights_status = row.get("rights_status")
            if classification is None or rights_status is None:
                metadata_missing = True
            else:
                if classification not in EVIDENCE_CLASSIFICATIONS:
                    raise ValueError("artifact evidence_classification is invalid")
                if not isinstance(rights_status, str) or not rights_status:
                    raise ValueError("artifact rights_status is invalid")
                classifications.append(classification)
                rights_statuses.append(rights_status)

                capture_kind = str(row.get("capture_kind", "")).upper()
                if "SYNTHETIC" in capture_kind and classification != "SYNTHETIC_ONLY":
                    raise ValueError("synthetic capture is misclassified")
                if (
                    "FIXTURE" in capture_kind
                    and classification != "RECORDED_AUTHORIZED_FIXTURE"
                ):
                    raise ValueError("fixture capture is misclassified")
        except (OSError, TypeError, ValueError) as exc:
            audit.structural_errors.append(f"{label}_INVALID:{exc}")

    audit.artifact_hashes = frozenset(verified_hashes)
    if metadata_missing or len(classifications) != len(artifacts):
        audit.limitations.extend(
            [
                f"{audit.component}_HASH_BOUND_EVIDENCE_CLASSIFICATION_MISSING",
                f"{audit.component}_HASH_BOUND_RIGHTS_STATUS_MISSING",
            ]
        )
        classifications.append("PARTIAL")
    if not artifacts:
        audit.limitations.append(f"{audit.component}_MANIFEST_HAS_NO_RAW_ARTIFACTS")
        classifications.append("PARTIAL")

    if audit.structural_errors:
        audit.evidence_classification = "BLOCKED"
    else:
        audit.evidence_classification = _aggregate_classification(classifications)
    audit.rights_statuses = tuple(sorted(set(rights_statuses)))
    audit.rights_compatible = bool(rights_statuses) and all(
        status in _RESEARCH_COMPATIBLE_RIGHTS or status in _FIXTURE_RIGHTS
        for status in rights_statuses
    )
    if not audit.rights_compatible:
        audit.limitations.append(f"{audit.component}_RIGHTS_NOT_RESEARCH_COMPATIBLE")


def _source_authority_registry(project_root: Path) -> dict[str, dict[str, Any]]:
    """Load the committed public-source registry, never packet-local authority claims."""

    content = safe_regular_file(
        project_root / "config" / "sources.json",
        field="PROJECT_SOURCE_AUTHORITY_REGISTRY",
    )
    payload = strict_json_object(content, "PROJECT_SOURCE_AUTHORITY_REGISTRY")
    rows = payload.get("sources")
    if not isinstance(rows, list) or not rows:
        raise ValueError("project source authority registry has no sources")
    registry: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(rows):
        if not isinstance(value, dict):
            raise ValueError(f"project source authority row {index} is not an object")
        source_id = value.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(f"project source authority row {index} has no source_id")
        if source_id in registry:
            raise ValueError(f"project source authority source_id is duplicated: {source_id}")
        urls = value.get("urls")
        if not isinstance(urls, list) or any(not isinstance(item, str) for item in urls):
            raise ValueError(f"project source authority {source_id} has invalid urls")
        hosts = frozenset(
            (urlsplit(item).hostname or "").lower()
            for item in urls
            if (urlsplit(item).hostname or "")
        )
        registry[source_id] = {
            "role": value.get("role"),
            "market_evidence_allowed": value.get("market_evidence_allowed"),
            "hosts": hosts,
        }
    return registry


def _host_matches_authority(host: str, authorities: frozenset[str]) -> bool:
    return any(host == authority or host.endswith("." + authority) for authority in authorities)


def _audit_real_evidence_authority(
    audits: tuple[_ComponentAudit, ...],
    *,
    project_root: Path,
) -> None:
    """Reject self-attested real evidence that has no project-side authority root.

    Hashes prove byte preservation, not provenance.  Public official evidence must
    therefore bind to a separately committed source definition and its declared
    domain.  Licensed evidence remains dependent unless a later final-stage API
    independently revalidates its external runtime trust root.
    """

    proven = [
        audit
        for audit in audits
        if audit.evidence_classification == "PROVEN_REAL_EVIDENCE"
    ]
    if not proven:
        return
    try:
        root = require_real_directory(project_root, field="PROJECT_ROOT")
        registry = _source_authority_registry(root)
    except (OSError, ValueError) as exc:
        for audit in proven:
            audit.structural_errors.append(
                f"{audit.component}_SOURCE_AUTHORITY_REGISTRY_INVALID:{exc}"
            )
            audit.evidence_classification = "BLOCKED"
        return

    for audit in proven:
        artifacts = audit.manifest.get("artifacts", []) if audit.manifest else []
        licensed_dependency = False
        for index, row in enumerate(artifacts):
            if not isinstance(row, dict) or row.get("evidence_classification") != "PROVEN_REAL_EVIDENCE":
                continue
            label = f"{audit.component}_MANIFEST_ARTIFACT_{index}"
            source_id = row.get("source_id")
            authority = registry.get(source_id) if isinstance(source_id, str) else None
            if authority is None:
                audit.structural_errors.append(f"{label}_UNREGISTERED_REAL_SOURCE")
                continue
            if authority["role"] == "AUTHORIZED_TAPE":
                licensed_dependency = True
                continue
            if (
                authority["role"] not in _PUBLIC_AUTHORITY_ROLES
                or authority["market_evidence_allowed"] is not True
            ):
                audit.structural_errors.append(f"{label}_SOURCE_NOT_REAL_EVIDENCE_AUTHORITY")
                continue
            try:
                source_url = row.get("source_url")
                if not isinstance(source_url, str) or not source_url.startswith("https://"):
                    raise ValueError("real source_url must be HTTPS")
                host = (urlsplit(source_url).hostname or "").lower()
                if not host or not _host_matches_authority(host, authority["hosts"]):
                    raise ValueError("real source_url is outside its registered authority domains")
                if str(row.get("capture_kind", "")).upper() not in _REAL_CAPTURE_KINDS:
                    raise ValueError("real evidence has no accepted capture kind")
                if not isinstance(row.get("artifact_role"), str) or not row["artifact_role"]:
                    raise ValueError("real evidence has no artifact_role")
                parse_aware(row.get("observed_at"), f"{label}.observed_at")
                if row.get("rights_status") not in _RESEARCH_COMPATIBLE_RIGHTS:
                    raise ValueError("real evidence lacks research-compatible rights")
            except (TypeError, ValueError) as exc:
                audit.structural_errors.append(f"{label}_REAL_PROVENANCE_INVALID:{exc}")
        if licensed_dependency and not audit.structural_errors:
            audit.evidence_classification = "LICENSED_FEED_DEPENDENT"
            audit.limitations.append(
                f"{audit.component}_EXTERNAL_RUNTIME_TRUST_NOT_REVALIDATED"
            )
        else:
            # The current component manifests carry packet-local provenance labels,
            # not an external receipt that cryptographically binds the exact raw
            # artifact SHA-256, capture event, query/window, and validator result.
            # Source allowlists prove neither origin nor content.  Keep final READY
            # unreachable until that artifact-bound authority contract exists.
            audit.structural_errors.append(
                f"{audit.component}_ARTIFACT_BOUND_CAPTURE_AUTHORITY_REQUIRED"
            )
            audit.evidence_classification = "BLOCKED"


def _verify_hash_references(
    audit: _ComponentAudit,
    relative_path: str,
    *,
    fields: tuple[str, ...],
) -> None:
    rows = audit.rows.get(relative_path)
    if rows is None:
        return
    for index, row in enumerate(rows):
        for field_name in fields:
            value = row.get(field_name, "")
            if not value:
                continue
            separator = "|" if "hashes" in field_name or "sha256s" in field_name else None
            values = value.split(separator) if separator else [value]
            for digest in values:
                if not _HASH_RE.fullmatch(digest):
                    audit.structural_errors.append(
                        f"{audit.component}_{_error_code(relative_path)}_ROW_{index}_"
                        f"{_error_code(field_name)}_INVALID"
                    )
                elif digest not in audit.artifact_hashes:
                    audit.structural_errors.append(
                        f"{audit.component}_{_error_code(relative_path)}_ROW_{index}_"
                        f"{_error_code(field_name)}_UNRESOLVED"
                    )


def _audit_official_foundation(root: Path) -> _ComponentAudit:
    audit = _ComponentAudit(
        "OFFICIAL_FOUNDATION",
        root,
        "reports/official_foundation_import_report.json",
    )
    try:
        audit.root = require_real_directory(root, field="OFFICIAL_FOUNDATION_ROOT")
    except ValueError as exc:
        audit.structural_errors.append(f"OFFICIAL_FOUNDATION_ROOT_INVALID:{exc}")
        audit.evidence_classification = "BLOCKED"
        return audit
    _audit_manifest(audit)
    audit.report = _read_component_json(audit, audit.report_path)
    _read_component_json(audit, "official_foundation_manifest.json")
    _read_component_json(audit, "reports/official_identity_report.json")
    _read_component_json(audit, "reports/trading_calendar_report.json")
    _read_component_csv(
        audit,
        "normalized/security_master.csv",
        required_headers=(
            "security_code",
            "ticker",
            "valid_from",
            "raw_sha256",
        ),
    )
    _read_component_csv(
        audit,
        "normalized/trading_calendar.csv",
        required_headers=("trade_date", "is_trading_day", "raw_sha256"),
    )
    _verify_hash_references(
        audit,
        "normalized/security_master.csv",
        fields=("raw_sha256", "supporting_raw_sha256s"),
    )
    _verify_hash_references(
        audit,
        "normalized/trading_calendar.csv",
        fields=("raw_sha256", "supporting_raw_sha256s"),
    )
    if audit.structural_errors:
        audit.evidence_classification = "BLOCKED"
    return audit


def _audit_status_history(root: Path) -> _ComponentAudit:
    audit = _ComponentAudit(
        "STATUS_HISTORY",
        root,
        "reports/status_history_import_report.json",
    )
    try:
        audit.root = require_real_directory(root, field="STATUS_HISTORY_ROOT")
    except ValueError as exc:
        audit.structural_errors.append(f"STATUS_HISTORY_ROOT_INVALID:{exc}")
        audit.evidence_classification = "BLOCKED"
        return audit
    _audit_manifest(audit)
    audit.report = _read_component_json(audit, audit.report_path)
    _read_component_json(audit, "reports/status_history_validation_report.json")
    _read_component_json(audit, "status_history_manifest.json")
    _read_component_csv(
        audit,
        "normalized/status_intervals.csv",
        required_headers=(
            "security_code",
            "status",
            "effective_from",
            "opening_evidence_sha256",
            "evidence_hashes",
        ),
    )
    _read_component_csv(
        audit,
        "normalized/opening_status_evidence.csv",
        required_headers=("security_code", "status", "effective_date", "raw_sha256"),
    )
    _read_component_csv(
        audit,
        "manifests/status_query_ledger.csv",
        required_headers=(
            "query_id",
            "security_code",
            "pages_declared",
            "pages_received",
            "result_count_declared",
            "rows_normalized",
            "zero_result",
            "raw_sha256",
        ),
    )
    _verify_hash_references(
        audit,
        "normalized/status_intervals.csv",
        fields=("opening_evidence_sha256", "evidence_hashes"),
    )
    _verify_hash_references(
        audit,
        "normalized/opening_status_evidence.csv",
        fields=("raw_sha256",),
    )
    _verify_hash_references(
        audit,
        "manifests/status_query_ledger.csv",
        fields=("raw_sha256",),
    )
    if audit.structural_errors:
        audit.evidence_classification = "BLOCKED"
    return audit


def _audit_ca_enrichment(root: Path) -> _ComponentAudit:
    audit = _ComponentAudit(
        "CA_ENRICHMENT",
        root,
        "reports/ca_enrichment_import_report.json",
    )
    try:
        audit.root = require_real_directory(root, field="CA_ENRICHMENT_ROOT")
    except ValueError as exc:
        audit.structural_errors.append(f"CA_ENRICHMENT_ROOT_INVALID:{exc}")
        audit.evidence_classification = "BLOCKED"
        return audit
    _audit_manifest(audit)
    audit.report = _read_component_json(audit, audit.report_path)
    _read_component_json(audit, "ca_enrichment_manifest.json")
    _read_component_csv(
        audit,
        "normalized/corporate_action_factor_ledger.csv",
        required_headers=(
            "action_id",
            "security_code",
            "action_type",
            "reference_price_factor",
            "historical_continuity_factor",
            "position_quantity_multiplier",
            "return_price_multiplier",
            "cash_distribution_per_pre_action_share_fils",
            "rights_cash_contribution_per_pre_action_share_fils",
            "return_engine_treatment",
            "return_engine_ready",
        ),
    )
    _read_component_csv(
        audit,
        "normalized/corporate_action_return_policy_queue.csv",
        required_headers=(
            "action_id",
            "action_type",
            "required_policy",
            "factor_status",
            "review_status",
        ),
    )
    _verify_hash_references(
        audit,
        "normalized/corporate_action_factor_ledger.csv",
        fields=(
            "disclosure_raw_sha256",
            "disclosure_text_sha256",
            "price_reference_raw_sha256",
        ),
    )
    if audit.structural_errors:
        audit.evidence_classification = "BLOCKED"
    return audit


def _audit_research_prices(root: Path) -> _ComponentAudit:
    audit = _ComponentAudit(
        "RESEARCH_PRICE_HISTORY",
        root,
        "reports/user_export_import_report.json",
    )
    try:
        audit.root = require_real_directory(root, field="RESEARCH_PRICE_HISTORY_ROOT")
    except ValueError as exc:
        audit.structural_errors.append(f"RESEARCH_PRICE_HISTORY_ROOT_INVALID:{exc}")
        audit.evidence_classification = "BLOCKED"
        return audit
    _audit_manifest(audit)
    audit.report = _read_component_json(audit, audit.report_path)
    _read_component_json(audit, "reports/data_quality_report.json")
    _read_component_csv(audit, "price_collection_manifest.csv")
    rows = _read_component_csv(
        audit,
        "normalized/research_price_history.csv",
        required_headers=(
            "trade_date",
            "security_code",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "raw_sha256",
            "capture_mode",
            "price_basis",
            "currency",
            "unit",
            "corporate_action_status",
        ),
    )
    _verify_hash_references(
        audit,
        "normalized/research_price_history.csv",
        fields=("raw_sha256",),
    )
    if rows is not None:
        capture_modes = {row.get("capture_mode", "").upper() for row in rows}
        if "RECORDED_AUTHORIZED_FIXTURE" in capture_modes:
            if audit.evidence_classification == "PROVEN_REAL_EVIDENCE":
                audit.structural_errors.append(
                    "RESEARCH_PRICE_HISTORY_FIXTURE_CANNOT_BE_CLASSIFIED_AS_REAL"
                )
            else:
                audit.evidence_classification = "RECORDED_AUTHORIZED_FIXTURE"
    if audit.structural_errors:
        audit.evidence_classification = "BLOCKED"
    return audit


def _audit_benchmark(root: Path) -> _ComponentAudit:
    audit = _ComponentAudit(
        "BENCHMARK",
        root,
        "reports/benchmark_import_report.json",
    )
    try:
        audit.root = require_real_directory(root, field="BENCHMARK_ROOT")
    except ValueError as exc:
        audit.structural_errors.append(f"BENCHMARK_ROOT_INVALID:{exc}")
        audit.evidence_classification = "BLOCKED"
        return audit
    _audit_manifest(audit)
    audit.report = _read_component_json(audit, audit.report_path)
    _read_component_json(audit, "benchmark_registry.json")
    _read_component_json(audit, "benchmark_history_manifest.json")
    _read_component_json(audit, "upstream_calendar_receipt.json")
    _read_component_csv(
        audit,
        "normalized/benchmark_history.csv",
        required_headers=("trade_date", "benchmark_code", "raw_sha256"),
    )
    _verify_hash_references(
        audit,
        "normalized/benchmark_history.csv",
        fields=("raw_sha256",),
    )
    if audit.structural_errors:
        audit.evidence_classification = "BLOCKED"
    return audit


def _audit_official_eod(root: Path) -> _ComponentAudit:
    audit = _ComponentAudit(
        "OFFICIAL_EOD",
        root,
        "reports/official_eod_import_report.json",
    )
    try:
        audit.root = require_real_directory(root, field="OFFICIAL_EOD_ROOT")
    except ValueError as exc:
        audit.structural_errors.append(f"OFFICIAL_EOD_ROOT_INVALID:{exc}")
        audit.evidence_classification = "BLOCKED"
        return audit
    _audit_manifest(audit)
    audit.report = _read_component_json(audit, audit.report_path)
    _read_component_json(audit, "official_eod_manifest.json")
    _read_component_csv(
        audit,
        "normalized/official_daily_eod.csv",
        required_headers=("trade_date", "security_code", "raw_sha256"),
    )
    _read_component_csv(
        audit,
        "normalized/daily_market_totals.csv",
        required_headers=("trade_date", "raw_sha256"),
        required=False,
    )
    _verify_hash_references(
        audit,
        "normalized/official_daily_eod.csv",
        fields=("raw_sha256", "supporting_raw_sha256s"),
    )
    _verify_hash_references(
        audit,
        "normalized/daily_market_totals.csv",
        fields=("raw_sha256", "supporting_raw_sha256s"),
    )
    if audit.structural_errors:
        audit.evidence_classification = "BLOCKED"
    return audit


def _receipt_mismatch(
    audit: _ComponentAudit,
    *,
    label: str,
    receipt: Mapping[str, Any] | None,
    expected: Mapping[str, str],
) -> None:
    if not isinstance(receipt, Mapping):
        audit.structural_errors.append(f"{label}_MISSING_OR_INVALID")
        audit.evidence_classification = "BLOCKED"
        return
    mismatches = sorted(
        key for key, value in expected.items() if receipt.get(key) != value
    )
    if mismatches:
        audit.structural_errors.append(
            f"{label}_STALE_OR_SUBSTITUTED:" + ",".join(mismatches)
        )
        audit.evidence_classification = "BLOCKED"


def _verify_cross_component_receipts(
    official: _ComponentAudit,
    status_history: _ComponentAudit,
    benchmark: _ComponentAudit,
    eod: _ComponentAudit,
) -> None:
    benchmark_receipt = benchmark.json_files.get("upstream_calendar_receipt.json")
    _receipt_mismatch(
        benchmark,
        label="BENCHMARK_OFFICIAL_CALENDAR_RECEIPT",
        receipt=benchmark_receipt,
        expected={
            "official_foundation_report_sha256": official.file_hashes.get(
                "reports/official_foundation_import_report.json", ""
            ),
            "trading_calendar_sha256": official.file_hashes.get(
                "normalized/trading_calendar.csv", ""
            ),
            "evidence_manifest_sha256": official.file_hashes.get("manifest.json", ""),
        },
    )
    benchmark_report = benchmark.report or {}
    if benchmark_report.get("registry_sha256") != benchmark.file_hashes.get(
        "benchmark_registry.json"
    ):
        benchmark.structural_errors.append("BENCHMARK_REGISTRY_RECEIPT_STALE")
        benchmark.evidence_classification = "BLOCKED"
    benchmark_rows = benchmark.rows.get("normalized/benchmark_history.csv", [])
    if benchmark_report.get("row_count") != len(benchmark_rows):
        benchmark.structural_errors.append("BENCHMARK_NORMALIZED_ROW_COUNT_STALE")
        benchmark.evidence_classification = "BLOCKED"

    eod_report = eod.report or {}
    upstream = eod_report.get("upstream")
    official_receipt = (
        upstream.get("official_foundation") if isinstance(upstream, dict) else None
    )
    status_receipt = upstream.get("status_history") if isinstance(upstream, dict) else None
    _receipt_mismatch(
        eod,
        label="OFFICIAL_EOD_FOUNDATION_RECEIPT",
        receipt=official_receipt,
        expected={
            "report_sha256": official.file_hashes.get(
                "reports/official_foundation_import_report.json", ""
            ),
            "manifest_sha256": official.file_hashes.get("manifest.json", ""),
            "security_master_sha256": official.file_hashes.get(
                "normalized/security_master.csv", ""
            ),
            "trading_calendar_sha256": official.file_hashes.get(
                "normalized/trading_calendar.csv", ""
            ),
        },
    )
    _receipt_mismatch(
        eod,
        label="OFFICIAL_EOD_STATUS_HISTORY_RECEIPT",
        receipt=status_receipt,
        expected={
            "report_sha256": status_history.file_hashes.get(
                "reports/status_history_import_report.json", ""
            ),
            "manifest_sha256": status_history.file_hashes.get("manifest.json", ""),
            "status_intervals_sha256": status_history.file_hashes.get(
                "normalized/status_intervals.csv", ""
            ),
            "status_query_ledger_sha256": status_history.file_hashes.get(
                "manifests/status_query_ledger.csv", ""
            ),
        },
    )
    preserved_manifest = eod.json_files.get("official_eod_manifest.json")
    if not isinstance(preserved_manifest, dict) or preserved_manifest.get("upstream") != upstream:
        eod.structural_errors.append("OFFICIAL_EOD_PRESERVED_MANIFEST_UPSTREAM_STALE")
        eod.evidence_classification = "BLOCKED"
    if eod_report.get("official_eod_manifest_sha256") != eod.file_hashes.get(
        "official_eod_manifest.json"
    ):
        eod.structural_errors.append("OFFICIAL_EOD_MANIFEST_RECEIPT_STALE")
        eod.evidence_classification = "BLOCKED"
    normalized_receipt = eod_report.get("official_daily_eod")
    if (
        not isinstance(normalized_receipt, dict)
        or normalized_receipt.get("sha256")
        != eod.file_hashes.get("normalized/official_daily_eod.csv")
        or normalized_receipt.get("rows")
        != len(eod.rows.get("normalized/official_daily_eod.csv", []))
    ):
        eod.structural_errors.append("OFFICIAL_EOD_NORMALIZED_RECEIPT_STALE")
        eod.evidence_classification = "BLOCKED"
    totals_receipt = eod_report.get("daily_market_totals")
    totals_hash = eod.file_hashes.get("normalized/daily_market_totals.csv")
    if totals_hash is not None and (
        not isinstance(totals_receipt, dict)
        or totals_receipt.get("sha256") != totals_hash
        or totals_receipt.get("rows")
        != len(eod.rows.get("normalized/daily_market_totals.csv", []))
    ):
        eod.structural_errors.append("OFFICIAL_EOD_MARKET_TOTALS_RECEIPT_STALE")
        eod.evidence_classification = "BLOCKED"

    benchmark_window = (
        benchmark_report.get("window_from"),
        benchmark_report.get("window_to"),
    )
    eod_window = (eod_report.get("window_from"), eod_report.get("window_to"))
    if None in benchmark_window or None in eod_window or benchmark_window != eod_window:
        benchmark.structural_errors.append("BENCHMARK_AND_OFFICIAL_EOD_WINDOW_MISMATCH")
        benchmark.evidence_classification = "BLOCKED"


def _report_semantic_status(
    audit: _ComponentAudit,
    *,
    ready_statuses: frozenset[str] = frozenset(),
) -> tuple[str, list[str]]:
    if audit.structural_errors or audit.report is None:
        return "BLOCKED", list(audit.structural_errors)
    errors: list[str] = []
    report_errors = audit.report.get("errors", [])
    if report_errors not in (None, []):
        if isinstance(report_errors, list):
            errors.extend(
                f"{audit.component}_UPSTREAM_REPORTED_ERROR_{index}_"
                f"{_sha256(str(value).encode('utf-8'))[:16]}"
                for index, value in enumerate(report_errors)
            )
        else:
            errors.append(f"{audit.component}_UPSTREAM_ERRORS_INVALID")
    status = str(audit.report.get("status", "")).upper()
    if status in _BLOCKED_REPORT_STATUSES or not status:
        errors.append(f"{audit.component}_UPSTREAM_STATUS_{status or 'MISSING'}")
        return "BLOCKED", errors
    if status in _PARTIAL_REPORT_STATUSES:
        errors.append(f"{audit.component}_UPSTREAM_STATUS_{status}")
        return "PARTIAL", errors
    if ready_statuses and status not in ready_statuses:
        errors.append(f"{audit.component}_UPSTREAM_STATUS_UNRECOGNIZED:{status}")
        return "PARTIAL", errors
    if errors:
        return "BLOCKED", errors
    return "PASS", []


def _gate_status(
    audits: tuple[_ComponentAudit, ...],
    *,
    semantic_status: str,
    semantic_errors: list[str],
) -> tuple[str, str, list[str], bool]:
    if semantic_status not in GATE_STATUSES:
        raise ValueError("semantic_status is invalid")
    errors = [
        *semantic_errors,
        *(error for audit in audits for error in audit.structural_errors),
    ]
    limitations = [value for audit in audits for value in audit.limitations]
    classification = _aggregate_classification(
        [audit.evidence_classification for audit in audits]
    )
    rights_compatible = bool(audits) and all(
        audit.rights_compatible for audit in audits
    )
    if errors or semantic_status == "BLOCKED" or classification == "BLOCKED":
        return "BLOCKED", "BLOCKED", sorted(set(errors + limitations)), False
    if (
        semantic_status == "PARTIAL"
        or classification != "PROVEN_REAL_EVIDENCE"
        or not rights_compatible
        or limitations
    ):
        return (
            "PARTIAL",
            classification,
            sorted(set(semantic_errors + limitations)),
            rights_compatible,
        )
    return "PASS", classification, [], True


def _hashes_for(audits: tuple[_ComponentAudit, ...]) -> list[dict[str, str]]:
    return sorted(
        [item for audit in audits for item in audit.hashes()],
        key=lambda item: (item["component"], item["path"], item["sha256"]),
    )


def _gate(
    name: str,
    audits: tuple[_ComponentAudit, ...],
    *,
    semantic_status: str,
    semantic_errors: list[str],
    checks: Mapping[str, str],
    metrics: Mapping[str, str | int | bool | None],
    concepts: tuple[str, ...] = (),
    extra_hashes: tuple[dict[str, str], ...] = (),
) -> dict[str, Any]:
    status, classification, errors, rights = _gate_status(
        audits,
        semantic_status=semantic_status,
        semantic_errors=semantic_errors,
    )
    return {
        "gate": name,
        "critical": True,
        "status": status,
        "evidence_classification": classification,
        "rights_compatible": rights,
        "errors": errors,
        "hashes": sorted(
            [*_hashes_for(audits), *extra_hashes],
            key=lambda item: (item["component"], item["path"], item["sha256"]),
        ),
        "details": {
            "components": [audit.component for audit in audits],
            "checks": dict(sorted(checks.items())),
            "metrics": dict(sorted(metrics.items())),
            "concepts": list(concepts),
        },
    }


def _identity_gate(official: _ComponentAudit) -> dict[str, Any]:
    semantic, errors = _report_semantic_status(
        official,
        ready_statuses=frozenset({"CURRENT_IDENTITY_AND_CALENDAR_READY"}),
    )
    report = official.report or {}
    rows = official.rows.get("normalized/security_master.csv", [])
    if report.get("identity_status") != "PASS":
        semantic = "BLOCKED"
        errors.append("OFFICIAL_IDENTITY_REPORT_NOT_PASS")
    identity_scopes = {row.get("identity_scope", "") for row in rows}
    point_in_time = bool(rows) and identity_scopes <= {
        "POINT_IN_TIME_OFFICIAL",
        "EFFECTIVE_DATED_OFFICIAL",
    }
    if not rows:
        semantic = "BLOCKED"
        errors.append("OFFICIAL_IDENTITY_EMPTY")
    elif not point_in_time and semantic != "BLOCKED":
        semantic = "PARTIAL"
        errors.append("HISTORICAL_POINT_IN_TIME_IDENTITY_NOT_PROVEN")
    return _gate(
        "POINT_IN_TIME_IDENTITY",
        (official,),
        semantic_status=semantic,
        semantic_errors=errors,
        checks={
            "effective_dated_identity": "PASS" if point_in_time else "PARTIAL",
            "upstream_identity_validation": (
                "PASS" if report.get("identity_status") == "PASS" else "BLOCKED"
            ),
        },
        metrics={"security_rows": len(rows)},
    )


def _calendar_gate(official: _ComponentAudit) -> dict[str, Any]:
    semantic, errors = _report_semantic_status(
        official,
        ready_statuses=frozenset({"CURRENT_IDENTITY_AND_CALENDAR_READY"}),
    )
    report = official.report or {}
    rows = official.rows.get("normalized/trading_calendar.csv", [])
    if report.get("calendar_status") != "PASS":
        semantic = "BLOCKED"
        errors.append("OFFICIAL_TRADING_CALENDAR_REPORT_NOT_PASS")
    if not rows:
        semantic = "BLOCKED"
        errors.append("OFFICIAL_TRADING_CALENDAR_EMPTY")
    dates = [row.get("trade_date", "") for row in rows]
    if len(dates) != len(set(dates)):
        semantic = "BLOCKED"
        errors.append("OFFICIAL_TRADING_CALENDAR_DUPLICATE_DATE")
    return _gate(
        "TRADING_CALENDAR",
        (official,),
        semantic_status=semantic,
        semantic_errors=errors,
        checks={
            "date_keys_unique": "PASS" if len(dates) == len(set(dates)) else "BLOCKED",
            "upstream_calendar_validation": (
                "PASS" if report.get("calendar_status") == "PASS" else "BLOCKED"
            ),
        },
        metrics={
            "calendar_rows": len(rows),
            "official_session_rows": sum(
                row.get("is_trading_day", "").lower() == "true" for row in rows
            ),
        },
    )


def _query_ledger_status(status_history: _ComponentAudit) -> tuple[str, list[str]]:
    rows = status_history.rows.get("manifests/status_query_ledger.csv", [])
    errors: list[str] = []
    if not rows:
        return "BLOCKED", ["STATUS_QUERY_LEDGER_EMPTY"]
    for index, row in enumerate(rows):
        try:
            pages_declared = int(row.get("pages_declared", ""))
            pages_received = int(row.get("pages_received", ""))
            result_count = int(row.get("result_count_declared", ""))
            normalized = int(row.get("rows_normalized", ""))
            zero_result = row.get("zero_result", "").lower()
            if min(pages_declared, pages_received, result_count, normalized) < 0:
                raise ValueError("negative count")
            if pages_declared != pages_received:
                raise ValueError("pagination mismatch")
            if result_count != normalized:
                raise ValueError("result count mismatch")
            if zero_result not in {"true", "false"}:
                raise ValueError("zero_result invalid")
            if (zero_result == "true") != (result_count == 0):
                raise ValueError("zero_result mismatch")
        except (TypeError, ValueError) as exc:
            errors.append(f"STATUS_QUERY_LEDGER_ROW_{index}:{exc}")
    return ("PASS", []) if not errors else ("BLOCKED", errors)


def _status_history_gate(status_history: _ComponentAudit) -> dict[str, Any]:
    semantic, errors = _report_semantic_status(
        status_history,
        ready_statuses=frozenset({"HISTORICAL_STATUS_INTERVALS_READY"}),
    )
    report = status_history.report or {}
    intervals = status_history.rows.get("normalized/status_intervals.csv", [])
    openings = status_history.rows.get("normalized/opening_status_evidence.csv", [])
    if not report.get("claim_boundaries", {}).get(
        "status_history_ready_for_declared_window", False
    ):
        semantic = "BLOCKED"
        errors.append("STATUS_HISTORY_DECLARED_WINDOW_NOT_READY")
    if not intervals or not openings:
        semantic = "BLOCKED"
        errors.append("STATUS_HISTORY_INTERVAL_OR_OPENING_EVIDENCE_EMPTY")
    query_status, query_errors = _query_ledger_status(status_history)
    if query_status == "BLOCKED":
        semantic = "BLOCKED"
        errors.extend(query_errors)
    return _gate(
        "SECURITY_STATUS_HISTORY",
        (status_history,),
        semantic_status=semantic,
        semantic_errors=errors,
        checks={
            "opening_evidence": "PASS" if openings else "BLOCKED",
            "query_reconciliation": query_status,
            "status_intervals": "PASS" if intervals else "BLOCKED",
        },
        metrics={
            "interval_rows": len(intervals),
            "opening_rows": len(openings),
            "query_rows": len(
                status_history.rows.get("manifests/status_query_ledger.csv", [])
            ),
        },
        concepts=(
            "CURRENT_SNAPSHOT_MAY_NOT_BACKFILL_HISTORY",
            "SUSPENDED_AND_HALTED_ARE_EXPLICIT_INTERVAL_STATES",
        ),
    )


def _eod_semantics(eod: _ComponentAudit) -> tuple[str, list[str], dict[str, Any]]:
    semantic, errors = _report_semantic_status(
        eod,
        ready_statuses=frozenset(
            {
                "READY",
                "OFFICIAL_EOD_READY",
                "OFFICIAL_COMPLETE_EOD_READY",
                "OFFICIAL_COMPLETE_DAILY_EOD_READY",
            }
        ),
    )
    report = eod.report or {}
    rows = eod.rows.get("normalized/official_daily_eod.csv", [])
    keys = [
        (row.get("trade_date", ""), row.get("security_code", "")) for row in rows
    ]
    duplicate_count = len(keys) - len(set(keys))
    if duplicate_count:
        semantic = "BLOCKED"
        errors.append("OFFICIAL_EOD_DUPLICATE_SECURITY_SESSION_KEY")
    denominator_status = str(report.get("denominator_status", "")).upper()
    if denominator_status != "PASS":
        semantic = "BLOCKED" if denominator_status == "BLOCKED" else "PARTIAL"
        errors.append("OFFICIAL_EOD_DENOMINATOR_NOT_PASS")
    missing_count = report.get("missing_pair_count", report.get("missing_row_count", 0))
    quarantine_count = report.get("quarantine_count", 0)
    if isinstance(missing_count, bool) or not isinstance(missing_count, int):
        semantic = "BLOCKED"
        errors.append("OFFICIAL_EOD_MISSING_PAIR_COUNT_INVALID")
        missing_count = -1
    elif missing_count != 0:
        semantic = "BLOCKED"
        errors.append("OFFICIAL_EOD_DENOMINATOR_HAS_MISSING_PAIRS")
    if isinstance(quarantine_count, bool) or not isinstance(quarantine_count, int):
        semantic = "BLOCKED"
        errors.append("OFFICIAL_EOD_QUARANTINE_COUNT_INVALID")
        quarantine_count = -1
    elif quarantine_count != 0:
        semantic = "BLOCKED"
        errors.append("OFFICIAL_EOD_HAS_QUARANTINED_CONFLICTS")
    if not rows:
        semantic = "BLOCKED"
        errors.append("OFFICIAL_EOD_EMPTY")
    expected = report.get("expected_pair_count")
    normalized = report.get("normalized_row_count", len(rows))
    if isinstance(expected, int) and not isinstance(expected, bool) and expected != len(rows):
        semantic = "BLOCKED"
        errors.append("OFFICIAL_EOD_EXPECTED_PAIR_COUNT_MISMATCH")
    if isinstance(normalized, int) and not isinstance(normalized, bool) and normalized != len(rows):
        semantic = "BLOCKED"
        errors.append("OFFICIAL_EOD_NORMALIZED_ROW_COUNT_MISMATCH")
    return semantic, errors, {
        "rows": len(rows),
        "duplicate_count": duplicate_count,
        "missing_pair_count": missing_count,
        "quarantine_count": quarantine_count,
    }


def _price_denominator_gate(eod: _ComponentAudit) -> dict[str, Any]:
    semantic, errors, metrics = _eod_semantics(eod)
    return _gate(
        "PRICE_DENOMINATOR",
        (eod,),
        semantic_status=semantic,
        semantic_errors=errors,
        checks={
            "exactly_one_security_session_row": (
                "PASS" if metrics["duplicate_count"] == 0 else "BLOCKED"
            ),
            "expected_denominator_reconciled": (
                "PASS"
                if metrics["missing_pair_count"] == 0 and metrics["rows"] > 0
                else "BLOCKED"
            ),
            "provider_conflicts_quarantined": (
                "PASS" if metrics["quarantine_count"] == 0 else "BLOCKED"
            ),
        },
        metrics=metrics,
        concepts=(
            "ONE_EXPLICIT_STATE_PER_ELIGIBLE_SECURITY_SESSION",
            "NO_TRADE_SUSPENDED_HALTED_ARE_NOT_MISSING_ROWS",
        ),
    )


def _research_price_semantics(
    research: _ComponentAudit,
) -> tuple[str, list[str], dict[str, Any]]:
    semantic, errors = _report_semantic_status(
        research,
        ready_statuses=frozenset(
            {"RESEARCH_PRICE_HISTORY_READY", "BLOCKED_OFFICIAL_IDENTITY"}
        ),
    )
    report = research.report or {}
    price_status = str(report.get("price_history_status", "")).upper()
    if price_status != "RESEARCH_PRICE_HISTORY_READY":
        if price_status == "BLOCKED":
            semantic = "BLOCKED"
        elif semantic != "BLOCKED":
            semantic = "PARTIAL"
        errors.append("RESEARCH_PRICE_HISTORY_NOT_READY")
    rows = research.rows.get("normalized/research_price_history.csv", [])
    if not rows:
        semantic = "BLOCKED"
        errors.append("RESEARCH_PRICE_HISTORY_EMPTY")
    return semantic, errors, {
        "rows": len(rows),
        "adjusted_rows": sum(row.get("price_basis", "").upper() == "ADJUSTED" for row in rows),
        "fixture_rows": sum(
            row.get("capture_mode", "").upper() == "RECORDED_AUTHORIZED_FIXTURE"
            for row in rows
        ),
    }


def _price_evidence_gate(
    eod: _ComponentAudit,
    research: _ComponentAudit,
) -> dict[str, Any]:
    eod_semantic, eod_errors, eod_metrics = _eod_semantics(eod)
    research_semantic, research_errors, research_metrics = _research_price_semantics(
        research
    )
    semantic = (
        "BLOCKED"
        if "BLOCKED" in {eod_semantic, research_semantic}
        else "PARTIAL"
        if "PARTIAL" in {eod_semantic, research_semantic}
        else "PASS"
    )
    report = eod.report or {}
    price_evidence_status = str(report.get("price_evidence_status", "")).upper()
    if price_evidence_status and price_evidence_status != "PASS":
        semantic = "BLOCKED" if price_evidence_status == "BLOCKED" else "PARTIAL"
        eod_errors.append("OFFICIAL_EOD_PRICE_EVIDENCE_NOT_PASS")
    return _gate(
        "PRICE_EVIDENCE",
        (eod, research),
        semantic_status=semantic,
        semantic_errors=[*eod_errors, *research_errors],
        checks={
            "official_eod_hash_resolution": eod_semantic,
            "official_price_evidence": (
                "PASS" if price_evidence_status in {"", "PASS"} else price_evidence_status
            ),
            "research_history_support": research_semantic,
        },
        metrics={
            "official_eod_rows": eod_metrics["rows"],
            "research_price_rows": research_metrics["rows"],
            "research_fixture_rows": research_metrics["fixture_rows"],
        },
        concepts=(
            "OFFICIAL_EOD_IS_SEPARATE_FROM_RESEARCH_PRICE_HISTORY",
            "SOURCE_ID_OR_REVIEW_STATUS_IS_NOT_PROOF",
        ),
    )


def _corporate_action_integration(
    ca: _ComponentAudit,
    official: _ComponentAudit,
    status_history: _ComponentAudit,
    eod: _ComponentAudit,
    benchmark: _ComponentAudit,
) -> tuple[str, list[str], dict[str, str], dict[str, int]]:
    """Join every corporate-action row to dated foundation evidence.

    Older fixture ledgers predate the identity/date columns.  They remain explicit
    PARTIAL evidence: an absent date is never replaced with a report date or an EOD
    date.  An explicit unknown/mismatched identity or malformed date is a blocker.
    """

    factor_rows = ca.rows.get("normalized/corporate_action_factor_ledger.csv", [])
    policy_rows = ca.rows.get(
        "normalized/corporate_action_return_policy_queue.csv", []
    )
    identity_rows = official.rows.get("normalized/security_master.csv", [])
    calendar_rows = official.rows.get("normalized/trading_calendar.csv", [])
    status_rows = status_history.rows.get("normalized/status_intervals.csv", [])
    eod_rows = eod.rows.get("normalized/official_daily_eod.csv", [])
    benchmark_rows = benchmark.rows.get("normalized/benchmark_history.csv", [])

    errors: set[str] = set()
    identity_errors: set[str] = set()
    calendar_errors: set[str] = set()
    status_errors: set[str] = set()
    eod_errors: set[str] = set()
    benchmark_errors: set[str] = set()
    benchmark_treatment_errors: set[str] = set()
    link_errors: set[str] = set()
    partial = {
        "identity": False,
        "calendar": False,
        "status": False,
        "eod": False,
        "benchmark": False,
        "link": False,
    }
    metrics = {
        "ca_factor_rows_joined": 0,
        "ca_policy_rows_joined": 0,
        "ca_rows_unverifiable_without_invention": 0,
        "in_window_action_rows": 0,
        "out_of_window_action_rows": 0,
        "affected_eod_rows_joined": 0,
        "benchmark_action_dates_joined": 0,
        "total_return_benchmark_action_dates": 0,
        "benchmark_rows_with_forbidden_ca_treatment": 0,
    }

    identities_by_code: dict[str, list[dict[str, str]]] = {}
    for row in identity_rows:
        identities_by_code.setdefault(row.get("security_code", ""), []).append(row)
    statuses_by_code: dict[str, list[dict[str, str]]] = {}
    for row in status_rows:
        statuses_by_code.setdefault(row.get("security_code", ""), []).append(row)

    parsed_calendar: list[tuple[object, dict[str, str]]] = []
    for index, row in enumerate(calendar_rows):
        try:
            day = parse_iso_date(
                row.get("trade_date"), f"official calendar row {index}.trade_date"
            )
        except ValueError:
            calendar_errors.add(f"OFFICIAL_CALENDAR_ROW_{index}_TRADE_DATE_INVALID")
            continue
        parsed_calendar.append((day, row))

    parsed_eod: list[tuple[object, dict[str, str]]] = []
    for index, row in enumerate(eod_rows):
        try:
            day = parse_iso_date(
                row.get("trade_date"), f"official EOD row {index}.trade_date"
            )
        except ValueError:
            eod_errors.add(f"OFFICIAL_EOD_ROW_{index}_TRADE_DATE_INVALID")
            continue
        parsed_eod.append((day, row))

    eod_window: tuple[object, object] | None = None
    eod_report = eod.report or {}
    window_from = eod_report.get("window_from")
    window_to = eod_report.get("window_to")
    if window_from in (None, "") and window_to in (None, ""):
        partial["eod"] = bool(factor_rows or policy_rows)
    else:
        try:
            parsed_from = parse_iso_date(window_from, "official EOD window_from")
            parsed_to = parse_iso_date(window_to, "official EOD window_to")
            if parsed_from > parsed_to:
                raise ValueError("reversed window")
            eod_window = (parsed_from, parsed_to)
        except ValueError:
            eod_errors.add("OFFICIAL_EOD_DECLARED_WINDOW_INVALID")

    factor_rows_by_action: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for index, row in enumerate(factor_rows):
        action_id = row.get("action_id", "").strip()
        if not action_id:
            link_errors.add(f"CA_FACTOR_ROW_{index}_ACTION_ID_MISSING")
            continue
        factor_rows_by_action.setdefault(action_id, []).append((index, row))
    for indexed_rows in factor_rows_by_action.values():
        if len(indexed_rows) > 1:
            for index, _ in indexed_rows:
                link_errors.add(f"CA_FACTOR_ROW_{index}_ACTION_ID_DUPLICATE")

    factor_join_status: dict[int, str] = {}
    in_window_actions: list[tuple[int, object, str]] = []
    allowed_eod_states = {
        "TRADING": {"TRADED", "NO_TRADE", "HALTED"},
        "SUSPENDED": {"SUSPENDED", "TRADED_THEN_SUSPENDED"},
        "DELISTED": {"NOT_LISTED_OR_NOT_ELIGIBLE"},
    }

    for index, row in enumerate(factor_rows):
        row_errors_before = sum(
            len(values)
            for values in (
                identity_errors,
                calendar_errors,
                status_errors,
                eod_errors,
                benchmark_errors,
                link_errors,
            )
        )
        row_partial = False
        code = row.get("security_code", "").strip()
        if not code or not code.isdigit():
            identity_errors.add(f"CA_FACTOR_ROW_{index}_SECURITY_CODE_INVALID")
            status_errors.add(f"CA_FACTOR_ROW_{index}_STATUS_SECURITY_CODE_INVALID")
            factor_join_status[index] = "BLOCKED"
            continue

        code_identities = identities_by_code.get(code, [])
        code_statuses = statuses_by_code.get(code, [])
        if not code_identities:
            identity_errors.add(
                f"CA_FACTOR_ROW_{index}_OFFICIAL_IDENTITY_SECURITY_CODE_UNKNOWN"
            )
        if not code_statuses:
            status_errors.add(f"CA_FACTOR_ROW_{index}_STATUS_SECURITY_CODE_UNKNOWN")

        ticker = row.get("ticker", "").strip()
        isin = row.get("isin", "").strip()
        raw_action_date = row.get("ex_date", "").strip()
        if not ticker or not isin:
            partial["identity"] = True
            partial["link"] = True
            row_partial = True
        if not raw_action_date:
            partial["identity"] = True
            partial["calendar"] = True
            partial["status"] = True
            partial["eod"] = True
            partial["link"] = True
            row_partial = True
            metrics["ca_rows_unverifiable_without_invention"] += 1
            row_errors_after = sum(
                len(values)
                for values in (
                    identity_errors,
                    calendar_errors,
                    status_errors,
                    eod_errors,
                    benchmark_errors,
                    link_errors,
                )
            )
            factor_join_status[index] = (
                "BLOCKED" if row_errors_after > row_errors_before else "PARTIAL"
            )
            continue
        try:
            action_date = parse_iso_date(
                raw_action_date, f"CA factor row {index}.ex_date"
            )
        except ValueError:
            link_errors.add(f"CA_FACTOR_ROW_{index}_EX_DATE_INVALID")
            factor_join_status[index] = "BLOCKED"
            continue

        effective_identities: list[dict[str, str]] = []
        identity_interval_invalid = False
        for identity in code_identities:
            try:
                valid_from = parse_iso_date(
                    identity.get("valid_from"),
                    f"CA factor row {index} official identity valid_from",
                )
                valid_to_raw = identity.get("valid_to", "")
                valid_to = (
                    None
                    if valid_to_raw in (None, "")
                    else parse_iso_date(
                        valid_to_raw,
                        f"CA factor row {index} official identity valid_to",
                    )
                )
                if valid_to is not None and valid_to < valid_from:
                    raise ValueError("reversed identity interval")
            except ValueError:
                identity_interval_invalid = True
                continue
            if valid_from <= action_date and (
                valid_to is None or action_date <= valid_to
            ):
                effective_identities.append(identity)
        if identity_interval_invalid:
            identity_errors.add(
                f"CA_FACTOR_ROW_{index}_OFFICIAL_IDENTITY_INTERVAL_INVALID"
            )
        if len(effective_identities) != 1:
            identity_errors.add(
                f"CA_FACTOR_ROW_{index}_OFFICIAL_IDENTITY_MISSING_OR_AMBIGUOUS"
            )
        else:
            identity = effective_identities[0]
            official_ticker = identity.get("ticker", "").strip()
            official_isin = identity.get("isin", "").strip()
            if ticker and official_ticker and ticker != official_ticker:
                identity_errors.add(
                    f"CA_FACTOR_ROW_{index}_OFFICIAL_IDENTITY_TICKER_MISMATCH"
                )
            elif not ticker or not official_ticker:
                partial["identity"] = True
                row_partial = True
            if isin and official_isin and isin != official_isin:
                identity_errors.add(
                    f"CA_FACTOR_ROW_{index}_OFFICIAL_IDENTITY_ISIN_MISMATCH"
                )
            elif not isin or not official_isin:
                partial["identity"] = True
                row_partial = True

        matching_calendar = [
            calendar_row
            for calendar_day, calendar_row in parsed_calendar
            if calendar_day == action_date
        ]
        if len(matching_calendar) != 1:
            calendar_errors.add(
                f"CA_FACTOR_ROW_{index}_OFFICIAL_CALENDAR_DATE_MISSING_OR_AMBIGUOUS"
            )
        elif matching_calendar[0].get("is_trading_day", "").lower() != "true":
            calendar_errors.add(
                f"CA_FACTOR_ROW_{index}_EX_DATE_NOT_OFFICIAL_TRADING_SESSION"
            )

        effective_statuses: list[dict[str, str]] = []
        status_interval_incomplete = False
        status_interval_invalid = False
        for status_row in code_statuses:
            try:
                effective_from = parse_iso_date(
                    status_row.get("effective_from"),
                    f"CA factor row {index} status effective_from",
                )
                effective_to_raw = status_row.get("effective_to", "")
                if effective_to_raw in (None, ""):
                    status_interval_incomplete = True
                    continue
                effective_to = parse_iso_date(
                    effective_to_raw,
                    f"CA factor row {index} status effective_to",
                )
                if effective_to < effective_from:
                    raise ValueError("reversed status interval")
            except ValueError:
                status_interval_invalid = True
                continue
            if effective_from <= action_date <= effective_to:
                effective_statuses.append(status_row)
        if status_interval_invalid:
            status_errors.add(f"CA_FACTOR_ROW_{index}_STATUS_INTERVAL_INVALID")
        if len(effective_statuses) != 1:
            if status_interval_incomplete and not effective_statuses:
                partial["status"] = True
                row_partial = True
            else:
                status_errors.add(
                    f"CA_FACTOR_ROW_{index}_STATUS_INTERVAL_MISSING_OR_AMBIGUOUS"
                )
        else:
            effective_status = effective_statuses[0]
            status_ticker = effective_status.get("ticker", "").strip()
            if ticker and status_ticker and ticker != status_ticker:
                status_errors.add(
                    f"CA_FACTOR_ROW_{index}_STATUS_IDENTITY_TICKER_MISMATCH"
                )
            elif not ticker or not status_ticker:
                partial["status"] = True
                row_partial = True
            if effective_status.get("status", "") not in allowed_eod_states:
                status_errors.add(f"CA_FACTOR_ROW_{index}_STATUS_VALUE_INVALID")

        if eod_window is None:
            partial["eod"] = True
            row_partial = True
        elif eod_window[0] <= action_date <= eod_window[1]:
            metrics["in_window_action_rows"] += 1
            in_window_actions.append(
                (index, action_date, row.get("action_type", ""))
            )
            matching_eod = [
                eod_row
                for eod_day, eod_row in parsed_eod
                if eod_day == action_date
                and eod_row.get("security_code", "") == code
            ]
            if len(matching_eod) != 1:
                eod_errors.add(
                    f"CA_FACTOR_ROW_{index}_AFFECTED_EOD_ROW_MISSING_OR_AMBIGUOUS"
                )
            else:
                eod_row = matching_eod[0]
                eod_ticker = eod_row.get("ticker", "").strip()
                if ticker and eod_ticker and ticker != eod_ticker:
                    eod_errors.add(
                        f"CA_FACTOR_ROW_{index}_AFFECTED_EOD_TICKER_MISMATCH"
                    )
                state = eod_row.get("trading_state", "")
                if len(effective_statuses) == 1:
                    status_value = effective_statuses[0].get("status", "")
                    if state not in allowed_eod_states.get(status_value, set()):
                        eod_errors.add(
                            f"CA_FACTOR_ROW_{index}_EOD_STATUS_SESSION_CONFLICT"
                        )
                elif not state:
                    partial["eod"] = True
                    row_partial = True
                metrics["affected_eod_rows_joined"] += 1
        else:
            metrics["out_of_window_action_rows"] += 1

        row_errors_after = sum(
            len(values)
            for values in (
                identity_errors,
                calendar_errors,
                status_errors,
                eod_errors,
                benchmark_errors,
                link_errors,
            )
        )
        if row_errors_after > row_errors_before:
            factor_join_status[index] = "BLOCKED"
        elif row_partial:
            factor_join_status[index] = "PARTIAL"
        else:
            factor_join_status[index] = "PASS"
            metrics["ca_factor_rows_joined"] += 1

    for index, row in enumerate(policy_rows):
        action_id = row.get("action_id", "").strip()
        if not action_id:
            link_errors.add(f"CA_POLICY_ROW_{index}_ACTION_ID_MISSING")
            continue
        linked = factor_rows_by_action.get(action_id, [])
        if len(linked) != 1:
            link_errors.add(
                f"CA_POLICY_ROW_{index}_FACTOR_ACTION_MISSING_OR_AMBIGUOUS"
            )
            continue
        factor_index, factor_row = linked[0]
        required_link_fields = ("security_code", "ticker", "ex_date", "action_type")
        if any(not row.get(field, "").strip() for field in required_link_fields):
            partial["link"] = True
            metrics["ca_rows_unverifiable_without_invention"] += 1
            continue
        mismatch = False
        for field in required_link_fields:
            if row.get(field, "").strip() != factor_row.get(field, "").strip():
                link_errors.add(
                    f"CA_POLICY_ROW_{index}_FACTOR_{_error_code(field)}_MISMATCH"
                )
                mismatch = True
        if not factor_row.get("isin", "").strip():
            partial["link"] = True
            metrics["ca_rows_unverifiable_without_invention"] += 1
        elif factor_join_status.get(factor_index) == "PASS" and not mismatch:
            metrics["ca_policy_rows_joined"] += 1
        elif factor_join_status.get(factor_index) == "PARTIAL":
            partial["link"] = True

    parsed_benchmark: list[tuple[object, dict[str, str]]] = []
    forbidden_benchmark_fields = {
        "corporate_action_factor",
        "corporate_action_multiplier",
        "return_price_multiplier",
        "cash_distribution_per_pre_action_share_fils",
    }
    for index, row in enumerate(benchmark_rows):
        if any(row.get(field, "").strip() for field in forbidden_benchmark_fields):
            treatment_error = (
                f"BENCHMARK_ROW_{index}_CORPORATE_ACTION_TREATMENT_FORBIDDEN"
            )
            benchmark_errors.add(treatment_error)
            benchmark_treatment_errors.add(treatment_error)
            metrics["benchmark_rows_with_forbidden_ca_treatment"] += 1
        try:
            benchmark_day = parse_iso_date(
                row.get("trade_date"), f"benchmark row {index}.trade_date"
            )
        except ValueError:
            benchmark_errors.add(f"BENCHMARK_ROW_{index}_TRADE_DATE_INVALID")
            continue
        basis = row.get("calculation_basis", "").strip()
        if not basis:
            partial["benchmark"] = True
        elif basis not in {"PRICE_INDEX", "TOTAL_RETURN_INDEX"}:
            benchmark_errors.add(f"BENCHMARK_ROW_{index}_CALCULATION_BASIS_INVALID")
        parsed_benchmark.append((benchmark_day, row))

    for factor_index, action_date, action_type in in_window_actions:
        same_day = [
            row for benchmark_day, row in parsed_benchmark if benchmark_day == action_date
        ]
        if not same_day:
            benchmark_errors.add(
                f"CA_FACTOR_ROW_{factor_index}_BENCHMARK_DATE_COVERAGE_MISSING"
            )
            continue
        metrics["benchmark_action_dates_joined"] += 1
        bases = {row.get("calculation_basis", "").strip() for row in same_day}
        if action_type in {"CASH_DIVIDEND_NORMAL", "CASH_DIVIDEND_SPECIAL"}:
            if "TOTAL_RETURN_INDEX" in bases:
                metrics["total_return_benchmark_action_dates"] += 1
            else:
                partial["benchmark"] = True

    errors.update(identity_errors)
    errors.update(calendar_errors)
    errors.update(status_errors)
    errors.update(eod_errors)
    errors.update(benchmark_errors)
    errors.update(link_errors)

    def check_status(category_errors: set[str], category_partial: bool) -> str:
        if category_errors:
            return "BLOCKED"
        if category_partial:
            return "PARTIAL"
        return "PASS"

    identity_status = check_status(identity_errors | link_errors, partial["identity"])
    calendar_status = check_status(calendar_errors | link_errors, partial["calendar"])
    eod_status = check_status(eod_errors | link_errors, partial["eod"])
    benchmark_status = check_status(
        benchmark_errors | link_errors, partial["benchmark"]
    )
    integration_status = (
        "BLOCKED"
        if errors
        else "PARTIAL"
        if any(partial.values())
        else "PASS"
    )
    checks = {
        "affected_eod_coverage": eod_status,
        "benchmark_basis_comparison": benchmark_status,
        "benchmark_treatment_separation": check_status(
            benchmark_treatment_errors, False
        ),
        "corporate_action_identity_join": identity_status,
        "official_action_calendar_join": calendar_status,
        "policy_factor_action_link": check_status(link_errors, partial["link"]),
        "status_session_integration": integration_status,
    }
    return integration_status, sorted(errors), checks, metrics


def _corporate_action_gate(
    ca: _ComponentAudit,
    official: _ComponentAudit,
    eod: _ComponentAudit,
    research: _ComponentAudit,
    status_history: _ComponentAudit,
    benchmark: _ComponentAudit,
) -> dict[str, Any]:
    ca_semantic, errors = _report_semantic_status(
        ca,
        ready_statuses=frozenset(
            {"CA_ENRICHMENT_READY", "CA_ENRICHMENT_ZERO_RESULT_READY"}
        ),
    )
    factor_rows = ca.rows.get("normalized/corporate_action_factor_ledger.csv", [])
    policy_rows = ca.rows.get(
        "normalized/corporate_action_return_policy_queue.csv", []
    )
    eod_rows = eod.rows.get("normalized/official_daily_eod.csv", [])
    research_rows = research.rows.get("normalized/research_price_history.csv", [])
    cash_rows = [
        row for row in factor_rows if row.get("action_type") == "CASH_DIVIDEND_NORMAL"
    ]
    invalid_cash = [
        row.get("action_id", "")
        for row in cash_rows
        if row.get("return_engine_treatment") != "RAW_PRICE_PLUS_CASH_COMPONENT"
        or not row.get("cash_distribution_per_pre_action_share_fils")
        or row.get("return_price_multiplier") not in {"1", "1.0", "1.00"}
    ]
    complex_rows = [
        row for row in factor_rows if row.get("action_type") in _COMPLEX_ACTIONS
    ]
    invalid_complex_ready = [
        row.get("action_id", "")
        for row in complex_rows
        if row.get("return_engine_ready", "").lower() == "true"
    ]
    pending_complex = sorted(
        {
            row.get("action_id", "")
            for row in complex_rows
            if row.get("return_engine_ready", "").lower() != "true"
        }
        | {row.get("action_id", "") for row in policy_rows}
    )
    adjusted_eod = sum(
        row.get("price_basis", "").upper() in {"ADJUSTED", "OFFICIALLY_ADJUSTED"}
        for row in eod_rows
    )
    adjusted_research = sum(
        row.get("price_basis", "").upper() == "ADJUSTED" for row in research_rows
    )
    double_count_risk = bool(adjusted_eod and factor_rows)
    integration_status, integration_errors, integration_checks, integration_metrics = (
        _corporate_action_integration(
            ca, official, status_history, eod, benchmark
        )
    )
    if invalid_cash:
        ca_semantic = "BLOCKED"
        errors.append("NORMAL_CASH_RAW_PLUS_CASH_CONTRACT_INVALID")
    if invalid_complex_ready:
        ca_semantic = "BLOCKED"
        errors.append("RIGHTS_OR_COMPLEX_ACTION_INCORRECTLY_MARKED_RETURN_READY")
    if double_count_risk:
        ca_semantic = "BLOCKED"
        errors.append("ADJUSTED_PRICE_DOUBLE_COUNT_RISK")
    if integration_status == "BLOCKED":
        ca_semantic = "BLOCKED"
        errors.extend(integration_errors)
    elif integration_status == "PARTIAL" and ca_semantic == "PASS":
        ca_semantic = "PARTIAL"
    if policy_rows or pending_complex:
        if ca_semantic != "BLOCKED":
            ca_semantic = "PARTIAL"
        errors.append("RIGHTS_OR_COMPLEX_RETURN_POLICY_PENDING")
    status_semantic, status_errors = _report_semantic_status(
        status_history,
        ready_statuses=frozenset({"HISTORICAL_STATUS_INTERVALS_READY"}),
    )
    if status_semantic == "BLOCKED":
        ca_semantic = "BLOCKED"
        errors.extend(status_errors)
    elif status_semantic == "PARTIAL" and ca_semantic == "PASS":
        ca_semantic = "PARTIAL"
        errors.extend(status_errors)
    state_field = next(
        (
            field_name
            for field_name in ("session_state", "trading_state", "trading_status")
            if any(field_name in row for row in eod_rows)
        ),
        "",
    )
    affected_status_rows = (
        sum(row.get(state_field, "") in {"SUSPENDED", "HALTED"} for row in eod_rows)
        if state_field
        else 0
    )
    return _gate(
        "PRICE_CORPORATE_ACTION_QA",
        (ca, official, eod, research, status_history, benchmark),
        semantic_status=ca_semantic,
        semantic_errors=errors,
        checks={
            "adjusted_price_double_count_guard": (
                "BLOCKED" if double_count_risk else "PASS"
            ),
            "cash_dividend_raw_plus_cash": "BLOCKED" if invalid_cash else "PASS",
            "rights_and_complex_return_policy": (
                "PARTIAL" if pending_complex else "PASS"
            ),
            **integration_checks,
        },
        metrics={
            "adjusted_official_eod_rows": adjusted_eod,
            "adjusted_research_rows": adjusted_research,
            "cash_action_rows": len(cash_rows),
            "complex_action_rows": len(complex_rows),
            "pending_policy_rows": len(policy_rows),
            "suspended_or_halted_eod_rows": affected_status_rows,
            **integration_metrics,
        },
        concepts=(
            "REFERENCE_PRICE_FACTOR",
            "HISTORICAL_CONTINUITY_FACTOR",
            "POSITION_QUANTITY_MULTIPLIER",
            "RETURN_PRICE_MULTIPLIER",
            "CASH_COMPONENT",
            "NORMAL_CASH_USES_RAW_PRICE_PLUS_SEPARATE_CASH",
            "RIGHTS_EXERCISE_SALE_LAPSE_POLICY_PENDING_BLOCKS_OUTCOMES",
            "COMPLEX_ACTION_PENDING_TREATMENT_BLOCKS_OUTCOMES",
            "ADJUSTED_PRICE_PLUS_ACTION_TREATMENT_MAY_DOUBLE_COUNT",
            "CORPORATE_ACTION_TREATMENTS_ARE_NOT_APPLIED_TO_BENCHMARK_SERIES",
            "TOTAL_RETURN_OUTCOMES_REQUIRE_COMPATIBLE_BENCHMARK_BASIS",
            "SUSPENDED_OR_HALTED_SESSION_IS_NOT_ORDINARY_MISSING_PRICE",
        ),
    )


def _benchmark_semantics(
    benchmark: _ComponentAudit,
) -> tuple[str, list[str], dict[str, Any]]:
    semantic, errors = _report_semantic_status(
        benchmark,
        ready_statuses=frozenset(
            {"READY", "BENCHMARK_HISTORY_READY", "BENCHMARK_IMPORT_READY"}
        ),
    )
    report = benchmark.report or {}
    rows = benchmark.rows.get("normalized/benchmark_history.csv", [])
    if not rows:
        semantic = "BLOCKED"
        errors.append("BENCHMARK_HISTORY_EMPTY")
    entries = report.get("benchmark_entries", [])
    if not isinstance(entries, list):
        semantic = "BLOCKED"
        errors.append("BENCHMARK_ENTRIES_NOT_LIST")
        entries = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            semantic = "BLOCKED"
            errors.append(f"BENCHMARK_ENTRY_{index}_NOT_OBJECT")
            continue
        availability = str(entry.get("availability_status", "")).upper()
        validation = str(entry.get("validation_status", "")).upper()
        if availability not in {"AVAILABLE", "READY"} or validation != "PASS":
            if semantic != "BLOCKED":
                semantic = "PARTIAL"
            errors.append(f"BENCHMARK_ENTRY_{index}_NOT_READY")
    return semantic, errors, {
        "rows": len(rows),
        "benchmark_count": len({row.get("benchmark_code", "") for row in rows}),
        "entry_count": len(entries),
    }


def _benchmark_history_gate(benchmark: _ComponentAudit) -> dict[str, Any]:
    semantic, errors, metrics = _benchmark_semantics(benchmark)
    report = benchmark.report or {}
    basis_types = sorted(
        {
            row.get("benchmark_type", row.get("calculation_basis", ""))
            for row in benchmark.rows.get("normalized/benchmark_history.csv", [])
            if row.get("benchmark_type", row.get("calculation_basis", ""))
        }
    )
    return _gate(
        "BENCHMARK_HISTORY",
        (benchmark,),
        semantic_status=semantic,
        semantic_errors=errors,
        checks={
            "calendar_reconciliation": (
                "PASS"
                if all(
                    not entry.get("missing_trading_dates")
                    and not entry.get("extra_trading_dates")
                    for entry in report.get("benchmark_entries", [])
                    if isinstance(entry, dict)
                )
                else "BLOCKED"
            ),
            "normalized_history": "PASS" if metrics["rows"] else "BLOCKED",
            "type_and_basis_explicit": "PASS" if basis_types else "PARTIAL",
        },
        metrics=metrics,
        concepts=(
            "PRICE_INDEX_IS_NOT_TOTAL_RETURN_INDEX",
            "NO_FORWARD_FILL_OR_SUBSTITUTE_BENCHMARK",
        ),
    )


def _benchmark_evidence_gate(benchmark: _ComponentAudit) -> dict[str, Any]:
    semantic, errors, metrics = _benchmark_semantics(benchmark)
    return _gate(
        "BENCHMARK_EVIDENCE",
        (benchmark,),
        semantic_status=semantic,
        semantic_errors=errors,
        checks={
            "hash_bound_classification": (
                "PASS"
                if benchmark.evidence_classification == "PROVEN_REAL_EVIDENCE"
                else "PARTIAL"
            ),
            "raw_hash_resolution": "PASS" if not benchmark.structural_errors else "BLOCKED",
            "research_use_rights": "PASS" if benchmark.rights_compatible else "PARTIAL",
        },
        metrics=metrics,
        concepts=("REPORT_SOURCE_ID_OR_REVIEW_STATUS_IS_NOT_EVIDENCE_PROOF",),
    )


def _market_totals_gate(eod: _ComponentAudit) -> dict[str, Any]:
    semantic, errors, _ = _eod_semantics(eod)
    report = eod.report or {}
    totals_rows = eod.rows.get("normalized/daily_market_totals.csv", [])
    totals_status = str(report.get("market_totals_status", "")).upper()
    if totals_status != "PASS":
        if totals_status == "BLOCKED":
            semantic = "BLOCKED"
        elif semantic != "BLOCKED":
            semantic = "PARTIAL"
        errors.append("DAILY_MARKET_TOTAL_RECONCILIATION_NOT_PASS")
    if not totals_rows and semantic != "BLOCKED":
        semantic = "PARTIAL"
        errors.append("DAILY_MARKET_TOTALS_NOT_AVAILABLE")
    return _gate(
        "MARKET_TOTAL_RECONCILIATION",
        (eod,),
        semantic_status=semantic,
        semantic_errors=errors,
        checks={
            "official_totals_available": "PASS" if totals_rows else "PARTIAL",
            "upstream_totals_reconciliation": (
                "PASS" if totals_status == "PASS" else "PARTIAL"
            ),
        },
        metrics={"market_total_rows": len(totals_rows)},
    )


def _benchmark_query_status(benchmark: _ComponentAudit) -> tuple[str, list[str]]:
    report = benchmark.report or {}
    explicit = str(report.get("query_and_pagination_status", "")).upper()
    manifest = benchmark.json_files.get("benchmark_history_manifest.json", {})
    entries = manifest.get(
        "artifacts",
        manifest.get("benchmarks", manifest.get("entries", [])),
    )
    errors: list[str] = []
    if not isinstance(entries, list) or not entries:
        return "PARTIAL", ["BENCHMARK_QUERY_CONTRACT_NOT_REINSPECTABLE"]
    for index, entry in enumerate(entries):
        try:
            if not isinstance(entry, dict):
                raise ValueError("entry is not an object")
            pages_declared = int(entry["pages_declared"])
            pages_received = int(entry["pages_received"])
            result_count = int(entry["result_count_declared"])
            row_count = int(entry["row_count"])
            if pages_declared != pages_received:
                raise ValueError("pagination mismatch")
            if result_count != row_count:
                raise ValueError("result count mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"BENCHMARK_QUERY_ENTRY_{index}:{exc}")
    if explicit == "BLOCKED":
        errors.append("BENCHMARK_QUERY_AND_PAGINATION_REPORT_BLOCKED")
    if errors:
        return "BLOCKED", errors
    return "PASS", []


def _query_gate(
    status_history: _ComponentAudit,
    research: _ComponentAudit,
    benchmark: _ComponentAudit,
    eod: _ComponentAudit,
) -> dict[str, Any]:
    status_state, status_errors = _query_ledger_status(status_history)
    benchmark_state, benchmark_errors = _benchmark_query_status(benchmark)
    eod_report = eod.report or {}
    eod_state = str(
        eod_report.get(
            "query_and_pagination_status",
            eod_report.get("capture_completeness_status", ""),
        )
    ).upper()
    if not eod_state:
        denominator = str(eod_report.get("denominator_status", "")).upper()
        eod_state = "PASS" if denominator == "PASS" else "PARTIAL"
    if eod_state not in GATE_STATUSES:
        eod_state = "PARTIAL"
    research_report = research.report or {}
    preserved_manifest_hash = research.file_hashes.get("price_collection_manifest.csv")
    research_state = (
        "PASS"
        if preserved_manifest_hash
        and research_report.get("collection_manifest_sha256") == preserved_manifest_hash
        and not research_report.get("manifest_errors")
        else "PARTIAL"
    )
    states = {status_state, benchmark_state, eod_state, research_state}
    semantic = (
        "BLOCKED"
        if "BLOCKED" in states
        else "PARTIAL"
        if "PARTIAL" in states
        else "PASS"
    )
    errors = [*status_errors, *benchmark_errors]
    if eod_state != "PASS":
        errors.append("OFFICIAL_EOD_QUERY_OR_EXPORT_COMPLETENESS_NOT_PROVEN")
    if research_state != "PASS":
        errors.append("RESEARCH_PRICE_COLLECTION_MANIFEST_NOT_HASH_BOUND")
    return _gate(
        "QUERY_AND_PAGINATION_COMPLETENESS",
        (status_history, research, benchmark, eod),
        semantic_status=semantic,
        semantic_errors=errors,
        checks={
            "benchmark_queries": benchmark_state,
            "official_eod_capture": eod_state,
            "research_price_export_manifest": research_state,
            "status_history_queries": status_state,
        },
        metrics={
            "status_query_rows": len(
                status_history.rows.get("manifests/status_query_ledger.csv", [])
            )
        },
    )


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PRIVATE_KEY",
        re.compile(r"-----BEGIN (?:DSA |EC |OPENSSH |PGP |RSA )?PRIVATE KEY-----"),
    ),
    (
        "KNOWN_TOKEN_FORMAT",
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"glpat-[A-Za-z0-9_-]{20,}|(?:AKIA|ASIA)[0-9A-Z]{16}|"
            r"AIza[0-9A-Za-z_-]{35}|GOCSPX-[0-9A-Za-z_-]{20,}|"
            r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
            r"(?:rk|sk)_live_[A-Za-z0-9]{16,}|"
            r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}|"
            r"hf_[A-Za-z0-9]{20,}|npm_[A-Za-z0-9]{20,}|"
            r"[0-9]{8,12}:[A-Za-z0-9_-]{30,})\b"
        ),
    ),
    (
        "JWT",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\b"
        ),
    ),
    (
        "CREDENTIAL_URL",
        re.compile(
            r"(?:https?|mongodb(?:\+srv)?|mysql|postgres(?:ql)?|redis)://"
            r"[^\s/@:]+:[^\s/@]+@"
        ),
    ),
    (
        "SIGNED_OR_TOKENIZED_URL",
        re.compile(
            r"(?i)[?&](?:access_token|signature|token|x-amz-(?:credential|signature)|"
            r"x-goog-(?:credential|signature)|oauth_token|code|jwt)=[^&\s]+"
        ),
    ),
    (
        "CREDENTIAL_ASSIGNMENT",
        re.compile(
            r"(?i)[\"']?[A-Za-z0-9_.-]*(?:access[_-]?token|api[_-]?key|auth[_-]?token|"
            r"client[_-]?secret|hmac[_-]?key|password|passwd|private[_-]?key|secret|"
            r"session(?:id)?|signature|cookie|credential)[\"']?\s*[:=]\s*"
            r"[\"'][A-Za-z0-9_./+=:@-]{8,}[\"']"
        ),
    ),
    (
        "CREDENTIAL_UNQUOTED_CONFIG_ASSIGNMENT",
        re.compile(
            r"(?i)^\s*[A-Za-z0-9_.-]*(?:access[_-]?token|api[_-]?key|"
            r"auth[_-]?token|bearer[_-]?token|client[_-]?secret|hmac[_-]?key|"
            r"password|passwd|private[_-]?key|secret|sessionid|signature|token|"
            r"cookie|credential)\s*:\s*[A-Za-z0-9_./+=:@-]{8,}\s*(?:#.*)?$"
        ),
    ),
    (
        "CREDENTIAL_ENVIRONMENT_ASSIGNMENT",
        re.compile(
            r"^\s*[A-Z0-9_]*(?:ACCESS_TOKEN|API_KEY|AUTH_TOKEN|BEARER_TOKEN|"
            r"CLIENT_SECRET|HMAC_KEY|PASSWORD|PASSWD|PRIVATE_KEY|SECRET|SESSIONID|"
            r"SIGNATURE|TOKEN|COOKIE|CREDENTIAL)\s*=\s*[^\s#]{8,}\s*$"
        ),
    ),
)
_SECRET_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "env",
        "htmlcov",
        "runtime",
        "venv",
    }
)
_SENSITIVE_SUFFIXES = frozenset({".jks", ".key", ".keystore", ".p12", ".pfx"})
_MAX_SECRET_SCAN_BYTES = 16 * 1024 * 1024
_REQUIRED_REPOSITORY_FILES = frozenset(
    {
        "AGENTS.md",
        "CODEX_START_HERE.md",
        "config/pilot/security_master_seed.json",
        "config/sources.json",
        "docs/codex/CURRENT_TASK.md",
        "pyproject.toml",
    }
)


def _git_output(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("git repository inspection is unavailable") from exc
    if result.returncode != 0:
        raise ValueError("git repository inspection failed")
    return result.stdout


def _repository_identity(project_root: Path) -> tuple[Path, str, frozenset[str]]:
    """Resolve a real KU-BO Git top-level and bind the scan to its current HEAD."""

    root = require_real_directory(project_root, field="PROJECT_ROOT")
    git_marker = root / ".git"
    if git_marker.is_symlink() or not git_marker.exists():
        raise ValueError("project root has no real Git metadata marker")
    try:
        declared_root = Path(
            _git_output(root, "rev-parse", "--show-toplevel")
            .decode("utf-8")
            .strip()
        )
    except UnicodeError as exc:
        raise ValueError("Git top-level is not UTF-8") from exc
    if os.path.normcase(str(declared_root.resolve())) != os.path.normcase(
        str(root.resolve())
    ):
        raise ValueError("project root is not the Git repository top-level")
    try:
        head_sha = _git_output(root, "rev-parse", "--verify", "HEAD").decode(
            "ascii"
        ).strip()
        tracked = frozenset(
            item
            for item in _git_output(root, "ls-files", "--full-name", "-z")
            .decode("utf-8")
            .split("\x00")
            if item
        )
    except UnicodeError as exc:
        raise ValueError("Git repository identity is not decodable") from exc
    if not re.fullmatch(r"[0-9a-f]{40,64}", head_sha):
        raise ValueError("Git HEAD is not a canonical object ID")
    missing = sorted(_REQUIRED_REPOSITORY_FILES - tracked)
    if missing:
        raise ValueError(
            "project repository lacks required tracked KU-BO files:"
            + ",".join(missing)
        )
    return root, head_sha, tracked


def _git_output_with_input(
    root: Path,
    arguments: tuple[str, ...],
    content: bytes,
) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("git blob inspection is unavailable") from exc
    if result.returncode != 0:
        raise ValueError("git blob inspection failed")
    return result.stdout


def _git_relative_path(value: bytes, *, field_name: str) -> str:
    try:
        decoded = value.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{field_name} is not UTF-8") from exc
    return _relative_artifact_path(decoded, field_name=field_name)


def _head_entries(root: Path) -> list[tuple[str, str, str]]:
    content = _git_output(root, "ls-tree", "-r", "-z", "--full-tree", "HEAD")
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for index, record in enumerate(item for item in content.split(b"\x00") if item):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ")
        except (UnicodeError, ValueError) as exc:
            raise ValueError(f"HEAD tree entry {index} is malformed") from exc
        path = _git_relative_path(raw_path, field_name=f"HEAD tree path {index}")
        if path in seen:
            raise ValueError("HEAD tree contains a duplicate path")
        if object_type not in {"blob", "commit"}:
            raise ValueError("HEAD tree contains an unsupported object type")
        if not re.fullmatch(r"[0-9a-f]{40,64}", object_id):
            raise ValueError("HEAD tree contains an invalid object ID")
        seen.add(path)
        entries.append((path, mode, object_id))
    if not entries:
        raise ValueError("HEAD tree is empty")
    return entries


def _index_entries(root: Path) -> list[tuple[str, str, str]]:
    content = _git_output(root, "ls-files", "--stage", "-z")
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for index, record in enumerate(item for item in content.split(b"\x00") if item):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split(" ")
        except (UnicodeError, ValueError) as exc:
            raise ValueError(f"Git index entry {index} is malformed") from exc
        if stage != "0":
            raise ValueError("Git index contains unresolved merge stages")
        path = _git_relative_path(raw_path, field_name=f"Git index path {index}")
        if path in seen:
            raise ValueError("Git index contains a duplicate path")
        if not re.fullmatch(r"[0-9a-f]{40,64}", object_id):
            raise ValueError("Git index contains an invalid object ID")
        seen.add(path)
        entries.append((path, mode, object_id))
    if not entries:
        raise ValueError("Git index is empty")
    return entries


def _git_blob_payloads(
    root: Path,
    object_ids: set[str],
) -> tuple[dict[str, bytes], frozenset[str]]:
    ordered = sorted(object_ids)
    if not ordered:
        return {}, frozenset()
    queries = b"".join(value.encode("ascii") + b"\n" for value in ordered)
    metadata = _git_output_with_input(
        root,
        ("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"),
        queries,
    ).splitlines()
    if len(metadata) != len(ordered):
        raise ValueError("git blob metadata response count is invalid")
    safe: list[str] = []
    oversize: set[str] = set()
    declared_sizes: dict[str, int] = {}
    for expected, raw in zip(ordered, metadata, strict=True):
        try:
            returned, object_type, raw_size = raw.decode("ascii").split(" ")
            size = int(raw_size)
        except (UnicodeError, ValueError) as exc:
            raise ValueError("git blob metadata response is malformed") from exc
        if returned != expected or object_type != "blob" or size < 0:
            raise ValueError("git blob metadata response does not match its query")
        declared_sizes[expected] = size
        if size > _MAX_SECRET_SCAN_BYTES:
            oversize.add(expected)
        else:
            safe.append(expected)
    if not safe:
        return {}, frozenset(oversize)

    payload_response = _git_output_with_input(
        root,
        ("cat-file", "--batch"),
        b"".join(value.encode("ascii") + b"\n" for value in safe),
    )
    payloads: dict[str, bytes] = {}
    offset = 0
    for expected in safe:
        header_end = payload_response.find(b"\n", offset)
        if header_end < 0:
            raise ValueError("git blob payload header is missing")
        try:
            returned, object_type, raw_size = payload_response[
                offset:header_end
            ].decode("ascii").split(" ")
            size = int(raw_size)
        except (UnicodeError, ValueError) as exc:
            raise ValueError("git blob payload header is malformed") from exc
        if (
            returned != expected
            or object_type != "blob"
            or size != declared_sizes[expected]
        ):
            raise ValueError("git blob payload header does not match metadata")
        content_start = header_end + 1
        content_end = content_start + size
        if (
            content_end >= len(payload_response)
            or payload_response[content_end : content_end + 1] != b"\n"
        ):
            raise ValueError("git blob payload is truncated")
        payloads[expected] = payload_response[content_start:content_end]
        offset = content_end + 1
    if offset != len(payload_response):
        raise ValueError("git blob payload response contains trailing data")
    return payloads, frozenset(oversize)


def _tracked_runtime(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return bool(parts) and parts[0].casefold() == "runtime"


def _payload_secret_findings(
    payload: bytes,
    *,
    path: str,
    origin: str,
) -> list[str]:
    label = f"{origin}:{path}"
    if PurePosixPath(path).suffix.casefold() in _SENSITIVE_SUFFIXES:
        return [f"{label}:0:CREDENTIAL_FILE"]
    text = payload.decode("utf-8", errors="ignore")
    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if "secret-guard: allow" in line:
            continue
        for rule, pattern in _SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{label}:{line_number}:{rule}")
    return findings


def _scan_git_entries(
    root: Path,
    entries: list[tuple[str, str, str]],
    *,
    origin: str,
) -> tuple[list[str], int]:
    findings: list[str] = []
    regular: list[tuple[str, str]] = []
    for path, mode, object_id in entries:
        label = f"{origin}:{path}"
        if _tracked_runtime(path):
            findings.append(f"{label}:0:TRACKED_RUNTIME_PATH_FORBIDDEN")
        if mode in {"100644", "100755"}:
            regular.append((path, object_id))
        elif mode == "120000":
            findings.append(f"{label}:0:TRACKED_SYMLINK_NOT_SCANNED")
        elif mode == "160000":
            findings.append(f"{label}:0:TRACKED_GITLINK_NOT_SCANNED")
        else:
            raise ValueError(f"{origin} contains an unsupported Git file mode")
    payloads, oversize = _git_blob_payloads(
        root,
        {object_id for _, object_id in regular},
    )
    scanned = 0
    for path, object_id in regular:
        label = f"{origin}:{path}"
        if object_id in oversize:
            findings.append(f"{label}:0:OVERSIZE_TRACKED_BLOB_NOT_SCANNED")
            continue
        payload = payloads.get(object_id)
        if payload is None:
            raise ValueError(f"{origin} tracked blob payload is missing")
        scanned += 1
        findings.extend(
            _payload_secret_findings(payload, path=path, origin=origin)
        )
    return findings, scanned


def _git_path_set(root: Path, *arguments: str) -> set[str]:
    content = _git_output(root, *arguments)
    paths: set[str] = set()
    for index, raw_path in enumerate(item for item in content.split(b"\x00") if item):
        path = _git_relative_path(raw_path, field_name=f"Git path output {index}")
        if path in paths:
            raise ValueError("Git path output contains a duplicate path")
        paths.add(path)
    return paths


def _worktree_relevant_paths(root: Path) -> set[str]:
    changed = _git_path_set(root, "diff", "--name-only", "-z", "--")
    untracked = _git_path_set(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    ignored = _git_path_set(
        root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
    )
    return changed | untracked | ignored


def _repository_secret_scan(
    project_root: Path,
) -> tuple[str, list[str], int, str]:
    try:
        root, head_sha, _tracked = _repository_identity(project_root)
    except ValueError as exc:
        return (
            "BLOCKED",
            [f"PROJECT_ROOT_NOT_KU_BO_GIT_REPOSITORY:{exc}"],
            0,
            "",
        )
    try:
        head_entries = _head_entries(root)
        index_entries = _index_entries(root)
        head_findings, head_scanned = _scan_git_entries(
            root,
            head_entries,
            origin="HEAD",
        )
        head_by_path = {
            path: (mode, object_id) for path, mode, object_id in head_entries
        }
        queued_entries = [
            entry
            for entry in index_entries
            if head_by_path.get(entry[0]) != (entry[1], entry[2])
        ]
        index_findings, index_scanned = _scan_git_entries(
            root,
            queued_entries,
            origin="INDEX",
        )
        worktree_paths = _worktree_relevant_paths(root)
    except ValueError as exc:
        return (
            "BLOCKED",
            [f"REPOSITORY_GIT_BLOB_SCAN_INVALID:{exc}"],
            0,
            head_sha,
        )
    findings: list[str] = [*head_findings, *index_findings]
    scanned = head_scanned + index_scanned
    index_paths = {path for path, _, _ in index_entries}
    for relative_name in sorted(worktree_paths):
        relative = PurePosixPath(relative_name)
        if (
            relative_name not in index_paths
            and any(part in _SECRET_IGNORED_DIRECTORIES for part in relative.parts)
        ):
            continue
        path = root / relative
        if path.is_symlink():
            findings.append(
                f"WORKTREE:{relative_name}:0:REPOSITORY_SYMLINK_NOT_SCANNED"
            )
            continue
        if not path.exists():
            continue
        if not path.is_file():
            findings.append(f"WORKTREE:{relative_name}:0:NONREGULAR_PATH_NOT_SCANNED")
            continue
        try:
            payload = safe_regular_file(
                path,
                field=f"SECRET_GUARD:{relative_name}",
                max_bytes=_MAX_SECRET_SCAN_BYTES,
            )
        except ValueError:
            findings.append(
                f"WORKTREE:{relative_name}:0:UNSCANNED_OR_OVERSIZE_REPOSITORY_FILE"
            )
            continue
        scanned += 1
        findings.extend(
            _payload_secret_findings(
                payload,
                path=relative_name,
                origin="WORKTREE",
            )
        )
    return ("PASS", [], scanned, head_sha) if not findings else (
        "BLOCKED",
        sorted(set(findings)),
        scanned,
        head_sha,
    )


def _secret_gate(project_root: Path) -> dict[str, Any]:
    status, findings, scanned, head_sha = _repository_secret_scan(project_root)
    return {
        "gate": "RUNTIME_SECRET_GUARD",
        "critical": True,
        "status": status,
        "evidence_classification": (
            "PROVEN_REAL_EVIDENCE" if status == "PASS" else "BLOCKED"
        ),
        "rights_compatible": status == "PASS",
        "errors": findings,
        "hashes": [],
        "details": {
            "components": [],
            "checks": {"conservative_repository_scan": status},
            "metrics": {
                "finding_count": len(findings),
                "repository_head_sha": head_sha,
                "scanned_file_count": scanned,
            },
            "concepts": [
                "GIT_TOP_LEVEL_AND_REQUIRED_TRACKED_FILES_VERIFIED",
                "UNTRACKED_RUNTIME_DIRECTORY_EXCLUDED_FROM_REPOSITORY_SECRET_SCAN",
                "TRACKED_RUNTIME_PATHS_FORBIDDEN",
                "NO_SECRET_RECEIPT_WAS_FABRICATED",
            ],
        },
    }


def _committed_outcome_policy(project_root: Path) -> bytes | None:
    """Return the exact policy blob at HEAD, or None before its first commit."""

    try:
        root = require_real_directory(project_root, field="PROJECT_ROOT")
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "cat-file",
                "blob",
                "HEAD:config/pilot/outcome_session_policy.json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _policy_audit(
    path: Path | None,
    *,
    project_root: Path,
    authoritative_path: Path,
) -> tuple[str, list[str], dict[str, str] | None]:
    if path is None:
        return "MISSING", ["OUTCOME_SESSION_POLICY_NOT_FROZEN"], None
    try:
        payload, content = load_strict_json_object(
            path,
            field="OUTCOME_SESSION_POLICY",
        )
    except ValueError as exc:
        return "INVALID", [f"OUTCOME_SESSION_POLICY_INVALID:{exc}"], None
    receipt = {
        "component": "OUTCOME_SESSION_POLICY",
        "path": "outcome_session_policy.json",
        "sha256": _sha256(content),
    }
    try:
        _, authoritative_content = load_strict_json_object(
            authoritative_path,
            field="AUTHORITATIVE_OUTCOME_SESSION_POLICY",
        )
    except ValueError as exc:
        return (
            "INVALID",
            [f"AUTHORITATIVE_OUTCOME_SESSION_POLICY_INVALID:{exc}"],
            receipt,
        )
    if content != authoritative_content:
        return (
            "INVALID",
            ["OUTCOME_SESSION_POLICY_NOT_AUTHORITATIVE"],
            receipt,
        )
    committed_content = _committed_outcome_policy(project_root)
    if committed_content is not None and authoritative_content != committed_content:
        return (
            "INVALID",
            ["AUTHORITATIVE_OUTCOME_SESSION_POLICY_DIFFERS_FROM_COMMITTED_HEAD"],
            receipt,
        )
    expected_keys = {
        "schema_version",
        "policy_id",
        "status",
        "timezone",
        "horizon_basis",
        "non_trading_day_rule",
        "suspended_or_halted_rule",
        "corporate_action_rule",
        "adjusted_price_double_count_guard",
        "rights_issue_policy",
        "complex_action_policy",
        "decision_id",
        "claim_boundary",
    }
    if set(payload) != expected_keys:
        return (
            "INVALID",
            ["OUTCOME_SESSION_POLICY_UNKNOWN_OR_MISSING_FIELDS"],
            {
                "component": "OUTCOME_SESSION_POLICY",
                "path": "outcome_session_policy.json",
                "sha256": _sha256(content),
            },
        )
    if (
        not isinstance(payload.get("policy_id"), str)
        or not payload["policy_id"].strip()
        or payload["policy_id"] != payload["policy_id"].strip()
        or not isinstance(payload.get("decision_id"), str)
        or not payload["decision_id"].strip()
        or payload["decision_id"] != payload["decision_id"].strip()
        or payload.get("status") not in {"FROZEN", "UNFROZEN"}
    ):
        return (
            "INVALID",
            ["OUTCOME_SESSION_POLICY_IDENTIFIER_OR_STATUS_INVALID"],
            {
                "component": "OUTCOME_SESSION_POLICY",
                "path": "outcome_session_policy.json",
                "sha256": _sha256(content),
            },
        )
    expected = {
        "schema_version": "1.0",
        "policy_id": "KU_BO_PILOT_OUTCOME_SESSION_POLICY",
        "timezone": "Asia/Kuwait",
        "horizon_basis": "OFFICIAL_TRADING_SESSIONS",
        "non_trading_day_rule": "ADVANCE_TO_NEXT_ELIGIBLE_OFFICIAL_SESSION",
        "corporate_action_rule": "RAW_PRICE_PLUS_SEPARATE_CASH_COMPONENT",
        "adjusted_price_double_count_guard": True,
        "rights_issue_policy": "BLOCK_UNTIL_EXERCISE_SALE_LAPSE_POLICY_FROZEN",
        "complex_action_policy": "BLOCK_UNTIL_RETURN_TREATMENT_FROZEN",
        "decision_id": "KU-BO-008-D01",
    }
    invalid = [key for key, value in expected.items() if payload.get(key) != value]
    if invalid:
        return (
            "INVALID",
            [
                "OUTCOME_SESSION_POLICY_CONTRACT_FIELDS_INVALID:"
                + ",".join(sorted(set(invalid)))
            ],
            {
                "component": "OUTCOME_SESSION_POLICY",
                "path": "outcome_session_policy.json",
                "sha256": _sha256(content),
            },
        )
    if payload.get("status") == "FROZEN":
        return (
            "INVALID",
            ["OUTCOME_SESSION_USER_DECISION_NOT_APPROVED:KU-BO-008-D01"],
            receipt,
        )
    if (
        payload.get("suspended_or_halted_rule") != "UNDECIDED"
        or payload.get("claim_boundary")
        != "OUTCOME_SESSION_POLICY_NOT_FROZEN"
    ):
        return (
            "INVALID",
            ["OUTCOME_SESSION_POLICY_UNFROZEN_FIELDS_INVALID"],
            {
                "component": "OUTCOME_SESSION_POLICY",
                "path": "outcome_session_policy.json",
                "sha256": _sha256(content),
            },
        )
    return (
        "UNFROZEN",
        ["OUTCOME_SESSION_POLICY_NOT_FROZEN"],
        {
            "component": "OUTCOME_SESSION_POLICY",
            "path": "outcome_session_policy.json",
            "sha256": _sha256(content),
        },
    )


def _claim_boundaries(
    audits: tuple[_ComponentAudit, ...],
    policy_status: str,
) -> list[str]:
    values = {
        "NAMED_FIVE_SECURITY_PILOT_IS_NOT_FULL_MARKET_COVERAGE",
        "NO_FORECAST_PROBABILITY_RECOMMENDATION_OR_ACCURACY_CLAIM",
        "NO_PROSPECTIVE_VALIDATION_CLAIM",
        "SOURCE_ID_OR_REVIEW_STATUS_IS_NOT_PROOF",
        "SYNTHETIC_OR_FIXTURE_EVIDENCE_CANNOT_PROMOTE_READINESS",
    }
    if policy_status != "FROZEN":
        values.add("OUTCOME_SESSION_POLICY_NOT_FROZEN")
    else:
        values.add("OUTCOME_SESSION_POLICY_FROZEN")
    if any(audit.evidence_classification != "PROVEN_REAL_EVIDENCE" for audit in audits):
        values.add("REAL_BASELINE_BACKTEST_READINESS_NOT_PROVEN")
    if any(audit.limitations for audit in audits):
        values.add("LEGACY_CLASSIFICATION_OR_RIGHTS_METADATA_CANNOT_BE_INFERRED")
    ca = next((item for item in audits if item.component == "CA_ENRICHMENT"), None)
    if ca is not None and ca.rows.get(
        "normalized/corporate_action_return_policy_queue.csv", []
    ):
        values.add("RIGHTS_OR_COMPLEX_ACTION_RETURN_POLICY_PENDING")
    return sorted(values)


def _claim_gate(
    audits: tuple[_ComponentAudit, ...],
    gates: list[dict[str, Any]],
    *,
    policy_status: str,
    policy_errors: list[str],
    policy_hash: dict[str, str] | None,
) -> dict[str, Any]:
    component_classification = _aggregate_classification(
        [audit.evidence_classification for audit in audits]
    )
    rights = all(audit.rights_compatible for audit in audits)
    prior_blocked = any(gate["status"] == "BLOCKED" for gate in gates)
    prior_partial = any(gate["status"] == "PARTIAL" for gate in gates)
    if policy_status == "INVALID" or prior_blocked:
        status = "BLOCKED"
    elif policy_status != "FROZEN" or prior_partial:
        status = "PARTIAL"
    elif component_classification != "PROVEN_REAL_EVIDENCE" or not rights:
        status = "PARTIAL"
    else:
        status = "PASS"
    classification = "BLOCKED" if status == "BLOCKED" else component_classification
    errors = list(policy_errors)
    if component_classification != "PROVEN_REAL_EVIDENCE":
        errors.append("ALL_COMPONENTS_ARE_NOT_PROVEN_REAL_EVIDENCE")
    if not rights:
        errors.append("ALL_COMPONENT_RIGHTS_ARE_NOT_RESEARCH_COMPATIBLE")
    if prior_blocked:
        errors.append("ONE_OR_MORE_CRITICAL_GATES_BLOCKED")
    elif prior_partial:
        errors.append("ONE_OR_MORE_CRITICAL_GATES_PARTIAL")
    hashes = [policy_hash] if policy_hash is not None else []
    return {
        "gate": "CLAIM_BOUNDARIES",
        "critical": True,
        "status": status,
        "evidence_classification": classification,
        "rights_compatible": rights,
        "errors": sorted(set(errors)),
        "hashes": hashes,
        "details": {
            "components": [audit.component for audit in audits],
            "checks": {
                "all_critical_gates_pass": (
                    "PASS" if not prior_blocked and not prior_partial else status
                ),
                "all_evidence_proven_real": (
                    "PASS"
                    if component_classification == "PROVEN_REAL_EVIDENCE"
                    else "PARTIAL"
                ),
                "outcome_session_policy": (
                    "PASS"
                    if policy_status == "FROZEN"
                    else "BLOCKED"
                    if policy_status == "INVALID"
                    else "PARTIAL"
                ),
                "rights_compatible": "PASS" if rights else "PARTIAL",
            },
            "metrics": {
                "blocked_prior_gate_count": sum(
                    gate["status"] == "BLOCKED" for gate in gates
                ),
                "partial_prior_gate_count": sum(
                    gate["status"] == "PARTIAL" for gate in gates
                ),
            },
            "concepts": _claim_boundaries(audits, policy_status),
        },
    }


def _component_packet(audit: _ComponentAudit) -> dict[str, Any]:
    return {
        "component": audit.component,
        "evidence_classification": audit.evidence_classification,
        "rights_compatible": audit.rights_compatible,
        "rights_statuses": list(audit.rights_statuses),
        "structural_errors": sorted(set(audit.structural_errors)),
        "limitations": sorted(set(audit.limitations)),
        "file_hashes": audit.hashes(),
    }


def _contains_absolute_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    if isinstance(value, str):
        return value.startswith("/") or bool(_WINDOWS_ABSOLUTE_RE.match(value))
    return False


_GATE_REPORT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "evidence_classification",
        "rights_compatible",
        "gates",
        "claim_boundaries",
    }
)
_GATE_FIELDS = frozenset(
    {
        "gate",
        "critical",
        "status",
        "evidence_classification",
        "rights_compatible",
        "errors",
        "hashes",
        "details",
    }
)
_GATE_DETAIL_FIELDS = frozenset({"components", "checks", "metrics", "concepts"})
_PACKET_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "evidence_classification",
        "rights_compatible",
        "outcome_session_policy_status",
        "components",
        "claim_boundaries",
    }
)
_PACKET_COMPONENT_FIELDS = frozenset(
    {
        "component",
        "evidence_classification",
        "rights_compatible",
        "rights_statuses",
        "structural_errors",
        "limitations",
        "file_hashes",
    }
)
_FINAL_MANIFEST_ARTIFACT_FIELDS = frozenset(
    {"path", "sha256", "size_bytes", "artifact_role", "evidence_classification"}
)
_FINAL_ARTIFACT_ROLES = {
    "data_foundation_packet.json": "FINAL_DATA_FOUNDATION_PACKET",
    "reports/data_foundation_gate_report.json": "FINAL_DATA_FOUNDATION_GATE_REPORT",
}
_READY_STATUS = "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST"


def _validate_canonical_strings(value: Any, *, field_name: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(set(value))
    ):
        raise ValueError(f"{field_name} must be a canonical unique string list")
    return value


def _validate_hash_receipts(value: Any, *, field_name: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    keys: list[tuple[str, str, str]] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"component", "path", "sha256"}
            or not isinstance(item.get("component"), str)
            or not item["component"]
            or not _HASH_RE.fullmatch(str(item.get("sha256", "")))
        ):
            raise ValueError(f"{field_name} contains an invalid hash receipt")
        _relative_artifact_path(item["path"], field_name=f"{field_name} path")
        keys.append((item["component"], item["path"], item["sha256"]))
    if keys != sorted(set(keys)):
        raise ValueError(f"{field_name} must be canonical and unique")
    return value


def _validate_gate_report(payload: dict[str, Any]) -> None:
    if set(payload) != _GATE_REPORT_FIELDS:
        raise ValueError("data-foundation gate report fields do not match the contract")
    if payload.get("schema_version") != DATA_FOUNDATION_RECONCILIATION_SCHEMA_VERSION:
        raise ValueError("data-foundation gate report schema_version is invalid")
    if payload.get("status") not in {
        "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST",
        "DATA_FOUNDATION_PARTIAL",
        "DATA_FOUNDATION_BLOCKED",
    }:
        raise ValueError("data-foundation gate report status is invalid")
    if payload.get("evidence_classification") not in EVIDENCE_CLASSIFICATIONS:
        raise ValueError("data-foundation gate report classification is invalid")
    if not isinstance(payload.get("rights_compatible"), bool):
        raise ValueError("data-foundation gate report rights_compatible is invalid")
    gates = payload.get("gates")
    if not isinstance(gates, list) or tuple(
        item.get("gate") if isinstance(item, dict) else None for item in gates
    ) != GATE_ORDER:
        raise ValueError("data-foundation gates must match the canonical order")
    for gate in gates:
        if set(gate) != _GATE_FIELDS:
            raise ValueError("data-foundation gate fields do not match the contract")
        if gate.get("critical") is not True:
            raise ValueError("every data-foundation gate must be critical")
        if gate.get("status") not in GATE_STATUSES:
            raise ValueError("data-foundation gate status is invalid")
        if gate.get("evidence_classification") not in EVIDENCE_CLASSIFICATIONS:
            raise ValueError("data-foundation gate classification is invalid")
        if not isinstance(gate.get("rights_compatible"), bool):
            raise ValueError("data-foundation gate rights_compatible is invalid")
        errors = _validate_canonical_strings(
            gate.get("errors"), field_name="data-foundation gate errors"
        )
        _validate_hash_receipts(
            gate.get("hashes"), field_name="data-foundation gate hashes"
        )
        details = gate.get("details")
        if not isinstance(details, dict) or set(details) != _GATE_DETAIL_FIELDS:
            raise ValueError("data-foundation gate details do not match the contract")
        components = details.get("components")
        if (
            not isinstance(components, list)
            or any(item not in _COMPONENT_ORDER for item in components)
            or len(components) != len(set(components))
        ):
            raise ValueError("data-foundation gate components are invalid")
        checks = details.get("checks")
        if (
            not isinstance(checks, dict)
            or any(
                not isinstance(key, str)
                or not key
                or value not in GATE_STATUSES
                for key, value in checks.items()
            )
        ):
            raise ValueError("data-foundation gate checks are invalid")
        metrics = details.get("metrics")
        if not isinstance(metrics, dict) or any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, (str, int, bool, type(None)))
            for key, value in metrics.items()
        ):
            raise ValueError("data-foundation gate metrics are invalid")
        concepts = details.get("concepts")
        if (
            not isinstance(concepts, list)
            or any(not isinstance(item, str) or not item for item in concepts)
            or len(concepts) != len(set(concepts))
        ):
            raise ValueError("data-foundation gate concepts are invalid")
        if gate["status"] == "PASS" and (
            gate["evidence_classification"] != "PROVEN_REAL_EVIDENCE"
            or gate["rights_compatible"] is not True
            or errors
            or any(value != "PASS" for value in checks.values())
        ):
            raise ValueError(
                "a PASS gate must be real, rights-compatible, error-free, and fully checked"
            )
        if gate["status"] == "BLOCKED" and gate["evidence_classification"] != "BLOCKED":
            raise ValueError("a BLOCKED gate must use BLOCKED evidence classification")
    boundaries = _validate_canonical_strings(
        payload.get("claim_boundaries"),
        field_name="data-foundation claim boundaries",
    )
    if gates[-1]["details"]["concepts"] != boundaries:
        raise ValueError("CLAIM_BOUNDARIES gate does not match the report boundaries")
    statuses = [gate["status"] for gate in gates]
    status = payload["status"]
    if status == "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST":
        if (
            any(value != "PASS" for value in statuses)
            or payload["evidence_classification"] != "PROVEN_REAL_EVIDENCE"
            or payload["rights_compatible"] is not True
        ):
            raise ValueError("READY report invariants are not satisfied")
    elif status == "DATA_FOUNDATION_BLOCKED":
        if "BLOCKED" not in statuses or payload["evidence_classification"] != "BLOCKED":
            raise ValueError("BLOCKED report invariants are not satisfied")
    elif (
        "BLOCKED" in statuses
        or "PARTIAL" not in statuses
        or payload["evidence_classification"] == "BLOCKED"
    ):
        raise ValueError("PARTIAL report invariants are not satisfied")
    prior_statuses = statuses[:-1]
    claim_status = statuses[-1]
    if "BLOCKED" in prior_statuses and claim_status != "BLOCKED":
        raise ValueError("CLAIM_BOUNDARIES must block after a blocked critical gate")
    if (
        "BLOCKED" not in prior_statuses
        and "PARTIAL" in prior_statuses
        and claim_status != "PARTIAL"
    ):
        raise ValueError("CLAIM_BOUNDARIES must remain partial after a partial gate")
    if _contains_absolute_path(payload):
        raise ValueError("data-foundation gate report contains an absolute path")


def _validate_packet_binding(
    packet: dict[str, Any], report: Mapping[str, Any]
) -> None:
    if set(packet) != _PACKET_FIELDS:
        raise ValueError("data-foundation packet fields do not match the contract")
    for field_name in (
        "schema_version",
        "status",
        "evidence_classification",
        "rights_compatible",
        "claim_boundaries",
    ):
        if packet.get(field_name) != report.get(field_name):
            raise ValueError(f"data-foundation packet {field_name} differs from report")
    if packet.get("outcome_session_policy_status") not in {
        "MISSING",
        "UNFROZEN",
        "INVALID",
        "FROZEN",
    }:
        raise ValueError("data-foundation packet policy status is invalid")
    components = packet.get("components")
    if not isinstance(components, list) or tuple(
        item.get("component") if isinstance(item, dict) else None
        for item in components
    ) != _COMPONENT_ORDER:
        raise ValueError("data-foundation packet components are not canonical")
    for component in components:
        if set(component) != _PACKET_COMPONENT_FIELDS:
            raise ValueError("data-foundation packet component fields are invalid")
        if component.get("evidence_classification") not in EVIDENCE_CLASSIFICATIONS:
            raise ValueError("data-foundation packet component classification is invalid")
        if not isinstance(component.get("rights_compatible"), bool):
            raise ValueError("data-foundation packet component rights are invalid")
        for field_name in ("rights_statuses", "structural_errors", "limitations"):
            _validate_canonical_strings(
                component.get(field_name),
                field_name=f"data-foundation packet component {field_name}",
            )
        _validate_hash_receipts(
            component.get("file_hashes"),
            field_name="data-foundation packet component file_hashes",
        )
    if _contains_absolute_path(packet):
        raise ValueError("data-foundation packet contains an absolute path")


def _require_independent_final_readiness_authority(
    report: Mapping[str, Any],
) -> None:
    """Keep a self-hashed final packet from serving as its own readiness authority.

    KU-BO does not yet define an independently authenticated final receipt or
    signature whose trust root is outside the mutable output directory.  Until
    that contract exists and is verified here, a persisted READY claim must fail
    closed even when its report, packet, and manifest hashes are self-consistent.
    """

    if report.get("status") == _READY_STATUS:
        raise ValueError(
            "READY_FINAL_AUTHORITY_RECEIPT_REQUIRED:"
            "self-hashed report, packet, and manifest are not an independent trust root"
        )


def build_data_foundation_packet(
    *,
    official_foundation_root: Path,
    status_history_root: Path,
    ca_enrichment_root: Path,
    research_price_history_root: Path,
    benchmark_root: Path,
    official_eod_root: Path,
    project_root: Path,
    output_root: Path,
    outcome_session_policy_path: Path | None = None,
) -> dict[str, Any]:
    """Rehash and reconcile the conventional KU-BO data-foundation outputs.

    Input paths are authority locations only and are deliberately absent from every
    emitted JSON artifact.  Readiness is derived from preserved bytes, normalized
    rows, and hash-bound manifest metadata; no caller readiness/classification
    boolean is accepted.
    """

    official = _audit_official_foundation(Path(official_foundation_root))
    status_history = _audit_status_history(Path(status_history_root))
    ca = _audit_ca_enrichment(Path(ca_enrichment_root))
    research = _audit_research_prices(Path(research_price_history_root))
    benchmark = _audit_benchmark(Path(benchmark_root))
    eod = _audit_official_eod(Path(official_eod_root))
    audits = (official, status_history, ca, research, benchmark, eod)
    _audit_real_evidence_authority(audits, project_root=Path(project_root))
    _verify_cross_component_receipts(official, status_history, benchmark, eod)

    gates = [
        _identity_gate(official),
        _calendar_gate(official),
        _status_history_gate(status_history),
        _price_denominator_gate(eod),
        _price_evidence_gate(eod, research),
        _corporate_action_gate(
            ca, official, eod, research, status_history, benchmark
        ),
        _benchmark_history_gate(benchmark),
        _benchmark_evidence_gate(benchmark),
        _market_totals_gate(eod),
        _query_gate(status_history, research, benchmark, eod),
        _secret_gate(Path(project_root)),
    ]
    policy_status, policy_errors, policy_hash = _policy_audit(
        Path(outcome_session_policy_path)
        if outcome_session_policy_path is not None
        else None,
        project_root=Path(project_root),
        authoritative_path=(
            Path(project_root) / "config" / "pilot" / "outcome_session_policy.json"
        ),
    )
    gates.append(
        _claim_gate(
            audits,
            gates,
            policy_status=policy_status,
            policy_errors=policy_errors,
            policy_hash=policy_hash,
        )
    )

    if tuple(gate["gate"] for gate in gates) != GATE_ORDER:
        raise AssertionError("internal gate order drift")
    component_classification = _aggregate_classification(
        [audit.evidence_classification for audit in audits]
    )
    rights_compatible = all(audit.rights_compatible for audit in audits)
    any_blocked = any(gate["status"] == "BLOCKED" for gate in gates)
    all_pass = all(gate["status"] == "PASS" for gate in gates)
    if any_blocked:
        status = "DATA_FOUNDATION_BLOCKED"
        classification = "BLOCKED"
    elif (
        all_pass
        and component_classification == "PROVEN_REAL_EVIDENCE"
        and rights_compatible
        and policy_status == "FROZEN"
    ):
        status = "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST"
        classification = "PROVEN_REAL_EVIDENCE"
    else:
        status = "DATA_FOUNDATION_PARTIAL"
        classification = component_classification

    boundaries = _claim_boundaries(audits, policy_status)
    gate_report = {
        "schema_version": DATA_FOUNDATION_RECONCILIATION_SCHEMA_VERSION,
        "status": status,
        "evidence_classification": classification,
        "rights_compatible": rights_compatible,
        "gates": gates,
        "claim_boundaries": boundaries,
    }
    _validate_gate_report(gate_report)

    packet = {
        "schema_version": DATA_FOUNDATION_RECONCILIATION_SCHEMA_VERSION,
        "status": status,
        "evidence_classification": classification,
        "rights_compatible": rights_compatible,
        "outcome_session_policy_status": policy_status,
        "components": [_component_packet(audit) for audit in audits],
        "claim_boundaries": boundaries,
    }
    if _contains_absolute_path(packet):
        raise AssertionError("internal packet contains an absolute path")

    output = prepare_output_root(Path(output_root), label="DATA_FOUNDATION_OUTPUT_ROOT")
    reports = output / "reports"
    reports.mkdir(parents=False, exist_ok=False)
    packet_bytes = canonical_json_bytes(packet)
    report_bytes = canonical_json_bytes(gate_report)
    (output / "data_foundation_packet.json").write_bytes(packet_bytes)
    (reports / "data_foundation_gate_report.json").write_bytes(report_bytes)
    manifest = {
        "schema_version": "3.0",
        "artifacts": [
            {
                "path": "data_foundation_packet.json",
                "sha256": _sha256(packet_bytes),
                "size_bytes": len(packet_bytes),
                "artifact_role": "FINAL_DATA_FOUNDATION_PACKET",
                "evidence_classification": classification,
            },
            {
                "path": "reports/data_foundation_gate_report.json",
                "sha256": _sha256(report_bytes),
                "size_bytes": len(report_bytes),
                "artifact_role": "FINAL_DATA_FOUNDATION_GATE_REPORT",
                "evidence_classification": classification,
            },
        ],
    }
    (output / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return gate_report


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(Path(os.path.abspath(left)))) == os.path.normcase(
        str(Path(os.path.abspath(right)))
    )


def _read_bound_data_foundation_output(
    report_path: Path,
    *,
    manifest_path: Path | None,
) -> dict[str, Any]:
    report = Path(os.path.abspath(report_path))
    manifest = (
        Path(os.path.abspath(manifest_path))
        if manifest_path is not None
        else report.parent.parent / "manifest.json"
    )
    output_root = require_real_directory(
        manifest.parent,
        field="DATA_FOUNDATION_OUTPUT_ROOT",
    )
    expected_manifest = output_root / "manifest.json"
    expected_report = output_root / "reports" / "data_foundation_gate_report.json"
    if not _same_path(manifest, expected_manifest):
        raise ValueError("data-foundation manifest must be at the output root")
    if not _same_path(report, expected_report):
        raise ValueError("gate report is outside the conventional data-foundation output")

    manifest_payload, manifest_bytes = load_strict_json_object(
        expected_manifest,
        field="DATA_FOUNDATION_FINAL_MANIFEST",
    )
    if manifest_bytes != canonical_json_bytes(manifest_payload):
        raise ValueError("data-foundation final manifest is not canonical JSON")
    if set(manifest_payload) != {"schema_version", "artifacts"}:
        raise ValueError("data-foundation final manifest fields are invalid")
    if manifest_payload.get("schema_version") != "3.0":
        raise ValueError("data-foundation final manifest schema_version is invalid")
    artifacts = manifest_payload.get("artifacts")
    if not isinstance(artifacts, list) or [
        item.get("path") if isinstance(item, dict) else None for item in artifacts
    ] != list(_FINAL_ARTIFACT_ROLES):
        raise ValueError("data-foundation final manifest artifact set is invalid")

    contents: dict[str, bytes] = {}
    classifications: dict[str, str] = {}
    for item in artifacts:
        if set(item) != _FINAL_MANIFEST_ARTIFACT_FIELDS:
            raise ValueError("data-foundation final manifest artifact fields are invalid")
        relative = _relative_artifact_path(
            item.get("path"),
            field_name="data-foundation final manifest artifact path",
        )
        if item.get("artifact_role") != _FINAL_ARTIFACT_ROLES[relative]:
            raise ValueError("data-foundation final manifest artifact role is invalid")
        declared_hash = item.get("sha256")
        if not isinstance(declared_hash, str) or not _HASH_RE.fullmatch(declared_hash):
            raise ValueError("data-foundation final manifest artifact hash is invalid")
        size_bytes = item.get("size_bytes")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError("data-foundation final manifest artifact size is invalid")
        classification = item.get("evidence_classification")
        if classification not in EVIDENCE_CLASSIFICATIONS:
            raise ValueError("data-foundation final manifest classification is invalid")
        content = safe_regular_file(
            output_root / PurePosixPath(relative),
            field=f"DATA_FOUNDATION_FINAL_ARTIFACT:{relative}",
        )
        if len(content) != size_bytes or _sha256(content) != declared_hash:
            raise ValueError(
                f"data-foundation final artifact hash or size mismatch:{relative}"
            )
        contents[relative] = content
        classifications[relative] = classification

    payload = strict_json_object(
        contents["reports/data_foundation_gate_report.json"],
        "DATA_FOUNDATION_GATE_REPORT",
    )
    if contents["reports/data_foundation_gate_report.json"] != canonical_json_bytes(
        payload
    ):
        raise ValueError("data-foundation gate report is not canonical JSON")
    _validate_gate_report(payload)
    packet = strict_json_object(
        contents["data_foundation_packet.json"],
        "DATA_FOUNDATION_PACKET",
    )
    if contents["data_foundation_packet.json"] != canonical_json_bytes(packet):
        raise ValueError("data-foundation packet is not canonical JSON")
    _validate_packet_binding(packet, payload)
    if any(value != payload["evidence_classification"] for value in classifications.values()):
        raise ValueError("data-foundation final manifest classification differs from report")
    _require_independent_final_readiness_authority(payload)
    return payload


def read_data_foundation_gate_report(
    path: Path,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Read a conventional final report only after rehashing its output manifest."""

    return _read_bound_data_foundation_output(
        Path(path),
        manifest_path=manifest_path,
    )


def render_data_foundation_gate_report(
    report: Mapping[str, Any],
) -> str:
    payload = dict(report)
    _validate_gate_report(payload)
    lines = [
        (
            f"{payload['status']} | evidence={payload['evidence_classification']} | "
            f"rights_compatible={str(payload['rights_compatible']).lower()}"
        )
    ]
    for gate in payload["gates"]:
        lines.append(
            f"{gate['gate']}: {gate['status']} [{gate['evidence_classification']}]"
        )
        for error in gate["errors"]:
            lines.append(f"  - {error}")
    lines.append("CLAIM_BOUNDARIES:")
    lines.extend(f"  - {value}" for value in payload["claim_boundaries"])
    return "\n".join(lines) + "\n"


def print_data_foundation_gate_report(
    path: Path,
    *,
    stream: TextIO | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    report = read_data_foundation_gate_report(path, manifest_path=manifest_path)
    rendered = render_data_foundation_gate_report(report)
    if stream is None:
        print(rendered, end="")
    else:
        stream.write(rendered)
    return report


__all__ = [
    "DATA_FOUNDATION_RECONCILIATION_SCHEMA_VERSION",
    "EVIDENCE_CLASSIFICATIONS",
    "GATE_ORDER",
    "build_data_foundation_packet",
    "print_data_foundation_gate_report",
    "read_data_foundation_gate_report",
    "render_data_foundation_gate_report",
]
