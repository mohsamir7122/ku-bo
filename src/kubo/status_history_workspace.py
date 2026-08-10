from __future__ import annotations

import csv
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from .hashing import canonical_json_bytes, sha256_bytes
from .strict import parse_iso_date


STATUS_HISTORY_MANIFEST_SCHEMA_VERSION = "1.0"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_UPSTREAM_STATUSES = frozenset(
    {
        "CURRENT_STATUS_AND_CA_SCHEDULE_READY",
        "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY",
    }
)
MAX_UPSTREAM_BYTES = 10 * 1024 * 1024
HISTORICAL_DISCLOSURES_URL = (
    "https://www.boursakuwait.com.kw/en/announcements/"
    "disclosures-and-announcements/historical-disclosures-and-announcements/"
)



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
        payload = os.read(descriptor, max_bytes + 1)
        if len(payload) > max_bytes:
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
            raise ValueError(f"{field} changed while being read")
        return payload
    finally:
        os.close(descriptor)



def _strict_json_object(content: bytes, field: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{field} contains duplicate key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"{field} contains non-finite JSON: {value}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{field} must be strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return payload



def _read_csv(content: bytes, field: str) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field} must be UTF-8 CSV") from exc
    reader = csv.DictReader(text.splitlines())
    headers = tuple(reader.fieldnames or ())
    required = {
        "security_code",
        "ticker",
        "status",
        "effective_from",
        "temporal_scope",
    }
    if not required.issubset(headers):
        raise ValueError(f"{field} lacks required current-status columns")
    rows = [
        {key: str(value or "").strip() for key, value in row.items()}
        for row in reader
    ]
    if not rows:
        raise ValueError(f"{field} must contain current status rows")
    return rows



def _safe_output_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.exists() and current.is_symlink():
            raise ValueError("output_root must not contain symlink components")
    if absolute.exists() or absolute.is_symlink():
        if absolute.is_symlink() or not absolute.is_dir():
            raise ValueError("output_root must be a real directory")
        if any(absolute.iterdir()):
            raise ValueError("refusing to overwrite a non-empty status-history workspace")
    else:
        absolute.mkdir(parents=True, exist_ok=False)
    return absolute



