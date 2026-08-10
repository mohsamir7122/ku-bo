from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from kubo.benchmark_workspace import (
    load_official_calendar_receipt,
    prepare_benchmark_workspace,
)
from tests.foundation_fixture_helpers import ROOT, build_official_foundation_output


WINDOW_FROM = "2026-08-03"
WINDOW_TO = "2026-08-09"


def prepare_fixture_workspace(
    root: Path,
) -> tuple[Path, Path, tuple[str, ...]]:
    official = build_official_foundation_output(root)
    receipt = load_official_calendar_receipt(official)
    workspace = root / "benchmark-workspace"
    prepare_benchmark_workspace(
        config_dir=ROOT / "config",
        official_foundation_root=official,
        output_root=workspace,
        run_id="benchmark-fixture-001",
        window_from=WINDOW_FROM,
        window_to=WINDOW_TO,
        prepared_by="benchmark-fixture-helper",
    )
    trading_dates = tuple(
        day.isoformat()
        for day in sorted(receipt.trading_dates)
        if WINDOW_FROM <= day.isoformat() <= WINDOW_TO
    )
    if not trading_dates:
        raise AssertionError("fixture window contains no official trading dates")
    return official, workspace, trading_dates


def accept_fixture_manifest(
    workspace: Path,
    trading_dates: Sequence[str],
    *,
    availability: Mapping[str, str] | None = None,
    omitted_dates: Mapping[str, set[str]] | None = None,
    value_overrides: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, object]:
    availability = availability or {}
    omitted_dates = omitted_dates or {}
    value_overrides = value_overrides or {}
    manifest_path = workspace / "manifests" / "benchmark_history_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_dir = workspace / "raw_exports" / "benchmarks"
    for series_number, row in enumerate(manifest["artifacts"]):
        code = row["benchmark_code"]
        state = availability.get(code, "AVAILABLE")
        row.update(
            {
                "availability_status": state,
                "observed_at": "2026-08-10T09:00:00+03:00",
                "captured_by": "benchmark-fixture-helper",
                "review_status": "ACCEPTED",
                "review_notes": "recorded contract fixture; never real evidence",
                "unavailable_reason": "",
            }
        )
        if state == "UNAVAILABLE":
            row["file_name"] = f"{code}.receipt.txt"
            content = (
                f"{code}: authorized benchmark export not supplied; "
                "external license required.\n"
            ).encode("utf-8")
            row.update(
                {
                    "capture_mode": "SOURCE_ACCESS_RECEIPT",
                    "rights_status": "RESTRICTED",
                    "pages_declared": 0,
                    "pages_received": 0,
                    "result_count_declared": 0,
                    "row_count": 0,
                    "unavailable_reason": "EXTERNAL_LICENSE_REQUIRED",
                }
            )
        elif state == "ZERO_RESULT":
            content = b"trade_date,benchmark_value\n"
            row.update(
                {
                    "capture_mode": "RECORDED_AUTHORIZED_FIXTURE",
                    "rights_status": "FIXTURE_ONLY",
                    "pages_declared": 1,
                    "pages_received": 1,
                    "result_count_declared": 0,
                    "row_count": 0,
                }
            )
        elif state == "AVAILABLE":
            dates = [
                day for day in trading_dates if day not in omitted_dates.get(code, set())
            ]
            values = value_overrides.get(code)
            if values is None:
                values = [
                    f"{1000 + (series_number * 100) + index}.25"
                    for index in range(len(dates))
                ]
            if len(values) != len(dates):
                raise ValueError("value override count must match emitted trading dates")
            content = (
                "trade_date,benchmark_value\n"
                + "".join(
                    f"{day},{value}\n" for day, value in zip(dates, values, strict=True)
                )
            ).encode("utf-8")
            row.update(
                {
                    "capture_mode": "RECORDED_AUTHORIZED_FIXTURE",
                    "rights_status": "FIXTURE_ONLY",
                    "pages_declared": 1,
                    "pages_received": 1,
                    "result_count_declared": len(dates),
                    "row_count": len(dates),
                }
            )
        else:
            raise ValueError(f"unsupported fixture availability: {state}")
        (raw_dir / row["file_name"]).write_bytes(content)
        row["file_sha256"] = hashlib.sha256(content).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "ROOT",
    "WINDOW_FROM",
    "WINDOW_TO",
    "accept_fixture_manifest",
    "prepare_fixture_workspace",
]
