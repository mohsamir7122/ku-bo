from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import canonical_json_bytes
from .symbol_mapping import SymbolMapping, SymbolMappingCatalog


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


@dataclass(frozen=True)
class PriceCollectionWorkspace:
    output_root: Path
    manifest_path: Path
    checklist_path: Path
    report_path: Path
    symbol_count: int


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def _manifest_row(mapping: SymbolMapping, source_name: str, downloaded_by: str) -> dict[str, str]:
    return {
        "ticker": mapping.boursa_symbol,
        "security_code": mapping.security_code,
        "isin": mapping.isin,
        "name_en": mapping.name_en,
        "sector": mapping.sector,
        "source_name": source_name,
        "source_type": "SECONDARY_MANUAL_EXPORT" if source_name.lower() == "investing" else "",
        "source_url_or_location": mapping.investing_url if source_name.lower() == "investing" else "",
        "downloaded_at": "",
        "downloaded_by": downloaded_by,
        "file_name": f"{mapping.boursa_symbol}.csv",
        "file_sha256": "",
        "date_range_start": "",
        "date_range_end": "",
        "row_count": "",
        "price_basis": "UNKNOWN",
        "currency": "KWD",
        "unit": "",
        "allowed_use": "USER_EXPORT",
        "review_status": "PENDING",
        "review_notes": "Fill after authorized export is collected and SHA-256 is computed.",
    }


def _checklist_lines(mappings: list[SymbolMapping], source_name: str) -> list[str]:
    lines = [
        "# Price Collection Checklist",
        "",
        "Use this checklist before running `import-investing-user-exports`.",
        "",
        "Required steps for each symbol:",
        "",
        "- Place the authorized raw CSV under `raw_exports/{source_name}/{ticker}.csv`.",
        "- Do not edit the raw CSV in place.",
        "- Compute and record SHA-256 in `manifests/price_collection_manifest.csv`.",
        "- Fill `downloaded_at`, `date_range_start`, `date_range_end`, `row_count`, `price_basis`, and `unit`.",
        "- Keep `review_status=PENDING` until identity and OHLC checks pass.",
        "- Move any doubtful file to `quarantine/` and explain the reason.",
        "",
        "Symbols in this workspace:",
        "",
    ]
    for mapping in mappings:
        lines.append(
            f"- {mapping.boursa_symbol}: security_code `{mapping.security_code}`, "
            f"ISIN `{mapping.isin}`, file `raw_exports/{source_name}/{mapping.boursa_symbol}.csv`"
        )
    lines.append("")
    return lines


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
        raise ValueError(
            "source_name must be a single path-safe ASCII directory name"
        )
    if expected_scope not in _EXPECTED_SCOPES:
        raise ValueError("expected_scope must be mapped or all_market")
    if output_root.is_symlink():
        raise ValueError("output_root must not be a symlink")
    if output_root.exists():
        if not output_root.is_dir():
            raise ValueError("output_root must be a directory")
        if any(output_root.iterdir()):
            raise ValueError("refusing to overwrite a non-empty workspace")

    catalog = SymbolMappingCatalog(config_dir)
    mappings = sorted(
        catalog.capture_candidates(), key=lambda mapping: mapping.boursa_symbol
    )
    if not mappings:
        raise ValueError("symbol mapping has no non-retired mappings with source URLs")
    output_root.mkdir(parents=True, exist_ok=True)
    for directory in (
        output_root / "raw_exports" / source_name,
        output_root / "manifests",
        output_root / "normalized",
        output_root / "reports",
        output_root / "quarantine",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    placeholder_rows: list[dict[str, str]] = []
    for mapping in mappings:
        placeholder = output_root / "raw_exports" / source_name / f"{mapping.boursa_symbol}.csv.placeholder"
        placeholder.write_text(
            "Replace this placeholder with an authorized raw CSV named "
            f"{mapping.boursa_symbol}.csv.\n"
            "Do not edit provider data in place. Record SHA-256 in the manifest.\n",
            encoding="utf-8",
        )
        placeholder_rows.append(_manifest_row(mapping, source_name, downloaded_by))
    manifest_path = output_root / "manifests" / "price_collection_manifest.csv"
    _write_csv(manifest_path, MANIFEST_HEADERS, placeholder_rows)
    checklist_path = output_root / "reports" / "price_collection_checklist.md"
    checklist_path.write_text(
        "\n".join(_checklist_lines(mappings, source_name)),
        encoding="utf-8",
    )
    all_market_requested = expected_scope == "all_market"
    coverage_scope = catalog.coverage.get("scope", "")
    config_declares_all_listed = coverage_scope == "ALL_LISTED_SECURITIES"
    # A self-declared config scope is not point-in-time universe evidence.  This
    # workspace has no official expected-universe artifact to reconcile, so an
    # all-market request must remain blocked regardless of the config label.
    status = (
        "FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED"
        if all_market_requested
        else "PASS"
    )
    report = {
        "status": status,
        "workspace_kind": "PRICE_COLLECTION_WORKSPACE",
        "output_root": str(output_root),
        "source_name": source_name,
        "expected_scope": expected_scope,
        "mapping_scope": coverage_scope,
        "symbol_count": len(mappings),
        "drive_folder_url": drive_folder_url,
        "manifest_path": str(manifest_path),
        "checklist_path": str(checklist_path),
        "raw_export_dir": str(output_root / "raw_exports" / source_name),
        "next_commands": [
            "Fill manifests/price_collection_manifest.csv after collecting authorized CSV exports.",
            "Replace .csv.placeholder files with real {ticker}.csv files.",
            "Run import-investing-user-exports against raw_exports/{source_name}.",
        ],
        "symbols": [
            {
                "ticker": mapping.boursa_symbol,
                "security_code": mapping.security_code,
                "isin": mapping.isin,
                "name_en": mapping.name_en,
                "source_url": mapping.investing_url,
            }
            for mapping in mappings
        ],
        "claim_boundaries": {
            "does_not_collect_from_web": True,
            "does_not_upload_to_drive": True,
            "workspace_is_ready_for_authorized_exports": True,
            "config_scope_is_not_reconciliation_evidence": True,
            "config_declares_all_listed_securities": config_declares_all_listed,
            "full_market_requires_external_point_in_time_identity_evidence": all_market_requested,
        },
    }
    report_path = output_root / "reports" / "price_collection_workspace_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = ["MANIFEST_HEADERS", "prepare_price_collection_workspace"]
