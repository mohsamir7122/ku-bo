from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Any

from .hashing import canonical_json_bytes
from .strict import https_url
from .vendor_symbol_mapping import VendorSymbolMapping, VendorSymbolMappingCatalog


MANIFEST_HEADERS = (
    "ticker",
    "security_code",
    "isin",
    "name_en",
    "sector",
    "source_name",
    "source_type",
    "source_url_or_location",
    "downloaded_at",
    "downloaded_by",
    "file_name",
    "file_sha256",
    "date_range_start",
    "date_range_end",
    "row_count",
    "price_basis",
    "currency",
    "unit",
    "allowed_use",
    "review_status",
    "review_notes",
)
_SOURCE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_EXPECTED_SCOPES = frozenset({"mapped", "all_market"})



def _reject_symlink_ancestors(path: Path, field: str) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if not current.exists() and not current.is_symlink():
            break
        if current.is_symlink():
            raise ValueError(f"{field} must not contain symlink components")
    return absolute



def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=MANIFEST_HEADERS,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in MANIFEST_HEADERS})



def _manifest_row(
    mapping: VendorSymbolMapping,
    catalog: VendorSymbolMappingCatalog,
    *,
    source_name: str,
    downloaded_by: str,
) -> dict[str, str]:
    identity = catalog.identities.identities[mapping.ticker]
    return {
        "ticker": mapping.ticker,
        "security_code": mapping.security_code,
        "isin": mapping.isin,
        "name_en": identity.name_en,
        "sector": identity.sector,
        "source_name": source_name,
        "source_type": (
            "SECONDARY_MANUAL_EXPORT" if source_name.casefold() == "investing" else ""
        ),
        "source_url_or_location": mapping.provider_url,
        "downloaded_at": "",
        "downloaded_by": downloaded_by,
        "file_name": f"{mapping.ticker}.csv",
        "file_sha256": "",
        "date_range_start": "",
        "date_range_end": "",
        "row_count": "",
        "price_basis": "UNKNOWN",
        "currency": "KWD",
        "unit": "",
        "allowed_use": "USER_EXPORT",
        "review_status": "PENDING",
        "review_notes": (
            "Fill only after an authorized export is preserved, hashed, and reviewed."
        ),
    }



def prepare_price_collection_workspace(
    *,
    config_dir: Path,
    output_root: Path,
    source_name: str = "investing",
    downloaded_by: str = "",
    expected_scope: str = "mapped",
    drive_folder_url: str = "",
) -> dict[str, Any]:
    if not _SOURCE_NAME_RE.fullmatch(source_name):
        raise ValueError("source_name must be one path-safe ASCII directory name")
    if expected_scope not in _EXPECTED_SCOPES:
        raise ValueError("expected_scope must be mapped or all_market")
    if drive_folder_url:
        drive_folder_url = https_url(drive_folder_url, "drive_folder_url")
    output_root = _reject_symlink_ancestors(Path(output_root), "output_root")
    if output_root.exists() or output_root.is_symlink():
        if output_root.is_symlink() or not output_root.is_dir():
            raise ValueError("output_root must be a real directory")
        if any(output_root.iterdir()):
            raise ValueError("refusing to overwrite a non-empty workspace")
    else:
        output_root.mkdir(parents=True, exist_ok=False)

    catalog = VendorSymbolMappingCatalog(config_dir)
    mappings = sorted(
        catalog.capture_candidates(source_name.casefold()),
        key=lambda mapping: mapping.ticker,
    )
    if not mappings:
        raise ValueError("no active vendor mappings exist for the requested source")

    raw_export_dir = output_root / "raw_exports" / source_name
    manifest_dir = output_root / "manifests"
    report_dir = output_root / "reports"
    for directory in (
        raw_export_dir,
        manifest_dir,
        output_root / "normalized",
        report_dir,
        output_root / "quarantine",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, str]] = []
    for mapping in mappings:
        placeholder = raw_export_dir / f"{mapping.ticker}.csv.placeholder"
        placeholder.write_text(
            "Replace this placeholder with an authorized raw provider export named "
            f"{mapping.ticker}.csv.\n"
            "Do not edit provider bytes in place. Record SHA-256 and review metadata "
            "in manifests/price_collection_manifest.csv.\n",
            encoding="utf-8",
        )
        manifest_rows.append(
            _manifest_row(
                mapping,
                catalog,
                source_name=source_name,
                downloaded_by=downloaded_by,
            )
        )

    manifest_path = manifest_dir / "price_collection_manifest.csv"
    _write_csv(manifest_path, manifest_rows)
    checklist_path = report_dir / "price_collection_checklist.md"
    checklist_lines = [
        "# Price Collection Checklist",
        "",
        "This workspace accepts authorized user exports only.",
        "",
        "For every mapped security:",
        "",
        f"- Replace the placeholder under `raw_exports/{source_name}/` with the exact CSV export.",
        "- Do not edit the raw export in place.",
        "- Record SHA-256, download time, date range, row count, price basis, and unit.",
        "- Set `review_status=ACCEPTED` only after identity and OHLC review.",
        "- Move doubtful files to `quarantine/`; never repair provider rows silently.",
        "",
        "Pilot securities:",
        "",
    ]
    for mapping in mappings:
        checklist_lines.append(
            f"- {mapping.ticker}: security_code `{mapping.security_code}`, "
            f"ISIN `{mapping.isin}`, provider route `{mapping.provider_symbol}`"
        )
    checklist_lines.append("")
    checklist_path.write_text("\n".join(checklist_lines), encoding="utf-8")

    all_market_requested = expected_scope == "all_market"
    status = (
        "FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED"
        if all_market_requested
        else "PASS"
    )
    report = {
        "schema_version": "1.0",
        "status": status,
        "workspace_kind": "RESEARCH_PRICE_HISTORY_COLLECTION",
        "output_root": str(output_root),
        "source_name": source_name,
        "expected_scope": expected_scope,
        "symbol_count": len(mappings),
        "drive_folder_url": drive_folder_url,
        "manifest_path": str(manifest_path),
        "checklist_path": str(checklist_path),
        "raw_export_dir": str(raw_export_dir),
        "official_identity_ready": catalog.identities.official_identity_ready,
        "symbols": [
            {
                "ticker": mapping.ticker,
                "security_code": mapping.security_code,
                "isin": mapping.isin,
                "provider": mapping.provider,
                "provider_url": mapping.provider_url,
            }
            for mapping in mappings
        ],
        "claim_boundaries": {
            "does_not_collect_from_web": True,
            "does_not_upload_to_drive": True,
            "workspace_is_ready_for_authorized_exports": True,
            "vendor_mapping_is_official_identity": False,
            "seed_identity_is_official_evidence": False,
            "full_market_claim_allowed": False,
            "backtest_ready": False,
        },
    }
    report_path = report_dir / "price_collection_workspace_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = ["MANIFEST_HEADERS", "prepare_price_collection_workspace"]
