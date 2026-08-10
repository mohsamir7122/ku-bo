from __future__ import annotations

import csv
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from .hashing import canonical_json_bytes, sha256_bytes


CA_ENRICHMENT_MANIFEST_SCHEMA_VERSION = "1.0"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_UPSTREAM_STATUSES = frozenset(
    {
        "CURRENT_STATUS_AND_CA_SCHEDULE_READY",
        "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY",
    }
)
MAX_UPSTREAM_FILE_BYTES = 10 * 1024 * 1024



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



def _read_csv(content: bytes, field: str) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field} must be UTF-8 CSV") from exc
    reader = csv.DictReader(text.splitlines())
    headers = tuple(reader.fieldnames or ())
    if not headers or len(headers) != len(set(headers)):
        raise ValueError(f"{field} has missing or duplicate headers")
    return headers, [
        {key: str(value or "").strip() for key, value in row.items()}
        for row in reader
    ]



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
            raise ValueError("refusing to overwrite a non-empty enrichment workspace")
    else:
        absolute.mkdir(parents=True, exist_ok=False)
    return absolute



def _load_upstream(status_corporate_root: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
    root = Path(status_corporate_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("status_corporate_root must be a real directory")
    report_bytes = _safe_regular_file(
        root / "reports" / "status_corporate_import_report.json",
        field="upstream status/corporate report",
        max_bytes=MAX_UPSTREAM_FILE_BYTES,
    )
    report = _strict_json_object(report_bytes, "upstream status/corporate report")
    if report.get("status") not in _ALLOWED_UPSTREAM_STATUSES:
        raise ValueError("upstream status/corporate stage is not ready")

    schedule_bytes = _safe_regular_file(
        root / "normalized" / "corporate_action_schedule.csv",
        field="upstream corporate_action_schedule.csv",
        max_bytes=MAX_UPSTREAM_FILE_BYTES,
    )
    queue_bytes = _safe_regular_file(
        root / "normalized" / "corporate_action_enrichment_queue.csv",
        field="upstream corporate_action_enrichment_queue.csv",
        max_bytes=MAX_UPSTREAM_FILE_BYTES,
    )
    schedule_headers, schedule_rows = _read_csv(schedule_bytes, "corporate action schedule")
    queue_headers, queue_rows = _read_csv(queue_bytes, "corporate action enrichment queue")
    required_schedule = {
        "security_code",
        "ticker",
        "isin",
        "action_id",
        "cum_date",
        "ex_date",
        "record_date",
        "payment_date",
        "action_type",
        "adjustment_factor",
        "factor_status",
        "raw_sha256",
        "query_id",
        "coverage_scope",
        "source_url",
    }
    required_queue = {
        "action_id",
        "security_code",
        "ticker",
        "ex_date",
        "required_enrichment",
        "disclosure_url",
        "disclosure_raw_sha256",
        "review_status",
        "review_notes",
    }
    if not required_schedule.issubset(schedule_headers):
        raise ValueError("upstream corporate-action schedule contract is incomplete")
    if not required_queue.issubset(queue_headers):
        raise ValueError("upstream enrichment queue contract is incomplete")
    schedule_by_id = {row["action_id"]: row for row in schedule_rows}
    queue_by_id = {row["action_id"]: row for row in queue_rows}
    if len(schedule_by_id) != len(schedule_rows) or len(queue_by_id) != len(queue_rows):
        raise ValueError("upstream action IDs must be unique")
    if set(schedule_by_id) != set(queue_by_id):
        raise ValueError("upstream schedule and enrichment queue action sets differ")
    for action_id, schedule in schedule_by_id.items():
        queue = queue_by_id[action_id]
        for field in ("security_code", "ticker", "ex_date"):
            if schedule[field] != queue[field]:
                raise ValueError(f"upstream enrichment identity mismatch: {action_id}:{field}")
        if schedule["factor_status"] != "pending" or schedule["adjustment_factor"]:
            raise ValueError(f"upstream action is not pending enrichment: {action_id}")
    hashes = {
        "report_sha256": sha256_bytes(report_bytes),
        "schedule_sha256": sha256_bytes(schedule_bytes),
        "enrichment_queue_sha256": sha256_bytes(queue_bytes),
    }
    return report, schedule_rows, queue_rows, hashes



def prepare_ca_enrichment_workspace(
    *,
    status_corporate_root: Path,
    output_root: Path,
    run_id: str,
    prepared_by: str = "",
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be a canonical path-safe identifier")
    report, schedule_rows, queue_rows, hashes = _load_upstream(
        status_corporate_root
    )
    root = _safe_output_root(output_root)
    raw_disclosures = root / "raw_exports" / "disclosures"
    text_disclosures = root / "text_exports" / "disclosures"
    raw_prices = root / "raw_exports" / "reference_prices"
    manifest_dir = root / "manifests"
    report_dir = root / "reports"
    for directory in (
        raw_disclosures,
        text_disclosures,
        raw_prices,
        manifest_dir,
        root / "normalized",
        report_dir,
        root / "quarantine",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    queue_by_id = {row["action_id"]: row for row in queue_rows}
    actions: list[dict[str, Any]] = []
    for schedule in sorted(schedule_rows, key=lambda row: (row["ex_date"], row["security_code"], row["action_id"])):
        action_id = schedule["action_id"]
        queue = queue_by_id[action_id]
        raw_name = f"{action_id}.official"
        text_name = f"{action_id}.txt"
        price_name = f"{action_id}.previous_close.official"
        (raw_disclosures / f"{raw_name}.placeholder").write_text(
            "Replace this placeholder with the exact official disclosure bytes from Boursa Kuwait, iFSAH, or CMA.\n"
            f"Action ID: {action_id}\n"
            "Do not edit the official bytes. Record SHA-256 and source metadata in the manifest.\n",
            encoding="utf-8",
        )
        (text_disclosures / f"{text_name}.placeholder").write_text(
            "Replace with a UTF-8 visible-text export derived from the official disclosure.\n"
            "The manifest must identify the derivation mode and exact evidence phrases.\n",
            encoding="utf-8",
        )
        (raw_prices / f"{price_name}.placeholder").write_text(
            "Replace with the exact official previous-close evidence used by the calculation.\n"
            "The evidence excerpt in the manifest must occur in these bytes.\n",
            encoding="utf-8",
        )
        schedule_row_sha256 = sha256_bytes(canonical_json_bytes(schedule))
        actions.append(
            {
                "action_id": action_id,
                "security_code": schedule["security_code"],
                "ticker": schedule["ticker"],
                "isin": schedule["isin"],
                "cum_date": schedule["cum_date"],
                "ex_date": schedule["ex_date"],
                "record_date": schedule["record_date"],
                "payment_date": schedule["payment_date"],
                "schedule_row_sha256": schedule_row_sha256,
                "required_enrichment": queue["required_enrichment"],
                "disclosure": {
                    "source_url": "",
                    "raw_file_name": raw_name,
                    "raw_sha256": "",
                    "text_file_name": text_name,
                    "text_sha256": "",
                    "text_derivation": "",
                    "published_at": "",
                    "captured_at": "",
                    "captured_by": prepared_by,
                    "evidence_phrases": [],
                    "review_status": "PENDING",
                    "review_notes": "",
                },
                "price_reference": {
                    "source_url": "",
                    "raw_file_name": price_name,
                    "raw_sha256": "",
                    "trade_date": "",
                    "previous_close_fils": "",
                    "evidence_excerpt": "",
                    "captured_at": "",
                    "captured_by": prepared_by,
                    "review_status": "PENDING",
                    "review_notes": "",
                },
                "terms": {
                    "action_type": "OTHER",
                    "formula_mode": "NO_AUTOMATIC_FORMULA",
                    "previous_close_fils": "",
                    "cash_per_share_fils": "",
                    "new_shares_per_old_share": "",
                    "rights_new_shares_per_old_share": "",
                    "subscription_price_fils": "",
                    "official_reference_price_fils": "",
                    "official_factor": "",
                    "official_position_quantity_multiplier": "",
                    "fractional_entitlement_policy": "UNKNOWN",
                    "formula_notes": "",
                },
            }
        )

    manifest = {
        "schema_version": CA_ENRICHMENT_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "upstream": {
            "status": report["status"],
            "run_id": report.get("run_id"),
            **hashes,
        },
        "actions": actions,
    }
    manifest_path = manifest_dir / "ca_enrichment_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    checklist_lines = [
        "# Corporate Action Disclosure Enrichment Checklist",
        "",
        "The schedule dates are already official. This workspace adds action type, terms, and narrowly defined adjustment calculations.",
        "",
        "For every action:",
        "",
        "- Preserve the exact disclosure bytes from Boursa Kuwait, iFSAH, or CMA.",
        "- Preserve a UTF-8 visible-text export and list exact evidence phrases that occur in it.",
        "- Preserve official previous-close evidence when a formula needs it.",
        "- Use `OFFICIAL_FACTOR` or `OFFICIAL_REFERENCE_PRICE` only when the official evidence explicitly supplies that value.",
        "- Use `REPRODUCIBLE_MECHANICAL` only for supported formula types and complete official terms.",
        "- Keep `NO_AUTOMATIC_FORMULA` for capital reductions, mergers, ambiguous rights terms, or any incomplete disclosure.",
        "- Never use a Search Snippet, manually typed market price, or secondary website as official evidence.",
        "",
        "Important distinction:",
        "",
        "- `reference_price_factor` and `historical_continuity_factor` are not automatically the same as the return-engine multiplier.",
        "- Cash dividends use raw prices plus a separate cash component in the return engine.",
        "- Rights issues remain return-policy blocked until exercise, sale, or lapse treatment is frozen.",
        "",
    ]
    checklist_path = report_dir / "ca_enrichment_checklist.md"
    checklist_path.write_text("\n".join(checklist_lines), encoding="utf-8")

    status = "NO_PENDING_ACTIONS" if not actions else "PASS"
    workspace_report = {
        "schema_version": "1.0",
        "status": status,
        "workspace_kind": "CORPORATE_ACTION_DISCLOSURE_ENRICHMENT",
        "run_id": run_id,
        "output_root": str(root),
        "pending_action_count": len(actions),
        "manifest_path": str(manifest_path),
        "checklist_path": str(checklist_path),
        "claim_boundaries": {
            "workspace_contains_official_evidence": False,
            "placeholder_is_evidence": False,
            "reviewed_text_export_is_original_disclosure": False,
            "mechanical_factor_is_official_factor": False,
            "reference_price_factor_is_return_engine_multiplier": False,
            "rights_terp_is_execution_receipt": False,
            "backtest_ready": False,
        },
    }
    report_path = report_dir / "ca_enrichment_workspace_report.json"
    report_path.write_bytes(canonical_json_bytes(workspace_report))
    return workspace_report


__all__ = [
    "CA_ENRICHMENT_MANIFEST_SCHEMA_VERSION",
    "prepare_ca_enrichment_workspace",
]
