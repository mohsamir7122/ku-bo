from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from statistics import mean, median
from typing import Any, Iterable

from .strict import finite_number


@dataclass(frozen=True)
class DescriptiveSignal:
    signal_kind: str
    direction: str
    strength: float
    materiality: float
    rationale: tuple[str, ...]
    method_id: str
    claim_boundary: str = "DESCRIPTIVE_RESEARCH_SIGNAL_NOT_PROBABILITY"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _direction(value: float, neutral_band: float) -> str:
    if value > neutral_band:
        return "POSITIVE"
    if value < -neutral_band:
        return "NEGATIVE"
    return "NEUTRAL"


def _strength(value: float, full_scale: float) -> float:
    return min(1.0, abs(value) / full_scale) if full_scale > 0 else 0.0


def analyze_price_window(rows: Iterable[dict[str, Any]]) -> tuple[DescriptiveSignal, ...]:
    bars = list(rows)
    if len(bars) < 5:
        raise ValueError("at least five point-in-time price bars are required")
    closes: list[float] = []
    volumes: list[float | None] = []
    for index, row in enumerate(bars):
        closes.append(finite_number(row.get("close_fils"), f"bar_{index}.close_fils", minimum=0.001))
        volume = row.get("volume")
        volumes.append(None if volume in (None, "") else finite_number(volume, f"bar_{index}.volume", minimum=0))
    returns = [current / previous - 1.0 for previous, current in zip(closes, closes[1:])]
    trailing_return = closes[-1] / closes[0] - 1.0
    return_mean = mean(returns)
    volatility = math.sqrt(mean([(item - return_mean) ** 2 for item in returns])) if returns else 0.0
    max_close = max(closes)
    drawdown = closes[-1] / max_close - 1.0
    momentum = DescriptiveSignal(
        "TECHNICAL",
        _direction(trailing_return, 0.005),
        _strength(trailing_return, 0.10),
        min(1.0, 0.4 + len(bars) / 100),
        (
            f"trailing_return={trailing_return:.8f}",
            f"realized_volatility={volatility:.8f}",
            f"current_drawdown={drawdown:.8f}",
        ),
        "transparent_price_window_v1",
    )

    prior_positive_volumes = [value for value in volumes[:-1] if value is not None and value > 0]
    last_volume = volumes[-1]
    volume_ratio = None
    if last_volume is not None and prior_positive_volumes:
        volume_ratio = last_volume / median(prior_positive_volumes)
    activity_direction = _direction(returns[-1], 0.002)
    activity_strength = _strength(returns[-1], 0.05)
    if volume_ratio is not None:
        activity_strength = min(1.0, activity_strength * min(2.0, max(0.5, volume_ratio)))
    price_activity = DescriptiveSignal(
        "PRICE_ACTIVITY",
        activity_direction,
        activity_strength,
        0.6 if volume_ratio is not None else 0.35,
        (
            f"last_return={returns[-1]:.8f}",
            f"last_volume_ratio={volume_ratio:.8f}" if volume_ratio is not None else "last_volume_ratio=UNKNOWN",
        ),
        "transparent_price_activity_v1",
    )

    missing = sum(value is None for value in volumes)
    zero = sum(value == 0 for value in volumes if value is not None)
    nontrading_ratio = (missing + zero) / len(volumes)
    liquidity_direction = "NEGATIVE" if nontrading_ratio >= 0.20 else "NEUTRAL"
    liquidity = DescriptiveSignal(
        "LIQUIDITY",
        liquidity_direction,
        min(1.0, nontrading_ratio / 0.50),
        0.8,
        (
            f"missing_volume_sessions={missing}",
            f"zero_volume_sessions={zero}",
            f"nontrading_ratio={nontrading_ratio:.8f}",
        ),
        "transparent_liquidity_availability_v1",
    )
    return momentum, price_activity, liquidity


def _growth(current: float, prior: float) -> float | None:
    return None if abs(prior) < 1e-12 else current / abs(prior) - (1 if prior > 0 else -1)


