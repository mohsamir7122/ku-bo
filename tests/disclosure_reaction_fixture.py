from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from kubo.disclosure_reaction import PRODUCT_ID

KUWAIT = timezone(timedelta(hours=3))
HASHES = {
    "official": "a" * 64,
    "calendar": "b" * 64,
    "price": "c" * 64,
    "market": "d" * 64,
    "sector": "e" * 64,
    "actions": "f" * 64,
    "opinion": "1" * 64,
    "opinion_archive": "2" * 64,
    "recent_market": "3" * 64,
    "financial": "4" * 64,
}


def trading_days(start: date, count: int) -> list[date]:
    rows: list[date] = []
    current = start
    while len(rows) < count:
        if current.weekday() in {6, 0, 1, 2, 3}:
            rows.append(current)
        current += timedelta(days=1)
    return rows


def stamp(day: date, hour: int, minute: int = 0) -> str:
    return datetime.combine(day, time(hour, minute), KUWAIT).isoformat()


def interpolate(start: float, end: float, count: int) -> list[float]:
    return [start + (end - start) * index / (count - 1) for index in range(count)]


def packet(*, pre_start: float = 100.0, pre_end: float = 100.0, immediate_end: float = 100.0, post_end: float = 100.0, opinions=None):
    days = trading_days(date(2026, 1, 4), 40)
    pre_days, post_days = days[:20], days[20:]
    event_at = datetime.combine(pre_days[-1], time(14, 0), KUWAIT)
    pre_stock = interpolate(pre_start, pre_end, 20)
    post_stock = [immediate_end] + interpolate(immediate_end, post_end, 19)
    def session(day_value, stock):
        return {
            "trade_date": day_value.isoformat(),
            "session_close_at": stamp(day_value, 13, 15),
            "observed_at": stamp(day_value, 13, 20),
            "stock_total_return_index": stock,
            "market_total_return_index": 100.0,
            "sector_total_return_index": 100.0,
            "calendar_evidence_sha256": HASHES["calendar"],
            "price_evidence_sha256": HASHES["price"],
            "market_benchmark_evidence_sha256": HASHES["market"],
            "sector_benchmark_evidence_sha256": HASHES["sector"],
            "corporate_action_evidence_sha256": HASHES["actions"],
        }
    pre = [session(day_value, pre_stock[index]) for index, day_value in enumerate(pre_days)]
    post = [session(day_value, post_stock[index]) for index, day_value in enumerate(post_days)]
    return {
        "schema_version": "1.0",
        "packet_id": "reaction-fixture",
        "product_id": PRODUCT_ID,
        "timezone": "Asia/Kuwait",
        "created_at": stamp(post_days[-1], 14, 0),
        "policy": {
            "immediate_post_sessions": 2,
            "movement_threshold_pct": 1.0,
            "numeric_output_rule": "QUALITATIVE_ONLY",
            "causality_rule": "ASSOCIATION_NOT_CAUSATION",
            "current_market_rule": "EXCLUDED_FROM_HISTORICAL_REACTION",
            "latest_financial_rule": "EXCLUDED_FROM_HISTORICAL_REACTION",
        },
        "historical_disclosure": {
            "schema_version": "1.0",
            "data_domain": "HISTORICAL_DISCLOSURE_ARCHIVE",
            "immutability": "APPEND_ONLY",
            "record_id": "disclosure-2026-01",
            "security_code": "HUMANSOFT",
            "canonical_cluster_id": "cluster-2026-01",
            "record_type": "ORIGINAL",
            "headline": "نتائج مالية دورية",
            "published_at": event_at.isoformat(),
            "available_at": event_at.isoformat(),
            "archived_at": stamp(post_days[-1], 13, 30),
            "official_source_url": "https://example.com/official-disclosure",
            "evidence_sha256": HASHES["official"],
            "corrects_record_id": None,
            "supersedes_record_id": None,
        },
        "historical_market_window": {
            "schema_version": "1.0",
            "data_domain": "HISTORICAL_EVENT_MARKET_WINDOW",
            "immutability": "FROZEN",
            "window_id": "window-2026-01",
            "security_code": "HUMANSOFT",
            "canonical_cluster_id": "cluster-2026-01",
            "disclosure_record_id": "disclosure-2026-01",
            "frozen_at": stamp(post_days[-1], 13, 30),
            "price_basis": "TOTAL_RETURN_INDEX",
            "benchmark_basis": "MARKET_AND_SECTOR_EXCESS",
            "corporate_action_status": "ADJUSTED",
            "pre_sessions": pre,
            "post_sessions": post,
            "evidence_receipts": {
                "trading_calendar_sha256": HASHES["calendar"],
                "price_history_sha256": HASHES["price"],
                "market_benchmark_sha256": HASHES["market"],
                "sector_benchmark_sha256": HASHES["sector"],
                "corporate_actions_sha256": HASHES["actions"],
            },
        },
        "public_opinion_archive": {
            "schema_version": "1.0",
            "data_domain": "HISTORICAL_PUBLIC_OPINION_ARCHIVE",
            "immutability": "FROZEN_AS_OF_CAPTURE",
            "archive_id": "opinion-archive-2026-01",
            "security_code": "HUMANSOFT",
            "canonical_cluster_id": "cluster-2026-01",
            "captured_through": stamp(post_days[-1], 13, 30),
            "items": opinions or [],
            "evidence_sha256": HASHES["opinion_archive"],
        },
    }


