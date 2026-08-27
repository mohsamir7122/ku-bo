#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kubo.automation_schedule import (  # noqa: E402
    AutomationScheduleError,
    resolve_background_backfill_occurrence,
    resolve_automation_run,
    validate_automation_schedule,
)
from kubo.hashing import canonical_json_bytes  # noqa: E402


def _bool(value: str) -> bool:
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no", ""}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Validate or resolve the fail-closed Kuwait automation schedule."
    )
    value.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    value.add_argument("--resolve", action="store_true")
    value.add_argument("--resolve-background-backfill", action="store_true")
    value.add_argument("--event-schedule")
    value.add_argument("--slot-id")
    value.add_argument("--actual-started-at")
    value.add_argument(
        "--mode", choices=("CONTRACT_CHECK", "EXECUTE"), default="CONTRACT_CHECK"
    )
    value.add_argument("--activation-enabled", type=_bool, default=False)
    value.add_argument("--admission-ready", type=_bool, default=False)
    value.add_argument("--source-access-configured", type=_bool, default=False)
    value.add_argument("--drive-runtime-configured", type=_bool, default=False)
    value.add_argument("--output", type=Path)
    value.add_argument("--github-output", type=Path)
    return value


def _write_new(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.resolve and args.resolve_background_backfill:
            raise AutomationScheduleError("choose only one schedule resolver")
        if args.resolve_background_backfill:
            report = resolve_background_backfill_occurrence(
                actual_started_at=args.actual_started_at
                or datetime.now(timezone.utc).isoformat(),
                event_schedule=args.event_schedule or "",
            )
        elif args.resolve:
            report = resolve_automation_run(
                args.project_root,
                actual_started_at=args.actual_started_at
                or datetime.now(timezone.utc).isoformat(),
                event_schedule=args.event_schedule,
                slot_id=args.slot_id,
                mode=args.mode,
                activation_enabled=args.activation_enabled,
                admission_ready=args.admission_ready,
                source_access_configured=args.source_access_configured,
                drive_runtime_configured=args.drive_runtime_configured,
            )
        else:
            report = validate_automation_schedule(args.project_root)
    except (AutomationScheduleError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, sort_keys=True))
        return 1

    encoded = canonical_json_bytes(report)
    if args.output is not None:
        _write_new(args.output, encoded)
    print(encoded.decode("utf-8"), end="")
    if args.github_output is not None:
        outputs = {
            "status": report["status"],
            "slot_id": report.get("slot_id", "VALIDATE_ONLY"),
            "market_day_status": report.get("market_day_status", "NOT_APPLICABLE"),
            "run_collection": str(report.get("should_run_collection", False)).lower(),
            "run_validation": str(report.get("should_run_validation", False)).lower(),
            "run_live_scoring": str(report.get("should_run_live_scoring", False)).lower(),
        }
        if "scheduled_at" in report:
            outputs["scheduled_at"] = str(report["scheduled_at"])
            outputs["actual_started_at"] = str(report["actual_started_at"])
        with args.github_output.open("a", encoding="utf-8", newline="\n") as handle:
            for key, value in outputs.items():
                handle.write(f"{key}={value}\n")

    if args.resolve_background_backfill:
        return 0
    if not args.resolve or args.mode == "CONTRACT_CHECK":
        return 0
    if report["status"] in {
        "BLOCKED_DISABLED",
        "MAINTENANCE_ONLY_NO_TRADE",
        "READY_MAIN",
        "READY_LIVE",
    }:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
