from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .disclosure_reaction_common import (
    DisclosureReactionError,
    aware,
    day,
    exact_fields,
    mapping,
    number,
    safe_https_url,
    sha256,
    text,
)

_MARKET_FIELDS = {
    "schema_version", "data_domain", "mutability", "purpose", "series_id",
    "security_code", "series_as_of", "price_basis", "records",
    "evidence_sha256", "historical_reaction_recompute_allowed",
}
_MARKET_RECORD_FIELDS = {
    "trade_date", "observed_at", "total_return_index", "evidence_sha256",
}
_FINANCIAL_FIELDS = {
    "schema_version", "data_domain", "mutability", "purpose", "snapshot_id",
    "security_code", "reporting_period_end", "published_at", "available_at",
    "snapshot_as_of", "source_url", "evidence_sha256", "metrics",
    "historical_reaction_input_allowed",
}
_METRIC_FIELDS = {"metric_id", "value", "unit", "currency"}


def validate_recent_daily_market_series(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = mapping(raw, "recent_daily_market")
    exact_fields(value, _MARKET_FIELDS, "recent_daily_market")
    if value["schema_version"] != "1.0":
        raise DisclosureReactionError("recent daily market schema_version must equal 1.0")
    if value["data_domain"] != "RECENT_DAILY_MARKET_SERIES":
        raise DisclosureReactionError("recent daily market data_domain mismatch")
    if value["mutability"] != "ROLLING_CURRENT":
        raise DisclosureReactionError("recent daily market mutability must be ROLLING_CURRENT")
    if value["purpose"] != "CURRENT_CONTEXT_ONLY":
        raise DisclosureReactionError("recent daily market purpose must be CURRENT_CONTEXT_ONLY")
    if value["price_basis"] != "TOTAL_RETURN_INDEX":
        raise DisclosureReactionError("recent daily market requires TOTAL_RETURN_INDEX")
    if value["historical_reaction_recompute_allowed"] is not False:
        raise DisclosureReactionError("recent daily market cannot recompute historical reactions")
    security_code = text(value["security_code"], "recent_daily_market.security_code", 64).upper()
    if security_code != "HUMANSOFT":
        raise DisclosureReactionError("recent daily market security_code must equal HUMANSOFT")
    series_as_of = aware(value["series_as_of"], "recent_daily_market.series_as_of")
    records = value["records"]
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise DisclosureReactionError("recent_daily_market.records must be non-empty")
    if len(records) > 120:
        raise DisclosureReactionError("recent_daily_market.records exceeds rolling window")
    validated: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for index, item in enumerate(records):
        row = mapping(item, f"recent_daily_market.records[{index}]")
        exact_fields(row, _MARKET_RECORD_FIELDS, f"recent_daily_market.records[{index}]")
        trade_date = day(row["trade_date"], f"recent_daily_market.records[{index}].trade_date").isoformat()
        if trade_date in seen_dates:
            raise DisclosureReactionError(f"duplicate recent market trade_date: {trade_date}")
        seen_dates.add(trade_date)
        observed = aware(row["observed_at"], f"recent_daily_market.records[{index}].observed_at")
        if observed > series_as_of:
            raise DisclosureReactionError("recent market record postdates series_as_of")
        validated.append({
            "trade_date": trade_date,
            "observed_at": row["observed_at"],
            "total_return_index": number(row["total_return_index"], f"recent_daily_market.records[{index}].total_return_index", minimum=1e-12),
            "evidence_sha256": sha256(row["evidence_sha256"], f"recent_daily_market.records[{index}].evidence_sha256"),
        })
    if [row["trade_date"] for row in validated] != sorted(seen_dates):
        raise DisclosureReactionError("recent daily market records must be ascending")
    return {
        **dict(value),
        "series_id": text(value["series_id"], "recent_daily_market.series_id", 128),
        "security_code": security_code,
        "records": validated,
        "evidence_sha256": sha256(value["evidence_sha256"], "recent_daily_market.evidence_sha256"),
    }


def validate_latest_financial_snapshot(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = mapping(raw, "latest_financial_snapshot")
    exact_fields(value, _FINANCIAL_FIELDS, "latest_financial_snapshot")
    if value["schema_version"] != "1.0":
        raise DisclosureReactionError("latest financial snapshot schema_version must equal 1.0")
    if value["data_domain"] != "LATEST_FINANCIAL_SNAPSHOT":
        raise DisclosureReactionError("latest financial snapshot data_domain mismatch")
    if value["mutability"] != "REPLACE_BY_NEWER_SNAPSHOT":
        raise DisclosureReactionError("latest financial snapshot mutability mismatch")
    if value["purpose"] != "CURRENT_FINANCIAL_CONTEXT_ONLY":
        raise DisclosureReactionError("latest financial snapshot purpose mismatch")
    if value["historical_reaction_input_allowed"] is not False:
        raise DisclosureReactionError("latest financial snapshot cannot enter historical reaction analysis")
    security_code = text(value["security_code"], "latest_financial_snapshot.security_code", 64).upper()
    if security_code != "HUMANSOFT":
        raise DisclosureReactionError("latest financial snapshot security_code must equal HUMANSOFT")
    reporting_period_end = day(value["reporting_period_end"], "latest_financial_snapshot.reporting_period_end")
    published = aware(value["published_at"], "latest_financial_snapshot.published_at")
    available = aware(value["available_at"], "latest_financial_snapshot.available_at")
    snapshot_as_of = aware(value["snapshot_as_of"], "latest_financial_snapshot.snapshot_as_of")
    if available < published or snapshot_as_of < available:
        raise DisclosureReactionError("latest financial snapshot timestamps are inconsistent")
    if reporting_period_end > published.date():
        raise DisclosureReactionError("reporting_period_end postdates publication")
    metrics = value["metrics"]
    if not isinstance(metrics, Sequence) or isinstance(metrics, (str, bytes)) or not metrics:
        raise DisclosureReactionError("latest_financial_snapshot.metrics must be non-empty")
    seen: set[str] = set()
    validated_metrics: list[dict[str, Any]] = []
    for index, item in enumerate(metrics):
        row = mapping(item, f"latest_financial_snapshot.metrics[{index}]")
        exact_fields(row, _METRIC_FIELDS, f"latest_financial_snapshot.metrics[{index}]")
        metric_id = text(row["metric_id"], f"latest_financial_snapshot.metrics[{index}].metric_id", 128)
        if metric_id in seen:
            raise DisclosureReactionError(f"duplicate financial metric_id: {metric_id}")
        seen.add(metric_id)
        validated_metrics.append({
            "metric_id": metric_id,
            "value": number(row["value"], f"latest_financial_snapshot.metrics[{index}].value"),
            "unit": text(row["unit"], f"latest_financial_snapshot.metrics[{index}].unit", 64),
            "currency": text(row["currency"], f"latest_financial_snapshot.metrics[{index}].currency", 16),
        })
    return {
        **dict(value),
        "snapshot_id": text(value["snapshot_id"], "latest_financial_snapshot.snapshot_id", 128),
        "security_code": security_code,
        "source_url": safe_https_url(value["source_url"], "latest_financial_snapshot.source_url"),
        "evidence_sha256": sha256(value["evidence_sha256"], "latest_financial_snapshot.evidence_sha256"),
        "metrics": validated_metrics,
    }


__all__ = ["validate_recent_daily_market_series", "validate_latest_financial_snapshot"]
