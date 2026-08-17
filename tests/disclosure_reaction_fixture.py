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


def packet(
    *,
    pre_start: float = 100.0,
    pre_end: float = 100.0,
    immediate_end: float = 100.0,
    post_end: float = 100.0,
    opinions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    days = trading_days(date(2026, 1, 4), 40)
    pre_days = days[:20]
    post_days = days[20:]
    event_at = datetime.combine(pre_days[-1], time(14, 0), KUWAIT)

    def interpolate(start: float, end: float, count: int) -> list[float]:
        if count == 1:
            return [end]
        return [start + (end - start) * i / (count - 1) for i in range(count)]

    pre_stock = interpolate(pre_start, pre_end, 20)
    post_stock = [immediate_end]
    post_stock += interpolate(immediate_end, post_end, 19)
    pre: list[dict[str, object]] = []
    post: list[dict[str, object]] = []
    for index, day in enumerate(pre_days):
        pre.append(
            {
                "trade_date": day.isoformat(),
                "session_close_at": stamp(day, 13, 15),
                "observed_at": stamp(day, 13, 20),
                "stock_total_return_index": pre_stock[index],
                "market_total_return_index": 100.0,
                "sector_total_return_index": 100.0,
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
                "stock_total_return_index": post_stock[index],
                "market_total_return_index": 100.0,
                "sector_total_return_index": 100.0,
                "calendar_evidence_sha256": HASHES["calendar"],
                "price_evidence_sha256": HASHES["price"],
                "market_benchmark_evidence_sha256": HASHES["market"],
                "sector_benchmark_evidence_sha256": HASHES["sector"],
                "corporate_action_evidence_sha256": HASHES["actions"],
            }
        )
    return {
        "schema_version": "1.0",
        "packet_id": "humansoft-disclosure-fixture",
        "product_id": PRODUCT_ID,
        "timezone": "Asia/Kuwait",
        "created_at": stamp(post_days[-1], 14, 0),
        "disclosure": {
            "disclosure_id": "disclosure-2026-01",
            "security_code": "HUMANSOFT",
            "canonical_cluster_id": "cluster-2026-01",
            "disclosure_type": "FINANCIAL_RESULTS",
            "headline": "نتائج مالية دورية",
            "published_at": event_at.isoformat(),
            "available_at": event_at.isoformat(),
            "official_source_url": "https://example.com/official-disclosure",
            "official_evidence_sha256": HASHES["official"],
            "duplicate_of": None,
        },
        "policy": {
            "pre_sessions": 20,
            "post_sessions": 20,
            "immediate_post_sessions": 2,
            "movement_threshold_pct": 1.0,
            "price_basis": "TOTAL_RETURN_INDEX",
            "benchmark_rule": "MARKET_AND_SECTOR_EXCESS",
            "corporate_action_rule": "ADJUSTED_OR_EXPLICIT_NONE",
            "public_opinion_rule": "SOURCE_BACKED_INDEPENDENT_GROUPS",
            "numeric_output_rule": "QUALITATIVE_ONLY",
            "causality_rule": "ASSOCIATION_NOT_CAUSATION",
        },
        "pre_sessions": pre,
        "post_sessions": post,
        "public_opinion": opinions or [],
        "evidence_receipts": {
            "official_disclosure_sha256": HASHES["official"],
            "trading_calendar_sha256": HASHES["calendar"],
            "price_history_sha256": HASHES["price"],
            "market_benchmark_sha256": HASHES["market"],
            "sector_benchmark_sha256": HASHES["sector"],
            "corporate_actions_sha256": HASHES["actions"],
            "public_opinion_archive_sha256": HASHES["opinion"],
        },
    }


def opinion(*, when: str, stance: str, group: str = "source-a") -> dict[str, object]:
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