def analyze_fundamentals(current: dict[str, Any], prior: dict[str, Any]) -> DescriptiveSignal:
    required = ("revenue", "net_income", "operating_cash_flow", "total_debt", "equity")
    current_values = {field: finite_number(current.get(field), f"current.{field}") for field in required}
    prior_values = {field: finite_number(prior.get(field), f"prior.{field}") for field in required}
    if current_values["equity"] <= 0:
        debt_to_equity = None
    else:
        debt_to_equity = current_values["total_debt"] / current_values["equity"]
    revenue_growth = _growth(current_values["revenue"], prior_values["revenue"])
    income_growth = _growth(current_values["net_income"], prior_values["net_income"])
    quality_votes = [
        current_values["net_income"] > 0,
        current_values["operating_cash_flow"] > 0,
        current_values["operating_cash_flow"] >= current_values["net_income"],
        revenue_growth is not None and revenue_growth > 0,
        income_growth is not None and income_growth > 0,
        debt_to_equity is not None and debt_to_equity <= 1.5,
    ]
    quality_score = sum(quality_votes) / len(quality_votes)
    direction = "POSITIVE" if quality_score >= 2 / 3 else "NEGATIVE" if quality_score <= 1 / 3 else "NEUTRAL"
    return DescriptiveSignal(
        "FUNDAMENTAL",
        direction,
        abs(quality_score - 0.5) * 2,
        0.75,
        (
            f"quality_vote_share={quality_score:.8f}",
            f"revenue_growth={revenue_growth:.8f}" if revenue_growth is not None else "revenue_growth=UNKNOWN",
            f"net_income_growth={income_growth:.8f}" if income_growth is not None else "net_income_growth=UNKNOWN",
            f"debt_to_equity={debt_to_equity:.8f}" if debt_to_equity is not None else "debt_to_equity=UNKNOWN",
        ),
        "transparent_fundamental_quality_v1",
    )


def analyze_sentiment(rows: Iterable[dict[str, Any]]) -> DescriptiveSignal:
    best_by_origin: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        origin_id = str(row.get("origin_id", "")).strip()
        author_id = str(row.get("author_id", "")).strip()
        if not origin_id or not author_id:
            raise ValueError(f"sentiment_{index} requires origin_id and author_id")
        tone = finite_number(row.get("tone"), f"sentiment_{index}.tone", minimum=-1, maximum=1)
        reliability = finite_number(row.get("author_reliability", 0.5), f"sentiment_{index}.author_reliability", minimum=0, maximum=1)
        candidate = {"origin_id": origin_id, "author_id": author_id, "tone": tone, "reliability": reliability}
        current = best_by_origin.get(origin_id)
        if current is None or reliability > current["reliability"]:
            best_by_origin[origin_id] = candidate
    unique = list(best_by_origin.values())
    authors = {row["author_id"] for row in unique}
    if not unique:
        return DescriptiveSignal("SENTIMENT", "NEUTRAL", 0.0, 0.0, ("no_sentiment_observations",), "reliability_weighted_sentiment_v1")
    denominator = sum(row["reliability"] for row in unique)
    weighted_tone = sum(row["tone"] * row["reliability"] for row in unique) / denominator if denominator else 0.0
    direction = _direction(weighted_tone, 0.10) if len(authors) >= 2 else "NEUTRAL"
    return DescriptiveSignal(
        "SENTIMENT",
        direction,
        _strength(weighted_tone, 0.75) if len(authors) >= 2 else 0.0,
        min(0.5, len(authors) / 10),
        (
            f"unique_origins={len(unique)}",
            f"independent_authors={len(authors)}",
            f"weighted_text_tone={weighted_tone:.8f}",
            "tone_is_not_claim_truth",
        ),
        "reliability_weighted_sentiment_v1",
    )


__all__ = ["DescriptiveSignal", "analyze_fundamentals", "analyze_price_window", "analyze_sentiment"]
