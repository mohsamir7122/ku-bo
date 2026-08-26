#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kubo.codex_live_bootstrap import (  # noqa: E402
    CodexBootstrapError,
    validate_codex_live_bootstrap,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Validate the fail-closed KU-BO Codex handoff contract."
    )
    value.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    value.add_argument("--config", type=Path)
    value.add_argument("--json", action="store_true")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = validate_codex_live_bootstrap(
            args.project_root,
            config_path=args.config,
        )
    except CodexBootstrapError as exc:
        if args.json:
            print(json.dumps({"status": "BLOCKED", "error": str(exc)}, indent=2))
        else:
            print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status']}: {report['mission_status']} "
            f"at {report['activation_local']} {report['timezone']}"
        )
        print(
            "Runtime: NOT_IMPLEMENTED; scheduler: DISABLED_UNTIL_AUTHORIZED; "
            "Factor 9: RESEARCH_ASSET_PENDING_ADMISSION"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
