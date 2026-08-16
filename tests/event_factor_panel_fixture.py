from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from kubo.event_factor_panel import PRODUCT_ID



ROOT = Path(__file__).resolve().parents[1]
KUWAIT = timezone(timedelta(hours=3))
HASHES = {
    "event": "a" * 64,
    "snapshot": "b" * 64,
    "calendar": "c" * 64,
    "price": "d" * 64,
    "market": "e" * 64,
    "sector": "f" * 64,
    "actions": "1" * 64,
    "factor": "2" * 64,
}


def sessions(start: date, count: int) -> list[date]:
    rows: list[date] = []
    current = start
    while len(rows) < count:
        if current.weekday() in {6, 0, 1, 2, 3}:
            rows.append(current)
        current += timedelta(days=1)
    return rows


def stamp(day: date, hour: int, minute: int = 0) -> str:
    return datetime.combine(day, time(hour, minute), KUWAIT).isoformat()


def valid_packet() -> dict[str, object]:
    session_days = sessions(date(2026, 1, 4), 40)
    pre_days = session_days[:20]
    post_days = session_days[20:]
    event_at = datetime.combine(pre_days[-1], time(14, 0), KUWAIT)
    pre: list[dict[str, object]] = []
    post: list[dict[str, object]] = []
    for index, day in enumerate(pre_days):
        pre.append(
            {
                "trade_date": day.isoformat(),
                "session_close_at": stamp(day, 13, 15),
                "observed_at": stamp(day, 13, 20),
                "stock_total_return_index": 100.0 + index * 0.25,
                "market_total_return_index": 1000.0 + index * 0.5,
                "sector_total_return_index": 500.0 + index * 0.4,
                "volume": 100_000.0 + index * 1_000.0,
                "calendar_evidence_sha256": HASHES["calendar"],
                "price_evidence_sha256": HASHES["price"],
                "market_benchmark_evidence_sha256": HASHES["market"],
                "sector_benchmark_evidence_sha256": HASHES["sector"],
                "corporate_action_evidence_sha256": HASHES["actions"],
            }
        )
    for index, day in enumerate(post_days):
        post.append(
            {
                "trade_date": day.isoformat(),
                "session_close_at": stamp(day, 13, 15),
                "observed_at": stamp(day, 13, 20),
                "stock_total_return_index": 105.0 + index * 0.5,
                "market_total_return_index": 1010.0 + index * 0.2,
                "sector_total_return_index": 505.0 + index * 0.15,
                "volume": 150_000.0 + index * 1_500.0,
                "calendar_evidence_sha256": HASHES["calendar"],
                "price_evidence_sha256": HASHES["price"],
                "market_benchmark_evidence_sha256": HASHES["market"],
                "sector_benchmark_evidence_sha256": HASHES["sector"],
                "corporate_action_evidence_sha256": HASHES["actions"],
            }
        )
    return {
        "schema_version": "1.0",
        "packet_id": "humansoft-event-fixture",
        "product_id": PRODUCT_ID,
        "timezone": "Asia/Kuwait",
        "created_at": stamp(post_days[-1], 14, 0),
        "evidence_classification": "PROVEN_REAL_EVIDENCE",
        "rights_status": "RESEARCH_USE_AUTHORIZED",
        "policy": {
            "pre_event_sessions": 20,
            "post_event_sessions": 20,
            "entry_rule": "FIRST_ELIGIBLE_CLOSE_AFTER_EVENT",
            "price_basis": "TOTAL_RETURN_INDEX",
            "benchmark_rule": "POINT_IN_TIME_MARKET_AND_SECTOR",
            "corporate_action_rule": "ADJUSTED_OR_EXPLICIT_NONE",
            "material_return_threshold_pct": 4.0,
            "event_cluster_rule": "ONE_CANONICAL_EVENT_CLUSTER",
            "feature_cutoff_rule": "AVAILABLE_AT_OR_BEFORE_EVENT",
            "overlap_rule": "PURGE_AND_EMBARGO",
        },
        "event": {
            "event_id": "event-2026-01",
            "security_code": "HUMANSOFT",
            "canonical_cluster_id": "cluster-2026-01",
            "event_type": "FINANCIAL_RESULTS",
            "published_at": event_at.isoformat(),
            "available_at": event_at.isoformat(),
            "source_url": "https://example.com/official-disclosure",
            "evidence_sha256": HASHES["event"],
            "duplicate_of": None,
        },
        "factor_snapshot": {
            "snapshot_id": "snapshot-2026-01",
            "snapshot_at": event_at.isoformat(),
            "evidence_sha256": HASHES["snapshot"],
            "factors": [
                {
                    "factor_id": "EXCESS_MOMENTUM_20",
                    "state": "OBSERVED",
                    "value": 0.25,
                    "available_at": event_at.isoformat(),
                    "evidence_sha256": HASHES["factor"],
                },
                {
                    "factor_id": "ANALYST_REVISION",
                    "state": "UNKNOWN_NOT_OBSERVED",
                    "value": None,
                    "available_at": event_at.isoformat(),
                    "evidence_sha256": HASHES["factor"],
                },
                {
                    "factor_id": "SOCIAL_DIFFUSION",
                    "state": "BLOCKED",
                    "value": None,
                    "available_at": event_at.isoformat(),
                    "evidence_sha256": HASHES["factor"],
                },
            ],
        },
        "pre_sessions": pre,
        "post_sessions": post,
        "evidence_receipts": {
            "event_ledger_sha256": HASHES["event"],
            "factor_snapshot_sha256": HASHES["snapshot"],
            "trading_calendar_sha256": HASHES["calendar"],
            "price_history_sha256": HASHES["price"],
            "market_benchmark_sha256": HASHES["market"],
            "sector_benchmark_sha256": HASHES["sector"],
            "corporate_actions_sha256": HASHES["actions"],
        },
        "independent_authority_receipt": None,
    }


__all__ = ["HASHES", "KUWAIT", "ROOT", "valid_packet"]