def opinion(*, when: str, stance: str, group: str = "source-a"):
    return {
        "opinion_id": f"opinion-{group}-{stance}-{when}",
        "published_at": when,
        "source_kind": "SOCIAL_MEDIA",
        "source_group": group,
        "source_url": "https://example.com/public-opinion",
        "stance": stance,
        "relevance": "DIRECT_DISCLOSURE_REACTION",
        "evidence_sha256": HASHES["opinion"],
    }


def recent_daily_market():
    days = trading_days(date(2026, 7, 1), 5)
    return {
        "schema_version": "1.0",
        "data_domain": "RECENT_DAILY_MARKET_SERIES",
        "mutability": "ROLLING_CURRENT",
        "purpose": "CURRENT_CONTEXT_ONLY",
        "series_id": "recent-market-1",
        "security_code": "HUMANSOFT",
        "series_as_of": stamp(days[-1], 14, 0),
        "price_basis": "TOTAL_RETURN_INDEX",
        "records": [
            {
                "trade_date": item.isoformat(),
                "observed_at": stamp(item, 13, 20),
                "total_return_index": 100.0 + index,
                "evidence_sha256": HASHES["recent_market"],
            }
            for index, item in enumerate(days)
        ],
        "evidence_sha256": HASHES["recent_market"],
        "historical_reaction_recompute_allowed": False,
    }


def latest_financial_snapshot():
    return {
        "schema_version": "1.0",
        "data_domain": "LATEST_FINANCIAL_SNAPSHOT",
        "mutability": "REPLACE_BY_NEWER_SNAPSHOT",
        "purpose": "CURRENT_FINANCIAL_CONTEXT_ONLY",
        "snapshot_id": "financial-2026-q2",
        "security_code": "HUMANSOFT",
        "reporting_period_end": "2026-06-30",
        "published_at": "2026-07-29T08:00:00+03:00",
        "available_at": "2026-07-29T08:00:00+03:00",
        "snapshot_as_of": "2026-08-17T12:00:00+03:00",
        "source_url": "https://example.com/latest-financials",
        "evidence_sha256": HASHES["financial"],
        "metrics": [
            {"metric_id": "REVENUE", "value": 1.0, "unit": "CURRENCY", "currency": "KWD"},
        ],
        "historical_reaction_input_allowed": False,
    }
