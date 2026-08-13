from __future__ import annotations

import json
import os
import re
import stat
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .atomic_output import run_atomic_output
from .hashing import canonical_json_bytes, sha256_bytes
from .identity import IdentityRecord, validate_security_master, validate_status_history
from .status_corporate_parsers import (
    CorporateActionScheduleRecord,
    parse_boursa_corporate_actions_html,
    parse_boursa_delisted_companies_html,
    parse_boursa_suspended_companies_html,
)
from .status_corporate_validation import (
    CORPORATE_ACTION_ENRICHMENT_HEADERS,
    CORPORATE_ACTION_SCHEDULE_HEADERS,
    DELISTING_ARCHIVE_HEADERS,
    QUERY_LEDGER_HEADERS,
    SECURITY_STATUS_EVIDENCE_HEADERS,
    validate_corporate_action_schedule_rows,
    validate_delisting_archive_rows,
    validate_security_status_evidence_rows,
    write_csv,
)
from .status_corporate_workspace import (
    STATUS_CORPORATE_ARTIFACT_SPECS,
    STATUS_CORPORATE_MANIFEST_SCHEMA_VERSION,
)
from .strict import parse_aware, parse_iso_date, require_sha256
from .tri_security_admission import (
    BoundaryAdmissionRequest,
    admit_boundary,
    build_boundary_operation_binding,
)


KUWAIT = ZoneInfo("Asia/Kuwait")
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024
MARKET_CORPORATE_ACTION_HEADERS = (
    "isin",
    "security_code",
    "ticker",
    "cum_date",
    "ex_date",
    "record_date",
    "payment_date",
    "raw_sha256",
    "source_url",
)


