from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .hashing import canonical_json_bytes
from .strict import parse_iso_date


STATUS_CORPORATE_MANIFEST_SCHEMA_VERSION = "1.0"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

STATUS_CORPORATE_ARTIFACT_SPECS: tuple[dict[str, str], ...] = (
    {
        "artifact_id": "suspended_companies",
        "source_id": "boursa_current",
        "source_url": "https://www.boursakuwait.com.kw/en/securities/company-information/suspended-companies/",
        "file_name": "suspended_companies_rendered.html",
        "capture_mode": "AUTHORIZED_BROWSER",
        "purpose": "Rendered official current Suspended Companies table; an empty rendered table is an observed zero snapshot.",
    },
    {
        "artifact_id": "delisted_companies",
        "source_id": "boursa_current",
        "source_url": "https://www.boursakuwait.com.kw/en/securities/company-information/delisted-companies/",
        "file_name": "delisted_companies_rendered.html",
        "capture_mode": "AUTHORIZED_BROWSER",
        "purpose": "Rendered official Delisted Companies archive with the official delisting date.",
    },
    {
        "artifact_id": "corporate_actions",
        "source_id": "boursa_current",
        "source_url": "https://www.boursakuwait.com.kw/en/securities/company-information/corporate-actions/",
        "file_name": "corporate_actions_rendered.html",
        "capture_mode": "AUTHORIZED_BROWSER",
        "purpose": "Rendered official Corporate Actions schedule for the declared page filter window and pagination receipt.",
    },
)


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
            raise ValueError("refusing to overwrite a non-empty status/corporate workspace")
    else:
        absolute.mkdir(parents=True, exist_ok=False)
    return absolute


def prepare_status_corporate_workspace(
    *,
    output_root: Path,
    run_id: str,
    action_window_from: str,
    action_window_to: str,
    prepared_by: str = "",
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be a canonical path-safe identifier")
    window_from = parse_iso_date(action_window_from, "action_window_from")
    window_to = parse_iso_date(action_window_to, "action_window_to")
    if window_from > window_to:
        raise ValueError("corporate-action window is reversed")
    root = _safe_output_root(output_root)
    raw_dir = root / "raw_exports" / "boursa"
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

    artifacts: list[dict[str, Any]] = []
    for spec in STATUS_CORPORATE_ARTIFACT_SPECS:
        placeholder = raw_dir / f"{spec['file_name']}.placeholder"
        placeholder.write_text(
            "Replace this placeholder with the exact rendered official HTML bytes.\n"
            f"Artifact: {spec['artifact_id']}\n"
            f"Official URL: {spec['source_url']}\n"
            f"Expected file name: {spec['file_name']}\n"
            "Do not edit the capture. Record SHA-256, observed_at, and review status in the manifest.\n",
            encoding="utf-8",
        )
        artifacts.append(
            {
                **spec,
                "file_sha256": "",
                "observed_at": "",
                "captured_by": prepared_by,
                "review_status": "PENDING",
                "review_notes": "Accept only after the rendered table and all declared result pages are visible and preserved.",
            }
        )

    manifest = {
        "schema_version": STATUS_CORPORATE_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "status_snapshot_effective_date": "",
        "corporate_action_window_from": window_from.isoformat(),
        "corporate_action_window_to": window_to.isoformat(),
        "corporate_action_query": {
            "filter_applied": False,
            "pages_declared": "",
            "pages_received": "",
            "result_count_declared": "",
            "review_status": "PENDING",
            "review_notes": "Record the rendered result count and pagination after applying the official page filter.",
        },
        "artifacts": artifacts,
    }
    manifest_path = manifest_dir / "status_corporate_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    checklist_lines = [
        "# Security Status and Corporate Actions Checklist",
        "",
        "This workspace captures current status evidence and an official corporate-action schedule only.",
        "",
    ]
    for spec in STATUS_CORPORATE_ARTIFACT_SPECS:
        checklist_lines.extend(
            [
                f"## {spec['artifact_id']}",
                "",
                f"- URL: {spec['source_url']}",
                f"- File: `raw_exports/boursa/{spec['file_name']}`",
                f"- Capture mode: `{spec['capture_mode']}`",
                f"- Purpose: {spec['purpose']}",
                "- Save the page only after the rendered table is visible.",
                "- Preserve exact bytes and record SHA-256 and observed_at.",
                "",
            ]
        )
    checklist_lines.extend(
        [
            "Before import:",
            "",
            "- The Suspended and Delisted pages must be captured on the same Kuwait civil date used as `status_snapshot_effective_date`.",
            "- An empty Suspended Companies result is valid only when the rendered table headers are present.",
            "- Apply the official Corporate Actions date filter and preserve every result page in one rendered HTML export or a complete combined export.",
            "- Set `corporate_action_query.filter_applied=true` and reconcile pages and result count to the rendered rows.",
            "- Corporate Actions schedule dates do not reveal action type, amount, or adjustment factor; those remain pending issuer-disclosure enrichment.",
            "- Set every accepted artifact and the query receipt to `review_status=ACCEPTED`.",
            "- Search snippets, screenshots, copied tables, and manually typed market rows are not raw evidence.",
            "",
        ]
    )
    checklist_path = report_dir / "status_corporate_checklist.md"
    checklist_path.write_text("\n".join(checklist_lines), encoding="utf-8")

    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "workspace_kind": "SECURITY_STATUS_AND_CORPORATE_ACTION_SCHEDULE",
        "run_id": run_id,
        "output_root": str(root),
        "action_window_from": window_from.isoformat(),
        "action_window_to": window_to.isoformat(),
        "artifact_count": len(artifacts),
        "manifest_path": str(manifest_path),
        "checklist_path": str(checklist_path),
        "raw_export_dir": str(raw_dir),
        "next_command": (
            "kubo-data-foundation --project-root . import-status-corporate "
            f"--workspace {root} --official-foundation-root <official-output> "
            f"--output-root runtime/data_foundation/{run_id}-status-ca"
        ),
        "claim_boundaries": {
            "workspace_contains_official_evidence": False,
            "placeholder_is_evidence": False,
            "current_status_is_status_history": False,
            "corporate_action_schedule_contains_action_type": False,
            "corporate_action_schedule_contains_adjustment_factor": False,
            "query_receipt_is_official_market_fact": False,
            "backtest_ready": False,
        },
    }
    report_path = report_dir / "status_corporate_workspace_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "STATUS_CORPORATE_ARTIFACT_SPECS",
    "STATUS_CORPORATE_MANIFEST_SCHEMA_VERSION",
    "prepare_status_corporate_workspace",
]