def _load_upstream(status_corporate_root: Path) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, str]]:
    root = Path(status_corporate_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("status_corporate_root must be a real directory")
    report_bytes = _safe_regular_file(
        root / "reports" / "status_corporate_import_report.json",
        field="upstream status/corporate report",
        max_bytes=MAX_UPSTREAM_BYTES,
    )
    report = _strict_json_object(report_bytes, "upstream status/corporate report")
    if report.get("status") not in _ALLOWED_UPSTREAM_STATUSES:
        raise ValueError("upstream status/corporate stage is not ready")
    status_bytes = _safe_regular_file(
        root / "normalized" / "security_status_evidence.csv",
        field="upstream security_status_evidence.csv",
        max_bytes=MAX_UPSTREAM_BYTES,
    )
    rows = _read_csv(status_bytes, "upstream security status evidence")
    snapshot_date = parse_iso_date(
        report.get("status_snapshot_effective_date"),
        "upstream status_snapshot_effective_date",
    )
    codes: set[str] = set()
    tickers: set[str] = set()
    for row in rows:
        code = row["security_code"]
        ticker = row["ticker"].upper()
        if not code or code in codes or not ticker or ticker in tickers:
            raise ValueError("upstream current status identities must be unique")
        if row["status"] not in {"TRADING", "SUSPENDED"}:
            raise ValueError("upstream current status must be TRADING or SUSPENDED")
        if row["temporal_scope"] != "CURRENT_SNAPSHOT_ONLY":
            raise ValueError("upstream status scope is not current snapshot only")
        if parse_iso_date(row["effective_from"], "effective_from") != snapshot_date:
            raise ValueError("upstream current status date does not match report")
        codes.add(code)
        tickers.add(ticker)
    hashes = {
        "report_sha256": sha256_bytes(report_bytes),
        "status_evidence_sha256": sha256_bytes(status_bytes),
    }
    return report, rows, hashes



def prepare_status_history_workspace(
    *,
    status_corporate_root: Path,
    output_root: Path,
    run_id: str,
    history_window_from: str,
    history_window_to: str,
    prepared_by: str = "",
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be a canonical path-safe identifier")
    window_from = parse_iso_date(history_window_from, "history_window_from")
    window_to = parse_iso_date(history_window_to, "history_window_to")
    if window_from > window_to:
        raise ValueError("status-history window is reversed")
    upstream_report, current_rows, hashes = _load_upstream(status_corporate_root)
    upstream_snapshot = parse_iso_date(
        upstream_report["status_snapshot_effective_date"],
        "upstream status_snapshot_effective_date",
    )
    if window_to != upstream_snapshot:
        raise ValueError(
            "history_window_to must equal the upstream current-status snapshot date"
        )
    root = _safe_output_root(output_root)
    query_dir = root / "raw_exports" / "queries"
    opening_dir = root / "raw_exports" / "opening_states"
    notice_dir = root / "raw_exports" / "notices"
    text_dir = root / "text_exports" / "notices"
    manifest_dir = root / "manifests"
    report_dir = root / "reports"
    for directory in (
        query_dir,
        opening_dir,
        notice_dir,
        text_dir,
        manifest_dir,
        root / "normalized",
        report_dir,
        root / "quarantine",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    queries: list[dict[str, Any]] = []
    opening_states: list[dict[str, Any]] = []
    for row in sorted(current_rows, key=lambda item: int(item["security_code"])):
        code = row["security_code"]
        ticker = row["ticker"].upper()
        query_id = f"historical-status:{code}:{window_from.isoformat()}:{window_to.isoformat()}"
        query_file = f"{ticker}.historical_disclosures.rendered.html"
        opening_file = f"{ticker}.opening_status.official"
        (query_dir / f"{query_file}.placeholder").write_text(
            "Replace with the exact rendered historical-disclosure result export for this security and window.\n"
            f"Security: {ticker} ({code})\n"
            "Record complete pagination, result count, SHA-256, and review status in the manifest.\n",
            encoding="utf-8",
        )
        (opening_dir / f"{opening_file}.placeholder").write_text(
            "Replace with exact official evidence establishing the security state at history_window_from.\n"
            "Do not infer the opening state from the current snapshot.\n",
            encoding="utf-8",
        )
        queries.append(
            {
                "query_id": query_id,
                "security_code": code,
                "ticker": ticker,
                "source_url": HISTORICAL_DISCLOSURES_URL,
                "raw_file_name": query_file,
                "raw_sha256": "",
                "pages_declared": "",
                "pages_received": "",
                "result_count_declared": "",
                "rows_normalized": "",
                "zero_result": False,
                "observed_at": "",
                "captured_by": prepared_by,
                "review_status": "PENDING",
                "review_notes": "",
            }
        )
        opening_states.append(
            {
                "security_code": code,
                "ticker": ticker,
                "status": "",
                "effective_date": window_from.isoformat(),
                "source_id": "boursa_historical_disclosures",
                "source_url": "",
                "raw_file_name": opening_file,
                "raw_sha256": "",
                "evidence_excerpt": "",
                "observed_at": "",
                "captured_by": prepared_by,
                "review_status": "PENDING",
                "review_notes": "",
            }
        )

    manifest = {
        "schema_version": STATUS_HISTORY_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "history_window_from": window_from.isoformat(),
        "history_window_to": window_to.isoformat(),
        "upstream": {
            "status": upstream_report["status"],
            "run_id": upstream_report.get("run_id"),
            "status_snapshot_effective_date": upstream_snapshot.isoformat(),
            **hashes,
        },
        "queries": queries,
        "opening_states": opening_states,
        "notices": [],
    }
    manifest_path = manifest_dir / "status_history_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    notice_template = {
        "notice_id": "replace-with-stable-id",
        "security_code": "",
        "ticker": "",
        "event_type": "SUSPEND_OR_RESUME_OR_DELIST_OR_RELIST",
        "effective_date": "YYYY-MM-DD",
        "published_date": "YYYY-MM-DD",
        "source_id": "boursa_historical_disclosures",
        "source_url": "",
        "raw_file_name": "notice.official",
        "raw_sha256": "",
        "text_file_name": "notice.txt",
        "text_sha256": "",
        "text_derivation": "OFFICIAL_HTML_VISIBLE_TEXT",
        "query_id": "",
        "classification_phrase": "exact phrase present in text export",
        "captured_at": "",
        "captured_by": prepared_by,
        "review_status": "PENDING",
        "review_notes": "",
    }
    (manifest_dir / "status_notice_template.json").write_bytes(
        canonical_json_bytes(notice_template)
    )
    checklist_lines = [
        "# Historical Suspension and Resumption Notice Checklist",
        "",
        "For every pilot security:",
        "",
        "- Capture the complete rendered historical-disclosure search result for the declared window.",
        "- Reconcile pages, result count, normalized notice count, and explicit zero result.",
        "- Preserve official evidence for the opening state at history_window_from; never copy the current state backward.",
        "- Add one manifest notice per SUSPEND, RESUME, DELIST, or RELIST event.",
        "- Preserve the exact notice bytes and a reviewed UTF-8 visible-text export.",
        "- Record an exact classification phrase that appears in the text export.",
        "- Keep effective dates at daily granularity; same-day conflicting transitions are rejected.",
        "- Final reconstructed state must reconcile to the upstream current snapshot at history_window_to.",
        "",
        "An empty query is valid only when the rendered result export, pagination, and declared zero count are all preserved and accepted.",
        "",
    ]
    checklist_path = report_dir / "status_history_checklist.md"
    checklist_path.write_text("\n".join(checklist_lines), encoding="utf-8")
    workspace_report = {
        "schema_version": "1.0",
        "status": "PASS",
        "workspace_kind": "HISTORICAL_STATUS_NOTICE_LEDGER",
        "run_id": run_id,
        "output_root": str(root),
        "security_count": len(current_rows),
        "history_window_from": window_from.isoformat(),
        "history_window_to": window_to.isoformat(),
        "manifest_path": str(manifest_path),
        "notice_template": str(
            manifest_dir / "status_notice_template.json"
        ),
        "checklist_path": str(checklist_path),
        "claim_boundaries": {
            "workspace_contains_official_evidence": False,
            "current_status_is_opening_status": False,
            "query_zero_result_without_rendered_receipt": False,
            "reviewed_text_export_is_original_notice": False,
            "status_history_ready": False,
            "backtest_ready": False,
        },
    }
    report_path = report_dir / "status_history_workspace_report.json"
    report_path.write_bytes(canonical_json_bytes(workspace_report))
    return workspace_report


__all__ = [
    "HISTORICAL_DISCLOSURES_URL",
    "STATUS_HISTORY_MANIFEST_SCHEMA_VERSION",
    "prepare_status_history_workspace",
]
