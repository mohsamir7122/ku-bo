from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .hashing import canonical_json_bytes, sha256_bytes, sha256_file


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_synthetic_valid_pack(root: Path) -> Path:
    """Create a tiny valid pack for contract tests only.

    The pack is synthetic and must never be presented as market evidence.
    """
    raw_dir = root / "raw"
    normalized = root / "normalized"
    manifests = root / "manifests"
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized.mkdir(parents=True, exist_ok=True)
    manifests.mkdir(parents=True, exist_ok=True)
    raw_specs = {
        "master.json": {"synthetic": True, "dataset": "security_master", "rows": 1},
        "status.json": {"synthetic": True, "dataset": "security_status_history", "rows": 1},
        "calendar.json": {"synthetic": True, "dataset": "trading_calendar", "rows": 1},
        "eod.json": {"synthetic": True, "dataset": "daily_eod", "rows": 1},
        "totals.json": {"synthetic": True, "dataset": "daily_market_totals", "rows": 1},
        "disclosures.json": {"synthetic": True, "dataset": "disclosures", "rows": 0},
        "corporate_actions.json": {"synthetic": True, "dataset": "corporate_actions", "rows": 0},
    }
    raw_hashes: dict[str, str] = {}
    artifacts: list[dict[str, Any]] = []
    for name, payload in raw_specs.items():
        content = canonical_json_bytes(payload)
        path = raw_dir / name
        path.write_bytes(content)
        digest = sha256_bytes(content)
        raw_hashes[name] = digest
        artifacts.append(
            {
                "path": f"raw/{name}",
                "sha256": digest,
                "size_bytes": len(content),
                "source_id": "boursa_kuwait",
                "source_url": "https://www.boursakuwait.com.kw/en/",
                "observed_at": "2026-08-06T14:00:00+03:00",
                "provider_as_of": "2026-08-06T13:15:00+03:00" if name in {"eod.json", "totals.json"} else None,
                "content_type": "application/json",
            }
        )
    (manifests / "file_manifest.json").write_text(json.dumps({"schema_version": "2.0", "artifacts": artifacts}, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    _write_csv(
        normalized / "security_master.csv",
        ["security_code", "ticker", "isin", "name_ar", "name_en", "board", "market_segment", "currency", "valid_from", "valid_to", "listing_status", "raw_sha256"],
        [{"security_code": "101", "ticker": "SYNTH", "isin": "KW0000000001", "name_ar": "اصطناعي", "name_en": "Synthetic", "board": "cash", "market_segment": "MAIN", "currency": "KWD", "valid_from": "2026-01-01", "valid_to": "", "listing_status": "TRADING", "raw_sha256": raw_hashes["master.json"]}],
    )
    _write_csv(
        normalized / "security_status_history.csv",
        ["security_code", "board", "status", "effective_from", "effective_to", "reason_code", "notice_id", "raw_sha256"],
        [{"security_code": "101", "board": "cash", "status": "TRADING", "effective_from": "2026-01-01", "effective_to": "", "reason_code": "SYNTHETIC", "notice_id": "S1", "raw_sha256": raw_hashes["status.json"]}],
    )
    _write_csv(
        normalized / "trading_calendar.csv",
        ["trade_date", "is_trading_day", "session_type", "session_regime_id", "continuous_start", "continuous_end", "trade_at_last_end", "raw_sha256"],
        [{"trade_date": "2026-08-06", "is_trading_day": "true", "session_type": "NORMAL", "session_regime_id": "POST_2025_10_12", "continuous_start": "09:00:00", "continuous_end": "13:00:00", "trade_at_last_end": "13:15:00", "raw_sha256": raw_hashes["calendar.json"]}],
    )
    _write_csv(
        normalized / "eod_ohlcv.csv",
        ["trade_date", "security_code", "ticker", "open_fils", "high_fils", "low_fils", "close_fils", "volume", "value_traded_kwd", "trade_count", "reference_price_fils", "trading_status", "corporate_action_status", "raw_sha256"],
        [{"trade_date": "2026-08-06", "security_code": "101", "ticker": "SYNTH", "open_fils": "100", "high_fils": "105", "low_fils": "99", "close_fils": "103", "volume": "1000", "value_traded_kwd": "103", "trade_count": "10", "reference_price_fils": "100", "trading_status": "TRADED", "corporate_action_status": "not_applicable", "raw_sha256": raw_hashes["eod.json"]}],
    )
    _write_csv(
        normalized / "daily_market_totals.csv",
        ["trade_date", "board", "traded_security_count", "total_volume", "total_value_kwd", "total_trade_count", "raw_sha256"],
        [{"trade_date": "2026-08-06", "board": "cash", "traded_security_count": "1", "total_volume": "1000", "total_value_kwd": "103", "total_trade_count": "10", "raw_sha256": raw_hashes["totals.json"]}],
    )
    _write_csv(
        normalized / "disclosures.csv",
        ["security_code", "ticker", "news_id", "announcement_type", "event_at", "published_at", "relation_type", "original_news_id", "fetched_at", "raw_sha256"],
        [],
    )
    _write_csv(
        normalized / "corporate_actions.csv",
        ["security_code", "ticker", "action_id", "action_type", "announcement_date", "ex_date", "record_date", "payment_date", "adjustment_factor", "factor_status", "raw_sha256"],
        [],
    )
    _write_csv(
        manifests / "query_ledger.csv",
        ["query_id", "dataset", "window_from", "window_to", "pages_declared", "pages_received", "result_count_declared", "rows_normalized", "zero_result", "raw_sha256"],
        [
            {"query_id": "q-disclosures", "dataset": "disclosures", "window_from": "2026-08-06", "window_to": "2026-08-06", "pages_declared": "1", "pages_received": "1", "result_count_declared": "0", "rows_normalized": "0", "zero_result": "true", "raw_sha256": raw_hashes["disclosures.json"]},
            {"query_id": "q-ca", "dataset": "corporate_actions", "window_from": "2026-08-06", "window_to": "2026-08-06", "pages_declared": "1", "pages_received": "1", "result_count_declared": "0", "rows_normalized": "0", "zero_result": "true", "raw_sha256": raw_hashes["corporate_actions.json"]},
        ],
    )
    collection = {
        "schema_version": "2.0",
        "pack_id": "synthetic-contract-pack",
        "as_of": "2026-08-06T14:00:00+03:00",
        "window_from": "2026-08-06",
        "window_to": "2026-08-06",
        "timezone": "Asia/Kuwait",
        "included_boards": ["cash"],
        "run_status": "QUALIFIED",
        "budget": {"max_requests": 20, "max_raw_bytes": 1000000, "max_wall_seconds": 300, "max_zero_yield_attempts_per_family": 2},
        "usage": {"requests": 7, "raw_bytes": sum(item["size_bytes"] for item in artifacts), "wall_seconds": 1},
        "synthetic": True,
    }
    (manifests / "collection_run.json").write_text(json.dumps(collection, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    mapping = {
        "security_master": ("security_master.csv", "master.json"),
        "security_status_history": ("security_status_history.csv", "status.json"),
        "trading_calendar": ("trading_calendar.csv", "calendar.json"),
        "daily_eod": ("eod_ohlcv.csv", "eod.json"),
        "daily_market_totals": ("daily_market_totals.csv", "totals.json"),
        "official_disclosures": ("disclosures.csv", "disclosures.json"),
        "corporate_actions": ("corporate_actions.csv", "corporate_actions.json"),
    }
    attestations = []
    for capability, (filename, raw_name) in mapping.items():
        attestations.append(
            {
                "capability": capability,
                "status": "PASS",
                "source_ids": ["boursa_kuwait"],
                "evidence_hashes": [raw_hashes[raw_name]],
                "normalized_path": f"normalized/{filename}",
                "normalized_sha256": sha256_file(normalized / filename),
                "validator_id": f"kubo.{capability}",
                "validator_version": "2.0",
                "validated_at": "2026-08-06T14:00:00+03:00",
                "access_class": "PUBLIC_OFFICIAL",
                "coverage_numerator": 1,
                "coverage_denominator": 1,
                "limitations": ["SYNTHETIC_TEST_DATA_ONLY"],
            }
        )
    capability_report = {"schema_version": "2.0", "pack_id": "synthetic-contract-pack", "as_of": "2026-08-06T14:00:00+03:00", "attestations": attestations}
    (manifests / "capability_report.json").write_text(json.dumps(capability_report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return root


__all__ = ["build_synthetic_valid_pack"]
