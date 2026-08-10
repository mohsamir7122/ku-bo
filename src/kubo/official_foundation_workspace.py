from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from .hashing import canonical_json_bytes


OFFICIAL_FOUNDATION_MANIFEST_SCHEMA_VERSION = "1.0"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

OFFICIAL_ARTIFACT_SPECS: tuple[dict[str, str], ...] = (
    {
        "artifact_id": "short_sell_identity",
        "source_id": "boursa_reports_archive",
        "source_url": "https://reports.boursakuwait.com.kw/en/shortsell",
        "file_name": "short_sell_identity.html",
        "capture_mode": "PUBLIC_PAGE",
        "purpose": "Official current security-code, company-name, and ISIN table.",
    },
    {
        "artifact_id": "listed_companies",
        "source_id": "boursa_current",
        "source_url": "https://www.boursakuwait.com.kw/en/participants/participants/listed-companies/",
        "file_name": "listed_companies_rendered.html",
        "capture_mode": "AUTHORIZED_BROWSER",
        "purpose": "Rendered official Listed Companies table with ticker, sector, market segment, and listing date.",
    },
    {
        "artifact_id": "market_holidays",
        "source_id": "boursa_current",
        "source_url": "https://www.boursakuwait.com.kw/en/securities/trading/market-holidays/",
        "file_name": "market_holidays.html",
        "capture_mode": "PUBLIC_PAGE",
        "purpose": "Official market-holiday snapshot for the selected calendar year.",
    },
    {
        "artifact_id": "trading_extension",
        "source_id": "boursa_current",
        "source_url": "https://www.boursakuwait.com.kw/TS-Extension-EN/",
        "file_name": "trading_extension.html",
        "capture_mode": "PUBLIC_PAGE",
        "purpose": "Official effective date and cash-market session times introduced from October 12, 2025.",
    },
    {
        "artifact_id": "contact_hours",
        "source_id": "boursa_current",
        "source_url": "https://www.boursakuwait.com.kw/en/contact/",
        "file_name": "contact_hours.html",
        "capture_mode": "PUBLIC_PAGE",
        "purpose": "Official Sunday-to-Thursday trading-weekday statement.",
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
            raise ValueError("refusing to overwrite a non-empty official workspace")
    else:
        absolute.mkdir(parents=True, exist_ok=False)
    return absolute


def prepare_official_foundation_workspace(
    *,
    output_root: Path,
    run_id: str,
    calendar_year: int = 2026,
    prepared_by: str = "",
) -> dict[str, Any]:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be a canonical path-safe identifier")
    if not 2000 <= calendar_year <= 2100:
        raise ValueError("calendar_year must be between 2000 and 2100")
    root = _safe_output_root(output_root)
    raw_dir = root / "raw_exports" / "boursa"
    manifest_dir = root / "manifests"
    report_dir = root / "reports"
    for directory in (raw_dir, manifest_dir, root / "normalized", report_dir, root / "quarantine"):
        directory.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, Any]] = []
    for spec in OFFICIAL_ARTIFACT_SPECS:
        placeholder = raw_dir / f"{spec['file_name']}.placeholder"
        placeholder.write_text(
            "Replace this placeholder with the exact captured official HTML bytes.\n"
            f"Artifact: {spec['artifact_id']}\n"
            f"Official URL: {spec['source_url']}\n"
            f"Expected file name: {spec['file_name']}\n"
            "Do not edit the captured bytes. Compute SHA-256 and complete the manifest.\n",
            encoding="utf-8",
        )
        artifacts.append(
            {
                **spec,
                "file_sha256": "",
                "observed_at": "",
                "captured_by": prepared_by,
                "review_status": "PENDING",
                "review_notes": "Accept only after the correct official page/table is visible and the exact bytes are hashed.",
            }
        )

    manifest = {
        "schema_version": OFFICIAL_FOUNDATION_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "identity_snapshot_effective_date": "",
        "calendar_window_from": date(calendar_year, 1, 1).isoformat(),
        "calendar_window_to": date(calendar_year, 12, 31).isoformat(),
        "artifacts": artifacts,
    }
    manifest_path = manifest_dir / "official_foundation_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    checklist_lines = [
        "# Official Identity and Trading Calendar Checklist",
        "",
        "Required artifacts:",
        "",
    ]
    for spec in OFFICIAL_ARTIFACT_SPECS:
        checklist_lines.extend(
            [
                f"## {spec['artifact_id']}",
                "",
                f"- URL: {spec['source_url']}",
                f"- File: `raw_exports/boursa/{spec['file_name']}`",
                f"- Capture mode: `{spec['capture_mode']}`",
                f"- Purpose: {spec['purpose']}",
                "- Preserve the exact bytes and record SHA-256 and observed_at.",
                "",
            ]
        )
    checklist_lines.extend(
        [
            "Before import:",
            "",
            "- Fill `identity_snapshot_effective_date` only from the official snapshot date or capture date; it is not a historical listing start.",
            "- Set every accepted artifact to `review_status=ACCEPTED`.",
            "- Do not use a Search Snippet, screenshot, copied table, or manually typed identity row as raw evidence.",
            "- The Listed Companies page must be saved after the client-rendered table is visible.",
            "- Market holidays remain a dated snapshot and may be changed by later official decisions.",
            "",
        ]
    )
    checklist_path = report_dir / "official_foundation_checklist.md"
    checklist_path.write_text("\n".join(checklist_lines), encoding="utf-8")

    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "workspace_kind": "OFFICIAL_IDENTITY_AND_TRADING_CALENDAR",
        "run_id": run_id,
        "output_root": str(root),
        "calendar_year": calendar_year,
        "artifact_count": len(artifacts),
        "manifest_path": str(manifest_path),
        "checklist_path": str(checklist_path),
        "raw_export_dir": str(raw_dir),
        "next_command": (
            "kubo-data-foundation --project-root . import-official-foundation "
            f"--workspace {root} --output-root runtime/data_foundation/{run_id}-official"
        ),
        "claim_boundaries": {
            "workspace_contains_official_evidence": False,
            "placeholder_is_evidence": False,
            "search_snippet_is_evidence": False,
            "calendar_is_immutable": False,
            "historical_identity_ready": False,
            "backtest_ready": False,
        },
    }
    report_path = report_dir / "official_foundation_workspace_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "OFFICIAL_ARTIFACT_SPECS",
    "OFFICIAL_FOUNDATION_MANIFEST_SCHEMA_VERSION",
    "prepare_official_foundation_workspace",
]
