from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from .foundation_io import read_csv_bytes, require_real_directory, safe_regular_file, strict_json_object
from .hashing import sha256_bytes
from .identity import StatusRecord, validate_status_history
from .market import validate_trading_calendar
from .strict import parse_aware, parse_iso_date, require_sha256


KUWAIT = ZoneInfo("Asia/Kuwait")
POLICY_RELATIVE_PATH = "config/pilot/outcome_session_policy.json"

_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "status",
        "timezone",
        "horizon_basis",
        "non_trading_day_rule",
        "suspended_or_halted_rule",
        "corporate_action_rule",
        "adjusted_price_double_count_guard",
        "rights_issue_policy",
        "complex_action_policy",
        "decision_id",
        "claim_boundary",
    }
)
def _committed_blob(project_root: Path, relative_path: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "cat-file", "blob", f"HEAD:{relative_path}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _validate_project_root(project_root: Path) -> tuple[Path | None, list[str]]:
    try:
        root = require_real_directory(project_root, field="OUTCOME_SESSION_PROJECT_ROOT")
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return None, [f"OUTCOME_SESSION_PROJECT_ROOT_INVALID:{exc}"]
    if result.returncode != 0 or Path(result.stdout.strip()).resolve() != root.resolve():
        return None, ["OUTCOME_SESSION_PROJECT_ROOT_NOT_GIT_TOP_LEVEL"]
    pyproject = _committed_blob(root, "pyproject.toml")
    agents = _committed_blob(root, "AGENTS.md")
    start_here = _committed_blob(root, "CODEX_START_HERE.md")
    if pyproject is None or agents is None or start_here is None:
        return None, ["OUTCOME_SESSION_PROJECT_ROOT_KU_BO_MARKERS_NOT_COMMITTED"]
    marker = pyproject.decode("utf-8", errors="replace")
    if (
        'name = "kubo-kuwait-research-engine"' not in marker
        or "https://github.com/mohsamir7122/ku-bo" not in marker
    ):
        return None, ["OUTCOME_SESSION_PROJECT_ROOT_KU_BO_MARKERS_INVALID"]
    return root, []


def _policy_state(project_root: Path) -> tuple[dict[str, Any] | None, bytes | None, list[str]]:
    policy_path = project_root / Path(POLICY_RELATIVE_PATH)
    try:
        current = safe_regular_file(
            policy_path,
            field="OUTCOME_SESSION_POLICY",
            max_bytes=256 * 1024,
        )
        payload = strict_json_object(current, "OUTCOME_SESSION_POLICY")
    except (OSError, ValueError) as exc:
        return None, None, [f"OUTCOME_SESSION_POLICY_INVALID:{exc}"]
    if set(payload) != _POLICY_FIELDS:
        return payload, current, ["OUTCOME_SESSION_POLICY_UNKNOWN_OR_MISSING_FIELDS"]
    if payload.get("status") != "FROZEN":
        return payload, current, ["OUTCOME_SESSION_POLICY_NOT_FROZEN"]
    # KU-BO-008-D01 is OPEN.  v1 has no approved product-specific maximum
    # extension/terminal-treatment contract or decision receipt.  A caller cannot
    # turn the globally hard-coded Option 1 into authority merely by committing it.
    return payload, current, [
        "OUTCOME_SESSION_USER_DECISION_NOT_APPROVED:KU-BO-008-D01"
    ]


@dataclass(frozen=True)
class OutcomeSessionAuthority:
    """Fail-closed structural resolver for a session-horizon outcome time.

    ``from_structural_files`` validates the exact policy blob committed at
    ``HEAD`` and structurally/hash-validates calendar and status inputs.  It does
    not mistake caller-provided hashes for official provenance: until an external
    artifact-bound capture receipt exists, every instance remains blocked for
    forecast recording while still reporting the due time the rows imply.
    """

    status: str
    errors: tuple[str, ...]
    policy_sha256: str | None
    trading_calendar_sha256: str | None
    security_status_sha256: str | None
    calendar: Mapping[date, Mapping[str, Any]]
    statuses: tuple[StatusRecord, ...]
    board: str = "cash"

    @classmethod
    def from_structural_files(
        cls,
        *,
        project_root: Path,
        trading_calendar_path: Path | None = None,
        security_status_path: Path | None = None,
        manifest_hashes: frozenset[str] = frozenset(),
        known_security_codes: frozenset[str] = frozenset(),
        board: str = "cash",
    ) -> "OutcomeSessionAuthority":
        root, errors = _validate_project_root(Path(project_root))
        if root is None:
            root = Path(project_root)
            policy_content = None
        else:
            _, policy_content, policy_errors = _policy_state(root)
            errors.extend(policy_errors)
        policy_sha256 = sha256_bytes(policy_content) if policy_content is not None else None
        calendar: dict[date, dict[str, Any]] = {}
        statuses: list[StatusRecord] = []
        calendar_sha256: str | None = None
        status_sha256: str | None = None

        if trading_calendar_path is None:
            errors.append("OFFICIAL_TRADING_CALENDAR_REQUIRED")
        else:
            calendar_path = Path(trading_calendar_path)
            try:
                calendar_content = safe_regular_file(
                    calendar_path,
                    field="OFFICIAL_TRADING_CALENDAR",
                    max_bytes=64 * 1024 * 1024,
                )
                headers, rows = read_csv_bytes(
                    calendar_content,
                    field="OFFICIAL_TRADING_CALENDAR",
                    required_headers=("trade_date",),
                )
                if "trade_date" not in headers or not rows:
                    raise ValueError("calendar must contain trade_date rows")
                dates = [parse_iso_date(row.get("trade_date"), "trade_date") for row in rows]
                window_from, window_to = min(dates), max(dates)
                calendar, result = validate_trading_calendar(
                    calendar_path,
                    manifest_hashes=manifest_hashes,
                    window_from=window_from,
                    window_to=window_to,
                )
                errors.extend(f"OFFICIAL_TRADING_CALENDAR_INVALID:{item}" for item in result.errors)
                if safe_regular_file(
                    calendar_path,
                    field="OFFICIAL_TRADING_CALENDAR",
                    max_bytes=64 * 1024 * 1024,
                ) != calendar_content:
                    raise ValueError("calendar changed during validation")
                calendar_sha256 = sha256_bytes(calendar_content)
            except (OSError, TypeError, ValueError) as exc:
                errors.append(f"OFFICIAL_TRADING_CALENDAR_INVALID:{exc}")

        if security_status_path is None:
            errors.append("OFFICIAL_SECURITY_STATUS_REQUIRED")
        elif not known_security_codes:
            errors.append("OFFICIAL_SECURITY_STATUS_KNOWN_CODES_REQUIRED")
        else:
            status_path = Path(security_status_path)
            try:
                status_content = safe_regular_file(
                    status_path,
                    field="OFFICIAL_SECURITY_STATUS",
                    max_bytes=64 * 1024 * 1024,
                )
                statuses, status_errors = validate_status_history(
                    status_path,
                    manifest_hashes=manifest_hashes,
                    known_codes=known_security_codes,
                )
                errors.extend(
                    f"OFFICIAL_SECURITY_STATUS_INVALID:{item}" for item in status_errors
                )
                if safe_regular_file(
                    status_path,
                    field="OFFICIAL_SECURITY_STATUS",
                    max_bytes=64 * 1024 * 1024,
                ) != status_content:
                    raise ValueError("security status changed during validation")
                status_sha256 = sha256_bytes(status_content)
            except (OSError, TypeError, ValueError) as exc:
                errors.append(f"OFFICIAL_SECURITY_STATUS_INVALID:{exc}")

        # These validators establish structure and byte binding only.  The current
        # repository has no independently authenticated receipt binding these exact
        # bytes to an official capture.  A caller-provided manifest hash set is not
        # provenance authority, so it must never promote a forecast into the ledger.
        errors.append("OUTCOME_SESSION_ARTIFACT_BOUND_OFFICIAL_AUTHORITY_REQUIRED")
        canonical_errors = tuple(sorted(set(errors)))
        return cls(
            status="PASS" if not canonical_errors else "BLOCKED",
            errors=canonical_errors,
            policy_sha256=policy_sha256,
            trading_calendar_sha256=calendar_sha256,
            security_status_sha256=status_sha256,
            calendar=calendar,
            statuses=tuple(statuses),
            board=board.lower(),
        )

    def _structural_option_one_due_at(
        self,
        *,
        security_code: str,
        decision_at: datetime,
        horizon_sessions: int,
    ) -> datetime:
        """Exercise unapproved D01 Option 1; never return policy authority."""
        if horizon_sessions <= 0:
            raise ValueError("HORIZON_NOT_POSITIVE")
        decision_day = decision_at.astimezone(KUWAIT).date()
        if not self.calendar:
            raise ValueError("OFFICIAL_TRADING_CALENDAR_REQUIRED")
        decision_row = self.calendar.get(decision_day)
        if decision_row is None or not bool(decision_row.get("is_trading_day")):
            raise ValueError("DECISION_AT_IS_NOT_AN_OFFICIAL_TRADING_SESSION")
        try:
            decision_close = parse_aware(
                f"{decision_day.isoformat()}T{decision_row.get('trade_at_last_end', '')}+03:00",
                "decision_official_session_close",
            )
        except ValueError as exc:
            raise ValueError("DECISION_OFFICIAL_SESSION_CLOSE_INVALID") from exc
        if decision_at < decision_close:
            raise ValueError("DECISION_AT_PRECEDES_OFFICIAL_SESSION_CLOSE")
        decision_status = [
            item
            for item in self.statuses
            if item.security_code == security_code
            and item.board == self.board
            and item.active_on(decision_day)
        ]
        if len(decision_status) != 1 or decision_status[0].status != "TRADING":
            raise ValueError("DECISION_SECURITY_STATUS_NOT_TRADING")
        last_day = max(self.calendar)
        current = decision_day + timedelta(days=1)
        eligible_closes: list[datetime] = []
        while current <= last_day:
            calendar_row = self.calendar.get(current)
            if calendar_row is None:
                raise ValueError(f"OFFICIAL_TRADING_CALENDAR_MISSING_DATE:{current.isoformat()}")
            if bool(calendar_row.get("is_trading_day")):
                close_time = str(calendar_row.get("trade_at_last_end", ""))
                try:
                    session_close = parse_aware(
                        f"{current.isoformat()}T{close_time}+03:00",
                        "official_session_close",
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"OFFICIAL_TRADING_CALENDAR_SESSION_CLOSE_INVALID:{current.isoformat()}"
                    ) from exc
                active = [
                    item
                    for item in self.statuses
                    if item.security_code == security_code
                    and item.board == self.board
                    and item.active_on(current)
                ]
                if len(active) != 1:
                    raise ValueError(
                        f"OFFICIAL_SECURITY_STATUS_MISSING_OR_AMBIGUOUS:{security_code}:{current.isoformat()}"
                    )
                if active[0].status == "TRADING":
                    eligible_closes.append(session_close)
                    if len(eligible_closes) == horizon_sessions:
                        return session_close
            current += timedelta(days=1)
        raise ValueError("OFFICIAL_SESSION_HORIZON_NOT_COVERED")

    def validate_due_at(
        self,
        *,
        security_code: str,
        decision_at: Any,
        outcome_due_at: Any,
        horizon_sessions: int,
        policy_hash: Any,
        trading_calendar_hash: Any,
        security_status_hash: Any,
    ) -> tuple[str, ...]:
        errors = list(self.errors)
        errors.append("OUTCOME_SESSION_ARTIFACT_BOUND_OFFICIAL_AUTHORITY_REQUIRED")
        try:
            supplied_policy = require_sha256(policy_hash, "policy_hash")
            if supplied_policy != self.policy_sha256:
                errors.append("OUTCOME_SESSION_POLICY_HASH_MISMATCH")
        except ValueError as exc:
            errors.append(str(exc))
        try:
            supplied_calendar = require_sha256(
                trading_calendar_hash, "trading_calendar_hash"
            )
            if supplied_calendar != self.trading_calendar_sha256:
                errors.append("OUTCOME_SESSION_TRADING_CALENDAR_HASH_MISMATCH")
        except ValueError as exc:
            errors.append(str(exc))
        try:
            supplied_status = require_sha256(
                security_status_hash, "security_status_hash"
            )
            if supplied_status != self.security_status_sha256:
                errors.append("OUTCOME_SESSION_SECURITY_STATUS_HASH_MISMATCH")
        except ValueError as exc:
            errors.append(str(exc))
        # D01 is OPEN and the safer recorded alternative explicitly forbids
        # producing an outcome date.  Public validation stops here and never calls
        # the private Option-1 traversal, even if all caller hashes happen to match.
        return tuple(sorted(set(errors)))


def validate_session_horizon_due_at(
    *,
    authority: OutcomeSessionAuthority | None,
    security_code: Any,
    decision_at: Any,
    outcome_due_at: Any,
    horizon_sessions: Any,
    policy_hash: Any,
    trading_calendar_hash: Any,
    security_status_hash: Any,
) -> tuple[str, ...]:
    try:
        horizon = int(horizon_sessions)
    except (TypeError, ValueError):
        return ("INVALID_HORIZON",)
    if horizon <= 0:
        return ("HORIZON_NOT_POSITIVE",)
    if authority is None:
        return ("OUTCOME_SESSION_AUTHORITY_REQUIRED",)
    if type(authority) is not OutcomeSessionAuthority:
        return ("OUTCOME_SESSION_AUTHORITY_EXACT_TYPE_REQUIRED",)
    return OutcomeSessionAuthority.validate_due_at(
        authority,
        security_code=str(security_code),
        decision_at=decision_at,
        outcome_due_at=outcome_due_at,
        horizon_sessions=horizon,
        policy_hash=policy_hash,
        trading_calendar_hash=trading_calendar_hash,
        security_status_hash=security_status_hash,
    )


__all__ = [
    "OutcomeSessionAuthority",
    "POLICY_RELATIVE_PATH",
    "validate_session_horizon_due_at",
]
