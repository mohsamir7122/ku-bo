from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .foundation_io import require_real_directory, safe_regular_file, strict_json_object
from .hashing import hash_json, sha256_bytes
from .strict import finite_number, parse_aware, parse_iso_date, require_sha256, strict_bool


KUWAIT = ZoneInfo("Asia/Kuwait")
SCHEMA_VERSION = "1.0"
PRODUCT_ID = "KUWAIT_120D_NEXT_SESSION_RESEARCH"
DECISION_SESSION_COUNT = 40
OFFICIAL_SESSION_COUNT = DECISION_SESSION_COUNT + 1
MAX_PACKET_BYTES = 64 * 1024 * 1024
MAX_SECURITIES_PER_DECISION = 1_000
MAX_DENOMINATOR_ROWS = DECISION_SESSION_COUNT * MAX_SECURITIES_PER_DECISION

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "packet_id",
        "product_id",
        "timezone",
        "created_at",
        "evidence_classification",
        "rights_status",
        "data_foundation_status",
        "final_authority_receipt_sha256",
        "trading_calendar_sha256",
        "code_sha256",
        "policy_sha256",
        "policy",
        "official_sessions",
        "decisions",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "primary_label",
        "secondary_labels",
        "horizon_sessions",
        "decision_count",
        "top_k",
        "minimum_effective_decisions",
        "non_fill_policy",
        "benchmark_rule",
        "ranking_rule",
    }
)
_SESSION_FIELDS = frozenset(
    {
        "trade_date",
        "session_open_at",
        "session_close_at",
        "calendar_first_available_at",
        "raw_sha256",
        "is_trading_day",
    }
)
_DECISION_FIELDS = frozenset(
    {
        "decision_id",
        "decision_session",
        "outcome_session",
        "decision_at",
        "universe_first_available_at",
        "universe_evidence_sha256",
        "universe_sha256",
        "feature_snapshot_sha256",
        "feature_snapshot_created_at",
        "policy_sha256",
        "code_sha256",
        "expected_security_codes",
        "rows",
    }
)
_ROW_FIELDS = frozenset(
    {
        "security_code",
        "identity_valid_from",
        "identity_valid_to",
        "identity_first_available_at",
        "feature_available_at",
        "score_computed_at",
        "feature_evidence_sha256",
        "sector_code",
        "sector_valid_from",
        "sector_valid_to",
        "sector_first_available_at",
        "sector_identity_evidence_sha256",
        "outcome_observed_at",
        "outcome_evidence_sha256",
        "market_benchmark_evidence_sha256",
        "sector_benchmark_evidence_sha256",
        "corporate_action_evidence_sha256",
        "execution_evidence_sha256",
        "execution_status",
        "outcome_status",
        "entry_at",
        "exit_at",
        "entry_price_fils",
        "exit_price_fils",
        "fees_return",
        "spread_return",
        "slippage_return",
        "decision_close_fils",
        "outcome_close_fils",
        "price_adjustment_factor",
        "cash_distribution_return",
        "market_benchmark_decision_value",
        "market_benchmark_outcome_value",
        "sector_benchmark_decision_value",
        "sector_benchmark_outcome_value",
        "score",
        "rank",
        "selected",
        "abstained",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "input_sha256",
        "packet_id",
        "errors",
        "warnings",
        "metrics",
        "diagnostics",
        "agreement_rate",
        "agreement_rate_status",
        "authority_receipt_sha256",
        "authority_verified",
        "accuracy_claim_allowed",
        "claim_boundaries",
    }
)
_RESULT_DIAGNOSTIC_FIELDS = frozenset(
    {
        "decision_sessions",
        "effective_decisions",
        "process_valid_scoreable_sessions",
        "denominator_rows",
        "selected_rows",
    }
)
_RESULT_CLAIM_BOUNDARY_FIELDS = frozenset(
    {
        "historical_replay_is_prospective_accuracy",
        "absolute_up_is_primary_label",
        "market_and_sector_net_excess_are_secondary_labels",
        "modeled_costs_affect_actionable_and_excess_metrics",
        "independent_final_authority_receipt_verified",
        "probability_generated",
        "metrics_withheld_on_stop",
    }
)
_RESULT_METRIC_FIELDS = frozenset(
    {
        "decision_sessions",
        "effective_decisions",
        "denominator_rows",
        "selected_rows",
        "coverage",
        "primary_label",
        "primary_absolute_up_hits",
        "primary_selected_denominator",
        "primary_selected_directional_agreement",
        "primary_selected_wilson_95",
        "primary_top1_hits",
        "primary_top1_denominator",
        "primary_top1_directional_agreement",
        "primary_top1_wilson_95",
        "actionable_net_up_hits",
        "actionable_net_up_denominator",
        "actionable_net_up_rate",
        "secondary_labels",
        "market_net_excess_hits",
        "market_net_excess_denominator",
        "market_net_excess_rate",
        "sector_net_excess_hits",
        "sector_net_excess_denominator",
        "sector_net_excess_rate",
        "mean_selected_adjusted_gross_return",
        "mean_selected_net_return",
        "mean_selected_market_net_excess_return",
        "mean_selected_sector_net_excess_return",
        "mean_recall_at_k",
        "mean_primary_rank_ic",
        "primary_rank_ic_decisions",
        "mean_market_net_excess_rank_ic",
        "market_rank_ic_decisions",
        "mean_sector_net_excess_rank_ic",
        "sector_rank_ic_decisions",
        "probability",
    }
)
_RESULT_STOP_STATUSES = frozenset({"STOP_BACKTEST"})
_NONTRADING_OUTCOME_STATUSES = frozenset(
    {
        "NO_TRADE",
        "SUSPENDED",
        "HALTED",
        "TRADED_THEN_SUSPENDED",
        "NOT_LISTED_OR_NOT_ELIGIBLE",
    }
)


class ReplayValidationError(ValueError):
    """Stable fail-closed validation error for a replay packet."""


@dataclass(frozen=True)
class _OfficialSession:
    trade_date: date
    open_at: datetime
    close_at: datetime
    calendar_first_available_at: datetime


@dataclass(frozen=True)
class _ReplayRow:
    security_code: str
    score: float | None
    rank: int | None
    selected: bool
    abstained: bool
    gross_return: float
    net_return: float
    market_return: float
    sector_return: float
    market_excess_return: float
    sector_excess_return: float
    absolute_up: bool
    actionable_net_up: bool
    market_excess_up: bool
    sector_excess_up: bool


@dataclass(frozen=True)
class _ReplayDecision:
    decision_id: str
    decision_session: date
    outcome_session: date
    rows: tuple[_ReplayRow, ...]


@dataclass(frozen=True)
class _ValidatedReplay:
    packet_id: str
    created_at: datetime
    top_k: int
    minimum_effective_decisions: int
    decisions: tuple[_ReplayDecision, ...]


def _fail(field: str, code: str) -> None:
    raise ReplayValidationError(f"{field}:{code}")