def _strict_json_object(content: bytes, field: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{field} contains non-finite JSON value: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{field} contains duplicate object key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{field} must be strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return payload


def _safe_regular_file(path: Path, *, field: str, max_bytes: int) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ValueError(f"{field} is missing or unreadable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{field} must not contain symlinks")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise ValueError(f"{field} cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{field} must be a regular file")
        if before.st_size > max_bytes:
            raise ValueError(f"{field} exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"{field} exceeds {max_bytes} bytes")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError(f"{field} changed while it was read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _prepare_output_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:-1]:
        current /= component
        if current.exists() and current.is_symlink():
            raise ValueError("output_root parent must not contain symlinks")
    if absolute.exists() or absolute.is_symlink():
        if absolute.is_symlink() or not absolute.is_dir():
            raise ValueError("output_root must be a real directory")
        if any(absolute.iterdir()):
            raise ValueError("output_root must be empty to preserve prior evidence")
    else:
        absolute.mkdir(parents=True, exist_ok=False)
    return absolute


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise ValueError(f"{field} must be a non-negative integer")
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _positive_int(value: Any, field: str) -> int:
    parsed = _nonnegative_int(value, field)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _artifact_spec_map() -> dict[str, dict[str, str]]:
    return {item["artifact_id"]: dict(item) for item in STATUS_CORPORATE_ARTIFACT_SPECS}


def _load_workspace_manifest(
    workspace: Path,
) -> tuple[dict[str, Any], bytes, dict[str, dict[str, Any]]]:
    path = workspace / "manifests" / "status_corporate_manifest.json"
    content = _safe_regular_file(
        path,
        field="status/corporate manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    payload = _strict_json_object(content, "status/corporate manifest")
    expected_top = {
        "schema_version",
        "run_id",
        "status_snapshot_effective_date",
        "corporate_action_window_from",
        "corporate_action_window_to",
        "corporate_action_query",
        "artifacts",
    }
    if set(payload) != expected_top:
        raise ValueError("status/corporate manifest has unknown or missing fields")
    if payload["schema_version"] != STATUS_CORPORATE_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported status/corporate manifest schema_version")
    run_id = str(payload["run_id"])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise ValueError("manifest run_id is invalid")
    snapshot_date = parse_iso_date(
        payload["status_snapshot_effective_date"],
        "status_snapshot_effective_date",
    )
    window_from = parse_iso_date(
        payload["corporate_action_window_from"],
        "corporate_action_window_from",
    )
    window_to = parse_iso_date(
        payload["corporate_action_window_to"],
        "corporate_action_window_to",
    )
    if window_from > window_to:
        raise ValueError("corporate-action window is reversed")

    query = payload["corporate_action_query"]
    expected_query = {
        "filter_applied",
        "pages_declared",
        "pages_received",
        "result_count_declared",
        "review_status",
        "review_notes",
    }
    if not isinstance(query, dict) or set(query) != expected_query:
        raise ValueError("corporate_action_query has unknown or missing fields")
    if query["filter_applied"] is not True:
        raise ValueError("corporate_action_query.filter_applied must be true")
    pages_declared = _positive_int(query["pages_declared"], "pages_declared")
    pages_received = _positive_int(query["pages_received"], "pages_received")
    if pages_received != pages_declared:
        raise ValueError("corporate-action pagination is incomplete")
    result_count = _nonnegative_int(
        query["result_count_declared"],
        "result_count_declared",
    )
    if query["review_status"] != "ACCEPTED":
        raise ValueError("corporate_action_query is not accepted")
    payload["status_snapshot_effective_date"] = snapshot_date
    payload["corporate_action_window_from"] = window_from
    payload["corporate_action_window_to"] = window_to
    payload["corporate_action_query"] = {
        **query,
        "pages_declared": pages_declared,
        "pages_received": pages_received,
        "result_count_declared": result_count,
    }

    rows = payload["artifacts"]
    specs = _artifact_spec_map()
    if not isinstance(rows, list) or len(rows) != len(specs):
        raise ValueError("manifest must contain every required status/corporate artifact")
    expected_fields = {
        "artifact_id",
        "source_id",
        "source_url",
        "file_name",
        "capture_mode",
        "purpose",
        "file_sha256",
        "observed_at",
        "captured_by",
        "review_status",
        "review_notes",
    }
    artifacts: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise ValueError(f"manifest artifact {index} has unknown or missing fields")
        artifact_id = str(row["artifact_id"])
        spec = specs.get(artifact_id)
        if spec is None or artifact_id in artifacts:
            raise ValueError(f"manifest artifact {index} has unknown or duplicate artifact_id")
        for field in (
            "source_id",
            "source_url",
            "file_name",
            "capture_mode",
            "purpose",
        ):
            if row[field] != spec[field]:
                raise ValueError(f"manifest {artifact_id}.{field} differs from source contract")
        digest = require_sha256(row["file_sha256"], f"{artifact_id}.file_sha256")
        observed = parse_aware(row["observed_at"], f"{artifact_id}.observed_at")
        if row["review_status"] != "ACCEPTED":
            raise ValueError(f"manifest artifact is not accepted: {artifact_id}")
        if not str(row["captured_by"]).strip():
            raise ValueError(f"manifest captured_by is required: {artifact_id}")
        artifacts[artifact_id] = {
            **row,
            "file_sha256": digest,
            "observed_datetime": observed,
        }
    observed_days = {
        item["observed_datetime"].astimezone(KUWAIT).date()
        for item in artifacts.values()
    }
    if observed_days != {snapshot_date}:
        raise ValueError(
            "all status/corporate artifacts must be observed on status_snapshot_effective_date in Asia/Kuwait"
        )
    return payload, content, artifacts


def _load_upstream_identity(
    official_root: Path,
    *,
    snapshot_date: date,
) -> tuple[list[IdentityRecord], str, dict[str, Any]]:
    root = Path(official_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("official_foundation_root must be a real directory")
    report_bytes = _safe_regular_file(
        root / "reports" / "official_foundation_import_report.json",
        field="upstream official foundation report",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    report = _strict_json_object(report_bytes, "upstream official foundation report")
    if report.get("status") != "CURRENT_IDENTITY_AND_CALENDAR_READY":
        raise ValueError("upstream official foundation is not ready")
    upstream_identity_date = parse_iso_date(
        report.get("identity_snapshot_effective_date"),
        "upstream identity_snapshot_effective_date",
    )
    if upstream_identity_date > snapshot_date:
        raise ValueError("status snapshot precedes the upstream identity snapshot")

    manifest_bytes = _safe_regular_file(
        root / "manifest.json",
        field="upstream evidence manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    manifest = _strict_json_object(manifest_bytes, "upstream evidence manifest")
    artifacts = manifest.get("artifacts")
    if manifest.get("schema_version") != "3.0" or not isinstance(artifacts, list):
        raise ValueError("upstream evidence manifest is invalid")
    manifest_hashes: set[str] = set()
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            raise ValueError(f"upstream artifact {index} is invalid")
        relative = Path(str(row.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError(f"upstream artifact {index} path is unsafe")
        raw_path = root / relative
        content = _safe_regular_file(
            raw_path,
            field=f"upstream artifact {index}",
            max_bytes=MAX_ARTIFACT_BYTES,
        )
        digest = require_sha256(row.get("sha256"), f"upstream artifact {index}.sha256")
        if sha256_bytes(content) != digest:
            raise ValueError(f"upstream artifact {index} hash mismatch")
        manifest_hashes.add(digest)

    security_master_path = root / "normalized" / "security_master.csv"
    security_master_bytes = _safe_regular_file(
        security_master_path,
        field="upstream security_master.csv",
        max_bytes=MAX_ARTIFACT_BYTES,
    )
    identities, errors = validate_security_master(
        security_master_path,
        manifest_hashes=frozenset(manifest_hashes),
    )
    if errors or not identities:
        raise ValueError("upstream security master is invalid: " + ";".join(errors))
    active = [item for item in identities if item.active_on(snapshot_date)]
    if not active:
        raise ValueError("upstream security master has no identity active at status snapshot")
    security_master_sha256 = sha256_bytes(security_master_bytes)
    receipt = {
        "status": report["status"],
        "run_id": report.get("run_id"),
        "identity_snapshot_effective_date": upstream_identity_date.isoformat(),
        "security_master_sha256": security_master_sha256,
        "evidence_manifest_sha256": sha256_bytes(manifest_bytes),
        "active_security_count": len(active),
    }
    return active, security_master_sha256, receipt


def _action_dates(record: CorporateActionScheduleRecord) -> list[date]:
    result = [record.cum_date, record.ex_date, record.record_date]
    if record.payment_date is not None:
        result.append(record.payment_date)
    return result


def _action_in_window(
    record: CorporateActionScheduleRecord,
    window_from: date,
    window_to: date,
) -> bool:
    values = _action_dates(record)
    return not (max(values) < window_from or min(values) > window_to)


def _stable_action_id(record: CorporateActionScheduleRecord, raw_sha256: str) -> str:
    identity = "\0".join(
        (
            record.security_code,
            record.isin,
            record.cum_date.isoformat(),
            record.ex_date.isoformat(),
            record.record_date.isoformat(),
            "" if record.payment_date is None else record.payment_date.isoformat(),
            raw_sha256,
        )
    ).encode("utf-8")
    return "ca-schedule-" + sha256_bytes(identity)[:24]


def _import_status_corporate_unchecked(
    *,
    config_dir: Path,
    official_foundation_root: Path,
    workspace: Path,
    output_root: Path,
    logical_output_root: Path | None = None,
) -> dict[str, Any]:
    del config_dir  # Identity is taken only from the validated upstream official packet.
    workspace = Path(workspace)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("workspace must be a real directory")
    output = _prepare_output_root(Path(output_root))
    logical_output = (
        Path(os.path.abspath(logical_output_root))
        if logical_output_root is not None
        else output
    )
    raw_output = output / "raw"
    normalized_output = output / "normalized"
    report_output = output / "reports"
    manifest_output = output / "manifests"
    for directory in (raw_output, normalized_output, report_output, manifest_output):
        directory.mkdir(parents=True, exist_ok=True)

    manifest, manifest_bytes, artifact_rows = _load_workspace_manifest(workspace)
    snapshot_date: date = manifest["status_snapshot_effective_date"]
    window_from: date = manifest["corporate_action_window_from"]
    window_to: date = manifest["corporate_action_window_to"]
    identities, identity_snapshot_sha256, upstream_receipt = _load_upstream_identity(
        official_foundation_root,
        snapshot_date=snapshot_date,
    )
    expected_codes = frozenset(item.security_code for item in identities)
    identity_by_code = {item.security_code: item for item in identities}
    expected_identity = {
        item.security_code: (item.ticker, str(item.isin or "")) for item in identities
    }

    raw_input = workspace / "raw_exports" / "boursa"
    contents: dict[str, bytes] = {}
    manifest_artifacts: list[dict[str, Any]] = []
    for artifact_id, row in sorted(artifact_rows.items()):
        source_path = raw_input / row["file_name"]
        content = _safe_regular_file(
            source_path,
            field=f"status/corporate artifact {artifact_id}",
            max_bytes=MAX_ARTIFACT_BYTES,
        )
        digest = sha256_bytes(content)
        if digest != row["file_sha256"]:
            raise ValueError(f"status/corporate artifact hash mismatch: {artifact_id}")
        preserved = raw_output / row["file_name"]
        preserved.write_bytes(content)
        contents[artifact_id] = content
        manifest_artifacts.append(
            {
                "path": preserved.relative_to(output).as_posix(),
                "sha256": digest,
                "size_bytes": len(content),
                "source_id": row["source_id"],
                "source_url": row["source_url"],
                "observed_at": row["observed_datetime"].isoformat(),
                "capture_kind": "USER_EXPORT",
                "artifact_role": artifact_id.upper(),
            }
        )
    hashes = {
        item["artifact_role"].lower(): item["sha256"] for item in manifest_artifacts
    }
    urls = {
        artifact_id: artifact_rows[artifact_id]["source_url"]
        for artifact_id in artifact_rows
    }
    manifest_hashes = frozenset(item["sha256"] for item in manifest_artifacts)

    suspended = parse_boursa_suspended_companies_html(contents["suspended_companies"])
    delisted = parse_boursa_delisted_companies_html(contents["delisted_companies"])
    suspended_by_code = {item.security_code: item for item in suspended}
    delisted_by_code = {item.security_code: item for item in delisted}
    status_conflicts: list[str] = []
    for code, identity in identity_by_code.items():
        suspended_item = suspended_by_code.get(code)
        if suspended_item is not None and suspended_item.ticker != identity.ticker:
            status_conflicts.append(f"SUSPENDED_TICKER_CONFLICT:{code}")
        delisted_item = delisted_by_code.get(code)
        if delisted_item is not None and delisted_item.delisting_date <= snapshot_date:
            status_conflicts.append(f"CURRENT_IDENTITY_APPEARS_DELISTED:{code}")

    status_rows: list[dict[str, Any]] = []
    for identity in sorted(identities, key=lambda item: int(item.security_code)):
        is_suspended = identity.security_code in suspended_by_code
        status = "SUSPENDED" if is_suspended else "TRADING"
        reason = (
            "PRESENT_IN_CURRENT_SUSPENDED_TABLE"
            if is_suspended
            else "ABSENT_FROM_COMPLETE_SUSPENDED_TABLE"
        )
        status_rows.append(
            {
                "security_code": identity.security_code,
                "ticker": identity.ticker,
                "board": "cash",
                "status": status,
                "effective_from": snapshot_date.isoformat(),
                "effective_to": "",
                "reason_code": reason,
                "notice_id": (
                    f"status-snapshot:{snapshot_date.isoformat()}:"
                    f"{identity.security_code}:{status.lower()}"
                ),
                "raw_sha256": hashes["suspended_companies"],
                "identity_snapshot_sha256": identity_snapshot_sha256,
                "temporal_scope": "CURRENT_SNAPSHOT_ONLY",
                "source_url": urls["suspended_companies"],
            }
        )
    status_path = normalized_output / "security_status_evidence.csv"
    write_csv(status_path, SECURITY_STATUS_EVIDENCE_HEADERS, status_rows)
    _, structural_status_errors = validate_status_history(
        status_path,
        manifest_hashes=manifest_hashes,
        known_codes=expected_codes,
    )
    status_report = validate_security_status_evidence_rows(
        status_rows,
        expected_codes=expected_codes,
        suspended_codes=frozenset(suspended_by_code),
        manifest_hashes=manifest_hashes,
        identity_snapshot_sha256=identity_snapshot_sha256,
        snapshot_date=snapshot_date,
    )
    if structural_status_errors or status_conflicts:
        status_report["status"] = "BLOCKED"
        status_report["errors"] = sorted(
            set(
                [
                    *status_report["errors"],
                    *structural_status_errors,
                    *status_conflicts,
                ]
            )
        )
    status_report["market_suspended_count"] = len(suspended)
    status_report["pilot_suspended_count"] = sum(
        item.security_code in expected_codes for item in suspended
    )
    status_report["suspended_zero_result"] = len(suspended) == 0

    delisting_rows = [
        {
            "security_code": item.security_code,
            "ticker": item.ticker,
            "name": item.name,
            "sector": item.sector,
            "market_segment": item.market_segment,
            "delisting_date": item.delisting_date.isoformat(),
            "raw_sha256": hashes["delisted_companies"],
            "source_url": urls["delisted_companies"],
        }
        for item in delisted
    ]
    delisting_path = normalized_output / "delisting_archive.csv"
    write_csv(delisting_path, DELISTING_ARCHIVE_HEADERS, delisting_rows)
    delisting_report = validate_delisting_archive_rows(
        delisting_rows,
        manifest_hashes=manifest_hashes,
        snapshot_date=snapshot_date,
    )
    delisting_report["pilot_delisted_count"] = sum(
        item.security_code in expected_codes for item in delisted
    )

    market_actions = parse_boursa_corporate_actions_html(contents["corporate_actions"])
    query = manifest["corporate_action_query"]
    query_id = (
        f"corporate-actions:{window_from.isoformat()}:{window_to.isoformat()}:"
        f"{hashes['corporate_actions'][:12]}"
    )
    query_errors: list[str] = []
    if len(market_actions) != query["result_count_declared"]:
        query_errors.append(
            "CORPORATE_ACTION_RESULT_COUNT_MISMATCH:"
            f"declared={query['result_count_declared']}:parsed={len(market_actions)}"
        )
    outside_window = [
        item for item in market_actions if not _action_in_window(item, window_from, window_to)
    ]
    if outside_window:
        query_errors.append(
            f"CORPORATE_ACTION_ROWS_OUTSIDE_DECLARED_WINDOW:{len(outside_window)}"
        )

    market_action_rows = [
        {
            "isin": item.isin,
            "security_code": item.security_code,
            "ticker": item.ticker,
            "cum_date": item.cum_date.isoformat(),
            "ex_date": item.ex_date.isoformat(),
            "record_date": item.record_date.isoformat(),
            "payment_date": (
                "" if item.payment_date is None else item.payment_date.isoformat()
            ),
            "raw_sha256": hashes["corporate_actions"],
            "source_url": urls["corporate_actions"],
        }
        for item in market_actions
    ]
    market_action_path = normalized_output / "corporate_action_market_rows.csv"
    write_csv(market_action_path, MARKET_CORPORATE_ACTION_HEADERS, market_action_rows)

    pilot_actions = [item for item in market_actions if item.security_code in expected_codes]
    action_rows: list[dict[str, Any]] = []
    enrichment_rows: list[dict[str, Any]] = []
    for item in pilot_actions:
        action_id = _stable_action_id(item, hashes["corporate_actions"])
        action_rows.append(
            {
                "security_code": item.security_code,
                "ticker": item.ticker,
                "isin": item.isin,
                "action_id": action_id,
                "cum_date": item.cum_date.isoformat(),
                "ex_date": item.ex_date.isoformat(),
                "record_date": item.record_date.isoformat(),
                "payment_date": (
                    "" if item.payment_date is None else item.payment_date.isoformat()
                ),
                "action_type": "UNCLASSIFIED_ENTITLEMENT",
                "adjustment_factor": "",
                "factor_status": "pending",
                "raw_sha256": hashes["corporate_actions"],
                "query_id": query_id,
                "coverage_scope": "OFFICIAL_SCHEDULE_DATES_ONLY",
                "source_url": urls["corporate_actions"],
            }
        )
        enrichment_rows.append(
            {
                "action_id": action_id,
                "security_code": item.security_code,
                "ticker": item.ticker,
                "ex_date": item.ex_date.isoformat(),
                "required_enrichment": (
                    "OFFICIAL_DISCLOSURE_ACTION_TYPE_AMOUNT_AND_ADJUSTMENT_FACTOR"
                ),
                "disclosure_url": "",
                "disclosure_raw_sha256": "",
                "review_status": "PENDING",
                "review_notes": (
                    "Schedule dates are official; action type, amount, and factor remain unproven."
                ),
            }
        )
    action_path = normalized_output / "corporate_action_schedule.csv"
    write_csv(action_path, CORPORATE_ACTION_SCHEDULE_HEADERS, action_rows)
    enrichment_path = normalized_output / "corporate_action_enrichment_queue.csv"
    write_csv(
        enrichment_path,
        CORPORATE_ACTION_ENRICHMENT_HEADERS,
        enrichment_rows,
    )
    action_report = validate_corporate_action_schedule_rows(
        action_rows,
        expected_identity=expected_identity,
        manifest_hashes=manifest_hashes,
        query_id=query_id,
        action_window_from=window_from,
        action_window_to=window_to,
    )
    if query_errors:
        action_report["status"] = "BLOCKED"
        action_report["errors"] = sorted(
            set([*action_report["errors"], *query_errors])
        )
    action_report.update(
        {
            "market_rows": len(market_actions),
            "pilot_rows": len(pilot_actions),
            "query_id": query_id,
            "query_filter_applied": True,
            "query_pages_declared": query["pages_declared"],
            "query_pages_received": query["pages_received"],
            "query_result_count_declared": query["result_count_declared"],
            "query_completeness": "OPERATOR_ATTESTED_RENDERED_PAGE_RECONCILED",
            "window_semantics": "PAGE_FILTER_ATTESTED_DATES_INTERSECT_WINDOW",
        }
    )

    query_rows = [
        {
            "query_id": query_id,
            "dataset": "corporate_action_market_schedule",
            "window_from": window_from.isoformat(),
            "window_to": window_to.isoformat(),
            "pages_declared": query["pages_declared"],
            "pages_received": query["pages_received"],
            "result_count_declared": query["result_count_declared"],
            "rows_normalized": len(market_action_rows),
            "zero_result": "true" if not market_action_rows else "false",
            "raw_sha256": hashes["corporate_actions"],
        }
    ]
    query_path = manifest_output / "query_ledger.csv"
    write_csv(query_path, QUERY_LEDGER_HEADERS, query_rows)

    evidence_manifest = {
        "schema_version": "3.0",
        "artifacts": manifest_artifacts,
    }
    (output / "manifest.json").write_bytes(canonical_json_bytes(evidence_manifest))
    (output / "status_corporate_manifest.json").write_bytes(manifest_bytes)
    (output / "upstream_identity_receipt.json").write_bytes(
        canonical_json_bytes(upstream_receipt)
    )
    (report_output / "security_status_report.json").write_bytes(
        canonical_json_bytes(status_report)
    )
    (report_output / "delisting_archive_report.json").write_bytes(
        canonical_json_bytes(delisting_report)
    )
    (report_output / "corporate_action_schedule_report.json").write_bytes(
        canonical_json_bytes(action_report)
    )

    status_ok = (
        status_report["status"] == "PASS"
        and delisting_report["status"] == "PASS"
    )
    action_ok = action_report["status"] == "PASS"
    if status_ok and action_ok:
        status = (
            "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY"
            if not pilot_actions
            else "CURRENT_STATUS_AND_CA_SCHEDULE_READY"
        )
    elif status_ok or action_ok:
        status = "PARTIAL"
    else:
        status = "BLOCKED"
    report = {
        "schema_version": "1.0",
        "status": status,
        "run_id": manifest["run_id"],
        "output_root": str(logical_output),
        "status_snapshot_effective_date": snapshot_date.isoformat(),
        "corporate_action_window_from": window_from.isoformat(),
        "corporate_action_window_to": window_to.isoformat(),
        "upstream_identity_receipt": str(
            logical_output / "upstream_identity_receipt.json"
        ),
        "security_status_evidence": str(
            logical_output / "normalized" / "security_status_evidence.csv"
        ),
        "delisting_archive": str(
            logical_output / "normalized" / "delisting_archive.csv"
        ),
        "corporate_action_market_rows": str(
            logical_output / "normalized" / "corporate_action_market_rows.csv"
        ),
        "corporate_action_schedule": str(
            logical_output / "normalized" / "corporate_action_schedule.csv"
        ),
        "corporate_action_enrichment_queue": str(
            logical_output
            / "normalized"
            / "corporate_action_enrichment_queue.csv"
        ),
        "query_ledger": str(
            logical_output / "manifests" / "query_ledger.csv"
        ),
        "security_status_report": str(
            logical_output / "reports" / "security_status_report.json"
        ),
        "delisting_archive_report": str(
            logical_output / "reports" / "delisting_archive_report.json"
        ),
        "corporate_action_schedule_report": str(
            logical_output / "reports" / "corporate_action_schedule_report.json"
        ),
        "security_status": status_report["status"],
        "corporate_action_schedule_status": action_report["status"],
        "pilot_corporate_action_rows": len(pilot_actions),
        "pending_corporate_action_factor_rows": action_report[
            "pending_factor_rows"
        ],
        "remaining_gates": [
            "HISTORICAL_SUSPENSION_AND_RESUMPTION_NOTICES",
            "CORPORATE_ACTION_DISCLOSURE_ENRICHMENT",
            "CORPORATE_ACTION_ADJUSTMENT_FACTORS",
            "BENCHMARK_HISTORY",
            "OFFICIAL_COMPLETE_DAILY_EOD",
        ],
        "claim_boundaries": {
            "current_status_is_status_history": False,
            "absence_from_suspended_snapshot_proves_past_trading": False,
            "delisting_archive_proves_all_suspension_intervals": False,
            "corporate_action_schedule_contains_action_type": False,
            "corporate_action_schedule_contains_amount": False,
            "corporate_action_factor_ledger_ready": action_report[
                "corporate_action_factor_ledger_ready"
            ],
            "query_receipt_is_official_market_fact": False,
            "security_status_history_ready": False,
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }
    report_path = report_output / "status_corporate_import_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


def import_status_corporate(
    *,
    config_dir: Path,
    official_foundation_root: Path,
    workspace: Path,
    output_root: Path,
    admission_request: BoundaryAdmissionRequest,
) -> dict[str, Any]:
    target = Path(os.path.abspath(output_root))
    operation_binding = build_boundary_operation_binding(
        "import_status_corporate",
        decision_at=admission_request.decision_at,
    )
    token = admit_boundary(
        admission_request,
        boundary_id="import_status_corporate",
        output_root=target,
        boundary_inputs={
            "official_foundation_root": official_foundation_root,
            "workspace": workspace,
        },
        operation_binding=operation_binding,
    )

    def worker(staging: Path) -> dict[str, Any]:
        report = _import_status_corporate_unchecked(
            config_dir=config_dir,
            official_foundation_root=official_foundation_root,
            workspace=workspace,
            output_root=staging,
            logical_output_root=target,
        )
        token.materialize_receipt(staging)
        token.materialize_lineage(staging)
        return report

    return run_atomic_output(
        target,
        worker,
        before_commit=lambda _staging: token.revalidate_before_commit(),
    )


__all__ = [
    "MARKET_CORPORATE_ACTION_HEADERS",
    "import_status_corporate",
]
