"""Fail-closed Kuwait GitHub Actions schedule contract.

The contract validates local/UTC slots, official trading-day coverage, workflow
ordering, and activation controls.  It does not collect market data or turn a
scheduled invocation into a research candidate.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .foundation_io import load_strict_json_object, safe_regular_file
from .hashing import canonical_json_bytes
from .strict import https_url, parse_aware, parse_iso_date
from .workflow_yaml import WorkflowYamlError, load_workflow_yaml


SCHEDULE_CONFIG = Path("config/kuwait_automation_schedule.json")
WORKFLOW_PATH = Path(".github/workflows/kuwait-market-pipeline.yml")
KUWAIT_TZ = ZoneInfo("Asia/Kuwait")
BACKGROUND_BACKFILL_CRON = "23 */2 * * *"

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

_AUTOMATION_ACTION_ALLOWLIST = frozenset(
    {
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    }
)
_AUTOMATION_JOB_SKELETON_SHA256 = {
    "backfill_gate": "4d0188b7e9a6824e9dec8bfc3cb6ec2d76d9ded214efa50bb63b65531e22e0a4",
    "gate": "e3961e554c3c590c5eeff5e5e0cfe72f4816a277f407571d7923a607c0a94eeb",
    "collection": "39cc6108691250854fccbc0efb4dca4fb4dd2b1c11ba80e7d80a6442ced7939e",
    "validation": "c538c53743364637f453fee2616bc532b7a6bef733e55b41a6abeea96c7ae992",
    "live_scoring": "05b512ce0a65d00ccbdb693773a1aa8875cf74f328bfc639379cb92f1f1c0d80",
    "recovery_success": "b98886271595277d9ba12306a29f1d22e9e027557c135026e070ad1cd82669a6",
    "no_trade": "1bdbe81645e8941712a0173e7ec77e655c2a8fb46ca564787105d35db21940fa",
}
_AUTOMATION_RUN_SHA256 = {
    "backfill_gate": (
        "df846cc295169b3e22f1d661d35a2a580148bc9a1dc5c4748f38e310c96f4cb1",
        "e5c94afeb8c10e096ab67db869ba1b5974ab57d47fd5c5341821ba383480206c",
        "6c8c56950e8f3af98ffe5384526d299131896e5225d3531b814140b08852c3c9",
        "5827fed219508a3b16cfe88265b25930f3c3d2deca07d2f77fb4c1a4743cc193",
        "177e52c1bda3cf8dede302304ee74618e2a7885d155d48c3463a40d6485de8fb",
        "3653b319c40bd0140d2f9abccd9e5c46025aca6fcf4fd146508d963755b7e7cd",
    ),
    "gate": (
        "df846cc295169b3e22f1d661d35a2a580148bc9a1dc5c4748f38e310c96f4cb1",
        "58f3dbcba4b4059206aa72c352c0881b873e6647aff89a0d876392eb599167a5",
        "bcb46e7dc1fdaf3428ebb2dbd513b84d2fa2761e17009624a36fcc4e326d6142",
        "a276f61f69ec92949601f07c53e2172e26dd07354127a060b427d6d8600efaf6",
        "58b205d6755d02751756559efa8406eb4d3b5cfd9010a5e36e835bf5ec8da835",
        "0c43a83b58ecde31c2d24d217ee11c3d51e3656c364aac677fd2b93a52fad007",
        "f90cf90505b3b5d627adb9dd6288fbd416d6053203844b235ee8b0f37c73db21",
        "13249ef966f1ddf3a79cf5f34363ab3e4583ddf85cd003e7bfe3d635a7aaf1ff",
    ),
    "collection": (
        "d379373ea905e179949044c326e337b1769e8301038903a38936eb75b878193d",
        "caf36839a4dea5e14d2ca7318df3e5419a72d683a222a36cbe55d3cdf9b56b53",
    ),
    "validation": (
        "c4dcccdcd07295bcd0fa644b9eedc578472ae867a4fee20b57cbd31720412744",
        "5362fb632b157f283b9135804a517da6491d939d8635435911a91f389c9e4aff",
    ),
    "live_scoring": (
        "724ceac183a3191f2ea394de56a4ea6b6b7ebfe9aef4973e4a4b30ce6dc0c5c9",
        "5362fb632b157f283b9135804a517da6491d939d8635435911a91f389c9e4aff",
    ),
    "recovery_success": (
        "cafa22f5f83c46d9a865eab19d6e0435ce17601bbf2867c167cc587f3284538f",
        "bb57f05a04288b7f6481d8fc0a362af5126c5fada2e130599d2f1f3ff6a80be0",
    ),
    "no_trade": (
        "77b9b4fa3ff8e3a7c6029b582cfea0bbcce8570348476840726e1011e776147b",
    ),
}

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
    try:
        workflow = load_workflow_yaml(content, field="Kuwait automation workflow")
    except WorkflowYamlError as exc:
        raise AutomationScheduleError("workflow must be valid unique-key YAML") from exc

    root = _exact_keys(
        workflow,
        frozenset({"name", "on", "permissions", "concurrency", "env", "jobs"}),
        "workflow",
    )
    _exact(root["name"], "Kuwait Market Pipeline", "workflow.name")

    raw_triggers = root["on"]
    if isinstance(raw_triggers, Mapping) and "schedule" in raw_triggers:
        raise AutomationScheduleError(
            "workflow must not activate cron while implementation_ready is false"
        )
    triggers = _exact_keys(
        raw_triggers,
        frozenset({"workflow_dispatch", "repository_dispatch"}),
        "workflow triggers",
    )
    expected_triggers = {
        "workflow_dispatch": {
            "inputs": {
                "mode": {
                    "description": "Fail-closed execution mode",
                    "required": "true",
                    "default": "normal",
                    "type": "choice",
                    "options": ["normal", "retry", "resume"],
                },
                "incident_id": {
                    "description": "Required for retry or resume",
                    "required": "false",
                    "type": "string",
                },
                "incident_key": {
                    "description": (
                        "Exact recovery incident state key for retry or resume"
                    ),
                    "required": "false",
                    "type": "string",
                },
                "checkpoint": {
                    "description": "Optional validated checkpoint for resume only",
                    "required": "false",
                    "type": "string",
                },
                "slot_id": {
                    "description": "Kuwait contract slot",
                    "required": "true",
                    "default": "main_1500",
                    "type": "choice",
                    "options": [row["slot_id"] for row in EXPECTED_SLOTS],
                },
            }
        },
        "repository_dispatch": {"types": ["market-recovery-request"]},
    }
    if triggers != expected_triggers:
        raise AutomationScheduleError(
            "workflow triggers do not match the locked manual/recovery contract"
        )

    _exact(root["permissions"], {"contents": "read"}, "workflow.permissions")
    _exact(
        root["concurrency"],
        {"group": "kubo-kuwait-market-ai", "cancel-in-progress": "false"},
        "workflow.concurrency",
    )
    _exact(
        root["env"],
        {"TZ": "Asia/Kuwait", "PYTHONUNBUFFERED": "1"},
        "workflow.env",
    )

    jobs = _exact_keys(
        root["jobs"],
        frozenset(
            {
                "backfill_gate",
                "gate",
                "collection",
                "validation",
                "live_scoring",
                "recovery_success",
                "no_trade",
            }
        ),
        "workflow.jobs",
    )
    expected_job_contracts = {
        "backfill_gate": {"timeout": "5", "needs": None},
        "gate": {"timeout": "5", "needs": None},
        "collection": {"timeout": "20", "needs": "gate"},
        "validation": {"timeout": "20", "needs": "collection"},
        "live_scoring": {"timeout": "15", "needs": ["gate", "validation"]},
        "recovery_success": {
            "timeout": "5",
            "needs": ["gate", "collection", "validation", "live_scoring"],
        },
        "no_trade": {
            "timeout": "5",
            "needs": ["gate", "collection", "validation", "live_scoring"],
        },
    }
    for job_name, expected in expected_job_contracts.items():
        job = jobs[job_name]
        if not isinstance(job, Mapping):
            raise AutomationScheduleError(f"workflow.jobs.{job_name} must be an object")
        _exact(
            job.get("timeout-minutes"),
            expected["timeout"],
            f"workflow.jobs.{job_name}.timeout-minutes",
        )
        _exact(
            job.get("needs"),
            expected["needs"],
            f"workflow.jobs.{job_name}.needs",
        )
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            raise AutomationScheduleError(
                f"workflow.jobs.{job_name}.steps must be a non-empty list"
            )
        permissions = job.get("permissions")
        if permissions is not None:
            if not isinstance(permissions, Mapping) or not permissions or any(
                not isinstance(value, str) or value not in {"read", "none"}
                for value in permissions.values()
            ):
                raise AutomationScheduleError(
                    f"workflow.jobs.{job_name}.permissions must remain read-only"
                )
        locked_steps: list[dict[str, Any]] = []
        run_hashes: list[str] = []
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                raise AutomationScheduleError(
                    f"workflow.jobs.{job_name}.steps[{index}] must be an object"
                )
            action = step.get("uses")
            if action is not None and re.fullmatch(
                r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}",
                str(action),
            ) is None:
                raise AutomationScheduleError(
                    f"workflow.jobs.{job_name}.steps[{index}].uses must pin a full SHA"
                )
            if action is not None and action not in _AUTOMATION_ACTION_ALLOWLIST:
                raise AutomationScheduleError(
                    f"workflow.jobs.{job_name}.steps[{index}].uses is not allowlisted"
                )
            if str(action).startswith("actions/checkout@"):
                with_args = step.get("with")
                if not isinstance(with_args, Mapping) or with_args.get(
                    "persist-credentials"
                ) != "false":
                    raise AutomationScheduleError(
                        f"workflow.jobs.{job_name} checkout must disable credentials"
                    )
            locked_step = dict(step)
            if "run" in step:
                run = step.get("run")
                if not isinstance(run, str):
                    raise AutomationScheduleError(
                        f"workflow.jobs.{job_name}.steps[{index}].run must be a string"
                    )
                run_hashes.append(hashlib.sha256(run.encode("utf-8")).hexdigest())
                locked_step["run"] = "<LOCKED_RUN>"
            locked_steps.append(locked_step)
        if tuple(run_hashes) != _AUTOMATION_RUN_SHA256[job_name]:
            raise AutomationScheduleError(
                f"workflow.jobs.{job_name} run bodies differ from the locked contract"
            )
        locked_job = {**job, "steps": locked_steps}
        skeleton_sha256 = hashlib.sha256(canonical_json_bytes(locked_job)).hexdigest()
        if skeleton_sha256 != _AUTOMATION_JOB_SKELETON_SHA256[job_name]:
            raise AutomationScheduleError(
                f"workflow.jobs.{job_name} skeleton differs from the locked contract"
            )

    _exact(
        jobs["backfill_gate"].get("if"),
        "${{ false }}",
        "workflow.jobs.backfill_gate.if",
    )
    validator_install = {
        "name": "Install pinned workflow-validator dependency",
        "run": "python -m pip install --disable-pip-version-check PyYAML==6.0.3",
    }
    for job_name in ("backfill_gate", "gate"):
        installs = [
            step
            for step in jobs[job_name]["steps"]
            if isinstance(step, Mapping)
            and step.get("name") == validator_install["name"]
        ]
        if installs != [validator_install]:
            raise AutomationScheduleError(
                f"workflow.jobs.{job_name} must install exact pinned PyYAML"
            )

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


def resolve_background_backfill_occurrence(
    *,
    actual_started_at: datetime | str,
    event_schedule: str,
) -> dict[str, Any]:
    """Resolve the latest eligible minute-23 occurrence without claiming punctuality."""

    if event_schedule != BACKGROUND_BACKFILL_CRON:
        raise AutomationScheduleError("background backfill schedule is not allowlisted")
    actual = (
        parse_aware(actual_started_at, "actual_started_at")
        if isinstance(actual_started_at, str)
        else actual_started_at
    )
    if actual.tzinfo is None or actual.utcoffset() is None:
        raise AutomationScheduleError("actual_started_at must be timezone-aware")
    actual_utc = actual.astimezone(timezone.utc)
    scheduled_hour = actual_utc.hour - (actual_utc.hour % 2)
    scheduled = actual_utc.replace(
        hour=scheduled_hour,
        minute=23,
        second=0,
        microsecond=0,
    )
    if scheduled > actual_utc:
        scheduled -= timedelta(hours=2)
    delay_seconds = int((actual_utc - scheduled).total_seconds())
    return {
        "schema_version": "1.0",
        "status": "PASS_BACKGROUND_OCCURRENCE_RESOLUTION",
        "workload_class": "BACKFILL_90D",
        "priority": 10,
        "event_schedule": BACKGROUND_BACKFILL_CRON,
        "scheduled_at": scheduled.isoformat().replace("+00:00", "Z"),
        "scheduled_at_basis": "MOST_RECENT_ELIGIBLE_CRON_OCCURRENCE",
        "actual_started_at": actual_utc.isoformat().replace("+00:00", "Z"),
        "start_delay_seconds": delay_seconds,
        "scheduled_minute_is_guaranteed": False,
        "schedule_active_claim": False,
    }


__all__ = [
    "AutomationScheduleError",
    "BACKGROUND_BACKFILL_CRON",
    "EXPECTED_SLOTS",
    "SCHEDULE_CONFIG",
    "WORKFLOW_PATH",
    "resolve_automation_run",
    "resolve_background_backfill_occurrence",
    "validate_automation_schedule",
]