def _exact_object(value: Any, fields: frozenset[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(field, "OBJECT_REQUIRED")
    actual = set(value)
    if actual != fields:
        missing = ",".join(sorted(fields - actual)) or "-"
        extra = ",".join(sorted(actual - fields)) or "-"
        _fail(field, f"UNKNOWN_OR_MISSING_FIELDS:missing={missing}:extra={extra}")
    return value


def _text(value: Any, field: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str):
        _fail(field, "STRING_REQUIRED")
    text = value.strip()
    if not text or len(text) > maximum or any(ord(character) < 32 for character in text):
        _fail(field, "INVALID_TEXT")
    return text


def _strict_int(
    value: Any,
    field: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(field, "INTEGER_REQUIRED")
    if value < minimum or (maximum is not None and value > maximum):
        _fail(field, "INTEGER_OUT_OF_RANGE")
    return value


def _kuwait_datetime(value: Any, field: str) -> datetime:
    try:
        parsed = parse_aware(value, field)
    except ValueError as exc:
        raise ReplayValidationError(str(exc)) from exc
    if parsed.utcoffset() != timedelta(hours=3):
        _fail(field, "ASIA_KUWAIT_OFFSET_REQUIRED")
    return parsed.astimezone(KUWAIT)


def _iso_date(value: Any, field: str) -> date:
    try:
        return parse_iso_date(value, field)
    except ValueError as exc:
        raise ReplayValidationError(str(exc)) from exc


def _sha256(value: Any, field: str) -> str:
    try:
        return require_sha256(value, field)
    except ValueError as exc:
        raise ReplayValidationError(str(exc)) from exc


def _number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(field, "JSON_NUMBER_REQUIRED")
    try:
        return finite_number(value, field, minimum=minimum, maximum=maximum)
    except ValueError as exc:
        raise ReplayValidationError(str(exc)) from exc


def _boolean(value: Any, field: str) -> bool:
    try:
        return strict_bool(value, field)
    except ValueError as exc:
        raise ReplayValidationError(str(exc)) from exc


def _security_code(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.isdigit() or not 1 <= len(value) <= 12:
        _fail(field, "SECURITY_CODE_INVALID")
    return value


def _optional_date(value: Any, field: str) -> date | None:
    if value is None:
        return None
    return _iso_date(value, field)


def _optional_hash(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _sha256(value, field)


def _optional_score(value: Any, field: str) -> float | None:
    if value is None:
        return None
    return _number(value, field)


def _optional_rank(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _strict_int(value, field, minimum=1, maximum=MAX_SECURITIES_PER_DECISION)


def _load_packet(packet_path: Path, runtime_root: Path) -> tuple[dict[str, Any], str]:
    try:
        root = require_real_directory(Path(runtime_root), field="runtime_root")
    except (OSError, ValueError) as exc:
        raise ReplayValidationError(f"runtime_root:INVALID:{exc}") from exc
    candidate = Path(os.path.abspath(packet_path))
    if candidate != root and root not in candidate.parents:
        _fail("packet_path", "OUTSIDE_RUNTIME_ROOT")
    try:
        content = safe_regular_file(
            candidate,
            field="forty_session_replay_packet",
            max_bytes=MAX_PACKET_BYTES,
        )
        packet = strict_json_object(content, "forty_session_replay_packet")
    except (OSError, ValueError) as exc:
        raise ReplayValidationError(f"packet_path:UNSAFE_OR_INVALID_JSON:{exc}") from exc
    return packet, sha256_bytes(content)


def _validate_policy(packet: dict[str, Any]) -> tuple[int, int]:
    policy = _exact_object(packet["policy"], _POLICY_FIELDS, "policy")
    expected_literals = {
        "primary_label": "GROSS_ADJUSTED_RETURN_GT_0",
        "horizon_sessions": 1,
        "decision_count": DECISION_SESSION_COUNT,
        "minimum_effective_decisions": DECISION_SESSION_COUNT,
        "non_fill_policy": "STOP_BACKTEST",
        "benchmark_rule": "POINT_IN_TIME_MARKET_AND_SECTOR",
        "ranking_rule": "SCORE_DESC_SECURITY_CODE_ASC",
    }
    for key, expected in expected_literals.items():
        if policy.get(key) != expected:
            _fail(f"policy.{key}", f"MUST_EQUAL:{expected}")
    if policy.get("secondary_labels") != [
        "MARKET_NET_EXCESS_GT_0",
        "SECTOR_NET_EXCESS_GT_0",
    ]:
        _fail(
            "policy.secondary_labels",
            "MUST_EQUAL:MARKET_NET_EXCESS_GT_0,SECTOR_NET_EXCESS_GT_0",
        )
    top_k = _strict_int(policy["top_k"], "policy.top_k", minimum=1, maximum=20)
    minimum_effective = _strict_int(
        policy["minimum_effective_decisions"],
        "policy.minimum_effective_decisions",
        minimum=DECISION_SESSION_COUNT,
        maximum=DECISION_SESSION_COUNT,
    )
    declared_hash = _sha256(packet["policy_sha256"], "policy_sha256")
    if hash_json(policy) != declared_hash:
        _fail("policy_sha256", "POLICY_BYTES_MISMATCH")
    return top_k, minimum_effective


def _validate_sessions(packet: dict[str, Any]) -> tuple[_OfficialSession, ...]:
    rows = packet["official_sessions"]
    if not isinstance(rows, list) or len(rows) != OFFICIAL_SESSION_COUNT:
        _fail("official_sessions", "EXACTLY_41_REQUIRED")
    sessions: list[_OfficialSession] = []
    seen_dates: set[date] = set()
    prior_date: date | None = None
    for index, raw in enumerate(rows):
        field = f"official_sessions[{index}]"
        row = _exact_object(raw, _SESSION_FIELDS, field)
        trade_date = _iso_date(row["trade_date"], f"{field}.trade_date")
        open_at = _kuwait_datetime(row["session_open_at"], f"{field}.session_open_at")
        close_at = _kuwait_datetime(row["session_close_at"], f"{field}.session_close_at")
        available_at = _kuwait_datetime(
            row["calendar_first_available_at"],
            f"{field}.calendar_first_available_at",
        )
        _sha256(row["raw_sha256"], f"{field}.raw_sha256")
        if not _boolean(row["is_trading_day"], f"{field}.is_trading_day"):
            _fail(f"{field}.is_trading_day", "OFFICIAL_TRADING_SESSION_REQUIRED")
        if open_at.date() != trade_date or close_at.date() != trade_date:
            _fail(field, "SESSION_LOCAL_DATE_MISMATCH")
        if open_at >= close_at:
            _fail(field, "SESSION_OPEN_MUST_PRECEDE_CLOSE")
        if trade_date in seen_dates or (prior_date is not None and trade_date <= prior_date):
            _fail(field, "DATES_MUST_BE_UNIQUE_AND_STRICTLY_INCREASING")
        if available_at > close_at:
            _fail(f"{field}.calendar_first_available_at", "CALENDAR_AVAILABLE_AFTER_SESSION")
        seen_dates.add(trade_date)
        prior_date = trade_date
        sessions.append(_OfficialSession(trade_date, open_at, close_at, available_at))
    declared_calendar_hash = _sha256(
        packet["trading_calendar_sha256"],
        "trading_calendar_sha256",
    )
    if hash_json(rows) != declared_calendar_hash:
        _fail("trading_calendar_sha256", "CALENDAR_BYTES_MISMATCH")
    return tuple(sessions)


def _validate_expected_codes(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not 2 <= len(value) <= MAX_SECURITIES_PER_DECISION:
        _fail(field, "SECURITY_LIST_SIZE_INVALID")
    codes = tuple(_security_code(item, f"{field}[{index}]") for index, item in enumerate(value))
    if len(set(codes)) != len(codes):
        _fail(field, "DUPLICATE_SECURITY_CODE")
    if list(codes) != sorted(codes, key=lambda item: (int(item), item)):
        _fail(field, "SECURITY_CODES_NOT_CANONICALLY_SORTED")
    return codes


def _validate_row(
    raw: Any,
    *,
    field: str,
    expected_code: str,
    decision_session: date,
    decision_at: datetime,
    feature_snapshot_created_at: datetime,
    outcome_session: _OfficialSession,
    created_at: datetime,
) -> _ReplayRow:
    row = _exact_object(raw, _ROW_FIELDS, field)
    code = _security_code(row["security_code"], f"{field}.security_code")
    if code != expected_code:
        _fail(f"{field}.security_code", "DENOMINATOR_ORDER_OR_IDENTITY_MISMATCH")

    identity_from = _iso_date(row["identity_valid_from"], f"{field}.identity_valid_from")
    identity_to = _optional_date(row["identity_valid_to"], f"{field}.identity_valid_to")
    if identity_from > decision_session or (identity_to is not None and identity_to < decision_session):
        _fail(field, "IDENTITY_NOT_EFFECTIVE_AT_DECISION")
    if identity_to is not None and identity_to < identity_from:
        _fail(field, "IDENTITY_INTERVAL_REVERSED")

    identity_available = _kuwait_datetime(
        row["identity_first_available_at"],
        f"{field}.identity_first_available_at",
    )
    feature_available = _kuwait_datetime(
        row["feature_available_at"],
        f"{field}.feature_available_at",
    )
    score_computed = _kuwait_datetime(
        row["score_computed_at"],
        f"{field}.score_computed_at",
    )
    outcome_observed = _kuwait_datetime(
        row["outcome_observed_at"],
        f"{field}.outcome_observed_at",
    )
    if identity_available > decision_at:
        _fail(field, "LOOK_AHEAD_IDENTITY")

    sector_code = _text(row["sector_code"], f"{field}.sector_code", maximum=64).upper()
    if not all(character.isalnum() or character in "_.:-" for character in sector_code):
        _fail(f"{field}.sector_code", "SECTOR_CODE_INVALID")
    sector_from = _iso_date(row["sector_valid_from"], f"{field}.sector_valid_from")
    sector_to = _optional_date(row["sector_valid_to"], f"{field}.sector_valid_to")
    if sector_from > decision_session or (
        sector_to is not None and sector_to < decision_session
    ):
        _fail(field, "SECTOR_NOT_EFFECTIVE_AT_DECISION")
    if sector_to is not None and sector_to < sector_from:
        _fail(field, "SECTOR_INTERVAL_REVERSED")
    sector_available = _kuwait_datetime(
        row["sector_first_available_at"],
        f"{field}.sector_first_available_at",
    )
    if sector_available > decision_at:
        _fail(field, "LOOK_AHEAD_SECTOR_IDENTITY")
    _sha256(
        row["sector_identity_evidence_sha256"],
        f"{field}.sector_identity_evidence_sha256",
    )
    if feature_available > decision_at:
        _fail(field, "LOOK_AHEAD_FEATURE")
    if feature_available > feature_snapshot_created_at:
        _fail(field, "FEATURE_POSTDATES_SNAPSHOT")
    if score_computed < feature_snapshot_created_at or score_computed > decision_at:
        _fail(field, "SCORE_COMPUTED_OUTSIDE_POINT_IN_TIME_WINDOW")
    if outcome_observed < outcome_session.close_at:
        _fail(field, "OUTCOME_OBSERVED_BEFORE_OFFICIAL_CLOSE")
    if outcome_observed > created_at:
        _fail(field, "OUTCOME_OBSERVED_AFTER_PACKET_CREATION")

    _sha256(row["feature_evidence_sha256"], f"{field}.feature_evidence_sha256")
    _sha256(row["outcome_evidence_sha256"], f"{field}.outcome_evidence_sha256")
    _sha256(
        row["market_benchmark_evidence_sha256"],
        f"{field}.market_benchmark_evidence_sha256",
    )
    _sha256(
        row["sector_benchmark_evidence_sha256"],
        f"{field}.sector_benchmark_evidence_sha256",
    )
    outcome_status = row["outcome_status"]
    if outcome_status in _NONTRADING_OUTCOME_STATUSES:
        selected_without_outcome = _boolean(row["selected"], f"{field}.selected")
        execution_status_without_outcome = row["execution_status"]
        execution_hash_without_outcome = row["execution_evidence_sha256"]
        if selected_without_outcome:
            if execution_status_without_outcome not in {
                "NON_FILL",
                "SUSPENDED",
                "HALTED",
                "NO_EXECUTABLE_PRICE",
            }:
                _fail(field, "SELECTED_NONTRADING_ROW_REQUIRES_NONFILL_STATUS")
            _sha256(
                execution_hash_without_outcome,
                f"{field}.execution_evidence_sha256",
            )
        elif (
            execution_status_without_outcome != "NOT_SELECTED"
            or execution_hash_without_outcome is not None
        ):
            _fail(field, "NON_SELECTED_EXECUTION_MUST_REMAIN_NULL")
        if any(
            row[field_name] is not None
            for field_name in (
                "entry_at",
                "exit_at",
                "entry_price_fils",
                "exit_price_fils",
                "fees_return",
                "spread_return",
                "slippage_return",
            )
        ):
            _fail(field, "NONTRADING_OUTCOME_EXECUTION_FIELDS_MUST_BE_NULL")
        if (
            outcome_status != "TRADED_THEN_SUSPENDED"
            and row["outcome_close_fils"] is not None
        ):
            _fail(field, "NONTRADING_OUTCOME_MUST_NOT_CONTAIN_SYNTHETIC_CLOSE")
        _fail(
            field,
            "OUTCOME_SESSION_POLICY_NOT_FROZEN:"
            f"KU-BO-008-D01:{outcome_status}",
        )
    if outcome_status != "OBSERVED_TRADING_OUTCOME":
        _fail(field, "UNKNOWN_OUTCOME_STATUS")
    ca_hash = _optional_hash(
        row["corporate_action_evidence_sha256"],
        f"{field}.corporate_action_evidence_sha256",
    )

    decision_close = _number(row["decision_close_fils"], f"{field}.decision_close_fils", minimum=0.001)
    outcome_close = _number(row["outcome_close_fils"], f"{field}.outcome_close_fils", minimum=0.001)
    adjustment = _number(
        row["price_adjustment_factor"],
        f"{field}.price_adjustment_factor",
        minimum=0.0000001,
    )
    distribution = _number(
        row["cash_distribution_return"],
        f"{field}.cash_distribution_return",
        minimum=0,
        maximum=10,
    )
    if ca_hash is None and (adjustment != 1.0 or distribution != 0.0):
        _fail(field, "CORPORATE_ACTION_EVIDENCE_REQUIRED")
    market_decision = _number(
        row["market_benchmark_decision_value"],
        f"{field}.market_benchmark_decision_value",
        minimum=0.0000001,
    )
    market_outcome = _number(
        row["market_benchmark_outcome_value"],
        f"{field}.market_benchmark_outcome_value",
        minimum=0.0000001,
    )
    sector_decision = _number(
        row["sector_benchmark_decision_value"],
        f"{field}.sector_benchmark_decision_value",
        minimum=0.0000001,
    )
    sector_outcome = _number(
        row["sector_benchmark_outcome_value"],
        f"{field}.sector_benchmark_outcome_value",
        minimum=0.0000001,
    )
    gross_return = outcome_close * adjustment / decision_close - 1.0 + distribution
    net_return = gross_return
    market_return = market_outcome / market_decision - 1.0
    sector_return = sector_outcome / sector_decision - 1.0

    selected = _boolean(row["selected"], f"{field}.selected")
    abstained = _boolean(row["abstained"], f"{field}.abstained")
    execution_status = row["execution_status"]
    execution_hash = row["execution_evidence_sha256"]
    if selected:
        _sha256(execution_hash, f"{field}.execution_evidence_sha256")
        if execution_status != "FILLED":
            _fail(field, "NON_FILL_OR_UNRESOLVED_EXECUTION_FORBIDDEN")
        entry_at = _kuwait_datetime(row["entry_at"], f"{field}.entry_at")
        exit_at = _kuwait_datetime(row["exit_at"], f"{field}.exit_at")
        if entry_at < outcome_session.open_at or entry_at > outcome_session.close_at:
            _fail(field, "ENTRY_OUTSIDE_OUTCOME_SESSION")
        if exit_at != outcome_session.close_at or exit_at < entry_at:
            _fail(field, "EXIT_MUST_EQUAL_OUTCOME_SESSION_CLOSE")
        entry_price = _number(
            row["entry_price_fils"],
            f"{field}.entry_price_fils",
            minimum=0.001,
        )
        exit_price = _number(
            row["exit_price_fils"],
            f"{field}.exit_price_fils",
            minimum=0.001,
        )
        fees = _number(row["fees_return"], f"{field}.fees_return", minimum=0, maximum=1)
        spread = _number(
            row["spread_return"], f"{field}.spread_return", minimum=0, maximum=1
        )
        slippage = _number(
            row["slippage_return"],
            f"{field}.slippage_return",
            minimum=0,
            maximum=1,
        )
        net_return = exit_price / entry_price - 1.0 - fees - spread - slippage
    elif execution_status != "NOT_SELECTED" or execution_hash is not None:
        _fail(field, "NON_SELECTED_EXECUTION_MUST_REMAIN_NULL")
    elif any(
        row[field_name] is not None
        for field_name in (
            "entry_at",
            "exit_at",
            "entry_price_fils",
            "exit_price_fils",
            "fees_return",
            "spread_return",
            "slippage_return",
        )
    ):
        _fail(field, "NON_SELECTED_EXECUTION_MUST_REMAIN_NULL")

    market_excess = net_return - market_return
    sector_excess = net_return - sector_return
    if not all(
        math.isfinite(item)
        for item in (
            gross_return,
            net_return,
            market_return,
            sector_return,
            market_excess,
            sector_excess,
        )
    ):
        _fail(field, "NON_FINITE_DERIVED_RETURN")
    score = _optional_score(row["score"], f"{field}.score")
    rank = _optional_rank(row["rank"], f"{field}.rank")
    if abstained:
        if selected or score is not None or rank is not None:
            _fail(field, "ABSTENTION_SEMANTICS_INVALID")
    elif score is None or rank is None:
        _fail(field, "SCORED_ROW_REQUIRES_SCORE_AND_RANK")

    return _ReplayRow(
        security_code=code,
        score=score,
        rank=rank,
        selected=selected,
        abstained=abstained,
        gross_return=gross_return,
        net_return=net_return,
        market_return=market_return,
        sector_return=sector_return,
        market_excess_return=market_excess,
        sector_excess_return=sector_excess,
        absolute_up=gross_return > 0.0,
        actionable_net_up=net_return > 0.0,
        market_excess_up=market_excess > 0.0,
        sector_excess_up=sector_excess > 0.0,
    )


def _validate_decisions(
    packet: dict[str, Any],
    *,
    sessions: tuple[_OfficialSession, ...],
    created_at: datetime,
    top_k: int,
) -> tuple[_ReplayDecision, ...]:
    raw_decisions = packet["decisions"]
    if not isinstance(raw_decisions, list) or len(raw_decisions) != DECISION_SESSION_COUNT:
        _fail("decisions", "EXACTLY_40_REQUIRED")
    policy_hash = _sha256(packet["policy_sha256"], "policy_sha256")
    code_hash = _sha256(packet["code_sha256"], "code_sha256")
    decisions: list[_ReplayDecision] = []
    seen_ids: set[str] = set()
    total_rows = 0
    for index, raw in enumerate(raw_decisions):
        field = f"decisions[{index}]"
        decision = _exact_object(raw, _DECISION_FIELDS, field)
        decision_id = _text(decision["decision_id"], f"{field}.decision_id")
        if decision_id in seen_ids:
            _fail(f"{field}.decision_id", "DUPLICATE_DECISION_ID")
        seen_ids.add(decision_id)
        decision_day = _iso_date(decision["decision_session"], f"{field}.decision_session")
        outcome_day = _iso_date(decision["outcome_session"], f"{field}.outcome_session")
        if decision_day != sessions[index].trade_date or outcome_day != sessions[index + 1].trade_date:
            _fail(field, "DECISION_OR_OUTCOME_NOT_CONSECUTIVE_OFFICIAL_SESSION")
        decision_at = _kuwait_datetime(decision["decision_at"], f"{field}.decision_at")
        if decision_at < sessions[index].close_at:
            _fail(f"{field}.decision_at", "DECISION_PRECEDES_OFFICIAL_CLOSE")
        if decision_at >= sessions[index + 1].open_at:
            _fail(f"{field}.decision_at", "DECISION_NOT_BEFORE_OUTCOME_OPEN")
        if sessions[index].calendar_first_available_at > decision_at:
            _fail(field, "DECISION_SESSION_CALENDAR_LOOK_AHEAD")
        if sessions[index + 1].calendar_first_available_at > decision_at:
            _fail(field, "OUTCOME_SESSION_CALENDAR_NOT_KNOWN_AT_DECISION")
        universe_available = _kuwait_datetime(
            decision["universe_first_available_at"],
            f"{field}.universe_first_available_at",
        )
        if universe_available > decision_at:
            _fail(field, "LOOK_AHEAD_UNIVERSE")
        _sha256(decision["universe_evidence_sha256"], f"{field}.universe_evidence_sha256")
        _sha256(decision["feature_snapshot_sha256"], f"{field}.feature_snapshot_sha256")
        feature_snapshot_created_at = _kuwait_datetime(
            decision["feature_snapshot_created_at"],
            f"{field}.feature_snapshot_created_at",
        )
        if feature_snapshot_created_at > decision_at:
            _fail(field, "LOOK_AHEAD_FEATURE_SNAPSHOT")
        if _sha256(decision["policy_sha256"], f"{field}.policy_sha256") != policy_hash:
            _fail(field, "POLICY_HASH_MISMATCH")
        if _sha256(decision["code_sha256"], f"{field}.code_sha256") != code_hash:
            _fail(field, "CODE_HASH_MISMATCH")
        expected_codes = _validate_expected_codes(
            decision["expected_security_codes"],
            f"{field}.expected_security_codes",
        )
        expected_universe_hash = hash_json(
            {
                "decision_session": decision_day.isoformat(),
                "security_codes": list(expected_codes),
            }
        )
        if _sha256(decision["universe_sha256"], f"{field}.universe_sha256") != expected_universe_hash:
            _fail(field, "UNIVERSE_HASH_MISMATCH")
        raw_rows = decision["rows"]
        if not isinstance(raw_rows, list) or len(raw_rows) != len(expected_codes):
            _fail(field, "FULL_DENOMINATOR_MISMATCH")
        total_rows += len(raw_rows)
        if total_rows > MAX_DENOMINATOR_ROWS:
            _fail("decisions", "DENOMINATOR_ROW_LIMIT_EXCEEDED")
        rows = tuple(
            _validate_row(
                row,
                field=f"{field}.rows[{row_index}]",
                expected_code=expected_codes[row_index],
                decision_session=decision_day,
                decision_at=decision_at,
                feature_snapshot_created_at=feature_snapshot_created_at,
                outcome_session=sessions[index + 1],
                created_at=created_at,
            )
            for row_index, row in enumerate(raw_rows)
        )
        scored = sorted(
            (row for row in rows if not row.abstained),
            key=lambda row: int(row.rank or 0),
        )
        ranks = [int(row.rank or 0) for row in scored]
        if ranks != list(range(1, len(scored) + 1)):
            _fail(field, "RANKS_MUST_BE_UNIQUE_AND_CONTIGUOUS")
        score_ranked = sorted(
            scored,
            key=lambda row: (
                -float(row.score),
                int(row.security_code),
                row.security_code,
            ),
        )
        if any(
            row.rank != expected_rank
            for expected_rank, row in enumerate(score_ranked, start=1)
        ):
            _fail(field, "RANK_MUST_DERIVE_FROM_SCORE_DESC_SECURITY_CODE_ASC")
        expected_selected = {
            row.security_code for row in score_ranked[: min(top_k, len(score_ranked))]
        }
        actual_selected = {row.security_code for row in rows if row.selected}
        if actual_selected != expected_selected:
            _fail(field, "SELECTED_ROWS_MUST_EQUAL_TOP_K")
        decisions.append(_ReplayDecision(decision_id, decision_day, outcome_day, rows))
    return tuple(decisions)


def validate_forty_session_replay_packet(packet: Any) -> _ValidatedReplay:
    """Validate and normalize one in-memory 40-session replay packet.

    This is structural and point-in-time validation of the supplied evidence
    contract.  File safety and input-byte hashing are applied by
    :func:`evaluate_forty_session_replay`.
    """

    value = _exact_object(packet, _TOP_LEVEL_FIELDS, "packet")
    if value["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version", f"MUST_EQUAL:{SCHEMA_VERSION}")
    packet_id = _text(value["packet_id"], "packet_id")
    if value["product_id"] != PRODUCT_ID:
        _fail("product_id", f"MUST_EQUAL:{PRODUCT_ID}")
    if value["timezone"] != "Asia/Kuwait":
        _fail("timezone", "MUST_EQUAL:Asia/Kuwait")
    if value["evidence_classification"] != "PROVEN_REAL_EVIDENCE":
        _fail("evidence_classification", "PROVEN_REAL_EVIDENCE_REQUIRED")
    if value["rights_status"] != "RESEARCH_USE_AUTHORIZED":
        _fail("rights_status", "RESEARCH_USE_AUTHORIZED_REQUIRED")
    if value["data_foundation_status"] != "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST":
        _fail("data_foundation_status", "REAL_DATA_FOUNDATION_READY_REQUIRED")
    created_at = _kuwait_datetime(value["created_at"], "created_at")
    _sha256(value["final_authority_receipt_sha256"], "final_authority_receipt_sha256")
    _sha256(value["trading_calendar_sha256"], "trading_calendar_sha256")
    _sha256(value["code_sha256"], "code_sha256")
    top_k, minimum_effective = _validate_policy(value)
    sessions = _validate_sessions(value)
    decisions = _validate_decisions(
        value,
        sessions=sessions,
        created_at=created_at,
        top_k=top_k,
    )
    return _ValidatedReplay(packet_id, created_at, top_k, minimum_effective, decisions)


def _rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][1] == indexed[position][1]:
            end += 1
        average_rank = (position + 1 + end) / 2
        for cursor in range(position, end):
            ranks[indexed[cursor][0]] = average_rank
        position = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def _spearman(left: list[float], right: list[float]) -> float | None:
    return _pearson(_rank(left), _rank(right))


def _wilson_interval(hits: int, denominator: int, *, z: float = 1.959963984540054) -> list[float] | None:
    """Return a two-sided 95% Wilson interval without implying calibration."""

    if denominator <= 0:
        return None
    proportion = hits / denominator
    z2 = z * z
    scale = 1.0 + z2 / denominator
    centre = (proportion + z2 / (2.0 * denominator)) / scale
    margin = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / denominator
            + z2 / (4.0 * denominator * denominator)
        )
        / scale
    )
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def _metrics(replay: _ValidatedReplay) -> tuple[dict[str, Any] | None, dict[str, int]]:
    selected_rows: list[_ReplayRow] = []
    primary_rank_ics: list[float] = []
    market_rank_ics: list[float] = []
    sector_rank_ics: list[float] = []
    recall_at_k: list[float] = []
    top1_rows: list[_ReplayRow] = []
    effective_decisions = 0
    denominator_rows = 0
    for decision in replay.decisions:
        rows = list(decision.rows)
        denominator_rows += len(rows)
        selected = [row for row in rows if row.selected]
        selected_rows.extend(selected)
        if selected:
            effective_decisions += 1
        top1 = [row for row in selected if row.rank == 1]
        if top1:
            top1_rows.append(top1[0])
        scored = [row for row in rows if not row.abstained and row.score is not None]
        if len(scored) >= 2:
            scores = [float(row.score) for row in scored]
            for values, destination in (
                ([row.gross_return for row in scored], primary_rank_ics),
                ([row.market_excess_return for row in scored], market_rank_ics),
                ([row.sector_excess_return for row in scored], sector_rank_ics),
            ):
                rank_ic = _spearman(scores, values)
                if rank_ic is not None:
                    destination.append(rank_ic)
        actual_top = sorted(
            rows,
            key=lambda row: (-row.gross_return, row.security_code),
        )[: min(replay.top_k, len(rows))]
        actual_codes = {row.security_code for row in actual_top}
        selected_codes = {row.security_code for row in selected}
        if actual_codes:
            recall_at_k.append(len(actual_codes & selected_codes) / len(actual_codes))

    diagnostics = {
        "decision_sessions": len(replay.decisions),
        "effective_decisions": effective_decisions,
        "denominator_rows": denominator_rows,
        "selected_rows": len(selected_rows),
    }
    if effective_decisions < replay.minimum_effective_decisions or not selected_rows:
        return None, diagnostics

    primary_hits = sum(row.absolute_up for row in selected_rows)
    actionable_hits = sum(row.actionable_net_up for row in selected_rows)
    market_hits = sum(row.market_excess_up for row in selected_rows)
    sector_hits = sum(row.sector_excess_up for row in selected_rows)
    top1_hits = sum(row.absolute_up for row in top1_rows)
    metrics = {
        **diagnostics,
        "coverage": 1.0,
        "primary_label": "GROSS_ADJUSTED_RETURN_GT_0",
        "primary_absolute_up_hits": primary_hits,
        "primary_selected_denominator": len(selected_rows),
        "primary_selected_directional_agreement": primary_hits / len(selected_rows),
        "primary_selected_wilson_95": _wilson_interval(primary_hits, len(selected_rows)),
        "primary_top1_hits": top1_hits,
        "primary_top1_denominator": len(top1_rows),
        "primary_top1_directional_agreement": top1_hits / len(top1_rows),
        "primary_top1_wilson_95": _wilson_interval(top1_hits, len(top1_rows)),
        "actionable_net_up_hits": actionable_hits,
        "actionable_net_up_denominator": len(selected_rows),
        "actionable_net_up_rate": actionable_hits / len(selected_rows),
        "secondary_labels": [
            "MARKET_NET_EXCESS_GT_0",
            "SECTOR_NET_EXCESS_GT_0",
        ],
        "market_net_excess_hits": market_hits,
        "market_net_excess_denominator": len(selected_rows),
        "market_net_excess_rate": market_hits / len(selected_rows),
        "sector_net_excess_hits": sector_hits,
        "sector_net_excess_denominator": len(selected_rows),
        "sector_net_excess_rate": sector_hits / len(selected_rows),
        "mean_selected_adjusted_gross_return": mean(row.gross_return for row in selected_rows),
        "mean_selected_net_return": mean(row.net_return for row in selected_rows),
        "mean_selected_market_net_excess_return": mean(
            row.market_excess_return for row in selected_rows
        ),
        "mean_selected_sector_net_excess_return": mean(
            row.sector_excess_return for row in selected_rows
        ),
        "mean_recall_at_k": mean(recall_at_k),
        "mean_primary_rank_ic": mean(primary_rank_ics) if primary_rank_ics else None,
        "primary_rank_ic_decisions": len(primary_rank_ics),
        "mean_market_net_excess_rank_ic": (
            mean(market_rank_ics) if market_rank_ics else None
        ),
        "market_rank_ic_decisions": len(market_rank_ics),
        "mean_sector_net_excess_rank_ic": (
            mean(sector_rank_ics) if sector_rank_ics else None
        ),
        "sector_rank_ic_decisions": len(sector_rank_ics),
        "probability": None,
    }
    return metrics, diagnostics


def _non_performance_diagnostics(replay: _ValidatedReplay) -> dict[str, int]:
    """Describe contract coverage without scoring any realized return."""

    rows = [row for decision in replay.decisions for row in decision.rows]
    return {
        "decision_sessions": len(replay.decisions),
        "effective_decisions": sum(
            any(row.selected for row in decision.rows) for decision in replay.decisions
        ),
        "denominator_rows": len(rows),
        "selected_rows": sum(row.selected for row in rows),
    }


def _validate_result_messages(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        _fail(field, "ARRAY_REQUIRED")
    messages: list[str] = []
    for index, message in enumerate(value):
        if not isinstance(message, str) or not message:
            _fail(f"{field}[{index}]", "NONEMPTY_STRING_REQUIRED")
        messages.append(message)
    if len(messages) != len(set(messages)):
        _fail(field, "DUPLICATE_MESSAGES_FORBIDDEN")
    return messages


def _validate_result_diagnostics(value: Any) -> dict[str, int]:
    diagnostics = _exact_object(
        value,
        _RESULT_DIAGNOSTIC_FIELDS,
        "result.diagnostics",
    )
    decision_sessions = _strict_int(
        diagnostics["decision_sessions"],
        "result.diagnostics.decision_sessions",
        minimum=0,
        maximum=DECISION_SESSION_COUNT,
    )
    effective_decisions = _strict_int(
        diagnostics["effective_decisions"],
        "result.diagnostics.effective_decisions",
        minimum=0,
        maximum=DECISION_SESSION_COUNT,
    )
    process_valid = _strict_int(
        diagnostics["process_valid_scoreable_sessions"],
        "result.diagnostics.process_valid_scoreable_sessions",
        minimum=0,
        maximum=DECISION_SESSION_COUNT,
    )
    denominator_rows = _strict_int(
        diagnostics["denominator_rows"],
        "result.diagnostics.denominator_rows",
        minimum=0,
        maximum=MAX_DENOMINATOR_ROWS,
    )
    selected_rows = _strict_int(
        diagnostics["selected_rows"],
        "result.diagnostics.selected_rows",
        minimum=0,
        maximum=DECISION_SESSION_COUNT * 20,
    )
    if effective_decisions > decision_sessions:
        _fail("result.diagnostics", "EFFECTIVE_EXCEEDS_DECISION_SESSIONS")
    if process_valid > effective_decisions:
        _fail("result.diagnostics", "PROCESS_VALID_EXCEEDS_EFFECTIVE_DECISIONS")
    if selected_rows > denominator_rows:
        _fail("result.diagnostics", "SELECTED_EXCEEDS_DENOMINATOR_ROWS")
    return {
        "decision_sessions": decision_sessions,
        "effective_decisions": effective_decisions,
        "process_valid_scoreable_sessions": process_valid,
        "denominator_rows": denominator_rows,
        "selected_rows": selected_rows,
    }


def _validate_result_claim_boundaries(
    value: Any,
    *,
    authority_verified: bool,
    metrics_withheld: bool,
) -> None:
    boundaries = _exact_object(
        value,
        _RESULT_CLAIM_BOUNDARY_FIELDS,
        "result.claim_boundaries",
    )
    expected = {
        "historical_replay_is_prospective_accuracy": False,
        "absolute_up_is_primary_label": True,
        "market_and_sector_net_excess_are_secondary_labels": True,
        "modeled_costs_affect_actionable_and_excess_metrics": True,
        "independent_final_authority_receipt_verified": authority_verified,
        "probability_generated": False,
        "metrics_withheld_on_stop": metrics_withheld,
    }
    for name, expected_value in expected.items():
        actual = _boolean(boundaries[name], f"result.claim_boundaries.{name}")
        if actual is not expected_value:
            _fail(f"result.claim_boundaries.{name}", f"MUST_EQUAL:{expected_value}")


def _validate_result_rate(value: Any, field: str) -> float:
    return _number(value, field, minimum=0.0, maximum=1.0)


def _validate_result_sha256(value: Any, field: str) -> str:
    digest = _sha256(value, field)
    if value != digest:
        _fail(field, "LOWERCASE_SHA256_REQUIRED")
    return digest


def _validate_result_rate_identity(
    metrics: dict[str, Any],
    *,
    hits_field: str,
    denominator_field: str,
    rate_field: str,
) -> float:
    hits = _strict_int(
        metrics[hits_field],
        f"result.metrics.{hits_field}",
        minimum=0,
        maximum=DECISION_SESSION_COUNT * 20,
    )
    denominator = _strict_int(
        metrics[denominator_field],
        f"result.metrics.{denominator_field}",
        minimum=1,
        maximum=DECISION_SESSION_COUNT * 20,
    )
    if hits > denominator:
        _fail(f"result.metrics.{hits_field}", "HITS_EXCEED_DENOMINATOR")
    rate = _validate_result_rate(
        metrics[rate_field],
        f"result.metrics.{rate_field}",
    )
    if not math.isclose(rate, hits / denominator, rel_tol=0.0, abs_tol=1e-12):
        _fail(f"result.metrics.{rate_field}", "RATE_DENOMINATOR_MISMATCH")
    return rate


def _validate_result_wilson_interval(
    value: Any,
    *,
    hits: int,
    denominator: int,
    field: str,
) -> None:
    if not isinstance(value, list) or len(value) != 2:
        _fail(field, "TWO_VALUE_ARRAY_REQUIRED")
    lower = _validate_result_rate(value[0], f"{field}[0]")
    upper = _validate_result_rate(value[1], f"{field}[1]")
    if lower > upper:
        _fail(field, "LOWER_BOUND_EXCEEDS_UPPER_BOUND")
    expected = _wilson_interval(hits, denominator)
    if expected is None or not all(
        math.isclose(actual, target, rel_tol=0.0, abs_tol=1e-12)
        for actual, target in zip((lower, upper), expected)
    ):
        _fail(field, "WILSON_INTERVAL_MISMATCH")


def _validate_result_rank_ic(
    metrics: dict[str, Any],
    *,
    mean_field: str,
    count_field: str,
) -> None:
    count = _strict_int(
        metrics[count_field],
        f"result.metrics.{count_field}",
        minimum=0,
        maximum=DECISION_SESSION_COUNT,
    )
    rank_ic = metrics[mean_field]
    if rank_ic is None:
        if count != 0:
            _fail(f"result.metrics.{mean_field}", "NULL_REQUIRES_ZERO_DECISIONS")
        return
    _number(
        rank_ic,
        f"result.metrics.{mean_field}",
        minimum=-1.0,
        maximum=1.0,
    )
    if count == 0:
        _fail(f"result.metrics.{count_field}", "NONZERO_REQUIRED_FOR_MEASURED_IC")


def _validate_pass_metrics(
    value: Any,
    *,
    diagnostics: dict[str, int],
) -> dict[str, Any]:
    metrics = _exact_object(value, _RESULT_METRIC_FIELDS, "result.metrics")
    for name in ("decision_sessions", "effective_decisions"):
        measured = _strict_int(
            metrics[name],
            f"result.metrics.{name}",
            minimum=DECISION_SESSION_COUNT,
            maximum=DECISION_SESSION_COUNT,
        )
        if measured != diagnostics[name]:
            _fail(f"result.metrics.{name}", "DIAGNOSTICS_MISMATCH")
    denominator_rows = _strict_int(
        metrics["denominator_rows"],
        "result.metrics.denominator_rows",
        minimum=DECISION_SESSION_COUNT * 2,
        maximum=MAX_DENOMINATOR_ROWS,
    )
    selected_rows = _strict_int(
        metrics["selected_rows"],
        "result.metrics.selected_rows",
        minimum=DECISION_SESSION_COUNT,
        maximum=DECISION_SESSION_COUNT * 20,
    )
    if denominator_rows != diagnostics["denominator_rows"]:
        _fail("result.metrics.denominator_rows", "DIAGNOSTICS_MISMATCH")
    if selected_rows != diagnostics["selected_rows"]:
        _fail("result.metrics.selected_rows", "DIAGNOSTICS_MISMATCH")
    if selected_rows > denominator_rows:
        _fail("result.metrics.selected_rows", "SELECTED_EXCEEDS_DENOMINATOR_ROWS")
    coverage = _number(metrics["coverage"], "result.metrics.coverage")
    if coverage != 1.0:
        _fail("result.metrics.coverage", "MUST_EQUAL:1.0")
    if metrics["primary_label"] != "GROSS_ADJUSTED_RETURN_GT_0":
        _fail(
            "result.metrics.primary_label",
            "MUST_EQUAL:GROSS_ADJUSTED_RETURN_GT_0",
        )
    if metrics["secondary_labels"] != [
        "MARKET_NET_EXCESS_GT_0",
        "SECTOR_NET_EXCESS_GT_0",
    ]:
        _fail("result.metrics.secondary_labels", "EXACT_LABELS_REQUIRED")
    if metrics["probability"] is not None:
        _fail("result.metrics.probability", "NULL_REQUIRED")

    denominator_fields = (
        "primary_selected_denominator",
        "actionable_net_up_denominator",
        "market_net_excess_denominator",
        "sector_net_excess_denominator",
    )
    for name in denominator_fields:
        denominator = _strict_int(
            metrics[name],
            f"result.metrics.{name}",
            minimum=DECISION_SESSION_COUNT,
            maximum=DECISION_SESSION_COUNT * 20,
        )
        if denominator != selected_rows:
            _fail(f"result.metrics.{name}", "SELECTED_DENOMINATOR_MISMATCH")

    _validate_result_rate_identity(
        metrics,
        hits_field="primary_absolute_up_hits",
        denominator_field="primary_selected_denominator",
        rate_field="primary_selected_directional_agreement",
    )
    primary_hits = int(metrics["primary_absolute_up_hits"])
    _validate_result_wilson_interval(
        metrics["primary_selected_wilson_95"],
        hits=primary_hits,
        denominator=selected_rows,
        field="result.metrics.primary_selected_wilson_95",
    )

    top1_denominator = _strict_int(
        metrics["primary_top1_denominator"],
        "result.metrics.primary_top1_denominator",
        minimum=DECISION_SESSION_COUNT,
        maximum=DECISION_SESSION_COUNT,
    )
    _validate_result_rate_identity(
        metrics,
        hits_field="primary_top1_hits",
        denominator_field="primary_top1_denominator",
        rate_field="primary_top1_directional_agreement",
    )
    top1_hits = int(metrics["primary_top1_hits"])
    _validate_result_wilson_interval(
        metrics["primary_top1_wilson_95"],
        hits=top1_hits,
        denominator=top1_denominator,
        field="result.metrics.primary_top1_wilson_95",
    )

    for hits_field, denominator_field, rate_field in (
        (
            "actionable_net_up_hits",
            "actionable_net_up_denominator",
            "actionable_net_up_rate",
        ),
        (
            "market_net_excess_hits",
            "market_net_excess_denominator",
            "market_net_excess_rate",
        ),
        (
            "sector_net_excess_hits",
            "sector_net_excess_denominator",
            "sector_net_excess_rate",
        ),
    ):
        _validate_result_rate_identity(
            metrics,
            hits_field=hits_field,
            denominator_field=denominator_field,
            rate_field=rate_field,
        )

    for name in (
        "mean_selected_adjusted_gross_return",
        "mean_selected_net_return",
        "mean_selected_market_net_excess_return",
        "mean_selected_sector_net_excess_return",
    ):
        _number(metrics[name], f"result.metrics.{name}")
    _validate_result_rate(metrics["mean_recall_at_k"], "result.metrics.mean_recall_at_k")
    for mean_field, count_field in (
        ("mean_primary_rank_ic", "primary_rank_ic_decisions"),
        ("mean_market_net_excess_rank_ic", "market_rank_ic_decisions"),
        ("mean_sector_net_excess_rank_ic", "sector_rank_ic_decisions"),
    ):
        _validate_result_rank_ic(
            metrics,
            mean_field=mean_field,
            count_field=count_field,
        )
    return metrics


def validate_forty_session_replay_result(result: Any) -> dict[str, Any]:
    """Validate the fail-closed replay output before it reaches a caller.

    ``PASS_BACKTEST`` is deliberately rejected until an independent authority
    resolver passes a verified attestation into a separate production API.  A
    caller-authored boolean and receipt-shaped hash can never certify metrics.
    The JSON Schema may document the future PASS shape, but this public runtime
    validator only releases fail-closed stop results today.
    """

    value = _exact_object(result, _RESULT_FIELDS, "result")
    if value["schema_version"] != SCHEMA_VERSION:
        _fail("result.schema_version", f"MUST_EQUAL:{SCHEMA_VERSION}")
    status = value["status"]
    if not isinstance(status, str):
        _fail("result.status", "STRING_REQUIRED")
    if status != "PASS_BACKTEST" and status not in _RESULT_STOP_STATUSES:
        _fail("result.status", "UNKNOWN_STATUS")
    if status == "PASS_BACKTEST":
        _fail("result.status", "PASS_REQUIRES_INDEPENDENT_AUTHORITY_RESOLVER")
    if value["input_sha256"] is not None:
        _validate_result_sha256(value["input_sha256"], "result.input_sha256")
    if value["packet_id"] is not None:
        packet_id = _text(value["packet_id"], "result.packet_id")
        if packet_id != value["packet_id"]:
            _fail("result.packet_id", "CANONICAL_TEXT_REQUIRED")
    errors = _validate_result_messages(value["errors"], "result.errors")
    _validate_result_messages(value["warnings"], "result.warnings")
    diagnostics = _validate_result_diagnostics(value["diagnostics"])
    authority_verified = _boolean(
        value["authority_verified"],
        "result.authority_verified",
    )
    accuracy_claim_allowed = _boolean(
        value["accuracy_claim_allowed"],
        "result.accuracy_claim_allowed",
    )

    if status in _RESULT_STOP_STATUSES:
        if not errors:
            _fail("result.errors", "STOP_REASON_REQUIRED")
        if value["metrics"] is not None:
            _fail("result.metrics", "NULL_REQUIRED_ON_STOP")
        if value["agreement_rate"] is not None:
            _fail("result.agreement_rate", "NULL_REQUIRED_ON_STOP")
        if value["agreement_rate_status"] != "NOT_APPLICABLE":
            _fail("result.agreement_rate_status", "NOT_APPLICABLE_REQUIRED_ON_STOP")
        if value["authority_receipt_sha256"] is not None:
            _fail("result.authority_receipt_sha256", "NULL_REQUIRED_ON_STOP")
        if authority_verified:
            _fail("result.authority_verified", "FALSE_REQUIRED_ON_STOP")
        if accuracy_claim_allowed:
            _fail("result.accuracy_claim_allowed", "FALSE_REQUIRED_ON_STOP")
        _validate_result_claim_boundaries(
            value["claim_boundaries"],
            authority_verified=False,
            metrics_withheld=True,
        )
        return value

    raise AssertionError("unreachable replay result status")


def _result(
    *,
    status: str,
    input_sha256: str | None,
    packet_id: str | None,
    errors: Iterable[str] = (),
    warnings: Iterable[str] = (),
    metrics: dict[str, Any] | None = None,
    diagnostics: dict[str, int] | None = None,
) -> dict[str, Any]:
    resolved_packet_id: str | None = None
    if isinstance(packet_id, str):
        candidate_packet_id = packet_id.strip()
        if (
            candidate_packet_id
            and len(candidate_packet_id) <= 128
            and not any(ord(character) < 32 for character in candidate_packet_id)
        ):
            resolved_packet_id = candidate_packet_id
    resolved_diagnostics = diagnostics or {
        "decision_sessions": 0,
        "effective_decisions": 0,
        "process_valid_scoreable_sessions": 0,
        "denominator_rows": 0,
        "selected_rows": 0,
    }
    if "process_valid_scoreable_sessions" not in resolved_diagnostics:
        resolved_diagnostics = {
            **resolved_diagnostics,
            "process_valid_scoreable_sessions": int(
                resolved_diagnostics.get("effective_decisions", 0)
            ),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "input_sha256": input_sha256,
        "packet_id": resolved_packet_id,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "metrics": metrics,
        "diagnostics": resolved_diagnostics,
        "agreement_rate": (
            metrics.get("primary_selected_directional_agreement")
            if metrics is not None
            else None
        ),
        "agreement_rate_status": "MEASURED" if metrics is not None else "NOT_APPLICABLE",
        "authority_receipt_sha256": None,
        "authority_verified": False,
        "accuracy_claim_allowed": False,
        "claim_boundaries": {
            "historical_replay_is_prospective_accuracy": False,
            "absolute_up_is_primary_label": True,
            "market_and_sector_net_excess_are_secondary_labels": True,
            "modeled_costs_affect_actionable_and_excess_metrics": True,
            "independent_final_authority_receipt_verified": False,
            "probability_generated": False,
            "metrics_withheld_on_stop": status != "PASS_BACKTEST",
        },
    }


def evaluate_forty_session_replay(
    packet_path: Path,
    *,
    runtime_root: Path,
) -> dict[str, Any]:
    """Read, validate, and evaluate a strict 40-decision-session packet.

    Unsafe paths, malformed evidence, incomplete denominators, timing leakage,
    or outcome ambiguity return ``STOP_BACKTEST`` with ``metrics=None``.
    The repository does not yet implement an independently authenticated final
    Data-Foundation authority receipt.  Consequently even a structurally valid
    packet is contract-checked but returns ``STOP_BACKTEST`` with
    ``metrics=None``.  A caller-authored status or hash can never unlock a
    performance number.  The strict runtime accepts only complete packets, so
    incomplete or ambiguous inputs remain ``STOP_BACKTEST`` rather than
    advertising a second stop state that this evaluator cannot reach.
    """

    input_sha256: str | None = None
    packet_id: str | None = None
    try:
        packet, input_sha256 = _load_packet(Path(packet_path), Path(runtime_root))
        if isinstance(packet.get("packet_id"), str):
            packet_id = packet["packet_id"].strip() or None
        replay = validate_forty_session_replay_packet(packet)
        packet_id = replay.packet_id
        diagnostics = _non_performance_diagnostics(replay)
        result = _result(
            status="STOP_BACKTEST",
            input_sha256=input_sha256,
            packet_id=packet_id,
            errors=("FINAL_DATA_FOUNDATION_AUTHORITY_RECEIPT_REQUIRED",),
            metrics=None,
            diagnostics=diagnostics,
        )
        return validate_forty_session_replay_result(result)
    except (OSError, TypeError, ReplayValidationError, ValueError) as exc:
        result = _result(
            status="STOP_BACKTEST",
            input_sha256=input_sha256,
            packet_id=packet_id,
            errors=(str(exc) or exc.__class__.__name__,),
            metrics=None,
            diagnostics=None,
        )
        return validate_forty_session_replay_result(result)


__all__ = [
    "DECISION_SESSION_COUNT",
    "PRODUCT_ID",
    "ReplayValidationError",
    "evaluate_forty_session_replay",
    "validate_forty_session_replay_packet",
    "validate_forty_session_replay_result",
]
