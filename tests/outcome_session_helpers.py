from __future__ import annotations

import csv
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

from kubo.outcome_sessions import OutcomeSessionAuthority


CALENDAR_RAW_HASH = "7" * 64
STATUS_RAW_HASH = "8" * 64


def _run_git(root: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def build_test_outcome_authority(
    root: Path,
    *,
    trading_dates: frozenset[date] | None = None,
    status_rows: tuple[dict[str, str], ...] | None = None,
) -> OutcomeSessionAuthority:
    """Build an unapproved Option-1 fixture for structural traversal tests only."""

    root.mkdir(parents=True, exist_ok=True)
    policy_dir = root / "config" / "pilot"
    evidence_dir = root / "official"
    policy_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    policy = {
        "schema_version": "1.0",
        "policy_id": "KU_BO_PILOT_OUTCOME_SESSION_POLICY",
        "status": "FROZEN",
        "timezone": "Asia/Kuwait",
        "horizon_basis": "OFFICIAL_TRADING_SESSIONS",
        "non_trading_day_rule": "ADVANCE_TO_NEXT_ELIGIBLE_OFFICIAL_SESSION",
        "suspended_or_halted_rule": "ADVANCE_TO_NEXT_ELIGIBLE_OFFICIAL_SESSION",
        "corporate_action_rule": "RAW_PRICE_PLUS_SEPARATE_CASH_COMPONENT",
        "adjusted_price_double_count_guard": True,
        "rights_issue_policy": "BLOCK_UNTIL_EXERCISE_SALE_LAPSE_POLICY_FROZEN",
        "complex_action_policy": "BLOCK_UNTIL_RETURN_TREATMENT_FROZEN",
        "decision_id": "KU-BO-008-D01",
        "claim_boundary": "OUTCOME_SESSION_POLICY_FROZEN",
    }
    (policy_dir / "outcome_session_policy.json").write_text(
        json.dumps(policy, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "kubo-kuwait-research-engine"\n'
        'Repository = "https://github.com/mohsamir7122/ku-bo"\n',
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text("KU-BO isolated outcome-session test root.\n", encoding="utf-8")
    (root / "CODEX_START_HERE.md").write_text(
        "KU-BO isolated outcome-session test root.\n", encoding="utf-8"
    )

    trading_dates = trading_dates or frozenset(
        {date(2026, 8, 6), date(2026, 8, 9), date(2026, 8, 10), date(2026, 8, 11)}
    )
    calendar_path = evidence_dir / "trading_calendar.csv"
    calendar_fields = (
        "trade_date",
        "is_trading_day",
        "session_type",
        "session_regime_id",
        "continuous_start",
        "continuous_end",
        "trade_at_last_end",
        "raw_sha256",
    )
    with calendar_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=calendar_fields)
        writer.writeheader()
        current = date(2026, 8, 6)
        while current <= date(2026, 8, 11):
            trading = current in trading_dates
            writer.writerow(
                {
                    "trade_date": current.isoformat(),
                    "is_trading_day": "true" if trading else "false",
                    "session_type": "NORMAL" if trading else "CLOSED",
                    "session_regime_id": "TEST_REGIME" if trading else "",
                    "continuous_start": "09:00:00" if trading else "",
                    "continuous_end": "13:00:00" if trading else "",
                    "trade_at_last_end": "13:15:00" if trading else "",
                    "raw_sha256": CALENDAR_RAW_HASH,
                }
            )
            current += timedelta(days=1)

    status_path = evidence_dir / "security_status.csv"
    status_fields = (
        "security_code",
        "board",
        "status",
        "effective_from",
        "effective_to",
        "reason_code",
        "notice_id",
        "raw_sha256",
    )
    rows = status_rows or (
        {
            "security_code": "101",
            "board": "cash",
            "status": "TRADING",
            "effective_from": "2026-08-01",
            "effective_to": "",
            "reason_code": "TEST_OFFICIAL_STATUS",
            "notice_id": "test-notice",
            "raw_sha256": STATUS_RAW_HASH,
        },
    )
    with status_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=status_fields)
        writer.writeheader()
        writer.writerows(rows)

    _run_git(root, "init", "--quiet")
    _run_git(root, "config", "user.email", "tests@example.invalid")
    _run_git(root, "config", "user.name", "KU-BO Tests")
    _run_git(root, "remote", "add", "origin", "https://github.com/mohsamir7122/ku-bo.git")
    _run_git(
        root,
        "add",
        "config/pilot/outcome_session_policy.json",
        "pyproject.toml",
        "AGENTS.md",
        "CODEX_START_HERE.md",
    )
    _run_git(root, "commit", "--quiet", "-m", "test: freeze outcome session policy")

    authority = OutcomeSessionAuthority.from_structural_files(
        project_root=root,
        trading_calendar_path=calendar_path,
        security_status_path=status_path,
        manifest_hashes=frozenset({CALENDAR_RAW_HASH, STATUS_RAW_HASH}),
        known_security_codes=frozenset({"101"}),
    )
    expected_blocker = "OUTCOME_SESSION_ARTIFACT_BOUND_OFFICIAL_AUTHORITY_REQUIRED"
    if expected_blocker not in authority.errors:
        raise AssertionError(authority.errors)
    if "OUTCOME_SESSION_USER_DECISION_NOT_APPROVED:KU-BO-008-D01" not in authority.errors:
        raise AssertionError(authority.errors)
    return authority


__all__ = ["build_test_outcome_authority"]
