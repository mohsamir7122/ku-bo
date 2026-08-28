#!/usr/bin/env python3
"""Build and validate the manual GitHub Artifact checkpoint canary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kubo.atomic_output import AtomicOutputError
from kubo.checkpoint_artifact_journal import (
    ArtifactJournalCanaryError,
    create_generation_one,
    create_generation_two,
    validate_artifact_journal_bundle,
    validate_artifact_journal_chain,
)


def _context_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-generation-1")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--now", required=True)
    _context_arguments(create)

    resume = commands.add_parser("create-generation-2")
    resume.add_argument("--previous", type=Path, required=True)
    resume.add_argument("--output", type=Path, required=True)
    resume.add_argument("--now", required=True)
    _context_arguments(resume)

    validate = commands.add_parser("validate")
    validate.add_argument("--root", type=Path, required=True)
    _context_arguments(validate)

    chain = commands.add_parser("validate-chain")
    chain.add_argument("--previous", type=Path, required=True)
    chain.add_argument("--current", type=Path, required=True)
    _context_arguments(chain)
    return parser


def _print(value: object, *, stream: object = sys.stdout) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), file=stream)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create-generation-1":
            report = create_generation_one(
                args.output,
                repository=args.repository,
                workflow=args.workflow,
                workflow_ref=args.workflow_ref,
                workflow_sha=args.workflow_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                head_sha=args.head_sha,
                now=args.now,
            )
        elif args.command == "create-generation-2":
            report = create_generation_two(
                args.previous,
                args.output,
                repository=args.repository,
                workflow=args.workflow,
                workflow_ref=args.workflow_ref,
                workflow_sha=args.workflow_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                head_sha=args.head_sha,
                now=args.now,
            )
        elif args.command == "validate":
            report = validate_artifact_journal_bundle(
                args.root,
                expected_repository=args.repository,
                expected_workflow=args.workflow,
                expected_workflow_ref=args.workflow_ref,
                expected_workflow_sha=args.workflow_sha,
                expected_run_id=args.run_id,
                expected_run_attempt=args.run_attempt,
                expected_head_sha=args.head_sha,
            )
        elif args.command == "validate-chain":
            report = validate_artifact_journal_chain(
                args.previous,
                args.current,
                expected_repository=args.repository,
                expected_workflow=args.workflow,
                expected_workflow_ref=args.workflow_ref,
                expected_workflow_sha=args.workflow_sha,
                expected_run_id=args.run_id,
                expected_run_attempt=args.run_attempt,
                expected_head_sha=args.head_sha,
            )
        else:  # pragma: no cover - argparse enforces one command.
            raise AssertionError("unknown command")
    except (ArtifactJournalCanaryError, AtomicOutputError, OSError, ValueError) as exc:
        _print(
            {
                "status": "CANARY_REJECTED",
                "production_coordinator_status": "NOT_PRODUCTION_COORDINATOR",
                "error_class": type(exc).__name__,
                "sanitized_summary": str(exc)[:1000],
            },
            stream=sys.stderr,
        )
        return 2
    _print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
