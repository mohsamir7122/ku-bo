#!/usr/bin/env python3
"""Build or validate the fail-closed Kuwait 90-day research-context package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kubo.atomic_output import AtomicOutputError
from kubo.backfill_90d import (
    RightsAwareBackfillError,
    build_rights_aware_bundle,
    validate_backfill_policy,
    validate_rights_aware_bundle,
)
from kubo.priority_runtime import BlockedCheckpointStore
from kubo.recovery import sanitize_text


def _print(value: object, *, stream: object = sys.stdout) -> None:
    print(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2),
        file=stream,
    )


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="repository root containing config/ and schemas/",
    )
    commands = value.add_subparsers(dest="command", required=True)
    commands.add_parser("policy", help="validate the fail-closed backfill policy")

    validate = commands.add_parser("validate", help="reopen and validate one package")
    validate.add_argument("--bundle", type=Path, required=True)

    build = commands.add_parser("build", help="atomically build one immutable package")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--run-id", required=True)
    build.add_argument("--code-sha", required=True)
    build.add_argument("--scheduled-at", required=True)
    build.add_argument("--actual-started-at", required=True)
    build.add_argument("--finished-at", required=True)
    build.add_argument(
        "--receipt",
        action="append",
        nargs=2,
        metavar=("PLAN", "PROBE"),
        default=[],
        help="canonical one-source probe plan and access-probe receipt",
    )
    build.add_argument(
        "--production",
        action="store_true",
        help="require the durable production checkpoint store",
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "policy":
            report = validate_backfill_policy(args.project_root)
        elif args.command == "validate":
            report = validate_rights_aware_bundle(args.project_root, args.bundle)
        elif args.command == "build":
            report = build_rights_aware_bundle(
                args.project_root,
                args.output,
                run_id=args.run_id,
                code_sha=args.code_sha,
                scheduled_at=args.scheduled_at,
                actual_started_at=args.actual_started_at,
                finished_at=args.finished_at,
                receipt_bindings=[
                    (Path(plan), Path(probe)) for plan, probe in args.receipt
                ],
                production=args.production,
            )
        else:  # pragma: no cover - argparse enforces a subcommand
            raise AssertionError("unknown command")
    except (
        AtomicOutputError,
        BlockedCheckpointStore,
        RightsAwareBackfillError,
        OSError,
        ValueError,
    ) as exc:
        _print(
            {
                "status": "BLOCKED",
                "error_class": type(exc).__name__,
                "failure_code": getattr(exc, "failure_code", None),
                "sanitized_summary": sanitize_text(exc, max_length=1000),
                "publish_allowed": False,
                "strict_forecast_status": "LOCKED",
            },
            stream=sys.stderr,
        )
        return 2
    _print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
