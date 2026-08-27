from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

from kubo.foundation_io import load_strict_json_object
from kubo.recovery import (
    RecoveryError,
    build_incident,
    load_recovery_policy,
    recovery_decision,
    sanitize_diagnostics,
    validate_dispatch_inputs,
    validate_incident,
    validate_recovery_policy,
)


def _now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryError("--now must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecoveryError("--now must be timezone-aware")
    return parsed


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _safe_write_json(path: Path, value: Any) -> None:
    absolute = Path(os.path.abspath(path))
    absolute.parent.mkdir(parents=True, exist_ok=True)
    if absolute.is_symlink():
        raise RecoveryError("output must not be a symlink")
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_TRUNC
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(absolute, flags, 0o600)
    except OSError as exc:
        raise RecoveryError("cannot open output safely") from exc
    try:
        os.fchmod(descriptor, 0o600)
        encoded = content.encode("utf-8")
        offset = 0
        while offset < len(encoded):
            offset += os.write(descriptor, encoded[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _active_runs(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload, _ = load_strict_json_object(path, field="active runs", max_bytes=1024 * 1024)
    if frozenset(payload) != {"runs"} or not isinstance(payload["runs"], list):
        raise RecoveryError("active-runs file must contain only a runs array")
    rows: list[dict[str, Any]] = []
    for row in payload["runs"]:
        if not isinstance(row, dict):
            raise RecoveryError("active-runs entries must be objects")
        rows.append(row)
    return rows


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Validate incidents and make fail-closed KU-BO recovery decisions"
    )
    value.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = value.add_subparsers(dest="command", required=True)

    commands.add_parser("validate-policy")

    validate = commands.add_parser("validate-incident")
    validate.add_argument("--incident", type=Path, required=True)

    create = commands.add_parser("create-incident")
    create.add_argument("--market", default="KUWAIT")
    create.add_argument("--stage", required=True)
    create.add_argument("--error-class", required=True)
    create.add_argument("--component", required=True)
    create.add_argument("--failure-code", required=True)
    create.add_argument("--code-sha", required=True)
    create.add_argument("--failed-run-id", required=True)
    create.add_argument("--summary", required=True)
    create.add_argument("--run-url")
    create.add_argument("--checkpoint-id")
    create.add_argument("--required-user-action")
    create.add_argument("--now")
    create.add_argument("--output", type=Path)

    decide = commands.add_parser("decide")
    decide.add_argument("--incident", type=Path, required=True)
    decide.add_argument("--active-runs", type=Path)
    decide.add_argument("--secret-state", choices=("unknown", "missing", "present"), default="unknown")
    decide.add_argument("--current-code-sha")
    decide.add_argument("--relevant-code-change", action="store_true")
    decide.add_argument("--ci-passed", action="store_true")
    decide.add_argument("--smoke-passed", action="store_true")
    decide.add_argument("--now")

    dispatch = commands.add_parser("validate-dispatch")
    dispatch.add_argument("--mode", required=True)
    dispatch.add_argument("--incident-id")
    dispatch.add_argument("--checkpoint")

    redact = commands.add_parser("redact-diagnostics")
    redact.add_argument("--input", type=Path, required=True)
    redact.add_argument("--output", type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = args.project_root.resolve()
        if args.command == "validate-policy":
            result = validate_recovery_policy(root)
        elif args.command == "validate-incident":
            result = validate_incident(args.incident, project_root=root)
        elif args.command == "create-incident":
            result = build_incident(
                root,
                market=args.market,
                stage=args.stage,
                error_class=args.error_class,
                component=args.component,
                failure_code=args.failure_code,
                code_sha=args.code_sha,
                failed_run_id=args.failed_run_id,
                summary=args.summary,
                now=_now(args.now),
                run_url=args.run_url,
                checkpoint_id=args.checkpoint_id,
                required_user_action=args.required_user_action,
            )
            if args.output:
                _safe_write_json(args.output, result)
        elif args.command == "decide":
            policy, _ = load_recovery_policy(root)
            incident = validate_incident(args.incident, policy=policy)
            secret = None if args.secret_state == "unknown" else args.secret_state == "present"
            result = recovery_decision(
                incident,
                now=_now(args.now),
                policy=policy,
                active_runs=_active_runs(args.active_runs),
                required_secret_available=secret,
                current_code_sha=args.current_code_sha,
                relevant_code_change=args.relevant_code_change,
                ci_passed=args.ci_passed,
                smoke_passed=args.smoke_passed,
            )
        elif args.command == "validate-dispatch":
            result = validate_dispatch_inputs(
                mode=args.mode,
                incident_id=args.incident_id,
                checkpoint=args.checkpoint,
            )
        elif args.command == "redact-diagnostics":
            payload, _ = load_strict_json_object(
                args.input, field="diagnostics", max_bytes=4 * 1024 * 1024
            )
            result = sanitize_diagnostics(payload)
            if args.output:
                _safe_write_json(args.output, result)
        else:  # pragma: no cover - argparse enforces the subcommand
            raise RecoveryError("unsupported command")
        _print(result)
        return 0
    except (RecoveryError, ValueError) as exc:
        print(f"RECOVERY_CONTROLLER_BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
