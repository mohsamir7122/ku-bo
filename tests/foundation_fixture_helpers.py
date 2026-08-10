from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kubo.official_foundation_import import import_official_foundation
from kubo.official_foundation_workspace import prepare_official_foundation_workspace
from kubo.status_corporate_import import import_status_corporate
from kubo.status_corporate_workspace import prepare_status_corporate_workspace
from tests.test_official_foundation_import import (
    CONTACT_HTML,
    EXTENSION_HTML,
    HOLIDAYS_HTML,
    LISTED_HTML,
    SHORT_SELL_HTML,
)
from tests.test_status_corporate_import import (
    CORPORATE_ACTIONS_HTML,
    DELISTED_HTML,
    EMPTY_CORPORATE_ACTIONS_HTML,
    EMPTY_SUSPENDED_HTML,
    SUSPENDED_HTML,
)


ROOT = Path(__file__).resolve().parents[1]


def build_official_foundation_output(root: Path) -> Path:
    workspace = root / "official-workspace"
    prepare_official_foundation_workspace(
        output_root=workspace,
        run_id="official-pilot-001",
        calendar_year=2026,
        prepared_by="fixture-helper",
    )
    manifest_path = workspace / "manifests" / "official_foundation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["identity_snapshot_effective_date"] = "2026-08-09"
    contents = {
        "short_sell_identity": SHORT_SELL_HTML,
        "listed_companies": LISTED_HTML,
        "market_holidays": HOLIDAYS_HTML,
        "trading_extension": EXTENSION_HTML,
        "contact_hours": CONTACT_HTML,
    }
    raw_dir = workspace / "raw_exports" / "boursa"
    for row in manifest["artifacts"]:
        content = contents[row["artifact_id"]]
        (raw_dir / row["file_name"]).write_bytes(content)
        row["file_sha256"] = hashlib.sha256(content).hexdigest()
        row["observed_at"] = "2026-08-09T09:00:00+03:00"
        row["captured_by"] = "fixture-helper"
        row["review_status"] = "ACCEPTED"
        row["review_notes"] = "authorized contract fixture"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    output = root / "official-output"
    report = import_official_foundation(
        config_dir=ROOT / "config",
        workspace=workspace,
        output_root=output,
    )
    if report["status"] != "CURRENT_IDENTITY_AND_CALENDAR_READY":
        raise AssertionError(report)
    return output


def build_status_corporate_output(
    root: Path,
    *,
    zero_suspended: bool = False,
    zero_actions: bool = False,
) -> Path:
    official_output = build_official_foundation_output(root)
    workspace = root / "status-workspace"
    prepare_status_corporate_workspace(
        output_root=workspace,
        run_id="status-ca-001",
        action_window_from="2026-01-01",
        action_window_to="2026-12-31",
        prepared_by="fixture-helper",
    )
    manifest_path = workspace / "manifests" / "status_corporate_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status_snapshot_effective_date"] = "2026-08-09"
    manifest["corporate_action_query"].update(
        {
            "filter_applied": True,
            "pages_declared": 1,
            "pages_received": 1,
            "result_count_declared": 0 if zero_actions else 2,
            "review_status": "ACCEPTED",
            "review_notes": "rendered page count reconciled",
        }
    )
    contents = {
        "suspended_companies": (
            EMPTY_SUSPENDED_HTML if zero_suspended else SUSPENDED_HTML
        ),
        "delisted_companies": DELISTED_HTML,
        "corporate_actions": (
            EMPTY_CORPORATE_ACTIONS_HTML
            if zero_actions
            else CORPORATE_ACTIONS_HTML
        ),
    }
    raw_dir = workspace / "raw_exports" / "boursa"
    for row in manifest["artifacts"]:
        content = contents[row["artifact_id"]]
        (raw_dir / row["file_name"]).write_bytes(content)
        row["file_sha256"] = hashlib.sha256(content).hexdigest()
        row["observed_at"] = "2026-08-09T10:00:00+03:00"
        row["captured_by"] = "fixture-helper"
        row["review_status"] = "ACCEPTED"
        row["review_notes"] = "authorized rendered contract fixture"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    output = root / "status-output"
    report = import_status_corporate(
        config_dir=ROOT / "config",
        official_foundation_root=official_output,
        workspace=workspace,
        output_root=output,
    )
    expected = (
        "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY"
        if zero_actions
        else "CURRENT_STATUS_AND_CA_SCHEDULE_READY"
    )
    if report["status"] != expected:
        raise AssertionError(report)
    return output


__all__ = [
    "ROOT",
    "build_official_foundation_output",
    "build_status_corporate_output",
]
