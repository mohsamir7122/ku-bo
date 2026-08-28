#!/usr/bin/env python3
"""Audit one manual Kuwait public-access canary and publish sanitized receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kubo.access_canary import (  # noqa: E402
    AccessCanaryError,
    run_access_canary_audit,
)
from kubo.atomic_output import AtomicOutputError  # noqa: E402


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    value.add_argument("--source-id", required=True)
    value.add_argument(
        "--confirm-no-trade",
        choices=("true", "false"),
        required=True,
    )
    value.add_argument("--plan", type=Path, required=True)
    value.add_argument("--probe", type=Path, required=True)
    value.add_argument("--execution-report", type=Path, required=True)
    value.add_argument("--output-root", type=Path, required=True)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = run_access_canary_audit(
            project_root=args.project_root,
            source_id=args.source_id,
            confirm_no_trade=args.confirm_no_trade == "true",
            plan_path=args.plan,
            probe_path=args.probe,
            execution_report_path=args.execution_report,
            output_root=args.output_root,
        )
    except (AccessCanaryError, AtomicOutputError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_ACCESS_ONLY_CANARY",
                    "failure_code": getattr(
                        exc, "failure_code", "CANARY_AUDIT_PUBLICATION_FAILED"
                    ),
                    "candidate_count": 0,
                    "no_trade": True,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS_ACCESS_ONLY_CANARY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
