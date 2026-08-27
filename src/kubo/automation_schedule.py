"""Fail-closed Kuwait GitHub Actions schedule contract.

The contract validates local/UTC slots, official trading-day coverage, workflow
ordering, and activation controls.  It does not collect market data or turn a
scheduled invocation into a research candidate.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .foundation_io import load_strict_json_object, safe_regular_file
from .strict import https_url, parse_aware, parse_iso_date


SCHEDULE_CONFIG = Path("config/kuwait_automation_schedule.json")
WORKFLOW_PATH = Path(".github/workflows/kuwait-market-ai.yml")
KUWAIT_TZ = ZoneInfo("Asia/Kuwait")

EXPECTED_MARKET = {
    "jurisdiction_code": "KW",
    "market_name": "BOURSA_KUWAIT",
    "currency": "KWD",
    "timezone": "Asia/Kuwait",
}
EXPECTED_ACTIVATION = {
    "enabled_variable": "KUBO_KUWAIT_AUTOMATION_ENABLED",
    "admission_variable": "KUBO_KUWAIT_DATA_ADMISSION_READY",
    "required_secrets": [
        "KUBO_AUTHORIZED_SOURCE_ACCESS",
        "KUBO_DRIVE_RUNTIME_CONFIG",
    ],
    "implementation_ready": False,
    "blocked_reason": "REAL_SOURCE_ADMISSION_NOT_COMPLETE",
}
EXPECTED_EXECUTION = {
    "stage_order": ["collection", "validation", "live_scoring"],
    "concurrency_group": "kubo-kuwait-market-ai",
    "cancel_in_progress": False,
    "timeouts_minutes": {
        "gate": 5,
        "collection": 20,
        "validation": 20,
        "live_scoring": 15,
    },
    "retry_policy": {"max_transient_attempts": 2, "backoff_seconds": 5},
    "scheduled_minute_is_guaranteed": False,
    "record_actual_execution_time": True,
}
EXPECTED_CLAIM_BOUNDARIES = {
    "schedule_contract_is_live_collection": False,
    "scheduled_minute_is_exactly_guaranteed": False,
    "holiday_run_may_emit_live_candidate": False,
    "missing_secret_may_be_replaced_with_placeholder": False,
    "workflow_may_submit_trade": False,
    "workflow_may_merge_code": False,
}
EXPECTED_SLOTS = [
    {
        "slot_id": "main_1500",
        "purpose": "MAIN_COLLECTION_VALIDATION",
        "cadence": "DAILY",
        "local_time": "15:00",
        "utc_time": "12:00",
        "cron": "0 12 * * *",
        "requires_trading_day": False,
        "live_scoring_requested": False,
    },
    {
        "slot_id": "live_0400",
        "purpose": "LIVE_RESEARCH_CHECK",
        "cadence": "KUWAIT_TRADING_WEEKDAYS",
        "local_time": "04:00",
        "utc_time": "01:00",
        "cron": "0 1 * * 0-4",
        "requires_trading_day": True,
        "live_scoring_requested": True,
    },
    {
        "slot_id": "live_0700",
        "purpose": "LIVE_RESEARCH_CHECK",
        "cadence": "KUWAIT_TRADING_WEEKDAYS",
        "local_time": "07:00",
        "utc_time": "04:00",
        "cron": "0 4 * * 0-4",
        "requires_trading_day": True,
        "live_scoring_requested": True,
    },
    {
        "slot_id": "market_open_0900",
        "purpose": "MARKET_OPEN_CHECK",
        "cadence": "KUWAIT_TRADING_WEEKDAYS",
        "local_time": "09:00",
        "utc_time": "06:00",
        "cron": "0 6 * * 0-4",
        "requires_trading_day": True,
        "live_scoring_requested": True,
    },
    {
        "slot_id": "live_1100",
        "purpose": "LIVE_RESEARCH_CHECK",
        "cadence": "KUWAIT_TRADING_WEEKDAYS",
        "local_time": "11:00",
        "utc_time": "08:00",
        "cron": "0 8 * * 0-4",
        "requires_trading_day": True,
        "live_scoring_requested": True,
    },
    {
        "slot_id": "live_1200",
        "purpose": "LIVE_RESEARCH_CHECK",
        "cadence": "KUWAIT_TRADING_WEEKDAYS",
        "local_time": "12:00",
        "utc_time": "09:00",
        "cron": "0 9 * * 0-4",
        "requires_trading_day": True,
        "live_scoring_requested": True,
    },
    {
        "slot_id": "live_1300",
        "purpose": "CONTINUOUS_SESSION_END_CHECK",
        "cadence": "KUWAIT_TRADING_WEEKDAYS",
        "local_time": "13:00",
        "utc_time": "10:00",
        "cron": "0 10 * * 0-4",
        "requires_trading_day": True,
        "live_scoring_requested": True,
    },
]

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "schedule_id",
        "status",
        "market",
        "official_basis",
        "activation",
        "execution",
        "slots",
        "claim_boundaries",
    }
)
_WEEKDAY_CODES = {6: "SUN", 0: "MON", 1: "TUE", 2: "WED", 3: "THU", 4: "FRI", 5: "SAT"}
_EXPECTED_HOLIDAY_DATES = (
    "2026-01-01",
    "2026-01-18",
    "2026-02-25",
    "2026-02-26",
    "2026-03-19",
    "2026-03-20",
    "2026-03-21",
    "2026-03-22",
    "2026-05-26",
    "2026-05-27",
    "2026-05-28",
    "2026-05-29",
    "2026-05-30",
    "2026-06-16",
    "2026-08-27",
)


class AutomationScheduleError(ValueError):
    """Raised when the Kuwait schedule or its workflow weakens the contract."""


def _exact(value: Any, expected: Any, field: str) -> None:
    if value != expected:
        raise AutomationScheduleError(f"{field} does not match the locked contract")


def _exact_keys(value: Any, expected: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AutomationScheduleError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != expected:
        raise AutomationScheduleError(
            f"{field} has missing={sorted(expected - actual)} unknown={sorted(actual - expected)}"
        )
    return value


def _parse_hhmm(value: Any, field: str) -> time:
    text = str(value or "")
    if not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", text):
        raise AutomationScheduleError(f"{field} must be HH:MM")
    hour, minute = (int(part) for part in text.split(":"))
    if hour > 23:
        raise AutomationScheduleError(f"{field} has an invalid hour")
    return time(hour, minute)


def _validate_workflow(path: Path) -> str:
    try:
        content = safe_regular_file(path, field="Kuwait automation workflow", max_bytes=256 * 1024)
        text = content.decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise AutomationScheduleError(f"cannot read workflow safely: {path}") from exc
    if "\t" in text:
        raise AutomationScheduleError("workflow must not contain tab indentation")
    crons = re.findall(r'^\s*- cron: "([^"]+)"\s*$', text, flags=re.MULTILINE)
    expected_crons = [row["cron"] for row in EXPECTED_SLOTS]
    if crons != expected_crons:
        raise AutomationScheduleError("workflow cron order differs from the locked slots")
    required = (
        "permissions:\n  contents: read",
        "group: kubo-kuwait-market-ai",
        "cancel-in-progress: false",
        "timeout-minutes: 5",
        "timeout-minutes: 20",
        "timeout-minutes: 15",
        "needs: gate",
        "needs: collection",
        "needs: [gate, validation]",
        "persist-credentials: false",
        "KUBO_KUWAIT_AUTOMATION_ENABLED",
        "KUBO_KUWAIT_DATA_ADMISSION_READY",
        "KUBO_AUTHORIZED_SOURCE_ACCESS",
        "KUBO_DRIVE_RUNTIME_CONFIG",
        "github.run_id",
        "Safety tripwire",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise AutomationScheduleError(f"workflow is missing locked markers: {missing}")
    if re.search(r"\b(push|pull_request):", text):
        raise AutomationScheduleError("automation workflow must not push or open pull requests")
    return hashlib.sha256(content).hexdigest()


def _load_validated(
    project_root: Path,
    *,
    config_path: Path | None = None,
    workflow_path: Path | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    path = config_path or project_root / SCHEDULE_CONFIG
    workflow = workflow_path or project_root / WORKFLOW_PATH
    try:
        payload, content = load_strict_json_object(
            path, field="Kuwait automation schedule", max_bytes=1024 * 1024
        )
    except ValueError as exc:
        raise AutomationScheduleError(f"cannot load strict schedule JSON: {path}") from exc
    _exact_keys(payload, _ROOT_KEYS, "schedule")
    _exact(payload["schema_version"], "1.0", "schema_version")
    _exact(payload["schedule_id"], "kuwait-market-ai-sequential-v1", "schedule_id")
    _exact(
        payload["status"],
        "BLOCKED_PENDING_REAL_SOURCE_ADMISSION",
        "status",
    )
    _exact(payload["market"], EXPECTED_MARKET, "market")
    _exact(payload["activation"], EXPECTED_ACTIVATION, "activation")
    _exact(payload["execution"], EXPECTED_EXECUTION, "execution")
    _exact(payload["slots"], EXPECTED_SLOTS, "slots")
    _exact(
        payload["claim_boundaries"],
        EXPECTED_CLAIM_BOUNDARIES,
        "claim_boundaries",
    )

    basis = _exact_keys(
        payload["official_basis"],
        frozenset(
            {
                "accessed_at_utc",
                "trading_weekdays",
                "continuous_session",
                "calendar",
                "sources",
            }
        ),
        "official_basis",
    )
    accessed = parse_aware(basis["accessed_at_utc"], "official_basis.accessed_at_utc")
    if accessed.utcoffset() != timezone.utc.utcoffset(accessed):
        raise AutomationScheduleError("official_basis.accessed_at_utc must be UTC")
    _exact(
        basis["trading_weekdays"],
        ["SUN", "MON", "TUE", "WED", "THU"],
        "official_basis.trading_weekdays",
    )
    session = _exact_keys(
        basis["continuous_session"],
        frozenset({"start_local", "end_local", "trade_at_last_end_local"}),
        "official_basis.continuous_session",
    )
    _exact(
        dict(session),
        {"start_local": "09:00", "end_local": "13:00", "trade_at_last_end_local": "13:15"},
        "official_basis.continuous_session",
    )
    for key, value in session.items():
        _parse_hhmm(value, f"official_basis.continuous_session.{key}")

    calendar = _exact_keys(
        basis["calendar"],
        frozenset({"coverage_start", "coverage_end", "holidays"}),
        "official_basis.calendar",
    )
    coverage_start = parse_iso_date(calendar["coverage_start"], "coverage_start")
    coverage_end = parse_iso_date(calendar["coverage_end"], "coverage_end")
    if (coverage_start, coverage_end) != (date(2026, 1, 1), date(2026, 12, 31)):
        raise AutomationScheduleError("official calendar coverage must be the verified 2026 range")
    holidays = calendar["holidays"]
    if not isinstance(holidays, list):
        raise AutomationScheduleError("official holidays must be an array")
    holiday_dates: list[str] = []
    for index, row in enumerate(holidays):
        item = _exact_keys(
            row,
            frozenset({"date", "name", "status"}),
            f"official_basis.calendar.holidays[{index}]",
        )
        holiday = parse_iso_date(item["date"], f"holidays[{index}].date")
        if not coverage_start <= holiday <= coverage_end:
            raise AutomationScheduleError("holiday escapes calendar coverage")
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise AutomationScheduleError("holiday name must be non-empty")
        _exact(item["status"], "CONFIRMED", f"holidays[{index}].status")
        holiday_dates.append(holiday.isoformat())
    if tuple(holiday_dates) != _EXPECTED_HOLIDAY_DATES:
        raise AutomationScheduleError("official holiday dates differ from the verified source")

    sources = basis["sources"]
    if not isinstance(sources, list) or len(sources) != 3:
        raise AutomationScheduleError("official_basis.sources must contain exactly three rows")
    for index, row in enumerate(sources):
        item = _exact_keys(
            row,
            frozenset(
                {
                    "publisher",
                    "title",
                    "url",
                    "publication_date",
                    "event_date",
                    "accessed_at_utc",
                    "status",
                }
            ),
            f"official_basis.sources[{index}]",
        )
        _exact(item["publisher"], "Boursa Kuwait", f"sources[{index}].publisher")
        url = https_url(item["url"], f"sources[{index}].url")
        if not url.startswith("https://www.boursakuwait.com.kw/"):
            raise AutomationScheduleError("official schedule source must remain on Boursa Kuwait")
        if item["publication_date"] is not None:
            parse_iso_date(item["publication_date"], f"sources[{index}].publication_date")
        if item["event_date"] is not None:
            parse_iso_date(item["event_date"], f"sources[{index}].event_date")
        parse_aware(item["accessed_at_utc"], f"sources[{index}].accessed_at_utc")
        _exact(item["status"], "CONFIRMED", f"sources[{index}].status")

    anchor = date(2026, 1, 5)
    for index, slot in enumerate(EXPECTED_SLOTS):
        local_clock = _parse_hhmm(slot["local_time"], f"slots[{index}].local_time")
        expected_utc = _parse_hhmm(slot["utc_time"], f"slots[{index}].utc_time")
        local_value = datetime.combine(anchor, local_clock, KUWAIT_TZ)
        actual_utc = local_value.astimezone(timezone.utc).time().replace(tzinfo=None)
        if actual_utc != expected_utc:
            raise AutomationScheduleError(f"UTC conversion mismatch for {slot['slot_id']}")

    workflow_sha = _validate_workflow(workflow)
    return payload, content, workflow_sha


def validate_automation_schedule(
    project_root: Path | str,
    *,
    config_path: Path | str | None = None,
    workflow_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    payload, content, workflow_sha = _load_validated(
        root,
        config_path=Path(config_path).resolve() if config_path is not None else None,
        workflow_path=Path(workflow_path).resolve() if workflow_path is not None else None,
    )
    return {
        "schema_version": "1.0",
        "status": "PASS_SCHEDULE_CONTRACT",
        "schedule_id": payload["schedule_id"],
        "schedule_status": payload["status"],
        "slot_count": len(payload["slots"]),
        "schedule_sha256": hashlib.sha256(content).hexdigest(),
        "workflow_sha256": workflow_sha,
        "calendar_coverage": ["2026-01-01", "2026-12-31"],
        "holiday_count": len(payload["official_basis"]["calendar"]["holidays"]),
        "implementation_ready": False,
        "claim_boundaries": EXPECTED_CLAIM_BOUNDARIES,
    }


def _market_day_status(payload: Mapping[str, Any], local_date: date) -> str:
    basis = payload["official_basis"]
    calendar = basis["calendar"]
    start = parse_iso_date(calendar["coverage_start"], "coverage_start")
    end = parse_iso_date(calendar["coverage_end"], "coverage_end")
    if not start <= local_date <= end:
        return "CALENDAR_COVERAGE_MISSING"
    if _WEEKDAY_CODES[local_date.weekday()] not in basis["trading_weekdays"]:
        return "WEEKEND"
    holidays = {row["date"] for row in calendar["holidays"]}
    return "HOLIDAY" if local_date.isoformat() in holidays else "TRADING_DAY"


def resolve_automation_run(
    project_root: Path | str,
    *,
    actual_started_at: datetime | str,
    event_schedule: str | None = None,
    slot_id: str | None = None,
    mode: str = "EXECUTE",
    activation_enabled: bool = False,
    admission_ready: bool = False,
    source_access_configured: bool = False,
    drive_runtime_configured: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    payload, content, workflow_sha = _load_validated(root)
    actual = (
        parse_aware(actual_started_at, "actual_started_at")
        if isinstance(actual_started_at, str)
        else actual_started_at
    )
    if actual.tzinfo is None or actual.utcoffset() is None:
        raise AutomationScheduleError("actual_started_at must be timezone-aware")
    normalized_mode = str(mode).upper()
    if normalized_mode not in {"CONTRACT_CHECK", "EXECUTE"}:
        raise AutomationScheduleError("mode must be CONTRACT_CHECK or EXECUTE")
    if bool(event_schedule) == bool(slot_id):
        raise AutomationScheduleError("provide exactly one of event_schedule or slot_id")
    matches = [
        row
        for row in payload["slots"]
        if row["cron"] == event_schedule or row["slot_id"] == slot_id
    ]
    if len(matches) != 1:
        raise AutomationScheduleError("scheduled invocation does not map to exactly one slot")
    slot = matches[0]
    local_actual = actual.astimezone(KUWAIT_TZ)
    market_day = _market_day_status(payload, local_actual.date())
    missing_controls: list[str] = []
    if not activation_enabled:
        missing_controls.append(EXPECTED_ACTIVATION["enabled_variable"])
    if not admission_ready:
        missing_controls.append(EXPECTED_ACTIVATION["admission_variable"])
    if not source_access_configured:
        missing_controls.append(EXPECTED_ACTIVATION["required_secrets"][0])
    if not drive_runtime_configured:
        missing_controls.append(EXPECTED_ACTIVATION["required_secrets"][1])

    if normalized_mode == "CONTRACT_CHECK":
        status = "PASS_CONTRACT_CHECK"
    elif slot["requires_trading_day"] and market_day != "TRADING_DAY":
        status = "MAINTENANCE_ONLY_NO_TRADE"
    elif not activation_enabled:
        status = "BLOCKED_DISABLED"
    elif missing_controls:
        status = "BLOCKED_MISSING_CONTROLS"
    elif not payload["activation"]["implementation_ready"]:
        status = "BLOCKED_IMPLEMENTATION_GATE"
    else:  # pragma: no cover - deliberately unreachable in the current contract
        status = "READY_LIVE" if slot["live_scoring_requested"] else "READY_MAIN"

    executable = status in {"READY_LIVE", "READY_MAIN"}
    live = executable and bool(slot["live_scoring_requested"])
    return {
        "schema_version": "1.0",
        "status": status,
        "schedule_id": payload["schedule_id"],
        "slot_id": slot["slot_id"],
        "purpose": slot["purpose"],
        "requested_mode": normalized_mode,
        "scheduled_local_time": slot["local_time"],
        "scheduled_utc_time": slot["utc_time"],
        "actual_started_at_utc": actual.astimezone(timezone.utc).isoformat(),
        "actual_started_at_kuwait": local_actual.isoformat(),
        "market_local_date": local_actual.date().isoformat(),
        "market_day_status": market_day,
        "missing_controls": missing_controls,
        "implementation_ready": bool(payload["activation"]["implementation_ready"]),
        "should_run_collection": executable,
        "should_run_validation": executable,
        "should_run_live_scoring": live,
        "schedule_sha256": hashlib.sha256(content).hexdigest(),
        "workflow_sha256": workflow_sha,
        "claim_boundaries": {
            **EXPECTED_CLAIM_BOUNDARIES,
            "contract_check_executes_market_stages": False,
            "market_data_collected": False,
            "candidate_created": False,
        },
    }


__all__ = [
    "AutomationScheduleError",
    "EXPECTED_SLOTS",
    "SCHEDULE_CONFIG",
    "WORKFLOW_PATH",
    "resolve_automation_run",
    "validate_automation_schedule",
]
