from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from statistics import median
from typing import Any, Iterable

from .strict import finite_number


@dataclass(frozen=True)
class LiquidityMetrics:
    sessions: int
    traded_sessions: int
    missing_volume_sessions: int
    zero_volume_sessions: int
    zero_return_sessions: int
    nontrading_ratio: float
    median_volume: float | None
    median_turnover_kwd: float | None
    amihud_illiquidity: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_liquidity_metrics(rows: Iterable[dict[str, Any]]) -> LiquidityMetrics:
    ordered = list(rows)
    if not ordered:
        raise ValueError("at least one market session is required")
    volumes: list[float] = []
    turnovers: list[float] = []
    amihud_terms: list[float] = []
    missing_volume = 0
    zero_volume = 0
    zero_returns = 0
    traded = 0
    previous_close: float | None = None
    for index, row in enumerate(ordered):
        close = finite_number(row.get("close_fils"), f"row_{index}.close_fils", minimum=0.001)
        volume_value = row.get("volume")
        if volume_value in (None, ""):
            missing_volume += 1
            volume = None
        else:
            volume = finite_number(volume_value, f"row_{index}.volume", minimum=0)
            if volume == 0:
                zero_volume += 1
            else:
                traded += 1
                volumes.append(volume)
        turnover_value = row.get("turnover_kwd")
        turnover = None
        if turnover_value not in (None, ""):
            turnover = finite_number(turnover_value, f"row_{index}.turnover_kwd", minimum=0)
            if turnover > 0:
                turnovers.append(turnover)
        if previous_close is not None:
            daily_return = close / previous_close - 1.0
            if abs(daily_return) < 1e-15:
                zero_returns += 1
            if turnover is not None and turnover > 0 and volume is not None and volume > 0:
                amihud_terms.append(abs(daily_return) / turnover)
        previous_close = close
    sessions = len(ordered)
    nontrading = zero_volume + missing_volume
    return LiquidityMetrics(
        sessions=sessions,
        traded_sessions=traded,
        missing_volume_sessions=missing_volume,
        zero_volume_sessions=zero_volume,
        zero_return_sessions=zero_returns,
        nontrading_ratio=nontrading / sessions,
        median_volume=median(volumes) if volumes else None,
        median_turnover_kwd=median(turnovers) if turnovers else None,
        amihud_illiquidity=sum(amihud_terms) / len(amihud_terms) if amihud_terms else None,
    )


@dataclass(frozen=True)
class SimulatedFill:
    status: str
    requested_quantity: int
    filled_quantity: int
    unfilled_quantity: int
    fill_price_fils: float | None
    gross_notional_kwd: float
    estimated_cost_kwd: float
    participation_rate: float | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def simulate_liquidity_constrained_fill(
    *,
    side: str,
    quantity: int,
    session_volume: int | None,
    bid_fils: float | None,
    ask_fils: float | None,
    trading_status: str,
    max_participation: float = 0.05,
    fees_bps: float = 10.0,
    impact_bps_at_full_participation: float = 50.0,
    upper_limit_queue: bool = False,
    lower_limit_queue: bool = False,
) -> SimulatedFill:
    side = side.upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    participation_cap = finite_number(max_participation, "max_participation", minimum=0.000001, maximum=1)
    fee_rate = finite_number(fees_bps, "fees_bps", minimum=0) / 10_000
    impact_rate = finite_number(impact_bps_at_full_participation, "impact_bps_at_full_participation", minimum=0) / 10_000
    reasons: list[str] = []
    status = str(trading_status).upper()
    if status != "TRADED":
        reasons.append("TRADING_NOT_AVAILABLE")
    if side == "BUY" and upper_limit_queue:
        reasons.append("UPPER_LIMIT_QUEUE_NO_FILL_ASSUMPTION")
    if side == "SELL" and lower_limit_queue:
        reasons.append("LOWER_LIMIT_QUEUE_NO_FILL_ASSUMPTION")
    if session_volume is None:
        reasons.append("SESSION_VOLUME_MISSING")
    elif type(session_volume) is not int or session_volume < 0:
        raise ValueError("session_volume must be a non-negative integer or null")
    elif session_volume == 0:
        reasons.append("ZERO_SESSION_VOLUME")
    quote = ask_fils if side == "BUY" else bid_fils
    if quote is None:
        reasons.append("SIDE_QUOTE_MISSING")
    else:
        quote = finite_number(quote, "side_quote_fils", minimum=0.001)
    if reasons:
        return SimulatedFill("NO_FILL", quantity, 0, quantity, None, 0.0, 0.0, None, tuple(reasons))

    assert session_volume is not None and quote is not None
    available = math.floor(session_volume * participation_cap)
    filled = min(quantity, available)
    if filled <= 0:
        return SimulatedFill("NO_FILL", quantity, 0, quantity, None, 0.0, 0.0, 0.0, ("PARTICIPATION_CAP_ROUNDS_TO_ZERO",))
    realized_participation = filled / session_volume
    relative_to_cap = min(1.0, realized_participation / participation_cap)
    signed_impact = impact_rate * relative_to_cap * (1 if side == "BUY" else -1)
    fill_price = quote * (1 + signed_impact)
    gross_notional = fill_price * filled / 1000.0
    cost = gross_notional * (fee_rate + abs(impact_rate * relative_to_cap))
    fill_status = "FILLED" if filled == quantity else "PARTIAL_FILL"
    if fill_status == "PARTIAL_FILL":
        reasons.append("ORDER_EXCEEDS_PARTICIPATION_CAP")
    return SimulatedFill(
        fill_status,
        quantity,
        filled,
        quantity - filled,
        fill_price,
        gross_notional,
        cost,
        realized_participation,
        tuple(reasons),
    )


__all__ = [
    "LiquidityMetrics",
    "SimulatedFill",
    "calculate_liquidity_metrics",
    "simulate_liquidity_constrained_fill",
]
