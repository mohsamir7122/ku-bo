from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import sha256_bytes


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_synthetic_network_run(root: Path, *, include_boursa: bool = True) -> Path:
    """Build a contract fixture; never market data or a forecast."""

    root.mkdir(parents=True, exist_ok=True)
    raw_dir = root / "raw"
    raw_dir.mkdir(exist_ok=True)
    source_rows = [
        (
            "tradingview_screeners",
            "https://www.tradingview.com/markets/stocks-kuwait/",
            ["MARKET_DISCOVERY", "PRICE_HISTORY"],
            {"fixture": "market screen", "securities": ["101", "102"]},
        ),
        (
            "investing_history",
            "https://www.investing.com/equities/kwt-real-est-historical-data",
            ["MARKET_DISCOVERY", "PRICE_HISTORY"],
            {"fixture": "price history", "securities": ["101", "102"]},
        ),
        (
            "reuters_middle_east",
            "https://www.reuters.com/world/middle-east/",
            ["NEWS_ARCHIVE"],
            {"fixture": "news search", "items": 1},
        ),
        (
            "telegram_kuwaitstockex",
            "https://t.me/s/kuwaitstockex",
            ["COMMUNITY_SENTIMENT"],
            {"fixture": "community messages", "items": 2},
        ),
        (
            "kuna",
            "https://www.kuna.net.kw/",
            ["NEWS_ARCHIVE"],
            {"fixture": "government news search", "items": 1},
        ),
    ]
    if include_boursa:
        source_rows.append(
            (
                "boursa_disclosure_archive",
                "https://www.boursakuwait.com.kw/en/announcements/disclosures-and-announcements/historical-disclosures-and-announcements/",
                ["OFFICIAL_EVENT", "NEWS_ARCHIVE"],
                {"fixture": "official disclosure", "security_code": "101"},
            )
        )
    # Boursa's current surface remains observable independently from its
    # disclosure archive.  The fixture also carries a separate official CMA
    # identity receipt so a single official-site degradation does not create an
    # identity bypass or stop otherwise valid research.
    source_rows.append(
        (
            "boursa_current",
            "https://www.boursakuwait.com.kw/en/",
            ["IDENTITY_REFERENCE"],
            {"fixture": "official point-in-time universe", "security_codes": ["101", "102"]},
        )
    )
    source_rows.append(
        (
            "cma_ifsah",
            "https://ifsah.cma.gov.kw/",
            ["IDENTITY_REFERENCE"],
            {"fixture": "official identity fallback", "security_codes": ["101", "102"]},
        )
    )

    artifacts: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    digest_by_source: dict[str, str] = {}
    for index, (source_id, url, roles, payload) in enumerate(source_rows):
        content = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        relative = Path("raw") / f"{index:02d}_{source_id}.json"
        (root / relative).write_bytes(content)
        digest = sha256_bytes(content)
        digest_by_source[source_id] = digest
        artifacts.append(
            {
                "path": relative.as_posix(),
                "sha256": digest,
                "size_bytes": len(content),
                "source_id": source_id,
                "source_url": url,
                "observed_at": "2026-08-07T00:50:00+03:00",
                "capture_kind": "RAW_PAGE",
            }
        )
        observations.append(
            {
                "source_id": source_id,
                "state": "AVAILABLE",
                "access_mode": "PUBLIC_PAGE",
                "attempted_at": "2026-08-07T00:50:00+03:00",
                "query_status": "QUALIFIED",
                "roles_observed": roles,
                "qualified_items": 1,
                "zero_result": False,
                "raw_sha256s": [digest],
                "data_quality_flags": [],
                "limitations": ["SYNTHETIC_FIXTURE_ONLY"],
                "entitlement_id": "",
            }
        )

    _write_json(
        root / "research_run.json",
        {
            "schema_version": "3.0",
            "run_id": "synthetic-network-run",
            "product_id": "next_session_rank",
            "decision_at": "2026-08-07T01:00:00+03:00",
            "timezone": "Asia/Kuwait",
            "scope": "CANDIDATE_SET",
            "expected_universe_count": 2,
            "covered_universe_count": 2,
            "budget": {"max_requests": 20, "max_raw_bytes": 1000000, "max_wall_seconds": 300},
            "usage": {"requests": len(source_rows), "raw_bytes": sum(item["size_bytes"] for item in artifacts), "wall_seconds": 10},
        },
    )
    _write_json(root / "manifest.json", {"schema_version": "3.0", "artifacts": artifacts})
    _write_json(root / "source_observations.json", {"schema_version": "3.0", "sources": observations})
    _write_json(
        root / "universe.json",
        {
            "schema_version": "3.0",
            "reconciliation_status": "EXACT",
            "membership_basis": "POINT_IN_TIME_OFFICIAL",
            "membership_source_id": "cma_ifsah",
            "membership_raw_sha256": digest_by_source["cma_ifsah"],
            "membership_as_of": "2026-08-07T00:50:00+03:00",
            "expected_security_codes": ["101", "102"],
            "covered_security_codes": ["101", "102"],
            "securities": [
                {
                    "security_code": "101",
                    "ticker": "AAA",
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                },
                {
                    "security_code": "102",
                    "ticker": "BBB",
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                },
            ],
        },
    )

    official_or_news_source = "boursa_disclosure_archive" if include_boursa else "kuna"
    official_or_news_url = next(url for source_id, url, _, _ in source_rows if source_id == official_or_news_source)
    findings = [
        {
            "finding_id": "f-101-price",
            "security_code": "101",
            "ticker": "AAA",
            "source_id": "tradingview_screeners",
            "source_url": source_rows[0][1],
            "published_at": "2026-08-07T00:40:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "C",
            "raw_sha256": digest_by_source["tradingview_screeners"],
            "evidence_roles": ["MARKET_DISCOVERY"],
            "signal_kind": "PRICE_ACTIVITY",
            "direction": "POSITIVE",
            "fact_type": "MOVER_DISCOVERY",
            "strength": 0.85,
            "materiality": 0.80,
            "origin_id": "tv-screen-101",
            "event_key": "price-101",
            "claim_text": "Synthetic positive activity finding.",
        },
        {
            "finding_id": "f-101-technical",
            "security_code": "101",
            "ticker": "AAA",
            "source_id": "investing_history",
            "source_url": source_rows[1][1],
            "published_at": "2026-08-07T00:35:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "C",
            "raw_sha256": digest_by_source["investing_history"],
            "evidence_roles": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
            "signal_kind": "TECHNICAL",
            "direction": "POSITIVE",
            "fact_type": "SECONDARY_TECHNICAL",
            "strength": 0.75,
            "materiality": 0.70,
            "origin_id": "investing-technical-101",
            "event_key": "technical-101",
            "claim_text": "Synthetic positive technical finding.",
        },
        {
            "finding_id": "f-101-liquidity",
            "security_code": "101",
            "ticker": "AAA",
            "source_id": "investing_history",
            "source_url": source_rows[1][1],
            "published_at": "2026-08-07T00:35:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "C",
            "raw_sha256": digest_by_source["investing_history"],
            "evidence_roles": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
            "signal_kind": "LIQUIDITY",
            "direction": "POSITIVE",
            "fact_type": "SECONDARY_PRICE_HISTORY",
            "strength": 0.70,
            "materiality": 0.65,
            "origin_id": "investing-liquidity-101",
            "event_key": "liquidity-101",
            "claim_text": "Synthetic liquidity context.",
        },
        {
            "finding_id": "f-101-catalyst-news",
            "security_code": "101",
            "ticker": "AAA",
            "source_id": "reuters_middle_east",
            "source_url": source_rows[2][1],
            "published_at": "2026-08-07T00:20:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "B",
            "raw_sha256": digest_by_source["reuters_middle_east"],
            "evidence_roles": ["NEWS_ARCHIVE"],
            "signal_kind": "CATALYST",
            "direction": "POSITIVE",
            "fact_type": "ORIGINAL_REPORTING",
            "strength": 0.75,
            "materiality": 0.80,
            "origin_id": "reuters-event-101",
            "event_key": "catalyst-101",
            "claim_text": "Synthetic reported catalyst.",
        },
        {
            "finding_id": "f-101-catalyst-confirmation",
            "security_code": "101",
            "ticker": "AAA",
            "source_id": official_or_news_source,
            "source_url": official_or_news_url,
            "published_at": "2026-08-07T00:25:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "A" if include_boursa else "B",
            "raw_sha256": digest_by_source[official_or_news_source],
            "evidence_roles": ["OFFICIAL_EVENT", "NEWS_ARCHIVE"] if include_boursa else ["NEWS_ARCHIVE"],
            "signal_kind": "CATALYST",
            "direction": "POSITIVE",
            "fact_type": "DISCLOSURE" if include_boursa else "GOVERNMENT_NEWS",
            "strength": 0.90 if include_boursa else 0.65,
            "materiality": 0.90 if include_boursa else 0.60,
            "origin_id": "boursa-event-101" if include_boursa else "kuna-event-101",
            "event_key": "catalyst-101",
            "claim_text": "Synthetic primary confirmation." if include_boursa else "Synthetic second editorial copy.",
        },
        {
            "finding_id": "f-101-sentiment",
            "security_code": "101",
            "ticker": "AAA",
            "source_id": "telegram_kuwaitstockex",
            "source_url": source_rows[3][1],
            "published_at": "2026-08-07T00:30:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "B",
            "raw_sha256": digest_by_source["telegram_kuwaitstockex"],
            "evidence_roles": ["COMMUNITY_SENTIMENT"],
            "signal_kind": "SENTIMENT",
            "direction": "POSITIVE",
            "fact_type": "ATTENTION",
            "strength": 0.90,
            "materiality": 0.50,
            "origin_id": "telegram-attention-101",
            "event_key": "sentiment-101",
            "claim_text": "Synthetic community attention.",
        },
        {
            "finding_id": "f-102-price",
            "security_code": "102",
            "ticker": "BBB",
            "source_id": "tradingview_screeners",
            "source_url": source_rows[0][1],
            "published_at": "2026-08-07T00:40:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "C",
            "raw_sha256": digest_by_source["tradingview_screeners"],
            "evidence_roles": ["MARKET_DISCOVERY"],
            "signal_kind": "PRICE_ACTIVITY",
            "direction": "NEGATIVE",
            "fact_type": "MOVER_DISCOVERY",
            "strength": 0.75,
            "materiality": 0.70,
            "origin_id": "tv-screen-102",
            "event_key": "price-102",
            "claim_text": "Synthetic negative activity finding.",
        },
        {
            "finding_id": "f-102-technical",
            "security_code": "102",
            "ticker": "BBB",
            "source_id": "investing_history",
            "source_url": source_rows[1][1],
            "published_at": "2026-08-07T00:35:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "C",
            "raw_sha256": digest_by_source["investing_history"],
            "evidence_roles": ["MARKET_DISCOVERY", "PRICE_HISTORY"],
            "signal_kind": "TECHNICAL",
            "direction": "NEGATIVE",
            "fact_type": "SECONDARY_TECHNICAL",
            "strength": 0.65,
            "materiality": 0.60,
            "origin_id": "investing-technical-102",
            "event_key": "technical-102",
            "claim_text": "Synthetic negative technical finding.",
        },
        {
            "finding_id": "f-102-risk",
            "security_code": "102",
            "ticker": "BBB",
            "source_id": "reuters_middle_east",
            "source_url": source_rows[2][1],
            "published_at": "2026-08-07T00:20:00+03:00",
            "available_at": "2026-08-07T00:50:00+03:00",
            "capture_mode": "PROSPECTIVE",
            "timing_grade": "B",
            "raw_sha256": digest_by_source["reuters_middle_east"],
            "evidence_roles": ["NEWS_ARCHIVE"],
            "signal_kind": "RISK",
            "direction": "NEGATIVE",
            "fact_type": "REGIONAL_CONTEXT",
            "strength": 0.70,
            "materiality": 0.80,
            "origin_id": "risk-102",
            "event_key": "risk-102",
            "claim_text": "Synthetic negative risk context.",
        },
    ]
    if include_boursa:
        findings.append(
            {
                "finding_id": "f-102-kuna-context",
                "security_code": "102",
                "ticker": "BBB",
                "source_id": "kuna",
                "source_url": "https://www.kuna.net.kw/",
                "published_at": "2026-08-07T00:15:00+03:00",
                "available_at": "2026-08-07T00:50:00+03:00",
                "capture_mode": "PROSPECTIVE",
                "timing_grade": "B",
                "raw_sha256": digest_by_source["kuna"],
                "evidence_roles": ["NEWS_ARCHIVE"],
                "signal_kind": "RISK",
                "direction": "NEUTRAL",
                "fact_type": "MACRO_CONTEXT",
                "strength": 0.40,
                "materiality": 0.30,
                "origin_id": "kuna-context-102",
                "event_key": "macro-context-102",
                "claim_text": "Synthetic independent government-news context.",
            }
        )
    with (root / "findings.jsonl").open("w", encoding="utf-8") as handle:
        for row in findings:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return root


__all__ = ["build_synthetic_network_run"]
